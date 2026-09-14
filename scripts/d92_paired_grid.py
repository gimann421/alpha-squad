"""The committed paired-draft grid runner (D92).

Why this file exists
--------------------
D88, D89 and D90 each ran a paired Y1-vs-candidate grid from a script that was **never
committed**. D92 established that every documented input to those phases reproduces byte-for-byte
in a fresh container -- the upstream board blob's sha256 matches the commit D89 read, model
training is bit-reproducible, and the simulation is deterministic across `PYTHONHASHSEED` -- and
yet their published control-arm behaviour does not come back. Inputs that match plus outputs that
do not means the transformation differed, and the transformation lived in code nobody kept.

So this is the instrument, versioned. It changes no production behaviour: it imports the shipped
harness and the shipped objective, and writes only to the path you give it.

Every run records the board vintage it measured against (`evaluation/board_vintage.py`) next to
its results, so two phases' numbers can be compared only when they are actually comparable. Pass
`--expect-vintage <combined_hash>` to turn that from a record into a precondition.

    # the D89/D90/D91/D92 board, target format, full grid
    uv run python scripts/d92_paired_grid.py --league target_league \
        --seasons 2021,2022,2023,2024,2025 --slots 1-10 --arms O0,O1 \
        --out reports/d92_target.json

Cost: Y1 (`O0`) is ~0.02 s/pick; `O1` is ~3-5 s/pick because its marginal value is a 200-draw
Monte Carlo, so a 60-draft O1 arm is roughly an hour. Both are reported by the runner.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import duckdb

from alpha_squad.evaluation.board_vintage import (
    BACKTEST_SEASONS,
    assert_vintage,
    compute_board_vintage,
)
from alpha_squad.evaluation.draft_forensics import (
    load_season_static,
    preseason_page_type,
    simulate_forensic_draft,
)
from alpha_squad.evaluation.draft_simulation import MARKET_CONSENSUS_ROSTER_AWARE
from alpha_squad.evaluation.weekly_objective import (
    bench_contribution,
    load_weekly_points,
    season_long_lineup_points,
    weekly_lineup_points,
    weekly_lineup_points_no_foresight,
)
from alpha_squad.league.context import resolve_league
from alpha_squad.market.edge import MissingMarketBoardError
from alpha_squad.market.series import resolve_market_series

#: The opponent field D89/D90 recorded and D91/D92 reproduce. Named here rather than defaulted at
#: the call site so a run cannot silently measure against a different opponent.
OPPONENT = MARKET_CONSENSUS_ROSTER_AWARE

#: How much of each pick's candidate ranking to keep. The harness records the top five plus the
#: selection and runner-up; keeping them is what lets a later phase do first-divergence analysis
#: without re-running the grid, which D89/D90 could not do.
TRACE_FIELDS = ("player_id", "position", "projection", "vorp", "marginal_starter_value", "score")


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def _cand(c: dict | None) -> dict | None:
    return None if c is None else {k: c.get(k) for k in TRACE_FIELDS}


def _trim_trace(trace: list[dict]) -> list[dict]:
    return [
        {
            "round": p["round"],
            "overall_pick": p["overall_pick"],
            "roster_before_pick": p["roster_before_pick"],
            "n_candidates": p["n_candidates"],
            "selected": _cand(p["selected"]),
            "runner_up": _cand(p["runner_up"]),
            "score_gap_to_runner_up": p["score_gap_to_runner_up"],
            "top_5": [_cand(c) for c in p["top_5_candidates"]],
        }
        for p in trace
    ]


def run(
    db: str,
    league_id: str,
    seasons: list[int],
    slots: list[int],
    arms: list[str],
    out_path: str,
    expect_vintage: str | None,
    keep_traces: bool,
) -> dict:
    con = duckdb.connect(db, read_only=True)
    league = resolve_league(league_id, con=con)
    series = resolve_market_series(league)
    ecr_type = series.ecr_type

    # Verified/recorded over the canonical backtest window rather than this run's season subset,
    # so a one-season diagnostic and a six-season replication quote the SAME vintage when they
    # read the same board. See board_vintage.assert_vintage.
    if expect_vintage:
        vintage = assert_vintage(con, expect_vintage)
        print(f"board vintage VERIFIED: {vintage.combined_hash}", flush=True)
    else:
        vintage = compute_board_vintage(con)
        print(f"board vintage recorded: {vintage.combined_hash}", flush=True)

    # D96: refuse a season the series has no preseason board for, BEFORE any draft runs.
    # This check has to live here rather than being inherited from D95's contract, because the
    # line below deliberately resolves the season's OWN page_type and passes it explicitly --
    # which is exactly the case D95 leaves alone, since naming a page is a deliberate act. For a
    # benchmark it is not: `preseason_page_type` resolves 2020 to the upstream's pre-rename
    # label, so without this the grid would happily measure a season production itself refuses,
    # against a board that is a different market series by D56's definition. That is how every
    # 2020 cell in D89-D93 came to be measured. See docs/DECISIONS.md D95/D96.
    uncovered = [s for s in seasons if not series.covers(s)]
    if uncovered:
        raise MissingMarketBoardError(
            f"seasons {uncovered} have no preseason board for series {series} "
            f"({series.label}); its first covered season is {series.first_preseason_season}. "
            "The pre-2020-10-16 rows are a different (ecr_type, page_type) pair and must not be "
            "substituted into a benchmark. Restrict --seasons to the covered window "
            f"(see BACKTEST_SEASONS = {BACKTEST_SEASONS})."
        )

    rows: list[dict] = []
    picks_timed: dict[str, list[float]] = {a: [] for a in arms}
    t0 = time.time()
    for season in seasons:
        page_type = preseason_page_type(con, ecr_type, season)
        static = load_season_static(con, league, season, page_type=page_type)
        weekly = load_weekly_points(con, season)
        season_totals = {
            r[0]: float(r[1])
            for r in con.execute(
                "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
                "WHERE season = ?",
                [season],
            ).fetchall()
        }
        for slot in slots:
            for arm in arms:
                trace: list[dict] = []
                started = time.time()
                result = simulate_forensic_draft(
                    con,
                    league,
                    season,
                    arm,
                    slot,
                    static,
                    trace=trace,
                    opponent_strategy=OPPONENT,
                )
                elapsed = time.time() - started
                picks_timed[arm].append(elapsed / max(1, len(result.drafted_player_ids)))
                roster = list(result.drafted_player_ids)
                positions = {p: static.positions.get(p, "UNKNOWN") for p in roster}
                row = {
                    "league": league_id,
                    "season": season,
                    "slot": slot,
                    "arm": arm,
                    "page_type": page_type,
                    "opponent_strategy": result.opponent_strategy,
                    "roster": roster,
                    "positions": [positions[p] for p in roster],
                    "total_roster_points": result.total_roster_points,
                    "weekly_no_foresight": weekly_lineup_points_no_foresight(
                        league, roster, positions, weekly, static.projections
                    ),
                    "weekly_hindsight": weekly_lineup_points(league, roster, positions, weekly),
                    "season_long": season_long_lineup_points(
                        league, roster, positions, season_totals
                    ),
                    "bench": bench_contribution(league, roster, positions, weekly, season_totals),
                    "seconds": round(elapsed, 3),
                }
                if keep_traces:
                    row["trace"] = _trim_trace(trace)
                rows.append(row)
            print(f"  {league_id} {season} slot {slot} ({time.time() - t0:.0f}s)", flush=True)

    payload = {
        "config": {
            "league": league_id,
            "seasons": seasons,
            "slots": slots,
            "arms": arms,
            "opponent_strategy": OPPONENT,
            "ecr_type": ecr_type,
            "keep_traces": keep_traces,
        },
        "provenance": {
            "git_head": _git_head(),
            "python": platform.python_version(),
            "argv": sys.argv,
            "board_vintage": vintage.as_dict(),
        },
        "cost_seconds_per_pick": {
            a: (round(sum(v) / len(v), 4) if v else None) for a, v in picks_timed.items()
        },
        "rows": rows,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(payload))
    print(
        f"wrote {out_path}: {len(rows)} drafts in {time.time() - t0:.0f}s; "
        f"s/pick {payload['cost_seconds_per_pick']}"
    )
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--league", default="target_league")
    # D96: the covered backtest window. 2020 is NOT in it -- no shipped series has a preseason
    # board before 2021 (D95), and the run() guard refuses it even if named explicitly.
    ap.add_argument("--seasons", default=",".join(str(s) for s in BACKTEST_SEASONS))
    ap.add_argument("--slots", default="1-10")
    ap.add_argument("--arms", default="O0,O1")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--expect-vintage",
        default=None,
        help="combined board-vintage hash this run must measure against; mismatch raises",
    )
    ap.add_argument("--no-traces", action="store_true", help="omit per-pick candidate rankings")
    a = ap.parse_args()
    lo, _, hi = a.slots.partition("-")
    run(
        a.db,
        a.league,
        [int(s) for s in a.seasons.split(",")],
        list(range(int(lo), int(hi or lo) + 1)),
        a.arms.split(","),
        a.out,
        a.expect_vintage,
        not a.no_traces,
    )


if __name__ == "__main__":
    main()
