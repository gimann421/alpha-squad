"""D109 Parts 2/3/5/6 -- what the REAL production engine does at picks 1-30, and why.

Instrument: `evaluation/opening_audit.py::audit_opening`, which runs
`league/draft.py::recommend_draft_pick` itself and whose `decompose_candidate` ASSERTS that the
reassembled term-by-term score equals the production score to 1e-6. No parallel scoring
implementation exists here.

Design: 5 seasons x 10 draft slots, 3 audited rounds. Slot s picks at overall s, 21-s, 20+s,
so the 10 slots together cover every one of overall picks 1..30 exactly once per season.

Realized value reuses the benchmark's own scorer (`compute_league_starters` with teams=1 over
realized points), not a reimplementation.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys

import duckdb as _ddb

from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import audit_opening, load_board_state
from alpha_squad.league.context import load_league_context
from alpha_squad.league.replacement import compute_league_starters
from alpha_squad.market.series import resolve_market_series

#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SP = SP
SEASONS = [int(sys.argv[2])]
OUT = None


def main() -> None:
    world = sys.argv[1] if len(sys.argv) > 1 else "default"
    global OUT
    OUT = f"{SP}/p2_picks_{SEASONS[0]}.json"
    con = _ddb.connect(sys.argv[3], read_only=True)
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type

    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())

    records = []
    rosters = []
    for season in SEASONS:
        board = load_board_state(con, league, season, ecr_type)
        realized = _actual_points_for(con, season, sorted(board.projections))
        for slot in range(1, league.teams + 1):
            res = audit_opening(
                con,
                league,
                season,
                slot,
                world=world,
                audit_rounds=3,
                top_n=150,
            )

            # --- realized value of the FULL 16-round roster, benchmark scorer, unchanged ---
            drafted = res.full_roster_player_ids
            actual = {p: realized.get(p, 0.0) for p in drafted}
            pos_of = {p: board.positions.get(p, "UNKNOWN") for p in drafted}
            starters = compute_league_starters(league, actual, pos_of, teams=1)
            starter_pts = sum(actual.get(p, 0.0) for p in starters["starters"])

            rosters.append(
                {
                    "season": season,
                    "slot": slot,
                    "positions": res.full_roster_positions,
                    "opening3": res.full_roster_positions[:3],
                    "player_ids": drafted,
                    "realized_starter_points": starter_pts,
                    "first_rb_round": (
                        res.full_roster_positions.index("RB") + 1
                        if "RB" in res.full_roster_positions
                        else None
                    ),
                    "first_wr_round": (
                        res.full_roster_positions.index("WR") + 1
                        if "WR" in res.full_roster_positions
                        else None
                    ),
                    "first_qb_round": (
                        res.full_roster_positions.index("QB") + 1
                        if "QB" in res.full_roster_positions
                        else None
                    ),
                }
            )

            for ap in res.audited_picks:
                chosen = next(c for c in ap.candidates if c.player_id == ap.recommendation)
                bbp = {
                    pos: dataclasses.asdict(d) | {"name": names.get(d.player_id, d.player_id)}
                    for pos, d in ap.best_by_position.items()
                }
                # remaining pool composition, for scarcity questions
                pool_by_pos: dict[str, int] = {}
                for pid in ap.available_before:
                    p = board.positions.get(pid)
                    if p:
                        pool_by_pos[p] = pool_by_pos.get(p, 0) + 1

                records.append(
                    {
                        "season": season,
                        "slot": slot,
                        "overall_pick": ap.overall_pick,
                        "round": ap.round_no,
                        "next_pick": ap.next_pick_overall,
                        "picks_until_next_turn": ap.picks_until_next_turn,
                        "roster_positions_before": ap.roster_positions_before,
                        "roster_ids": ap.roster_before,
                        # Compact and exactly reconstructible: the available pool is every
                        # projected player MINUS these. At pick 30 that is at most 29 ids,
                        # where storing the pool itself would be ~3100 per pick.
                        "drafted_before_ids": sorted(
                            set(board.projections) - set(ap.available_before)
                        ),
                        "pick_position": ap.recommended_position,
                        "pick_player": names.get(ap.recommendation, ap.recommendation),
                        "pick_player_id": ap.recommendation,
                        "score_gap_to_runner_up": ap.score_gap_to_runner_up,
                        "chosen": dataclasses.asdict(chosen),
                        "chosen_ecr": board.market_ranks.get(ap.recommendation, (None, None))[1],
                        "chosen_realized": realized.get(ap.recommendation, 0.0),
                        "best_by_position": bbp,
                        "best_by_position_ecr": {
                            pos: board.market_ranks.get(d.player_id, (None, None))[1]
                            for pos, d in ap.best_by_position.items()
                        },
                        "best_by_position_realized": {
                            pos: realized.get(d.player_id, 0.0)
                            for pos, d in ap.best_by_position.items()
                        },
                        "pool_by_position": pool_by_pos,
                        "available_pool_size": ap.available_pool_size,
                        "top5": [
                            {
                                "name": names.get(c.player_id, c.player_id),
                                "pos": c.position,
                                "score": c.score,
                                "proj": c.projection,
                            }
                            for c in ap.candidates[:5]
                        ],
                    }
                )
            print(f"  {season} slot {slot}: {res.full_roster_positions[:3]} "
                  f"realized {starter_pts:.0f}", flush=True)

    with open(OUT, "w") as f:
        json.dump({"world": world, "picks": records, "rosters": rosters}, f, default=str)
    print(f"\nwrote {len(records)} audited picks, {len(rosters)} drafts -> {OUT}")


if __name__ == "__main__":
    main()
