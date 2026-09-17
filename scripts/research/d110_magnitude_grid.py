"""D110 -- cross-position projection-MAGNITUDE sensitivity.

PRE-REGISTERED. This file is committed BEFORE any arm is run. The arm grid below, the primary
metric, and the exclusions are fixed at commit time; nothing here may be re-selected after
looking at a result. (D92's lesson: D88/D89/D90's runner was never committed, and that -- not
the board -- is why their numbers did not reproduce.)

THE QUESTION
------------
Not "can we build a better projection model", but: **is cross-position projection magnitude a
causal lever in Alpha's early-round decisions, and is the effect large enough to matter in
realized draft value?** This is a sensitivity experiment, not a calibration.

THE TRANSFORMATION
------------------
    adjusted_projection = position_multiplier x Y1_projection

A strictly positive multiplier is monotone, so **within-position order is preserved exactly**;
only the magnitude of one position relative to the others moves. Applied to BOTH
`uncertainty_predictions.point_prediction` (established players) and
`rookie_predictions.predicted_rookie_points` (rookies are 143 of 714 RBs in this window, so
scaling only the former would silently leave a quarter of the position unscaled).

What the multiplier therefore moves: projections -> marginal starter value, draft-aware VORP,
the replacement level itself, static VORP, and positional opportunity cost. What it deliberately
does NOT move: `uncertainty_predictions.confidence` (the engine's `risk` multiplier) and
`market_snapshot` (survival probability, opponent ECR order). Risk is held FROZEN so that it
remains a control rather than a confound -- D109 flagged it as a suspect, and this phase is not
its test.

Because opponents draft by ECR, which no arm touches, every arm faces an identical opponent
field on an identical board: the trials are paired by (season, slot).

THE GRID (fixed before any result was seen)
-------------------------------------------
Centred on Y1 = 1.00 and deliberately COARSE; D109's implied RB correction is about x1.21
(a -41.5 point bias on a mean projection of 197.1 inside ECR<=30), so the grid brackets that
generously in BOTH directions. No direction is assumed correct.

  VALUE-SCORED arms (full population: 5 seasons x 10 slots = 50 drafts each)
    control      all positions 1.00                      -- frozen Y1
    rb_080       RB 0.80      rb_090  RB 0.90            -- RB magnitude DOWN
    rb_110       RB 1.10      rb_120  RB 1.20            -- RB magnitude UP
    rb_140       RB 1.40                                 -- RB far beyond any measured bias
    qb_090       QB 0.90      qb_110  QB 1.10            -- move QB instead of RB
    wr_090       WR 0.90                                 -- move WR instead of RB
    gap_rb120_wr090  RB 1.20 + WR 0.90                   -- the D109-implied GAP correction

  DECISION-SURFACE-ONLY arms (4 slots x 5 seasons = 20 drafts each; NOT value-scored, and
  reported only as threshold resolution for Part 2, never as a value comparison)
    rb_095, rb_105, rb_115, rb_130

EXCLUSION, stated in advance: TE is not given an arm. D109's TE bias (-17.0) rests on n=8
inside ECR<=30 and TE is taken in only 10 of 150 early picks, so a TE arm would buy threshold
resolution on a cell too small to interpret. This is a scope decision, not a finding.

PRIMARY METRIC: absolute realized starter points of the full 16-round roster, per
(season, slot), differenced against the control on the SAME (season, slot). Arm-relative pick
regret is deliberately NOT primary -- D105/D106 established it becomes non-monotone when the arm
changes the oracle comparison.

INSTRUMENT: `evaluation/draft_simulation.py::simulate_draft` with `ALPHA_LEAGUE_AWARE` (which
calls `league/draft.py::recommend_draft_pick` itself) against the fair roster-aware consensus
opponent field (D61 Stage 1.1). No parallel scoring implementation exists here.

DATA VINTAGE: the D109 rebuild, assembled-board `combined_hash` d2955868... The upstream
DynastyProcess board and id map reproduce D89 byte-identically; the nflverse panel underneath
was restated upstream, so numbers here must NOT be compared against pre-D109 published figures.
The runner prints and records the vintage on every run.

    uv run python scripts/research/d110_magnitude_grid.py --arm rb_120 --db <copy> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time

import duckdb

from alpha_squad.evaluation.board_vintage import compute_board_vintage
from alpha_squad.evaluation.draft_simulation import (
    ALPHA_LEAGUE_AWARE,
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
    simulate_draft,
)
from alpha_squad.league.context import load_league_context
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.models.uncertainty.run import MODEL_VERSION

SEASONS = (2021, 2022, 2023, 2024, 2025)
FULL_SLOTS = tuple(range(1, 11))
#: The repository's own default slot subset (D103), used for the decision-surface-only arms.
COARSE_SLOTS = (1, 4, 7, 10)

#: {arm: {position: multiplier}}. FROZEN AT COMMIT TIME.
ARMS: dict[str, dict[str, float]] = {
    "control": {},
    "rb_080": {"RB": 0.80},
    "rb_090": {"RB": 0.90},
    "rb_110": {"RB": 1.10},
    "rb_120": {"RB": 1.20},
    "rb_140": {"RB": 1.40},
    "qb_090": {"QB": 0.90},
    "qb_110": {"QB": 1.10},
    "wr_090": {"WR": 0.90},
    "gap_rb120_wr090": {"RB": 1.20, "WR": 0.90},
    # decision-surface only
    "rb_095": {"RB": 0.95},
    "rb_105": {"RB": 1.05},
    "rb_115": {"RB": 1.15},
    "rb_130": {"RB": 1.30},
}

VALUE_SCORED = (
    "control", "rb_080", "rb_090", "rb_110", "rb_120", "rb_140",
    "qb_090", "qb_110", "wr_090", "gap_rb120_wr090",
)
DECISION_ONLY = ("rb_095", "rb_105", "rb_115", "rb_130")


def apply_arm(con: duckdb.DuckDBPyConnection, multipliers: dict[str, float]) -> None:
    """Scale every projection at each named position, in place, in an ISOLATED database copy.

    Both projection tables the engine's own loader reads are scaled. `confidence` is never
    touched, so the engine's `risk` multiplier is identical across arms."""
    for position, m in multipliers.items():
        con.execute(
            "UPDATE uncertainty_predictions SET point_prediction = point_prediction * ? "
            "WHERE position = ? AND season BETWEEN ? AND ? AND model_version = ?",
            [m, position, SEASONS[0], SEASONS[-1], MODEL_VERSION],
        )
        con.execute(
            "UPDATE rookie_predictions SET predicted_rookie_points = predicted_rookie_points * ? "
            "WHERE position = ? AND draft_class BETWEEN ? AND ?",
            [m, position, SEASONS[0], SEASONS[-1]],
        )


def verify_arm(
    con: duckdb.DuckDBPyConnection, baseline: dict[int, dict[str, float]],
    positions_by_season: dict[int, dict[str, str]], multipliers: dict[str, float],
) -> None:
    """Assert the override reached the engine's OWN loader at the expected ratio, for every
    position and every season. D81 recorded that an override passed as an argument is a silent
    no-op because `recommend_draft_pick` reloads the board itself."""
    for season in SEASONS:
        proj, _ = load_season_projections(con, season)
        pos = positions_by_season[season]
        for pid, before in baseline[season].items():
            want = before * multipliers.get(pos.get(pid, ""), 1.0)
            if abs(proj[pid] - want) > 1e-6 * max(1.0, abs(want)):
                raise AssertionError(
                    f"arm did not reach the loader for {pid} ({pos.get(pid)}) in {season}: "
                    f"{proj[pid]!r} != {want!r}"
                )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--db", required=True, help="source database; a private copy is made")
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default="", help="override; defaults by arm family")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    slots = (
        tuple(int(s) for s in args.slots.split(","))
        if args.slots
        else (COARSE_SLOTS if args.arm in DECISION_ONLY else FULL_SLOTS)
    )
    multipliers = ARMS[args.arm]

    work_db = os.path.join(args.out, f"d110_{args.arm}.duckdb")
    shutil.copy(args.db, work_db)
    con = duckdb.connect(work_db)
    league = load_league_context()

    vintage = compute_board_vintage(con).combined_hash
    baseline, positions_by_season = {}, {}
    for season in SEASONS:
        proj, pos = load_season_projections(con, season)
        baseline[season] = dict(proj)
        positions_by_season[season] = dict(pos)

    apply_arm(con, multipliers)
    verify_arm(con, baseline, positions_by_season, multipliers)
    print(f"arm={args.arm} multipliers={multipliers} slots={slots}", flush=True)
    print(f"control board vintage {vintage}", flush=True)

    rows = []
    for season in SEASONS:
        realized = _actual_points_for(con, season, sorted(baseline[season]))
        _, pos = load_season_projections(con, season)
        for slot in slots:
            t0 = time.time()
            res = simulate_draft(
                con, league, season, ALPHA_LEAGUE_AWARE, slot,
                opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
            )
            picks = res.drafted_player_ids
            rows.append({
                "arm": args.arm,
                "multipliers": multipliers,
                "season": season,
                "slot": slot,
                "starter_points": res.starter_points,
                "total_roster_points": res.total_roster_points,
                "n_unfilled_mandatory_slots": res.n_unfilled_mandatory_slots,
                "picks": picks,
                "pick_positions": [pos.get(p, "UNKNOWN") for p in picks],
                "pick_realized": [realized.get(p, 0.0) for p in picks],
                "board_vintage": vintage,
            })
            print(
                f"  {season} slot {slot}: {[pos.get(p, '?') for p in picks[:3]]} "
                f"starters {res.starter_points:.0f}  ({time.time() - t0:.0f}s)",
                flush=True,
            )

    with open(os.path.join(args.out, f"d110_{args.arm}.json"), "w") as f:
        json.dump(rows, f)
    os.remove(work_db)
    print(f"wrote d110_{args.arm}.json ({len(rows)} drafts)", flush=True)


if __name__ == "__main__":
    main()
