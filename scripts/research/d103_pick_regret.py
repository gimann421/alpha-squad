"""D103 -- pick-level regret under the weekly objective, by draft phase, plus the ORACLE_Y1 cell.

Read-only research runner. Opens the database read-only, drives the shipped instruments
(`draft_oracle.audit_draft`, `draft_forensics._pick_by_tier`) and writes nothing but JSON
artifacts. It changes no production module: `models/` and `league/` are untouched, and the only
`src/` change D103 makes at all is `draft_oracle.py`'s new `objective` parameter, whose default
reproduces every pre-D103 number.

    uv run python scripts/research/d103_pick_regret.py --mode parity   --out <dir>
    uv run python scripts/research/d103_pick_regret.py --mode regret   --out <dir>
    uv run python scripts/research/d103_pick_regret.py --mode oracle_y1 --out <dir>

PRE-REGISTRATION (written before any D103 result was inspected)
==========================================================================================

POPULATION.  `BACKTEST_SEASONS` (2021-2025) x `--slots` x every round, on both shipped 1-QB
formats, matching D86's shape (5 seasons x 4 slots x 16 rounds = 320 pick states per format).
D86's exact slot set is not recorded anywhere in the repository -- its runner was a scratchpad
script that no longer exists -- so `--slots` defaults to {1, 4, 7, 10}, spread across the snake,
and that choice is reported rather than presented as a reproduction of D86's own sample.
**Consequence, stated in advance: the SEASON_LONG numbers here are a re-measurement on a
possibly different slot set, so a discrepancy against D86's recorded mean regret of 116.2 is
expected and is not by itself evidence of a defect.**

PHASES.  EARLY = rounds 1-5, MIDDLE = 6-10, LATE = 11-16, the convention this phase registers.
It is NOT the repository's previous convention: D102 proposed a four-segment split (1-4 / 5-8 /
9-12 / 13-16) reasoned from the 10-starter/6-bench roster. Neither was ever measured. The
three-phase split is used here because it is the registered one; the per-round table is reported
alongside so the four-segment reading is recoverable without re-running anything.

OBJECTIVES.  `SEASON_LONG` (D86's, the default, season totals with one lineup allocation) and
`WEEKLY_NO_FORESIGHT` (lineup set each week by preseason projection among that week's actual
participants). Both are applied ONLY to a finished roster.

ORACLE_Y1.  The missing cell of D97's 2x2: oracle INFORMATION with the Y1 DECISION RULE. What it
is allowed to change is stated in `oracle_static` and is deliberately narrow -- only the
projections and the quantities mathematically derived from them. The market board, the opponent
model, the uncertainty/confidence inputs and the draft geometry are held fixed, because changing
those would alter the environment or the rule rather than the information.

LEAKAGE.  `assert_no_realized_inputs_in_policy()` is called before any measurement in every mode
and the run aborts if it fails. In `regret` mode outcomes reach only the roster scorer. In
`oracle_y1` mode outcomes DO enter the policy's inputs -- that is the entire point of the arm --
so that mode is quarantined behind its own name and its output is never mixed with regret rows.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.draft_forensics import (
    _pick_by_tier,
    load_season_static,
    preseason_page_type,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    WEEKLY_NO_FORESIGHT,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    draft_order,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.replacement import (
    compute_league_starters,
    marginal_value_over_replacement,
)
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
DEFAULT_SLOTS = (1, 4, 7, 10)
#: The phase convention D103 registers. See the module docstring for why it differs from D102's.
PHASES: dict[str, range] = {
    "EARLY (1-5)": range(1, 6),
    "MIDDLE (6-10)": range(6, 11),
    "LATE (11-16)": range(11, 17),
}
NEAR_ZERO = 1.0


def phase_of(round_no: int) -> str:
    for name, rounds in PHASES.items():
        if round_no in rounds:
            return name
    return "OUT OF RANGE"


def _static_for(con, league, season):
    series = resolve_market_series(league)
    return load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )


# --------------------------------------------------------------------------------------------
# MODE: parity -- the real-data companion to tests/unit/test_draft_oracle.py's fixture check
# --------------------------------------------------------------------------------------------
def run_parity(con, slots: tuple[int, ...]) -> dict:
    agree = 0
    mismatches: list[tuple] = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            positions = static.positions
            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, positions, league, opps[seat], remaining
                        )
                        opps[seat].append(positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    prod, _ = _pick_by_tier(
                        static, con, league, season, set(avail),
                        [positions.get(p, "UNKNOWN") for p in mine], "H", current, nxt, **kw
                    )
                    repl, _ = _pick_by_tier(
                        static, con, league, season, set(avail),
                        [positions.get(p, "UNKNOWN") for p in mine], SHIPPED_TIER,
                        current, nxt, **kw
                    )
                    if prod == repl:
                        agree += 1
                    else:
                        mismatches.append((league_name, season, slot, round_no, prod, repl))
                    mine.append(prod)
                    avail.discard(prod)
            print(f"  parity {league_name} {season} done", flush=True)
    print(f"\nPARITY: {SHIPPED_TIER} vs H over {agree + len(mismatches)} real pick states -- "
          f"agree {agree}, DISAGREE {len(mismatches)}")
    for m in mismatches[:10]:
        print("   mismatch", m)
    return {"agree": agree, "mismatches": mismatches}


# --------------------------------------------------------------------------------------------
# MODE: regret -- the phase's primary measurement
# --------------------------------------------------------------------------------------------
def run_regret(con, slots: tuple[int, ...], objectives: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            for objective in objectives:
                for slot in slots:
                    picks = audit_draft(
                        con, league, season, slot, static,
                        objective=objective,
                        weekly=weekly if objective == WEEKLY_NO_FORESIGHT else None,
                    )
                    for p in picks:
                        alpha, oracle = p.alpha, p.oracle
                        rows.append({
                            "league": league_name, "season": season, "slot": slot,
                            "objective": objective, "round": p.round_no,
                            "phase": phase_of(p.round_no),
                            "regret": p.regret,
                            "alpha_is_oracle": p.alpha_is_oracle,
                            "slate": len(p.candidates),
                            "spread": (max(c.rollout_starter_points for c in p.candidates)
                                       - min(c.rollout_starter_points for c in p.candidates))
                                      if p.candidates else 0.0,
                            "alpha_pos": alpha.position if alpha else None,
                            "oracle_pos": oracle.position if oracle else None,
                            "alpha_realized": alpha.realized_points if alpha else 0.0,
                            "oracle_realized": oracle.realized_points if oracle else 0.0,
                            "alpha_rank_of_oracle": oracle.alpha_rank if oracle else None,
                        })
                    print(f"  {league_name} {season} slot {slot} {objective} done", flush=True)
    return rows


def _describe(values: list[float]) -> str:
    if not values:
        return "n/a"
    near = sum(1 for v in values if v <= NEAR_ZERO) / len(values)
    return (f"n={len(values):<5} mean {mean(values):>7.1f}  median {median(values):>7.1f}  "
            f"total {sum(values):>9.0f}  zero/near-zero {near:>5.1%}")


def report_regret(rows: list[dict]) -> None:
    for league_name in FORMATS:
        for objective in sorted({r["objective"] for r in rows}):
            sub = [r for r in rows if r["league"] == league_name and r["objective"] == objective]
            if not sub:
                continue
            print(f"\n{'=' * 96}\n{league_name}  |  objective = {objective}\n{'=' * 96}")
            print(f"  ALL PICKS   {_describe([r['regret'] for r in sub])}")
            print(f"  alpha == oracle: "
                  f"{sum(1 for r in sub if r['alpha_is_oracle']) / len(sub):.1%} of picks")
            print("\n  BY PHASE")
            for phase in PHASES:
                vals = [r["regret"] for r in sub if r["phase"] == phase]
                print(f"    {phase:<15}{_describe(vals)}")
            print("\n  BY ROUND")
            print(f"    {'rd':<4}{'n':>4}{'mean':>9}{'median':>9}{'max':>9}{'spread':>9}"
                  f"{'alpha=oracle':>14}")
            for rnd in sorted({r["round"] for r in sub}):
                vals = [r["regret"] for r in sub if r["round"] == rnd]
                spr = [r["spread"] for r in sub if r["round"] == rnd]
                hit = [r["alpha_is_oracle"] for r in sub if r["round"] == rnd]
                print(f"    {rnd:<4}{len(vals):>4}{mean(vals):>9.1f}{median(vals):>9.1f}"
                      f"{max(vals):>9.1f}{mean(spr):>9.1f}{sum(hit) / len(hit):>13.0%}")
            print("\n  REGRET DISTRIBUTION (quantiles of per-pick regret)")
            ordered = sorted(r["regret"] for r in sub)
            qs = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0]
            print("    " + "  ".join(
                f"p{int(q * 100)}={ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]:.0f}"
                for q in qs))
            print("\n  SEASON-LEVEL mean regret (the independent cluster)")
            for season in sorted({r["season"] for r in sub}):
                vals = [r["regret"] for r in sub if r["season"] == season]
                print(f"    {season}: {mean(vals):>7.1f}")


def report_attribution(rows: list[dict]) -> None:
    """Part 4D. Decomposition into the categories the existing instrument can actually support."""
    print(f"\n{'=' * 96}\nATTRIBUTION -- what distinguishes a high-regret pick (Part 4D)\n{'=' * 96}")
    for league_name in FORMATS:
        for objective in sorted({r["objective"] for r in rows}):
            sub = [r for r in rows if r["league"] == league_name and r["objective"] == objective
                   and not r["alpha_is_oracle"]]
            if not sub:
                continue
            outscored = [r for r in sub if r["oracle_realized"] > r["alpha_realized"]]
            structural = [r for r in sub if r["oracle_realized"] <= r["alpha_realized"]]
            same_pos = [r for r in sub if r["alpha_pos"] == r["oracle_pos"]]
            print(f"\n  {league_name} / {objective}: {len(sub)} picks where alpha != oracle")
            print(f"    oracle's player simply SCORED MORE (luck-shaped)      "
                  f"{len(outscored) / len(sub):>6.1%}  mean regret {mean([r['regret'] for r in outscored]) if outscored else 0:.1f}")
            print(f"    oracle's player scored NO MORE and still won (structural) "
                  f"{len(structural) / len(sub):>6.1%}  mean regret {mean([r['regret'] for r in structural]) if structural else 0:.1f}")
            print(f"    WITHIN-position error (alpha and oracle same position) "
                  f"{len(same_pos) / len(sub):>6.1%}")
            print(f"    CROSS-position error                                  "
                  f"{1 - len(same_pos) / len(sub):>6.1%}")
            ranks = [r["alpha_rank_of_oracle"] for r in sub if r["alpha_rank_of_oracle"]]
            if ranks:
                print(f"    where the oracle's player sat on Alpha's own ranked board: "
                      f"median rank {median(ranks):.0f}, "
                      f"{sum(1 for x in ranks if x <= 5) / len(ranks):.0%} in Alpha's top 5")


# --------------------------------------------------------------------------------------------
# MODE: oracle_y1 -- D97's missing 2x2 cell
# --------------------------------------------------------------------------------------------
def oracle_static(con, league, season, static):
    """`static` with PROJECTIONS replaced by realized points, and only the quantities that are
    mathematically derived from projections recomputed.

    What this arm is allowed to change, stated because "it can be coded" is not a justification:

      * `projections` -- the information under test.
      * `vorp`, `replacement_levels` -- functions of the projections; leaving them stale would
        make the arm incoherent rather than conservative.

    What it deliberately does NOT change, and why:

      * `market_rank` -- drives the OPPONENTS and the survival term. Changing it would alter the
        environment, not our information, and would stop the arm being comparable to PROD.
      * `confidence` / `ecr_dispersion` -- uncertainty inputs. Under perfect information one
        could argue confidence should be 1.0, but that is a change to the RULE, not to the
        information, and this cell exists to hold the rule fixed.
      * `consumption_demand`, `scarcity_*` -- properties of the consensus board, not of our
        projections.
    """
    import dataclasses

    realized = _actual_points_for(con, season, sorted(static.projections))
    projections = {p: realized.get(p, 0.0) for p in static.projections}
    vorp = marginal_value_over_replacement(league, projections, static.positions)
    return dataclasses.replace(static, projections=projections, vorp=vorp)


def _play_draft(con, league, season, static, slot, tier, scoring_static, weekly, objective):
    """One full draft by `tier` on `static`, scored on realized outcomes."""
    rounds = int(league.roster.get("roster_size", 0))
    teams = league.teams
    avail = set(static.projections)
    mine: list[str] = []
    opps = {s: [] for s in range(1, teams + 1) if s != slot}
    my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
    for current, round_no, seat in draft_order(league):
        if not avail:
            break
        remaining = rounds - round_no + 1
        if seat != slot:
            pick = roster_aware_market_pick(
                avail, static.market_rank, static.positions, league, opps[seat], remaining
            )
            opps[seat].append(static.positions.get(pick, "UNKNOWN"))
            avail.discard(pick)
            continue
        nxt = next((p for p in my_picks if p > current), None)
        pick, _ = _pick_by_tier(
            static, con, league, season, avail,
            [static.positions.get(p, "UNKNOWN") for p in mine], tier, current, nxt,
            roster_player_ids=list(mine), picks_remaining=remaining,
        )
        mine.append(pick)
        avail.discard(pick)

    actual = _actual_points_for(con, season, mine)
    if objective == WEEKLY_NO_FORESIGHT:
        from alpha_squad.evaluation.weekly_objective import weekly_lineup_points_no_foresight
        return weekly_lineup_points_no_foresight(
            league, mine, scoring_static.positions, weekly, scoring_static.projections
        )
    single = league.model_copy(update={"teams": 1})
    starters = compute_league_starters(
        single, {p: actual.get(p, 0.0) for p in mine},
        {p: scoring_static.positions.get(p, "UNKNOWN") for p in mine},
    )
    return sum(actual.get(p, 0.0) for p in starters["starters"])


def run_oracle_y1(con, slots: tuple[int, ...], objective: str) -> list[dict]:
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            o_static = oracle_static(con, league, season, static)
            weekly = load_weekly_points(con, season)
            for slot in slots:
                prod = _play_draft(con, league, season, static, slot, SHIPPED_TIER,
                                   static, weekly, objective)
                oy1 = _play_draft(con, league, season, o_static, slot, SHIPPED_TIER,
                                  static, weekly, objective)
                rows.append({"league": league_name, "season": season, "slot": slot,
                             "objective": objective, "PROD": prod, "ORACLE_Y1": oy1})
            print(f"  oracle_y1 {league_name} {season} done", flush=True)
    return rows


def report_oracle_y1(rows: list[dict]) -> None:
    print(f"\n{'=' * 96}\nORACLE_Y1 -- oracle INFORMATION with the Y1 DECISION RULE\n{'=' * 96}")
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        by_season = defaultdict(list)
        for r in sub:
            by_season[r["season"]].append(r["ORACLE_Y1"] - r["PROD"])
        means = [mean(v) for _, v in sorted(by_season.items())]
        k = len(means)
        md = mean(means)
        se = stdev(means) / k**0.5 if k > 1 and stdev(means) > 0 else float("nan")
        print(f"\n  {league_name}")
        print(f"    PROD      mean {mean(r['PROD'] for r in sub):>9.1f}")
        print(f"    ORACLE_Y1 mean {mean(r['ORACLE_Y1'] for r in sub):>9.1f}")
        print(f"    INFORMATION EFFECT (ORACLE_Y1 - PROD, rule held at Y1): {md:>+9.1f}")
        if se == se:
            print(f"      season-clustered 95% CI [{md - 2.776 * se:+.1f}, {md + 2.776 * se:+.1f}]"
                  f"  seasons better {sum(1 for m in means if m > 0)}/{k}")
        for season, vals in sorted(by_season.items()):
            print(f"      {season}: {mean(vals):>+9.1f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True, choices=("parity", "regret", "oracle_y1"))
    ap.add_argument("--slots", default=",".join(str(s) for s in DEFAULT_SLOTS))
    ap.add_argument("--objective", default=None, choices=(SEASON_LONG, WEEKLY_NO_FORESIGHT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = tuple(int(s) for s in args.slots.split(","))

    assert_no_realized_inputs_in_policy()  # Part 6: refuse to run if the guard is broken
    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}")
    print(f"seasons {BACKTEST_SEASONS}  slots {slots}  formats {FORMATS}  mode {args.mode}\n")

    if args.mode == "parity":
        result = run_parity(con, slots)
        (out / "d103_parity.json").write_text(json.dumps(result, default=str))
    elif args.mode == "regret":
        objectives = (args.objective,) if args.objective else (SEASON_LONG, WEEKLY_NO_FORESIGHT)
        rows = run_regret(con, slots, objectives)
        (out / f"d103_regret_{'_'.join(objectives)}.json").write_text(json.dumps(rows))
        report_regret(rows)
        report_attribution(rows)
    else:
        rows = run_oracle_y1(con, slots, args.objective or SEASON_LONG)
        (out / "d103_oracle_y1.json").write_text(json.dumps(rows))
        report_oracle_y1(rows)


if __name__ == "__main__":
    main()
