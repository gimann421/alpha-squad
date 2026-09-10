"""Unit tests for the D79 monotonicity phase (`evaluation/projection_monotonicity.py`).

The load-bearing tests here are the two that guard the instrument rather than the result:
`_new_model` must refuse the MAE-plus-constraints combination that silently produces a
near-constant model, and E0 must be the shipped estimator. A phase whose control is not the
shipped model, or whose treatment arm is quietly degenerate, measures nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.projection_monotonicity import (
    ARM_DESCRIPTIONS,
    E_ARM_SPEC,
    E_ARMS,
    MONOTONE_CAPABLE_LOSSES,
    MONOTONE_DIRECTIONS,
    PREREGISTERED_CONTROL,
    PREREGISTERED_TARGET_SEASONS,
    SHIPPED_LOSS,
    SHIPPED_ROW_SPECIFICATION,
    _new_model,
    dominated_pairs,
    monotone_constraints_for,
    partial_dependence_inversions,
)
from alpha_squad.models.established.season_level import FEATURES


class TestPreRegistration:
    def test_the_control_is_the_shipped_estimator(self):
        assert PREREGISTERED_CONTROL == "E0"
        assert E_ARMS[0] == "E0"
        assert E_ARM_SPEC["E0"] == (SHIPPED_LOSS, False)

    def test_every_arm_trains_on_the_shipped_row_specification(self):
        """The training set and the estimator must not change in the same phase, or a
        difference between arms is unattributable."""
        assert SHIPPED_ROW_SPECIFICATION == "Y1"

    def test_the_loss_change_is_its_own_arm(self):
        """The constraint cannot be applied under MAE, so the loss change is unavoidable. It is
        a separate arm so that E2 - E1 isolates the constraint and E2 - E0 is the shipping
        comparison."""
        assert E_ARM_SPEC["E1"] == ("RMSE", False)
        assert E_ARM_SPEC["E2"] == ("RMSE", True)

    def test_the_evaluation_window_matches_d78(self):
        assert PREREGISTERED_TARGET_SEASONS == (2022, 2023, 2024, 2025)

    def test_every_arm_is_described(self):
        assert set(ARM_DESCRIPTIONS) == set(E_ARMS)
        for arm in E_ARMS:
            assert ARM_DESCRIPTIONS[arm]

    def test_prior_games_is_never_constrained(self):
        """Its direction is genuinely ambiguous; constraining it would be an assumption this
        phase exists to avoid making."""
        assert MONOTONE_DIRECTIONS["prior_games"] == 0

    def test_constraint_directions_match_what_the_features_mean(self):
        assert MONOTONE_DIRECTIONS["prior_ppg"] == 1
        assert MONOTONE_DIRECTIONS["prior_weighted_total"] == 1
        # ECR rank is 1 = best, so the projection must be NON-INCREASING in the rank value.
        assert MONOTONE_DIRECTIONS["preseason_ecr_rank"] == -1

    def test_constraint_vectors_are_in_feature_order(self):
        assert monotone_constraints_for("E0") == [0, 0, 0, 0]
        assert monotone_constraints_for("E1") == [0, 0, 0, 0]
        expected = [MONOTONE_DIRECTIONS[f] for f in FEATURES]
        assert monotone_constraints_for("E2") == expected

    def test_unknown_arm_raises(self):
        with pytest.raises(ValueError, match="unknown arm"):
            monotone_constraints_for("E9")


class TestTheInstrumentGuard:
    """The defect that voided this phase's first arm set. CatBoost applies monotone constraints
    only under some losses; under MAE it silently switches leaf estimation from `Exact` to
    `Gradient` and fits a near-constant model. Measuring that would have looked like
    'constraints are catastrophic' rather than 'the fit is broken'."""

    def test_mae_is_not_a_monotone_capable_loss(self):
        assert SHIPPED_LOSS not in MONOTONE_CAPABLE_LOSSES

    def test_the_control_and_the_loss_arm_still_build(self):
        assert _new_model("E0") is not None
        assert _new_model("E1") is not None

    def test_constraints_under_the_shipped_loss_raise_rather_than_degrade(self, monkeypatch):
        import alpha_squad.evaluation.projection_monotonicity as mod

        monkeypatch.setitem(mod.E_ARM_SPEC, "E2", (SHIPPED_LOSS, True))
        with pytest.raises(ValueError, match="monotone constraints under loss"):
            mod._new_model("E2")

    def test_the_control_passes_no_constraint_parameter_at_all(self):
        """Not 'the shipped model with an all-zero constraint vector' -- CatBoost need not treat
        those identically, and the control has to be the shipped fit."""
        params = _new_model("E0").get_params()
        assert "monotone_constraints" not in params
        assert params["loss_function"] == SHIPPED_LOSS

    def test_the_constrained_arm_does_pass_one(self):
        params = _new_model("E2").get_params()
        assert params["monotone_constraints"] == monotone_constraints_for("E2")
        assert params["loss_function"] in MONOTONE_CAPABLE_LOSSES


class _StubModel:
    """Returns a caller-supplied function of the feature row, so the diagnostics can be tested
    against a known shape instead of against whatever a real fit happens to produce."""

    def __init__(self, fn):
        self._fn = fn

    def predict(self, X):
        return np.array([self._fn(row) for row in np.asarray(X, dtype=float)])


def _train_frame():
    rng = np.random.default_rng(0)
    n = 200
    return pd.DataFrame(
        {
            "prior_ppg": rng.uniform(0, 25, n),
            "prior_games": rng.integers(1, 18, n).astype(float),
            "prior_weighted_total": rng.uniform(0, 400, n),
            "preseason_ecr_rank": rng.uniform(1, 999, n),
        }
    )


class TestPartialDependenceInversions:
    def test_a_monotone_increasing_function_has_none(self):
        train = _train_frame()
        idx = FEATURES.index("prior_weighted_total")
        model = _StubModel(lambda r: 2.0 * r[idx])
        inv, cmp_ = partial_dependence_inversions(model, train, "prior_weighted_total")
        assert cmp_ > 0
        assert inv == 0

    def test_a_decreasing_function_inverts_at_every_step(self):
        train = _train_frame()
        idx = FEATURES.index("prior_weighted_total")
        model = _StubModel(lambda r: -2.0 * r[idx])
        inv, cmp_ = partial_dependence_inversions(model, train, "prior_weighted_total")
        assert inv == cmp_ > 0

    def test_the_ecr_direction_is_reversed(self):
        """Lower rank is better, so a projection that RISES with the rank value is the
        inversion -- the opposite sign to the production features."""
        train = _train_frame()
        idx = FEATURES.index("preseason_ecr_rank")
        rising = _StubModel(lambda r: 1.0 * r[idx])
        falling = _StubModel(lambda r: -1.0 * r[idx])
        inv_rising, cmp_ = partial_dependence_inversions(rising, train, "preseason_ecr_rank")
        inv_falling, _ = partial_dependence_inversions(falling, train, "preseason_ecr_rank")
        assert inv_rising == cmp_ > 0
        assert inv_falling == 0

    def test_an_unconstrained_feature_is_not_measured(self):
        train = _train_frame()
        model = _StubModel(lambda r: -99.0 * r[FEATURES.index("prior_games")])
        assert partial_dependence_inversions(model, train, "prior_games") == (0, 0)


class TestDominatedPairs:
    @staticmethod
    def _targets(rows):
        return pd.DataFrame(rows)

    def test_a_correctly_ordered_board_has_none(self):
        target = self._targets(
            [
                {
                    "prior_ppg": 20.0,
                    "prior_games": 17,
                    "prior_weighted_total": 360.0,
                    "preseason_ecr_rank": 2.0,
                },
                {
                    "prior_ppg": 15.0,
                    "prior_games": 17,
                    "prior_weighted_total": 300.0,
                    "preseason_ecr_rank": 8.0,
                },
            ]
        )
        dominated, comparisons, worst = dominated_pairs(np.array([300.0, 200.0]), target)
        assert comparisons == 1
        assert dominated == 0
        assert worst == 0.0

    def test_a_backwards_pair_is_counted_with_its_gap(self):
        """The reported 2026 case in miniature: strictly better on every constrained feature,
        projected lower."""
        target = self._targets(
            [
                {
                    "prior_ppg": 20.0,
                    "prior_games": 17,
                    "prior_weighted_total": 360.0,
                    "preseason_ecr_rank": 2.0,
                },
                {
                    "prior_ppg": 15.0,
                    "prior_games": 17,
                    "prior_weighted_total": 300.0,
                    "preseason_ecr_rank": 8.0,
                },
            ]
        )
        dominated, comparisons, worst = dominated_pairs(np.array([169.0, 266.0]), target)
        assert comparisons == 1
        assert dominated == 1
        assert worst == pytest.approx(97.0)

    def test_players_that_do_not_dominate_are_not_compared(self):
        """Better on production but worse on consensus rank is not a dominated pair -- the model
        is entitled to order those either way."""
        target = self._targets(
            [
                {
                    "prior_ppg": 20.0,
                    "prior_games": 17,
                    "prior_weighted_total": 360.0,
                    "preseason_ecr_rank": 40.0,
                },
                {
                    "prior_ppg": 15.0,
                    "prior_games": 17,
                    "prior_weighted_total": 300.0,
                    "preseason_ecr_rank": 3.0,
                },
            ]
        )
        dominated, comparisons, _ = dominated_pairs(np.array([169.0, 266.0]), target)
        assert comparisons == 0
        assert dominated == 0

    def test_a_single_row_board_is_handled(self):
        target = self._targets(
            [
                {
                    "prior_ppg": 1.0,
                    "prior_games": 1,
                    "prior_weighted_total": 1.0,
                    "preseason_ecr_rank": 1.0,
                }
            ]
        )
        assert dominated_pairs(np.array([1.0]), target) == (0, 0, 0.0)
