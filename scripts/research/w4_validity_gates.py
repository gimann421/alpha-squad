"""W4 --- the six validity gates that must pass BEFORE any W4 result is interpreted.

`docs/weekly/W4_PREREGISTRATION.md` §10 lists them and states the rule: *"If any gate fails,
stop and fix the methodology before reading results."* This script is the committed instrument
that enforces it (D92: a finding whose runner was never committed is not a finding), so a later
phase can re-run the same checks rather than trusting a sentence in a document.

    uv run python scripts/research/w4_validity_gates.py

  G1  causality       no calibration fit sees the week it is ranking, or anything after it
  G2  already-played  no evaluated player's team had already kicked off at the cutoff
  G3  universe        every system scores the identical player set, week by week
  G4  monotonicity    no calibration changes any WITHIN-position ordering
  G5  no-ECR          Alpha's board and every calibrated board are functions of Alpha's
                      predictions (and prior outcomes) alone -- ECR enters only as a benchmark
  G6  determinism     the benchmark run twice is byte-identical

G4 is the load-bearing one. W4's entire claim is that a calibration effect is *purely*
cross-position; a transform that reordered players inside a position would confound that with a
change to the positional rankings and the phase could no longer answer its own question. It
failed on the first run (458 of 948 cells) and that failure is what surfaced the tie defect
recorded in `alpha_board`'s docstring.

Exit code is non-zero if any gate fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import (  # noqa: E402
    audit,
    benchmark,
    calibration,
    counterfactual,
    snapshots,
)
from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS  # noqa: E402
from scripts.research.w4_flex_forensics import SEASONS, _common_flex_board  # noqa: E402


def _positional_order(board, positions: dict[str, str]) -> dict[str, list[str]]:
    """Player ids per position, in the board's own rank order."""
    out: dict[str, list[str]] = {}
    for row in sorted(board.rows, key=lambda r: r.ecr):
        out.setdefault(positions[row.player_id], []).append(row.player_id)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--skip-determinism", action="store_true")
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

    weeks = audit.week_coverage(con, SEASONS).snapshots
    failures: list[str] = []

    # --- G1 causality -------------------------------------------------------------------
    # Not a re-statement of the predicate: it runs the predicate the fitter actually emits
    # against the real table and asks for the LATEST row it admits. A `<=` typo shows up here.
    leaks = 0
    for snap in weeks:
        window = calibration.FitWindow(snap.season, snap.week)
        row = con.execute(
            f"""
            SELECT count(*) FROM weekly_projection_snapshot w
            WHERE w.model_name = ? AND {window.sql("w")}
              AND (w.season > ? OR (w.season = ? AND w.week >= ?))
            """,
            [alpha_mod.WEEKLY_PROJECTION_BASE_MODEL, snap.season, snap.season, snap.week],
        ).fetchone()
        leaks += int(row[0])
    print(f"G1 causality       : fit rows at or after the evaluated week: {leaks}")
    if leaks:
        failures.append("G1")

    # --- G2 already-played --------------------------------------------------------------
    # Re-derived here from the schedule and the player's REAL week-w team, the same way
    # `board_for_week` derives it -- not read back off the board, which would only prove the
    # board agrees with itself. The board's own team column is untrustworthy for history
    # (W1.1: the FantasyPros API returns *current* teams for historical weeks).
    contaminated = 0
    evaluated_universe: dict[str, set[str]] = {}
    for snap in weeks:
        playing = snapshots.teams_already_playing(con, snap)
        already = {
            r[0]
            for r in con.execute(
                """
                SELECT s.player_id FROM player_week_stats s
                WHERE s.season = ? AND s.week = ? AND s.team = ANY(?)
                """,
                [snap.season, snap.week, list(playing) or [""]],
            ).fetchall()
        }
        common, _alpha_b, _preds = _common_flex_board(con, snap)
        universe = {r.player_id for r in common.rows}
        evaluated_universe[f"{snap.season}-{snap.week}"] = universe
        contaminated += len(universe & already)
    print(f"G2 already-played  : evaluated players whose team had kicked off: {contaminated}")
    if contaminated:
        failures.append("G2")

    # --- G3/G4/G5 ------------------------------------------------------------------------
    universe_mismatch = 0
    monotonicity_violations = 0
    manufactured_ties: dict[str, int] = {}
    realized_total, realized_tied, realized_zero = [0], [0], [0]
    cells = 0
    ecr_dependence = 0
    for snap in weeks:
        common, alpha_b, preds = _common_flex_board(con, snap)
        if len(common.rows) < benchmark.MIN_EVALUABLE:
            continue
        position_of = {r.player_id: r.position for r in common.rows}
        base = {r.player_id for r in alpha_b.rows}
        alpha_pos = _positional_order(alpha_b, position_of)

        # G5: Alpha's board must be reproducible from its predictions alone. If any ECR
        # information had leaked into the ordering this equality would break.
        expect = [
            r.player_id
            for r in sorted(common.rows, key=lambda r: (-preds[r.player_id], r.player_id))
        ]
        got = [r.player_id for r in sorted(alpha_b.rows, key=lambda r: r.ecr)]
        if expect != got:
            ecr_dependence += 1

        window = calibration.FitWindow(snap.season, snap.week)
        sample = calibration.load_prior_sample(
            con, window, FLEX_POSITIONS, alpha_mod.WEEKLY_PROJECTION_BASE_MODEL
        )
        alpha_rank = {pid: float(i) for i, pid in enumerate(expect, start=1)}

        boards = {
            name: counterfactual.build(name, common, preds)
            for name in counterfactual.COUNTERFACTUALS
        }
        by_position: dict[str, list[str]] = {}
        for pid, pos in position_of.items():
            by_position.setdefault(pos, []).append(pid)

        # Why the ORACLES need a tiebreak: how often realized values tie inside a
        # position-week. An oracle assigns realized values as scores, so every one of these is
        # an ordering the oracle would lose to `player_id` if nothing else broke the tie.
        realized_of = {r.player_id: float(r.realized) for r in common.rows}
        for pids in by_position.values():
            counts: dict[float, int] = {}
            for pid in pids:
                counts[realized_of[pid]] = counts.get(realized_of[pid], 0) + 1
            realized_total[0] += len(pids)
            realized_tied[0] += sum(n for n in counts.values() if n > 1)
            realized_zero[0] += counts.get(0.0, 0)
        for method in calibration.CALIBRATION_METHODS:
            scores = calibration.calibrated_scores(method, sample, preds, position_of)
            cal_board, _ = alpha_mod.alpha_board(common, scores, tiebreak=alpha_rank)
            boards[method] = cal_board
            # Why G4 needs a tiebreak at all: count the ties this transform MANUFACTURES --
            # same-position pairs whose predictions differ but whose calibrated values are
            # equal. Reported, not gated; the step-function methods legitimately produce them.
            for pids in by_position.values():
                for i in range(len(pids)):
                    for j in range(i + 1, len(pids)):
                        a, b = pids[i], pids[j]
                        if preds[a] != preds[b] and scores[a] == scores[b]:
                            manufactured_ties[method] = manufactured_ties.get(method, 0) + 1
            for position, order in _positional_order(cal_board, position_of).items():
                cells += 1
                if order != alpha_pos.get(position, []):
                    monotonicity_violations += 1
        boards["ECR"] = common
        for board in boards.values():
            if {r.player_id for r in board.rows} != base:
                universe_mismatch += 1

    print(f"G3 universe        : weeks x systems with a different player set: {universe_mismatch}")
    print(
        f"G4 monotonicity    : within-position reorderings across {cells} cells: {monotonicity_violations}"
    )
    print(
        f"G5 no-ECR          : weeks where Alpha's order is not a function of its predictions: {ecr_dependence}"
    )
    n_eval = len(evaluated_universe) or 1
    ties = "  ".join(
        f"{m}={manufactured_ties.get(m, 0) / n_eval:.1f}" for m in calibration.CALIBRATION_METHODS
    )
    print(f"   manufactured within-position ties per week (not gated): {ties}")
    rt = realized_total[0] or 1
    print(
        f"   realized values tied inside a position-week (not gated): "
        f"{realized_tied[0]:,} of {rt:,} ({realized_tied[0] / rt:.1%}); "
        f"{realized_zero[0]:,} exactly 0.0"
    )
    failures += [
        g
        for g, bad in (
            ("G3", universe_mismatch),
            ("G4", monotonicity_violations),
            ("G5", ecr_dependence),
        )
        if bad
    ]

    # --- G6 determinism -------------------------------------------------------------------
    if args.skip_determinism:
        print("G6 determinism     : SKIPPED")
    else:
        digests = []
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(2):
                out = Path(tmp) / f"run{i}.json"
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/research/w4_flex_forensics.py",
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
            f"G6 determinism     : {digests[0][:16]} vs {digests[1][:16]} -> {'identical' if same else 'DIFFERENT'}"
        )
        if not same:
            failures.append("G6")

    print()
    if failures:
        print(f"FAILED: {', '.join(sorted(set(failures)))} -- do not interpret W4 results.")
        return 1
    print("all six gates PASS")
    print(json.dumps({"weeks": len(weeks), "monotonicity_cells": cells}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
