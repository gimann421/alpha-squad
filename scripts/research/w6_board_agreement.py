"""W6 --- how much did the boards actually MOVE? (brief Part 7)

The arms differ enormously in the *level* of their predictions -- RB's mean prediction rises from
6.86 under MAE to 12.63 under an 80th-percentile target -- and not at all in what a fantasy
manager reads, which is the **order**. A monotone rescaling changes no ranking (W3), so a target
change can only matter to the extent that it **reorders** players.

This instrument measures exactly that, and nothing else: for every (week, position), the rank
correlation between the control board and each arm's board, the size of the top-10 set overlap,
and how often the top 10 is literally the same ten players. It is deliberately separate from the
main runner so that adding it could not disturb a byte-identical result that had already passed
its determinism gate.

    uv run python scripts/research/w6_board_agreement.py --out reports/weekly/w6_agreement.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import spearman  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    ALL_POSITIONS,
    SEASONS,
    positional_cell,
)

TOP_K = 10


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w6_agreement.json")
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

    trained = {arm: arms_mod.train_arm(con, arm) for arm in arms_mod.ARMS}
    weeks = audit.week_coverage(con, SEASONS).snapshots
    rows: list[dict] = []

    for snap in weeks:
        for position in ALL_POSITIONS:
            base = trained[arms_mod.CONTROL_ARM].for_week(snap.season, snap.week, position)
            if not base:
                continue
            common, board0, kept0 = positional_cell(con, snap, position, FULL_PPR, base)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            universe = {r.player_id for r in board0.rows}
            rank0 = {r.player_id: r.ecr for r in board0.rows}
            top0 = {p for p, v in rank0.items() if v <= TOP_K}
            ids = sorted(rank0)
            for arm in arms_mod.ARMS:
                preds = (
                    kept0
                    if arm == arms_mod.CONTROL_ARM
                    else trained[arm].for_week(snap.season, snap.week, position)
                )
                _c, board, _k = positional_cell(
                    con, snap, position, FULL_PPR, preds, universe=universe
                )
                rank1 = {r.player_id: r.ecr for r in board.rows}
                top1 = {p for p, v in rank1.items() if v <= TOP_K}
                rows.append(
                    {
                        "season": snap.season,
                        "week": snap.week,
                        "position": position,
                        "arm": arm,
                        "n": len(ids),
                        # Rank correlation between the two BOARDS -- 1.0 means the target change
                        # was a pure rescaling and could not have moved any metric.
                        "board_spearman": spearman(
                            [rank0[p] for p in ids], [-rank1[p] for p in ids]
                        ),
                        "top10_overlap": len(top0 & top1) / TOP_K,
                        "top10_identical": float(top0 == top1),
                        "order_identical": float(all(rank0[p] == rank1[p] for p in ids)),
                    }
                )

    out: dict = {"top_k": TOP_K, "n_weeks": len(weeks), "rows": rows, "summary": {}}
    for position in ALL_POSITIONS:
        for arm in arms_mod.ARMS:
            sel = [r for r in rows if r["position"] == position and r["arm"] == arm]
            if not sel:
                continue
            out["summary"][f"{position}|{arm}"] = {
                "cells": len(sel),
                "board_spearman_mean": statistics.fmean(
                    r["board_spearman"] for r in sel if r["board_spearman"] is not None
                ),
                "top10_overlap_mean": statistics.fmean(r["top10_overlap"] for r in sel),
                "top10_identical_share": statistics.fmean(r["top10_identical"] for r in sel),
                "order_identical_share": statistics.fmean(r["order_identical"] for r in sel),
            }

    print(
        f"{'cell':<18}{'board rho':>11}{'top10 overlap':>15}{'top10 identical':>17}{'board identical':>17}"
    )
    for k, v in out["summary"].items():
        print(
            f"{k:<18}{v['board_spearman_mean']:>11.4f}{v['top10_overlap_mean']:>15.3f}"
            f"{v['top10_identical_share']:>17.1%}{v['order_identical_share']:>17.1%}"
        )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
