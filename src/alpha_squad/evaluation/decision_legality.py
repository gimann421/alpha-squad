"""Pre-registered test of ECONOMIC VALUATION vs ROSTER LEGALITY as separable mechanisms (D85).

**Committed to git before any L-tier was run against real data** -- the arms, the rationale, the
gates, the effect-size thresholds, the selection rule, and the predicted outcomes.
D39/D54/D55/D63/D67/D79/D82/D83/D84 discipline.

What D84 established, and the single question it left open
----------------------------------------------------------
D84 (docs/DECISION_LAYER_FINAL_REPORT.md) proved the value base is algebraically incoherent:
`marginal_starter_value(c)` equals `proj(c)` EXACTLY whenever `c` fills an empty lineup slot, so

    msv + daVORP = proj + (proj - R) = 2*proj - R

adds two surpluses measured against two different baselines. Amplification over the principled
`proj - R` is `1 + proj/(proj - R)`, worst at the flattest positions: DST 8.10x, K 5.34x,
TE 3.36x, QB 3.15x, WR 2.61x, RB 2.59x.

It then measured the correction (arm C, `msv_over_replacement + daVORP`) and found:

  * the behavioural fix works exactly as predicted -- first QB 2.20 -> 3.10, first RB 4.94 ->
    3.62, first K 8.64 -> 10.14, first DST 10.08 -> 12.94;
  * it is worth **+3.1** starter points, CI [-128.8, +134.9], and **-29.6** out of format;
  * and it **breaks roster legality**: 2 infeasible rosters against the control's 0, because
    arm C zeroes TE twice.

That last finding is the whole of D85. D84's closing sentence:

    "Zero unfilled mandatory slots is NOT independent of the over-valuation -- it is bought by
    it. Pricing a kicker at 5.34x its surplus is what guarantees a kicker gets drafted at all."

So the engine currently uses ONE mechanism -- an over-valuation it can prove is wrong -- to
achieve TWO things: pricing players, and guaranteeing a legal roster. They cannot be fixed
independently while they remain the same mechanism. **D85 separates them and measures the 2x2.**

THE ARMS -- a 2x2 factorial, not a list of guesses
--------------------------------------------------
The factorial is the design, because the open question is an INTERACTION ("is the valuation
correction worth more once legality is guaranteed some other way?"), and only a factorial can
answer it. Two factors:

    VALUATION  : shipped Y1 (`msv + 1.0*daVORP`)  |  arm C (`msv_over_replacement + 1.0*daVORP`)
    LEGALITY   : off (production today)            |  on (endgame mandatory-slot reservation)

                        legality OFF        legality ON
    Y1 valuation            L0 (control)        L1
    arm C valuation         L2                  L3

    L0  CONTROL -- the shipped engine, byte-identical to D84's `Q0` and D79's `Z0`. A test
        asserts it reproduces `recommend_draft_pick` state by state, so any divergence is a
        harness defect rather than a finding (the check D78 found missing).

    L1  LEGALITY ALONE. Shipped valuation, plus the constraint. Isolates the constraint from
        any valuation change -- the same role D67's `W3` played for the demand target.

    L2  VALUATION ALONE. Reproduces D84's arm C / `Q1`. Present so D85's numbers are on the
        same instrument as D84's, and so the interaction term below is computable.

    L3  BOTH -- **the arm this phase exists to measure.** D84 named it as "the single most
        promising remaining direction".

The interaction is `(L3 - L1) - (L2 - L0)`. It is reported whatever its sign, and it is the
quantity that answers D85's primary question.

THE LEGALITY CONSTRAINT -- what it is, and why this form
---------------------------------------------------------
Unchanged from D67's `W2`/`W3` prototype (`draft_forensics._pick_by_tier`), which is in turn the
rule the fair benchmark opponent has always applied to itself
(`draft_simulation._market_consensus_roster_aware_pick`):

    Once this team's remaining picks equal the number of dedicated starting slots it has not
    yet filled, the pick is RESTRICTED to filling one of them -- still the best of those by the
    arm's own score.

Properties that make it a constraint rather than a valuation term, each of which the brief
requires:

  * **It never changes a player's value.** It restricts WHICH candidates are eligible; the
    ordering within the restricted set is the arm's own score, untouched.
  * **It has no free parameter.** The trigger is `picks_remaining <= unfilled_dedicated_slots`,
    both of which are counts read off the league config and the roster. There is no round
    number, no threshold, no coefficient. It is a feasibility check: "if I do not take one now,
    can this roster still be completed?"
  * **It is not a positional rule.** It names no position. A league with no K slot never fires
    it for K; `legacy_2qb_dynasty` (no K, no DEF) fires it for QB/RB/WR/TE only.
  * **It fires at the last possible moment**, so it cannot cause "late-round panic" earlier than
    the last round in which panic is the correct response. Firing earlier would require choosing
    how much earlier -- a free parameter, and exactly the tuning D67 rejected in D66.

Deliberately NOT proposed, recorded so the omission is auditable rather than silent:

  * **An earlier / softer reservation** (reserve a slot N picks before the end). Requires a free
    parameter with no structural anchor. If L3 fails only because the constraint binds too late,
    that is a finding to report, NOT a licence to introduce N post hoc.
  * **A positional bonus, quota, or round-based K/DST rule.** Forbidden by the brief and by D66.
  * **Starter-demand replacement.** D84 withdrew it (it is D67's `W0`, beaten by +32.1,
    CI [+11.5, +52.7]); D84 then measured the starter boundary directly and found it WIDENS the
    round-2 QB margin (+38.6 -> +48.5) rather than closing it. Twice refuted; not re-run.
  * **`msv_over_replacement` alone.** Measured and lost three times: D63 `N3`, D79 `Z2` (-44.4 /
    -75.8), and it is the scale confound arm C exists to control for.

THE GATES
---------
G1-G9 are **imported verbatim** from D84's `decision_value_base`, not restated, so this phase
cannot quietly adopt a friendlier bar. A test asserts the imported thresholds are identical.

    G1  no position carrying a starting requirement zeroed at a higher rate than the control
    G2  roster infeasibility no higher than the control
    G3  mean starter points worse than the control in at most 1 of the 5 seasons
    G4  no position drafted more than 2 rounds EARLIER than the control
    G5  no increase in cap breaches at any position
    G6  leave-one-season-out: the margin survives dropping any single season
    G7  rerun unchanged on `legacy_2qb_dynasty`; a candidate that only helps in the target
        format is a format artifact, not a fix
    G8  the SEASON-CLUSTERED 95% CI on the paired margin excludes zero (D71)
    G9  the point margin is at least MIN_STARTER_POINT_GAIN (25.0)

SELECTION RULE: ship the lowest-numbered L-tier clearing EVERY gate. If none clears them,
`league/draft.py` stays byte-identical to Y1 and this phase reports that.

PREDICTED OUTCOMES -- recorded so results cannot be reinterpreted afterwards
----------------------------------------------------------------------------
These are predictions, not hopes. Writing them down is what makes a surprise legible as a
surprise.

  P1. **L1 is close to inert.** On the Y1 valuation the constraint almost never binds, because
      the over-valuation already drags K and DST in by round 9-10 (D84: a kicker by round 10 in
      60 of 60 drafts). D84's independent K/DST-deferral probe cost -7.6, CI [-70.0, +54.8].
      Predict |L1 - L0| < 25 and 0 infeasible rosters in both arms.

  P2. **L2 reproduces D84's arm C** to within simulation noise: roughly +3 in the target format,
      roughly -30 on `legacy_2qb_dynasty`, ~2 infeasible rosters, first K ~10.1, first DST ~12.9.
      A material deviation means the rebuilt board differs from D84's and must be reported as a
      reproduction failure BEFORE any L3 number is interpreted.

  P3. **L3 clears G1 and G2 by construction.** The constraint makes an unfilled mandatory slot
      structurally impossible whenever the board still contains a body at that position, so
      arm C's 2 infeasible rosters should go to 0. This is the one thing the arm is nearly
      guaranteed to do, and it is therefore NOT evidence of anything on its own.

  P4. **L3 most likely still fails G8 and G9.** The rescue is worth about what an unfilled
      starting slot costs, ~130 realized points, on ~2 of 50 drafts -- roughly +5 points, on top
      of arm C's +3.1. Predicted L3 margin is single digits against a 25-point floor and a
      ~128-point minimum detectable effect. **The most likely outcome of this entire phase is
      that the legality constraint fixes the legality failure, the valuation correction remains
      worth approximately zero, and NOTHING SHIPS.**

  P5. **The interaction is predicted POSITIVE but small.** Legality should be worth more under
      arm C (where it binds) than under Y1 (where it does not).

If P3 holds and P4 holds, the honest report is: "the two mechanisms ARE separable, the
separation works exactly as designed, and it buys nothing measurable." That is a real result
about the architecture and it is not a failure of the phase.

Explicitly NOT goals, and never grounds to ship: fewer kickers, a later first quarterback, more
running backs, a board that agrees with consensus, or an opening that looks more intuitive.
Starter points first; every gate is a constraint, never the objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Imported rather than restated so D85 provably runs D84's bar. A test asserts these are the
# values `decision_value_base` declares.
from alpha_squad.evaluation.decision_value_base import (
    ARM_VORP_WEIGHT,
    MAX_ROUNDS_EARLIER,
    MAX_WORSE_SEASONS,
    MIN_STARTER_POINT_GAIN,
    PREREGISTERED_FORMATS,
    PREREGISTERED_SEASONS,
    PREREGISTERED_SLOTS,
)

__all__ = [
    "ARM_VORP_WEIGHT",
    "LEGALITY_TIERS",
    "L_TIER_SPEC",
    "L_TIER_DESCRIPTIONS",
    "MAX_ROUNDS_EARLIER",
    "MAX_WORSE_SEASONS",
    "MIN_STARTER_POINT_GAIN",
    "PREREGISTERED_CONTROL",
    "PREREGISTERED_FORMATS",
    "PREREGISTERED_SEASONS",
    "PREREGISTERED_SLOTS",
    "PREDICTIONS",
    "WITHDRAWN_MECHANISMS",
    "LTierVerdict",
    "GateResult",
    "enforces_legality",
    "interaction_effect",
    "value_base_for",
]

LTier = str

#: The pre-registered 2x2. There is no fifth tier; adding one after seeing results is a protocol
#: violation to be reported as a failed phase rather than patched around.
LEGALITY_TIERS: tuple[LTier, ...] = ("L0", "L1", "L2", "L3")
PREREGISTERED_CONTROL: LTier = "L0"

#: {tier: (value base name, enforce endgame mandatory-slot legality)}.
#:
#: The value-base names are the same strings `draft_forensics.score_candidate` already
#: dispatches on, so the wiring cannot drift from the pre-registration; a test asserts that the
#: L0/L2 value bases are exactly D84's A/C arms.
L_TIER_SPEC: dict[LTier, tuple[str, bool]] = {
    "L0": ("msv_plus_weighted_vorp", False),
    "L1": ("msv_plus_weighted_vorp", True),
    "L2": ("msv_over_replacement_plus_weighted_vorp", False),
    "L3": ("msv_over_replacement_plus_weighted_vorp", True),
}

L_TIER_DESCRIPTIONS: dict[LTier, str] = {
    "L0": "D85 control: the shipped Y1 engine (msv + 1.0*daVORP), no legality constraint. "
    "Byte-identical to D84's Q0 and D79's Z0",
    "L1": "D85: legality constraint ALONE on the shipped valuation -- isolates the constraint",
    "L2": "D85: arm C valuation ALONE (msv_over_replacement + 1.0*daVORP) -- reproduces D84's Q1",
    "L3": "D85: arm C valuation PLUS the legality constraint -- the joint arm D84 named as the "
    "single most promising remaining direction",
}

#: Recorded so each omission is auditable rather than a silent choice. See the module docstring
#: for the evidence behind each.
WITHDRAWN_MECHANISMS: dict[str, str] = {
    "earlier_reservation": (
        "reserving a mandatory slot N picks before the end rather than at the last possible "
        "pick -- requires a free parameter with no structural anchor, which is the tuning D67 "
        "rejected in D66. If L3 fails only because the constraint binds too late, that is a "
        "finding to report, not a licence to introduce N post hoc."
    ),
    "starter_demand_replacement": (
        "D84 withdrew it as D67's W0 (beaten by +32.1, CI [+11.5, +52.7]) and then measured the "
        "starter boundary directly: it WIDENS the round-2 QB margin (+38.6 -> +48.5). Twice "
        "refuted; not re-run."
    ),
    "msv_over_replacement_alone": (
        "measured and lost three times -- D63 N3, D79 Z2 (-44.4 target, -75.8 legacy), and it is "
        "the scale confound arm C exists to control for."
    ),
    "positional_rules": (
        "positional bonuses, quotas, round-based K/DST suppression, ECR forcing and "
        "player-specific patches are forbidden by the brief and by D66."
    ),
}

#: The pre-registered predictions, keyed for the report. Stated as testable claims.
PREDICTIONS: dict[str, str] = {
    "P1": "L1 is close to inert: |L1 - L0| < 25 starter points, 0 infeasible rosters in both.",
    "P2": "L2 reproduces D84's arm C: ~+3 target, ~-30 legacy, ~2 infeasible, first K ~10.1, "
    "first DST ~12.9. A material deviation is a reproduction failure to report BEFORE "
    "interpreting L3.",
    "P3": "L3 clears G1 and G2 by construction (arm C's 2 infeasible rosters go to 0). This is "
    "nearly guaranteed and is therefore NOT evidence of anything on its own.",
    "P4": "L3 most likely still fails G8 and G9: the rescue is worth ~+5 points on top of arm "
    "C's +3.1, against a 25-point floor and a ~128-point minimum detectable effect. The most "
    "likely outcome of the phase is that NOTHING SHIPS.",
    "P5": "The interaction (L3 - L1) - (L2 - L0) is positive but small: legality is worth more "
    "under arm C, where it binds, than under Y1, where it does not.",
}


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class LTierVerdict:
    tier: LTier
    gates: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)


def value_base_for(tier: LTier) -> str:
    """The value-base name `draft_forensics.score_candidate` dispatches on for this tier."""
    if tier not in L_TIER_SPEC:
        raise ValueError(f"unknown L-tier {tier!r}; known: {LEGALITY_TIERS}")
    return L_TIER_SPEC[tier][0]


def enforces_legality(tier: LTier) -> bool:
    """Whether this tier applies the endgame mandatory-slot reservation."""
    if tier not in L_TIER_SPEC:
        raise ValueError(f"unknown L-tier {tier!r}; known: {LEGALITY_TIERS}")
    return L_TIER_SPEC[tier][1]


def interaction_effect(l0: float, l1: float, l2: float, l3: float) -> float:
    """`(L3 - L1) - (L2 - L0)` -- how much MORE the valuation correction is worth once roster
    legality is guaranteed by a constraint instead of by the over-valuation.

    This is the quantity D85 exists to measure. Positive means the two mechanisms were indeed
    entangled and separating them recovers value the valuation correction could not deliver on
    its own; zero means they are independent and the correction is worth the same either way;
    negative means the constraint costs more under the corrected valuation than under Y1.

    Reported whatever its sign. It is a difference of four noisy means and is therefore NOT
    itself a shipping criterion -- the gates are.
    """
    return (l3 - l1) - (l2 - l0)
