"""W8 --- EXPLORATORY, POST-HOC: is ECR's surprise piece G_S an artifact of the instrument?

**Added after the pre-registered results were read, and excluded from every verdict.** It
checks one specific worry about the decomposition `G = G_F + G_S + G_C`:

    s = x - f, so a board that prefers players the Class A forecast `f` under-rates will show a
    NEGATIVE G_F -- and, if those players merely regress to their forecast, a mechanically
    POSITIVE G_S that has nothing to do with knowing anything.

The test: decompose boards built from **Class A information only** against Alpha, with exactly the
same instrument. They cannot know this week's usage surprise. If they, too, show a positive
G_S (or a positive rho(d, s)) when they disagree with Alpha, ECR's positive G_S is not evidence of
information. If they show ~0 or negative, it is.

  FORECAST_USAGE  rank by the Class A usage forecast f itself (W7)
  ALPHA_PLUS_OPP  Alpha retrained with W7's 9 Class A features (W7's one-change arm)
  LAST3_POINTS    rank by fantasy points per game over the last 3 appearances (Class A)
  ECR             the benchmark, for side-by-side comparison with the main run

    uv run python scripts/research/w8_null_check.py --out reports/weekly/w8_null_check.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, context  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from scripts.research.w7_opportunity import universes  # noqa: E402
from scripts.research.w8_ecr_advantage import (  # noqa: E402
    POSITIONS,
    REGION_DEPTH,
    SEASONS,
    ZERO,
    _put,
    collect,
    compare,
)

BOARDS = ("FORECAST_USAGE", "ALPHA_PLUS_OPP", "LAST3_POINTS", "ECR")
K = 10


def _order(ids, score: dict[str, float], tiebreak: dict[str, float]) -> list[str]:
    return sorted(ids, key=lambda p: (-score[p], tiebreak[p], p))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w8_null_check.json")
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
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    panel = op.build_panel(con, POSITIONS)
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    fc_opp = {p: op.walk_forward(panel, p, "T_OPP", "M_NEW", SEASONS) for p in POSITIONS}
    plus = arms_mod.train_with_extra_features(con, panel, list(op.NEW))
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    cells = collect(con, universes(con, snapshots, FULL_PPR), panel, fc, fc_opp, 1.0)

    store: dict = {}
    for (key, position), cell in sorted(cells.items()):
        snap, rows = cell["snap"], cell["rows"]
        ids = list(rows)
        tb = cell["rank_a"]
        plus_preds = plus.for_week(snap.season, snap.week, position)
        last3 = {}
        for p in ids:
            v = panel.at[idx[(p, snap.season, snap.week)], "fp_ppr_avg_last3"]
            last3[p] = float(v) if v == v else 0.0
        orders = {
            "FORECAST_USAGE": _order(ids, {p: rows[p].f for p in ids}, tb),
            "ALPHA_PLUS_OPP": _order(ids, plus_preds, tb),
            "LAST3_POINTS": _order(ids, last3, tb),
            "ECR": cell["order_e"],
        }
        for name, order in orders.items():
            dec = adv.decompose_gap(order, cell["order_a"], rows, K)
            if dec is None:
                continue
            for piece in ("G", "G_F", "G_S", "G_C"):
                _put(store, f"{position}|{name}", key, f"{piece}@{K}", dec[piece])
                _put(store, ZERO, key, f"{piece}@{K}", 0.0)
            rank_z = {p: float(n) for n, p in enumerate(order, start=1)}
            region = sorted(
                p for p in ids if cell["rank_a"][p] <= REGION_DEPTH or rank_z[p] <= REGION_DEPTH
            )
            d = [cell["rank_a"][p] - rank_z[p] for p in region]
            for comp in ("s", "c", "f"):
                vals = [getattr(rows[p], comp) for p in region]
                _put(
                    store, f"{position}|{name}", key, f"rho_d_{comp}", adv.spearman_values(d, vals)
                )
                _put(store, ZERO, key, f"rho_d_{comp}", 0.0)

    metrics = [f"{p}@{K}" for p in ("G", "G_F", "G_S", "G_C")] + [
        f"rho_d_{c}" for c in ("s", "c", "f")
    ]
    result = {
        "note": "EXPLORATORY, post-hoc instrument check; excluded from every W8 verdict",
        "k": K,
        "region_depth": REGION_DEPTH,
        "boards": {
            f"{pos}|{b}": compare(store, f"{pos}|{b}", ZERO, metrics)
            for pos in POSITIONS
            for b in BOARDS
        },
    }
    for pos in POSITIONS:
        for b in BOARDS:
            r = result["boards"][f"{pos}|{b}"]
            print(
                f"  {pos} {b:15s} "
                + "  ".join(
                    f"{m} {r[m]['mean_diff']:+.4f}{'*' if r[m]['excludes_zero'] else ' '}"
                    for m in metrics
                    if m in r
                )
            )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
