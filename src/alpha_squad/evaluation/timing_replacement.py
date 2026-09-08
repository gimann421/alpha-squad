"""PRE-REGISTRATION — experiment T: is replacement level being drawn at the wrong *time*?

This module is committed BEFORE any arm is run. It states the control, the arms, the primary
metric, every gate, and the ship condition, so that none of them can be chosen after seeing
which arm they would favour. Nothing here reads a result.

--------------------------------------------------------------------------------------------
The question
--------------------------------------------------------------------------------------------

Production's value base is `msv + 1.0 * daVORP`, where `daVORP = projection - replacement` and
replacement is the *demand-boundary* level (D67): the player sitting at the boundary of what a
full draft of this league still has to absorb at that position. That is an **end-of-draft**
quantity. It answers "what could I get at this position if I never spent another pick on it".

The decision a pick actually faces is different: "what could I get at this position **at my
next pick**, if I spend this one somewhere else". Those two questions have very different
answers, and they differ by different amounts per position. Measured on the real 2026 board at
overall pick #20 (slot 1, fair consensus room):

    position   end-of-draft boundary   available at my next changed board (#40)   difference
    QB                         203.0                                      306.7       -103.7
    RB                         100.9                                      243.9       -143.0
    WR                         107.8                                      212.4       -104.6
    TE                         120.0                                      146.5        -26.5

So the shipped level over-states every position's surplus, and over-states RB's by the most
and TE's by the least -- the exact opposite of the ordering the board's real scarcity has,
because the running back the engine likes (Love, 243.9) **survives the turn to #40** while the
tight end it likes (McBride, 202.0) **does not** (best TE at #40 is 146.5).

Production has one term that knows about timing -- the positional opportunity cost (D55) -- but
it is priced in static-VORP points and is worth at most a few tens of points against a value
base in the hundreds, and it is exactly zero at a back-to-back snake turn. So the timing signal
is present but small, and absent precisely at the turn.

Two mechanisms are therefore under test, and they are separable:

  (a) the value base is drawn at the wrong horizon (end-of-draft rather than next turn); and
  (b) the one timing-aware term goes blind at a back-to-back turn, where `picks_until_next_turn`
      is 0 and every opportunity cost is identically zero.

--------------------------------------------------------------------------------------------
Arms
--------------------------------------------------------------------------------------------

T0  CONTROL. The shipped engine, unchanged. Asserted equal to `recommend_draft_pick` by
    `assert_control_reproduces_production` at every audited pick before any arm is scored; a
    margin measured against a control that is not production measures the harness.

T1  Value base `msv + VONA`. Replacement is the best player at that position still on the board
    at my next **changed-board** pick (the literal opponent replay `positional_opportunity_cost`
    already uses, read for a different purpose). One factor: the horizon replacement is drawn
    at. Tests mechanism (a).

T2  Value base `VONA` alone. The pure timing formulation, with no level term at all. Tests (a)
    without the `msv` term that D79 measured as the source of the raw-projection double count.
    Registered in advance as the arm most likely to fail late-draft behaviour: once nothing at
    a position will be gone by my next pick, VONA is 0 for everyone there, so this arm has no
    way to prefer a better player over a worse one at an unthreatened position.

T3  Shipped value base, but the opportunity-cost horizon skips a zero-gap turn: at overall pick
    #20 it prices against the board at #40 rather than #21. Tests mechanism (b) alone, changing
    no value base at all. Parameter-free -- the horizon comes from the snake geometry, not a
    dial.

"Next changed-board pick" is defined structurally and has no free parameter: the first of my
own remaining picks strictly greater than `current + 1`. At every non-turn pick that is simply
my next pick, so T1/T2/T3 differ from production only where the geometry differs.

--------------------------------------------------------------------------------------------
Primary metric, gates, and the ship condition
--------------------------------------------------------------------------------------------

PRIMARY METRIC: mean realized starter points, paired on identical trials (same season, same
draft slot, same opponent field, same board, same projections). Board-ordering accuracy is
explicitly NOT the metric -- D79 established that an arm can move the board toward a hindsight
key and produce worse rosters.

Evaluation set: seasons 2021-2025 (2026 has no realized outcome) x 10 draft slots = 50 paired
drafts per arm per format, fair `market_consensus_roster_aware` opponents.

GATES (all must pass):

  G1  Mean starter points strictly greater than T0's, target format.
  G2  Wins in at least 3 of the 5 seasons (season means, paired).
  G3  Mean starter points at least T0's in `legacy_2qb_dynasty` -- a genuinely different
      decision problem, so a target-format-only gain is an artifact (D79 Gate 7).
  G4  Mean unfilled mandatory starting slots no worse than T0's.
  G5  No new roster pathology: mean count at QB, K and DST must not RISE above T0's, and mean
      count at RB and WR must not rise more than +1.5 above T0's. This gate is symmetric on
      purpose -- it forbids hoarding in either direction and is not a positional target.
  G6  RESOLVABILITY. The season-clustered paired 95% CI (t, df=4, per D71) must EXCLUDE ZERO.
      This is the binding gate and it is stated first because it is the one most likely to
      fail: D71 measured this instrument's minimum detectable effect at roughly 128 starter
      points, and every draft-layer change this project has ever shipped (D63 +39.9, D67
      +32.1) sits below it. An arm that improves the point estimate but whose CI contains zero
      DOES NOT SHIP. Recorded here in advance so that a positive-but-unresolvable result
      cannot be re-read as success.
  G7  Wins in at least 6 of the 10 draft slots.

SHIP CONDITION: the lowest-numbered arm clearing every gate ships. If no arm clears every
gate, NOTHING ships and the shipped engine stays byte-identical.

Registered in advance, so it cannot be claimed afterwards as a discovery: **the most likely
outcome of this experiment is that an arm improves the point estimate and fails G6**, because
that is what happened to every previous draft-layer candidate. That outcome is a null result,
not a partial success, and the correct response to it is to ship nothing and say so.
"""

from __future__ import annotations

from dataclasses import dataclass

# Arm identifiers, in selection order. `T0` is the control.
ARMS = ("T0", "T1", "T2", "T3")

ARM_DESCRIPTIONS: dict[str, str] = {
    "T0": "control: the shipped engine (msv + 1.0*daVORP at the end-of-draft demand boundary)",
    "T1": "value base msv + VONA (replacement at the next changed-board pick)",
    "T2": "value base VONA alone",
    "T3": "shipped value base; opportunity-cost horizon skips a zero-gap snake turn",
}

PRIMARY_METRIC = "mean_starter_points"
EVAL_SEASONS = (2021, 2022, 2023, 2024, 2025)
EVAL_SLOTS = tuple(range(1, 11))

# G5's hoarding bounds.
MAX_RISE_AT_SINGLE_SLOT_POSITIONS = 0.0  # QB, K, DST must not rise at all
MAX_RISE_AT_DEPTH_POSITIONS = 1.5  # RB, WR
SINGLE_SLOT_POSITIONS = ("QB", "K", "DST")
DEPTH_POSITIONS = ("RB", "WR")


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    detail: str


def evaluate_gates(
    arm_summary: dict,
    control_summary: dict,
    *,
    legacy_arm_summary: dict | None = None,
    legacy_control_summary: dict | None = None,
) -> list[GateResult]:
    """Apply G1-G7 exactly as registered above. Takes already-computed summaries so that the
    gate logic cannot depend on how a draft was run."""
    results: list[GateResult] = []

    margin = arm_summary["mean_starter_points"] - control_summary["mean_starter_points"]
    results.append(GateResult("G1", margin > 0, f"margin {margin:+.1f} starter points"))

    seasons_won = arm_summary["seasons_won"]
    results.append(
        GateResult("G2", seasons_won >= 3, f"{seasons_won} of {len(EVAL_SEASONS)} seasons won")
    )

    if legacy_arm_summary is None or legacy_control_summary is None:
        results.append(GateResult("G3", False, "legacy format not measured"))
    else:
        legacy_margin = (
            legacy_arm_summary["mean_starter_points"]
            - legacy_control_summary["mean_starter_points"]
        )
        results.append(GateResult("G3", legacy_margin >= 0, f"legacy margin {legacy_margin:+.1f}"))

    unfilled_delta = arm_summary["mean_unfilled"] - control_summary["mean_unfilled"]
    results.append(
        GateResult("G4", unfilled_delta <= 0, f"unfilled slots {unfilled_delta:+.2f} vs control")
    )

    violations = []
    for pos in SINGLE_SLOT_POSITIONS:
        rise = arm_summary["mean_counts"].get(pos, 0.0) - control_summary["mean_counts"].get(
            pos, 0.0
        )
        if rise > MAX_RISE_AT_SINGLE_SLOT_POSITIONS:
            violations.append(f"{pos} +{rise:.2f}")
    for pos in DEPTH_POSITIONS:
        rise = arm_summary["mean_counts"].get(pos, 0.0) - control_summary["mean_counts"].get(
            pos, 0.0
        )
        if rise > MAX_RISE_AT_DEPTH_POSITIONS:
            violations.append(f"{pos} +{rise:.2f}")
    results.append(
        GateResult("G5", not violations, "; ".join(violations) if violations else "no hoarding")
    )

    lo, hi = arm_summary["clustered_ci"]
    results.append(
        GateResult("G6", lo > 0.0 or hi < 0.0, f"season-clustered 95% CI [{lo:+.1f}, {hi:+.1f}]")
    )
    # G6 is directional in the ship sense: an interval excluding zero on the WRONG side is a
    # confirmed regression, not a pass. Re-stated as an explicit conjunction with G1 rather
    # than folded into the interval test, so the failure mode is visible in the output.
    if lo > 0.0 or hi < 0.0:
        results[-1] = GateResult(
            "G6",
            lo > 0.0,
            f"season-clustered 95% CI [{lo:+.1f}, {hi:+.1f}]"
            + ("" if lo > 0.0 else " -- excludes zero on the LOSING side"),
        )

    slots_won = arm_summary["slots_won"]
    results.append(GateResult("G7", slots_won >= 6, f"{slots_won} of {len(EVAL_SLOTS)} slots won"))
    return results


def selection(gate_results_by_arm: dict[str, list[GateResult]]) -> str | None:
    """The pre-registered selection rule: the lowest-numbered arm clearing every gate, else
    None (ship nothing)."""
    for arm in ARMS:
        if arm == "T0":
            continue
        results = gate_results_by_arm.get(arm)
        if results and all(r.passed for r in results):
            return arm
    return None
