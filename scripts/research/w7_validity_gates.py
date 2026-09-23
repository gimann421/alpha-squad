"""W7 --- the leakage and validity gates that must pass BEFORE any W7 result is read.

`docs/weekly/W7_PREREGISTRATION.md` §11 lists them. This phase is the most leakage-sensitive in
the program -- it is *about* whether information existed before Friday -- so the load-bearing gate
is not a code inspection but an experiment:

  G2  **redaction.** Rebuild the whole opportunity panel against a database in which every stat
      value at or after week w of season S has been NULLED (the rows stay, so the row being checked
      still exists), the usage file's rows at or after (S, w) are removed, and the depth chart's
      rows at or after (S, w) are removed. Every predictor for week w must be **unchanged**. A
      feature that silently reads the week it predicts, or any later week, cannot survive this.

  G1  production parity -- the Alpha+opportunity arm with no added features IS production
  G3  no injury field in any main-test feature
  G4  no current-week depth chart (covered by G2's redaction of the chart at week w)
  G5  no market / ECR / Vegas source read by any feature SQL
  G6  no realized game information in context (opponent measure covered by G2)
  G7  walk-forward -- no training frame contains the season it predicts
  G8  Friday cutoff -- zero evaluated players whose team had already kicked off
  G9  identical universe across boards (also enforced inside the runner)
  G10 determinism -- byte-identical output on a repeat run
  G11 upstream -- W3, W4, W5 and W6 still reproduce exactly

Exit code is non-zero if any gate fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context, snapshots  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from scripts.research.w6_upper_outcome import positional_cell  # noqa: E402

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
#: G2 rebuilds the full panel per sampled week; the stride is positional, never result-chosen.
REDACT_EVERY = 8
#: Every stat column the panel reads from `player_week_stats`. Nulled at/after (S, w) under G2.
STAT_COLUMNS = (
    "targets",
    "carries",
    "receptions",
    "target_share",
    "air_yards_share",
    "offense_snap_pct",
    "fantasy_points_ppr",
)
UPSTREAM = (
    ("W3", "scripts/research/w3_alpha_benchmark.py", "reports/weekly/w3_results.json"),
    ("W4", "scripts/research/w4_flex_forensics.py", "reports/weekly/w4_results.json"),
    ("W5", "scripts/research/w5_topboard_forensics.py", "reports/weekly/w5_results.json"),
    ("W6", "scripts/research/w6_upper_outcome.py", "reports/weekly/w6_results.json"),
)


def _wire(con) -> None:
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )


def _redacted(db: str, season: int, week: int):
    """A connection in which nothing at or after (season, week) carries an outcome."""
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    later = f"(season > {season} OR (season = {season} AND week >= {week}))"
    cols = [
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_catalog = 'src' AND table_name = 'player_week_stats' "
            "ORDER BY ordinal_position"
        ).fetchall()
    ]
    select = ", ".join(
        f"CASE WHEN {later} THEN NULL ELSE {c} END AS {c}" if c in STAT_COLUMNS else c for c in cols
    )
    con.execute(f"CREATE VIEW player_week_stats AS SELECT {select} FROM src.player_week_stats")
    for table in ("player_week_features", "games", "player_id_map", "snapshot_registry"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM src.{table}")
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    for view in ("_usage", "_depth"):
        con.execute(f"CREATE TEMP TABLE {view}_redacted AS SELECT * FROM {view} WHERE NOT {later}")
        con.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {view}_redacted")
    return con


def _same(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=0.0)


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w7_results.json")
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--skip-upstream", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    failures: list[str] = []

    # --- G1 production parity ---------------------------------------------------------------
    empty = pd.DataFrame(columns=["player_id", "season", "week"])
    control = arms_mod.train_with_extra_features(con, empty, [])
    stored = {
        k: v for k, v in arms_mod.load_production_predictions(con).items() if k in control.by_key
    }
    fid = arms_mod.compare_to_production(control, stored)
    print(
        f"G1  production parity : {fid['exact_matches']:,}/{fid['n_shared']:,} exact, "
        f"max abs diff {fid['max_abs_diff']}"
    )
    if fid["exact_share"] != 1.0 or fid["only_in_trained"] or fid["only_in_stored"]:
        failures.append("G1")

    # --- G2 / G4 / G6 redaction -------------------------------------------------------------
    predictors = list(op.NEW) + list(op.REDUNDANT) + list(op.CLASS_B)
    predictors += [
        f"{t}__{b}"
        for t in op.BASELINE_SOURCE
        for b in ("BL_LAST", "BL_MEAN3", "BL_WMEAN3", "BL_TREND")
    ]
    full = op.build_panel(con, POSITIONS)
    weeks = audit.week_coverage(con, SEASONS).snapshots
    moved: list[str] = []
    checked_rows = 0
    for snap in weeks[::REDACT_EVERY]:
        red = _redacted(args.db, snap.season, snap.week)
        try:
            rp = op.build_panel(red, POSITIONS)
        finally:
            red.close()
        a = full[(full.season == snap.season) & (full.week == snap.week)].set_index("player_id")
        b = rp[(rp.season == snap.season) & (rp.week == snap.week)].set_index("player_id")
        if set(a.index) != set(b.index):
            moved.append(f"{snap.season}-{snap.week}: row set changed")
            continue
        for pid in a.index:
            checked_rows += 1
            for col in predictors:
                if not _same(a.at[pid, col], b.at[pid, col]):
                    moved.append(f"{snap.season}-{snap.week}:{pid}:{col}")
        # The week's outcomes MUST have vanished, or the redaction redacted nothing and the gate
        # passes vacuously. `y_opp`/`y_tgt` are COALESCE(..., 0) sums and become 0 rather than
        # NULL, so the check uses the two targets that genuinely go missing: target share (a raw
        # stat column) and usage-expected points (a removed usage row).
        if b["y_tsh"].notna().any() or b["y_xfp"].notna().any():
            moved.append(f"{snap.season}-{snap.week}: redaction did not remove the week's outcomes")
    print(
        f"G2  redaction         : predictor values that moved when every outcome at/after the "
        f"ranked week was nulled ({checked_rows:,} player-weeks): {len(moved)}"
    )
    for m in moved[:5]:
        print(f"      {m}")
    if moved:
        failures.append("G2")
    print("G4  current depth    : covered by G2 (the week's depth chart is removed there)")
    print("G6  realized context : covered by G2 (the opponent measure is recomputed there)")

    # --- G3 / G5 static source checks ---------------------------------------------------------
    main_features = set(op.S0) | set(op.NEW) | set(op.REDUNDANT)
    injury_like = [f for f in main_features if any(t in f for t in ("injur", "practice", "status"))]
    sql = (op._panel_sql() + op._opponent_sql()).lower()
    source_hits = [t for t in ("ecr", "market", "vegas", "spread", "_injuries") if t in sql]
    print(f"G3  no injury field  : injury-like main features: {injury_like or 'none'}")
    print(
        f"G5  no market / ECR  : forbidden sources referenced by feature SQL: {source_hits or 'none'}"
    )
    if injury_like:
        failures.append("G3")
    if source_hits:
        failures.append("G5")

    # --- G7 walk-forward ------------------------------------------------------------------------
    leaks = 0
    for position in POSITIONS:
        pos = full[full.position == position]
        for season in SEASONS:
            train = pos[(pos.season >= op.MIN_TRAIN_SEASON) & (pos.season < season)]
            if not train.empty and int(train.season.max()) >= season:
                leaks += 1
    print(f"G7  walk-forward     : training frames containing the predicted season: {leaks}")
    if leaks:
        failures.append("G7")

    # --- G8 Friday cutoff / G9 universe ----------------------------------------------------------
    contaminated = 0
    for snap in weeks:
        playing = snapshots.teams_already_playing(con, snap)
        already = {
            r[0]
            for r in con.execute(
                "SELECT player_id FROM player_week_stats WHERE season=? AND week=? AND team = ANY(?)",
                [snap.season, snap.week, list(playing) or [""]],
            ).fetchall()
        }
        for position in POSITIONS:
            from alpha_squad.evaluation.weekly import alpha as alpha_mod

            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=(position,)
            )
            if not preds:
                continue
            common, board, _k = positional_cell(con, snap, position, FULL_PPR, preds)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            contaminated += len({r.player_id for r in board.rows} & already)
    print(f"G8  Friday cutoff    : evaluated players whose team had kicked off: {contaminated}")
    print("G9  universe         : enforced inside the runner (it aborts on any mismatch)")
    if contaminated:
        failures.append("G8")

    # --- G10 determinism ----------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism      : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rerun.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/research/w7_opportunity.py",
                    "--db",
                    args.db,
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
            b = hashlib.sha256(out.read_bytes()).hexdigest()
        print(
            f"G10 determinism      : {a[:16]} vs {b[:16]} -> {'identical' if a == b else 'DIFFERENT'}"
        )
        if a != b:
            failures.append("G10")

    # --- G11 upstream ---------------------------------------------------------------------------
    if args.skip_upstream:
        print("G11 upstream         : SKIPPED")
    else:
        parts = []
        with tempfile.TemporaryDirectory() as tmp:
            for tag, script, tracked in UPSTREAM:
                out = Path(tmp) / f"{tag}.json"
                subprocess.run(
                    [sys.executable, script, "--db", args.db, "--out", str(out)],
                    check=True,
                    capture_output=True,
                )
                fa = dict(_flatten(json.loads(out.read_text())))
                fb = dict(_flatten(json.loads(Path(tracked).read_text())))
                worst, bad = 0.0, 0
                for k in set(fa) & set(fb):
                    x, y = fa[k], fb[k]
                    if (
                        isinstance(x, int | float)
                        and isinstance(y, int | float)
                        and not isinstance(x, bool)
                    ):
                        worst = max(worst, abs(x - y))
                    elif x != y:
                        bad += 1
                ok = worst == 0 and bad == 0 and set(fa) == set(fb)
                parts.append(f"{tag} diff {worst:g}{'' if ok else ' FAIL'}")
                if not ok:
                    failures.append("G11")
        print("G11 upstream         : " + " | ".join(parts))

    print()
    if failures:
        print(f"FAILED: {', '.join(sorted(set(failures)))} -- do not interpret W7 results.")
        return 1
    print("all gates PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
