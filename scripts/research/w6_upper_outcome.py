"""W6 --- does training for higher-end outcomes fix the top of the RB/WR board?

Runs exactly what `docs/weekly/W6_PREREGISTRATION.md` specifies. **One argument changes between
arms** -- the CatBoost `loss_function` -- and the control arm reproduces production's stored
predictions exactly (gate 1). Nothing here writes to the database or touches production.

    uv run python scripts/research/w6_upper_outcome.py --out reports/weekly/w6_results.json

Five arms (A_MAE control, B0_RMSE discriminating control, B1_Q60 / B2_Q70 primary / B3_Q80),
scored on RB/WR/TE/QB positional boards and on the pooled FLEX board, against the W5 copula null,
with the movement diagnostics that separate "genuinely better" from "merely more extreme".
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import alpha as alpha_mod
from alpha_squad.evaluation.weekly import arms as arms_mod
from alpha_squad.evaluation.weekly import audit, benchmark, diagnostics, noise, nulls, topboard
from alpha_squad.evaluation.weekly.metrics import evaluate_cell, spearman, topk_precision
from alpha_squad.evaluation.weekly.metrics import topk_points_capture as capture
from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS, FULL_PPR, HALF_PPR

SEASONS = (2021, 2022, 2023, 2024, 2025)
PRIMARY_POSITIONS = ("RB", "WR")
GUARDRAIL_POSITIONS = ("TE",)
CONTRAST_POSITIONS = ("QB",)
ALL_POSITIONS = ("RB", "WR", "TE", "QB")
DEPTHS = topboard.W5_DEPTHS  # (5, 10, 20, 25, 50)
HEADLINE = (
    "spearman",
    "kendall",
    "pairwise",
    "decisive",
    *(f"capture@{k}" for k in DEPTHS),
    *(f"precision@{k}" for k in DEPTHS),
)
#: Predicted top-10 that finished outside the realized top-24 -- W5's frozen FALSE POSITIVE.
FP_PRED_DEPTH, FP_REAL_DEPTH = 10, 24


# ---------------------------------------------------------------------------------------
# Board construction: identical to W5's, with the arm's predictions injected
# ---------------------------------------------------------------------------------------


def positional_cell(con, snap, position: str, fmt, preds: dict[str, float], universe=None):
    """The W5 evaluated universe, scored with `preds` instead of the stored predictions.

    `universe` pins the player set to the control arm's, so every arm is scored on exactly the
    same players. All arms predict the same rows by construction, so this is belt-and-braces --
    and it is asserted as a gate rather than trusted."""
    ref = benchmark.positional_board(con, snap, position, fmt)
    played = {r.player_id for r in ref.evaluable}
    ref_played = alpha_mod.restrict_board(ref, played)
    board, _cov = alpha_mod.alpha_board(ref_played, preds)
    keep = universe if universe is not None else {r.player_id for r in board.rows}
    if universe is not None:
        board = alpha_mod.restrict_board(board, keep)
    common = alpha_mod.restrict_board(ref_played, keep)
    return common, board, {pid: preds[pid] for pid in keep if pid in preds}


def flex_cell(con, snap, fmt, preds: dict[str, float], universe=None):
    """The pooled FLEX board, built through the EXISTING path -- no separate FLEX model.

    W4/D112 settled that the cross-position combination step is not the lever, so it is left
    exactly as it is: three positional prediction vectors into one `sorted()`."""
    ref = benchmark.flex_board(con, snap, fmt)
    played = {r.player_id for r in ref.evaluable}
    ref_played = alpha_mod.restrict_board(ref, played)
    board, _cov = alpha_mod.alpha_board(ref_played, preds)
    keep = universe if universe is not None else {r.player_id for r in board.rows}
    if universe is not None:
        board = alpha_mod.restrict_board(board, keep)
    common = alpha_mod.restrict_board(ref_played, keep)
    return common, board, {pid: preds[pid] for pid in keep if pid in preds}


def _null_metrics(pred_rank: list[float], real: list[float]) -> dict:
    row: dict[str, float | None] = {"spearman": spearman(pred_rank, real)}
    for k in DEPTHS:
        row[f"capture@{k}"] = capture(pred_rank, real, k)
        row[f"precision@{k}"] = topk_precision(pred_rank, real, k)
    return row


def run(
    con,
    snapshots,
    fmt,
    trained: dict[str, arms_mod.ArmPredictions],
    *,
    null_arms: tuple[str, ...] | None = None,
):
    """Score every arm on every positional cell and on FLEX, plus the copula null per arm.

    `null_arms` restricts which arms get a calibrated copula null. The null is the expensive part
    (200 calibrated draws per arm per position per week), and the Half-PPR pass only has to
    replicate the cliff re-test for the control and the primary arm, so it does not pay for the
    dose-response arms' nulls. Defaults to every arm."""
    wanted_nulls = set(arms_mod.ARMS if null_arms is None else null_arms)
    cells: dict[str, dict] = {}
    null_cells: dict[str, dict] = {}
    movement: list[dict] = []
    universes: list[dict] = []

    for snap in snapshots:
        key = f"{snap.season}-{snap.week}"
        # The control arm defines the universe for the week, at every position.
        control = trained[arms_mod.CONTROL_ARM]
        for position in ALL_POSITIONS:
            base_preds = control.for_week(snap.season, snap.week, position)
            if not base_preds:
                continue
            common0, board0, kept0 = positional_cell(con, snap, position, fmt, base_preds)
            if len(common0.rows) < benchmark.MIN_EVALUABLE:
                continue
            universe = {r.player_id for r in board0.rows}
            realized = {r.player_id: float(r.realized) for r in common0.rows}
            universes.append(
                {"season": snap.season, "week": snap.week, "position": position, "n": len(universe)}
            )

            rank0 = {r.player_id: r.ecr for r in board0.rows}
            for arm in arms_mod.ARMS:
                preds = (
                    kept0
                    if arm == arms_mod.CONTROL_ARM
                    else trained[arm].for_week(snap.season, snap.week, position)
                )
                common, board, kept = positional_cell(
                    con, snap, position, fmt, preds, universe=universe
                )
                pr, rl = board.ranks_and_points()
                cells.setdefault(f"{position}|{arm}", {})[key] = evaluate_cell(
                    pr, rl, depths=DEPTHS
                ).as_row()
                movement.append(_movement_row(snap, position, arm, rank0, board, kept, realized))

                if arm in wanted_nulls:
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
                        row = {
                            m: statistics.fmean([d[m] for d in draws if d[m] is not None])
                            for m in draws[0]
                            if any(d[m] is not None for d in draws)
                        }
                        row["target_rho"] = rho
                        null_cells.setdefault(f"{position}|{arm}", {})[key] = row

            # --- ECR on the same universe, for context ---
            pr, rl = common0.ranks_and_points()
            cells.setdefault(f"{position}|ECR", {})[key] = evaluate_cell(
                pr, rl, depths=DEPTHS
            ).as_row()

        # --- FLEX: pool the treated RB/WR/TE predictions through the existing path ---
        base_flex = {
            pid: v
            for position in FLEX_POSITIONS
            for pid, v in control.for_week(snap.season, snap.week, position).items()
        }
        if not base_flex:
            continue
        commonf, boardf, keptf = flex_cell(con, snap, fmt, base_flex)
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        uni_f = {r.player_id for r in boardf.rows}
        for arm in arms_mod.ARMS:
            preds = (
                keptf
                if arm == arms_mod.CONTROL_ARM
                else {
                    pid: v
                    for position in FLEX_POSITIONS
                    for pid, v in trained[arm].for_week(snap.season, snap.week, position).items()
                }
            )
            _c, board, _k = flex_cell(con, snap, fmt, preds, universe=uni_f)
            pr, rl = board.ranks_and_points()
            cells.setdefault(f"FLEX|{arm}", {})[key] = evaluate_cell(pr, rl, depths=DEPTHS).as_row()
        pr, rl = commonf.ranks_and_points()
        cells.setdefault("FLEX|ECR", {})[key] = evaluate_cell(pr, rl, depths=DEPTHS).as_row()

    return {
        "cells": cells,
        "null_cells": null_cells,
        "movement": movement,
        "universes": universes,
    }


def _movement_row(snap, position, arm, rank0, board, preds, realized) -> dict:
    """How far players moved, who moved, and whether the top-10 got more bust-prone.

    The pre-registered guard against a metric that improves because the board became more extreme
    rather than more accurate (§7)."""
    rank1 = {r.player_id: r.ecr for r in board.rows}
    shared = sorted(set(rank0) & set(rank1))
    deltas = [rank0[p] - rank1[p] for p in shared]  # positive = moved UP
    real_rank = {
        p: i for i, p in enumerate(sorted(realized, key=lambda x: (-realized[x], x)), start=1)
    }
    top10 = [p for p in shared if rank1[p] <= FP_PRED_DEPTH]
    fp = sum(1 for p in top10 if real_rank.get(p, 10**6) > FP_REAL_DEPTH)
    vals = [preds[p] for p in shared if p in preds]
    return {
        "season": snap.season,
        "week": snap.week,
        "position": position,
        "arm": arm,
        "n": len(shared),
        "mean_abs_move": statistics.fmean(abs(d) for d in deltas) if deltas else None,
        "share_moved_gt5": (sum(1 for d in deltas if abs(d) > 5) / len(deltas)) if deltas else None,
        "share_moved_gt10": (
            (sum(1 for d in deltas if abs(d) > 10) / len(deltas)) if deltas else None
        ),
        "pred_sd": statistics.stdev(vals) if len(vals) > 1 else None,
        "pred_mean": statistics.fmean(vals) if vals else None,
        "top10_false_positives": fp,
        "top10_n": len(top10),
    }


def summarise(cells: dict, comparisons: list[tuple[str, str]]) -> dict:
    out: dict = {"distributions": {}, "paired": {}, "outcomes": {}}
    for name, weeks in cells.items():
        for metric in HEADLINE:
            vals = [
                r[metric]
                for _k, r in sorted(weeks.items())
                if not r.get("invalid") and r.get(metric) is not None
            ]
            d = noise.describe(metric, vals)
            if d:
                out["distributions"].setdefault(name, {})[metric] = d.as_row()
    for a_name, b_name in comparisons:
        if a_name not in cells or b_name not in cells:
            continue
        for metric in HEADLINE:
            a = {
                k: r[metric]
                for k, r in cells[a_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            b = {
                k: r[metric]
                for k, r in cells[b_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
            if pd_:
                out["paired"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = pd_.as_row()
            po = diagnostics.paired_outcome(metric, a_name, b_name, a, b)
            if po:
                out["outcomes"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = po.as_row()
    return out


def cliff(cells: dict, null_cells: dict, name: str) -> dict:
    """W5's cliff test, re-run per arm: actual minus its own same-Spearman null."""
    out: dict = {}
    actual, null = cells.get(name, {}), null_cells.get(name, {})
    for metric in (
        "spearman",
        *(f"capture@{k}" for k in DEPTHS),
        *(f"precision@{k}" for k in DEPTHS),
    ):
        a = {
            k: r[metric]
            for k, r in actual.items()
            if not r.get("invalid") and r.get(metric) is not None
        }
        b = {k: r[metric] for k, r in null.items() if r.get(metric) is not None}
        pd_ = noise.paired_difference(metric, "ACTUAL", "NULL", a, b)
        if pd_:
            out[metric] = pd_.as_row()
    return out


def leave_one_season_out(cells: dict, a_name: str, b_name: str, metric: str) -> dict:
    out: dict = {}
    for drop in SEASONS:
        a = {
            k: r[metric]
            for k, r in cells.get(a_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and not k.startswith(str(drop))
        }
        b = {
            k: r[metric]
            for k, r in cells.get(b_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and not k.startswith(str(drop))
        }
        pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
        if pd_:
            out[f"drop_{drop}"] = pd_.as_row()
    return out


def per_season(cells: dict, a_name: str, b_name: str, metric: str) -> dict:
    out: dict = {}
    for season in SEASONS:
        a = {
            k: r[metric]
            for k, r in cells.get(a_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and k.startswith(str(season))
        }
        b = {
            k: r[metric]
            for k, r in cells.get(b_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and k.startswith(str(season))
        }
        pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
        if pd_:
            out[str(season)] = pd_.as_row()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w6_results.json")
    ap.add_argument("--skip-half-ppr", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        snap = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(snap['local_path'])}"
        )

    print("[1/5] training the arms (one argument changes) ...")
    trained: dict[str, arms_mod.ArmPredictions] = {}
    for arm in arms_mod.ARMS:
        trained[arm] = arms_mod.train_arm(con, arm)
        print(
            f"      {arm:<9} loss={arms_mod.ARM_LOSS[arm]:<20} {len(trained[arm].by_key):,} preds"
        )

    control_check = arms_mod.compare_to_production(
        trained[arms_mod.CONTROL_ARM], arms_mod.load_production_predictions(con)
    )
    print(f"      control fidelity: {json.dumps(control_check)}")
    if control_check["exact_share"] != 1.0:
        raise SystemExit("GATE FAILED: the control arm does not reproduce production exactly")

    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"      weeks: {len(snapshots)}\n")

    print("[2/5] Full PPR: positional boards, FLEX, copula null per arm ...")
    full = run(con, snapshots, FULL_PPR, trained)
    print(f"      {len(full['cells'])} scored cells")

    print("[3/5] paired differences against the control ...")
    comparisons = []
    for position in (*ALL_POSITIONS, "FLEX"):
        for arm in arms_mod.ARMS:
            if arm == arms_mod.CONTROL_ARM:
                continue
            comparisons.append((f"{position}|{arm}", f"{position}|{arms_mod.CONTROL_ARM}"))
        comparisons.append((f"{position}|{arms_mod.CONTROL_ARM}", f"{position}|ECR"))
        comparisons.append((f"{position}|{arms_mod.PRIMARY_ARM}", f"{position}|ECR"))
    summary = summarise(full["cells"], comparisons)

    print("[4/5] cliff re-test per arm, robustness ...")
    cliffs = {
        f"{position}|{arm}": cliff(full["cells"], full["null_cells"], f"{position}|{arm}")
        for position in ALL_POSITIONS
        for arm in arms_mod.ARMS
    }
    primary = f"|{arms_mod.PRIMARY_ARM}"
    control = f"|{arms_mod.CONTROL_ARM}"
    loso = {
        position: {
            m: leave_one_season_out(
                full["cells"], f"{position}{primary}", f"{position}{control}", m
            )
            for m in ("capture@5", "capture@10")
        }
        for position in PRIMARY_POSITIONS
    }
    seasons = {
        position: {
            m: per_season(full["cells"], f"{position}{primary}", f"{position}{control}", m)
            for m in ("capture@5", "capture@10")
        }
        for position in PRIMARY_POSITIONS
    }

    half = None
    if not args.skip_half_ppr:
        print("      Half-PPR replication (replication only -- never a selection instrument) ...")
        h = run(
            con,
            snapshots,
            HALF_PPR,
            trained,
            null_arms=(arms_mod.CONTROL_ARM, arms_mod.PRIMARY_ARM),
        )
        half = {
            "summary": summarise(
                h["cells"],
                [
                    (f"{p}{primary}", f"{p}{control}")
                    for p in (*PRIMARY_POSITIONS, *GUARDRAIL_POSITIONS, "FLEX")
                ],
            ),
            "cliff": {
                f"{p}|{a}": cliff(h["cells"], h["null_cells"], f"{p}|{a}")
                for p in ALL_POSITIONS
                for a in (arms_mod.CONTROL_ARM, arms_mod.PRIMARY_ARM)
            },
        }

    print("[5/5] writing ...")
    for position in PRIMARY_POSITIONS:
        k = f"{position}{primary}_vs_{position}{control}"
        for m in ("capture@5", "capture@10"):
            v = summary["paired"].get(k, {}).get(m)
            o = summary["outcomes"].get(k, {}).get(m)
            if v:
                print(
                    f"  {position} {m}: {v['mean_diff']:+.4f} "
                    f"CI[{v['ci_low']:+.4f},{v['ci_high']:+.4f}] "
                    f"W-L={o.get('a_wins')}-{o.get('b_wins')}"
                )

    result = {
        "provenance": {
            "arms": {a: arms_mod.ARM_LOSS[a] for a in arms_mod.ARMS},
            "primary_arm": arms_mod.PRIMARY_ARM,
            "control_arm": arms_mod.CONTROL_ARM,
            "base_kwargs": arms_mod.BASE_KWARGS,
            "control_fidelity": control_check,
            "n_sim": nulls.N_SIM,
            "depths": list(DEPTHS),
        },
        "n_weeks": len(snapshots),
        "cells": full["cells"],
        "null_cells": full["null_cells"],
        "summary": summary,
        "cliff": cliffs,
        "movement": full["movement"],
        "universes": full["universes"],
        "robustness_loso": loso,
        "per_season": seasons,
        "half_ppr": half,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
