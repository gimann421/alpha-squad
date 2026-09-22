"""Unit tests for W6's research arms.

The experiment's entire validity rests on **one thing changing**. These tests pin that, cheaply
and without a database:

  * the arm table differs from production only in `loss_function`, and `BASE_KWARGS` carries
    every other hyperparameter verbatim from `MODEL_SPECS["ml_catboost"]`;
  * the primary arm is fixed, and is the one the pre-registration names;
  * the control-versus-production comparison reports *how* it differs, not just whether, because
    a handful of missing keys, a uniform epsilon and a wide spread are three different diagnoses.

The expensive half of the contract -- that retraining with MAE reproduces the stored production
predictions -- needs the real database and lives in `scripts/research/w6_validity_gates.py`, where
it runs before any arm result is interpreted.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.weekly import arms
from alpha_squad.models.established.train import MODEL_SPECS


class TestOnlyTheLossChanges:
    def test_base_kwargs_match_production_exactly_apart_from_the_loss(self):
        _cls, production_kwargs, _features = MODEL_SPECS["ml_catboost"]
        expected = {k: v for k, v in production_kwargs.items() if k != "loss_function"}
        assert dict(arms.BASE_KWARGS) == dict(expected)

    def test_base_kwargs_carries_no_loss_of_its_own(self):
        """If it did, the per-arm loss would be silently overridden or duplicated."""
        assert "loss_function" not in arms.BASE_KWARGS

    def test_the_control_arm_uses_productions_loss(self):
        _cls, production_kwargs, _features = MODEL_SPECS["ml_catboost"]
        assert arms.ARM_LOSS[arms.CONTROL_ARM] == production_kwargs["loss_function"] == "MAE"

    def test_the_arms_use_productions_features_and_target(self):
        from alpha_squad.models.established.features import FULL_FEATURES, TARGET_COLUMN

        _cls, _kwargs, production_features = MODEL_SPECS["ml_catboost"]
        assert production_features == FULL_FEATURES
        assert len(FULL_FEATURES) == 11
        assert TARGET_COLUMN == "target_fantasy_points_ppr"

    def test_the_arm_table_is_the_preregistered_one(self):
        assert arms.ARMS == ("A_MAE", "B0_RMSE", "B1_Q60", "B2_Q70", "B3_Q80")
        assert arms.ARM_LOSS["B1_Q60"] == "Quantile:alpha=0.6"
        assert arms.ARM_LOSS["B2_Q70"] == "Quantile:alpha=0.7"
        assert arms.ARM_LOSS["B3_Q80"] == "Quantile:alpha=0.8"

    def test_the_primary_arm_is_fixed_and_is_an_upper_quantile(self):
        assert arms.PRIMARY_ARM == "B2_Q70"
        assert arms.ARM_LOSS[arms.PRIMARY_ARM].startswith("Quantile:alpha=0.7")

    def test_rmse_is_present_as_the_discriminating_control(self):
        """Without it, a win for an upper quantile cannot be separated from
        'anything other than MAE helps'."""
        assert arms.ARM_LOSS["B0_RMSE"] == "RMSE"

    def test_an_unknown_arm_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="unknown arm"):
            arms.train_arm(None, "B9_Q99")

    def test_the_walk_forward_window_matches_production(self):
        from alpha_squad.models.established.train import MIN_TRAINING_ROWS

        assert arms.MIN_TRAIN_SEASON == 2015
        assert arms.TRAIN_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert MIN_TRAINING_ROWS == 50


class TestComparisonToProduction:
    def _pred(self, by_key):
        return arms.ArmPredictions(
            arm="A_MAE", loss="MAE", by_key=by_key, by_position={}, skipped=[]
        )

    def test_an_exact_match_reports_exactly_that(self):
        stored = {("p1", 2024, 1): 9.5, ("p2", 2024, 1): 3.25}
        out = arms.compare_to_production(self._pred(dict(stored)), stored)
        assert out["exact_matches"] == 2
        assert out["exact_share"] == 1.0
        assert out["max_abs_diff"] == 0.0
        assert out["only_in_trained"] == 0 and out["only_in_stored"] == 0

    def test_a_universe_mismatch_is_visible_as_key_counts_not_as_a_diff(self):
        """A re-implementation that predicts the wrong rows must not be able to hide behind a
        small max-abs-diff on the rows it happens to share."""
        stored = {("p1", 2024, 1): 9.5, ("p2", 2024, 1): 3.25}
        out = arms.compare_to_production(self._pred({("p1", 2024, 1): 9.5}), stored)
        assert out["max_abs_diff"] == 0.0
        assert out["only_in_stored"] == 1
        assert out["n_shared"] == 1

    def test_a_floating_point_epsilon_is_distinguishable_from_a_wrong_model(self):
        stored = {("p1", 2024, 1): 9.5, ("p2", 2024, 1): 3.25}
        tiny = arms.compare_to_production(
            self._pred({("p1", 2024, 1): 9.5 + 1e-12, ("p2", 2024, 1): 3.25}), stored
        )
        wrong = arms.compare_to_production(
            self._pred({("p1", 2024, 1): 14.0, ("p2", 2024, 1): 1.0}), stored
        )
        assert tiny["max_abs_diff"] < 1e-9
        assert tiny["exact_matches"] == 1
        assert wrong["max_abs_diff"] > 2.0
        assert wrong["exact_matches"] == 0

    def test_for_week_returns_only_that_week(self):
        p = self._pred({("p1", 2024, 1): 1.0, ("p2", 2024, 2): 2.0, ("p3", 2023, 1): 3.0})
        assert p.for_week(2024, 1) == {"p1": 1.0}
        assert p.for_week(2024, 2) == {"p2": 2.0}
        assert p.for_week(2022, 1) == {}
