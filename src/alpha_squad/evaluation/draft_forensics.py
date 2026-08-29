"""Diagnostic-only draft-engine forensic experiment harness (docs/DRAFT_ENGINE_FORENSIC_AUDIT.md,
docs/DRAFT_CONTROLLED_EXPERIMENTS.md).

This module is NOT used by production `league/draft.py` and does NOT replace
`evaluation/draft_simulation.py` (the official, already-validated benchmark harness behind
docs/DECISIONS.md D54's results). It exists so the *same* fixed opponent field, snake-draft
loop, and outcome scoring can run under eight explicitly-labeled, additively-constructed
scoring mechanisms (tiers A-H below) for a true ceteris-paribus ablation: isolating which
mechanism changes which failure, not picking a winner or tuning against real outcomes.

Every tier after A adds exactly one new term on top of the previous tier's score, in the order
the forensic directive specifies. Tier H calls the real, unmodified `recommend_draft_pick` so
the ablation has an honest endpoint to compare against the actual shipped behavior.

Static season data (projections, VORP, replacement levels, positional scarcity, market ranks,
confidence, ECR dispersion) is loaded ONCE per season into plain dicts rather than re-queried
per pick -- unlike `recommend_draft_pick`, which re-queries per candidate per pick (fine at
real single-user-draft scale, far too slow for the hundreds of drafts this diagnostic phase
needs). The *values* and formulas are identical to production; only the query pattern differs,
and every tier that reuses a production concept calls the production function directly
(`replacement_level`, `positional_scarcity`, `marginal_value_over_replacement`,
`roster_need`, `roster_fit_multiplier`) rather than reimplementing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import duckdb

from alpha_squad.evaluation.draft_simulation import (
    ALL_OPPONENT_STRATEGIES,
    MARKET_CONSENSUS,
    MARKET_CONSENSUS_ROSTER_AWARE,
    _market_consensus_pick,
    _market_consensus_roster_aware_pick,
    _next_pick_overall,
    _snake_overall_pick,
)
from alpha_squad.evaluation.replacement_diagnostics import REPLACEMENT_VARIANTS
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import (
    picks_until_next_turn,
    positional_opportunity_cost,
    replay_opponent_picks,
)
from alpha_squad.league.replacement import (
    best_lineup_points,
    load_season_projections,
    marginal_starter_value,
    marginal_value_over_replacement,
    positional_scarcity,
    replacement_level,
    replacement_marginal_starter_values,
)
from alpha_squad.league.roster import (
    OVER_CAP_VALUE_MULTIPLIER,
    positional_feasibility_cap,
    roster_fit_multiplier,
    roster_need,
    saturated_surplus,
    startable_saturation,
)
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

Tier = Literal[
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "P0",
    "P1",
    "P1b",
    "P1c",
    "P2",
    "P3",
    "M0",
    "M1",
    "M2",
    "M3",
    "N0",
    "N1",
    "N2",
    "N3",
    "N4",
    "N0x",
    "N1x",
    "N2x",
    "N3x",
    "N4x",
    "R0",
    "R1",
    "R2",
    "R3",
    "R4",
    "V0",
    "VA",
    "VB",
    "VC",
    "VD",
    "VE",
]
ALL_TIERS: tuple[Tier, ...] = ("A", "B", "C", "D", "E", "F", "G", "H")

# --- P-tiers (D55) -----------------------------------------------------------------------
# The A-H ablation established the ROOT CAUSE but could not, by itself, tell us what to ship:
# tier F (the best performer) is `vorp x fit x scarcity x future x [feasibility] + opp_cost`,
# which INCLUDES `scarcity_mult` -- the one mechanism the experiments proved harmful -- and
# EXCLUDES production's `risk_mult` and `survival_mult`. The redesign recommendation's proposed
# formula (`production + opp_cost`) was therefore never actually measured by A-H.
#
# The P-tiers close that gap: they hold the REAL production formula fixed as the base and vary
# only what is added on top, so the measured result belongs to a formula we could actually ship.
P_TIERS: tuple[Tier, ...] = ("P0", "P1", "P1b", "P1c", "P2", "P3")

# --- M-tiers (D58): marginal STARTER value ---------------------------------------------
# The 1-QB format audit found the scoring path has no representation of the team's own
# starting lineup. VORP measures a player against a LEAGUE-WIDE replacement level and
# `roster_need` measures a positional COUNT, so a player is scored identically whether he
# would be your WR1 or your WR5 -- the engine cannot ask "would this player actually start".
#
# M0 is the shipped production formula, unchanged, as the control. M1-M3 vary only where
# marginal starter value enters, from least to most invasive, so the measurement says which
# (if any) is worth shipping rather than assuming the most elaborate one is.
M_TIERS: tuple[Tier, ...] = ("M0", "M1", "M2", "M3")

# PRE-REGISTERED DECISION RULE for the M-tiers -- committed to source BEFORE these were run
# against real data, following the same D39/D54/D55 discipline as the P-tiers above.
#
#   Primary metric : mean realized starter points (docs/BENCHMARK_SPEC.md's primary).
#   Gate 1         : no position carrying a starting requirement may be zeroed at a higher
#                    rate than M0 zeroes it.
#   Gate 2         : every drafted roster must remain able to field a legal lineup at least
#                    as often as M0's do.
#   Tie-break      : prefer FEWER added mechanisms (Occam), then the simpler formulation.
#   Ship only if   : primary is STRICTLY better than M0's, and both gates pass.
#
# A tier that produces prettier-looking rosters while losing starter points does NOT qualify,
# and neither does one that wins by a margin smaller than the season-to-season spread.
PREREGISTERED_M_CONTROL: Tier = "M0"

# `msv_mult` maps marginal starter value onto the same bounded [0.7, 1.3] shape the existing
# roster-fit and scarcity multipliers use, so tier M2 swaps one bounded multiplier for
# another rather than changing the score's scale. The ratio is the share of a candidate's own
# projection that would actually reach the starting lineup: 1.0 for a player who starts at
# full value, 0.0 for one who would not start at all.
MSV_MULT_FLOOR = 0.7
MSV_MULT_RANGE = 0.6

# Hypothesis B's tightened over-cap multiplier: one order of magnitude below production's 0.1,
# pre-registered before any run rather than searched over. A swept value would be tuning
# against the benchmark, which this phase's rule forbids.
R2_TIGHTENED_OVER_CAP_MULTIPLIER = 0.01

# --- N-tiers (D63 Stage 3): which VALUE BASE, holding everything else identical -----------
# D61 established that D60 traded one blind spot for another. VORP encodes league-wide
# positional scarcity (it correctly refuses an early QB in a 1-QB league) but prices a bench
# K/DST above replacement, so the engine hoarded them. MSV encodes lineup saturation (a second
# kicker is worth exactly zero) but on an empty roster equals the raw projection, i.e. pure
# best-player-available by raw points -- which in a 1-QB league reaches for quarterbacks,
# precisely what VORP existed to correct. D60 chose one and discarded the other; these tiers
# test formulations that keep both.
#
# Every N-tier runs the SAME code path with the same risk/survival/roster-fit/feasibility
# terms and the same D55 opportunity-cost replay. ONLY the value base differs, so any
# difference between them is attributable to the value base and nothing else. `N0` is the
# shipped D60 formula and is therefore identical to `M3` by construction -- a deliberate
# redundancy that lets the harness self-check (see tests) rather than a duplicate mechanism.
#
# The `x` variants switch the opportunity-cost term OFF. That is not an afterthought: the term
# is VORP-denominated and D60 added it to an MSV base, a scale mismatch open since D60. Rather
# than assume it still helps, it is measured as an explicit arm.
N_TIERS: tuple[Tier, ...] = ("N0", "N1", "N2", "N3", "N4")
N_TIERS_NO_OPPORTUNITY_COST: tuple[Tier, ...] = ("N0x", "N1x", "N2x", "N3x", "N4x")
ALL_N_TIERS: tuple[Tier, ...] = (*N_TIERS, *N_TIERS_NO_OPPORTUNITY_COST)

# {tier: (value base, whether the opportunity-cost term is added)}.
N_TIER_SPEC: dict[Tier, tuple[str, bool]] = {
    "N0": ("msv", True),
    "N1": ("vorp", True),
    "N2": ("min_vorp_msv", True),
    "N3": ("msv_over_replacement", True),
    "N4": ("msv_plus_weighted_vorp", True),
    "N0x": ("msv", False),
    "N1x": ("vorp", False),
    "N2x": ("min_vorp_msv", False),
    "N3x": ("msv_over_replacement", False),
    "N4x": ("msv_plus_weighted_vorp", False),
}

# Tier N4 is `msv + w * vorp`. w is PRE-REGISTERED at 1.0 -- fixed before any N-tier ran, and
# not a fitted parameter. 1.0 is the Occam choice (equal weighting, no free dial to tune) and
# it is also what the already-measured M1 tier used (`vorp + opp_cost + msv`, 1987.2), so it is
# the one value with prior evidence behind it. Any other w would need its own pre-registration.
N4_VORP_WEIGHT = 1.0

# PRE-REGISTERED DECISION RULE for the N-tiers -- committed to source BEFORE any N-tier was
# executed against real data, per the D39/D54/D55 discipline and the explicit instruction in
# docs/DRAFT_STRATEGY_NEXT_PHASE_PLAN.md ("commit to source before any run").
#
#   Control        : N0, the shipped D60 formula, run under production's real feasibility caps
#                    against the FAIR (roster-aware) opponent.
#   Primary metric : mean realized starter points vs. the fair opponent.
#   Gate 1         : no starting-requirement position zeroed at a higher rate than the control.
#   Gate 2         : n_infeasible_rosters no higher than the control.
#   Gate 3         : mean starter points must not be worse than the control in more than 1 of
#                    the 5 seasons. Blocks a tier that wins the pooled mean on one big season --
#                    the failure mode this evidence base (n=5 seasons) is most exposed to.
#   Gate 4         : no position drafted at a mean round more than 2 rounds EARLIER than the
#                    control without measured justification. This is the gate that would have
#                    caught D60's K/DST timing regression, which no pre-D63 gate checked.
#   Robustness     : leave-one-season-out -- the margin must survive removing ANY single season.
#   Tie-break      : fewer mechanisms; then lower starter-points variance.
#   Ship only if   : strictly beats the control on the primary metric AND all four gates pass
#                    AND the margin survives leave-one-season-out.
#
# A tier that wins the pooled mean but fails a gate does NOT ship. Recording the rule here,
# before the numbers exist, is what stops the rule from being reshaped around the result.
PREREGISTERED_N_CONTROL: Tier = "N0"
PREREGISTERED_MAX_WORSE_SEASONS = 1
PREREGISTERED_MAX_ROUNDS_EARLIER = 2.0

# --- R-tiers (D64): correcting N4's kicker hoarding -----------------------------------------
# D63 shipped `msv + VORP` and reported a known regression: the blend breaches the kicker cap in
# 32 of 50 drafts (mean 2.74 K against a cap of 2). Tracing a real hoarding draft (2023, slot 9)
# pick-by-pick through the production scoring path established the mechanism, and it is NOT
# quite the one the documentation assumed:
#
#   * By the late rounds every startable slot is full, so MSV is 0.0 for EVERY candidate and
#     the value base collapses to VORP alone.
#   * VORP is measured against a STATIC, league-wide preseason replacement level. Ten teams
#     strip the skill-position pools, so by round 11 the best available RB/WR/TE has fallen far
#     BELOW its replacement level (measured: RB -135.6, WR -123.0, QB -273.5 at round 16).
#     Almost nobody drafts kickers, so the best available K is still far ABOVE its replacement
#     level (+30.1 at round 11, +17.2 at round 16).
#   * So VORP systematically favours K/DST late. Flex-eligibility matters, but as the second-
#     order cause: K saturates at ONE startable slot while RB/WR have four.
#
# Two consequences that shaped these tiers, both measured rather than assumed:
#   1. The second kicker is taken while the roster is still UNDER the feasibility cap (1 < 2).
#      At that pick every one of the top 20 candidates is under-cap, so the over-cap multiplier
#      is not even engaged.
#   2. At the third kicker every alternative is at or below replacement, so its score is <= 0.
#      No POSITIVE over-cap multiplier can reorder a positive K above a non-positive skill
#      player. The probe reported the multiplier would need to be < -0.0000 to flip the pick.
# Hypothesis B is therefore predicted to be inert. It is still measured, not dismissed.
R_TIERS: tuple[Tier, ...] = ("R0", "R1", "R2", "R3", "R4")

# R4 is POST-HOC, and is labelled as such rather than presented as pre-registered. It exists
# because measuring R1 exposed a defect in R1's own implementation, not because R1's number was
# disliked: zeroing a saturated position's surplus collapses many late candidates to a score of
# EXACTLY 0.0, and the generic `(-score, player_id)` sort then resolves those ties
# alphabetically. Measured over 144 real picks, R1 decides **19%** of its picks that way against
# R0's 0% -- i.e. one pick in five is effectively random. R4 keeps R1's scoring unchanged and
# replaces only the tie-break, so it must still clear the same pre-registered gates as anything
# else. Preferring, among exactly-tied candidates, the position with the most STARTABLE capacity
# left is not a new value model: the benchmark scores the best legal lineup from REALIZED
# points, so a bench WR who outperforms can still enter the lineup while a third kicker never
# can -- at equal projected value the flex-eligible player strictly dominates on realized upside.
R_TIERS_CAPACITY_TIEBREAK: tuple[Tier, ...] = ("R4",)

# --- V-tiers (D65): draft-aware replacement levels -----------------------------------------
# Production computes VORP from the FULL season pool every pick, so the replacement level a
# candidate is scored against is numerically identical at pick 1 and pick 160 -- confirmed in
# code: `available_player_ids` never reaches the VORP calculation in `league/draft.py`.
#
# These tiers hold the shipped N4 formula fixed -- (msv + vorp + opp_cost) x fit x risk x
# survival x [cap] -- and change ONLY where the replacement level inside `vorp` comes from, so
# any difference is attributable to staleness and nothing else. V0 is N4 unchanged.
# Definitions live in `evaluation/replacement_diagnostics.py`, deliberately outside production.
V_TIERS: tuple[Tier, ...] = ("V0", "VA", "VB", "VC", "VD", "VE")

#: {tier: key into replacement_diagnostics.REPLACEMENT_VARIANTS, or None for the static control}
V_TIER_SPEC: dict[Tier, str | None] = {
    "V0": None,  # shipped N4: static, full-season replacement -- the control
    "VA": "available_pool",  # Candidate A
    "VB": "remaining_demand",  # Candidate B
    "VC": "hybrid_capacity",  # Candidate C
    "VD": "dedicated_plus_one_bench",  # Candidate C4 (D66)
    "VE": "earned_starter",  # Candidate C5 (D66)
}

# --- D66: why C3 loads tight ends, and what the demand target should be ---------------------
# D65 left C3 (`hybrid_capacity`) as the strongest candidate but blocked on a Gate 3 failure
# traced to systematic TE loading (exactly 4.00 TEs every season). The cause is now measured,
# and it is an arithmetic defect in the demand target rather than anything about tight ends:
#
#   `startable_slots` counts every FLEX slot once per ELIGIBLE position. In the 1-QB target
#   format that is 2 flex slots counted 3x (RB, WR, TE), so it sums to 14 per team while the
#   lineup starts only 10. Candidates B and C inherit the error and demand 140 and 220
#   league-wide players for 100 real starting slots.
#
#   TE absorbs the worst of it. Its startable count of 3 assumes it wins both flex slots, but
#   measured across ALL FIVE real seasons, WR wins all 20 league-wide flex slots and TE wins
#   NONE. True TE starter demand is 1.00 per team -- C3 demands 4.
#
# C4 and C5 are the two pre-registered repairs, committed before either was run:
#   VD / C4  dedicated + 1 bench    -- the documented D65 proposal; drops flex entirely, then
#                                      restores one uniform unit of depth. Sums to 14/team.
#   VE / C5  earned-starter demand  -- per-team target read off the flex allocation
#                                      `compute_league_starters` ALREADY computes, so it sums
#                                      to exactly the lineup size (10) by construction and is
#                                      measured rather than assumed. No new constant.
#
# Decision rule is unchanged from D65: control V0 (= shipped N4), primary metric mean realized
# starter points vs. the fair opponent, Gates 1-4 verbatim, leave-one-season-out robustness.
# Ship only on a strict primary win with every gate passing. A candidate that merely reduces TE
# count without improving starter points does NOT qualify -- TE count is evidence, not a goal.

# PRE-REGISTERED DECISION RULE for the V-tiers -- committed before any V-tier ran, same
# discipline as the N- and R-tiers. Control V0 (= shipped N4), primary metric mean realized
# starter points vs. the fair opponent, Gates 1-4 reused verbatim, robustness by
# leave-one-season-out. Ship only on a strict primary win with all gates passing.
#
# Calibration recorded BEFORE running, so the result cannot be reinterpreted afterwards: the
# surplus-kicker problem this hypothesis targets has a measured ceiling of about +5 starter
# points (the 3rd and 4th kickers are worth EXACTLY 0.0 and never enter the realized lineup in
# 0/32 drafts; a marginal skill pick is worth +7.3, so perfectly reallocating those picks is
# worth ~7.3 x 32/50). That ceiling is far inside the +-33 confidence half-width, so a K-driven
# win is not detectable here. If these tiers help, it must be by re-ranking SKILL positions
# against each other in rounds 11-16, which carry 16.1% of realized starter points.
PREREGISTERED_V_CONTROL: Tier = "V0"

# {tier: (apply startable-saturation to the VORP surplus, over-cap multiplier)}
R_TIER_SPEC: dict[Tier, tuple[bool, float]] = {
    "R0": (False, OVER_CAP_VALUE_MULTIPLIER),  # N4 exactly, as shipped at D63 -- the control
    "R1": (True, OVER_CAP_VALUE_MULTIPLIER),  # Hypothesis A
    "R2": (False, R2_TIGHTENED_OVER_CAP_MULTIPLIER),  # Hypothesis B
    "R3": (True, R2_TIGHTENED_OVER_CAP_MULTIPLIER),  # A + B
    "R4": (True, OVER_CAP_VALUE_MULTIPLIER),  # A, with R1's zero-tie degeneracy repaired
}

# PRE-REGISTERED DECISION RULE for the R-tiers -- committed to source BEFORE any R-tier was run
# against real data, same discipline as the N-tiers above.
#
#   Control        : R0 (= the shipped D63 `msv + VORP`), fair opponent, production caps.
#   Primary metric : mean realized starter points vs. the fair opponent.
#   Gates 1-4      : unchanged from the N-tier rule (zero-rate, infeasibility, per-season
#                    consistency, positional timing) -- reused verbatim via
#                    `evaluate_preregistered_gates`.
#   Gate 5 (new)   : the candidate must not INCREASE cap breaches at any position relative to
#                    the control. This phase exists because a shipped tier passed the first
#                    four gates while carrying a cap-breach regression none of them checked.
#   Robustness     : leave-one-season-out -- the margin must survive removing any single season.
#   Ship only if   : strictly beats the control on the primary metric AND all gates pass AND
#                    the margin survives leave-one-season-out.
#
# Explicitly NOT a goal: fewer kickers. A tier that cuts kicker count while losing starter
# points does NOT ship, and the decision hierarchy is starter points first, roster feasibility
# fourth. Reducing K count is only evidence that the mechanism works, never the objective.
PREREGISTERED_R_CONTROL: Tier = "R0"


def marginal_starter_multiplier(msv: float, projection: float) -> float:
    """Bounded [0.7, 1.3] multiplier from marginal starter value (tier M2)."""
    if projection <= 0:
        return MSV_MULT_FLOOR
    ratio = max(0.0, min(1.0, msv / projection))
    return MSV_MULT_FLOOR + MSV_MULT_RANGE * ratio


# PRE-REGISTERED DECISION RULE -- committed before the P-tiers were ever run against real data,
# following the D39/D54 discipline of fixing the rule before seeing the outcome so a result
# cannot be rationalised after the fact.
#
#   Primary metric : mean starter points (the metric that decides real fantasy outcomes; total
#                    roster points rewards bench hoarding, which is the pathology under study).
#   Gate 1         : RB=0 rate must not exceed production's measured 10/50.
#   Gate 2         : no position carrying a starting requirement may be zeroed at a HIGHER rate
#                    than production zeroes it (guards against trading one hole for another).
#   Tie-break      : prefer the tier with FEWER added mechanisms (Occam; each mechanism is
#                    future maintenance and another way to be wrong).
#   Ship only if   : primary is STRICTLY better than P0's, and both gates pass.
#
# A tier that improves RB=0 while losing starter points does NOT qualify. Improving the
# headline pathology is not by itself evidence the system got better.
PREREGISTERED_PRIMARY_METRIC = "mean_starter_points"
PREREGISTERED_RB_ZERO_GATE = 10  # out of 50 trials; production's measured rate

TIER_DESCRIPTIONS: dict[Tier, str] = {
    "A": "raw player value only, no roster context",
    "B": "+ current roster fit (roster_need / roster_fit_multiplier, unchanged from production)",
    "C": "+ current positional scarcity (positional_scarcity -- computed in production for "
    "waiver.py but never consulted by draft.py)",
    "D": "+ analytical future positional scarcity (aggregate per-player survival-probability "
    "decay, extended from a single candidate to the whole position)",
    "E": "+ roster feasibility (a hard, league-config-derived cap, replacing roster_fit's soft "
    "bound once a position is unambiguously full)",
    "F": "+ explicit opportunity cost (current value vs. this position's expected value at my "
    "next pick, priced in points, not just a multiplier)",
    "G": "+ opponent-behavior simulation (literally replay the known real market-consensus "
    "opponent strategy forward to my next pick, rather than approximate it analytically)",
    "H": "the real, unmodified production recommend_draft_pick",
    # P-tiers: production formula held fixed as the base, only the addition varies (D55).
    "P0": "production formula reproduced in-harness (vorp x fit x risk x survival) -- the "
    "control; must match tier H closely or the harness does not model production",
    "P1": "P0 + opp_cost (raw additive) -- the redesign recommendation's literal proposal",
    "P1b": "P0 + opp_cost x risk_mult (confidence-scaled additive)",
    "P1c": "(vorp + opp_cost) x fit x risk x survival -- integrated: the opportunity cost is "
    "itself denominated in VORP points, so it is discounted by the same roster-fit and "
    "confidence factors as the value it augments",
    "P2": "P0 x feasibility_mult (hard league-derived positional cap, no opportunity cost)",
    "P3": "P1c x feasibility_mult (integrated opportunity cost + feasibility cap)",
    # M-tiers (D58): where marginal STARTER value enters, least to most invasive.
    "M0": "the shipped production formula, unchanged -- (vorp + opp_cost) x fit x risk x "
    "survival x [feasibility]. The control.",
    "M1": "M0 + marginal starter value added inside the value term: "
    "(vorp + opp_cost + msv) x fit x risk x survival x [feasibility]",
    "M2": "M0 with the COUNT-based roster-fit multiplier replaced by a starter-value one: "
    "(vorp + opp_cost) x msv_mult x risk x survival x [feasibility]",
    "M3": "marginal starter value replaces VORP as the value base: "
    "(msv + opp_cost) x fit x risk x survival x [feasibility]",
    # N-tiers (D63): identical formula throughout, ONLY the value base varies.
    "N0": "value base = msv (the shipped D60 formula; identical to M3) -- the control",
    "N1": "value base = vorp (the D55 formula; identical to M0) -- second reference point",
    "N2": "value base = min(vorp, msv) -- scarcity early (msv >= vorp on an empty roster, so "
    "min = vorp), saturation late (msv -> 0, so min -> 0)",
    "N3": "value base = marginal starter value OVER REPLACEMENT: "
    "best_lineup(roster+candidate) - best_lineup(roster+replacement body at that position). "
    "Reduces to vorp on an empty roster and to 0 at a saturated position, by construction",
    "N4": "value base = msv + w*vorp, w pre-registered at 1.0 -- the additive blend",
    "N0x": "N0 with the opportunity-cost term switched OFF",
    "N1x": "N1 with the opportunity-cost term switched OFF",
    "N2x": "N2 with the opportunity-cost term switched OFF",
    "N3x": "N3 with the opportunity-cost term switched OFF",
    "N4x": "N4 with the opportunity-cost term switched OFF",
    # R-tiers (D64): correcting N4's kicker hoarding. Control R0 == N4 == the shipped engine.
    "R0": "the shipped D63 formula, unchanged: (msv + vorp + opp_cost) x fit x risk x survival "
    "x [0.1 if over cap] -- the control",
    "R1": "Hypothesis A: the VORP SURPLUS is scaled by the fraction of the position's startable "
    "capacity still unfilled, so a position that can no longer start anyone contributes no "
    "surplus. Below-replacement value is left untouched",
    "R2": "Hypothesis B: R0 with the over-cap multiplier tightened 0.1 -> 0.01",
    "R3": "Hypothesis A + B combined",
    "R4": "Hypothesis A with the zero-score tie broken by remaining startable capacity, then "
    "projection, instead of alphabetically by player_id (post-hoc; repairs a measured defect "
    "in R1 that made 19% of its picks arbitrary)",
    # V-tiers (D65): N4 held fixed, only the replacement level behind VORP varies.
    "V0": "the shipped N4 formula with production's STATIC full-season replacement -- control",
    "VA": "Candidate A: replacement recomputed from the currently AVAILABLE pool each pick",
    "VB": "Candidate B: replacement at the league's REMAINING DEMAND boundary, demand from "
    "startable slots",
    "VC": "Candidate C: as B, with demand from positional_capacity (startable + bench share)",
    "VD": "Candidate C4: remaining demand from dedicated slots + one bench slot",
    "VE": "Candidate C5: remaining demand from the EARNED starter allocation (dedicated + flex "
    "slots the position actually wins), which sums to exactly the lineup size",
}


@dataclass
class SeasonStatic:
    """Everything needed to score any candidate at any point in a `season` draft, loaded once
    rather than per pick. `available_at_load` is irrelevant here -- VORP/replacement level are
    computed from the full season projection universe by design (standard value-based-drafting
    theory: replacement level represents the post-draft waiver-wire floor, which does not move
    just because one particular draft is in progress -- see the forensic audit's "ruled out"
    section for why this is not treated as a bug)."""

    season: int
    ecr_type: str
    projections: dict[str, float]
    positions: dict[str, str]
    vorp: dict[str, float]
    replacement_levels: dict[str, float]
    scarcity_raw: dict[str, float]
    scarcity_norm: dict[str, float]
    market_rank: dict[str, tuple[str, float]]  # player_id -> (position, ecr_rank)
    confidence: dict[str, float]
    ecr_dispersion: dict[str, tuple[float, float]]  # player_id -> (ecr_best, ecr_worst)


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return dict.fromkeys(values, 0.5)
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def load_season_static(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    ecr_type: str | None = None,
) -> SeasonStatic:
    # D56: the board has to match the league format the experiment is run against.
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type
    projections, positions = load_season_projections(con, season)
    vorp = marginal_value_over_replacement(league, projections, positions)
    levels = replacement_level(league, projections, positions)
    scarcity_raw = positional_scarcity(league, projections, positions)
    scarcity_norm = _normalize(scarcity_raw)
    market_rank = _preseason_overall_market(con, ecr_type, season)

    conf_rows = con.execute(
        "SELECT player_id, confidence FROM uncertainty_predictions "
        "WHERE season = ? AND model_version = ? AND confidence IS NOT NULL",
        [season, UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    confidence = dict(conf_rows)

    dispersion_rows = con.execute(
        """
        SELECT player_id, ecr_best, ecr_worst FROM (
            SELECT player_id, ecr_best, ecr_worst,
                   row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)
              AND ecr_best IS NOT NULL AND ecr_worst IS NOT NULL
        ) WHERE rn = 1
        """,
        [ecr_type, season],
    ).fetchall()
    ecr_dispersion = {pid: (best, worst) for pid, best, worst in dispersion_rows}

    return SeasonStatic(
        season=season,
        ecr_type=ecr_type,
        projections=projections,
        positions=positions,
        vorp=vorp,
        replacement_levels=levels,
        scarcity_raw=scarcity_raw,
        scarcity_norm=scarcity_norm,
        market_rank=market_rank,
        confidence=confidence,
        ecr_dispersion=ecr_dispersion,
    )


def _survival_probability(
    static: SeasonStatic, player_id: str, next_pick_overall: int | None
) -> float | None:
    """Identical formula to league/draft.py::next_pick_survival_probability, evaluated against
    the pre-loaded dispersion dict instead of a fresh query."""
    if next_pick_overall is None:
        return None
    disp = static.ecr_dispersion.get(player_id)
    if disp is None:
        return None
    best, worst = disp
    if worst <= best:
        return 0.0 if next_pick_overall >= best else 1.0
    if next_pick_overall <= best:
        return 1.0
    if next_pick_overall >= worst:
        return 0.0
    return 1.0 - (next_pick_overall - best) / (worst - best)


@dataclass
class CandidateScore:
    player_id: str
    position: str
    projection: float
    vorp: float
    replacement_level: float
    scarcity_raw: float
    scarcity_norm: float
    roster_need: float
    fit_multiplier: float
    confidence: float | None
    survival_probability: float | None
    future_scarcity_multiplier: float | None
    feasibility_multiplier: float | None
    opportunity_cost_pts: float | None
    opponent_depletion_multiplier: float | None
    score: float
    marginal_starter_value: float | None = None
    startable_saturation: float | None = None
    reasons: list[str] = field(default_factory=list)


def _future_position_pool_after_market_consensus(
    static: SeasonStatic, available: set[str], position: str, n_opponent_picks: int
) -> list[str]:
    """Literal agent-based simulation (tier G): replay `n_opponent_picks` real
    market-consensus picks forward (the actual, known strategy governing every one of this
    simulation's 9 opponent slots) and return the players still available at `position`
    afterward. This is more expensive than an analytical approximation but is a direct replay
    of the real opponent model already validated in evaluation/draft_simulation.py, not a new
    behavioral assumption.

    Delegates the replay itself to `league/opportunity_cost.py::replay_opponent_picks` (the
    canonical implementation now also used by the production draft engine, D55) so the two
    cannot drift. The `, p` secondary sort key is a determinism fix (D55): the original had
    none, and real VORP/projection ties exist in production data (2021: 8 tied WR groups
    covering 17 players, 5 TE groups / 13 players), so `future_pool[0]` could differ between
    process runs under hash randomization -- the same bug class D54 fixed in
    `draft_simulation.py`."""
    remaining = replay_opponent_picks(available, static.market_rank, n_opponent_picks)
    return sorted(
        (p for p in remaining if static.positions.get(p) == position),
        key=lambda p: (-static.projections.get(p, float("-inf")), p),
    )


def _opportunity_cost_for(
    static: SeasonStatic,
    position: str,
    available: set[str] | None,
    current_pick_overall: int | None,
    next_pick_overall: int | None,
    opportunity_costs: dict[str, float] | None,
) -> float:
    """Prefer the per-pick precomputed map (see `_pick_by_tier`); fall back to computing this
    one position on demand so `score_candidate` stays usable standalone in tests."""
    if opportunity_costs is not None:
        return opportunity_costs.get(position, 0.0)
    return positional_opportunity_cost(
        available or set(),
        static.positions,
        static.vorp,
        static.market_rank,
        picks_until_next_turn(current_pick_overall, next_pick_overall),
        [position],
    )[position]


def score_candidate(
    static: SeasonStatic,
    player_id: str,
    league: LeagueContext,
    roster_positions: list[str],
    tier: Tier,
    *,
    available: set[str] | None = None,
    current_pick_overall: int | None = None,
    next_pick_overall: int | None = None,
    opportunity_costs: dict[str, float] | None = None,
    roster_player_ids: list[str] | None = None,
    base_lineup_points: float | None = None,
    replacement_msv: dict[str, float] | None = None,
    saturation_factors: dict[str, float] | None = None,
    dynamic_levels: dict[str, float] | None = None,
) -> CandidateScore | None:
    position = static.positions.get(player_id)
    if position is None or player_id not in static.vorp:
        return None

    projection = static.projections[player_id]
    vorp = static.vorp[player_id]
    level = static.replacement_levels.get(position, 0.0)
    scarcity_raw = static.scarcity_raw.get(position, 0.0)
    scarcity_norm = static.scarcity_norm.get(position, 0.5)
    needs = roster_need(league, roster_positions)
    need_score = needs.get(position, 0.0)
    fit_mult = roster_fit_multiplier(need_score)
    confidence = static.confidence.get(player_id)
    survival = _survival_probability(static, player_id, next_pick_overall)

    reasons = [f"tier {tier}: {TIER_DESCRIPTIONS[tier]}"]
    future_mult = None
    feasibility_mult = None
    opp_cost = None
    opponent_mult = None

    if tier in V_TIERS:
        # N4 exactly, except that `vorp` is recomputed against a draft-aware replacement level.
        # V0 uses production's static level, so it reproduces N4 by construction.
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        opp_cost = _opportunity_cost_for(
            static,
            position,
            available,
            current_pick_overall,
            next_pick_overall,
            opportunity_costs,
        )
        msv = marginal_starter_value(
            league,
            roster_player_ids or [],
            player_id,
            static.projections,
            static.positions,
            base_points=base_lineup_points,
        )
        if dynamic_levels is None:
            vorp_term = vorp
        else:
            vorp_term = projection - dynamic_levels.get(position, level)
            reasons.append(
                f"draft-aware replacement {dynamic_levels.get(position, level):.1f} "
                f"(static {level:.1f}) -> vorp {vorp_term:+.1f} (static {vorp:+.1f})"
            )

        score = (msv + N4_VORP_WEIGHT * vorp_term + opp_cost) * fit_mult * risk_mult * survival_mult
        cap = positional_feasibility_cap(league, position)
        have = sum(1 for p in roster_positions if p == position)
        if have >= cap:
            feasibility_mult = OVER_CAP_VALUE_MULTIPLIER
            score *= feasibility_mult
            reasons.append(f"over_cap_mult (have {have} {position}, cap {cap})")
        reasons.append(f"marginal_starter_value={msv:+.1f} pts")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost,
            opponent_depletion_multiplier=None,
            marginal_starter_value=msv,
            score=score,
            reasons=reasons,
        )

    if tier in R_TIERS:
        # R-tiers share EVERY term with the shipped D63 engine; only the VORP surplus scaling
        # and the over-cap multiplier vary, so a difference is attributable to those two
        # mechanisms and nothing else. R0 reproduces the shipped engine exactly.
        apply_saturation, over_cap_multiplier = R_TIER_SPEC[tier]
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        opp_cost = _opportunity_cost_for(
            static,
            position,
            available,
            current_pick_overall,
            next_pick_overall,
            opportunity_costs,
        )
        msv = marginal_starter_value(
            league,
            roster_player_ids or [],
            player_id,
            static.projections,
            static.positions,
            base_points=base_lineup_points,
        )

        if apply_saturation:
            saturation = (saturation_factors or {}).get(position, 1.0)
            vorp_term = saturated_surplus(vorp, saturation)
            reasons.append(
                f"vorp {vorp:+.1f} x startable-saturation {saturation:.2f} -> {vorp_term:+.1f}"
            )
        else:
            vorp_term = vorp

        score = (msv + N4_VORP_WEIGHT * vorp_term + opp_cost) * fit_mult * risk_mult * survival_mult

        cap = positional_feasibility_cap(league, position)
        have = sum(1 for p in roster_positions if p == position)
        if have >= cap:
            feasibility_mult = over_cap_multiplier
            score *= feasibility_mult
            reasons.append(
                f"over_cap_mult={over_cap_multiplier:g} (have {have} {position}, cap {cap})"
            )

        reasons.append(f"marginal_starter_value={msv:+.1f} pts")
        if opp_cost:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost,
            opponent_depletion_multiplier=None,
            marginal_starter_value=msv,
            startable_saturation=(saturation_factors or {}).get(position, 1.0),
            score=score,
            reasons=reasons,
        )

    if tier in ALL_N_TIERS:
        # Every N-tier shares production's risk/survival/roster-fit/feasibility terms and the
        # D55 opportunity-cost replay. ONLY the value base varies (and, for the `x` variants,
        # whether the opportunity cost is added at all), so a difference between N-tiers is
        # attributable to the value base and nothing else.
        value_base_name, use_opportunity_cost = N_TIER_SPEC[tier]
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        opp_cost = (
            _opportunity_cost_for(
                static,
                position,
                available,
                current_pick_overall,
                next_pick_overall,
                opportunity_costs,
            )
            if use_opportunity_cost
            else 0.0
        )
        msv = marginal_starter_value(
            league,
            roster_player_ids or [],
            player_id,
            static.projections,
            static.positions,
            base_points=base_lineup_points,
        )

        if value_base_name == "msv":
            value_base = msv
        elif value_base_name == "vorp":
            value_base = vorp
        elif value_base_name == "min_vorp_msv":
            value_base = min(vorp, msv)
        elif value_base_name == "msv_over_replacement":
            # msv minus the msv a freely-available replacement-level body would add at the same
            # position -- see league/replacement.py::replacement_marginal_starter_values for why
            # that identity is the same thing as the lineup-difference definition.
            value_base = msv - (replacement_msv or {}).get(position, 0.0)
        else:  # msv_plus_weighted_vorp
            value_base = msv + N4_VORP_WEIGHT * vorp

        score = (value_base + opp_cost) * fit_mult * risk_mult * survival_mult

        cap = positional_feasibility_cap(league, position)
        have = sum(1 for p in roster_positions if p == position)
        if have >= cap:
            feasibility_mult = 0.1
            score *= feasibility_mult
            reasons.append(f"feasibility_mult=0.10 (already have {have} {position}, cap {cap})")

        reasons.append(f"value_base={value_base_name} {value_base:+.1f} pts")
        reasons.append(f"marginal_starter_value={msv:+.1f} pts")
        if opp_cost:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost if use_opportunity_cost else None,
            opponent_depletion_multiplier=None,
            marginal_starter_value=msv,
            score=score,
            reasons=reasons,
        )

    if tier in M_TIERS:
        # Every M-tier shares production's risk/survival/feasibility terms and the D55
        # opportunity-cost replay; only the value term and the roster multiplier vary, so a
        # difference between tiers is attributable to marginal starter value and nothing else.
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        opp_cost = _opportunity_cost_for(
            static,
            position,
            available,
            current_pick_overall,
            next_pick_overall,
            opportunity_costs,
        )
        msv = marginal_starter_value(
            league,
            roster_player_ids or [],
            player_id,
            static.projections,
            static.positions,
            base_points=base_lineup_points,
        )

        if tier == "M0":
            score = (vorp + opp_cost) * fit_mult * risk_mult * survival_mult
        elif tier == "M1":
            score = (vorp + opp_cost + msv) * fit_mult * risk_mult * survival_mult
        elif tier == "M2":
            msv_mult = marginal_starter_multiplier(msv, projection)
            score = (vorp + opp_cost) * msv_mult * risk_mult * survival_mult
            reasons.append(f"msv_mult={msv_mult:.2f} (marginal starter value {msv:+.1f})")
        else:  # M3
            score = (msv + opp_cost) * fit_mult * risk_mult * survival_mult

        cap = positional_feasibility_cap(league, position)
        have = sum(1 for p in roster_positions if p == position)
        if have >= cap:
            feasibility_mult = 0.1
            score *= feasibility_mult
            reasons.append(f"feasibility_mult=0.10 (already have {have} {position}, cap {cap})")

        reasons.append(f"marginal_starter_value={msv:+.1f} pts")
        if opp_cost:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost,
            opponent_depletion_multiplier=None,
            marginal_starter_value=msv,
            score=score,
            reasons=reasons,
        )

    if tier in P_TIERS:
        # Production's real scoring terms, reproduced against pre-loaded data (identical
        # formulas to league/draft.py, just without the per-candidate DB round-trips).
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        base_production = vorp * fit_mult * risk_mult * survival_mult

        opp_cost = 0.0
        if tier in ("P1", "P1b", "P1c", "P3"):
            opp_cost = _opportunity_cost_for(
                static,
                position,
                available,
                current_pick_overall,
                next_pick_overall,
                opportunity_costs,
            )

        if tier == "P0":
            score = base_production
        elif tier == "P1":
            score = base_production + opp_cost
        elif tier == "P1b":
            score = base_production + opp_cost * risk_mult
        else:  # P1c and P3 share the integrated form
            score = (vorp + opp_cost) * fit_mult * risk_mult * survival_mult

        if tier in ("P2", "P3"):
            cap = positional_feasibility_cap(league, position)
            have = sum(1 for p in roster_positions if p == position)
            if have >= cap:
                feasibility_mult = 0.1
                score *= feasibility_mult
                reasons.append(f"feasibility_mult=0.10 (already have {have} {position}, cap {cap})")

        opp_cost_pts = opp_cost if tier in ("P1", "P1b", "P1c", "P3") else None
        if opp_cost_pts is not None:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost_pts,
            opponent_depletion_multiplier=None,
            score=score,
            reasons=reasons,
        )

    if tier == "A":
        score = projection
    elif tier == "B":
        score = vorp * fit_mult
    elif tier in ("C", "D", "E", "F", "G"):
        scarcity_mult = 0.7 + 0.6 * scarcity_norm
        score = vorp * fit_mult * scarcity_mult
        reasons.append(f"scarcity_mult={scarcity_mult:.2f} (position scarcity {scarcity_raw:+.1f})")

        if tier in ("D", "E", "F", "G"):
            n_opponent_picks = (
                max(0, next_pick_overall - current_pick_overall - 1)
                if next_pick_overall is not None and current_pick_overall is not None
                else 0
            )
            if tier in ("D", "E", "F"):
                # Analytical approximation: expected fraction of this position's currently
                # -available depth that survives to my next pick, aggregated from the same
                # per-player Uniform(ecr_best, ecr_worst) model next_pick_survival_probability
                # already uses for one player at a time.
                pos_players = [p for p in (available or ()) if static.positions.get(p) == position]
                survivals = [
                    s
                    for p in pos_players
                    if (s := _survival_probability(static, p, next_pick_overall)) is not None
                ]
                expected_survival_rate = sum(survivals) / len(survivals) if survivals else 1.0
                # Less of a scarce position expected to survive -> larger boost, bounded the
                # same [0.7, 1.3] way as every other multiplier in this codebase for a
                # consistent scale across tiers.
                future_mult = 1.3 - 0.6 * expected_survival_rate
                score *= future_mult
                reasons.append(
                    f"future_scarcity_mult={future_mult:.2f} "
                    f"(expected {expected_survival_rate:.0%} of {position} pool survives "
                    f"{n_opponent_picks} opponent picks)"
                )
            else:  # tier G: literal opponent replay instead of the analytical approximation
                future_pool = _future_position_pool_after_market_consensus(
                    static, available or set(), position, n_opponent_picks
                )
                current_pool = sorted(
                    (p for p in (available or ()) if static.positions.get(p) == position),
                    key=lambda p: -static.projections.get(p, float("-inf")),
                )
                survives = player_id in future_pool or player_id not in current_pool
                opponent_mult = 1.0 if survives else 1.3
                score *= opponent_mult
                reasons.append(
                    f"opponent_depletion_mult={opponent_mult:.2f} "
                    f"(replayed {n_opponent_picks} real market-consensus opponent picks: "
                    f"{position} pool {len(current_pool)} -> {len(future_pool)})"
                )

        if tier in ("E", "F"):
            cap = positional_feasibility_cap(league, position)
            have = sum(1 for p in roster_positions if p == position)
            if have >= cap:
                feasibility_mult = 0.1
                score *= feasibility_mult
                reasons.append(
                    f"feasibility_mult=0.10 (already have {have} {position}, "
                    f"league-derived cap {cap})"
                )

        if tier == "F":
            # Explicit opportunity cost in points, not just a multiplier: value now minus the
            # expected value of the best-of-position replacement if I wait for my next pick.
            # Now delegates to the canonical `league/opportunity_cost.py` implementation (D55)
            # so the diagnostic tier and the production engine share one algorithm. That
            # implementation also clamps both sides at replacement level, which the original
            # tier-F code did not -- see the note in `_reproduce_tier_f_numbers` below.
            opp_cost = _opportunity_cost_for(
                static,
                position,
                available,
                current_pick_overall,
                next_pick_overall,
                opportunity_costs,
            )
            score += opp_cost
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
    else:
        raise ValueError(
            f"score_candidate does not handle tier {tier!r} directly (use tier H's "
            "recommend_draft_pick path instead)"
        )

    return CandidateScore(
        player_id=player_id,
        position=position,
        projection=projection,
        vorp=vorp,
        replacement_level=level,
        scarcity_raw=scarcity_raw,
        scarcity_norm=scarcity_norm,
        roster_need=need_score,
        fit_multiplier=fit_mult,
        confidence=confidence,
        survival_probability=survival,
        future_scarcity_multiplier=future_mult,
        feasibility_multiplier=feasibility_mult,
        opportunity_cost_pts=opp_cost,
        opponent_depletion_multiplier=opponent_mult,
        score=score,
        reasons=reasons,
    )


def _pick_by_tier(
    static: SeasonStatic,
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    available: set[str],
    roster_positions: list[str],
    tier: Tier,
    current_pick_overall: int | None,
    next_pick_overall: int | None,
    roster_player_ids: list[str] | None = None,
) -> tuple[str, list[CandidateScore]]:
    """Returns (chosen_player_id, every scored candidate sorted best-first) -- the ranked list
    is what a JSON trace needs to show runner-up reasoning, not just the winner."""
    if tier == "H":
        needs = roster_need(league, roster_positions)
        rec = recommend_draft_pick(
            con,
            league,
            season,
            roster_positions,
            available,
            next_pick_overall=next_pick_overall,
            top_n=20,
            current_pick_overall=current_pick_overall,
            # D60: real production now uses marginal starter value when it knows the
            # roster's actual players; tier H exists to mirror real production exactly, so
            # it must pass the same thing the official benchmark does.
            roster_player_ids=roster_player_ids,
        )
        scored = [
            CandidateScore(
                player_id=c.player_id,
                position=c.position,
                projection=static.projections.get(c.player_id, 0.0),
                vorp=c.vorp,
                replacement_level=static.replacement_levels.get(c.position, 0.0),
                scarcity_raw=static.scarcity_raw.get(c.position, 0.0),
                scarcity_norm=static.scarcity_norm.get(c.position, 0.5),
                roster_need=needs.get(c.position, 0.0),
                fit_multiplier=roster_fit_multiplier(needs.get(c.position, 0.0)),
                confidence=c.confidence,
                survival_probability=c.survival_probability,
                future_scarcity_multiplier=None,
                feasibility_multiplier=None,
                opportunity_cost_pts=None,
                opponent_depletion_multiplier=None,
                score=c.score,
                reasons=list(c.reasons),
            )
            for c in rec.candidates
        ]
        return rec.recommendation, scored

    # Opportunity cost is a property of the POSITION, not the candidate, so the opponent replay
    # is computed once per pick here and reused for every candidate -- not once per candidate
    # (which is what the original tier-F code did, and why it cost ~5.5s/draft). Correctness
    # note: this is not merely an optimization, it is the mechanism's actual shape; see
    # league/opportunity_cost.py's module docstring.
    # Marginal starter value compares each candidate against the CURRENT lineup, which does
    # not vary across candidates at one pick -- so it is computed once here rather than once
    # per candidate, the same optimization the opportunity-cost replay already uses below.
    # Startable saturation depends only on the CURRENT roster, not the candidate, so like the
    # opportunity-cost replay it is computed once per pick rather than once per candidate.
    saturation_factors: dict[str, float] | None = None
    if tier in R_TIERS and R_TIER_SPEC[tier][0]:
        saturation_factors = startable_saturation(league, roster_positions)

    # Draft-aware replacement depends only on the AVAILABLE pool, not the candidate, so it is
    # computed once per pick rather than once per candidate (D65).
    dynamic_levels: dict[str, float] | None = None
    if tier in V_TIERS and V_TIER_SPEC[tier] is not None:
        dynamic_levels = REPLACEMENT_VARIANTS[V_TIER_SPEC[tier]](
            league, available, static.projections, static.positions
        )

    base_lineup_points = None
    if tier in M_TIERS or tier in ALL_N_TIERS or tier in R_TIERS or tier in V_TIERS:
        base_lineup_points = best_lineup_points(
            league, roster_player_ids or [], static.projections, static.positions
        )

    # Tier N3's value base subtracts the marginal starter value a replacement-level body would
    # add. That depends only on the POSITION, not the candidate, so like the opportunity-cost
    # replay it is computed once per pick rather than once per candidate.
    replacement_msv: dict[str, float] | None = None
    if tier in ALL_N_TIERS and N_TIER_SPEC[tier][0] == "msv_over_replacement":
        replacement_msv = replacement_marginal_starter_values(
            league,
            roster_player_ids or [],
            static.projections,
            static.positions,
            static.replacement_levels,
            base_points=base_lineup_points,
        )

    tiers_using_opportunity_cost = (
        "P1",
        "P1b",
        "P1c",
        "P3",
        "F",
        *M_TIERS,
        *(t for t in ALL_N_TIERS if N_TIER_SPEC[t][1]),
        *R_TIERS,
        *V_TIERS,
    )
    opportunity_costs: dict[str, float] | None = None
    if tier in tiers_using_opportunity_cost:
        candidate_positions = {
            pos for p in available if (pos := static.positions.get(p)) is not None
        }
        opportunity_costs = positional_opportunity_cost(
            available,
            static.positions,
            static.vorp,
            static.market_rank,
            picks_until_next_turn(current_pick_overall, next_pick_overall),
            candidate_positions,
        )

    scored = []
    for player_id in available:
        s = score_candidate(
            static,
            player_id,
            league,
            roster_positions,
            tier,
            available=available,
            current_pick_overall=current_pick_overall,
            next_pick_overall=next_pick_overall,
            opportunity_costs=opportunity_costs,
            roster_player_ids=roster_player_ids,
            base_lineup_points=base_lineup_points,
            replacement_msv=replacement_msv,
            saturation_factors=saturation_factors,
            dynamic_levels=dynamic_levels,
        )
        if s is not None:
            scored.append(s)
    if not scored:
        raise RuntimeError(f"no evaluable candidates for tier {tier} at season {season}")
    if tier in R_TIERS_CAPACITY_TIEBREAK:
        # Exact 0.0 ties are genuinely exact here (0.0 * anything is 0.0), so this is a real
        # ordering rule rather than float-fragile. `player_id` remains the final key, so the
        # result stays deterministic across processes (D54).
        scored.sort(
            key=lambda s: (
                -s.score,
                -(s.startable_saturation if s.startable_saturation is not None else 0.0),
                -s.projection,
                s.player_id,
            )
        )
    else:
        scored.sort(key=lambda s: (-s.score, s.player_id))
    return scored[0].player_id, scored


@dataclass
class ForensicDraftResult:
    season: int
    tier: Tier
    draft_slot: int
    drafted_player_ids: list[str] = field(default_factory=list)
    drafted_positions: list[str] = field(default_factory=list)
    total_roster_points: float = 0.0
    starter_points: float = 0.0
    # D63 Stage 2: which opponent field this tier was measured against. Recorded on the
    # result rather than left implicit because the pre-D61 opponent forfeits mandatory
    # starting slots (D61), so a tier number is meaningless without knowing which opponent
    # produced it -- the same "label, never silently restate" rule D56 and D61 established.
    opponent_strategy: str = MARKET_CONSENSUS


def simulate_forensic_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    tier: Tier,
    draft_slot: int,
    static: SeasonStatic,
    *,
    trace: list[dict] | None = None,
    opponent_strategy: str = MARKET_CONSENSUS,
) -> ForensicDraftResult:
    """Same snake-draft loop, fixed 9-slot opponent field, and outcome scoring as
    evaluation/draft_simulation.py::simulate_draft -- the only thing that varies is how the
    team-in-question's own pick is scored (`tier`). If `trace` is given, every pick's full
    candidate ranking is appended to it (see `trace_draft` below for the JSON shape).

    `opponent_strategy` selects the fixed field, exactly as `simulate_draft` does (D61 Stage
    1.1): `market_consensus` reproduces every tier number published through D60, and
    `market_consensus_roster_aware` is the fair opponent that actually fields a legal lineup.
    It defaults to the former so a pre-D63 caller's numbers stay reproducible; every Stage 2+
    run passes the latter explicitly. Which one produced a result is recorded on the returned
    `ForensicDraftResult`, so a tier figure can never be read without its opponent."""
    if opponent_strategy not in ALL_OPPONENT_STRATEGIES:
        raise ValueError(f"unknown opponent strategy '{opponent_strategy}'")
    from alpha_squad.evaluation.draft_simulation import _actual_points_for
    from alpha_squad.league.replacement import compute_league_starters

    available = set(static.projections)
    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    drafted: list[str] = []
    my_roster_positions: list[str] = []
    # Per-opponent-slot roster, for the roster-aware field: roster awareness is a property of
    # each team, not of the league (D61 Stage 1.1).
    opponent_roster_positions: dict[int, list[str]] = {
        slot: [] for slot in range(1, league.teams + 1) if slot != draft_slot
    }

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        # Every slot picks exactly once per round in a snake draft, so this is exact for
        # every slot at this round.
        picks_remaining = total_rounds - round_no + 1
        for slot in order:
            if not available:
                break
            if slot == draft_slot:
                current_pick = _snake_overall_pick(round_no, slot, league.teams)
                next_pick = _next_pick_overall(round_no, slot, league.teams, total_rounds)
                pick, scored = _pick_by_tier(
                    static,
                    con,
                    league,
                    season,
                    available,
                    my_roster_positions,
                    tier,
                    current_pick,
                    next_pick,
                    roster_player_ids=drafted,
                )
                if trace is not None:
                    top = scored[0]
                    runner_up = scored[1] if len(scored) > 1 else None
                    trace.append(
                        {
                            "season": season,
                            "tier": tier,
                            "draft_slot": draft_slot,
                            "round": round_no,
                            "overall_pick": current_pick,
                            "roster_before_pick": list(my_roster_positions),
                            "n_candidates": len(scored),
                            "selected": _candidate_to_dict(top),
                            "runner_up": _candidate_to_dict(runner_up) if runner_up else None,
                            "score_gap_to_runner_up": (
                                top.score - runner_up.score if runner_up else None
                            ),
                            "top_5_candidates": [_candidate_to_dict(c) for c in scored[:5]],
                        }
                    )
                drafted.append(pick)
                my_roster_positions.append(static.positions.get(pick, "UNKNOWN"))
            else:
                if opponent_strategy == MARKET_CONSENSUS_ROSTER_AWARE:
                    pick = _market_consensus_roster_aware_pick(
                        available,
                        static.market_rank,
                        static.positions,
                        league,
                        opponent_roster_positions[slot],
                        picks_remaining,
                    )
                else:
                    pick = _market_consensus_pick(available, static.market_rank)
                opponent_roster_positions[slot].append(static.positions.get(pick, "UNKNOWN"))
            available.discard(pick)

    actual_points = _actual_points_for(con, season, drafted)
    total_points = sum(actual_points.values())
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        actual_points,
        {p: static.positions.get(p, "UNKNOWN") for p in drafted},
    )
    starter_points = sum(actual_points.get(p, 0.0) for p in starters["starters"])

    return ForensicDraftResult(
        season=season,
        tier=tier,
        draft_slot=draft_slot,
        drafted_player_ids=drafted,
        drafted_positions=my_roster_positions,
        total_roster_points=total_points,
        starter_points=starter_points,
        opponent_strategy=opponent_strategy,
    )


def _candidate_to_dict(c: CandidateScore) -> dict:
    return {
        "player_id": c.player_id,
        "position": c.position,
        "projection": round(c.projection, 2),
        "vorp": round(c.vorp, 2),
        "replacement_level": round(c.replacement_level, 2),
        "scarcity_raw": round(c.scarcity_raw, 2),
        "scarcity_norm": round(c.scarcity_norm, 3),
        "roster_need": round(c.roster_need, 3),
        "fit_multiplier": round(c.fit_multiplier, 3),
        "confidence": round(c.confidence, 3) if c.confidence is not None else None,
        "survival_probability": (
            round(c.survival_probability, 3) if c.survival_probability is not None else None
        ),
        "future_scarcity_multiplier": (
            round(c.future_scarcity_multiplier, 3)
            if c.future_scarcity_multiplier is not None
            else None
        ),
        "feasibility_multiplier": c.feasibility_multiplier,
        "marginal_starter_value": (
            round(c.marginal_starter_value, 2) if c.marginal_starter_value is not None else None
        ),
        "opportunity_cost_pts": (
            round(c.opportunity_cost_pts, 2) if c.opportunity_cost_pts is not None else None
        ),
        "opponent_depletion_multiplier": c.opponent_depletion_multiplier,
        "score": round(c.score, 3),
        "reasons": c.reasons,
    }


def homogeneous_league_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    strategy: Literal["market_consensus", "raw_value", "vorp"],
    static: SeasonStatic,
) -> dict[int, list[str]]:
    """Baseline sanity check (forensic directive section 14-15): draft ALL `league.teams`
    slots under the *same* homogeneous strategy -- not the 1-vs-9-market-consensus design used
    everywhere else in this codebase -- so a strategy's own roster realism can be inspected
    with no fixed-opponent confound at all. Returns {draft_slot: drafted_player_ids}.

    `market_consensus` here is a convenience re-derivation for a fully-homogeneous league;
    note this is mathematically identical to the ALREADY-COMPUTED market_consensus rows in
    draft_simulation_results (docs/DECISIONS.md D54), since every slot in that harness's
    market_consensus trials also faces 9 real market_consensus opponents -- see
    docs/DRAFT_CONTROLLED_EXPERIMENTS.md for why that existing data already answers "ADP/ECR
    vs itself" without a new run being required."""
    available = set(static.projections)
    total_rounds = int(league.roster.get("roster_size", 0))
    rosters: dict[int, list[str]] = {slot: [] for slot in range(1, league.teams + 1)}

    def pick_for(slot_available: set[str]) -> str:
        if strategy == "market_consensus":
            return _market_consensus_pick(slot_available, static.market_rank)
        if strategy == "raw_value":
            return max(slot_available, key=lambda p: (static.projections.get(p, float("-inf")), p))
        return max(slot_available, key=lambda p: (static.vorp.get(p, float("-inf")), p))  # "vorp"

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        for slot in order:
            if not available:
                break
            pick = pick_for(available)
            rosters[slot].append(pick)
            available.discard(pick)

    return rosters


def roster_feasibility_metrics(
    league: LeagueContext, drafted_positions: list[str]
) -> dict[str, object]:
    """Section 9 of the forensic directive: metrics for roster CONSTRUCTION, kept explicitly
    separate from fantasy VALUE (total/starter points, computed elsewhere). No arbitrary
    "looks normal" thresholds -- every bound here is derived from the league's own structural
    settings (dedicated_slots, bench_size), not picked to make a particular result look good
    or bad."""
    dedicated = league.dedicated_slots()
    counts: dict[str, int] = {}
    for pos in drafted_positions:
        counts[pos] = counts.get(pos, 0) + 1

    zero_drafted = [
        pos for pos, slots in dedicated.items() if slots > 0 and counts.get(pos, 0) == 0
    ]
    over_cap = {
        pos: counts.get(pos, 0)
        for pos in dedicated
        if counts.get(pos, 0) > positional_feasibility_cap(league, pos)
    }
    n_distinct = len([p for p in counts if counts[p] > 0])
    total_drafted = len(drafted_positions)

    return {
        "position_counts": counts,
        "starting_requirements": dedicated,
        "zero_drafted_starting_positions": zero_drafted,
        "positions_over_feasibility_cap": over_cap,
        "max_single_position_share": (
            max(counts.values()) / total_drafted if total_drafted else 0.0
        ),
        "n_distinct_positions_drafted": n_distinct,
        "concentration_index": (  # Herfindahl-style: sum of squared position shares, 1/n_pos
            # (even split) to 1.0 (one position only) -- a single scalar realism check.
            sum((c / total_drafted) ** 2 for c in counts.values()) if total_drafted else 0.0
        ),
    }


def first_round_by_position(drafted_positions: list[str]) -> dict[str, int]:
    """{position: 1-indexed round this team FIRST took that position}, for the positional
    -timing gate (Gate 4). The team in question picks exactly once per round, so a pick's
    index in `drafted_positions` is its round - 1 by construction.

    A position never drafted is simply absent rather than given a sentinel round: averaging a
    made-up number in would misreport timing. Callers aggregate over the drafts where the
    position actually appears and report that count alongside."""
    first: dict[str, int] = {}
    for i, pos in enumerate(drafted_positions):
        if pos not in first:
            first[pos] = i + 1
    return first


def run_tier_ablation(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    seasons: list[int],
    tiers: tuple[Tier, ...],
    slots: list[int] | None = None,
    *,
    opponent_strategy: str = MARKET_CONSENSUS,
) -> list[dict]:
    """One row per (season, tier, slot): the full ceteris-paribus grid.

    `load_season_static` is called once per season and shared across every tier and slot, so
    the only thing that varies within a season is the scoring mechanism -- which is what
    makes a difference between tiers attributable to the mechanism and nothing else.

    `opponent_strategy` picks the fixed opponent field and is recorded on every row (D63
    Stage 2), so an ablation table can never be read without knowing whether its opponent
    could field a legal lineup."""
    slots = slots if slots is not None else list(range(1, league.teams + 1))
    rows: list[dict] = []
    for season in seasons:
        static = load_season_static(con, league, season)
        for tier in tiers:
            for slot in slots:
                result = simulate_forensic_draft(
                    con,
                    league,
                    season,
                    tier,
                    slot,
                    static,
                    opponent_strategy=opponent_strategy,
                )
                feasibility = roster_feasibility_metrics(league, result.drafted_positions)
                rows.append(
                    {
                        "season": season,
                        "tier": tier,
                        "draft_slot": slot,
                        "opponent_strategy": result.opponent_strategy,
                        "starter_points": result.starter_points,
                        "total_roster_points": result.total_roster_points,
                        "drafted_positions": list(result.drafted_positions),
                        "first_round_by_position": first_round_by_position(
                            result.drafted_positions
                        ),
                        "position_counts": feasibility["position_counts"],
                        "zero_drafted_starting_positions": feasibility[
                            "zero_drafted_starting_positions"
                        ],
                        "positions_over_feasibility_cap": feasibility[
                            "positions_over_feasibility_cap"
                        ],
                        "max_single_position_share": feasibility["max_single_position_share"],
                    }
                )
    return rows


def summarize_tier_ablation(rows: list[dict], league: LeagueContext) -> list[dict]:
    """Per-tier aggregates, including every metric the pre-registered decision rules name.

    `zero_rate_by_position` is what Gate 1 is judged on; `mean_starter_points_by_season` is
    Gate 3's input; `mean_first_round_by_position` is Gate 4's (D63 Stage 2 -- both were
    uncomputable from the pre-D63 summary, which is why the D60 K/DST timing regression
    passed unnoticed). `late_round_position_counts` measures the failure mode the next-phase
    plan names explicitly: in the last third of the draft every startable slot is full, so an
    MSV-based value base collapses toward zero and picks fall to the opportunity-cost term
    and tie-breaks."""
    dedicated = league.dedicated_slots()
    total_rounds = int(league.roster.get("roster_size", 0))
    # "Late" = final third of the draft, derived from the league's own roster size rather
    # than a hardcoded round number, so it stays meaningful in a different format.
    late_round_start = total_rounds - max(1, total_rounds // 3) + 1

    by_tier: dict[str, list[dict]] = {}
    for row in rows:
        by_tier.setdefault(row["tier"], []).append(row)

    summary = []
    for tier, tier_rows in by_tier.items():
        n = len(tier_rows)
        starters = [r["starter_points"] for r in tier_rows]
        zero_rate = {
            pos: sum(1 for r in tier_rows if pos in r["zero_drafted_starting_positions"])
            for pos in dedicated
        }

        by_season: dict[int, list[float]] = {}
        for r in tier_rows:
            by_season.setdefault(r["season"], []).append(r["starter_points"])
        mean_by_season = {
            season: sum(vals) / len(vals) for season, vals in sorted(by_season.items())
        }

        # Mean first round per position, averaged only over the drafts that actually took
        # the position (see `first_round_by_position`), with that count reported alongside so
        # a timing figure drawn from few drafts is visibly weak rather than silently equal.
        first_rounds: dict[str, list[int]] = {}
        for r in tier_rows:
            for pos, rnd in r.get("first_round_by_position", {}).items():
                first_rounds.setdefault(pos, []).append(rnd)
        mean_first_round = {
            pos: sum(vals) / len(vals) for pos, vals in sorted(first_rounds.items())
        }
        n_drafts_with_position = {pos: len(vals) for pos, vals in sorted(first_rounds.items())}

        late_counts: dict[str, int] = {}
        for r in tier_rows:
            for i, pos in enumerate(r["drafted_positions"]):
                if i + 1 >= late_round_start:
                    late_counts[pos] = late_counts.get(pos, 0) + 1
        late_counts_per_draft = {pos: c / n for pos, c in sorted(late_counts.items())} if n else {}

        summary.append(
            {
                "tier": tier,
                "n": n,
                "opponent_strategy": tier_rows[0].get("opponent_strategy", MARKET_CONSENSUS),
                "mean_starter_points": sum(starters) / n if n else 0.0,
                "stdev_starter_points": _stdev(starters),
                "mean_total_roster_points": (
                    sum(r["total_roster_points"] for r in tier_rows) / n if n else 0.0
                ),
                "mean_starter_points_by_season": mean_by_season,
                "mean_first_round_by_position": mean_first_round,
                "n_drafts_with_position": n_drafts_with_position,
                "late_round_position_counts_per_draft": late_counts_per_draft,
                "zero_rate_by_position": zero_rate,
                "n_infeasible_rosters": sum(
                    1 for r in tier_rows if r["zero_drafted_starting_positions"]
                ),
                "mean_max_position_share": (
                    sum(r["max_single_position_share"] for r in tier_rows) / n if n else 0.0
                ),
            }
        )
    summary.sort(key=lambda r: -r["mean_starter_points"])
    return summary


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    mean = sum(xs) / len(xs)
    return (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def leave_one_season_out_margins(
    rows: list[dict], tier: str, control_tier: str
) -> dict[int, float]:
    """{excluded_season: `tier`'s mean-starter-point margin over `control_tier` with that
    season left out}.

    The next-phase plan's robustness requirement: a mechanism whose advantage disappears when
    any single season is removed is not shipped, regardless of the pooled mean. With only 5
    real seasons available, one outlier season can carry a pooled result on its own, and this
    is the check that makes that visible rather than assumed away."""
    seasons = sorted({r["season"] for r in rows})
    margins: dict[int, float] = {}
    for excluded in seasons:
        kept = [r for r in rows if r["season"] != excluded]
        tier_pts = [r["starter_points"] for r in kept if r["tier"] == tier]
        ctrl_pts = [r["starter_points"] for r in kept if r["tier"] == control_tier]
        if not tier_pts or not ctrl_pts:
            continue
        margins[excluded] = sum(tier_pts) / len(tier_pts) - sum(ctrl_pts) / len(ctrl_pts)
    return margins


def evaluate_preregistered_gates(
    summary: list[dict], rows: list[dict], control_tier: str
) -> list[dict]:
    """Apply the pre-registered decision rule to an ablation result, mechanically.

    Returns one row per non-control tier with each gate's pass/fail and the numbers behind
    it, so the ship/no-ship call is read off a table rather than argued after the fact. The
    rule itself is the module-level PREREGISTERED_* constants, committed to source before any
    run (D39/D54/D55 discipline)."""
    by_tier = {r["tier"]: r for r in summary}
    control = by_tier.get(control_tier)
    if control is None:
        raise ValueError(f"control tier {control_tier!r} not present in this ablation")

    verdicts = []
    for row in summary:
        tier = row["tier"]
        if tier == control_tier:
            continue

        beats_primary = row["mean_starter_points"] > control["mean_starter_points"]

        gate1_failures = {
            pos: (rate, control["zero_rate_by_position"].get(pos, 0))
            for pos, rate in row["zero_rate_by_position"].items()
            if rate > control["zero_rate_by_position"].get(pos, 0)
        }
        gate2_pass = row["n_infeasible_rosters"] <= control["n_infeasible_rosters"]

        worse_seasons = [
            season
            for season, pts in row["mean_starter_points_by_season"].items()
            if pts < control["mean_starter_points_by_season"].get(season, float("-inf"))
        ]
        gate3_pass = len(worse_seasons) <= PREREGISTERED_MAX_WORSE_SEASONS

        gate4_failures = {
            pos: (rnd, control["mean_first_round_by_position"][pos])
            for pos, rnd in row["mean_first_round_by_position"].items()
            if pos in control["mean_first_round_by_position"]
            and control["mean_first_round_by_position"][pos] - rnd
            > PREREGISTERED_MAX_ROUNDS_EARLIER
        }

        loso = leave_one_season_out_margins(rows, tier, control_tier)
        loso_survives = bool(loso) and all(m > 0 for m in loso.values())

        gates_pass = not gate1_failures and gate2_pass and gate3_pass and not gate4_failures
        verdicts.append(
            {
                "tier": tier,
                "margin_vs_control": row["mean_starter_points"] - control["mean_starter_points"],
                "beats_primary_metric": beats_primary,
                "gate1_pass": not gate1_failures,
                "gate1_failures": gate1_failures,
                "gate2_pass": gate2_pass,
                "gate3_pass": gate3_pass,
                "gate3_worse_seasons": worse_seasons,
                "gate4_pass": not gate4_failures,
                "gate4_failures": gate4_failures,
                "leave_one_season_out_margins": loso,
                "leave_one_season_out_survives": loso_survives,
                "ships": beats_primary and gates_pass and loso_survives,
            }
        )
    verdicts.sort(key=lambda v: -v["margin_vs_control"])
    return verdicts
