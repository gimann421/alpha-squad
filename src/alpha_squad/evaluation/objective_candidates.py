"""Pre-registered test of DRAFT OBJECTIVE candidates (D86).

**Committed to git before any candidate was run against real data** -- the arms, the rationale,
the metrics, the gates, the selection rule and the predicted outcomes.
D39/D54/D55/D63/D67/D79/D82/D83/D84/D85 discipline.

What the D86 diagnosis established before any arm was proposed
---------------------------------------------------------------
1. **The incumbent objective is the wrong quantity, and provably so.** Every published draft
   number scores a roster by season totals and one lineup allocation. Fantasy scores weekly. On
   the rosters Alpha actually drafts (2021-2025 x 4 slots), **17.8% of realized points come from
   players the season-long objective never starts** (21.6% with hindsight lineups), and a bench
   player enters the lineup in **16.2 of 17 weeks**. The incumbent metric prices all of that at
   exactly zero.

2. **The level is roughly right; the composition is not.** season-long 2036.2 vs weekly
   no-foresight 2017.3. So this is not a claim that past numbers were wrong in total -- it is a
   claim that the MARGINAL value of a bench player has been zero when it should not be.

3. **Availability is measurable with no new data and no free parameter.** A bye and an injury are
   both a missing `player_week_stats` row. Draftable-player availability 2021-2025:
   QB 88.2%, RB 85.3%, WR 86.1%, TE 87.3%, K 93.6%, DST 94.0%.

4. **D85 closed the value-base seam.** Nine reformulations of `value_base` have now been measured
   and every one failed. `d(value_base)/d(proj) = 2` under Y1 and under its correction alike, and
   no formulation inside `(value_base + oc) x multipliers` can have both the D63 scale and a
   correct slope. **So this phase does not touch the value base's algebra at all.** It changes
   what the value base is an expectation OF.

THE ARMS -- a 2x2 of POLICY x METRIC, because changing both at once is confounded
---------------------------------------------------------------------------------
    POLICY : Y1 (`msv + daVORP`)   |   availability-aware (`E[weekly msv] + daVORP`)
    METRIC : season-long (incumbent) | weekly (what fantasy actually scores)

                          scored season-long      scored weekly
    Y1 policy                  O0 (control)            O0w
    availability policy        O1                      O1w

    O0  CONTROL -- the shipped engine, scored the way every previous phase scored it. Asserted
        byte-identical to D85's `L0`, D84's `Q0` and D79's `Z0`.

    O1  AVAILABILITY-AWARE MARGINAL VALUE. `marginal_starter_value` is replaced by
        `weekly_objective.expected_weekly_marginal_value`; daVORP, opportunity cost, roster fit,
        confidence, survival and the feasibility cap are UNCHANGED.

        What problem it solves: the shipped MSV is `proj` at an empty slot and exactly `0` at a
        saturated one. Both are wrong for the same reason -- they assume the starter plays every
        week. The replacement is the same quantity computed under measured availability.

        Why it should solve it: it prices bench depth without a bench bonus, and prices it MORE
        at positions that miss more time (measured backup values on a saturated roster: RB 207.2,
        WR 79.2, TE 69.8, QB 34.1, K 9.1, DST 5.9). The K/DST over-draft that five phases could
        not remove without an arbitrary rule is removed here by an availability rate.

        What would reject it: any gate below.

    O2  ONE-STEP LOOKAHEAD. `argmax_c` of the PROJECTED final-roster value after rolling the rest
        of the draft out with the shipped policy. Formal statement of the user's objectives
        (D)/(G). Included only if the Phase 5 agreement test shows it changes picks at all; a
        policy that never disagrees with greedy cannot be worth its cost.

Deliberately NOT proposed, recorded so each omission is auditable:

  * **Any change to the value base's algebra.** D85 closed it: nine reformulations, all failed,
    and the slope problem is structural. Re-running one would be a known loss.
  * **A bench bonus, a positional bonus, a round rule, ECR forcing, a player-specific patch.**
    Forbidden by the brief. Note that O1 needs none of them to defer K/DST -- that is the test.
  * **A waiver-replacement level.** Phase 7 measured the incumbent draft replacement against the
    realized undrafted pool and found it well calibrated to the NO-FORESIGHT waiver replacement
    (QB 200.4 vs 194.6, RB 89.0 vs 94.1, WR 111.9 vs 133.8, TE 116.2 vs 118.4, K 132.9 vs 104.2,
    DST 95.5 vs 87.4). Streaming optionality is real but there is **no transaction history in
    this database** to size it, and the perfect-foresight bound is not achievable. Changing the
    replacement level on an unmeasurable quantity would be exactly the tuning this project
    refuses.
  * **A risk/variance term.** Phase 9 found the existing `risk_mult` and `survival_mult` already
    span [0.63, 1.3] and [1.0, 1.3]; adding a third uncertainty term without evidence that the
    first two are mis-specified would be unmotivated.

THE METRICS
-----------
**PRIMARY: weekly realized points, no-foresight lineups.** This is the honest version of the
quantity fantasy actually scores -- lineups set from who is available, ranked by preseason
projection rather than by what they went on to score.

**SECONDARY, both always reported:**
  * weekly realized points, hindsight lineups (the optimistic bracket);
  * season-long realized points (the incumbent metric, so every D86 number stays comparable to
    D63/D67/D79/D84/D85).

**Adjudication rule, fixed in advance:** a candidate that improves the primary but materially
degrades the season-long metric does NOT ship. The weekly metric is better motivated, but it is
new, and this project does not adopt a new instrument and a new winner in the same step.

THE GATES
---------
G1-G9 are **imported verbatim** from D84's `decision_value_base`, as D85 did, so this phase
cannot quietly adopt a friendlier bar. G10 is new and is the adjudication rule above.

    G1  no position carrying a starting requirement zeroed at a higher rate than the control
    G2  roster infeasibility no higher than the control
    G3  primary metric worse than the control in at most 1 of the 5 seasons
    G4  no position drafted more than 2 rounds EARLIER than the control
    G5  no increase in cap breaches at any position
    G6  leave-one-season-out: the margin survives dropping any single season
    G7  rerun unchanged on `legacy_2qb_dynasty`; a candidate that only helps in the target
        format is a format artifact, not a fix
    G8  the SEASON-CLUSTERED 95% CI on the paired primary margin excludes zero (D71)
    G9  the primary point margin is at least MIN_STARTER_POINT_GAIN (25.0)
    G10 the SEASON-LONG margin is not worse than -MIN_STARTER_POINT_GAIN

SELECTION RULE: ship the lowest-numbered arm clearing EVERY gate. If none clears them,
`league/draft.py` stays byte-identical to Y1 and this phase reports that.

PREDICTED OUTCOMES -- recorded so results cannot be reinterpreted afterwards
----------------------------------------------------------------------------
  Q1. **O1 defers K and DST substantially** -- first K later by 1.5+ rounds, first DST by 2+ --
      because a backup kicker prices at 9.1 against a backup RB's 207.2. This is the behaviour
      five previous phases could only get with an arbitrary rule, and it is the one thing O1 is
      nearly certain to do. It is therefore NOT evidence of anything on its own (D85's P3
      lesson).

  Q2. **O1 drafts more RB depth**, because RB is the least available position AND the only one
      with flex eligibility. Expect RB count up and the K/DST count down.

  Q3. **On the WEEKLY metric O1 beats O0**, because O1 optimizes something much closer to it.
      A failure here would mean the availability model is wrong, not merely unhelpful.

  Q4. **On the SEASON-LONG metric O1 is roughly neutral to slightly negative**, because that
      metric cannot see the bench value O1 is buying. This is the most likely route to a G10
      failure and it is registered in advance as a real possibility, not a surprise.

  Q5. **The most likely overall outcome is still that NOTHING SHIPS**, on G8. D71's minimum
      detectable effect is ~128 starter points at 5 seasons and every draft-layer margin this
      project has produced sits below it. A better objective does not make the instrument more
      powerful. If O1 wins the point estimate on the primary metric and fails G8, the correct
      report is "the objective is better specified and the benchmark cannot resolve it", and the
      correct action is to ship nothing and say so.

  Q6. **O2 (lookahead) changes few picks.** The oracle pilot showed final-roster value is nearly
      flat across the top candidates (2134-2156 at one pick, despite realized points ranging
      355-430), because the continuation policy re-optimizes around whatever is taken. If the
      agreement test confirms it, O2 is dropped before it is run at cost.

Explicitly NOT goals, and never grounds to ship: fewer kickers, a later first quarterback, more
running backs, a board that agrees with consensus, or an opening that looks more intuitive.
The primary metric first; every gate is a constraint, never the objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from alpha_squad.evaluation.decision_value_base import (
    MAX_ROUNDS_EARLIER,
    MAX_WORSE_SEASONS,
    MIN_STARTER_POINT_GAIN,
    PREREGISTERED_FORMATS,
    PREREGISTERED_SEASONS,
    PREREGISTERED_SLOTS,
)

Arm = str

#: The pre-registered arms. O2 is conditional on the Phase 5 agreement test (see Q6).
ARMS: tuple[Arm, ...] = ("O0", "O1")
CONDITIONAL_ARMS: tuple[Arm, ...] = ("O2",)
PREREGISTERED_CONTROL: Arm = "O0"

ARM_DESCRIPTIONS: dict[Arm, str] = {
    "O0": "control -- the shipped Y1 engine (msv + 1.0*daVORP), asserted identical to L0/Q0/Z0",
    "O1": "availability-aware marginal value: E[weekly msv] + 1.0*daVORP, everything else shipped",
    "O2": "one-step lookahead: argmax of projected final-roster value (conditional on Phase 5)",
}

#: Metric names. The primary is first.
PRIMARY_METRIC = "weekly_no_foresight"
METRICS: tuple[str, ...] = ("weekly_no_foresight", "weekly_hindsight", "season_long")

#: G10. A candidate may not buy a primary-metric win at the cost of a materially worse
#: season-long result -- the instrument every previous phase was measured on.
MAX_SEASON_LONG_REGRESSION = MIN_STARTER_POINT_GAIN

WITHDRAWN_MECHANISMS: dict[str, str] = {
    "value_base_algebra": (
        "D85 closed it: nine reformulations measured across D63/D79/D84/D85, all failed, and the "
        "slope problem is structural -- no formulation inside (value_base + oc) x multipliers can "
        "have both the D63 scale and a unit slope in the projection. Not re-run."
    ),
    "waiver_replacement_level": (
        "Phase 7 found the incumbent draft replacement well calibrated to the NO-FORESIGHT waiver "
        "replacement at every position. Streaming optionality is real but there is no transaction "
        "history in this database to size it, and the perfect-foresight bound is unachievable. "
        "Retuning a replacement level against an unmeasurable quantity is the tuning D66/D67 "
        "rejected."
    ),
    "risk_or_variance_term": (
        "Phase 9 found risk_mult and survival_mult already span [0.63, 1.3] and [1.0, 1.3]. Adding "
        "a third uncertainty term without evidence the first two are mis-specified is unmotivated."
    ),
    "bench_or_positional_bonus": (
        "forbidden by the brief and by D66. O1 needs none -- it defers K/DST via a measured "
        "availability rate, which is the test of whether the mechanism is real."
    ),
}

PREDICTIONS: dict[str, str] = {
    "Q1": "O1 defers K by 1.5+ rounds and DST by 2+. Nearly certain, therefore NOT evidence.",
    "Q2": "O1 drafts more RB depth and fewer K/DST.",
    "Q3": "O1 beats O0 on the WEEKLY metric; a failure here means the availability model is wrong.",
    "Q4": "O1 is neutral-to-negative on the SEASON-LONG metric, which cannot see bench value. "
    "This is the most likely route to a G10 failure and is registered as a real possibility.",
    "Q5": "The most likely overall outcome is still that NOTHING SHIPS, on G8: D71's ~128-point "
    "MDE is a property of the instrument and a better objective does not improve it.",
    "Q6": "O2 changes few picks, because final-roster value is nearly flat across top candidates. "
    "If the agreement test confirms it, O2 is dropped before being run at cost.",
}


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


__all__ = [
    "ARMS",
    "ARM_DESCRIPTIONS",
    "CONDITIONAL_ARMS",
    "MAX_ROUNDS_EARLIER",
    "MAX_SEASON_LONG_REGRESSION",
    "MAX_WORSE_SEASONS",
    "METRICS",
    "MIN_STARTER_POINT_GAIN",
    "PREDICTIONS",
    "PREREGISTERED_CONTROL",
    "PREREGISTERED_FORMATS",
    "PREREGISTERED_SEASONS",
    "PREREGISTERED_SLOTS",
    "PRIMARY_METRIC",
    "WITHDRAWN_MECHANISMS",
    "ArmVerdict",
    "GateResult",
]
