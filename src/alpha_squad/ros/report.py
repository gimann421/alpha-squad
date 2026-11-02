"""The reproducible end-to-end evaluation: ``alpha-squad ros backtest`` (D116).

Runs, in order: panel (re)build -> walk-forward QB backtest of every model -> decision metrics with
season/snapshot block-bootstrap intervals -> breakdowns and ablations -> Monte Carlo validation ->
roster-level (market-priced swap) backtest -> markdown tables.

Everything it prints was computed by this function in this run. Nothing is cached between runs
except the raw data files (and the panel built from them, which is rebuilt on request).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_squad.league.context import load_league_context
from alpha_squad.ros import backtest as BT
from alpha_squad.ros import metrics as M
from alpha_squad.ros import noise as NZ
from alpha_squad.ros import rosterbench as RB
from alpha_squad.ros.lineup import UNAVAILABLE
from alpha_squad.ros.models import (
    ALL_MODELS,
    EXPLORATORY,
    add_derived,
    make_model,
)
from alpha_squad.ros.trade import Asset, simulate_assets

MAIN_MODELS = ("ECR_order", *ALL_MODELS)
ABLATIONS = tuple(
    f"{b}-{g}"
    for b, gs in (
        (
            "D_usage",
            ("RECENT", "USAGE", "CONTEXT", "PRIOR", "SEASON", "SCHED", "INJ", "RZRUSH", "TEAMENV"),
        ),
        ("E_full", ("ECR", "RECENT", "USAGE", "CONTEXT", "PRIOR", "SEASON")),
    )
    for g in gs
)
TEST_SEASONS = (2022, 2023, 2024, 2025)
KEY_MODELS = ("ECR_order", "A_ecr", "S2D", "C_recent", "D_usage", "E_full", "E_avg")


# ----------------------------------------------------------------------------------------
# formatting
# ----------------------------------------------------------------------------------------
def md(df: pd.DataFrame, floatfmt: str = "{:.3f}", index: bool = False) -> str:
    d = df.reset_index() if index else df
    cols = list(d.columns)
    out = [
        "| " + " | ".join(str(c) for c in cols) + " |",
        "|" + "|".join("---" for _ in cols) + "|",
    ]
    for _, r in d.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float | np.floating):
                cells.append("" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def est_ci(row, digits=3) -> str:
    f = f"{{:.{digits}f}}"
    return f"{f.format(row['estimate'])} [{f.format(row['ci_lo'])}, {f.format(row['ci_hi'])}]"


def diff_ci(row, b, digits=3) -> str:
    k = f"diff_vs_{b}"
    if k not in row or pd.isna(row.get(k)):
        return ""
    f = f"{{:+.{digits}f}}"
    return f"{f.format(row[k])} [{f.format(row[f'{k}_lo'])}, {f.format(row[f'{k}_hi'])}]"


def summarize_two(
    snap: pd.DataFrame, cols: list[str], bases: tuple[str, str], n_boot: int
) -> pd.DataFrame:
    """Summary with paired differences against two baselines on one shared resample."""
    s1 = BT.summarize(snap, cols, bases[0], n_boot)
    s2 = BT.summarize(snap, cols, bases[1], n_boot)
    keep = ["metric", "model", "estimate", "ci_lo", "ci_hi"]
    out = s1[keep + [c for c in s1.columns if c.startswith("diff")]].rename(
        columns={c: f"{c}_{bases[0]}" for c in s1.columns if c.startswith(("diff", "p_better"))}
    )
    t2 = s2[
        ["metric", "model"] + [c for c in s2.columns if c.startswith(("diff", "p_better"))]
    ].rename(
        columns={c: f"{c}_{bases[1]}" for c in s2.columns if c.startswith(("diff", "p_better"))}
    )
    out = out.merge(t2, on=["metric", "model"], how="left")
    # normalise names to diff_vs_<b>, diff_vs_<b>_lo/hi
    ren = {}
    for b in bases:
        ren[f"diff_vs_baseline_{b}"] = f"diff_vs_{b}"
        ren[f"diff_lo_{b}"] = f"diff_vs_{b}_lo"
        ren[f"diff_hi_{b}"] = f"diff_vs_{b}_hi"
        ren[f"p_better_{b}"] = f"p_better_vs_{b}"
    return out.rename(columns=ren)


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


# ----------------------------------------------------------------------------------------
# analyses
# ----------------------------------------------------------------------------------------
def trust_ecr_tables(preds: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pair-level view of when the published ECR order is right, using only information in the
    snapshot (ECR gap, tier, expert dispersion, agreement with S2D) to define the strata."""
    rows = []
    wide = preds.pivot_table(
        index=["season", "snapshot_week", "gsis_id"], columns="model", values="pred_total"
    )
    base = preds[preds["model"] == "ECR_order"].set_index(["season", "snapshot_week", "gsis_id"])
    base = base.join(wide[["S2D", "D_usage", "A_ecr"]])
    for (s, w), g in base.groupby(level=[0, 1]):
        g = g.reset_index(drop=True)
        for i, j in M.band_pairs(g, 1, 24):
            a, b = (i, j) if g.at[i, "ecr"] < g.at[j, "ecr"] else (j, i)  # a = ECR-favoured
            nbar = (g.at[a, "n_remaining"] + g.at[b, "n_remaining"]) / 2
            dact = g.at[a, "y_total"] - g.at[b, "y_total"]
            if abs(dact) < M.TIE_PTS_PER_GAME * nbar:
                continue
            rows.append(
                dict(
                    season=s,
                    week=w,
                    ecr_gap=g.at[b, "ecr"] - g.at[a, "ecr"],
                    top_rank=g.at[a, "ecr_rank"],
                    ecr_right=float(dact > 0),
                    s2d_agrees=float(g.at[a, "S2D"] > g.at[b, "S2D"]),
                    s2d_gap=(g.at[b, "S2D"] - g.at[a, "S2D"])
                    / nbar,  # >0: S2D prefers the ECR-lower player
                    d_agrees=float(g.at[a, "D_usage"] > g.at[b, "D_usage"]),
                )
            )
    p = pd.DataFrame(rows)
    out: dict[str, pd.DataFrame] = {}
    p["gap_bin"] = pd.cut(
        p["ecr_gap"], [0, 1, 3, 6, 12, 40], labels=["<=1", "1-3", "3-6", "6-12", "12+"]
    )
    p["tier"] = pd.cut(
        p["top_rank"], [0, 6, 12, 24], labels=["better-ranked QB1-6", "QB7-12", "QB13-24"]
    )
    for name, key in (("ecr_gap", "gap_bin"), ("tier", "tier")):
        t = p.groupby(key, observed=True).agg(
            n_pairs=("ecr_right", "size"), ecr_correct=("ecr_right", "mean")
        )
        t["seasons_ecr_above_50"] = (
            p.groupby([key, "season"], observed=True)["ecr_right"]
            .mean()
            .gt(0.5)
            .groupby(level=0)
            .sum()
        )
        out[name] = t.reset_index()
    dis = p[p["s2d_agrees"] == 0].copy()
    dis["s2d_gap_bin"] = pd.cut(
        dis["s2d_gap"], [0, 0.5, 1.5, 3, 100], labels=["<0.5 pt/g", "0.5-1.5", "1.5-3", "3+"]
    )
    t = dis.groupby("s2d_gap_bin", observed=True).agg(
        n_pairs=("ecr_right", "size"), ecr_correct=("ecr_right", "mean")
    )
    t["s2d_correct"] = 1 - t["ecr_correct"]
    out["when_s2d_disagrees"] = t.reset_index()
    ag = (
        p.groupby("s2d_agrees")
        .agg(n_pairs=("ecr_right", "size"), ecr_correct=("ecr_right", "mean"))
        .reset_index()
    )
    ag["s2d_agrees"] = ag["s2d_agrees"].map({1.0: "S2D agrees with ECR", 0.0: "S2D disagrees"})
    out["agreement"] = ag
    return out


MC_KAPPA_GRID = (1.0, 1.25, 1.5, 1.75, 2.0)


def mc_validation(
    panel: pd.DataFrame,
    stats: pd.DataFrame,
    skill_players: pd.DataFrame,
    n_sims: int = 1000,
    kappas: tuple[float, ...] = MC_KAPPA_GRID,
) -> dict:
    """Do the simulated season-total distributions cover what actually happened?

    For every test QB-snapshot: forecast (play-rate, availability) from the two-part D_usage model
    fitted on EARLIER seasons, model uncertainty = SD of leave-one-season-out residuals inside
    those seasons, noise model fitted on earlier seasons -> simulate -> compare with y_total.
    ``kappa`` multiplies the model-uncertainty SD; the sweep shows how much the intervals must be
    widened to reach nominal coverage. The scale used live is the smallest kappa whose 80%
    interval covers >= 80% on the EARLIER half of the test seasons (2022-23), then re-checked on
    the later half (2024-25) -- so it is chosen without the seasons it is judged on."""
    df = add_derived(panel[panel["target_complete"]].reset_index(drop=True))
    ctx = []
    for T in TEST_SEASONS:
        train = df[df["season"] < T].reset_index(drop=True)
        test = df[(df["season"] == T) & df["snapshot_week"].isin(BT.DEFAULT_WEEKS)].reset_index(
            drop=True
        )
        m = make_model("D_usage").fit(train)
        res = []
        for s in sorted(train["season"].unique()):
            tr, te = (
                train[train["season"] != s],
                train[(train["season"] == s) & (train["y_apps"] > 0)],
            )
            if tr.empty or te.empty:
                continue
            mi = make_model("D_usage").fit(tr.reset_index(drop=True))
            rate, _ = mi.predict_parts(te.reset_index(drop=True))
            res.append((te["y_total"] / te["y_apps"]).to_numpy() - rate)
        tau = float(np.std(np.concatenate(res))) if res else 4.0
        noise = NZ.fit_noise_model(
            stats[stats["season"] < T], skill_players[skill_players["season"] < T]
        )
        rate, avail = m.predict_parts(test)
        ctx.append((T, test, rate, avail, tau, noise))
    weeks = list(range(int(max(c[1]["n_remaining"].max() for c in ctx))))
    sweep: dict[float, pd.DataFrame] = {}
    for kappa in kappas:
        recs = []
        for T, test, rate, avail, tau, noise in ctx:
            for k, r in test.iterrows():
                n = int(r["n_remaining"])
                a = Asset(
                    f"qb{k}",
                    "q",
                    "QB",
                    f"t{k}",
                    float(rate[k]),
                    tau * kappa,
                    float(avail[k]),
                    tuple(range(n)),
                )
                sim = simulate_assets([a], weeks, noise, n_sims, seed=101)[a.pid]
                tot = np.where(sim > UNAVAILABLE / 2, sim, 0.0).sum(axis=0)
                q = np.quantile(tot, [0.05, 0.10, 0.25, 0.75, 0.90, 0.95])
                recs.append(
                    dict(
                        season=T,
                        y=r["y_total"],
                        pit=float(np.mean(tot <= r["y_total"])),
                        mean=float(tot.mean()),
                        q05=q[0],
                        q10=q[1],
                        q25=q[2],
                        q75=q[3],
                        q90=q[4],
                        q95=q[5],
                    )
                )
        sweep[kappa] = pd.DataFrame(recs)

    def cov(d, lo, hi):
        return float(((d.y >= d[lo]) & (d.y <= d[hi])).mean())

    table = []
    for kappa, d in sweep.items():
        early, late = d[d.season <= 2023], d[d.season >= 2024]
        table.append(
            {
                "kappa": kappa,
                "cov50": cov(d, "q25", "q75"),
                "cov80": cov(d, "q10", "q90"),
                "cov90": cov(d, "q05", "q95"),
                "cov80_2022_23": cov(early, "q10", "q90"),
                "cov80_2024_25": cov(late, "q10", "q90"),
            }
        )
    sweep_tbl = pd.DataFrame(table)
    ok = sweep_tbl[sweep_tbl["cov80_2022_23"] >= 0.80]
    selected = float(ok["kappa"].iloc[0]) if len(ok) else float(sweep_tbl["kappa"].iloc[-1])
    d = sweep[1.0]
    pit_hist = np.histogram(d["pit"], bins=np.linspace(0, 1, 11))[0] / len(d)
    return {
        "n": int(len(d)),
        "coverage": {
            "50% interval": cov(d, "q25", "q75"),
            "80% interval": cov(d, "q10", "q90"),
            "90% interval": cov(d, "q05", "q95"),
        },
        "pit_deciles": [float(x) for x in pit_hist],
        "mean_bias": float((d["mean"] - d["y"]).mean()),
        "by_season": d.groupby("season")
        .apply(lambda g: cov(g, "q10", "q90"), include_groups=False)
        .to_dict(),
        "kappa_sweep": sweep_tbl.to_dict(orient="records"),
        "kappa_selected": selected,
        "kappa_rule": "smallest kappa with 80%-interval coverage >= 0.80 on 2022-23; judged on 2024-25",
    }


# ----------------------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------------------
def run_full_evaluation(
    panel_path: Path = Path("data/ros/qb_ros_panel.parquet"),
    out_dir: Path = Path("reports/ros"),
    n_boot: int = 4000,
    rebuild_panel: bool = False,
    skip_roster: bool = False,
    skip_mc: bool = False,
    models: tuple[str, ...] = MAIN_MODELS,
) -> dict:
    from alpha_squad.ros.pipeline import build_default_panel, build_skill_panel

    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = panel_path.parent
    inp = None
    if (
        rebuild_panel
        or not panel_path.exists()
        or not (data_dir / "skill_players.parquet").exists()
    ):
        panel, inp = build_default_panel(list(range(2020, 2027)), out_dir=data_dir)
        specs = [s for s in inp.provenance["_specs"] if s.season <= 2025]
        build_skill_panel(inp, specs, inp.provenance["_files"], out_dir=data_dir)
    panel = pd.read_parquet(panel_path)
    skill_players = pd.read_parquet(data_dir / "skill_players.parquet")
    skill_weekly = pd.read_parquet(data_dir / "skill_weekly.parquet")
    manifest = (
        json.loads((data_dir / "inputs_manifest.json").read_text())
        if (data_dir / "inputs_manifest.json").exists()
        else {}
    )

    t0 = datetime.now(UTC)
    res = BT.run_backtest(panel, models=models, test_seasons=TEST_SEASONS)
    BT.save_result(res, out_dir)
    snap = BT.snapshot_metrics(res.preds, res.oof)
    snap.to_csv(out_dir / "snapshot_metrics.csv", index=False)

    bases = ("ECR_order", "S2D")
    groups = {
        "pairwise": ["pw_top6", "pw_qb4_15", "pw_qb8_20", "pw_similar", "pw_qb8_20_decisive"],
        "rank": ["spearman", "kendall", "top6_hit", "top12_hit", "top24_hit", "mean_abs_rank_err"],
        "regret": [
            "regret_top6",
            "regret_qb4_15",
            "regret_qb8_20",
            "vs_ecr_qb4_15",
            "vs_ecr_qb8_20",
        ],
    }
    summ = {k: summarize_two(snap, v, bases, n_boot) for k, v in groups.items()}
    pt_models = snap[snap["model"] != "ECR_order"]
    summ["point"] = summarize_two(
        pt_models, ["mae", "rmse", "mean_error"], ("A_ecr", "S2D"), n_boot
    )
    summ["prob"] = summarize_two(
        pt_models.dropna(subset=["brier"]), ["brier", "logloss"], ("A_ecr", "S2D"), n_boot
    )
    for k, v in summ.items():
        v.to_csv(out_dir / f"summary_{k}.csv", index=False)

    # regret distribution (pooled decisions)
    reg_rows = []
    for m, g in snap.groupby("model"):
        for w in M.WINDOWS:
            if f"regret_{w}" in g:
                reg_rows.append({"model": m, "window": w, **M.regret_summary(g, w)})
    regret_tbl = pd.DataFrame(reg_rows)

    # season-by-season consistency
    by_season = {
        c: BT.season_table(snap, c)
        for c in ("pw_qb4_15", "pw_qb8_20", "spearman", "regret_qb8_20", "rmse")
    }

    # breakdowns
    breakdown = {m: BT.point_by_group(res.preds, m) for m in ("A_ecr", "S2D", "D_usage", "E_full")}
    pw_week = snap[snap.model.isin(KEY_MODELS)].pivot_table(
        index="snapshot_week", columns="model", values="pw_qb8_20"
    )
    gap_tbl = {
        m: M.pairwise_by_gap(res.preds[res.preds.model == m]) for m in ("A_ecr", "S2D", "D_usage")
    }

    # reliability of pairwise probabilities
    rel = {}
    cal_p: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for m in ("A_ecr", "S2D", "D_usage", "E_full", "E_avg"):
        ps, ys = [], []
        oof_m = res.oof[res.oof.model == m]
        for T in TEST_SEASONS:
            o = oof_m[oof_m.test_season == T]
            dp, wn = [], []
            for _, gs in o.groupby(["season", "snapshot_week"]):
                gs = gs.reset_index(drop=True)
                pf = M.pair_frame(gs, M.band_pairs(gs, 4, 20))
                pf = pf[~pf["tie"] & ~pf["pred_tie"]]
                dp.append(pf["dpred"].to_numpy())
                wn.append(pf["win"].to_numpy())
            cp = M.PairProb().fit(np.concatenate(dp), np.concatenate(wn))
            for _, gs in res.preds[(res.preds.model == m) & (res.preds.season == T)].groupby(
                "snapshot_week"
            ):
                gs = gs.reset_index(drop=True)
                pf = M.pair_frame(gs, M.band_pairs(gs, 4, 20))
                pf = pf[~pf["tie"] & ~pf["pred_tie"]]
                ps.append(cp.prob(pf["dpred"].to_numpy()))
                ys.append(pf["win"].to_numpy())
        p, y = np.concatenate(ps), np.concatenate(ys)
        rel[m] = M.reliability(p, y)
        cal_p[m] = (p, y)

    trust = trust_ecr_tables(res.preds)

    # ablations (own mini-backtest, same protocol)
    abl_res = BT.run_backtest(panel, models=ABLATIONS, test_seasons=TEST_SEASONS, compute_oof=False)
    abl_snap = BT.snapshot_metrics(abl_res.preds)
    ref = snap[snap.model.isin(["D_usage", "E_full"])]
    abl_all = pd.concat([ref, abl_snap], ignore_index=True)
    abl_sum = abl_all.groupby("model")[["rmse", "mae", "pw_qb4_15", "pw_qb8_20", "spearman"]].mean()

    # coefficients (fit on every season < 2026, for interpretation only)
    full = add_derived(panel[panel["target_complete"]].reset_index(drop=True))
    d_full = make_model("D_usage").fit(full)
    coefs = pd.DataFrame(
        {
            "points_per_game_played": d_full.coefficients(),
        }
    )
    coefs["availability"] = pd.Series(
        d_full.avail_.coef_ / d_full.prep_.sd,
        index=d_full.cols + [f"{c}__missing" for c in (d_full.prep_.miss_cols or [])],
    )
    std_sd = pd.Series(
        d_full.play_prep_.sd,
        index=d_full.cols + [f"{c}__missing" for c in (d_full.play_prep_.miss_cols or [])],
    )
    coefs["play_std_effect"] = coefs["points_per_game_played"] * std_sd.reindex(coefs.index)

    mc = {} if skip_mc else mc_validation(panel, _load_stats_for_noise(manifest), skill_players)
    if mc:
        (data_dir / "mc_calibration.json").write_text(
            json.dumps(
                {
                    "kappa": mc["kappa_selected"],
                    "rule": mc["kappa_rule"],
                    "sweep": mc["kappa_sweep"],
                    "git_sha": git_sha(),
                },
                indent=2,
            )
        )

    roster = {}
    if not skip_roster:
        rmodels = [m for m in models if m != "ECR_order"]
        rr = RB.run_roster_backtest(
            skill_players,
            skill_weekly,
            res.preds,
            load_league_context(),
            rmodels,
            test_seasons=TEST_SEASONS,
        )
        rr.to_parquet(out_dir / "roster_decisions.parquet", index=False)
        from alpha_squad.ros import tradeval as TV

        kappa = mc["kappa_selected"] if mc else 1.0
        tv = TV.validate_trade_simulation(
            panel,
            skill_players,
            skill_weekly,
            res.preds,
            rr,
            _load_stats_for_noise(manifest),
            load_league_context(),
            rmodels,
            kappa=kappa,
        )
        tv.to_csv(out_dir / "trade_sim_validation.csv", index=False)
        roster["trade_sim"] = TV.summarize_trade_validation(tv)
        roster["thresholds"] = {}
        for th in (0.0, 10.0, 20.0):
            rs = RB.snapshot_roster_metrics(rr, th)
            rs.to_csv(out_dir / f"roster_snapshot_metrics_th{int(th)}.csv", index=False)
            s_ = summarize_two(
                rs,
                ["mean_real_delta", "mean_real_delta_hindsight_lineups", "oracle_gap"],
                ("A_ecr", "S2D"),
                n_boot,
            )
            s_.to_csv(out_dir / f"summary_roster_th{int(th)}.csv", index=False)
            roster["thresholds"][th] = {
                "summary": s_,
                "season": rs.pivot_table(index="model", columns="season", values="mean_real_delta"),
                "behaviour": rs.groupby("model")[
                    ["trade_rate", "hit_rate", "mean_pred_delta_exec", "mean_real_delta_exec"]
                ].mean(),
            }

    fwd = forward_check(panel)
    if len(fwd):
        fwd.to_csv(out_dir / "forward_check_2026.csv", index=False)
    design = {
        c: M.design_effect(snap[snap.model == "S2D"], c)
        for c in ("pw_qb4_15", "pw_qb8_20", "spearman")
    }
    meta = {
        "git_sha": git_sha(),
        "run_utc": t0.isoformat(timespec="seconds"),
        "n_boot": n_boot,
        "test_seasons": list(TEST_SEASONS),
        "train_sizes": res.train_sizes,
        "eval_weeks": list(BT.DEFAULT_WEEKS),
        "models": list(models),
        "exploratory": list(EXPLORATORY),
        "n_test_rows_per_model": int((res.preds.model == "A_ecr").sum()),
        "n_snapshots": int(snap[snap.model == "A_ecr"].shape[0]),
        "design_effect": design,
        "mc": mc,
    }
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2, default=str))
    write_markdown(
        out_dir / "RESULTS.md",
        meta,
        summ,
        regret_tbl,
        by_season,
        breakdown,
        pw_week,
        gap_tbl,
        rel,
        cal_p,
        trust,
        abl_sum,
        coefs,
        mc,
        roster,
        panel,
        manifest,
        fwd,
    )
    return {
        "meta": meta,
        "summ": summ,
        "regret": regret_tbl,
        "by_season": by_season,
        "roster": roster,
        "trust": trust,
        "abl": abl_sum,
        "coefs": coefs,
        "breakdown": breakdown,
        "rel": rel,
        "pw_week": pw_week,
        "gap": gap_tbl,
    }


def forward_check(panel: pd.DataFrame, models=KEY_MODELS, season: int = 2026) -> pd.DataFrame:
    """Out-of-time check on the season in progress, with the models frozen at their
    historical-seasons fit. The horizon is TRUNCATED to the future games already played, so this is
    a small, noisy confirmation (one partial season), not a backtest."""
    df = add_derived(panel[panel["target_complete"]].reset_index(drop=True))
    cur = add_derived(
        panel[(panel["season"] == season) & (panel["n_future_played"] > 0)].reset_index(drop=True)
    )
    cur = cur[cur["snapshot_week"].isin(BT.DEFAULT_WEEKS)].reset_index(drop=True)
    if cur.empty:
        return pd.DataFrame()
    rows = []
    for name in models:
        m = make_model(name).fit(df)
        c = cur.copy()
        c["n_remaining"] = c["n_future_played"]  # truncated horizon: games already played
        c["pred_total"] = m.predict_rate(c) * c["n_remaining"]
        for w, g in c.groupby("snapshot_week"):
            g = g.reset_index(drop=True)
            rec = {
                "model": name,
                "snapshot_week": int(w),
                "n_games": int(g["n_remaining"].median()),
            }
            rec.update(M.pairwise_snapshot(g))
            rec.update(M.regret_snapshot(g))
            rec.update(M.rank_metrics_snapshot(g))
            rows.append(rec)
    return pd.DataFrame(rows)


def _load_stats_for_noise(manifest: dict) -> pd.DataFrame:
    from alpha_squad.ros import snapshots as sn
    from alpha_squad.ros.scoring import ScoringRules

    files = manifest["stats_player_week"]
    st = sn.load_weekly_stats({int(s): f["path"] for s, f in files.items()})
    st["pts"] = __import__("alpha_squad.ros.scoring", fromlist=["x"]).score_stat_lines(
        st, ScoringRules.nflverse_ppr()
    )
    st["appeared"] = (st[["attempts", "carries"]].fillna(0).sum(axis=1) > 0).astype(int)
    return st


def write_markdown(
    path,
    meta,
    summ,
    regret_tbl,
    by_season,
    breakdown,
    pw_week,
    gap_tbl,
    rel,
    cal_p,
    trust,
    abl_sum,
    coefs,
    mc,
    roster,
    panel,
    manifest,
    fwd=None,
) -> None:
    L: list[str] = []
    A = L.append
    A(
        f"# ROS QB backtest -- generated results\n\nRun {meta['run_utc']} UTC, git `{meta['git_sha']}`, "
        f"{meta['n_boot']} bootstrap draws, test seasons {meta['test_seasons']}, evaluation weeks {meta['eval_weeks']}.\n"
    )
    A(
        f"Test population: {meta['n_snapshots']} snapshots x 36 QBs = {meta['n_test_rows_per_model']} player-snapshots per model. "
        f"Training rows available per test season: {meta['train_sizes']}.\n"
    )
    A(
        "Intervals are 95% season-and-snapshot block-bootstrap intervals (seasons resampled, then snapshots within "
        "season). **With only four test seasons these intervals are themselves imprecise; treat them as a guide to "
        "season-to-season variation, not as exact coverage.** Models marked `*` were added after a first look at "
        f"results ({', '.join(meta['exploratory'])}).\n"
    )

    def tbl(key, metric_labels, bases=("ECR_order", "S2D"), digits=3, order=None):
        s = summ[key]
        rows = []
        models = order or list(dict.fromkeys(s["model"]))
        for m in models:
            rec = {"model": m + ("*" if m in meta["exploratory"] else "")}
            for met, lab in metric_labels.items():
                r = s[(s.metric == met) & (s.model == m)]
                if r.empty:
                    rec[lab] = ""
                    continue
                r = r.iloc[0]
                rec[lab] = est_ci(r, digits)
            rows.append(rec)
        return pd.DataFrame(rows)

    A("## 1. Pairwise decision accuracy (ties = 0.5; tie = realized totals within 0.5 pt/game)\n")
    A(
        md(
            tbl(
                "pairwise",
                {
                    "pw_top6": "Top-6 pairs",
                    "pw_qb4_15": "QB4-15 pairs",
                    "pw_qb8_20": "QB8-20 pairs",
                    "pw_similar": "ECR-similar pairs",
                },
            )
        )
    )
    A(
        "\nPaired difference vs the published ECR order (`ECR_order`) and vs the parameter-free season-to-date baseline (`S2D`), QB4-15 and QB8-20 bands:\n"
    )
    s = summ["pairwise"]
    rows = []
    for m in dict.fromkeys(s["model"]):
        rec = {"model": m + ("*" if m in meta["exploratory"] else "")}
        for met in ("pw_qb4_15", "pw_qb8_20"):
            r = s[(s.metric == met) & (s.model == m)].iloc[0]
            rec[f"{met} vs ECR"] = diff_ci(r, "ECR_order")
            rec[f"{met} vs S2D"] = diff_ci(r, "S2D")
        rows.append(rec)
    A(md(pd.DataFrame(rows)))
    A("\nBy season (mean over that season's five snapshots):\n")
    A("QB4-15 band\n\n" + md(by_season["pw_qb4_15"].round(3), index=True))
    A("\nQB8-20 band\n\n" + md(by_season["pw_qb8_20"].round(3), index=True))
    A("\nQB8-20 accuracy by snapshot week\n\n" + md(pw_week.round(3), index=True))
    for m, t in gap_tbl.items():
        A(
            f"\nDecisive-pair accuracy by the model's own predicted gap -- `{m}` (pooled, ranks 1-24)\n\n"
            + md(t)
        )

    A(
        "\n## 2. Decision regret (pick one QB from the window; regret = best realized minus realized pick, points)\n"
    )
    A(
        md(
            tbl(
                "regret",
                {"regret_top6": "Top-6", "regret_qb4_15": "QB4-15", "regret_qb8_20": "QB8-20"},
                digits=1,
            )
        )
    )
    A(
        "\nRealized points of the model's pick minus the ECR-top pick (positive = beats trusting ECR):\n"
    )
    A(
        md(
            tbl(
                "regret",
                {"vs_ecr_qb4_15": "QB4-15 vs ECR-top", "vs_ecr_qb8_20": "QB8-20 vs ECR-top"},
                digits=1,
            )
        )
    )
    A(
        "\nRegret distribution, pooled over the 20 test snapshots (hindsight regret; a diagnostic, not attainable):\n"
    )
    A(md(regret_tbl.round(2)))

    A("\n## 3. Rank accuracy over the 36-QB population\n")
    A(
        md(
            tbl(
                "rank",
                {
                    "spearman": "Spearman",
                    "kendall": "Kendall",
                    "top6_hit": "Top-6 hit",
                    "top12_hit": "Top-12 hit",
                    "top24_hit": "Top-24 hit",
                    "mean_abs_rank_err": "Mean |rank err|",
                },
            )
        )
    )

    A("\n## 4. Point accuracy of ROS totals (points over the remaining schedule)\n")
    A(md(tbl("point", {"mae": "MAE", "rmse": "RMSE", "mean_error": "Mean error"}, digits=1)))
    for m, bd in breakdown.items():
        A(f"\n`{m}` by ECR tier\n\n" + md(bd["tier"].round(2), index=True))
        A(f"\n`{m}` by rushing profile\n\n" + md(bd["rushing_profile"].round(2), index=True))
        A(f"\n`{m}` by snapshot week\n\n" + md(bd["week"].round(2), index=True))
        A(
            f"\n`{m}` by predicted-total quartile within snapshot\n\n"
            + md(bd["pred_quartile"].round(2), index=True)
        )
        A(f"\n`{m}` by season\n\n" + md(bd["season"].round(2), index=True))

    A(
        "\n## 5. Probability calibration of P(QB_i outscores QB_j), QB4-20 pairs, decisive pairs only\n"
    )
    A(md(tbl("prob", {"brier": "Brier", "logloss": "Log loss"})))
    A("\n(Coin-flip reference: Brier 0.250, log loss 0.693.)\n")
    for m, r in rel.items():
        A(
            f"\nReliability -- `{m}` (probabilities from a per-test-season logistic map fitted on out-of-fold training predictions)\n\n"
            + md(r.round(3))
        )

    A("\n## 6. Roster-level decision utility (market-priced one-for-one QB swap)\n")
    if roster:
        for th, blk in roster["thresholds"].items():
            A(f"\n### Execute only if predicted gain > {th:g} lineup points\n")
            s_ = blk["summary"]
            rows = []
            for m in dict.fromkeys(s_["model"]):
                r = s_[(s_.metric == "mean_real_delta") & (s_.model == m)].iloc[0]
                rg = s_[(s_.metric == "oracle_gap") & (s_.model == m)].iloc[0]
                rh = s_[(s_.metric == "mean_real_delta_hindsight_lineups") & (s_.model == m)].iloc[
                    0
                ]
                rows.append(
                    {
                        "model": m + ("*" if m in meta["exploratory"] else ""),
                        "realized lineup pts / team-snapshot": est_ci(r, 1),
                        "vs A_ecr": diff_ci(r, "A_ecr", 1),
                        "vs S2D": diff_ci(r, "S2D", 1),
                        "(sensitivity) hindsight-lineup scoring": est_ci(rh, 1),
                        "hindsight-best-trade gap": f"{rg['estimate']:.1f}",
                    }
                )
            A(md(pd.DataFrame(rows)))
            A(
                "\nBy season (mean realized lineup points per team-snapshot):\n\n"
                + md(blk["season"].round(1), index=True)
            )
            A(
                "\nBehaviour (trade rate, share of executed trades with positive realized value, mean predicted vs realized gain when executed):\n\n"
                + md(blk["behaviour"].round(3), index=True)
            )
        ts = roster.get("trade_sim")
        if ts:
            A("\n### Does the engine's P(trade improves lineup) mean what it says?\n")
            A(
                f"{ts['n_trades']} trades that `D_usage` executed at threshold 0 were re-simulated with the production "
                f"Monte Carlo engine (kappa applied to forecast uncertainty). Stated mean gain "
                f"{ts['mean_stated_gain']:+.1f} pts vs realized {ts['mean_realized_gain']:+.1f}; stated average "
                f"P(improves) {ts['mean_stated_p_improve']:.2f} vs observed {ts['observed_improved']:.2f}; "
                f"Brier {ts['brier']:.3f} (constant-base-rate reference {ts['brier_always_base_rate']:.3f}); "
                f"realized gain inside the simulated central 50% / 80% interval {ts['cov50']:.1%} / {ts['cov80']:.1%}.\n"
            )
            A(md(ts["reliability"].round(3)))
            A("\nBy season:\n\n" + md(ts["by_season"].round(2)))
    else:
        A("not run\n")

    A(
        "\n## 7. What information matters (drop-one-group ablation, walk-forward, means over 20 snapshots)\n"
    )
    A(md(abl_sum.round(3), index=True))
    A(
        "\nStandardized coefficients of the two-part `D_usage` model fit on all seasons < 2026 (interpretation only, not a result):\n\n"
        + md(coefs.round(3), index=True)
    )

    A("\n## 8. When to trust ECR\n")
    for k, t in trust.items():
        A(f"\n`{k}`\n\n" + md(t.round(3)))

    A(
        "\n## 9. Monte Carlo validation (does the simulated season-total distribution cover reality?)\n"
    )
    if mc:
        A(
            f"n = {mc['n']} QB-snapshots. Nominal 50/80/90% central intervals covered: "
            f"{mc['coverage']['50% interval']:.1%} / {mc['coverage']['80% interval']:.1%} / {mc['coverage']['90% interval']:.1%}. "
            f"Mean simulated-minus-actual total: {mc['mean_bias']:+.1f} pts. PIT deciles: {[round(x, 3) for x in mc['pit_deciles']]} "
            f"(uniform = 0.10 each). 80%-interval coverage by season (kappa=1): {mc['by_season']}.\n"
        )
        A(
            "\nWidening the model-uncertainty term by kappa (rule: "
            + mc["kappa_rule"]
            + f"; selected kappa = {mc['kappa_selected']}):\n\n"
            + md(pd.DataFrame(mc["kappa_sweep"]).round(3))
        )
    else:
        A("not run\n")
    A("\n## 10. Forward check on the season in progress (2026), models frozen on 2020-2025\n")
    if fwd is not None and len(fwd):
        t = fwd.groupby("model")[
            ["pw_qb4_15", "pw_qb8_20", "pw_top6", "spearman", "regret_qb4_15", "regret_qb8_20"]
        ].mean()
        A(
            "Truncated horizon (games already played after each snapshot); three snapshots (weeks 6-8) that share most of "
            "their outcome games, so this is roughly ONE small independent look. No inference is drawn from it.\n\n"
            + md(t.round(3), index=True)
        )
    else:
        A("not available\n")
    A("\n## 11. Effective sample size\n")
    A("```\n" + json.dumps(meta["design_effect"], indent=2) + "\n```\n")
    path.write_text("\n".join(L))
