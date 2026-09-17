"""D109 Part 4 (corrected) -- how wrong would Y1 have to be about RBs to change an early pick?

METHOD. The analytic flip threshold computed from the score decomposition FAILED production
validation (3 OK / 6 MISMATCH): every mismatch flipped EARLIER than predicted, because lowering
the chosen player's projection also lowers his position's opportunity cost (that term is a max
over static VORP at the position, and the chosen player is usually the position's VORP leader),
so the true derivative is steeper than the 2x the value base alone implies. The analytic
numbers are therefore DISCARDED, not reported.

What is reported instead is measured end-to-end through the production path.

PRE-REGISTERED DESIGN (fixed before any ladder result was inspected):

  CELL       every RB whose preseason overall ECR rank on this season's `ro` board is <= 36 --
             the rounds 1-3 contention set. Defined by market rank alone: preseason-available,
             never derived from an outcome, and a RULE over a cell rather than a player patch.
             The cell excludes the replacement-level RB (drawn near RB46), so a cell shift
             raises both `msv` and `da_vorp` and is NOT neutralised by the replacement level --
             unlike a uniform all-RB shift, which moves replacement by the same amount and
             therefore only moves `msv`.
  LADDER     delta in {0, 10, 20, 30, 40, 55, 70, 90, 120, 160} points added to every cell member
  OUTCOME    the smallest delta at which the production recommendation at that pick state
             becomes an RB
  PARITY     delta = 0 must reproduce the recorded recommendation exactly, or the run aborts

The override is written into an ISOLATED COPY of the database and verified to reach the engine's
own loader before each run -- D81 recorded that an override passed as an argument is a silent
no-op, because `recommend_draft_pick` reloads the board itself.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import duckdb

from alpha_squad.league.context import load_league_context
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import load_market_ranks
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.run import MODEL_VERSION


def _load(path: str):
    with open(path) as f:
        return json.load(f)


def _dump(obj, path: str) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, default=str)


#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SP = SP
LADDER = [0, 10, 20, 30, 40, 55, 70, 90, 120, 160]
CELL_ECR_MAX = 36


def main() -> None:
    season = int(sys.argv[1])
    db = f"{SP}/p4_{season}.duckdb"
    shutil.copy("data/alpha_squad.duckdb", db)

    data = _load(f"{SP}/p2_picks.json")
    picks = [r for r in data["picks"] if r["season"] == season]
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type

    con = duckdb.connect(db)
    base_proj, positions = load_season_projections(con, season)
    market = load_market_ranks(con, ecr_type, season)
    all_ids = set(base_proj)

    cell = [
        pid
        for pid in all_ids
        if positions.get(pid) == "RB" and pid in market and market[pid][1] <= CELL_ECR_MAX
    ]
    print(f"{season}: RB cell (ECR<={CELL_ECR_MAX}) has {len(cell)} players; "
          f"projections {min(base_proj[p] for p in cell):.1f}-{max(base_proj[p] for p in cell):.1f}",
          flush=True)

    out = []
    for r in picks:
        avail = all_ids - set(r["drafted_before_ids"])
        flip_at = None
        ladder_positions = {}
        for delta in LADDER:
            for pid in cell:
                con.execute(
                    "UPDATE uncertainty_predictions SET point_prediction = ? "
                    "WHERE player_id = ? AND season = ? AND model_version = ?",
                    [base_proj[pid] + delta, pid, season, MODEL_VERSION],
                )
            seen, _ = load_season_projections(con, season)
            assert abs(seen[cell[0]] - (base_proj[cell[0]] + delta)) < 1e-6, "override not seen"

            rec = recommend_draft_pick(
                con, league, season, r["roster_positions_before"], avail,
                next_pick_overall=r["next_pick"], ecr_type=ecr_type, top_n=1,
                current_pick_overall=r["overall_pick"], roster_player_ids=r["roster_ids"],
            )
            pos = positions.get(rec.recommendation, "?")
            ladder_positions[delta] = pos
            if delta == 0:
                assert rec.recommendation == r["pick_player_id"], (
                    f"PARITY FAILED at {season} pick {r['overall_pick']}: "
                    f"{rec.recommendation} != {r['pick_player_id']}"
                )
            if pos == "RB" and flip_at is None:
                flip_at = delta
        # restore
        for pid in cell:
            con.execute(
                "UPDATE uncertainty_predictions SET point_prediction = ? "
                "WHERE player_id = ? AND season = ? AND model_version = ?",
                [base_proj[pid], pid, season, MODEL_VERSION],
            )
        out.append({
            "season": season, "slot": r["slot"], "overall_pick": r["overall_pick"],
            "round": r["round"], "pick_position": r["pick_position"],
            "pick_player": r["pick_player"], "flip_to_rb_at": flip_at,
            "ladder": ladder_positions,
        })
        print(f"  {season} pick {r['overall_pick']:>2} ({r['pick_position']}) "
              f"-> RB at delta {flip_at}", flush=True)

    _dump(out, f"{SP}/p4b_{season}.json")
    print(f"wrote p4b_{season}.json", flush=True)


if __name__ == "__main__":
    main()
