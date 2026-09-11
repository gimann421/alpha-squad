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

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

import duckdb

from alpha_squad.evaluation.decision_legality import (
    L_TIER_SPEC as DECISION_L_TIER_SPEC,
)
from alpha_squad.evaluation.decision_legality import (
    LEGALITY_TIERS as DECISION_LEGALITY_TIERS,
)
from alpha_squad.evaluation.decision_value_base import (
    ARM_VORP_WEIGHT as DECISION_ARM_VORP_WEIGHT,
)
from alpha_squad.evaluation.decision_value_base import (
    survival_multiplier as dvb_survival_multiplier,
)
from alpha_squad.evaluation.draft_simulation import (
    ALL_OPPONENT_STRATEGIES,
    MARKET_CONSENSUS,
    MARKET_CONSENSUS_ROSTER_AWARE,
    _market_consensus_pick,
    _market_consensus_roster_aware_pick,
    _next_pick_overall,
    _snake_overall_pick,
)
from alpha_squad.evaluation.projection_calibration import (
    X_ARMS,
    Arm,
    ResidualRow,
    apply_calibration,
    band_edges,
    fit_arm,
    load_residual_rows,
    season_demand,
)
from alpha_squad.evaluation.replacement_diagnostics import (
    REPLACEMENT_VARIANTS,
    SWEEP_SCALES,
    consumption_replacement,
    mock_draft_consumption_demand,
)
from alpha_squad.evaluation.weekly_objective import (
    expected_weekly_marginal_value,
    expected_weekly_starter_points,
    measure_availability_rates,
)
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
    unfilled_dedicated_slots,
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
    "VS1",
    "VS2",
    "VS3",
    "VS4",
    "VS5",
    "VS6",
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "X0",
    "X1",
    "X2",
    "X3",
    "X4",
    "Y1",
    "Z0",
    "Z1",
    "Z2",
    "Z3",
    "ZW0",
    "ZW05",
    "ZW2",
    "ZW3",
    "S0",
    "S1",
    "SS15",
    "SS60",
    "SS100",
    "Q0",
    "Q1",
    "Q2",
    "Q3",
    "L0",
    "L1",
    "L2",
    "L3",
    "O0",
    "O1",
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

# D66 Phase 4: one tier per demand-depth multiplier, for the sensitivity sweep. These are a
# stress test of the winning mechanism, NOT additional candidates -- the question they answer
# is whether performance sits on a broad stable plateau or a narrow spike (the latter would be
# evidence of overfitting and grounds for rejection).
SWEEP_TIERS: tuple[Tier, ...] = ("VS1", "VS2", "VS3", "VS4", "VS5", "VS6")

#: Every tier that uses the draft-aware-replacement scoring path (candidates + sweep).
ALL_V_TIERS: tuple[Tier, ...] = (*V_TIERS, *SWEEP_TIERS)

SWEEP_TIERS_SCALES = (("VS1", "VS2", "VS3", "VS4", "VS5", "VS6"), SWEEP_SCALES)

#: {tier: key into replacement_diagnostics.REPLACEMENT_VARIANTS, or None for the static control}
V_TIER_SPEC: dict[Tier, str | None] = {
    "V0": None,  # shipped N4: static, full-season replacement -- the control
    "VA": "available_pool",  # Candidate A
    "VB": "remaining_demand",  # Candidate B
    "VC": "hybrid_capacity",  # Candidate C
    "VD": "dedicated_plus_one_bench",  # Candidate C4 (D66)
    "VE": "earned_starter",  # Candidate C5 (D66)
    **{
        t: f"scale_{sc}" for t, sc in zip(SWEEP_TIERS_SCALES[0], SWEEP_TIERS_SCALES[1], strict=True)
    },
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

# --- D67: a structural rule for replacement depth, and legality as a separate mechanism -----
# D66 left `scale x2.5`/`x3.0` passing every gate but selected post-hoc off a 6-point sweep.
# D67's diagnostics found why the multiplier works, and it is not a reason to keep it:
#
#   Deepening demand is arithmetically identical to adding a FIXED BONUS to every player at a
#   position, and the bonus size is set by the shape of that position's projection tail. At
#   x2.5, measured on real 2021-2025 data: RB +120.4, QB +108.9, TE +106.4, WR +92.0, but
#   K +30.4 and DST +10.7. K hoarding vanished not because K was priced right but because
#   everyone else got ~100 points and K got 30 -- an artifact of there being 225 WRs and 32
#   DSTs. That is a positional re-weighting in disguise.
#
# Two further measurements shape this phase:
#
#   * A real 160-pick draft consumes QB 20.4 / RB 46.4 / WR 56.4 / TE 16.8 / K 10 / DST 10.
#     `startable_slots` (QB 1, RB 4, WR 4, TE 3, K 1, DST 1 per team) is wrong in SHAPE -- it
#     under-counts QB 2x and over-counts TE 1.8x -- so no uniform multiplier can repair it.
#     Pool-clamping never occurs at any scale up to x3.0 (0/800 real pick-states); demand
#     EXHAUSTION is the only binding constraint, and QB is what forces the scale past 2.5.
#   * The engine has NO hard roster-legality constraint. `alpha_bpa` finishes 50/50 drafts with
#     a mean 6.48 unfilled mandatory starting slots and nothing raises. `alpha_league_aware`'s
#     current 0.00 is bought entirely by the static-replacement defect pricing a kicker at +30
#     to +50 VORP all draft -- so changing depth puts legality at risk, and padding depth to
#     keep K "valuable" would be solving a legality problem with a valuation knob.
#
# W1's demand target is therefore the classic VBD definition made literal (replacement level is
# the best player who will still be undrafted when the draft ends), computed by
# `replacement_diagnostics.mock_draft_consumption_demand`. It has NO free parameter.
# W2/W3 add the endgame mandatory-slot reservation the fair opponent already uses
# (`_market_consensus_roster_aware_pick`), which triggers only at the last possible pick and
# only while a slot is still empty -- this is not "force a kicker in round 14", and it is what
# lets depth be set on valuation grounds alone.
W_TIERS: tuple[Tier, ...] = ("W0", "W1", "W2", "W3", "W4")

#: {tier: (demand target, enforce endgame mandatory-slot legality)}. `None` target = static
#: replacement, exactly as shipped N4. `"scale_2.5"` is D66's uniform multiplier, unchanged, so
#: the correctly-shaped target is measured against it like-for-like rather than in isolation.
W_TIER_SPEC: dict[Tier, tuple[str | None, bool]] = {
    "W0": (None, False),  # control: shipped N4, static replacement, no legality constraint
    "W1": ("consumption", False),  # the structural rule alone
    "W2": ("consumption", True),  # the structural rule + legality
    "W3": (None, True),  # legality ALONE -- isolates it from any depth change
    "W4": ("scale_2.5", False),  # reference: D66's uniform x2.5, unchanged
}

# PRE-REGISTERED DECISION RULE for the W-tiers -- committed to source BEFORE any W-tier ran
# against real data, same discipline as the N-, R- and V-tiers above.
#
#   Control        : W0 (= shipped N4, static replacement), fair opponent, production caps.
#   Primary metric : mean realized starter points vs. the fair opponent, 95% CI excluding 0.
#   Gates 1-4      : unchanged, reused verbatim via `evaluate_preregistered_gates`
#                    (zero-rate, infeasibility, <=1 season worse, positional timing <=2 rounds).
#   Gate 5         : must not increase cap breaches at any position vs. the control (D64).
#   Gate 6         : leave-one-season-out positive on all five held-out seasons.
#   Gate 7         : rerun unchanged on `legacy_2qb_dynasty`; report the sign either way.
#   Ship           : the LOWEST-NUMBERED tier clearing every gate. If W3 alone clears them,
#                    legality was the whole story and no depth change ships. If nothing clears
#                    them, production stays N4 and this phase reports that.
#
# Recorded before running so the outcome cannot be reinterpreted afterwards: it is entirely
# possible that W4's crude ~+100-point skill-position bonus is doing real work -- acting as a
# proxy for "skill players are worth more than the lineup math says" -- that a correctly shaped
# target does not reproduce. W4 is in the run precisely so that is measured rather than assumed,
# and W1/W2 losing to it is a publishable result, not a reason to re-tune.
#
# Explicitly NOT goals, and not grounds to ship anything: fewer kickers, a lower TE count, a
# demand target that sums to a satisfying number. Starter points first; roster feasibility is a
# gate, never the objective.
PREREGISTERED_W_CONTROL: Tier = "W0"

# --------------------------------------------------------------------------------------------
# D68 -- projection calibration. The DRAFT ENGINE IS A CONSTANT HERE.
#
# Every X-tier scores exactly as W1 does -- the engine shipped at D67, `msv + 1.0 x
# draft-aware VORP` at the mock-draft consumption boundary. No X-tier adds a scoring term, a
# scarcity term, a depth or replacement multiplier, a positional cap, a round-specific rule or
# an RB bonus. The ONLY thing that differs between X-tiers is the projection input, applied at
# a single point in `load_season_static` before any value is derived from it, so that MSV,
# static VORP, replacement levels, scarcity and the D67 demand boundary all see one consistent
# set of numbers.
#
# X0 is therefore byte-identical to W1 by construction, and a test asserts it. If it ever
# diverges, the comparison is measuring the harness rather than the calibration.
#
# The arms, estimators, evidence prior and gates live in `evaluation/projection_calibration.py`
# and were committed before any of them were fitted against real data.
X_TIERS: tuple[Tier, ...] = ("X0", "X1", "X2", "X3", "X4")

#: {tier: calibration arm}. One-to-one; the indirection exists so the arm definitions stay in
#: the calibration module and the harness only has to know which arm a tier draws its
#: projections from.
X_TIER_SPEC: dict[Tier, Arm] = {tier: arm for tier, arm in zip(X_TIERS, X_ARMS, strict=True)}

PREREGISTERED_X_CONTROL: Tier = "X0"

# --------------------------------------------------------------------------------------------
# D70 -- RB availability (docs/RB_AVAILABILITY_PREREGISTRATION.md). Same reused scoring branch
# as the X-tiers (below): Y1 differs from the X0 control ONLY in `static.projections`, which
# `evaluation/rb_availability_experiment.py::rb_availability_static` builds by replacing RB
# entries in the control board with a walk-forward availability-feature refit -- QB/WR/TE/K/DST
# are untouched. Y1 is a SEPARATE letter from the X-tiers deliberately: D68 pre-registered X0-X4
# as a closed set of residual-calibration arms ("no sixth arm"), and this is a different kind of
# treatment (a model refit, not a residual correction), not a violation of that closure.
#
# Per the pre-registration, Y1 must not be measured at the draft layer unless the projection
# layer (`rb_availability_experiment.py::evaluate_projection_layer`, gates B1-B3) has already
# passed -- that ordering lives in which functions a caller invokes, the same way it did for D68.
Y_TIERS: tuple[Tier, ...] = ("Y1",)

PREREGISTERED_Y_CONTROL: Tier = "X0"


# --------------------------------------------------------------------------------------------
# D79 -- the VALUE BASE, re-measured on top of D67's draft-aware replacement level.
#
# WHY THIS IS NOT A RE-RUN OF D63. The N-tier ablation that selected `msv + 1.0*VORP` was run
# against the STATIC, full-season replacement level. D65 then measured that level to be wrong by
# +178.2 (QB) and +69.1 (WR) at round 13, and D64 traced N4's kicker hoarding to the same cause:
# after round 11 MSV is 0.0 for every candidate, the value base collapses to VORP alone, and a
# STATIC VORP systematically prefers kickers because ten teams strip the skill pools while barely
# touching K. That is a defect of the static level, and D67 removed it.
#
# So D63's central finding -- "summing the two signals wins; choosing between them per-candidate
# loses" -- was measured under conditions where one of the two signals was known to be defective
# in exactly the regime (rounds 11-16) where it governed the pick alone. The bases that lean
# HARDER on VORP (N1 `vorp`, N3 `msv over replacement`) were the ones most exposed to that
# defect, and they are the two that lost. Neither has been re-measured since D67 fixed it.
#
# WHAT MOTIVATED RE-OPENING IT (docs/DRAFT_DECISION_ENGINE_INVESTIGATION.md §3). Ranking the real
# 2021-2025 board by each layer of the production score and comparing the top-24 positional
# composition against a hindsight answer key (realized points over the REALIZED demand-boundary
# replacement level) shows the draft-aware VORP transform alone is the layer closest to the key
# (QB 23 vs the key's 23; RB 30), and that adding `msv` moves it AWAY (RB 30 -> 16, QB 23 -> 49).
# The reason is arithmetic, not incidental: on an empty roster `marginal_starter_value` is
# identically the candidate's own projection, so early in a draft the shipped value base is
# `2*projection - replacement` -- raw points at double weight, scarcity at single weight -- and
# `msv` contributes no roster information at all until slots start filling.
#
# THE HONEST BAR. D71 established that this benchmark's true experimental unit is the SEASON
# (ICC 0.0995, design effect 1.90, F(9,36)=0.54 for slot), giving a minimum detectable effect of
# ~128 starter points at n=5 seasons. D63's own margins (+48.6 over N3, +62.6 over N1) sit below
# that, quoted with naive i.i.d. intervals -- so the incumbent value base is not ESTABLISHED to
# beat the alternatives it beat, it merely won an underpowered comparison. That cuts both ways,
# and Gate 8 below is what stops this phase from repeating the error in the other direction.
Z_TIERS: tuple[Tier, ...] = ("Z0", "Z1", "Z2", "Z3")

# A labelled SENSITIVITY SWEEP on the VORP weight `w` in `msv + w*daVORP`, following the D66/D67
# precedent. These are a stress test of the incumbent's shape, NOT candidates: selecting a `w`
# post-hoc off a sweep is exactly what D67 rejected about D66's uniform x2.5, and no ZW tier may
# ship whatever it scores. What they answer is whether performance sits on a broad plateau in `w`
# (evidence the exact weight does not matter) or a narrow spike at 1.0 (evidence it was lucky).
# w = 1.0 is Z0 itself and is not repeated here.
Z_SWEEP_TIERS: tuple[Tier, ...] = ("ZW0", "ZW05", "ZW2", "ZW3")

ALL_Z_TIERS: tuple[Tier, ...] = (*Z_TIERS, *Z_SWEEP_TIERS)

#: {tier: (value base, VORP weight)}. Every Z-tier measures its surplus term against D67's
#: draft-aware demand-boundary replacement level -- that is the whole point of the phase -- and
#: shares every other term (opportunity cost, roster fit, confidence, survival, feasibility cap)
#: with the shipped engine, so a difference between Z-tiers is attributable to the value base and
#: nothing else. `Z0` is the shipped engine and is byte-identical to `X0`/`W1` by construction; a
#: test asserts it, exactly as D68 asserted X0 == W1.
Z_TIER_SPEC: dict[Tier, tuple[str, float]] = {
    "Z0": ("msv_plus_weighted_vorp", 1.0),  # control: the shipped D63/D67 engine
    "Z1": ("vorp", 0.0),  # pure draft-aware VBD (N1, re-measured)
    "Z2": ("msv_over_replacement", 0.0),  # the principled unification (N3, re-measured)
    "Z3": ("min_vorp_msv", 0.0),  # clamp (N2, re-measured)
    "ZW0": ("msv_plus_weighted_vorp", 0.0),  # sweep: msv alone (N0, re-measured)
    "ZW05": ("msv_plus_weighted_vorp", 0.5),
    "ZW2": ("msv_plus_weighted_vorp", 2.0),
    "ZW3": ("msv_plus_weighted_vorp", 3.0),
}

# PRE-REGISTERED DECISION RULE for the Z-tiers -- committed to source BEFORE any Z-tier was run
# against real data, same discipline as the N-, R-, V-, W- and X-tiers above.
#
#   Control        : Z0 (= the shipped engine: msv + 1.0*daVORP + opp_cost), fair opponent
#                    (`market_consensus_roster_aware`), production's real feasibility caps.
#   Primary metric : mean realized starter points vs the fair opponent.
#   Gates 1-4      : unchanged, reused VERBATIM via `evaluate_preregistered_gates`
#                    (zero-rate by position, roster infeasibility, <=1 season worse than control,
#                    no position drafted >2 rounds earlier than control).
#   Gate 5         : must not increase cap breaches at any position vs the control (D64).
#   Gate 6         : leave-one-season-out -- the margin must survive removing ANY single season.
#   Gate 7         : rerun unchanged on `legacy_2qb_dynasty`; report the sign either way. A value
#                    base that only helps in the target format is a format artifact, not a fix.
#   Gate 8 (NEW)   : the SEASON-CLUSTERED 95% CI must exclude zero -- paired per-slot differences
#                    against the control, averaged within season, then a t-interval on the 5
#                    season means (df=4). This is D71's correction, and it is the gate that makes
#                    this phase honest: the naive n=50 i.i.d. interval every prior phase quoted is
#                    anticonservative, and using it here would let this phase ship on exactly the
#                    kind of margin D71 showed the instrument cannot resolve.
#   Ship           : the LOWEST-NUMBERED Z-tier clearing EVERY gate. If none clears them,
#                    production's value base stays as it is and this phase reports that.
#   Never ships    : any ZW sweep tier, whatever it scores (see above).
#
# Recorded before running so the outcome cannot be reinterpreted afterwards. Two results are
# explicitly anticipated and are NOT grounds for re-tuning:
#   * A Z-tier wins the pooled mean but fails Gate 8. That is the expected outcome given D71's
#     power analysis, and the correct response is to report an unresolvable difference and ship
#     nothing -- not to fall back to the naive interval.
#   * Z0 wins outright. That would be positive evidence for the incumbent that D63 never had,
#     since D63 measured it under a replacement level since shown to be defective.
#
# Explicitly NOT goals, and not grounds to ship anything: more running backs, fewer quarterbacks,
# a board that agrees with consensus, or a top-24 composition closer to the hindsight key. The
# composition analysis is what generated the hypothesis; realized starter points is what tests it.
PREREGISTERED_Z_CONTROL: Tier = "Z0"


# --------------------------------------------------------------------------------------------
# D79 phase 2 -- the SURVIVAL multiplier, the one term in the production score that no phase has
# ever measured.
#
#   survival_mult = 1.0 + SURVIVAL_BONUS * (1 - P(this player lasts to my next pick))
#
# with `SURVIVAL_BONUS = 0.3` as a bare literal in `league/draft.py`, present since M10 and never
# ablated, swept or justified in any decision entry. Every other term in the score has been
# measured against an alternative: the value base by D63 and again by the Z-tiers, the replacement
# level by D65/D66/D67, the opportunity-cost term by D55 and re-measured by D63, the over-cap
# multiplier by D64, roster fit and the feasibility cap by D55's P-tiers. This one has not.
#
# WHY IT MATTERS ENOUGH TO MEASURE. It is MULTIPLICATIVE on the whole score, so its effect scales
# with the candidate's total value rather than with what is actually at stake in losing him: a
# 1.3x bonus is worth ~+150 points to a 500-point candidate and ~+30 to a 100-point one. In a
# controlled test (`tests/unit/test_draft_decision_behaviour.py`) it reverses an 81-point
# surplus gap on its own -- a larger swing than ANY value-base change the Z-tiers measured.
#
# There is also a design tension worth stating: D55 introduced the POSITIONAL opportunity-cost
# term precisely because single-player survival is the wrong instrument for positional scarcity
# ("will THIS player be there" is not "will a player THIS GOOD AT THIS POSITION be there" --
# docs/DRAFT_ENGINE_FORENSIC_AUDIT.md §6). That term is additive and denominated in real VORP
# points. The single-player term it was meant to supplement is multiplicative and unbounded by
# anything at stake, and is the larger of the two in practice.
#
# NOT A CLAIM THAT IT IS WRONG. The controlled tests show it behaving sensibly -- it correctly
# defers a scarce player who will still be on the board next turn, which is real draft skill. The
# claim is only that 0.3 was never chosen by evidence, and a term this large should be.
S_TIERS: tuple[Tier, ...] = ("S0", "S1")

#: Labelled sensitivity sweep, never ships -- same rule and same reason as `Z_SWEEP_TIERS`.
#: 0.3 is S0 itself and is not repeated here.
S_SWEEP_TIERS: tuple[Tier, ...] = ("SS15", "SS60", "SS100")

ALL_S_TIERS: tuple[Tier, ...] = (*S_TIERS, *S_SWEEP_TIERS)

#: {tier: survival bonus coefficient}. Everything else -- value base, draft-aware replacement,
#: opportunity cost, roster fit, confidence, feasibility cap -- is the shipped engine, so a
#: difference between S-tiers is attributable to this coefficient and nothing else. `S0` carries
#: the shipped 0.3 and is therefore byte-identical to `Z0`/`X0`/`W1`; a test asserts it.
S_TIER_SPEC: dict[Tier, float] = {
    "S0": 0.3,  # control: the shipped engine
    "S1": 0.0,  # the term switched OFF -- the parameter-free candidate
    "SS15": 0.15,
    "SS60": 0.6,
    "SS100": 1.0,
}

# PRE-REGISTERED DECISION RULE for the S-tiers -- committed to source BEFORE any S-tier was run
# against real data, same discipline and the SAME gates as the Z-tiers (Gates 1-8, including
# D71's season-clustered Gate 8 and the `legacy_2qb_dynasty` cross-format Gate 7).
#
#   Control        : S0 (= the shipped engine), fair opponent, production's real caps.
#   Primary metric : mean realized starter points vs the fair opponent.
#   Ship           : the LOWEST-NUMBERED S-tier clearing every gate. Only S1 is a candidate, and
#                    it is the parameter-free one (remove the term). If S1 does not clear them,
#                    the term stays exactly as shipped.
#   Never ships    : any SS sweep tier, whatever it scores. Selecting a coefficient post-hoc off
#                    a sweep is what D67 rejected about D66's uniform x2.5, and it would replace
#                    an unmeasured constant with a fitted one -- strictly worse, since a fitted
#                    constant carries an overfitting claim an unmeasured one does not.
#
# Anticipated and NOT grounds for re-tuning: S0 wins and the sweep shows a broad plateau. That is
# positive evidence for a constant that currently has none, and the correct outcome is to record
# it and change nothing. The sweep exists to distinguish "0.3 is fine anywhere in a wide range"
# from "0.3 happens to sit on a spike", which are very different states of knowledge about a
# number nobody chose deliberately.
PREREGISTERED_S_CONTROL: Tier = "S0"


# --- Q-tiers (D84): the two decision-layer axes nothing has varied ---------------------------
# Arms, rationale, gates and selection rule are PRE-REGISTERED in
# `evaluation/decision_value_base.py`, committed before any Q-tier was run. This dict is only
# the wiring; the science lives there.
#
#   Q0 = arm A, the shipped engine (control; asserted byte-identical to Z0/S0/X0/W1 by a test)
#   Q1 = arm C, msv_over_replacement + 1.0*daVORP -- removes the raw-projection double count
#        while HOLDING the value base's scale, which no prior arm did
#   Q2 = arm D, symmetric survival, so a player certain to still be there can be worth less now
#   Q3 = arm E, both
#
# Everything else -- draft-aware replacement, opportunity cost, roster fit, confidence,
# feasibility cap -- is the shipped engine, so a difference between Q-tiers is attributable to
# these two factors and nothing else.
Q_TIERS: tuple[Tier, ...] = ("Q0", "Q1", "Q2", "Q3")

#: {tier: (value base name, symmetric survival)} -- mirrors `decision_value_base.ARM_SPEC`, and a
#: test asserts the two agree so the wiring cannot drift from the pre-registration.
Q_TIER_SPEC: dict[Tier, tuple[str, bool]] = {
    "Q0": ("msv_plus_weighted_vorp", False),
    "Q1": ("msv_over_replacement_plus_weighted_vorp", False),
    "Q2": ("msv_plus_weighted_vorp", True),
    "Q3": ("msv_over_replacement_plus_weighted_vorp", True),
}

PREREGISTERED_Q_CONTROL: Tier = "Q0"


# --- L-tiers (D85): economic valuation and roster legality, separated --------------------------
# Arms, rationale, gates, selection rule and PREDICTED OUTCOMES are pre-registered in
# `evaluation/decision_legality.py`, committed before any L-tier was run. This block is only the
# wiring; the science lives there.
#
# D84 proved the engine uses ONE mechanism -- a value base it can prove is wrong -- to do TWO
# jobs: price players, and guarantee a legal roster. Its arm C removed the double count and
# broke roster legality (2 infeasible rosters vs the control's 0), because the over-valuation is
# what was dragging mandatory positions onto the roster at all. D85 is the 2x2 that separates
# them:
#
#                     legality OFF     legality ON
#   Y1 valuation          L0               L1
#   arm C valuation       L2               L3
#
# L0 == Q0 == Z0 == S0 == X0 == W1 (a test asserts it), and L2 == Q1, so D85's numbers land on
# exactly the instrument D84 published. The legality constraint is D67's W2/W3 rule verbatim,
# applied in `_pick_by_tier` -- it restricts which candidates are ELIGIBLE and never touches any
# candidate's value.
L_TIERS: tuple[Tier, ...] = DECISION_LEGALITY_TIERS

#: {tier: (value base name, enforce endgame mandatory-slot legality)} -- mirrors
#: `decision_legality.L_TIER_SPEC`, and a test asserts the two agree so the wiring cannot drift
#: from the pre-registration.
L_TIER_SPEC: dict[Tier, tuple[str, bool]] = dict(DECISION_L_TIER_SPEC)

PREREGISTERED_L_CONTROL: Tier = "L0"


# --- O-tiers (D86): the OBJECTIVE, not the value base --------------------------------------
# Arms, metrics, gates, selection rule and predictions Q1-Q6 are pre-registered in
# `evaluation/objective_candidates.py`, committed before any O-tier ran. This block is wiring.
#
# D85 closed the value-base seam: nine reformulations of `value_base`, all failed, and the slope
# problem is structural. So these tiers change NOTHING about the value base's algebra -- they
# change what its marginal-value half is an expectation OF. `marginal_starter_value` assumes
# every rostered player plays every week, which is why it equals `proj` at an empty slot and
# exactly `0` at a saturated one. `expected_weekly_marginal_value` computes the same quantity
# under MEASURED per-position availability, so a bench player is worth what the data says he is
# worth and no bench bonus exists anywhere.
#
#   O0 = control, the shipped engine (asserted identical to L0/Q0/Z0)
#   O1 = E[weekly msv] + 1.0*daVORP; daVORP, opportunity cost, roster fit, confidence, survival
#        and the feasibility cap are all UNCHANGED
O_TIERS: tuple[Tier, ...] = ("O0", "O1")

#: {tier: use availability-aware marginal value}
O_TIER_SPEC: dict[Tier, bool] = {"O0": False, "O1": True}

PREREGISTERED_O_CONTROL: Tier = "O0"

#: Every tier scored as "N4, except VORP may use a draft-aware replacement level". V- and
#: W-tiers share the scoring branch verbatim so a difference between them is attributable to the
#: demand target (and, for W2/W3, the legality constraint) and nothing else.
DRAFT_AWARE_REPLACEMENT_TIERS: tuple[Tier, ...] = (
    *ALL_V_TIERS,
    *W_TIERS,
    *X_TIERS,
    *Y_TIERS,
    *ALL_Z_TIERS,
    *ALL_S_TIERS,
    *Q_TIERS,
    *L_TIERS,
    *O_TIERS,
)

#: Tiers that enforce the endgame mandatory-slot reservation, as a hard restriction on the
#: candidate pool rather than a score adjustment -- roster legality is a constraint, not a value.
#: D67's W2/W3 and D85's L1/L3 apply the identical rule; keeping them in one tuple is what makes
#: "the constraint is unchanged from its prototype" a property of the code rather than a claim.
TIERS_ENFORCING_LEGALITY: tuple[Tier, ...] = (
    *(t for t, (_, legality) in W_TIER_SPEC.items() if legality),
    *(t for t, (_, legality) in L_TIER_SPEC.items() if legality),
)

#: Back-compat alias: D67 named this `W_TIERS_ENFORCING_LEGALITY` and existing tests import it.
W_TIERS_ENFORCING_LEGALITY: tuple[Tier, ...] = tuple(
    t for t, (_, legality) in W_TIER_SPEC.items() if legality
)


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
    **{
        t: f"D66 sensitivity sweep: demand = {sc}x startable_slots"
        for t, sc in zip(SWEEP_TIERS_SCALES[0], SWEEP_TIERS_SCALES[1], strict=True)
    },
    "W0": "D67 control: shipped N4, static replacement, no roster-legality constraint",
    "W1": "D67: replacement at the demand a full mock draft of this league actually CONSUMES "
    "(mock_draft_consumption_demand) -- no free parameter",
    "W2": "D67: W1 plus the endgame mandatory-slot reservation (roster legality as a hard "
    "constraint, separate from valuation)",
    "W3": "D67: the endgame mandatory-slot reservation ALONE, on static replacement -- isolates "
    "legality from any depth change",
    "W4": "D67 reference: D66's uniform 2.5x startable_slots demand, unchanged",
    "X0": "D68 control: the shipped W1 engine on uncalibrated projections",
    "X1": "D68: W1 on projections with a walk-forward position-specific ADDITIVE correction",
    "X2": "D68: W1 on projections with a walk-forward position-specific AFFINE (slope) correction",
    "X3": "D68: W1 on projections with a walk-forward RANK-BAND additive correction, bands "
    "derived from the league's own draft consumption",
    "X4": "D68: W1 on projections with the additive correction SHRUNK toward zero by empirical "
    "Bayes when the evidence is weak",
    "Y1": "D70: W1 with RB projections from a walk-forward refit adding preseason-knowable "
    "availability features (F1-F4); QB/WR/TE/K/DST unchanged from control",
    # Z-tiers (D79): D67's draft-aware replacement held FIXED, only the value base varies.
    "O0": "D86 control: the shipped Y1 engine. Byte-identical to L0/Q0/Z0",
    "O1": "D86: availability-aware marginal value (E[weekly msv]) + 1.0*daVORP",
    "L0": "D85 control: the shipped Y1 engine, no legality constraint. Byte-identical to Q0/Z0",
    "L1": "D85: endgame mandatory-slot legality constraint ALONE, on the shipped valuation",
    "L2": "D85: arm C valuation ALONE (msv_over_replacement + 1.0*daVORP) -- reproduces Q1",
    "L3": "D85: arm C valuation PLUS the legality constraint -- the joint arm",
    "Q0": "D84 control (arm A): the shipped engine. Byte-identical to Z0/S0/X0/W1",
    "Q1": "D84 arm C: value base = msv_over_replacement + 1.0*daVORP -- removes the "
    "raw-projection double count while HOLDING the value base's scale",
    "Q2": "D84 arm D: shipped value base, symmetric survival multiplier in [0.7, 1.3] so a "
    "player certain to still be available can be worth less now than later",
    "Q3": "D84 arm E: arm C + arm D",
    "Z0": "D79 control: the shipped engine -- msv + 1.0*daVORP + opp_cost. Byte-identical to "
    "X0/W1 by construction",
    "Z1": "D79: value base = daVORP alone -- pure value-based drafting at the shipped "
    "draft-aware replacement level (N1, re-measured now that the level is no longer static)",
    "Z2": "D79: value base = marginal starter value OVER the DRAFT-AWARE replacement level. "
    "Reduces to daVORP on an empty roster and to 0 at a saturated position, by construction "
    "(N3, re-measured)",
    "Z3": "D79: value base = min(daVORP, msv) (N2, re-measured)",
    "ZW0": "D79 sweep (never ships): msv alone, w=0 (N0, re-measured)",
    "ZW05": "D79 sweep (never ships): msv + 0.5*daVORP",
    "ZW2": "D79 sweep (never ships): msv + 2.0*daVORP",
    "ZW3": "D79 sweep (never ships): msv + 3.0*daVORP",
    # S-tiers (D79 phase 2): the shipped engine throughout, only the survival coefficient varies.
    "S0": "D79 control: the shipped engine, survival bonus 0.3. Byte-identical to Z0/X0/W1",
    "S1": "D79: the single-player survival multiplier switched OFF (bonus 0.0) -- the "
    "parameter-free candidate",
    "SS15": "D79 sweep (never ships): survival bonus 0.15",
    "SS60": "D79 sweep (never ships): survival bonus 0.6",
    "SS100": "D79 sweep (never ships): survival bonus 1.0",
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
    # D67: {position: players at that position a full draft of this league consumes, per team}.
    # Loaded here rather than per pick because it depends only on the season's consensus board,
    # exactly like `market_rank` and `vorp` -- computing it per pick would run a whole mock draft
    # 160 times per draft. Diagnostic only; the W-tiers are its sole consumer.
    consumption_demand: dict[str, float] = field(default_factory=dict)
    # D86: {position: fraction of fantasy weeks a draftable player was available}, measured on
    # seasons STRICTLY BEFORE `season` -- walk-forward by construction, so an O-tier draft for
    # 2024 cannot see 2024's injuries. Empty for seasons with no prior data; the O1 tier raises
    # rather than defaulting, so an empty dict fails loudly instead of silently becoming O0.
    availability_rates: dict[str, float] = field(default_factory=dict)


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return dict.fromkeys(values, 0.5)
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def preseason_page_type(con: duckdb.DuckDBPyConnection, ecr_type: str, season: int) -> str | None:
    """Which `page_type` actually holds this season's PRESEASON board for `ecr_type` (D89).

    `market/series.py` maps a league to one `(ecr_type, page_type)` pair, which is correct for
    production because production drafts the current season. Across history the label moved:
    DynastyProcess stored the 2020 preseason redraft board as **`redraft-offense`** and every
    season from 2021 as **`redraft-overall`**. Measured, not assumed -- 2020 `redraft-overall`
    has 4922 rows and **none of them are in the Jul/Aug preseason window**, so a fixed
    `redraft-overall` lookup returns an EMPTY board for 2020.

    An empty board is not a harmless gap. `market_rank` drives the fair opponent, the
    `market_draft_demand` target and the opportunity-cost replay; with it empty,
    `best_by_market_rank` falls through to sorting by `player_id`, so the opponents draft
    ALPHABETICALLY and the whole season measures a different game.

    This resolves the page_type from the data -- whichever page carries the most Jul/Aug rows
    for that `ecr_type` and season -- so it returns `redraft-overall` for 2021-2025 (leaving
    every published number byte-identical) and `redraft-offense` for 2020. It is deliberately
    NOT a hardcoded season->page map: a relabel in another season is handled by the same rule.

    Returns `None` when the season has no preseason rows at all. A caller passing that straight
    through does NOT get an unscoped query: `_preseason_overall_market` treats `page_type=None`
    as "use the series default", so an `ecr_type` with a registered series still gets scoped to
    it. The board comes back empty either way -- there were no preseason rows to find -- so this
    is the honest answer rather than a silent widening, but it is a fallback to the default
    scoping, not an absence of scoping.

    Note what this must NOT do: widen the Jul/Aug window to find rows. 2020's `redraft-overall`
    rows exist but are IN-SEASON, so reading them would leak market movement that happened after
    the draft -- exactly the D54 defect.
    """
    rows = con.execute(
        """
        SELECT page_type, count(*) AS n FROM market_snapshot
        WHERE ecr_type = ? AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)
          AND page_type IS NOT NULL
        GROUP BY 1 ORDER BY n DESC, page_type
        """,
        [ecr_type, season],
    ).fetchall()
    return rows[0][0] if rows else None


#: Opponent strategies that READ `static.market_rank` to choose a pick, and therefore degrade
#: silently to alphabetical ordering when the board is empty. Listed explicitly rather than
#: aliased to `ALL_OPPONENT_STRATEGIES` so that adding a non-market strategy later does not
#: quietly opt it into a check that does not apply to it.
MARKET_DRIVEN_OPPONENT_STRATEGIES: frozenset[str] = frozenset(
    {MARKET_CONSENSUS, MARKET_CONSENSUS_ROSTER_AWARE}
)


class EmptyMarketBoardError(RuntimeError):
    """A market-driven opponent was asked to draft against a season with no preseason board.

    Raised rather than tolerated because the failure is SILENT otherwise: with `market_rank`
    empty, `_market_consensus_pick` and `_market_consensus_roster_aware_pick` fall through to
    ordering by `player_id`, so the nine opponents draft ALPHABETICALLY. The loop completes, the
    rosters are legal and every metric is finite -- the run looks successful and measures a
    different game. That is a fabricated observation, which this project forbids outright.

    Found in D89: the `dsf` (dynasty superflex) series begins 2020-10-16, so the legacy format
    has no 2020 preseason board at all, and the legacy 2020 cell had to be dropped.
    """


def assert_usable_market_board(static: SeasonStatic, opponent_strategy: str) -> None:
    """Refuse to simulate a market-opponent draft against an empty preseason board (D89).

    Only the market-driven opponents are checked; a strategy that does not read `market_rank`
    is unaffected, and a season whose board is merely SPARSE is allowed through -- the line is
    drawn at "no board at all", which is the case that silently degrades to alphabetical."""
    if opponent_strategy not in MARKET_DRIVEN_OPPONENT_STRATEGIES:
        return
    if not static.market_rank:
        raise EmptyMarketBoardError(
            f"season {static.season} has no preseason market board for ecr_type "
            f"'{static.ecr_type}', so opponent strategy '{opponent_strategy}' would draft "
            f"alphabetically by player_id. Resolve the season's own page with "
            f"`preseason_page_type`, or exclude the season -- do not measure this cell."
        )


def load_season_static(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    ecr_type: str | None = None,
    projections_override: dict[str, float] | None = None,
    page_type: str | None = None,
) -> SeasonStatic:
    """`projections_override` is D68's single insertion point.

    It replaces the projection universe BEFORE anything is derived from it, so MSV, static
    VORP, replacement levels, scarcity and the D67 demand boundary are all computed from one
    consistent set of numbers. Substituting calibrated projections any later would produce an
    engine whose value terms disagreed with each other, and a tier difference would then be
    measuring the inconsistency rather than the calibration."""
    # D56: the board has to match the league format the experiment is run against.
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type
    projections, positions = load_season_projections(con, season)
    if projections_override is not None:
        projections = projections_override
    vorp = marginal_value_over_replacement(league, projections, positions)
    levels = replacement_level(league, projections, positions)
    scarcity_raw = positional_scarcity(league, projections, positions)
    scarcity_norm = _normalize(scarcity_raw)
    # D89: `page_type` defaults to `market/series.py`'s mapping (production behaviour, and what
    # every D86/D87/D88 number was measured with). A caller may pass the season's own page via
    # `preseason_page_type` to reach a season whose board was labelled differently.
    market_rank = _preseason_overall_market(con, ecr_type, season, page_type=page_type)
    # D86: measured on prior seasons only. `measure_availability_rates` returns {} for a
    # position with no data, and the O1 tier raises on an empty dict rather than defaulting.
    availability_rates = measure_availability_rates(
        con, tuple(range(max(2015, season - 5), season))
    )

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
        consumption_demand=mock_draft_consumption_demand(
            league, market_rank, projections, positions
        ),
        availability_rates=availability_rates,
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
    availability_rates: dict[str, float] | None = None,
    expected_weekly_base: float | None = None,
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

    if tier in DRAFT_AWARE_REPLACEMENT_TIERS:
        # N4 exactly, except that `vorp` is recomputed against a draft-aware replacement level.
        # V0/W0 use production's static level, so they reproduce N4 by construction. The W-tiers'
        # legality constraint is applied in `_pick_by_tier`, not here -- it restricts which
        # candidates are eligible, it does not change any candidate's value.
        risk_mult = confidence if confidence is not None else 0.7
        # D79 phase 2: only the S-tiers vary this coefficient; every other draft-aware tier keeps
        # the shipped 0.3, so V/W/X/Y/Z results stay byte-identical to what they were measured
        # at. `S0` resolves to 0.3, which is what makes S0 == Z0 == X0 == W1 by construction.
        survival_bonus = S_TIER_SPEC[tier] if tier in ALL_S_TIERS else 0.3
        # D84: the Q-tiers may re-centre this term so it can DISCOUNT a player who is certain to
        # still be available, not only add urgency to one who is not. Every other tier keeps the
        # shipped one-sided form, so Q0 reproduces Z0/S0/X0/W1 exactly.
        if tier in Q_TIERS and Q_TIER_SPEC[tier][1]:
            survival_mult = dvb_survival_multiplier(survival, symmetric=True)
        else:
            survival_mult = 1.0 if survival is None else (1.0 + survival_bonus * (1.0 - survival))
        opp_cost = _opportunity_cost_for(
            static,
            position,
            available,
            current_pick_overall,
            next_pick_overall,
            opportunity_costs,
        )
        if tier in O_TIERS and O_TIER_SPEC[tier]:
            # D86. Same marginal-value question, asked under measured availability instead of
            # under "everyone plays 17 weeks". RAISE rather than default if the rates were not
            # hoisted: without them this silently degrades to the control while still reporting
            # itself as O1 -- the D78/D81/D85 failure mode.
            if availability_rates is None:
                raise RuntimeError(
                    f"tier {tier} needs `availability_rates`; without them the value base "
                    "silently degrades to the control and the tier measures nothing"
                )
            msv = expected_weekly_marginal_value(
                league,
                roster_player_ids or [],
                player_id,
                static.projections,
                static.positions,
                availability_rates,
                base=expected_weekly_base,
            )
        else:
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

        # D79: only the Z-tiers vary the value base here; every other draft-aware tier keeps the
        # shipped N4 form, so V/W/X/Y results stay byte-identical to what they were measured at.
        # `Z0` resolves to `msv + 1.0*vorp_term`, which is that same expression -- which is what
        # makes Z0 == X0 == W1 by construction rather than by coincidence.
        if tier in ALL_Z_TIERS:
            base_name, weight = Z_TIER_SPEC[tier]
            if base_name == "vorp":
                value_base = vorp_term
            elif base_name == "min_vorp_msv":
                value_base = min(vorp_term, msv)
            elif base_name == "msv_over_replacement":
                # The subtrahend is computed against the DRAFT-AWARE levels (see `_pick_by_tier`),
                # so this reduces to `vorp_term` on an empty roster and to 0.0 at a saturated
                # position -- the identity `replacement_marginal_starter_values` documents, now
                # anchored to the replacement level D67 actually shipped rather than the static
                # one D63 measured it against.
                #
                # RAISE rather than default the subtrahend to 0.0. Without the hoisted map this
                # value base silently collapses to `msv`, i.e. it quietly becomes a DIFFERENT
                # tier (ZW0) while still reporting itself as Z2 -- the same class of silent
                # no-op D78 found in the paired-benchmark instrument, where both arms scored
                # identically and it looked like a null result rather than a harness defect.
                if replacement_msv is None:
                    raise RuntimeError(
                        f"tier {tier} needs `replacement_msv` (the per-position marginal starter "
                        "value of a draft-aware replacement body); without it the value base "
                        "silently degrades to `msv` and the tier measures something else"
                    )
                value_base = msv - replacement_msv.get(position, 0.0)
            else:  # msv_plus_weighted_vorp
                value_base = msv + weight * vorp_term
            reasons.append(f"value_base={base_name}(w={weight:g}) {value_base:+.1f} pts")
        elif tier in Q_TIERS:
            # D84. Q0/Q2 are the shipped base; Q1/Q3 replace the RAW-PROJECTION half of it with
            # a second surplus, so on an empty slot the base is 2*(proj - R) rather than
            # 2*proj - R. That holds the SCALE of the value base while removing the double
            # count -- the one thing Z1/Z2/Z3 could not separate, because each of them also
            # halved the base against a fixed opportunity cost.
            base_name = Q_TIER_SPEC[tier][0]
            if base_name == "msv_over_replacement_plus_weighted_vorp":
                # Same RAISE-rather-than-default rule as Z2: without the hoisted map this
                # silently becomes Q0 while still reporting itself as Q1.
                if replacement_msv is None:
                    raise RuntimeError(
                        f"tier {tier} needs `replacement_msv`; without it the value base "
                        "silently degrades to the control and the tier measures nothing"
                    )
                value_base = (msv - replacement_msv.get(position, 0.0)) + (
                    DECISION_ARM_VORP_WEIGHT * vorp_term
                )
            else:  # msv_plus_weighted_vorp -- the control
                value_base = msv + DECISION_ARM_VORP_WEIGHT * vorp_term
            reasons.append(f"value_base={base_name} {value_base:+.1f} pts")
        elif tier in O_TIERS:
            # The D63 sum, unchanged. Only `msv` above differs between O0 and O1.
            value_base = msv + DECISION_ARM_VORP_WEIGHT * vorp_term
            reasons.append(
                f"value_base={'E[weekly]' if O_TIER_SPEC[tier] else 'msv'}+vorp "
                f"{value_base:+.1f} pts"
            )
        elif tier in L_TIERS:
            # D85. The VALUE half of the 2x2 is exactly D84's: L0/L1 carry the shipped base,
            # L2/L3 carry arm C's. The LEGALITY half is not scored here at all -- it is a
            # restriction on candidate eligibility applied in `_pick_by_tier`, which is the whole
            # point of the phase, so L0/L1 are identical here and so are L2/L3.
            base_name = L_TIER_SPEC[tier][0]
            if base_name == "msv_over_replacement_plus_weighted_vorp":
                # Same RAISE-rather-than-default rule as Z2/Q1: without the hoisted map this
                # silently becomes the control while still reporting itself as L2/L3.
                if replacement_msv is None:
                    raise RuntimeError(
                        f"tier {tier} needs `replacement_msv`; without it the value base "
                        "silently degrades to the control and the tier measures nothing"
                    )
                value_base = (msv - replacement_msv.get(position, 0.0)) + (
                    DECISION_ARM_VORP_WEIGHT * vorp_term
                )
            else:  # msv_plus_weighted_vorp -- the control
                value_base = msv + DECISION_ARM_VORP_WEIGHT * vorp_term
            reasons.append(f"value_base={base_name} {value_base:+.1f} pts")
        else:
            value_base = msv + N4_VORP_WEIGHT * vorp_term

        score = (value_base + opp_cost) * fit_mult * risk_mult * survival_mult
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
    picks_remaining: int | None = None,
    shortlist_k: int | None = None,
) -> tuple[str, list[CandidateScore]]:
    """Returns (chosen_player_id, every scored candidate sorted best-first) -- the ranked list
    is what a JSON trace needs to show runner-up reasoning, not just the winner.

    `picks_remaining` (counting this one) is only consulted by the tiers in
    `TIERS_ENFORCING_LEGALITY` (D67's W2/W3, D85's L1/L3); every other tier ignores it, so
    omitting it leaves them byte-identical.

    `shortlist_k` (D87) is a pure COST approximation for the tiers whose objective is expensive
    (currently O1). When set, the whole board is first ranked by the CHEAP control scorer and only
    the top `shortlist_k` are re-scored under the expensive objective -- exactly the procedure
    D86's Phase 14 cost probe used. It changes no formula, no weight and no gate; it changes only
    how many candidates the expensive objective is evaluated on. `None` (the default) scores the
    entire board, which is what every D86 number was measured with.

    It is NOT free: a candidate outside the cheap top-K can never be selected, so a shortlist can
    in principle lose a position the roster still needs. Whether it actually does is measured
    (D87 Phases 3 and 5), never assumed."""
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
    if tier in ALL_V_TIERS and V_TIER_SPEC[tier] is not None:
        dynamic_levels = REPLACEMENT_VARIANTS[V_TIER_SPEC[tier]](
            league, available, static.projections, static.positions
        )
    elif tier in W_TIERS and W_TIER_SPEC[tier][0] is not None:
        target = W_TIER_SPEC[tier][0]
        variant = (
            consumption_replacement(static.consumption_demand)
            if target == "consumption"
            else REPLACEMENT_VARIANTS[target]
        )
        dynamic_levels = variant(league, available, static.projections, static.positions)
    elif (
        tier in X_TIERS
        or tier in Y_TIERS
        or tier in ALL_Z_TIERS
        or tier in ALL_S_TIERS
        or tier in Q_TIERS
        or tier in L_TIERS
    ):
        # D68/D70: identical to W1. The projections `static` carries are the treatment; the
        # replacement rule they are measured against is the shipped one, unchanged.
        # D85: the L-tiers MUST be here. Omitting them silently reverted every L-tier to the
        # STATIC replacement level -- the D65 defect D67 shipped to remove -- which made the
        # D85 control score 1963.62 against Q0/Z0/S0/W1/X0's 2042.80 on the identical board.
        # Caught by the pre-registered "L0 is byte-identical to Q0" check, which is exactly the
        # class of silent harness defect D78 and D81 recorded. `test_l0_is_the_shipped_engine`
        # now pins it so it cannot regress.
        # D79: the Z-tiers hold that same shipped replacement rule fixed and vary the VALUE BASE
        # instead -- the mirror image of D65-D67, which held the value base fixed and varied the
        # replacement rule.
        dynamic_levels = consumption_replacement(static.consumption_demand)(
            league, available, static.projections, static.positions
        )

    base_lineup_points = None
    if (
        tier in M_TIERS
        or tier in ALL_N_TIERS
        or tier in R_TIERS
        or tier in DRAFT_AWARE_REPLACEMENT_TIERS
    ):
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
    elif (
        tier in L_TIERS and L_TIER_SPEC[tier][0] == "msv_over_replacement_plus_weighted_vorp"
    ) or (tier in Q_TIERS and Q_TIER_SPEC[tier][0] == "msv_over_replacement_plus_weighted_vorp"):
        # D84/D85: identical quantity and identical draft-aware anchoring to Z2's below -- only
        # the value base that consumes it differs. L2/L3 share this branch with Q1/Q3 precisely
        # so that D85's valuation arm is the SAME computation D84 published, not a re-derivation.
        replacement_msv = replacement_marginal_starter_values(
            league,
            roster_player_ids or [],
            static.projections,
            static.positions,
            {**static.replacement_levels, **(dynamic_levels or {})},
            base_points=base_lineup_points,
        )
    elif tier in ALL_Z_TIERS and Z_TIER_SPEC[tier][0] == "msv_over_replacement":
        # D79: same quantity as N3's, but the replacement body is drawn at the DRAFT-AWARE level
        # rather than the static one. Falling back to the static level for a position the demand
        # model does not cover mirrors what `score_candidate`'s `vorp_term` already does, so the
        # minuend and the subtrahend are always measured against the same level.
        replacement_msv = replacement_marginal_starter_values(
            league,
            roster_player_ids or [],
            static.projections,
            static.positions,
            {**static.replacement_levels, **(dynamic_levels or {})},
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
        *DRAFT_AWARE_REPLACEMENT_TIERS,
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

    # D86: E[weekly lineup value] of the CURRENT roster -- the subtrahend in O1's marginal
    # value. Depends only on the roster, so it is hoisted out of the per-candidate loop exactly
    # like `base_lineup_points` above; recomputing it per candidate would multiply the Monte
    # Carlo cost by the size of the board.
    expected_weekly_base = None
    if tier in O_TIERS and O_TIER_SPEC[tier]:
        if not static.availability_rates:
            raise RuntimeError(
                f"tier {tier} needs measured availability rates and this season's static has "
                "none (no prior seasons?); refusing to default them"
            )
        expected_weekly_base = expected_weekly_starter_points(
            league,
            roster_player_ids or [],
            static.projections,
            static.positions,
            static.availability_rates,
        )

    # D87: restrict the EXPENSIVE objective to the cheap scorer's top-K, when asked. The cheap
    # ranking uses the control tier (`PREREGISTERED_O_CONTROL`), which is the shipped engine, so
    # the shortlist is built from production's own view of the board and nothing about the
    # expensive objective leaks into which candidates it gets to see.
    candidate_ids: Iterable[str] = available
    if shortlist_k is not None and tier in O_TIERS and O_TIER_SPEC[tier]:
        cheap = []
        for player_id in available:
            c = score_candidate(
                static,
                player_id,
                league,
                roster_positions,
                PREREGISTERED_O_CONTROL,
                available=available,
                current_pick_overall=current_pick_overall,
                next_pick_overall=next_pick_overall,
                opportunity_costs=opportunity_costs,
                roster_player_ids=roster_player_ids,
                base_lineup_points=base_lineup_points,
                dynamic_levels=dynamic_levels,
            )
            if c is not None:
                cheap.append(c)
        cheap.sort(key=lambda c: (-c.score, c.player_id))
        candidate_ids = [c.player_id for c in cheap[:shortlist_k]]

    scored = []
    for player_id in candidate_ids:
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
            availability_rates=static.availability_rates or None,
            expected_weekly_base=expected_weekly_base,
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

    # D67: roster legality as a hard CONSTRAINT, kept deliberately separate from valuation.
    # Once this team has exactly as many picks left as it has unfilled mandatory dedicated
    # slots, the pick is restricted to filling one of them -- still the best of those by the
    # tier's own score, so nothing about how players are valued changes. This is the same rule
    # `evaluation/draft_simulation.py::_market_consensus_roster_aware_pick` already applies to
    # the fair opponent, which the engine has never had (measured: `alpha_bpa` finishes 50/50
    # drafts with a mean 6.48 unfilled mandatory slots and nothing raises); applying it to both
    # sides also makes the benchmark symmetric. It triggers at the last possible pick and only
    # while a slot is still empty, so it is not a positional quota or a fixed round.
    if tier in TIERS_ENFORCING_LEGALITY and picks_remaining is not None:
        deficits = unfilled_dedicated_slots(league, roster_positions)
        total_deficit = sum(deficits.values())
        if total_deficit > 0 and picks_remaining <= total_deficit:
            restricted = [s for s in scored if s.position in deficits]
            if restricted:
                return restricted[0].player_id, scored
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
    shortlist_k: int | None = None,
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
    assert_usable_market_board(static, opponent_strategy)
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
                    picks_remaining=picks_remaining,
                    shortlist_k=shortlist_k,
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


def _calibrated_static(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    arm: Arm,
    residual_rows: list[ResidualRow],
    control: SeasonStatic,
) -> SeasonStatic:
    """`control`, rebuilt from `arm`'s walk-forward calibrated projections (D68).

    Returns the control object itself when the arm is the identity -- which it is for X0
    always, and for any arm the evidence prior or shrinkage zeroed. That is not an
    optimization: it guarantees such a tier is byte-identical to W1 rather than merely equal to
    it up to floating-point reconstruction, so a zero difference in the results table means
    exactly what it says."""
    training = [row for row in residual_rows if row.season < season]
    params = fit_arm(arm, training, season)
    if params.is_identity:
        return control
    edges = band_edges(league, season_demand(con, league, season))
    calibrated = apply_calibration(params, control.projections, control.positions, edges)
    return load_season_static(
        con, league, season, ecr_type=control.ecr_type, projections_override=calibrated
    )


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

    # D68: the residual history is loaded ONCE for the whole grid rather than per (season, arm).
    # It spans every season in the run, including the target ones -- which is safe only because
    # `fit_arm` raises if it is ever handed a row at or after the season being fitted, and
    # `calibrated_static` filters to strictly earlier seasons before calling it. The guard is
    # structural, so a future caller that forgets to filter gets an exception rather than a
    # quietly leaked benchmark.
    residual_rows: list[ResidualRow] = (
        load_residual_rows(con, league, seasons) if any(t in X_TIERS for t in tiers) else []
    )

    # D70: lazy import -- `rb_availability_experiment` imports `SeasonStatic`/`load_season_static`
    # FROM this module, so importing it back at module scope here would be circular. Only
    # imported when a Y-tier is actually requested.
    rb_availability_static = None
    if any(t in Y_TIERS for t in tiers):
        from alpha_squad.evaluation.rb_availability_experiment import (
            rb_availability_static as _rb_availability_static,
        )

        rb_availability_static = _rb_availability_static

    for season in seasons:
        static = load_season_static(con, league, season)
        calibrated_statics: dict[Arm, SeasonStatic] = {}
        y1_static: SeasonStatic | None = None
        for tier in tiers:
            season_static = static
            if tier in X_TIERS:
                arm = X_TIER_SPEC[tier]
                if arm not in calibrated_statics:
                    calibrated_statics[arm] = _calibrated_static(
                        con, league, season, arm, residual_rows, static
                    )
                season_static = calibrated_statics[arm]
            elif tier in Y_TIERS:
                if y1_static is None:
                    y1_static = rb_availability_static(con, league, season, static)
                season_static = y1_static
            for slot in slots:
                result = simulate_forensic_draft(
                    con,
                    league,
                    season,
                    tier,
                    slot,
                    season_static,
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


# Two-sided 95% t critical values, df = n_seasons - 1. Hardcoded for the season counts this
# benchmark can actually have (D71: additional history is unavailable before 2021, and new
# seasons arrive at one per year), so the clustered interval needs no scipy dependency.
_T_CRITICAL_95: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
}


def season_clustered_margin(rows: list[dict], tier: str, control_tier: str) -> dict:
    """Gate 8 (D79): the paired margin over `control_tier` with a SEASON-CLUSTERED interval.

    D71 established that this benchmark's 50 rows are not 50 independent observations -- one
    season's ten slots share one projection set, one market board and one set of realized
    outcomes, and Alpha's ten rosters within a season share 53-73% of their players. The naive
    i.i.d. interval over 50 rows that every phase through D70 quoted is therefore
    anticonservative. The honest unit is the season.

    Computed the paired way, which is what the deterministic cross-product design allows: take
    the per-(season, slot) difference against the control, average those within each season, then
    put a t-interval (df = n_seasons - 1) on the resulting season means. Pairing removes the
    between-slot and between-season variation that is common to both arms, so this is tighter
    than an unpaired season-level interval while still respecting the real unit.

    Returns the mean margin, the per-season means, and the 95% interval. `ci_excludes_zero` is
    the gate; it is deliberately the ONLY interval this phase is allowed to quote as evidence."""
    by_key: dict[tuple[int, int], dict[str, float]] = {}
    for r in rows:
        if r["tier"] in (tier, control_tier):
            by_key.setdefault((r["season"], r["draft_slot"]), {})[r["tier"]] = r["starter_points"]

    per_season: dict[int, list[float]] = {}
    for (season, _slot), pair in by_key.items():
        if tier in pair and control_tier in pair:
            per_season.setdefault(season, []).append(pair[tier] - pair[control_tier])

    season_means = {s: sum(d) / len(d) for s, d in sorted(per_season.items()) if d}
    n = len(season_means)
    if n == 0:
        return {
            "tier": tier,
            "n_seasons": 0,
            "mean_margin": float("nan"),
            "ci_excludes_zero": False,
        }
    values = list(season_means.values())
    mean = sum(values) / n
    if n < 2:
        return {
            "tier": tier,
            "n_seasons": n,
            "mean_margin": mean,
            "season_means": season_means,
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "ci_excludes_zero": False,
        }
    sd = _stdev(values)
    se = sd / (n**0.5)
    t = _T_CRITICAL_95.get(n - 1, 1.96)
    lo, hi = mean - t * se, mean + t * se
    return {
        "tier": tier,
        "n_seasons": n,
        "mean_margin": mean,
        "season_means": season_means,
        "sd_of_season_means": sd,
        "se": se,
        "ci_low": lo,
        "ci_high": hi,
        "ci_excludes_zero": (lo > 0) or (hi < 0),
        "n_wins": sum(1 for v in values if v > 0),
    }


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
