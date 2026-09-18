"""D112 -- does Alpha actually have an EARLY ROSTER-FEASIBILITY problem?

Read-only diagnostic runner. Opens the database read-only, drives the shipped instruments
(`draft_forensics._pick_by_tier`, the real `league/roster.py` legality primitives) and writes
nothing but JSON artifacts. No `src/` change in D112 at all: `models/`, `league/` and `evaluation/`
are byte-identical to HEAD.

    uv run python scripts/research/d112_feasibility_audit.py --mode parity --out <dir>
    uv run python scripts/research/d112_feasibility_audit.py --mode audit  --out <dir>

==========================================================================================
THE PREMISE BEING CHALLENGED
==========================================================================================

D111 measured that giving a pure-ECR drafter the end-of-draft mandatory-slot rule is worth
**+241.1 (target) / +215.3 (dynasty)** realized points, 5/5 seasons, t ~ 14-15 -- the only effect
in that phase above the 172-250 detection floor -- and recommended testing whether enforcing
feasibility EARLIER carries the same effect.

**That recommendation assumes Alpha has the problem the benchmark had. This phase tests the
assumption before spending a counterfactual on it, and is prepared to conclude that it does not.**

WHAT THE EXISTING MECHANISMS ARE, stated before anything is measured
--------------------------------------------------------------------
Alpha's roster machinery has two distinct parts, and conflating them is the trap this phase exists
to avoid:

  * **A MINIMUM (legality).** `league/roster.py::unfilled_dedicated_slots` reports which mandatory
    dedicated starting slots a roster has not yet filled. `roster_aware_market_pick` and the
    `TIERS_ENFORCING_LEGALITY` tiers (D85's L1/L3, D67's W2/W3) restrict the pick to those
    positions once `picks_remaining <= total_deficit`. **Production tier `L0` does NOT carry this
    restriction.**
  * **A MAXIMUM (capacity).** `positional_feasibility_cap` (= `positional_capacity`, derived from
    the league's own lineup and bench) multiplies a candidate's score by
    `OVER_CAP_VALUE_MULTIPLIER = 0.1` once the roster already holds that many. **This is in `L0`,
    i.e. in production.** In both shipped formats the caps are QB 2, RB 6, WR 6, TE 4, K 2, DST 2.

THE FEASIBILITY SLACK -- the quantity the whole audit turns on
---------------------------------------------------------------
At each of Alpha's own picks define

    slack = picks_remaining - sum(unfilled_dedicated_slots(league, roster).values())

counting the current pick. Both shipped formats have **8** mandatory dedicated slots
(QB 1, RB 2, WR 2, TE 1, K 1, DST 1) and **16** rounds, so slack starts at **8**. It falls by
exactly 1 for each pick that does NOT fill a mandatory slot and is unchanged by one that does.

`slack == 0` is precisely the condition under which the existing legality rule activates, and
`slack < 0` is an already-infeasible roster. So:

    min(slack) over a draft  >  0   ==>  the legality constraint NEVER binds in that draft, and
                                        no earlier enforcement of it could have changed any pick.

This is a deterministic identity, not an estimate, and it is why the audit can be conclusive on a
finite sample rather than merely suggestive.

Feasibility can also fail a second way -- the pool running out of a needed position -- so the audit
separately records, at every pick, the number of available players at each still-unfilled dedicated
position.

THE PART 2 CLASSIFICATION, fixed before the run
------------------------------------------------
Every pick is assigned exactly one of:

  **A** -- no roster constraint exists: `total_deficit == 0`, every mandatory slot already filled.
  **B** -- a constraint exists but is not binding (`deficit > 0` and `slack > 0`), so Alpha's
           choice is unrestricted. Reported alongside: whether Alpha's unrestricted pick happens to
           fill a deficit slot anyway.
  **C** -- the rule IS binding (`slack <= 0`) **and changes the pick**: the restricted argmax
           differs from the unrestricted argmax. **This is the category that matters.**
  **D** -- the rule IS binding but does **not** change the pick; it only insures against an
           eventual illegal roster.

Both argmaxes are computed from the same `_pick_by_tier` scored slate, so C/D are measured, not
inferred.

CAPACITY, MEASURED EXACTLY RATHER THAN INFERRED
------------------------------------------------
`CandidateScore.feasibility_multiplier` records when the over-cap penalty fired, and the penalty is
a pure multiplication by 0.1, so the un-penalised score is recoverable exactly as
`score / OVER_CAP_VALUE_MULTIPLIER`. The audit therefore reports, per round, how often the cap
fires and how often removing it would change Alpha's pick -- an exact counterfactual on the
mechanism that is already in production.

STOPPING RULE, fixed in advance
--------------------------------
**If the audit shows the legality constraint does not materially bind on Alpha -- concretely, if
category C is ~0% of picks in rounds 1-6 and min(slack) stays above 0 in essentially every draft --
the phase STOPS and reports that the D111 recommendation does not transfer. No counterfactual is
run.** A clean diagnostic that a recommendation does not apply is the deliverable; manufacturing a
treatment arm to have something to report is not.

If a counterfactual IS warranted it will be pre-registered separately, before any result is seen,
and will differ from the control ONLY in when the already-existing legality constraint becomes
binding -- never by adding a positional-balance heuristic. A legal roster is not the same thing as
a good roster, and this phase does not treat "more balanced" as success.

POPULATION AND PARITY
----------------------
2021-2025 x **all 10 draft slots** x both shipped 1-QB formats = 100 drafts per format. The audit is
a census rather than a paired experiment, so every slot is walked rather than D111's {1, 4, 7, 10}.
The `parity` mode re-measures Y1 on exactly D111's {1, 4, 7, 10} grid and must reproduce its
recorded control means (target 2002.9, dynasty 2061.5) before any audit number is read.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.draft_forensics import (
    _pick_by_tier,
    load_season_static,
    preseason_page_type,
)
from alpha_squad.evaluation.draft_oracle import (
    SHIPPED_TIER,
    assert_no_realized_inputs_in_policy,
    draft_order,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.replacement import compute_league_starters
from alpha_squad.league.roster import OVER_CAP_VALUE_MULTIPLIER, unfilled_dedicated_slots
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
ALL_SLOTS = tuple(range(1, 11))
D111_SLOTS = (1, 4, 7, 10)
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
EARLY_ROUNDS = range(1, 7)

#: D111's recorded Y1 control means on the {1,4,7,10} grid, `season_long`, vintage 63076e2e.
D111_CONTROL = {"target_league": 2002.9, "dynasty_1qb": 2061.5}


class ParityError(RuntimeError):
    """The control does not reproduce the current baseline. The audit must not be interpreted."""


def _static_for(con, league, season):
    series = resolve_market_series(league)
    static = load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )
    if not static.market_rank or not static.projections:
        raise ParityError(f"{league.league_id} {season}: empty board")
    return static


def classify_pick(league, roster_positions, picks_remaining, scored, pick):
    """`(binding, category, restricted_pick)` for one pick — the Part 2 classifier.

    The restriction is applied exactly as `league/opportunity_cost.py::roster_aware_market_pick`
    applies it: it activates once `picks_remaining <= total_deficit` (equivalently, slack <= 0) and
    restricts the choice to positions with an unfilled dedicated slot. Both the restricted and the
    unrestricted argmax come off the SAME `_pick_by_tier` slate, so C and D are measured rather
    than inferred.

        A -- no mandatory slot outstanding
        B -- one is, but the rule is not binding, so Alpha's choice is unrestricted
        C -- the rule is binding AND changes the pick
        D -- the rule is binding but does not change the pick
    """
    deficit = unfilled_dedicated_slots(league, roster_positions)
    total_deficit = sum(deficit.values())
    binding = total_deficit > 0 and picks_remaining <= total_deficit
    ranked = sorted(scored, key=lambda c: (-c.score, c.player_id))
    restricted = [c for c in ranked if c.position in deficit]
    restricted_pick = restricted[0].player_id if restricted else None
    if binding and restricted_pick is not None:
        return binding, ("C" if restricted_pick != pick else "D"), restricted_pick
    if total_deficit == 0:
        return binding, "A", restricted_pick
    return binding, "B", restricted_pick


def _walk_draft(con, league, season, static, slot, *, collect):
    """One full Alpha draft on the production-equivalent path, calling `collect` at each of our
    picks with the full pre-pick state. Identical geometry, opponents and tie-breaks to D103's
    `_play_draft`; it differs only in recording what it sees."""
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
        my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
        pick, scored = _pick_by_tier(
            static, con, league, season, avail, list(my_pos), SHIPPED_TIER, current, nxt,
            roster_player_ids=list(mine), picks_remaining=remaining,
        )
        collect(round_no, remaining, my_pos, set(avail), pick, scored)
        mine.append(pick)
        avail.discard(pick)
    return mine


# --------------------------------------------------------------------------------------------
# MODE: parity -- the control must reproduce D111's baseline before anything is read
# --------------------------------------------------------------------------------------------
def run_parity(con) -> dict:
    out = {"vintage": compute_board_vintage(con).as_dict()["combined_hash"], "means": {}}
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        values = []
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            for slot in D111_SLOTS:
                mine = _walk_draft(
                    con, league, season, static, slot, collect=lambda *a, **k: None
                )
                actual = _actual_points_for(con, season, mine)
                single = league.model_copy(update={"teams": 1})
                starters = compute_league_starters(
                    single, {p: actual.get(p, 0.0) for p in mine},
                    {p: static.positions.get(p, "UNKNOWN") for p in mine},
                )
                values.append(sum(actual.get(p, 0.0) for p in starters["starters"]))
            print(f"  parity {league_name} {season} done", flush=True)
        out["means"][league_name] = mean(values)
    return out


def report_parity(out: dict) -> None:
    print(f"\n{'=' * 96}\nCONTROL PARITY -- Y1 must reproduce D111's baseline\n{'=' * 96}")
    print(f"\n  board vintage {out['vintage']}")
    ok = True
    for league_name in FORMATS:
        got = out["means"][league_name]
        want = D111_CONTROL[league_name]
        match = abs(got - want) < 0.05
        ok = ok and match
        print(f"  {league_name:<16} D111 recorded {want:>8.1f}   re-measured {got:>8.1f}   "
              f"{'MATCH' if match else 'MISMATCH'}")
    print(f"\n  PARITY: {'PASS' if ok else 'FAIL -- STOP, do not interpret the audit'}")
    if not ok:
        raise ParityError("Y1 control does not reproduce D111's baseline")


# --------------------------------------------------------------------------------------------
# MODE: audit -- Parts 1 and 2
# --------------------------------------------------------------------------------------------
def run_audit(con, slots) -> dict:
    picks: list[dict] = []
    drafts: list[dict] = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            for slot in slots:
                rows: list[dict] = []

                def collect(round_no, remaining, my_pos, avail, pick, scored, _rows=rows,
                            league=league, static=static, league_name=league_name,
                            season=season, slot=slot):
                    deficit = unfilled_dedicated_slots(league, my_pos)
                    total_deficit = sum(deficit.values())
                    slack = remaining - total_deficit
                    ranked = sorted(scored, key=lambda c: (-c.score, c.player_id))
                    binding, category, restricted_pick = classify_pick(
                        league, my_pos, remaining, scored, pick
                    )
                    # --- the capacity ceiling, recovered exactly (the penalty is a x0.1 multiply)
                    uncapped = sorted(
                        ranked,
                        key=lambda c: (
                            -(c.score / OVER_CAP_VALUE_MULTIPLIER
                              if c.feasibility_multiplier is not None else c.score),
                            c.player_id,
                        ),
                    )
                    cap_fired = sum(1 for c in ranked if c.feasibility_multiplier is not None)
                    # --- is the pool able to satisfy every outstanding mandatory slot?
                    supply = {
                        pos: sum(1 for p in avail if static.positions.get(p) == pos)
                        for pos in deficit
                    }
                    _rows.append({
                        "league": league_name, "season": season, "slot": slot,
                        "round": round_no, "picks_remaining": remaining,
                        "deficit": dict(deficit), "total_deficit": total_deficit,
                        "slack": slack, "binding": binding, "category": category,
                        "pick_pos": static.positions.get(pick, "UNKNOWN"),
                        "restricted_pick_pos": (
                            static.positions.get(restricted_pick, "UNKNOWN")
                            if restricted_pick else None
                        ),
                        "fills_deficit": static.positions.get(pick, "UNKNOWN") in deficit,
                        "cap_fired_n": cap_fired,
                        "cap_changed_pick": uncapped[0].player_id != pick,
                        "cap_uncapped_pos": static.positions.get(
                            uncapped[0].player_id, "UNKNOWN"),
                        "min_supply": min(supply.values()) if supply else None,
                    })

                mine = _walk_draft(con, league, season, static, slot, collect=collect)
                final_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                final_deficit = unfilled_dedicated_slots(league, final_pos)
                first_round = {}
                for pos in POSITIONS:
                    for i, p in enumerate(final_pos, start=1):
                        if p == pos:
                            first_round[pos] = i
                            break
                # The margin that means anything is the minimum slack while a mandatory slot is
                # still OUTSTANDING. Once the deficit is zero, `slack == picks_remaining` and
                # decays trivially to 1 at the final pick, which is not a feasibility fact --
                # it is arithmetic. Both are recorded, and the report quotes `min_live_slack`.
                live = [r for r in rows if r["total_deficit"] > 0]
                drafts.append({
                    "league": league_name, "season": season, "slot": slot,
                    "min_slack": min(r["slack"] for r in rows),
                    "min_slack_round": min(rows, key=lambda r: r["slack"])["round"],
                    "min_live_slack": min((r["slack"] for r in live), default=None),
                    "last_deficit_round": max((r["round"] for r in live), default=0),
                    "final_unfilled": dict(final_deficit),
                    "legal": not final_deficit,
                    "first_round": first_round,
                    "n_binding": sum(1 for r in rows if r["binding"]),
                    "n_category_C": sum(1 for r in rows if r["category"] == "C"),
                    "composition": dict(Counter(final_pos)),
                })
                picks.extend(rows)
            print(f"  audit {league_name} {season} done", flush=True)
    return {"picks": picks, "drafts": drafts}


def report_audit(out: dict) -> None:
    picks, drafts = out["picks"], out["drafts"]
    print(f"\n{'=' * 96}\nPART 1 -- IS ALPHA EVER AT RISK OF AN ILLEGAL ROSTER?\n{'=' * 96}")
    for league_name in FORMATS:
        d = [x for x in drafts if x["league"] == league_name]
        p = [x for x in picks if x["league"] == league_name]
        if not d:
            continue
        illegal = [x for x in d if not x["legal"]]
        print(f"\n  {league_name}   ({len(d)} drafts, {len(p)} Alpha picks)")
        print(f"    final rosters ILLEGAL (a mandatory slot unfilled): "
              f"{len(illegal)}/{len(d)}")
        ms = [x["min_live_slack"] for x in d if x["min_live_slack"] is not None]
        print("    feasibility slack (picks_remaining - unfilled mandatory slots), starts at 8.")
        print("    Quoted while a mandatory slot is still OUTSTANDING -- after the deficit hits")
        print("    zero, slack is just picks_remaining decaying to 1, which is arithmetic, not a")
        print("    feasibility fact. The rule activates at slack == 0.")
        print(f"      minimum while live: min {min(ms)}  median {sorted(ms)[len(ms) // 2]}  "
              f"max {max(ms)}  mean {mean(ms):.2f}")
        print(f"      distribution of per-draft minimum live slack: "
              f"{dict(sorted(Counter(ms).items()))}")
        lr = [x["last_deficit_round"] for x in d]
        print(f"      round the LAST mandatory slot is filled: mean {mean(lr):.2f}  "
              f"worst {max(lr)}")
        print(f"      drafts where slack ever reached 0 (the rule would activate): "
              f"{sum(1 for x in d if x['min_live_slack'] is not None and x['min_live_slack'] <= 0)}"
              f"/{len(d)}")
        print(f"      drafts where slack ever went NEGATIVE (already infeasible): "
              f"{sum(1 for x in d if x['min_live_slack'] is not None and x['min_live_slack'] < 0)}"
              f"/{len(d)}")
        print(f"    picks at which the legality rule is BINDING: "
              f"{sum(1 for x in p if x['binding'])}/{len(p)}")
        print(f"    picks where it CHANGES Alpha's choice (category C): "
              f"{sum(1 for x in p if x['category'] == 'C')}/{len(p)}")
        sup = [x["min_supply"] for x in p if x["min_supply"] is not None]
        if sup:
            print(f"    pool supply at the scarcest outstanding mandatory position: "
                  f"min {min(sup)}  p10 {sorted(sup)[len(sup) // 10]}  median "
                  f"{sorted(sup)[len(sup) // 2]}")
        print("    first round each mandatory position is filled (mean / worst):")
        for pos in POSITIONS:
            got = [x["first_round"].get(pos) for x in d]
            have = [g for g in got if g is not None]
            missing = len(got) - len(have)
            print(f"      {pos:<4} mean {mean(have):>5.2f}  worst {max(have):>3}  "
                  f"never drafted in {missing}/{len(d)} drafts" if have else
                  f"      {pos:<4} never drafted in any draft")
        print("    mean roster composition: " + "  ".join(
            f"{pos} {mean(x['composition'].get(pos, 0) for x in d):.2f}" for pos in POSITIONS))

    print(f"\n{'=' * 96}\nPART 2 -- DOES FEASIBILITY CONSTRAIN THE EARLY PICKS?\n{'=' * 96}")
    print("\n  A = no mandatory slot outstanding   B = constraint exists but is not binding")
    print("  C = binding AND changes the pick     D = binding but does not change the pick")
    for league_name in FORMATS:
        p = [x for x in picks if x["league"] == league_name]
        if not p:
            continue
        print(f"\n  {league_name}")
        print(f"    {'rounds':<14}{'picks':>7}{'A':>8}{'B':>8}{'C':>8}{'D':>8}"
              f"{'C %':>8}{'min slack':>11}")
        groups = [("1-6 (EARLY)", range(1, 7)), ("7-11", range(7, 12)),
                  ("12-16", range(12, 17)), ("ALL", range(1, 17))]
        for label, rng in groups:
            sub = [x for x in p if x["round"] in rng]
            if not sub:
                continue
            c = Counter(x["category"] for x in sub)
            print(f"    {label:<14}{len(sub):>7}{c['A']:>8}{c['B']:>8}{c['C']:>8}{c['D']:>8}"
                  f"{c['C'] / len(sub):>7.1%}{min(x['slack'] for x in sub):>11}")
        print(f"    {'round':<7}{'n':>5}{'A':>6}{'B':>6}{'C':>6}{'D':>6}{'min slack':>11}"
              f"{'fills a deficit slot':>22}")
        for rnd in range(1, 17):
            sub = [x for x in p if x["round"] == rnd]
            if not sub:
                continue
            c = Counter(x["category"] for x in sub)
            fills = sum(1 for x in sub if x["fills_deficit"]) / len(sub)
            print(f"    {rnd:<7}{len(sub):>5}{c['A']:>6}{c['B']:>6}{c['C']:>6}{c['D']:>6}"
                  f"{min(x['slack'] for x in sub):>11}{fills:>21.0%}")

    print(f"\n{'=' * 96}\nTHE CAPACITY CEILING -- does the mechanism already in production bind?"
          f"\n{'=' * 96}")
    print(f"\n  `positional_feasibility_cap` x {OVER_CAP_VALUE_MULTIPLIER} is in tier L0, i.e. in")
    print("  production. Caps: QB 2, RB 6, WR 6, TE 4, K 2, DST 2. The un-penalised score is")
    print("  recovered exactly, so 'changes the pick' below is an exact counterfactual.")
    for league_name in FORMATS:
        p = [x for x in picks if x["league"] == league_name]
        if not p:
            continue
        print(f"\n  {league_name}")
        print(f"    {'rounds':<14}{'picks':>7}{'cap fires':>11}{'changes pick':>14}")
        for label, rng in (("1-6 (EARLY)", range(1, 7)), ("7-11", range(7, 12)),
                           ("12-16", range(12, 17)), ("ALL", range(1, 17))):
            sub = [x for x in p if x["round"] in rng]
            if not sub:
                continue
            fired = sum(1 for x in sub if x["cap_fired_n"] > 0)
            changed = sum(1 for x in sub if x["cap_changed_pick"])
            print(f"    {label:<14}{len(sub):>7}{fired / len(sub):>10.1%}"
                  f"{changed / len(sub):>13.1%}")
        changed_rows = [x for x in p if x["cap_changed_pick"]]
        if changed_rows:
            swaps = Counter((x["cap_uncapped_pos"], x["pick_pos"]) for x in changed_rows)
            print(f"    where it changes the pick (uncapped choice -> actual), top 6: "
                  f"{swaps.most_common(6)}")
            by_round = Counter(x["round"] for x in changed_rows)
            print(f"    by round: {dict(sorted(by_round.items()))}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True, choices=("parity", "audit"))
    ap.add_argument("--slots", default=",".join(str(s) for s in ALL_SLOTS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = tuple(int(s) for s in args.slots.split(","))

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise ParityError(f"{season} must never enter the historical evaluation")

    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}")
    print(f"seasons {BACKTEST_SEASONS}  slots {slots}  mode {args.mode}\n")

    if args.mode == "parity":
        result = run_parity(con)
        (out / "d112_parity.json").write_text(json.dumps(result, indent=2, default=str))
        report_parity(result)
    else:
        result = run_audit(con, slots)
        (out / "d112_audit.json").write_text(json.dumps(result, default=str))
        report_audit(result)


if __name__ == "__main__":
    main()
