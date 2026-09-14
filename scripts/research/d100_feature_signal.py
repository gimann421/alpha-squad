"""D100 -- do M6's four EXISTING features already separate the realized top-6 out-of-sample?

Read-only diagnostic. Imports the production feature loaders and reads `uncertainty_predictions`;
writes nothing to the database and touches no production module. Run it with

    uv run python scripts/research/d100_feature_signal.py --out <dir>

PRE-REGISTRATION (written before any result was inspected; see
docs/D100_FEATURE_SIGNAL_DIAGNOSTIC.md sections 4 and 10)
==========================================================================================

UNIVERSE.  For each season S in `BACKTEST_SEASONS` (2021-2025) and each position M6 actually
models (QB/RB/WR/TE -- M6 has no K/DST model at all, see `models/uncertainty/run.py::POSITIONS`),
the candidate pool is M6's own prediction set for S: every player carrying a row in
`uncertainty_predictions` under the production `model_version`. That is the only universe on
which *every* method under comparison has a score, so it is the one the primary comparison runs
on. `UNIVERSE_PRESEASON` -- the strictly preseason-available set returned by production's
`load_season_level_projection_data` -- is reported as a robustness check for the feature-only
methods, since M6 is undefined on the part of it that never played.

TARGET.  Realized `total_fantasy_points_ppr` for season S from `player_season_stats`, LEFT
joined and defaulted to 0.0 (a player with no season-S line scored nothing for a fantasy roster).
Realized top-6 is the six highest within (position, season) inside the universe, ties broken by
`player_id`. Season S's outcomes are used ONLY to (a) define this evaluation target and (b) label
training rows of *other* seasons for the learned diagnostics. They never enter a feature, a
threshold, a transform, a hyperparameter or a model-selection choice for S.

METHODS (all fixed in advance, none tuned).
  M6        production point prediction -- the incumbent, the thing to beat.
  U_ppg     rank by `prior_ppg` descending.
  U_games   rank by `prior_games` descending.
  U_wtotal  rank by `prior_weighted_total` descending.
  U_ecr     rank by `preseason_ecr_rank` ASCENDING (rank 1 is best; the only inverted feature).
  R2        mean of all four within-(position,season) percentile ranks (ECR reversed).
  R3        mean of the three magnitude ranks (ppg, weighted total, ECR) -- drops `prior_games`.
  R4        mean of (ppg, ECR) ranks only.
  D_rank    Ridge(alpha=1.0), pooled over positions, on the four percentile-ranked features,
            target = within-(position,season) percentile rank of realized points.
  D_clf     LogisticRegression(C=1.0, class_weight="balanced"), pooled, same four ranked
            features, target = binary realized-top-6 membership.
  D_gbm     M6's OWN estimator and hyperparameters (CatBoost, 150/3/0.08, MAE, seed 42) on the
            four RAW features, per position, target = raw realized points. This is the control
            that separates H4 from H3: same functional form, same features, only the training
            split changes.
  ORACLE    rank by realized points. 6/6 by construction. Reported only as the trivial bound;
            it is NOT an estimate of what the features can do and is never called a ceiling.

SPLITS.  Every learned diagnostic is fitted twice.
  LOSO  train on the four non-held-out seasons, evaluate on the fifth, rotate through all five.
        This is the brief's prescribed information-content test. It is NOT deployable -- a 2021
        fit sees 2024 -- and is labelled accordingly everywhere.
  WF    walk-forward: train only on seasons strictly before S. 2021 has no training season and
        is therefore undefined; 2022 trains on one. This is the deployable comparison, and it is
        the only one entitled to be set against M6 as a like-for-like.

METRICS, per (season, position, method): top-6 overlap (0-6), precision@6, recall@6 (all three
coincide here because both sets have exactly six members, and are reported anyway because the
brief names them), Spearman rank correlation against realized points over the whole pool, and
Mann-Whitney AUC for realized-top-6 membership. Season-level consistency (how many of the five
seasons a method matches or beats M6) is reported alongside every mean, because five seasons are
the independent clusters and a pooled player-level number would manufacture precision the design
does not have.

HYPOTHESES (Phase 7). H2 "right information, wrong within-position order" predicts some
feature-only method beats M6 on overlap out-of-sample. H3 "the information is absent" predicts
NOTHING -- including the LOSO diagnostics, which are allowed to cheat on season ordering --
separates top-6 materially better than M6. H4 "M6's functional form fails to extract it" requires
D_gbm/D_rank under WF to beat M6 with the same features; a gain that appears only under LOSO is
evidence about information content, not about M6's architecture.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.linear_model import LogisticRegression, Ridge

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.models.established.season_level import (
    FEATURES,
    load_season_level_projection_data,
)
from alpha_squad.models.uncertainty.run import MODEL_VERSION, POSITIONS

DB = "data/alpha_squad.duckdb"
TOP_N = 6
#: Features where a LARGER raw value means a better player. `preseason_ecr_rank` is a rank, so
#: it is the one feature where smaller is better; every ordering below respects this explicitly.
HIGHER_IS_BETTER = {
    "prior_ppg": True,
    "prior_games": True,
    "prior_weighted_total": True,
    "preseason_ecr_rank": False,
}
#: Pre-specified fixed rank aggregations (Phase 4B). Nothing here was chosen after seeing a result.
RANK_AGGREGATIONS = {
    "R2": ("prior_ppg", "prior_games", "prior_weighted_total", "preseason_ecr_rank"),
    "R3": ("prior_ppg", "prior_weighted_total", "preseason_ecr_rank"),
    "R4": ("prior_ppg", "preseason_ecr_rank"),
}


def _new_m6_estimator() -> CatBoostRegressor:
    """M6's estimator, hyperparameter for hyperparameter (`uncertainty/run.py::_new_model`).
    Rebuilt here rather than imported so the diagnostic cannot accidentally mutate production
    state; the values are asserted equal in tests/test_d100_feature_signal.py."""
    return CatBoostRegressor(
        iterations=150,
        depth=3,
        learning_rate=0.08,
        loss_function="MAE",
        verbose=False,
        random_seed=42,
    )


def pct_rank(values: np.ndarray, higher_is_better: bool) -> np.ndarray:
    """Within-group percentile rank in [0, 1], 1.0 = best. Feature-only: never sees an outcome."""
    order = pd.Series(values).rank(ascending=not higher_is_better, method="average").to_numpy()
    n = len(values)
    return (n - order) / (n - 1) if n > 1 else np.full(n, 0.5)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney AUC: P(score of a random positive > score of a random negative), ties at .5.
    Higher score must mean 'more likely top-6' for every caller."""
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def top_set(frame: pd.DataFrame, column: str, ascending: bool, n: int = TOP_N) -> set[str]:
    ordered = frame.sort_values([column, "player_id"], ascending=[ascending, True])
    return set(ordered["player_id"].head(n))


def load_universe(con: duckdb.DuckDBPyConnection, universe: str = "m6") -> pd.DataFrame:
    """M6's prediction set for each backtest season, with production features and realized points.

    The features are recomputed through production's own preseason loader rather than re-derived
    here, so a drift in the feature definition breaks this script instead of silently changing
    what it measures."""
    if universe not in ("m6", "preseason"):
        raise ValueError(f"unknown universe {universe!r}")
    frames = []
    for season in BACKTEST_SEASONS:
        realized = con.execute(
            "SELECT player_id, total_fantasy_points_ppr AS realized FROM player_season_stats "
            "WHERE season = ?",
            [season],
        ).fetchdf()
        preds = con.execute(
            "SELECT player_id, position, point_prediction FROM uncertainty_predictions "
            "WHERE season = ? AND model_version = ?",
            [season, MODEL_VERSION],
        ).fetchdf()
        for position in POSITIONS:
            feats = load_season_level_projection_data(con, position, season)
            feats = feats.assign(season=season, position=position)
            merged = feats.merge(
                preds[preds["position"] == position][["player_id", "point_prediction"]],
                on="player_id",
                how="left",
            ).merge(realized, on="player_id", how="left")
            merged["realized"] = merged["realized"].fillna(0.0)
            frames.append(merged)
    pool = pd.concat(frames, ignore_index=True)
    if universe == "m6":
        # The pre-registered primary universe. Enforced here rather than left to each metric:
        # if M6 is scored on a pool the feature-only methods do not share, every comparison
        # between them silently compares different denominators. `point_prediction` is null
        # exactly for players with no season-S stat line, whom M6's training loader's INNER
        # JOIN on the target season drops -- all of whom realized 0.0 and are easy negatives.
        pool = pool[pool["point_prediction"].notna()].reset_index(drop=True)
    return pool


def add_ranked_features(pool: pd.DataFrame) -> pd.DataFrame:
    """Percentile-rank each feature and the realized target WITHIN (season, position).

    The feature transform uses only that group's features, so it is available at preseason time.
    The target transform is an evaluation/labelling construct and is used for a season only when
    that season is a TRAINING season."""
    out = []
    for (_, _), group in pool.groupby(["season", "position"], sort=False):
        group = group.copy()
        for feature in FEATURES:
            group[f"r_{feature}"] = pct_rank(group[feature].to_numpy(), HIGHER_IS_BETTER[feature])
        group["r_realized"] = pct_rank(group["realized"].to_numpy(), True)
        group["is_top6"] = 0
        top = top_set(group, "realized", ascending=False)
        group.loc[group["player_id"].isin(top), "is_top6"] = 1
        out.append(group)
    return pd.concat(out, ignore_index=True)


def fit_learned(pool: pd.DataFrame, split: str) -> pd.DataFrame:
    """Attach D_rank / D_clf / D_gbm scores under `split` in {"loso", "wf"}.

    Higher score always means 'more likely to be top-6', for every one of the three."""
    ranked = [f"r_{f}" for f in FEATURES]
    pool = pool.copy()
    for column in ("D_rank", "D_clf", "D_gbm"):
        pool[f"{column}_{split}"] = np.nan

    for season in BACKTEST_SEASONS:
        train = (
            pool[pool["season"] != season] if split == "loso" else pool[pool["season"] < season]
        )
        held = pool["season"] == season
        if train.empty or train["season"].nunique() < 1:
            continue

        ridge = Ridge(alpha=1.0).fit(train[ranked].to_numpy(), train["r_realized"].to_numpy())
        pool.loc[held, f"D_rank_{split}"] = ridge.predict(pool.loc[held, ranked].to_numpy())

        if train["is_top6"].nunique() > 1:
            clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)
            clf.fit(train[ranked].to_numpy(), train["is_top6"].to_numpy())
            pool.loc[held, f"D_clf_{split}"] = clf.predict_proba(
                pool.loc[held, ranked].to_numpy()
            )[:, 1]

        for position in POSITIONS:
            tr = train[train["position"] == position]
            mask = held & (pool["position"] == position)
            if len(tr) < 30 or not mask.any():
                continue
            gbm = _new_m6_estimator()
            gbm.fit(tr[FEATURES].to_numpy(), tr["realized"].to_numpy())
            pool.loc[mask, f"D_gbm_{split}"] = gbm.predict(pool.loc[mask, FEATURES].to_numpy())
    return pool


def score_columns() -> dict[str, tuple[str, bool]]:
    """method -> (column, ascending). `ascending=True` means a SMALLER value is better."""
    methods: dict[str, tuple[str, bool]] = {
        "M6": ("point_prediction", False),
        "U_ppg": ("prior_ppg", False),
        "U_games": ("prior_games", False),
        "U_wtotal": ("prior_weighted_total", False),
        "U_ecr": ("preseason_ecr_rank", True),
    }
    for name in RANK_AGGREGATIONS:
        methods[name] = (name, False)
    for base in ("D_rank", "D_clf", "D_gbm"):
        for split in ("loso", "wf"):
            methods[f"{base}_{split}"] = (f"{base}_{split}", False)
    methods["ORACLE"] = ("realized", False)
    return methods


def evaluate(pool: pd.DataFrame) -> list[dict]:
    rows = []
    methods = score_columns()
    for (season, position), group in pool.groupby(["season", "position"], sort=True):
        realized_top = top_set(group, "realized", ascending=False)
        labels = group["player_id"].isin(realized_top).to_numpy().astype(int)
        for method, (column, ascending) in methods.items():
            usable = group[group[column].notna()]
            if len(usable) < TOP_N or usable[column].nunique() < 2:
                continue
            picked = top_set(usable, column, ascending=ascending)
            overlap = len(picked & realized_top)
            direction = -1.0 if ascending else 1.0
            sub_labels = usable["player_id"].isin(realized_top).to_numpy().astype(int)
            rows.append(
                {
                    "season": int(season),
                    "position": position,
                    "method": method,
                    "n_pool": int(len(usable)),
                    "n_positives": int(labels.sum()),
                    "overlap": overlap,
                    "precision_at_6": overlap / len(picked),
                    "recall_at_6": overlap / len(realized_top),
                    "spearman": spearman(
                        direction * usable[column].to_numpy(), usable["realized"].to_numpy()
                    ),
                    "auc": auc(direction * usable[column].to_numpy(), sub_labels),
                }
            )
    return rows


def _table(rows: list[dict], metric: str, methods: list[str], title: str) -> str:
    lines = [title, "  " + f"{'method':<14}" + "".join(f"{p:>8}" for p in POSITIONS) + f"{'ALL':>9}"]
    for method in methods:
        cells = []
        for position in POSITIONS:
            vals = [r[metric] for r in rows if r["method"] == method and r["position"] == position]
            cells.append(f"{mean(vals):>8.2f}" if vals else f"{'-':>8}")
        allv = [r[metric] for r in rows if r["method"] == method]
        cells.append(f"{mean(allv):>9.3f}" if allv else f"{'-':>9}")
        lines.append(f"  {method:<14}" + "".join(cells))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB)
    parser.add_argument("--out", required=True)
    parser.add_argument("--universe", default="m6", choices=("m6", "preseason"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}", flush=True)
    print(f"M6 positions: {POSITIONS}  (no K/DST model exists)  seasons {BACKTEST_SEASONS}\n")

    print(f"universe: {args.universe}\n")
    pool = add_ranked_features(load_universe(con, args.universe))
    for name, features in RANK_AGGREGATIONS.items():
        pool[name] = pool[[f"r_{f}" for f in features]].mean(axis=1)

    #: Structural ceiling: how much of each season's true positional top-6 is even reachable?
    reach = []
    for season in BACKTEST_SEASONS:
        for position in POSITIONS:
            whole = con.execute(
                "SELECT player_id, total_fantasy_points_ppr AS realized FROM player_season_stats "
                "WHERE season = ? AND position = ?",
                [season, position],
            ).fetchdf()
            true_top = top_set(whole, "realized", ascending=False)
            modelled = set(pool[(pool["season"] == season) & (pool["position"] == position)]
                           ["player_id"])
            reach.append(
                {
                    "season": season,
                    "position": position,
                    "true_top6_in_m6_pool": len(true_top & modelled),
                    "pool_size": len(modelled),
                }
            )

    pool = fit_learned(pool, "loso")
    pool = fit_learned(pool, "wf")
    rows = evaluate(pool)
    (out / "d100_rows.json").write_text(json.dumps(rows))
    (out / "d100_reach.json").write_text(json.dumps(reach))

    order = [
        "M6", "U_ppg", "U_games", "U_wtotal", "U_ecr", "R2", "R3", "R4",
        "D_rank_wf", "D_clf_wf", "D_gbm_wf", "D_rank_loso", "D_clf_loso", "D_gbm_loso", "ORACLE",
    ]
    print(_table(rows, "overlap", order, "TOP-6 OVERLAP (of 6), mean over seasons"))
    print()
    print(_table(rows, "auc", order, "AUC for realized-top-6 membership"))
    print()
    print(_table(rows, "spearman", order, "SPEARMAN vs realized points (whole pool)"))

    print("\nSEASON-LEVEL CONSISTENCY -- paired vs M6, summed overlap over the four positions")
    print("  Seasons are the independent clusters: k=5 (k=4 for walk-forward, which cannot score")
    print("  2021). t(k-1, .975) two-sided; a CI spanning 0 means 'not resolved', not 'no effect'.")
    base = defaultdict(float)
    for r in rows:
        if r["method"] == "M6":
            base[r["season"]] += r["overlap"]
    t_crit = {4: 2.776, 3: 3.182, 2: 4.303}
    print(f"  {'method':<14}" + "".join(f"{s:>7}" for s in BACKTEST_SEASONS)
          + f"{'mean d':>9}{'wins':>7}{'t':>8}{'95% CI':>18}")
    for method in order:
        per = defaultdict(float)
        seen = defaultdict(int)
        for r in rows:
            if r["method"] == method:
                per[r["season"]] += r["overlap"]
                seen[r["season"]] += 1
        seasons = [s for s in BACKTEST_SEASONS if seen.get(s, 0) == len(POSITIONS)]
        if not seasons:
            continue
        diffs = [per[s] - base[s] for s in seasons]
        cells = "".join(
            f"{per[s]:>7.0f}" if s in seasons else f"{'-':>7}" for s in BACKTEST_SEASONS
        )
        k = len(diffs)
        wins = sum(1 for d in diffs if d > 0)
        md = mean(diffs)
        if k >= 3 and stdev(diffs) > 0:
            se = stdev(diffs) / k**0.5
            tc = t_crit.get(k - 1, 2.776)
            stat = f"{md / se:>8.2f}"
            ci = f"[{md - tc * se:>+6.2f}, {md + tc * se:>+6.2f}]".rjust(18)
        else:
            stat, ci = f"{'n/a':>8}", f"{'n/a':>18}"
        print(f"  {method:<14}{cells}{md:>+9.2f}{wins:>4}/{k:<2}{stat}{ci}")

    print("\nSTRUCTURAL REACH -- how many of the position's TRUE top-6 are in M6's pool at all")
    print(f"  {'pos':<6}" + "".join(f"{s:>8}" for s in BACKTEST_SEASONS) + f"{'mean':>9}")
    for position in POSITIONS:
        vals = [
            next(r["true_top6_in_m6_pool"] for r in reach
                 if r["season"] == s and r["position"] == position)
            for s in BACKTEST_SEASONS
        ]
        print(f"  {position:<6}" + "".join(f"{v:>8}" for v in vals) + f"{mean(vals):>9.2f}")

    print("\nFEATURE DISTRIBUTIONS -- mean value, realized top-6 vs the rest (Phase 4A)")
    print(f"  {'pos':<6}{'feature':<24}{'top6':>10}{'rest':>10}{'ratio':>9}")
    for position in POSITIONS:
        sub = pool[pool["position"] == position]
        for feature in FEATURES:
            t = sub[sub["is_top6"] == 1][feature].mean()
            r = sub[sub["is_top6"] == 0][feature].mean()
            print(f"  {position:<6}{feature:<24}{t:>10.2f}{r:>10.2f}{(t / r if r else 0):>9.2f}")

    print("\nFEATURE REDUNDANCY -- Pearson r among the four raw features (pooled, all positions)")
    corr = pool[FEATURES].corr()
    print(f"  {'':<24}" + "".join(f"{f[:10]:>12}" for f in FEATURES))
    for feature in FEATURES:
        print(f"  {feature:<24}" + "".join(f"{corr.loc[feature, g]:>12.3f}" for g in FEATURES))
    implied = pool["prior_ppg"] * pool["prior_games"]
    print(f"  corr(prior_ppg * prior_games, prior_weighted_total) = "
          f"{implied.corr(pool['prior_weighted_total']):.4f}")


if __name__ == "__main__":
    main()
