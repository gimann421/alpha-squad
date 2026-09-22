"""W5 --- the validity gates that must pass BEFORE any W5 result is interpreted.

`docs/weekly/W5_PREREGISTRATION.md` §12 lists them and states the rule: *"If any gate fails, stop
and fix the instrument before reading results."* W4's G4 failure is the precedent -- it was real,
and fixing it changed a reportable number -- so this is a committed instrument (D92) rather than
a sentence in a document.

  G1  causality        the prior-window predicate admits nothing at or after the ranked week
  G2  no-outcome-leak  every pre-cutoff context value is UNCHANGED when the current week's
                       outcome rows are deleted from the database
  G3  universe         every system ranks the identical player set, cell by cell
  G4  position         every player on a positional board actually plays that position
  G5  oracle           ORACLE_OUTCOME is perfect; ORACLE_USAGE preserves the universe
  G6  no-ECR           Alpha's ordering is reproducible from its predictions alone
  G7  already-played   no evaluated player's team had kicked off at the cutoff
  G8  regret-exact     sum of player regret equals the week's shortfall, to 1e-9
  G9  null-calibration the copula null achieves the Spearman it was asked for
  G10 determinism      the benchmark run twice is byte-identical

**G2 is the one that matters most and is the hardest to fake.** Rather than inspecting SQL for
the word "week", it rebuilds every context variable against a database with the evaluated week's
`player_week_stats` rows physically removed, and requires the answer to be identical. A variable
that silently reads the current week's outcome cannot survive that.

Exit code is non-zero if any gate fails.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import (  # noqa: E402
    audit,
    benchmark,
    context,
    nulls,
    regret,
    snapshots,
    topboard,
)
from alpha_squad.evaluation.weekly.metrics import pairwise_accuracy, spearman  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from scripts.research.w5_topboard_forensics import (  # noqa: E402
    ALL_POSITIONS,
    CONFIRMATORY_POSITIONS,
    SEASONS,
    build_context,
    positional_cell,
)

#: G2 and G9 are expensive (a full context rebuild / a 200-draw calibration per cell), so they
#: run on a fixed, spread sample rather than all 79 weeks. The sample is chosen by position in
#: the week list, never by which weeks pass.
LEAK_SAMPLE_EVERY = 8


def _wire(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        snap = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(snap['local_path'])}"
        )
    context.wire_snapshot_views(con, SEASONS)


def _redacted_connection(db: str, season: int, week: int) -> duckdb.DuckDBPyConnection:
    """A connection whose `player_week_stats` has the evaluated week's rows REMOVED.

    Built by attaching the real database read-only and shadowing that one table with a filtered
    view; every other table, and every snapshot view, is identical. If a context variable reads
    the current week's outcome, its value moves."""
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    for table in (
        "player_week_features",
        "players",
        "games",
        "team_week_features",
        "player_id_map",
        "snapshot_registry",
        "weekly_projection_snapshot",
    ):
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM src.{table}")
    con.execute(
        "CREATE OR REPLACE VIEW player_week_stats AS SELECT * FROM src.player_week_stats "
        f"WHERE NOT (season = {season} AND week = {week})"
    )
    _wire(con)
    return con


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    weeks = audit.week_coverage(con, SEASONS).snapshots
    failures: list[str] = []

    # --- G1 causality -------------------------------------------------------------------
    leaks = 0
    for snap in weeks:
        win = context.PriorWindow(snap.season, snap.week)
        leaks += int(
            con.execute(
                f"SELECT count(*) FROM player_week_stats s WHERE {win.sql('s')} "
                "AND (s.season > ? OR (s.season = ? AND s.week >= ?))",
                [snap.season, snap.season, snap.week],
            ).fetchone()[0]
        )
    print(f"G1  causality       : prior rows at or after the ranked week: {leaks}")
    if leaks:
        failures.append("G1")

    # --- G2 no-outcome-leak --------------------------------------------------------------
    moved: list[str] = []
    checked = 0
    for snap in weeks[::LEAK_SAMPLE_EVERY]:
        full = build_context(con, snap)
        red_con = _redacted_connection(args.db, snap.season, snap.week)
        try:
            redacted = build_context(red_con, snap)
        finally:
            red_con.close()
        checked += 1
        for pid, a in full.items():
            b = redacted.get(pid)
            if b is None:
                moved.append(f"{snap.season}-{snap.week}:{pid}:MISSING")
                continue
            da, db_ = dataclasses.asdict(a), dataclasses.asdict(b)
            for field, va in da.items():
                if va != db_[field]:
                    moved.append(f"{snap.season}-{snap.week}:{pid}:{field}")
    print(
        f"G2  no-outcome-leak : context values that MOVED when the ranked week's outcomes were "
        f"deleted ({checked} weeks): {len(moved)}"
    )
    for m in moved[:5]:
        print(f"      {m}")
    if moved:
        failures.append("G2")

    # --- G3-G8 --------------------------------------------------------------------------
    universe_mismatch = wrong_position = ecr_dependence = oracle_bad = regret_bad = 0
    contaminated = 0
    cells = 0
    for snap in weeks:
        playing = snapshots.teams_already_playing(con, snap)
        already = {
            r[0]
            for r in con.execute(
                "SELECT s.player_id FROM player_week_stats s "
                "WHERE s.season=? AND s.week=? AND s.team = ANY(?)",
                [snap.season, snap.week, list(playing) or [""]],
            ).fetchall()
        }
        usage = context.load_usage_points(
            con, snap.season, snap.week, FULL_PPR.points_per_reception
        )
        for position in ALL_POSITIONS:
            common, alpha_b, preds = positional_cell(con, snap, position, FULL_PPR)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            cells += 1
            base = {r.player_id for r in common.rows}
            contaminated += len(base & already)
            wrong_position += sum(1 for r in common.rows if r.position != position)

            expect = [
                r.player_id
                for r in sorted(common.rows, key=lambda r: (-preds[r.player_id], r.player_id))
            ]
            got = [r.player_id for r in sorted(alpha_b.rows, key=lambda r: r.ecr)]
            if expect != got:
                ecr_dependence += 1

            oracle_o = topboard.oracle_outcome(common, preds)
            oracle_u, _ = topboard.oracle_usage(common, preds, usage)
            pr, rl = oracle_o.ranks_and_points()
            acc, pairs = pairwise_accuracy(pr, rl)
            if pairs and acc != 1.0:
                oracle_bad += 1
            for board in (alpha_b, oracle_o, oracle_u):
                if {r.player_id for r in board.rows} != base:
                    universe_mismatch += 1

            realized = {r.player_id: float(r.realized) for r in common.rows}
            rows = regret.player_regret(snap.season, snap.week, position, preds, realized)
            for depth in regret.REGRET_DEPTHS:
                universe = sorted(preds)
                ptop = sorted(universe, key=lambda p: (-preds[p], p))[:depth]
                rtop = sorted(universe, key=lambda p: (-realized[p], p))[:depth]
                shortfall = sum(realized[p] for p in rtop) - sum(realized[p] for p in ptop)
                if abs(sum(r.regret[depth] for r in rows) - shortfall) > 1e-9:
                    regret_bad += 1

    print(
        f"G3  universe        : boards whose player set differs from the cell's: {universe_mismatch}"
    )
    print(f"G4  position        : players on the wrong positional board: {wrong_position}")
    print(f"G5  oracle          : cells where ORACLE_OUTCOME is not perfect: {oracle_bad}")
    print(
        f"G6  no-ECR          : cells where Alpha's order needs more than its predictions: {ecr_dependence}"
    )
    print(f"G7  already-played  : evaluated players whose team had kicked off: {contaminated}")
    print(
        f"G8  regret-exact    : (cell x depth) where regret != shortfall: {regret_bad}  [{cells} cells]"
    )
    failures += [
        g
        for g, bad in (
            ("G3", universe_mismatch),
            ("G4", wrong_position),
            ("G5", oracle_bad),
            ("G6", ecr_dependence),
            ("G7", contaminated),
            ("G8", regret_bad),
        )
        if bad
    ]

    # --- G9 null calibration on real cells -------------------------------------------------
    worst = 0.0
    n_checked = 0
    for snap in weeks[::LEAK_SAMPLE_EVERY]:
        for position in CONFIRMATORY_POSITIONS:
            common, alpha_b, _preds = positional_cell(con, snap, position, FULL_PPR)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            pr, rl = alpha_b.ranks_and_points()
            rho = spearman(pr, rl)
            if rho is None or rho <= 0:
                continue
            latent = nulls.calibrate_latent(rl, rho, snap.season, snap.week, position)
            got = [
                spearman(
                    nulls.draw_null_ranking(
                        rl, rho, snap.season, snap.week, position, d, latent=latent
                    ).pred_rank,
                    rl,
                )
                for d in range(nulls.N_SIM)
            ]
            got = [g for g in got if g is not None]
            worst = max(worst, abs(sum(got) / len(got) - rho))
            n_checked += 1
    print(
        f"G9  null-calibration: worst |achieved - target| Spearman over {n_checked} cells: {worst:.2e}"
    )
    if worst > nulls.CALIB_TOL:
        failures.append("G9")

    # --- G10 determinism ---------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism     : SKIPPED")
    else:
        digests = []
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(2):
                out = Path(tmp) / f"run{i}.json"
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/research/w5_topboard_forensics.py",
                        "--db",
                        args.db,
                        "--out",
                        str(out),
                    ],
                    check=True,
                    capture_output=True,
                )
                digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        same = digests[0] == digests[1]
        print(
            f"G10 determinism     : {digests[0][:16]} vs {digests[1][:16]} -> "
            f"{'identical' if same else 'DIFFERENT'}"
        )
        if not same:
            failures.append("G10")

    print()
    if failures:
        print(f"FAILED: {', '.join(sorted(set(failures)))} -- do not interpret W5 results.")
        return 1
    print(f"all gates PASS  ({cells} positional cells, {len(weeks)} weeks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
