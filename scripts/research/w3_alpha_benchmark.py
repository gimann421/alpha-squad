"""W3 --- Alpha (no ECR) vs the season-to-date baseline vs FantasyPros ECR.

Runs exactly what `docs/weekly/W3_PREREGISTRATION.md` specifies. **Builds no model, fits
nothing, tunes nothing.** It reads the weekly predictions the unmodified
`alpha-squad train established` path already wrote, and scores them with W2's frozen metric
suite over W2's frozen universe.

    uv run alpha-squad train established --season-start 2021 --season-end 2025 \
        --min-train-season 2015                        # writes weekly_projection_snapshot
    uv run python scripts/research/w3_alpha_benchmark.py --out reports/weekly/w3_results.json

Read-only against the database; writes one JSON.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import alpha as alpha_mod
from alpha_squad.evaluation.weekly import audit, benchmark, diagnostics, noise
from alpha_squad.evaluation.weekly.metrics import DEPTHS, evaluate_cell
from alpha_squad.evaluation.weekly.scoring import FULL_PPR
from alpha_squad.identity.canonical import reader_expr, require_snapshot

SEASONS = (2021, 2022, 2023, 2024, 2025)
#: Boards where all three systems exist. K and DST are ECR-only (the model has no K/DST), so
#: they are deliberately absent -- W3 does not report a "three-way" comparison with two systems.
BOARDS = ("FLEX", "QB", "RB", "WR", "TE")
HEADLINE = (
    "spearman",
    "kendall",
    "pairwise",
    "decisive",
    *(f"capture@{k}" for k in DEPTHS),
    *(f"precision@{k}" for k in DEPTHS),
)
SYSTEMS = ("ALPHA", "ECR", "B0_season_to_date_ppg", "B1_prior_season_ppg")


def wire(con: duckdb.DuckDBPyConnection) -> dict:
    ecr = require_snapshot(con, "dynastyprocess", "fp_ecr_history")
    xw = require_snapshot(con, "dynastyprocess", "player_ids")
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW ecr AS SELECT * FROM {reader_expr(ecr['local_path'])}"
    )
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW xwalk AS SELECT * FROM {reader_expr(xw['local_path'])}"
    )
    return {
        "ecr_snapshot_id": ecr["snapshot_id"],
        "ecr_sha256": ecr["sha256"],
        "xwalk_sha256": xw["sha256"],
        "alpha_model": alpha_mod.WEEKLY_PROJECTION_BASE_MODEL,
    }


def _reference_board(con, snap, label):
    if label == "FLEX":
        return benchmark.flex_board(con, snap, FULL_PPR)
    return benchmark.positional_board(con, snap, label, FULL_PPR)


def run(con, snapshots) -> tuple[dict, dict, dict]:
    """Every cell's metrics for all four systems, plus coverage and FLEX composition.

    The universe rule (pre-registered §4): take ECR's board, keep players who PLAYED, then
    keep only those Alpha can also rank -- and apply that same restriction to ECR and both
    baselines, so all four systems are scored on a byte-identical player set."""
    cells: dict[str, dict] = {}
    coverage: list[dict] = []
    composition: dict[str, list] = {}

    for snap in snapshots:
        for label in BOARDS:
            ref = _reference_board(con, snap, label)
            # Restrict to players who actually played: the evaluable set every system shares.
            played = {r.player_id for r in ref.evaluable}
            ref_played = alpha_mod.restrict_board(ref, played)

            positions = ("RB", "WR", "TE") if label == "FLEX" else (label,)
            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=positions
            )
            alpha_b, cov = alpha_mod.alpha_board(ref_played, preds)
            coverage.append(
                {
                    "season": snap.season,
                    "week": snap.week,
                    "board": label,
                    "universe": cov.universe,
                    "alpha_ranked": cov.alpha_ranked,
                    "coverage": cov.coverage,
                }
            )

            keep = {r.player_id for r in alpha_b.rows}
            common = alpha_mod.restrict_board(ref_played, keep)
            systems = {
                "ALPHA": alpha_b,
                "ECR": common,
                **benchmark.baseline_boards(con, common, FULL_PPR),
            }

            key_week = f"{snap.season}-{snap.week}"
            for sysname, board in systems.items():
                pred, real = board.ranks_and_points()
                slot = cells.setdefault(f"{label}|{sysname}", {})
                if len(pred) < benchmark.MIN_EVALUABLE:
                    slot[key_week] = {"invalid": True, "n": len(pred)}
                    continue
                row = evaluate_cell(pred, real).as_row()
                row["n_universe"] = len(common.rows)
                slot[key_week] = row

            # SECONDARY: point diagnostics, Alpha only (ECR has no point projection).
            ordered = sorted(alpha_b.rows, key=lambda r: r.ecr)
            pd_ = diagnostics.point_diagnostics(
                [preds[r.player_id] for r in ordered],
                [float(r.realized) for r in ordered],
            )
            if pd_:
                cells.setdefault(f"{label}|ALPHA_POINTS", {})[key_week] = pd_.as_row()

            if label == "FLEX":
                for sysname in ("ALPHA", "ECR", "B0_season_to_date_ppg"):
                    b = systems[sysname]
                    ordered_b = sorted(b.rows, key=lambda r: r.ecr)
                    pos = [r.position for r in ordered_b]
                    pr = [r.ecr for r in ordered_b]
                    rl = [float(r.realized) for r in ordered_b]
                    for k in DEPTHS:
                        comp = diagnostics.flex_composition(pos, pr, rl, k)
                        if comp:
                            composition.setdefault(f"{sysname}@{k}", []).append(comp)
    return cells, {"per_cell": coverage}, composition


def summarise(cells: dict) -> dict:
    out: dict = {"distributions": {}, "paired": {}, "outcomes": {}, "invalid_cells": {}}
    by_board: dict[str, dict[str, dict]] = {}
    for key, weeks in cells.items():
        label, sysname = key.split("|")
        if sysname not in SYSTEMS:
            continue
        by_board.setdefault(label, {})[sysname] = weeks

    for label, systems in by_board.items():
        for sysname, weeks in systems.items():
            invalid = [w for w, r in weeks.items() if r.get("invalid")]
            out["invalid_cells"][f"{label}|{sysname}"] = len(invalid)
            for metric in HEADLINE:
                vals = [
                    r.get(metric)
                    for r in weeks.values()
                    if not r.get("invalid") and r.get(metric) is not None
                ]
                d = noise.describe(metric, vals)
                if d:
                    out["distributions"].setdefault(label, {}).setdefault(sysname, {})[metric] = (
                        d.as_row()
                    )

        # The three pre-registered primary comparisons.
        for a_name, b_name in (
            ("ALPHA", "B0_season_to_date_ppg"),
            ("ECR", "B0_season_to_date_ppg"),
            ("ALPHA", "ECR"),
        ):
            if a_name not in systems or b_name not in systems:
                continue
            for metric in HEADLINE:
                a = {
                    k: r[metric]
                    for k, r in systems[a_name].items()
                    if not r.get("invalid") and r.get(metric) is not None
                }
                b = {
                    k: r[metric]
                    for k, r in systems[b_name].items()
                    if not r.get("invalid") and r.get(metric) is not None
                }
                pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
                if pd_:
                    out["paired"].setdefault(label, {}).setdefault(f"{a_name}_vs_{b_name}", {})[
                        metric
                    ] = pd_.as_row()
                po = diagnostics.paired_outcome(metric, a_name, b_name, a, b)
                if po:
                    out["outcomes"].setdefault(label, {}).setdefault(f"{a_name}_vs_{b_name}", {})[
                        metric
                    ] = po.as_row()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w3_results.json")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    prov = wire(con)
    n_preds = con.execute(
        "SELECT count(*) FROM weekly_projection_snapshot WHERE model_name = ?",
        [alpha_mod.WEEKLY_PROJECTION_BASE_MODEL],
    ).fetchone()[0]
    if not n_preds:
        raise SystemExit(
            "weekly_projection_snapshot is empty -- run `alpha-squad train established "
            "--season-start 2021 --season-end 2025 --min-train-season 2015` first."
        )
    print(f"provenance: {json.dumps(prov, indent=2)}")
    print(f"alpha weekly predictions on file: {n_preds}")

    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"weeks: {len(snapshots)}\n")

    print("[1/2] building boards for all four systems and scoring the frozen suite ...")
    cells, coverage, composition = run(con, snapshots)

    print("[2/2] distributions, paired differences, win/loss, Wilcoxon ...")
    summary = summarise(cells)

    cov_vals = [c["coverage"] for c in coverage["per_cell"]]
    print(
        f"      Alpha coverage of the evaluable universe: "
        f"mean {statistics.fmean(cov_vals):.4f}, min {min(cov_vals):.4f}"
    )

    result = {
        "provenance": prov,
        "n_weeks": len(snapshots),
        "cells": cells,
        "summary": summary,
        "coverage": coverage,
        "flex_composition": composition,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
