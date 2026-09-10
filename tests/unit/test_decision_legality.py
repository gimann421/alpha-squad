"""Regression tests for the D85 legality-vs-valuation pre-registration.

These lock the PROTOCOL, not any result: the 2x2 factorial, the identity of the control with
D84's and D79's controls, the fact that D85 inherits D84's gate thresholds verbatim rather than
adopting a friendlier bar, the auditability of every withdrawn mechanism, and the algebra of the
interaction term. If a later session quietly adds an arm, relaxes a gate, redefines the
constraint, or lets the wiring drift from the pre-registration, these fail.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation import decision_value_base as dvb
from alpha_squad.evaluation.decision_legality import (
    ARM_VORP_WEIGHT,
    L_TIER_DESCRIPTIONS,
    L_TIER_SPEC,
    LEGALITY_TIERS,
    MAX_ROUNDS_EARLIER,
    MAX_WORSE_SEASONS,
    MIN_STARTER_POINT_GAIN,
    PREDICTIONS,
    PREREGISTERED_CONTROL,
    PREREGISTERED_FORMATS,
    PREREGISTERED_SEASONS,
    PREREGISTERED_SLOTS,
    WITHDRAWN_MECHANISMS,
    GateResult,
    LTierVerdict,
    enforces_legality,
    interaction_effect,
    value_base_for,
)
from alpha_squad.league.draft import DRAFT_VORP_WEIGHT

# ---------------------------------------------------------------------------------------------
# The pre-registration itself
# ---------------------------------------------------------------------------------------------


def test_tiers_are_exactly_the_preregistered_four() -> None:
    assert LEGALITY_TIERS == ("L0", "L1", "L2", "L3")
    assert PREREGISTERED_CONTROL == "L0"
    assert set(L_TIER_SPEC) == set(LEGALITY_TIERS)
    assert set(L_TIER_DESCRIPTIONS) == set(LEGALITY_TIERS)


def test_the_arms_are_a_clean_two_by_two_factorial() -> None:
    """The design IS the answer to D85's question: only a factorial can measure whether the
    valuation correction is worth more once legality is guaranteed some other way."""
    valuations = {t: value_base_for(t) for t in LEGALITY_TIERS}
    legality = {t: enforces_legality(t) for t in LEGALITY_TIERS}

    # Two distinct valuations, each appearing exactly twice.
    assert len(set(valuations.values())) == 2
    # Legality off/on, each appearing exactly twice.
    assert sum(legality.values()) == 2

    # Every (valuation, legality) cell occupied exactly once -- that is what makes it a 2x2.
    cells = {(valuations[t], legality[t]) for t in LEGALITY_TIERS}
    assert len(cells) == 4


def test_control_is_the_shipped_engine_with_no_constraint() -> None:
    assert value_base_for("L0") == "msv_plus_weighted_vorp"
    assert enforces_legality("L0") is False


def test_l1_isolates_legality_and_l2_isolates_valuation() -> None:
    """The two single-factor arms must each change exactly one thing about the control."""
    assert value_base_for("L1") == value_base_for("L0")
    assert enforces_legality("L1") is True

    assert value_base_for("L2") != value_base_for("L0")
    assert enforces_legality("L2") is False


def test_l3_is_both_factors() -> None:
    assert value_base_for("L3") == value_base_for("L2")
    assert enforces_legality("L3") is True


def test_valuation_arm_is_exactly_d84s_arm_c() -> None:
    """D85's valuation half must be the SAME computation D84 published, not a re-derivation --
    otherwise D85's L2 cannot be checked against D84's arm C at all."""
    assert value_base_for("L0") == dvb.value_base_for("A")
    assert value_base_for("L2") == dvb.value_base_for("C")


def test_vorp_weight_matches_production_and_is_not_swept() -> None:
    """D79's ZW tiers already swept w and 1.0 won; this phase must not re-sweep it."""
    assert ARM_VORP_WEIGHT == dvb.ARM_VORP_WEIGHT == DRAFT_VORP_WEIGHT == 1.0


# ---------------------------------------------------------------------------------------------
# The gates are D84's, inherited rather than restated
# ---------------------------------------------------------------------------------------------


def test_gate_thresholds_are_inherited_verbatim_from_d84() -> None:
    """Reusing D84's bar is what stops this phase quietly adopting a friendlier one. These are
    imports, so the assertion is that the import has not been shadowed by a local constant."""
    assert MIN_STARTER_POINT_GAIN is dvb.MIN_STARTER_POINT_GAIN == 25.0
    assert MAX_WORSE_SEASONS is dvb.MAX_WORSE_SEASONS == 1
    assert MAX_ROUNDS_EARLIER is dvb.MAX_ROUNDS_EARLIER == 2.0


def test_evaluation_design_is_inherited_verbatim_from_d84() -> None:
    assert PREREGISTERED_SEASONS is dvb.PREREGISTERED_SEASONS == (2021, 2022, 2023, 2024, 2025)
    assert PREREGISTERED_SLOTS is dvb.PREREGISTERED_SLOTS == tuple(range(1, 11))
    assert PREREGISTERED_FORMATS is dvb.PREREGISTERED_FORMATS
    assert "legacy_2qb_dynasty" in PREREGISTERED_FORMATS


# ---------------------------------------------------------------------------------------------
# Withdrawals and predictions stay auditable
# ---------------------------------------------------------------------------------------------


def test_every_withdrawn_mechanism_carries_its_reason() -> None:
    """A mechanism left out of the arms must be recorded with the evidence that excluded it,
    not silently omitted."""
    for key in (
        "earlier_reservation",
        "starter_demand_replacement",
        "msv_over_replacement_alone",
        "positional_rules",
    ):
        assert key in WITHDRAWN_MECHANISMS
        assert len(WITHDRAWN_MECHANISMS[key]) > 40


def test_the_free_parameter_withdrawal_is_explicit() -> None:
    """The one tempting post-hoc move -- reserving a slot earlier than the last possible pick --
    must be pre-emptively forbidden, because it is exactly the tuning D66/D67 rejected."""
    reason = WITHDRAWN_MECHANISMS["earlier_reservation"]
    assert "free parameter" in reason
    assert "post hoc" in reason


def test_predictions_are_recorded_before_the_run() -> None:
    """P1-P5 exist so a surprise is legible as a surprise. P4 in particular pre-commits to the
    most likely outcome being that nothing ships."""
    assert set(PREDICTIONS) == {"P1", "P2", "P3", "P4", "P5"}
    assert "NOTHING SHIPS" in PREDICTIONS["P4"].upper()
    assert "construction" in PREDICTIONS["P3"]


def test_unknown_tier_raises() -> None:
    for fn in (value_base_for, enforces_legality):
        with pytest.raises(ValueError):
            fn("L9")


# ---------------------------------------------------------------------------------------------
# The interaction term -- the quantity the phase exists to measure
# ---------------------------------------------------------------------------------------------


def test_interaction_is_zero_when_the_factors_are_independent() -> None:
    """If legality is worth the same (+10) under both valuations, the factors do not interact."""
    assert interaction_effect(l0=2000.0, l1=2010.0, l2=2005.0, l3=2015.0) == pytest.approx(0.0)


def test_interaction_is_positive_when_legality_is_worth_more_under_the_correction() -> None:
    """D85's hypothesis: the correction is held back by having to buy legality itself, so
    guaranteeing legality separately should let it deliver more."""
    # legality worth +5 under Y1, +40 under arm C
    assert interaction_effect(l0=2000.0, l1=2005.0, l2=1990.0, l3=2030.0) == pytest.approx(35.0)


def test_interaction_is_negative_when_the_constraint_costs_more_under_the_correction() -> None:
    assert interaction_effect(l0=2000.0, l1=2005.0, l2=1990.0, l3=1985.0) == pytest.approx(-10.0)


def test_interaction_is_symmetric_in_its_two_readings() -> None:
    """`(L3-L1)-(L2-L0)` and `(L3-L2)-(L1-L0)` are the same number -- the effect of legality
    given the correction, and the effect of the correction given legality."""
    l0, l1, l2, l3 = 2013.5, 2006.0, 2016.6, 2040.0
    assert interaction_effect(l0, l1, l2, l3) == pytest.approx((l3 - l2) - (l1 - l0))


# ---------------------------------------------------------------------------------------------
# Verdict plumbing
# ---------------------------------------------------------------------------------------------


def test_verdict_requires_every_gate_to_pass() -> None:
    v = LTierVerdict(tier="L3")
    v.gates.append(GateResult("G1", True, ""))
    v.gates.append(GateResult("G2", False, ""))
    assert not v.passed


def test_verdict_with_no_gates_is_not_a_pass() -> None:
    """A tier that was never evaluated must not read as shipping-eligible."""
    assert not LTierVerdict(tier="L3").passed


def test_verdict_passes_only_when_all_gates_pass() -> None:
    v = LTierVerdict(tier="L3", gates=[GateResult(f"G{i}", True, "") for i in range(1, 10)])
    assert v.passed
