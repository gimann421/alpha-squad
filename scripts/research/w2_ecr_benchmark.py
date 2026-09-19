"""W2 --- the ECR-alone weekly benchmark and its noise floor.

Runs exactly what `docs/weekly/W2_PREREGISTRATION.md` (including amendment A1) specifies, and
nothing else. **No Alpha system is built, fitted or compared.**

    uv run python scripts/research/w2_ecr_benchmark.py --out reports/weekly/w2_results.json

Read-only against `data/alpha_squad.duckdb`; writes one JSON of results.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import audit, benchmark, noise
from alpha_squad.evaluation.weekly.metrics import DEPTHS, evaluate_cell
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR, format_by_name
from alpha_squad.identity.canonical import reader_expr, require_snapshot

SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
#: Metrics carried into the noise-floor analysis. Chosen in the pre-registration, not here.
HEADLINE = (
    "spearman",
    "kendall",
    "pairwise",
    "decisive",
    *(f"capture@{k}" for k in DEPTHS),
    *(f"precision@{k}" for k in DEPTHS),
)


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
        "ecr_captured_at": str(ecr["captured_at"]),
        "xwalk_sha256": xw["sha256"],
    }


def run_boards(con, snapshots, fmt, label_filter=None) -> dict:
    """Every cell's metrics, for ECR and the two reference baselines."""
    out: dict[str, dict] = {}
    for snap in snapshots:
        boards = {"FLEX": benchmark.flex_board(con, snap, fmt)}
        for pos in POSITIONS:
            boards[pos] = benchmark.positional_board(con, snap, pos, fmt)
        for label, board in boards.items():
            if label_filter and label != label_filter:
                continue
            systems = {"ECR": board, **benchmark.baseline_boards(con, board, fmt)}
            for sysname, b in systems.items():
                pred, real = b.ranks_and_points()
                if len(pred) < benchmark.MIN_EVALUABLE:
                    out.setdefault(f"{label}|{sysname}", {})[f"{snap.season}-{snap.week}"] = {
                        "invalid": True,
                        "n": len(pred),
                    }
                    continue
                row = evaluate_cell(pred, real).as_row()
                row["ranked"] = len(b.rows)
                row["availability"] = b.availability
                out.setdefault(f"{label}|{sysname}", {})[f"{snap.season}-{snap.week}"] = row
    return out


def summarise(cells: dict) -> dict:
    """Per-week distributions and paired differences vs each reference baseline."""
    summary: dict = {"distributions": {}, "paired": {}, "invalid_cells": {}}
    by_board: dict[str, dict[str, dict]] = {}
    for key, weeks in cells.items():
        label, sysname = key.split("|")
        by_board.setdefault(label, {})[sysname] = weeks

    for label, systems in by_board.items():
        for sysname, weeks in systems.items():
            invalid = [w for w, r in weeks.items() if r.get("invalid")]
            summary["invalid_cells"][f"{label}|{sysname}"] = {
                "n_invalid": len(invalid),
                "weeks": invalid,
            }
            for metric in HEADLINE:
                vals = [r.get(metric) for r in weeks.values() if not r.get("invalid")]
                d = noise.describe(metric, [v for v in vals if v is not None])
                if d:
                    summary["distributions"].setdefault(label, {}).setdefault(sysname, {})[
                        metric
                    ] = d.as_row()
        ecr = systems.get("ECR")
        if not ecr:
            continue
        for other in ("B0_season_to_date_ppg", "B1_prior_season_ppg"):
            if other not in systems:
                continue
            for metric in HEADLINE:
                a = {
                    k: r[metric]
                    for k, r in ecr.items()
                    if not r.get("invalid") and r.get(metric) is not None
                }
                b = {
                    k: r[metric]
                    for k, r in systems[other].items()
                    if not r.get("invalid") and r.get(metric) is not None
                }
                pd = noise.paired_difference(metric, "ECR", other, a, b)
                if pd:
                    summary["paired"].setdefault(label, {}).setdefault(other, {})[metric] = (
                        pd.as_row()
                    )
    return summary


def validate_reconstruction(con, snapshots, cache_dir: str) -> dict:
    """Pre-registered A1 check: does the mirror's reconstructed FLEX top-10 match the REAL
    FantasyPros FLEX top-10? Decision threshold (fixed in A1): median overlap >= 0.70."""
    files = sorted(glob.glob(f"{cache_dir}/*/wk*/FLX_PPR.json"))
    by_week = {}
    for f in files:
        b = json.load(open(f))
        by_week[(b["season"], b["week"])] = b
    snap_by_week = {(s.season, s.week): s for s in snapshots}
    overlaps, rows = [], []
    for (season, week), api in sorted(by_week.items()):
        snap = snap_by_week.get((season, week))
        if not snap or not api.get("players"):
            continue
        board = benchmark.flex_board(con, snap, FULL_PPR)
        mirror_top = [r.player_id for r in board.rows[:10]]
        # Resolve the API's FantasyPros ids to canonical player ids through the same crosswalk.
        fp_ids = [str(p["player_id"]) for p in api["players"]]
        api_top = [
            r[0]
            for r in con.execute(
                """
                WITH x AS (SELECT DISTINCT fantasypros_id, gsis_id FROM xwalk
                           WHERE gsis_id IS NOT NULL)
                SELECT p.player_id, CAST(x.fantasypros_id AS VARCHAR) FROM x
                JOIN players p ON p.gsis_id = x.gsis_id
                WHERE CAST(x.fantasypros_id AS VARCHAR) = ANY(?)
                """,
                [fp_ids],
            ).fetchall()
        ]
        if not api_top or not mirror_top:
            continue
        ov = len(set(mirror_top) & set(api_top)) / 10.0
        overlaps.append(ov)
        rows.append(
            {
                "season": season,
                "week": week,
                "overlap": ov,
                "api_resolved": len(api_top),
                "mirror_n": len(board.rows),
            }
        )
    verdict = None
    if overlaps:
        med = statistics.median(overlaps)
        verdict = "reconstruction_sound" if med >= 0.70 else "reconstruction_weak"
    return {
        "n_weeks": len(overlaps),
        "median_overlap": statistics.median(overlaps) if overlaps else None,
        "mean_overlap": statistics.fmean(overlaps) if overlaps else None,
        "min_overlap": min(overlaps) if overlaps else None,
        "max_overlap": max(overlaps) if overlaps else None,
        "threshold": 0.70,
        "verdict": verdict,
        "per_week": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--scoring", default="full_ppr")
    ap.add_argument("--cache", default="reports/weekly/fp_api_cache")
    ap.add_argument("--out", default="reports/weekly/w2_results.json")
    args = ap.parse_args()

    fmt = format_by_name(args.scoring)
    con = duckdb.connect(args.db, read_only=True)
    prov = wire(con)
    wc = audit.week_coverage(con, SEASONS)
    snapshots = wc.snapshots
    print(f"provenance: {json.dumps(prov, indent=2)}")
    print(f"weeks: {len(snapshots)}  scoring: {fmt.name}")

    print("\n[1/4] building boards and computing the frozen metric suite ...")
    cells = run_boards(con, snapshots, fmt)
    print(f"      {len(cells)} board x system series")

    print("[2/4] per-week distributions + paired differences ...")
    summary = summarise(cells)

    print("[3/4] validating the FLEX reconstruction against the real FantasyPros board ...")
    recon = validate_reconstruction(con, snapshots, args.cache)
    print(
        f"      n_weeks={recon['n_weeks']} median_overlap={recon['median_overlap']} "
        f"verdict={recon['verdict']}"
    )

    print("[4/4] secondary: Half-PPR outcomes against the same (full-PPR-ranked) boards ...")
    half_cells = run_boards(con, snapshots, HALF_PPR, label_filter="FLEX")
    half_summary = summarise(half_cells)

    result = {
        "provenance": prov,
        "scoring": fmt.name,
        "n_weeks": len(snapshots),
        "covered_weeks": wc.covered,
        "uncovered_weeks": wc.uncovered,
        "cells": cells,
        "summary": summary,
        "reconstruction_validation": recon,
        "half_ppr_secondary": half_summary,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
