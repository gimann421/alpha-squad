"""D70 RB availability experiment (docs/RB_AVAILABILITY_PREREGISTRATION.md).

Structural tests only, written alongside the implementation before it was fitted against real
outcomes: the season-scope guard, the gate arithmetic (on synthetic per-season rows, not a real
fit), and the control-identity property of `rb_availability_static` outside the treated seasons.
Fitting against the real database happens separately, after these are green."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.rb_availability_experiment import (
    MAX_WORSE_SEASONS,
    TREATED_SEASONS,
    TREATMENT_FEATURES,
    TREATMENT_POSITION,
    _gate_projection_layer,
    fit_rb_availability_model,
    rb_availability_static,
)
from alpha_squad.features.availability import AVAILABILITY_FEATURES
from alpha_squad.models.established.season_level import FEATURES
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


class TestScope:
    def test_treatment_is_rb_only(self):
        assert TREATMENT_POSITION == "RB"

    def test_treated_seasons_match_the_preregistration(self):
        assert TREATED_SEASONS == (2023, 2024, 2025)

    def test_features_are_existing_plus_availability_with_nothing_else(self):
        assert [*FEATURES, *AVAILABILITY_FEATURES] == TREATMENT_FEATURES
        assert len(TREATMENT_FEATURES) == len(FEATURES) + 4

    @pytest.mark.parametrize("season", [2020, 2021, 2022, 2026])
    def test_fitting_outside_treated_seasons_raises(self, con, season):
        """Abandonment condition 6: 'do not treat 2021-2022 for power'. Structural, not a
        comment someone has to remember."""
        with pytest.raises(ValueError, match="TREATED_SEASONS"):
            fit_rb_availability_model(con, season)

    def test_insufficient_data_raises_rather_than_producing_a_prediction(self, con):
        """An empty in-memory DB has zero rows -- must fail loudly, not silently predict."""
        with pytest.raises(ValueError, match="insufficient data"):
            fit_rb_availability_model(con, 2023)


class TestGateArithmetic:
    """Gate math checked against constructed per-season rows -- not a real model fit."""

    def _rows(self, overrides: dict[int, dict] | None = None):
        base = [
            {
                "season": 2023,
                "treatment_mae": 50.0,
                "control_mae": 55.0,
                "treatment_rmse": 60.0,
                "control_rmse": 65.0,
                "treatment_mean_signed_residual": 5.0,
                "control_mean_signed_residual": 10.0,
                "b3_correlation": 0.3,
            },
            {
                "season": 2024,
                "treatment_mae": 48.0,
                "control_mae": 50.0,
                "treatment_rmse": 58.0,
                "control_rmse": 60.0,
                "treatment_mean_signed_residual": 8.0,
                "control_mean_signed_residual": 15.0,
                "b3_correlation": 0.4,
            },
            {
                "season": 2025,
                "treatment_mae": 52.0,
                "control_mae": 54.0,
                "treatment_rmse": 62.0,
                "control_rmse": 63.0,
                "treatment_mean_signed_residual": 6.0,
                "control_mean_signed_residual": 9.0,
                "b3_correlation": 0.2,
            },
        ]
        for row, patch in (overrides or {}).items():
            base[row].update(patch)
        return base

    def test_all_gates_pass_on_uniformly_better_rows(self):
        gates = _gate_projection_layer(self._rows())
        assert gates["B1_accuracy"]["passes"]
        assert gates["B2_bias_falls"]["passes"]
        assert gates["B3_availability_predicts_games"]["passes"]

    def test_b1_fails_when_pooled_mae_is_worse(self):
        rows = self._rows(
            {0: {"treatment_mae": 100.0}, 1: {"treatment_mae": 100.0}, 2: {"treatment_mae": 100.0}}
        )
        gates = _gate_projection_layer(rows)
        assert not gates["B1_accuracy"]["passes"]

    def test_b1_tolerates_at_most_max_worse_seasons(self):
        rows = self._rows({0: {"treatment_mae": 56.0}})  # only 1 season worse
        gates = _gate_projection_layer(rows)
        assert gates["B1_accuracy"]["seasons_worse_mae"] == 1
        assert MAX_WORSE_SEASONS == 1
        assert gates["B1_accuracy"]["passes"]  # exactly at the limit

    def test_b1_fails_beyond_max_worse_seasons(self):
        rows = self._rows(
            {0: {"treatment_mae": 56.0}, 1: {"treatment_mae": 51.0}}
        )  # 2 seasons worse
        gates = _gate_projection_layer(rows)
        assert gates["B1_accuracy"]["seasons_worse_mae"] == 2
        assert not gates["B1_accuracy"]["passes"]

    def test_b2_fails_if_any_single_season_bias_grows(self):
        """Conservative reading: pooled reduction is not enough if any individual treated
        season's |bias| increased."""
        rows = self._rows({0: {"treatment_mean_signed_residual": 20.0}})  # |20| > |10|
        gates = _gate_projection_layer(rows)
        assert not gates["B2_bias_falls"]["passes"]

    def test_b3_requires_positive_correlation_in_every_season(self):
        rows = self._rows({1: {"b3_correlation": -0.1}})
        gates = _gate_projection_layer(rows)
        assert not gates["B3_availability_predicts_games"]["passes"]

    def test_b3_treats_nan_correlation_as_a_failure(self):
        rows = self._rows({2: {"b3_correlation": float("nan")}})
        gates = _gate_projection_layer(rows)
        assert not gates["B3_availability_predicts_games"]["passes"]


class TestRBAvailabilityStatic:
    def test_outside_treated_seasons_returns_the_control_object_unchanged(self, con):
        """No fit is attempted for an untreated season -- the control `SeasonStatic` is
        returned as-is, the same identity-return pattern D68/D69's `_calibrated_static` uses."""
        sentinel = object()
        result = rb_availability_static(con, league=None, season=2022, control=sentinel)
        assert result is sentinel

        result = rb_availability_static(con, league=None, season=2026, control=sentinel)
        assert result is sentinel
