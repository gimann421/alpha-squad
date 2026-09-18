"""D111 Part 5 -- the pre-registered primary ablation: `risk_mult = 1.0`, nothing else changed.

PRE-REGISTERED. Committed before the ablation ran.

HOW THE ABLATION IS APPLIED WITHOUT TOUCHING PRODUCTION CODE
------------------------------------------------------------
`league/draft.py` computes `risk_mult = confidence if confidence is not None else 0.7`, where
`confidence` comes from `_confidence_for`, a lookup on
`uncertainty_predictions.(player_id, season, model_version)`. So setting that column to 1.0 for
every evaluable candidate gives `risk_mult == 1.0` exactly, with no change to `league/` or
`models/`.

The catch this design has to handle: **roughly a quarter of the projection universe has no
uncertainty row at all** -- every DST (32/season), most kickers (~44/season) and ~100 rookies --
and those candidates take the hardcoded **0.7** fallback rather than a model output. Setting only
the existing rows to 1.0 would therefore not be an ablation of risk; it would be a re-weighting of
skill players against K/DST/rookies. So the ablation also INSERTS a row for every projection-universe
player that lacks one, carrying that player's exact projection and position, which leaves
`load_season_projections` returning a byte-identical board (step 1 now supplies them, steps 2 and 3
skip them) while making `_confidence_for` return 1.0 for everyone.

Two assertions guard this, and the run aborts rather than reporting if either fails:
  1. the assembled `board_hash` for every season is UNCHANGED from the control, and
  2. every player in the projection universe returns `confidence == 1.0`.

Nothing else moves: same Y1 projections, same board, same MSV, same draft-aware VORP, same
opportunity cost, same roster fit, same survival, same capacity cap, same opponent field, same
seasons. The risk formula itself is not altered in any other way.

    uv run python scripts/research/d111_ablation.py --arm risk_off --league target_league ...
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time

import duckdb

from alpha_squad.evaluation.board_vintage import board_hash, compute_board_vintage
from alpha_squad.evaluation.draft_simulation import (
    ALPHA_LEAGUE_AWARE,
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
    simulate_draft,
)
from alpha_squad.league.context import load_league_context
from alpha_squad.league.draft import _confidence_for
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.models.uncertainty.run import MODEL_VERSION

SEASONS = (2021, 2022, 2023, 2024, 2025)
FEATURE_VERSION_FALLBACK = "d111_ablation"
ARMS = ("control", "risk_off")


def apply_risk_off(con: duckdb.DuckDBPyConnection, seasons: tuple[int, ...]) -> int:
    """Make `_confidence_for` return 1.0 for every evaluable candidate. Returns rows inserted."""
    inserted = 0
    for season in seasons:
        projections, positions = load_season_projections(con, season)
        have = {
            r[0]
            for r in con.execute(
                "SELECT player_id FROM uncertainty_predictions WHERE season=? AND model_version=?",
                [season, MODEL_VERSION],
            ).fetchall()
        }
        con.execute(
            "UPDATE uncertainty_predictions SET confidence = 1.0 "
            "WHERE season=? AND model_version=?",
            [season, MODEL_VERSION],
        )
        for pid, value in projections.items():
            if pid in have:
                continue
            con.execute(
                "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
                "model_version, feature_version, point_prediction, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)",
                [
                    f"d111-{pid}-{season}",
                    pid,
                    season,
                    positions[pid],
                    MODEL_VERSION,
                    FEATURE_VERSION_FALLBACK,
                    value,
                ],
            )
            inserted += 1
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--league", default="target_league")
    ap.add_argument("--slots", default="")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    league = load_league_context(
        f"src/alpha_squad/config/league_configs/{args.league}.yaml"
    )
    slots = (
        tuple(int(s) for s in args.slots.split(","))
        if args.slots
        else tuple(range(1, league.teams + 1))
    )

    work = os.path.join(args.out, f"d111_{args.league}_{args.arm}.duckdb")
    shutil.copy(args.db, work)
    con = duckdb.connect(work)

    before = {s: board_hash(con, s) for s in SEASONS}
    vintage = compute_board_vintage(con).combined_hash

    if args.arm == "risk_off":
        n_ins = apply_risk_off(con, SEASONS)
        # GUARD 1 -- the board must be byte-identical, or this is not a pure risk ablation.
        for s in SEASONS:
            after = board_hash(con, s)
            if after != before[s]:
                raise AssertionError(
                    f"board_hash changed for {s}: {before[s][:16]} -> {after[:16]}. The ablation "
                    "moved the projections, so it is not an ablation of risk alone."
                )
        # GUARD 2 -- every evaluable candidate must now return confidence 1.0.
        for s in SEASONS:
            projections, _ = load_season_projections(con, s)
            for pid in projections:
                c = _confidence_for(con, pid, s)
                if c is None or abs(c - 1.0) > 1e-12:
                    raise AssertionError(f"{pid} in {s} has confidence {c!r}, not 1.0")
        print(f"risk_off applied: {n_ins} rows inserted; board_hash unchanged for all "
              f"{len(SEASONS)} seasons; every candidate confidence == 1.0", flush=True)
    else:
        print("control: production Y1, untouched", flush=True)

    print(f"league={args.league} arm={args.arm} slots={slots} vintage={vintage[:16]}", flush=True)

    rows = []
    for season in SEASONS:
        projections, positions = load_season_projections(con, season)
        realized = _actual_points_for(con, season, sorted(projections))
        for slot in slots:
            t0 = time.time()
            res = simulate_draft(
                con, league, season, ALPHA_LEAGUE_AWARE, slot,
                opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
            )
            picks = res.drafted_player_ids
            rows.append({
                "league": args.league, "arm": args.arm, "season": season, "slot": slot,
                "starter_points": res.starter_points,
                "total_roster_points": res.total_roster_points,
                "n_unfilled_mandatory_slots": res.n_unfilled_mandatory_slots,
                "picks": picks,
                "pick_positions": [positions.get(p, "UNKNOWN") for p in picks],
                "pick_realized": [realized.get(p, 0.0) for p in picks],
                "board_vintage": vintage,
            })
            print(f"  {season} slot {slot}: {[positions.get(p, '?') for p in picks[:3]]} "
                  f"starters {res.starter_points:.0f} ({time.time() - t0:.0f}s)", flush=True)

    with open(os.path.join(args.out, f"d111_{args.league}_{args.arm}.json"), "w") as f:
        json.dump(rows, f)
    con.close()
    os.remove(work)
    print(f"wrote d111_{args.league}_{args.arm}.json ({len(rows)} drafts)", flush=True)


if __name__ == "__main__":
    main()
