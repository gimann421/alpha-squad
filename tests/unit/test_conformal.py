"""Unit tests for the split-conformal uncertainty primitives against hand-computed expected
values and synthetic data."""

from __future__ import annotations

import numpy as np
import pytest

from alpha_squad.models.uncertainty.conformal import (
    apply_quantiles,
    confidence_from_interval_width,
    fit_conformal_quantiles,
    monte_carlo_top_n_probabilities,
)


class TestFitConformalQuantiles:
    def test_median_of_symmetric_residuals_is_near_zero(self):
        residuals = np.array([-10.0, -5.0, 0.0, 5.0, 10.0])
        q = fit_conformal_quantiles(residuals)
        assert q[0.50] == pytest.approx(0.0)

    def test_quantiles_are_monotonically_increasing(self):
        residuals = np.array([-20.0, -8.0, -3.0, 0.0, 4.0, 9.0, 22.0])
        q = fit_conformal_quantiles(residuals)
        levels = [0.10, 0.25, 0.50, 0.75, 0.90]
        values = [q[level] for level in levels]
        assert values == sorted(values)

    def test_asymmetric_skewed_residuals_produce_asymmetric_quantiles(self):
        """Right-skewed residuals (a few large positive outliers, no large negative ones)
        must produce a p90 offset that is bigger in magnitude than the p10 offset — the
        whole point of using signed quantiles instead of a symmetric margin."""
        residuals = np.array([-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 50.0, 80.0])
        q = fit_conformal_quantiles(residuals)
        assert abs(q[0.90]) > abs(q[0.10])


class TestApplyQuantiles:
    def test_offsets_are_added_to_the_point_prediction(self):
        offsets = {0.10: -20.0, 0.25: -10.0, 0.50: 0.0, 0.75: 10.0, 0.90: 20.0}
        result = apply_quantiles(100.0, offsets)
        assert result == {"p10": 80.0, "p25": 90.0, "median": 100.0, "p75": 110.0, "p90": 120.0}


class TestConfidenceFromIntervalWidth:
    def test_zero_width_interval_is_maximally_confident(self):
        assert confidence_from_interval_width(100.0, 100.0, 100.0) == pytest.approx(1.0)

    def test_very_wide_interval_is_clamped_to_zero_not_negative(self):
        assert confidence_from_interval_width(10.0, -1000.0, 1000.0) == pytest.approx(0.0)

    def test_confidence_is_always_in_unit_interval(self):
        for point, p10, p90 in [(50.0, 40.0, 60.0), (0.0, -5.0, 5.0), (200.0, 199.0, 201.0)]:
            c = confidence_from_interval_width(point, p10, p90)
            assert 0.0 <= c <= 1.0


class TestMonteCarloTopNProbabilities:
    def test_clear_favorite_has_higher_top12_probability_than_clear_underdog(self):
        predictions = {"star": 300.0, "scrub": 20.0, **{f"mid{i}": 100.0 + i for i in range(20)}}
        residuals = np.random.default_rng(1).normal(0, 15, size=500)
        result = monte_carlo_top_n_probabilities(predictions, residuals, n_draws=1000)
        assert result["star"]["top12_prob"] > result["scrub"]["top12_prob"]
        assert result["star"]["top12_prob"] > 0.9

    def test_probabilities_are_between_zero_and_one(self):
        predictions = {f"p{i}": float(i) for i in range(30)}
        residuals = np.random.default_rng(2).normal(0, 10, size=200)
        result = monte_carlo_top_n_probabilities(predictions, residuals, n_draws=500)
        for probs in result.values():
            assert 0.0 <= probs["top12_prob"] <= 1.0
            assert 0.0 <= probs["top24_prob"] <= 1.0
            assert probs["top24_prob"] >= probs["top12_prob"]

    def test_fewer_than_two_players_returns_none_probabilities(self):
        result = monte_carlo_top_n_probabilities({"only": 50.0}, np.array([1.0, -1.0]))
        assert result["only"]["top12_prob"] is None
