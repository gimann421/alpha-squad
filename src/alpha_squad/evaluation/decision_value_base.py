"""Pre-registered test of DECISION-LAYER value-base candidates (D84).

**Committed to git before any arm was run against real data** -- the arms, the rationale, the
gates, the effect-size thresholds and the selection rule. D39/D54/D55/D63/D67/D79/D82/D83
discipline.

What the diagnosis established (docs/DECISION_LAYER_INVESTIGATION.md)
--------------------------------------------------------------------
Two independent defects, hitting different positions.

**Defect 1 -- the double count.** `marginal_starter_value(c)` equals `proj(c)` EXACTLY whenever
`c` fills an empty lineup slot (measured, all six positions, four roster states). So the value
base is

    msv + daVORP = proj + (proj - R) = 2*proj - R

which adds two surpluses measured against two different baselines: MSV's implicit zero and
daVORP's `R`. The amplification over the principled `proj - R` is `1 + proj/(proj - R)`, which
diverges as `R -> proj`, so the FLATTER the position the worse it is: DST 8.10x, K 5.34x,
TE 3.36x, QB 3.15x, WR 2.61x, RB 2.59x. That ranking reproduces the observed pathology ranking
and was derived from the algebra, not fitted to it.

**Defect 2 -- the demand target.** Starter demand sums to the lineup size (10); consumption
demand to `roster_size` (16). Their ratio is 2.20x at QB and exactly 1.00x at K and DST.

Why only two candidates, and what is deliberately NOT here
----------------------------------------------------------
This is a heavily-mined seam. Before proposing anything, the existing evidence was re-read:

* **Starter-demand replacement is NOT proposed.** It is essentially D67's `W0` control -- static
  `replacement_level()` allocates dedicated plus earned flex slots and IS the starter boundary --
  and `W1` (consumption) beat it by **+32.1** starter points, CI [+11.5, +52.7], and by +75.5 out
  of format. The economic argument for it is in the investigation document; the benchmark has
  already rejected it. Repeating it would be re-running a known loss.
* **`msv_over_replacement` alone is NOT proposed.** Measured twice and lost twice: D63's `N3`,
  and D79's `Z2` at **-44.4** in the target format and **-75.8** in `legacy_2qb_dynasty`.
* **No weight sweep on `msv + w*daVORP`.** D79's ZW tiers swept w over {0, 0.5, 1, 2, 3} and 1.0
  won. Selecting a `w` off a sweep is what D67 rejected about D66.
* **No positional bonus, no K/DST rule, no ECR term, no player-specific anything.**

That leaves exactly two untested axes, and both are here.

THE ARMS
--------
    A  CONTROL -- the shipped engine. `msv + 1.0*daVORP`, consumption-boundary replacement,
       production's opportunity cost, roster fit, confidence, survival and feasibility cap.

    C  SCALE-CONTROLLED DOUBLE-COUNT REMOVAL. `msv_over_replacement + 1.0*daVORP`.

       What problem it solves: Defect 1. On an empty slot this is `2*(proj - R)` against the
       control's `2*proj - R`, so the raw projection is replaced by a second surplus.

       Why it should solve it: every arm that has ever removed the raw-projection term (Z1, Z2,
       Z3) ALSO halved the scale of the value base while the opportunity cost stayed fixed, so
       "remove raw projection" and "halve the value base" are perfectly confounded in the
       existing evidence. Because the score is `(value_base + oc) * multipliers`, halving the
       base is NOT a monotone rescaling -- it re-weights every position against `oc`. This arm
       removes the raw projection while holding the scale, and is the only way to tell which of
       the two D79 actually measured.

       What would reject it: any gate below. Note in advance that `C - A = -R_p`, a
       position-specific constant, which is structurally the shape D67 rejected in D66's uniform
       multiplier ("a positional re-weighting in disguise"). The difference is that this constant
       is DERIVED -- it is exactly what removing the double count subtracts -- and has no free
       parameter. That distinction is recorded now so it cannot be claimed afterwards.

    D  SYMMETRIC SURVIVAL. `survival_mult = 1.0 + 0.3*(1 - 2*survival)`, range [0.7, 1.3].

       What problem it solves: production's `1.0 + 0.3*(1 - survival)` lies in [1.0, 1.3], so it
       can only ADD urgency and never subtract it. A player CERTAIN to be available later scores
       exactly 1.0x -- certainty of future availability is worth nothing. Measured: Alpha takes
       its kicker at #81 while its own survival model says P(that kicker survives) = 1.00 through
       #120 and 0.81 at #141, and consensus does not take a kicker until #145.

       Why it should solve it: recentring the term on survival = 0.5 makes it a genuine
       two-sided timing signal. It is the SAME coefficient family and the SAME [0.7, 1.3] range
       production already uses for `roster_fit_multiplier`, so it is a re-centring, not a new
       mechanism with a new scale.

       What would reject it: any gate. Specifically, it must not simply delay every position --
       G4 fails it if it pushes a position more than two rounds LATER than the control without a
       starter-points gain to justify it.

    E  C + D. Present because the two defects are independent and may interact; if C and D each
       clear the gates, E decides whether they compose.

Every arm shares every other term with production. `A` is asserted to reproduce
`recommend_draft_pick`'s actual recommendation on real board states, so a divergence is a harness
defect rather than a finding -- the check D78 found missing in the paired projection harness.

THE GATES
---------
Gates G1-G8 are D79's Z-tier gates, reused because they are the strictest already-coded set and
because reusing them means this phase cannot quietly adopt a friendlier bar. G9 is new and is the
user's explicit effect-size requirement.

    G1  no position carrying a starting requirement zeroed at a higher rate than the control
    G2  roster infeasibility no higher than the control
    G3  mean starter points worse than the control in at most 1 of the 5 seasons
    G4  no position drafted more than 2 rounds EARLIER than the control
    G5  no increase in cap breaches at any position
    G6  leave-one-season-out: the margin survives dropping any single season
    G7  rerun unchanged on `legacy_2qb_dynasty`; the sign is reported either way, and a
        candidate that only helps in the target format is a format artifact, not a fix
    G8  the SEASON-CLUSTERED 95% CI on the paired margin excludes zero (D71)
    G9  the point margin is at least MIN_STARTER_POINT_GAIN

SELECTION RULE: ship the earliest-lettered arm clearing EVERY gate. If none clears them,
`league/draft.py` stays byte-identical and this phase reports that.

Recorded before the run so the outcome cannot be reinterpreted afterwards:
  * G8 is the gate most likely to kill an arm. D71's power analysis puts the minimum detectable
    effect at ~128 starter points at 5 seasons, and D79's alternatives lost by 34-44. An arm that
    wins the pooled mean but fails G8 does NOT ship, and the correct response is to report an
    unresolvable difference -- not to fall back to the naive n=50 interval.
  * The control winning outright is a real and likely outcome, and is positive evidence for an
    incumbent whose two known defects have now been named precisely.
  * Explicitly NOT goals, and never grounds to ship: fewer kickers, a later first quarterback,
    more running backs, a board that agrees with consensus, or an opening that looks more
    intuitive. Starter points first; every gate is a constraint, never the objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Arm = str

#: The pre-registered arms. There is no fifth; adding one after seeing results is a protocol
#: violation to be reported as a failed phase rather than patched around.
ARMS: tuple[Arm, ...] = ("A", "C", "D", "E")
PREREGISTERED_CONTROL: Arm = "A"

#: Recorded so the withdrawal is auditable rather than a silent omission.
WITHDRAWN_ARMS: dict[Arm, str] = {
    "B": (
        "starter-demand replacement in the value term -- essentially D67's W0 control, which "
        "consumption demand (W1) beat by +32.1 starter points, CI [+11.5, +52.7], and by +75.5 "
        "on legacy_2qb_dynasty. Already measured; not re-run."
    ),
}

#: {arm: (value base name, symmetric survival)}. The value-base names are the same strings
#: `draft_forensics.score_candidate` already dispatches on, so the two stay in step.
ARM_SPEC: dict[Arm, tuple[str, bool]] = {
    "A": ("msv_plus_weighted_vorp", False),
    "C": ("msv_over_replacement_plus_weighted_vorp", False),
    "D": ("msv_plus_weighted_vorp", True),
    "E": ("msv_over_replacement_plus_weighted_vorp", True),
}

ARM_DESCRIPTIONS: dict[Arm, str] = {
    "A": "control -- the shipped engine (msv + 1.0*daVORP)",
    "C": "msv_over_replacement + 1.0*daVORP (double count removed, scale held)",
    "D": "control value base, symmetric survival multiplier",
    "E": "C + D",
}

#: The VORP weight, inherited from production. NOT swept here -- D79's ZW tiers already swept it
#: over {0, 0.5, 1, 2, 3} and 1.0 won.
ARM_VORP_WEIGHT = 1.0

#: Symmetric survival: 1.0 + SURVIVAL_BONUS*(1 - 2*survival), range [0.7, 1.3]. The coefficient
#: is production's own 0.3, unchanged; only the centring moves.
SURVIVAL_BONUS = 0.3


def survival_multiplier(survival: float | None, symmetric: bool) -> float:
    """Production's multiplier, or the recentred two-sided form.

    Production : 1.0 + 0.3*(1 - survival)      in [1.0, 1.3] -- can only add urgency.
    Symmetric  : 1.0 + 0.3*(1 - 2*survival)    in [0.7, 1.3] -- can also discount a player who
                 is certain to still be there.

    `None` (no market dispersion on record for this player) means no opinion, and both forms
    return 1.0 -- the production behaviour, preserved so a missing-data player is never
    penalised by the new arm.
    """
    if survival is None:
        return 1.0
    if symmetric:
        return 1.0 + SURVIVAL_BONUS * (1.0 - 2.0 * survival)
    return 1.0 + SURVIVAL_BONUS * (1.0 - survival)


# --------------------------------------------------------------------------------------------
# PRE-REGISTERED EVALUATION
# --------------------------------------------------------------------------------------------
#: Walk-forward seasons and slots, matching the shipped benchmark (docs/BENCHMARK_SPEC.md).
PREREGISTERED_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)
PREREGISTERED_SLOTS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
PREREGISTERED_FORMATS: tuple[str, ...] = ("target_league", "legacy_2qb_dynasty")

#: G9. Starter-point totals run ~2000, and D71 put the minimum detectable effect at ~128 points
#: with 5 seasons. A threshold below that would be a bar the instrument cannot clear honestly, so
#: this is set at the resolvable floor rather than at a number that merely looks modest.
MIN_STARTER_POINT_GAIN = 25.0

#: G3 / G4, inherited verbatim from the N/Z rules.
MAX_WORSE_SEASONS = 1
MAX_ROUNDS_EARLIER = 2.0


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ArmVerdict:
    arm: Arm
    gates: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)


def value_base_for(arm: Arm) -> str:
    if arm not in ARM_SPEC:
        raise ValueError(f"unknown arm {arm!r}")
    return ARM_SPEC[arm][0]


def uses_symmetric_survival(arm: Arm) -> bool:
    if arm not in ARM_SPEC:
        raise ValueError(f"unknown arm {arm!r}")
    return ARM_SPEC[arm][1]
