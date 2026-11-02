"""Walk-forward backtest driver for the ROS QB models (D116).

Protocol (fixed before results were inspected):

* TEST seasons are evaluated one at a time, in order. For test season ``T`` every model is fitted on
  rows from seasons ``< T`` ONLY (all snapshot weeks of those seasons are usable for training),
  then scored on ``T``'s evaluation-week snapshots (weeks 6-10 by default). No row of season ``T``
  reaches ``fit`` -- not for imputation medians, scaling, ridge penalty, rank->points map, blend
  weight or probability calibrator. ``tests/leakage/test_ros_leakage.py`` asserts this.
* The pairwise-probability calibrator for season ``T`` is fitted on leave-one-season-out
  out-of-fold predictions inside the TRAINING seasons, never on ``T``.
* Population = QBs inside the published top 36 of the archived ``ros-qb`` consensus on the
  snapshot date; identical for every model.
* Only snapshots whose whole target horizon has been played (``target_complete``) are scored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_squad.ros import metrics as M
from alpha_squad.ros.models import ALL_MODELS, add_derived, make_model
from alpha_squad.ros.snapshots import DEFAULT_WEEKS

BASELINES = ("S2D", "A_ecr")
ORDINAL_ONLY = ("ECR_order",)


@dataclass
class BacktestResult:
    preds: pd.DataFrame  # test-season predictions, long: one row per (model, player-snapshot)
    oof: pd.DataFrame  # leave-one-season-out predictions inside training seasons (calibrators)
    train_sizes: dict[int, int]
    models: list[str]
    eval_weeks: tuple[int, ...]


def _predict_frame(model_name: str, model, df: pd.DataFrame, kind: str) -> pd.DataFrame:
    out = df[
        [
            "season",
            "snapshot_week",
            "scrape_date",
            "gsis_id",
            "player",
            "ecr",
            "ecr_rank",
            "n_remaining",
            "rush_att_pg",
            "y_rate",
            "y_total",
            "y_apps",
        ]
    ].copy()
    out["model"] = model_name
    out["pred_rate"] = model.predict_rate(df)
    out["pred_total"] = out["pred_rate"] * df["n_remaining"].to_numpy()
    out["kind"] = kind
    return out


def run_backtest(
    panel: pd.DataFrame,
    models: tuple[str, ...] = (*ALL_MODELS, "ECR_order"),
    test_seasons: tuple[int, ...] = (2022, 2023, 2024, 2025),
    eval_weeks: tuple[int, ...] = DEFAULT_WEEKS,
    compute_oof: bool = True,
) -> BacktestResult:
    df = add_derived(panel[panel["target_complete"]].reset_index(drop=True))
    preds, oofs, sizes = [], [], {}
    for T in test_seasons:
        train = df[df["season"] < T].reset_index(drop=True)
        test = df[(df["season"] == T) & df["snapshot_week"].isin(eval_weeks)].reset_index(drop=True)
        if train.empty or test.empty:
            continue
        sizes[T] = int(len(train))
        for name in models:
            m = make_model(name).fit(train)
            preds.append(_predict_frame(name, m, test, "test"))
            if compute_oof and name not in ORDINAL_ONLY:
                for s in sorted(train["season"].unique()):
                    inner_tr = train[train["season"] != s]
                    inner_te = train[
                        (train["season"] == s) & train["snapshot_week"].isin(eval_weeks)
                    ]
                    if inner_tr.empty or inner_te.empty:
                        continue
                    mi = make_model(name).fit(inner_tr.reset_index(drop=True))
                    o = _predict_frame(name, mi, inner_te.reset_index(drop=True), "oof")
                    o["test_season"] = T
                    oofs.append(o)
            elif compute_oof:
                inner_te = train[train["snapshot_week"].isin(eval_weeks)]
                o = _predict_frame(name, m, inner_te.reset_index(drop=True), "oof")
                o["test_season"] = T
                oofs.append(o)
    return BacktestResult(
        pd.concat(preds, ignore_index=True),
        pd.concat(oofs, ignore_index=True) if oofs else pd.DataFrame(),
        sizes,
        list(models),
        eval_weeks,
    )


# ----------------------------------------------------------------------------------------
# per-snapshot metric table
# ----------------------------------------------------------------------------------------
def snapshot_metrics(preds: pd.DataFrame, oof: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (model, season, snapshot) with every snapshot-level metric."""
    rows = []
    # calibrators per (model, test_season)
    cal: dict[tuple[str, int], M.PairProb] = {}
    if oof is not None and len(oof):
        for (name, T), g in oof.groupby(["model", "test_season"]):
            dp, wn = [], []
            for _, gs in g.groupby(["season", "snapshot_week"]):
                gs = gs.reset_index(drop=True)
                pf = M.pair_frame(gs, M.band_pairs(gs, 4, 20), "pred_total")
                pf = pf[~pf["tie"] & ~pf["pred_tie"]]
                dp.append(pf["dpred"].to_numpy())
                wn.append(pf["win"].to_numpy())
            if dp:
                cal[(name, int(T))] = M.PairProb().fit(np.concatenate(dp), np.concatenate(wn))
    for (name, season, week), g in preds.groupby(["model", "season", "snapshot_week"]):
        g = g.reset_index(drop=True)
        rec: dict = {"model": name, "season": int(season), "snapshot_week": int(week)}
        rec.update(M.rank_metrics_snapshot(g))
        rec.update(M.pairwise_snapshot(g))
        rec.update(M.regret_snapshot(g))
        if name not in ORDINAL_ONLY:
            pm = M.point_metrics(g["y_total"].to_numpy(), g["pred_total"].to_numpy())
            rec.update(mae=pm["mae"], rmse=pm["rmse"], mean_error=pm["mean_error"])
            cp = cal.get((name, int(season)))
            if cp is not None:
                pf = M.pair_frame(g, M.band_pairs(g, 4, 20))
                pf = pf[~pf["tie"] & ~pf["pred_tie"]]
                if len(pf):
                    p = cp.prob(pf["dpred"].to_numpy())
                    rec.update(
                        brier=M.brier(p, pf["win"].to_numpy()),
                        logloss=M.logloss(p, pf["win"].to_numpy()),
                        n_prob_pairs=float(len(pf)),
                    )
        rows.append(rec)
    return pd.DataFrame(rows)


def summarize(
    snap: pd.DataFrame, metric_cols: list[str], baseline: str, n_boot: int = 4000
) -> pd.DataFrame:
    """Per model: point estimate and 95% season/snapshot-block bootstrap CI for each metric, plus the
    paired difference vs ``baseline`` (same resamples) and its CI."""
    wide = snap.pivot_table(index=["season", "snapshot_week"], columns="model", values=metric_cols)
    models = sorted(snap["model"].unique())
    rows = []
    # one shared resample across ALL (model, metric) columns -> paired differences are valid
    flat = pd.DataFrame(
        {f"{m}|{c}": wide[(c, m)] for c in metric_cols for m in models if (c, m) in wide.columns}
    )
    flat = flat.reset_index()
    cols = [c for c in flat.columns if "|" in c]
    point, draws = M.block_bootstrap(flat, cols, n_boot=n_boot)
    pt = dict(zip(cols, point, strict=True))
    for c in metric_cols:
        for m in models:
            key = f"{m}|{c}"
            if key not in draws:
                continue
            lo, hi = M.ci(draws[key])
            rec = {"metric": c, "model": m, "estimate": pt[key], "ci_lo": lo, "ci_hi": hi}
            bkey = f"{baseline}|{c}"
            if bkey in draws and m != baseline:
                d = draws[key] - draws[bkey]
                dl, dh = M.ci(d)
                rec.update(
                    diff_vs_baseline=pt[key] - pt[bkey],
                    diff_lo=dl,
                    diff_hi=dh,
                    p_better=float(np.mean(d > 0)),
                )
            rows.append(rec)
    return pd.DataFrame(rows)


def season_table(snap: pd.DataFrame, col: str) -> pd.DataFrame:
    return snap.groupby(["model", "season"])[col].mean().unstack("season")


def point_by_group(preds: pd.DataFrame, model: str) -> dict[str, pd.DataFrame]:
    g = preds[preds["model"] == model].copy()
    out: dict[str, pd.DataFrame] = {}

    def agg(by):
        return g.groupby(by).apply(
            lambda x: pd.Series(
                M.point_metrics(x["y_total"].to_numpy(), x["pred_total"].to_numpy())
            ),
            include_groups=False,
        )

    out["week"] = agg("snapshot_week")
    out["season"] = agg("season")
    g["tier"] = pd.cut(
        g["ecr_rank"], [0, 6, 12, 24, 36], labels=["QB1-6", "QB7-12", "QB13-24", "QB25-36"]
    )
    out["tier"] = agg("tier")
    g["profile"] = np.where(
        g["rush_att_pg"].fillna(0) >= M.RUSHER_ATT_PG, "rusher(>=5 car/g)", "pocket"
    )
    out["rushing_profile"] = agg("profile")
    g["pred_quartile"] = g.groupby(["season", "snapshot_week"])["pred_total"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 4, labels=["Q4(low)", "Q3", "Q2", "Q1(high)"])
    )
    out["pred_quartile"] = agg("pred_quartile")
    return out


def save_result(res: BacktestResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    res.preds.to_parquet(out_dir / "test_predictions.parquet", index=False)
    if len(res.oof):
        res.oof.to_parquet(out_dir / "oof_predictions.parquet", index=False)
    (out_dir / "run_meta.json").write_text(
        json.dumps(
            {
                "train_sizes": res.train_sizes,
                "models": res.models,
                "eval_weeks": list(res.eval_weeks),
            },
            indent=2,
        )
    )
