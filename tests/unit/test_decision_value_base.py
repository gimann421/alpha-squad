"""Regression tests for the D84 decision-layer pre-registration.

These lock the PROTOCOL, not any result: the arms, the withdrawal of the starter-demand arm,
the survival multiplier's algebra, and the gate thresholds. If a later session quietly adds an
arm, relaxes a gate, or lets the symmetric survival term escape its range, these fail.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.decision_value_base import (
    ARM_DESCRIPTIONS,
    ARM_SPEC,
    ARM_VORP_WEIGHT,
    ARMS,
    MAX_ROUNDS_EARLIER,
    MAX_WORSE_SEASONS,
    MIN_STARTER_POINT_GAIN,
    PREREGISTERED_CONTROL,
    PREREGISTERED_FORMATS,
    PREREGISTERED_SEASONS,
    PREREGISTERED_SLOTS,
    SURVIVAL_BONUS,
    WITHDRAWN_ARMS,
    ArmVerdict,
    GateResult,
    survival_multiplier,
    uses_symmetric_survival,
    value_base_for,
)
from alpha_squad.league.draft import DRAFT_VORP_WEIGHT

# ---------------------------------------------------------------------------------------------
# The pre-registration itself
# ---------------------------------------------------------------------------------------------


def test_arms_are_exactly_the_preregistered_four() -> None:
    assert ARMS == ("A", "C", "D", "E")
    assert PREREGISTERED_CONTROL == "A"
    assert set(ARM_SPEC) == set(ARMS)
    assert set(ARM_DESCRIPTIONS) == set(ARMS)


def test_control_arm_is_the_shipped_engine() -> None:
    assert value_base_for("A") == "msv_plus_weighted_vorp"
    assert uses_symmetric_survival("A") is False


def test_vorp_weight_matches_production_and_is_not_swept() -> None:
    """D79's ZW tiers already swept w and 1.0 won; this phase must not re-sweep it."""
    assert ARM_VORP_WEIGHT == DRAFT_VORP_WEIGHT == 1.0


def test_the_arms_are_a_clean_two_by_two_factorial() -> None:
    """C isolates the value base, D isolates survival, E is both -- so an effect is
    attributable to one factor rather than to a bundle."""
    assert value_base_for("C") != value_base_for("A")
    assert uses_symmetric_survival("C") is False
    assert value_base_for("D") == value_base_for("A")
    assert uses_symmetric_survival("D") is True
    assert value_base_for("E") == value_base_for("C")
    assert uses_symmetric_survival("E") is True


def test_starter_demand_arm_is_recorded_as_withdrawn_not_silently_dropped() -> None:
    """It is D67's W0, which consumption demand already beat. The withdrawal must stay
    auditable, with its reason attached."""
    assert "B" not in ARMS
    assert "B" in WITHDRAWN_ARMS
    assert "W0" in WITHDRAWN_ARMS["B"]
    assert "+32.1" in WITHDRAWN_ARMS["B"]


def test_unknown_arm_raises() -> None:
    with pytest.raises(ValueError):
        value_base_for("Z")
    with pytest.raises(ValueError):
        uses_symmetric_survival("Z")


def test_evaluation_design_matches_the_shipped_benchmark() -> None:
    assert PREREGISTERED_SEASONS == (2021, 2022, 2023, 2024, 2025)
    assert tuple(range(1, 11)) == PREREGISTERED_SLOTS
    assert PREREGISTERED_FORMATS == ("target_league", "legacy_2qb_dynasty")


def test_gate_thresholds_are_pinned() -> None:
    assert MIN_STARTER_POINT_GAIN == 25.0
    assert MAX_WORSE_SEASONS == 1
    assert MAX_ROUNDS_EARLIER == 2.0
    assert SURVIVAL_BONUS == 0.3


def test_cross_format_gate_includes_a_genuinely_different_format() -> None:
    """A candidate that only helps in the target format is a format artifact (D67/D79)."""
    assert "legacy_2qb_dynasty" in PREREGISTERED_FORMATS


# ---------------------------------------------------------------------------------------------
# The survival multiplier -- the one piece of new algebra
# ---------------------------------------------------------------------------------------------


def test_production_survival_can_only_add_urgency() -> None:
    """The defect being tested: production's form never drops below 1.0, so a player certain
    to be available later is worth exactly as much now as a player with no opinion."""
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert survival_multiplier(s, symmetric=False) >= 1.0
    assert survival_multiplier(1.0, symmetric=False) == pytest.approx(1.0)
    assert survival_multiplier(0.0, symmetric=False) == pytest.approx(1.3)


def test_symmetric_survival_discounts_a_certain_survivor() -> None:
    assert survival_multiplier(1.0, symmetric=True) == pytest.approx(0.7)
    assert survival_multiplier(0.0, symmetric=True) == pytest.approx(1.3)
    assert survival_multiplier(0.5, symmetric=True) == pytest.approx(1.0)


def test_symmetric_survival_stays_inside_the_shipped_multiplier_range() -> None:
    """[0.7, 1.3] is the range production already uses for roster fit, so this is a
    re-centring rather than a new scale."""
    for i in range(101):
        assert 0.7 - 1e-12 <= survival_multiplier(i / 100, symmetric=True) <= 1.3 + 1e-12


def test_symmetric_survival_is_monotone_decreasing_in_survival() -> None:
    values = [survival_multiplier(i / 100, symmetric=True) for i in range(101)]
    assert values == sorted(values, reverse=True)


def test_both_forms_agree_when_the_player_is_certain_to_be_gone() -> None:
    """At survival 0 the two forms must coincide: the urgency end is unchanged, and only the
    ability to discount is added."""
    assert survival_multiplier(0.0, symmetric=True) == pytest.approx(
        survival_multiplier(0.0, symmetric=False)
    )


def test_missing_market_dispersion_is_never_penalised() -> None:
    """`None` means no opinion. Both forms must return exactly 1.0, so the new arm cannot
    punish a player merely for having no dispersion on record."""
    assert survival_multiplier(None, symmetric=False) == 1.0
    assert survival_multiplier(None, symmetric=True) == 1.0


# ---------------------------------------------------------------------------------------------
# Verdict plumbing
# ---------------------------------------------------------------------------------------------


def test_verdict_requires_every_gate_to_pass() -> None:
    v = ArmVerdict(arm="C")
    v.gates.append(GateResult("G1", True, ""))
    v.gates.append(GateResult("G2", False, ""))
    assert not v.passed


def test_verdict_with_no_gates_is_not_a_pass() -> None:
    """An arm that was never evaluated must not read as shipping-eligible."""
    assert not ArmVerdict(arm="C").passed


def test_verdict_passes_only_when_all_gates_pass() -> None:
    v = ArmVerdict(arm="D", gates=[GateResult(f"G{i}", True, "") for i in range(1, 10)])
    assert v.passed
