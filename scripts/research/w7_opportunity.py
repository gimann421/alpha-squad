"""W7 --- is future opportunity predictable before Friday, and does it fix the top of the board?

Runs exactly what `docs/weekly/W7_PREREGISTRATION.md` specifies. **Fits no production model and
touches no production file.** Two stages:

  Q1  the forecast ladder -- five no-fitting baselines and five pre-registered forecasts of the
      week's realized opportunity, walk-forward, from Class A information only (plus one labelled
      Class B sensitivity). The double-counting test: does information Alpha does NOT hold beat a
      control that merely re-expresses what it does hold?
  Q2  the ranking ladder -- L0 current Alpha, L1 Alpha retrained with the Class A opportunity
      features (one change), L2 the W5 perfect-usage oracle -- and FORECAST_USAGE, the realistic
      analogue of that oracle.

    uv run python scripts/research/w7_opportunity.py --out reports/weekly/w7_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import (  # noqa: E402
    audit,
    benchmark,
    context,
    noise,
    nulls,
    topboard,
)
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import (  # noqa: E402
    evaluate_cell,
    spearman,
    topk_points_capture,
)
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    _null_metrics,
    cliff,
    flex_cell,
    leave_one_season_out,
    per_season,
    positional_cell,
    summarise,
)

SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ("RB", "WR", "TE")
PRIMARY_POSITIONS = ("RB", "WR")
DEPTHS = topboard.W5_DEPTHS
#: Predicted fantasy-rank bands for the "is it about the top of the board?" breakdown (§10.4).
RANK_BANDS: tuple[tuple[int, int], ...] = ((1, 5), (6, 10), (11, 20), (21, 50), (51, 10_000))
BOARDS = ("CF_A", "ALPHA_PLUS_OPP", "FORECAST_USAGE", "ORACLE_USAGE", "ORACLE_OUTCOME", "ECR")
NULL_BOARDS = ("CF_A", "ALPHA_PLUS_OPP")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def _ranks(scores: list[float], ids: list[str]) -> list[float]:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], ids[i]))
    out = [0.0] * len(scores)
    for r, i in enumerate(order, start=1):
        out[i] = float(r)
    return out


# ---------------------------------------------------------------------------------------
# The evaluated universe, identical to W3-W6
# ---------------------------------------------------------------------------------------


def universes(con, snapshots, fmt) -> dict[tuple[str, str], dict]:
    """(week key, position) -> {players, alpha_rank, realized} from the production control board."""
    out: dict[tuple[str, str], dict] = {}
    for snap in snapshots:
        key = f"{snap.season}-{snap.week}"
        for position in POSITIONS:
            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=(position,)
            )
            if not preds:
                continue
            common, board, kept = positional_cell(con, snap, position, fmt, preds)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            out[(key, position)] = {
                "snap": snap,
                "players": {r.player_id for r in board.rows},
                "alpha_rank": {r.player_id: r.ecr for r in board.rows},
                "alpha_pred": kept,
                "common": common,
            }
    return out


# ---------------------------------------------------------------------------------------
# Q1 -- the forecast ladder
# ---------------------------------------------------------------------------------------


def forecast_stage(panel: pd.DataFrame, unis: dict, targets_by_position: dict) -> dict:
    """Walk-forward forecasts, scored per week on the evaluated universe."""
    methods = (*op.BASELINES, *op.FORECAST_MODELS)
    forecasts: dict[tuple[str, str, str], pd.Series] = {}
    for position, targets in targets_by_position.items():
        for target in targets:
            for method in methods:
                forecasts[(position, target, method)] = op.walk_forward(
                    panel, position, target, method, SEASONS
                )

    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    cells: dict[str, dict] = {}
    pooled: dict[str, dict] = {}
    bands: dict[str, dict] = {}
    for (key, position), u in sorted(unis.items()):
        snap = u["snap"]
        for target in targets_by_position.get(position, ()):
            ycol = op.TARGETS[target]
            rows = [
                (pid, idx[(pid, snap.season, snap.week)])
                for pid in sorted(u["players"])
                if (pid, snap.season, snap.week) in idx
            ]
            rows = [(pid, i) for pid, i in rows if not pd.isna(panel.at[i, ycol])]
            if len(rows) < benchmark.MIN_EVALUABLE:
                continue
            ids = [pid for pid, _ in rows]
            real = [float(panel.at[i, ycol]) for _, i in rows]
            for method in methods:
                fc = forecasts[(position, target, method)]
                pred = [float(fc.at[i]) for _, i in rows]
                pr = _ranks(pred, ids)
                name = f"{position}|{target}|{method}"
                cells.setdefault(name, {})[key] = {
                    "n": len(rows),
                    "pearson": _pearson(pred, real),
                    "spearman": spearman(pr, real),
                    "mae": statistics.fmean(abs(a - b) for a, b in zip(pred, real, strict=True)),
                    "capture@10": topk_points_capture(pr, real, 10),
                    "capture@20": topk_points_capture(pr, real, 20),
                }
                agg = pooled.setdefault(name, {"pred": [], "real": []})
                agg["pred"] += pred
                agg["real"] += real
                if target == op.PRIMARY_TARGET and method in ("M_S0", "M_NEW", "M_RED", "M_B"):
                    for lo, hi in RANK_BANDS:
                        sel = [
                            j
                            for j, pid in enumerate(ids)
                            if lo <= u["alpha_rank"].get(pid, 10**9) <= hi
                        ]
                        b = bands.setdefault(
                            f"{position}|{method}|{lo}-{hi}", {"pred": [], "real": []}
                        )
                        b["pred"] += [pred[j] for j in sel]
                        b["real"] += [real[j] for j in sel]

    pooled_out = {}
    for name, agg in pooled.items():
        p, y = agg["pred"], agg["real"]
        my = statistics.fmean(y)
        ss_tot = sum((v - my) ** 2 for v in y)
        ss_res = sum((a - b) ** 2 for a, b in zip(p, y, strict=True))
        pooled_out[name] = {
            "n": len(y),
            "r2": (1 - ss_res / ss_tot) if ss_tot else None,
            "pearson": _pearson(p, y),
            "calibration": _calibration(p, y),
        }
    band_out = {
        name: {
            "n": len(b["real"]),
            "spearman": spearman(
                _ranks(b["pred"], [str(i) for i in range(len(b["pred"]))]), b["real"]
            )
            if len(b["real"]) >= 3
            else None,
            "mae": statistics.fmean(abs(a - c) for a, c in zip(b["pred"], b["real"], strict=True))
            if b["real"]
            else None,
        }
        for name, b in bands.items()
    }
    return {"cells": cells, "pooled": pooled_out, "bands": band_out, "forecasts": forecasts}


def _calibration(pred: list[float], real: list[float], k: int = 10) -> list[dict]:
    """Mean realized opportunity by predicted decile, pooled -- descriptive."""
    order = sorted(range(len(pred)), key=lambda i: pred[i])
    n = len(order)
    out = []
    for d in range(k):
        sel = order[d * n // k : (d + 1) * n // k]
        if not sel:
            continue
        out.append(
            {
                "decile": d + 1,
                "mean_pred": statistics.fmean(pred[i] for i in sel),
                "mean_real": statistics.fmean(real[i] for i in sel),
                "n": len(sel),
            }
        )
    return out


def forecast_comparisons(cells: dict, targets_by_position: dict) -> dict:
    """Δ_NEW, Δ_RED, Δ_NEW − Δ_RED, and every method against BL_MEAN3, per week."""
    out: dict = {}

    def per_week(name: str, metric: str) -> dict[str, float]:
        return {k: r[metric] for k, r in cells.get(name, {}).items() if r.get(metric) is not None}

    for position, targets in targets_by_position.items():
        for target in targets:
            base = f"{position}|{target}"
            for metric in ("spearman", "pearson", "capture@10", "mae"):
                s0 = per_week(f"{base}|M_S0", metric)
                new = per_week(f"{base}|M_NEW", metric)
                red = per_week(f"{base}|M_RED", metric)
                cb = per_week(f"{base}|M_CB", metric)
                cls_b = per_week(f"{base}|M_B", metric)
                pairs = {
                    "D_NEW": (new, s0),
                    "D_RED": (red, s0),
                    "M_CB_vs_M_NEW": (cb, new),
                    "D_CLASS_B": (cls_b, new),
                }
                for label, (a, b) in pairs.items():
                    pd_ = noise.paired_difference(metric, "A", "B", a, b)
                    if pd_:
                        out.setdefault(f"{base}|{label}", {})[metric] = pd_.as_row()
                # the double-counting test proper: (NEW - S0) - (RED - S0) = NEW - RED
                pd_ = noise.paired_difference(metric, "NEW", "RED", new, red)
                if pd_:
                    out.setdefault(f"{base}|D_NEW_minus_D_RED", {})[metric] = pd_.as_row()
    return out


# ---------------------------------------------------------------------------------------
# Q2 -- the ranking ladder
# ---------------------------------------------------------------------------------------


def ranking_stage(con, panel, unis, fmt, plus: arms_mod.ArmPredictions, usage_forecast) -> dict:
    """Score every board on every positional cell and FLEX, plus the copula null for two boards."""
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    cells: dict[str, dict] = {}
    null_cells: dict[str, dict] = {}
    for (key, position), u in sorted(unis.items()):
        snap, common = u["snap"], u["common"]
        players = u["players"]
        tiebreak = u["alpha_rank"]
        realized = {r.player_id: float(r.realized) for r in common.rows}
        usage = context.load_usage_points(con, snap.season, snap.week, fmt.points_per_reception)

        plus_preds = plus.for_week(snap.season, snap.week, position)
        fc = {
            pid: float(usage_forecast[position].at[idx[(pid, snap.season, snap.week)]])
            for pid in players
            if (pid, snap.season, snap.week) in idx
        }
        boards = {
            "CF_A": alpha_mod.alpha_board(common, u["alpha_pred"])[0],
            "ALPHA_PLUS_OPP": alpha_mod.alpha_board(common, plus_preds, tiebreak=tiebreak)[0],
            "FORECAST_USAGE": alpha_mod.alpha_board(common, fc, tiebreak=tiebreak)[0],
            "ORACLE_USAGE": topboard.oracle_usage(common, u["alpha_pred"], usage)[0],
            "ORACLE_OUTCOME": topboard.oracle_outcome(common, u["alpha_pred"]),
            "ECR": common,
        }
        for name, board in boards.items():
            if {r.player_id for r in board.rows} != players:
                raise SystemExit(f"GATE G9 FAILED: {name} {key} {position} changed the universe")
            pr, rl = board.ranks_and_points()
            cells.setdefault(f"{position}|{name}", {})[key] = evaluate_cell(
                pr, rl, depths=DEPTHS
            ).as_row()
            if name in NULL_BOARDS:
                rho = spearman(pr, rl)
                if rho is not None and rho > 0:
                    latent = nulls.calibrate_latent(rl, rho, snap.season, snap.week, position)
                    draws = [
                        _null_metrics(
                            nulls.draw_null_ranking(
                                rl, rho, snap.season, snap.week, position, d, latent=latent
                            ).pred_rank,
                            rl,
                        )
                        for d in range(nulls.N_SIM)
                    ]
                    null_cells.setdefault(f"{position}|{name}", {})[key] = {
                        m: statistics.fmean([d[m] for d in draws if d[m] is not None])
                        for m in draws[0]
                        if any(d[m] is not None for d in draws)
                    }
        del realized

    # --- FLEX, through the existing pooled path, for the two model boards ---
    by_week: dict[str, dict] = {}
    for (key, position), u in unis.items():
        by_week.setdefault(key, {"snap": u["snap"], "alpha": {}, "plus": {}})
        by_week[key]["alpha"].update(u["alpha_pred"])
        by_week[key]["plus"].update(plus.for_week(u["snap"].season, u["snap"].week, position))
    for key, w in sorted(by_week.items()):
        commonf, boardf, keptf = flex_cell(con, w["snap"], fmt, w["alpha"])
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        uni_f = {r.player_id for r in boardf.rows}
        _c, plusf, _k = flex_cell(con, w["snap"], fmt, w["plus"], universe=uni_f)
        for name, board in (("CF_A", boardf), ("ALPHA_PLUS_OPP", plusf), ("ECR", commonf)):
            pr, rl = board.ranks_and_points()
            cells.setdefault(f"FLEX|{name}", {})[key] = evaluate_cell(
                pr, rl, depths=DEPTHS
            ).as_row()
    return {"cells": cells, "null_cells": null_cells}


def ladder_ratios(summary: dict, positions: tuple[str, ...]) -> dict:
    """R_L1 and R_F on positional capture@10 -- descriptive decompositions, not gates."""
    out = {}
    paired = summary["paired"]

    def get(position: str, board: str):
        return paired.get(f"{position}|{board}_vs_{position}|CF_A", {}).get("capture@10")

    for position in positions:
        l1 = get(position, "ALPHA_PLUS_OPP")
        fu = get(position, "FORECAST_USAGE")
        l2 = get(position, "ORACLE_USAGE")
        if not (l1 and fu and l2) or not l2["mean_diff"]:
            continue
        out[position] = {
            "L1_minus_L0": l1["mean_diff"],
            "FORECAST_minus_L0": fu["mean_diff"],
            "L2_minus_L0": l2["mean_diff"],
            "R_L1": l1["mean_diff"] / l2["mean_diff"],
            "R_F": fu["mean_diff"] / l2["mean_diff"],
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w7_results.json")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    sources = context.wire_snapshot_views(con, tuple(range(2015, 2026)))

    print("[1/6] building the pre-Friday opportunity panel ...")
    panel = op.build_panel(con, POSITIONS)
    print(f"      {len(panel):,} appearances, 2015-2025")

    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"[2/6] evaluated universe: {len(snapshots)} weeks ...")
    unis = universes(con, snapshots, FULL_PPR)

    print("[3/6] Q1 forecast ladder (baselines + 5 forecasts, walk-forward) ...")
    fstage = forecast_stage(panel, unis, op.TARGETS_BY_POSITION)
    fcmp = forecast_comparisons(fstage["cells"], op.TARGETS_BY_POSITION)
    fsum = summarise(fstage["cells"], [])

    print("[4/6] Q2 ranking ladder: training ALPHA_PLUS_OPP (one change) ...")
    plus = arms_mod.train_with_extra_features(con, panel, list(op.NEW))
    usage_fc = {p: fstage["forecasts"][(p, "T_XFP", "M_NEW")] for p in POSITIONS}
    rstage = ranking_stage(con, panel, unis, FULL_PPR, plus, usage_fc)
    comps = []
    for position in (*POSITIONS, "FLEX"):
        for board in ("ALPHA_PLUS_OPP", "FORECAST_USAGE", "ORACLE_USAGE", "ORACLE_OUTCOME", "ECR"):
            comps.append((f"{position}|{board}", f"{position}|CF_A"))
        comps.append((f"{position}|ALPHA_PLUS_OPP", f"{position}|ECR"))
    rsum = summarise(rstage["cells"], comps)
    cliffs = {
        f"{p}|{b}": cliff(rstage["cells"], rstage["null_cells"], f"{p}|{b}")
        for p in POSITIONS
        for b in NULL_BOARDS
    }

    print("[5/6] robustness: LOSO, per-season, Half-PPR ...")
    loso = {
        "ranking": {
            p: {
                m: leave_one_season_out(rstage["cells"], f"{p}|ALPHA_PLUS_OPP", f"{p}|CF_A", m)
                for m in ("capture@5", "capture@10")
            }
            for p in PRIMARY_POSITIONS
        },
        "forecast": {
            p: leave_one_season_out(
                {
                    "NEW": fstage["cells"][f"{p}|T_XFP|M_NEW"],
                    "S0": fstage["cells"][f"{p}|T_XFP|M_S0"],
                },
                "NEW",
                "S0",
                "spearman",
            )
            for p in POSITIONS
        },
    }
    seasons = {
        "ranking": {
            p: per_season(rstage["cells"], f"{p}|ALPHA_PLUS_OPP", f"{p}|CF_A", "capture@10")
            for p in PRIMARY_POSITIONS
        },
        "forecast": {
            p: per_season(
                {
                    "NEW": fstage["cells"][f"{p}|T_XFP|M_NEW"],
                    "S0": fstage["cells"][f"{p}|T_XFP|M_S0"],
                },
                "NEW",
                "S0",
                "spearman",
            )
            for p in POSITIONS
        },
    }
    half_fc = {p: op.walk_forward(panel, p, "T_XFP_HALF", "M_NEW", SEASONS) for p in POSITIONS}
    half_unis = universes(con, snapshots, HALF_PPR)
    hstage = ranking_stage(con, panel, half_unis, HALF_PPR, plus, half_fc)
    hsum = summarise(
        hstage["cells"],
        [
            (f"{p}|{b}", f"{p}|CF_A")
            for p in (*POSITIONS, "FLEX")
            for b in ("ALPHA_PLUS_OPP", "FORECAST_USAGE", "ORACLE_USAGE")
        ],
    )
    hcliffs = {
        f"{p}|{b}": cliff(hstage["cells"], hstage["null_cells"], f"{p}|{b}")
        for p in POSITIONS
        for b in NULL_BOARDS
    }

    print("[6/6] writing ...")
    ratios = ladder_ratios(rsum, POSITIONS)
    for position in POSITIONS:
        d = fcmp.get(f"{position}|T_XFP|D_NEW", {}).get("spearman")
        r = fcmp.get(f"{position}|T_XFP|D_RED", {}).get("spearman")
        n = fstage["cells"].get(f"{position}|T_XFP|M_NEW", {})
        rho = statistics.fmean(v["spearman"] for v in n.values() if v["spearman"] is not None)
        c = (
            rsum["paired"]
            .get(f"{position}|ALPHA_PLUS_OPP_vs_{position}|CF_A", {})
            .get("capture@10")
        )
        rat = ratios.get(position, {})
        print(
            f"  {position}: T_XFP forecast rho={rho:.4f}  D_NEW={d['mean_diff']:+.4f}"
            f"  D_RED={r['mean_diff']:+.4f}  |  ALPHA_PLUS_OPP c@10 {c['mean_diff']:+.4f} "
            f"CI[{c['ci_low']:+.4f},{c['ci_high']:+.4f}]  R_L1={rat.get('R_L1', float('nan')):+.1%}"
            f"  R_F={rat.get('R_F', float('nan')):+.1%}"
        )

    result = {
        "provenance": {
            "features": {
                "S0": list(op.S0),
                "NEW": list(op.NEW),
                "REDUNDANT": list(op.REDUNDANT),
                "CLASS_B": list(op.CLASS_B),
            },
            "targets": op.TARGETS_BY_POSITION,
            "ridge_alpha": op.RIDGE_ALPHA,
            "catboost": op.CATBOOST_KWARGS,
            "alpha_plus_opp_counts": plus.by_position,
            "sources": sources,
            "n_sim": nulls.N_SIM,
        },
        "n_weeks": len(snapshots),
        "forecast": {
            "cells": fstage["cells"],
            "pooled": fstage["pooled"],
            "bands": fstage["bands"],
            "summary": fsum,
            "comparisons": fcmp,
        },
        "ranking": {
            "cells": rstage["cells"],
            "null_cells": rstage["null_cells"],
            "summary": rsum,
            "cliff": cliffs,
            "ratios": ratios,
        },
        "robustness": {"loso": loso, "per_season": seasons},
        "half_ppr": {"summary": hsum, "cliff": hcliffs, "ratios": ladder_ratios(hsum, POSITIONS)},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
