"""Experiment N's pre-registration must be a real constraint, not decoration.

The properties tested here are the ones that make its results interpretable: the control is
provably D80's control, the gates are provably D80's gates (imported, not copied), and the two
estimated parameters are estimated on seasons strictly before the target -- if either could see
the target season, every arm using it would be leaking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation import projection_shrinkage as N
from alpha_squad.evaluation import projection_topboard as TB
from alpha_squad.models.established.season_level import FEATURES, TARGET_COLUMN


def _frame(seasons, n_per=40, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(n_per):
            prior = float(400 - 8 * i)
            rows.append(
                {
                    "player_id": f"p{i:03d}",
                    "target_season": s,
                    "prior_ppg": prior / 17.0,
                    "prior_games": 15.0,
                    "prior_weighted_total": prior,
                    "preseason_ecr_rank": float(i + 1),
                    TARGET_COLUMN: prior * 0.6 + rng.normal(0, 25),
                }
            )
    return pd.DataFrame(rows)


class TestTheGatesAreD80sGates:
    def test_thresholds_are_the_imported_objects_not_copies(self):
        assert N.MIN_TARGET_GAIN is TB.MIN_TARGET_GAIN
        assert N.TOLERANCE is TB.TOLERANCE
        assert N.PREREGISTERED_TIERS is TB.PREREGISTERED_TIERS
        assert N.PREREGISTERED_OVERALL_TIERS is TB.PREREGISTERED_OVERALL_TIERS
        assert N.PREREGISTERED_TARGET_SEASONS is TB.PREREGISTERED_TARGET_SEASONS


class TestTheControlIsD80sControl:
    def test_n0_delegates_to_h0_exactly(self):
        train, target = _frame([2020, 2021, 2022]), _frame([2023], seed=9)
        assert N.predict_arm("N0", train, target, "RB") == pytest.approx(
            TB._fit_predict("H0", train, target)
        )

    def test_an_unknown_arm_raises_rather_than_silently_falling_back(self):
        train, target = _frame([2020]), _frame([2021])
        with pytest.raises(ValueError, match="unknown arm"):
            N.predict_arm("N9", train, target, "RB")


class TestShrinkageBehaviour:
    def test_a_dense_neighbourhood_barely_moves_and_a_sparse_one_moves_a_lot(self):
        """The whole point of partial pooling: the shrink is driven by the evidence behind the
        estimate, not applied uniformly."""
        base = np.array([170.0, 170.0])
        out = N.shrinkage_predict(base, pooled_mean=210.0, n_near=np.array([300.0, 3.0]), k=10.0)
        assert abs(out[0] - 170.0) < 2.0
        assert out[1] > 195.0

    def test_it_never_moves_past_the_pooled_mean(self):
        out = N.shrinkage_predict(np.array([50.0, 400.0]), 210.0, np.array([0.0, 0.0]), k=10.0)
        assert out == pytest.approx([210.0, 210.0])

    def test_local_density_counts_the_window(self):
        train = np.array([100.0, 120.0, 140.0, 400.0])
        got = N.local_density(train, np.array([120.0, 400.0]), half_width=25.0)
        assert got.tolist() == [3.0, 1.0]

    def test_the_elite_tail_really_is_the_sparse_end_on_a_realistic_spread(self):
        train = _frame([2020, 2021, 2022])["prior_weighted_total"].to_numpy()
        density = N.local_density(train, np.array([150.0, 400.0]), N.NEIGHBOURHOOD_HALF_WIDTH)
        assert density[1] < density[0]


class TestEstimatedParametersAreWalkForward:
    def test_choosing_k_never_reads_the_target_season(self, monkeypatch):
        train = _frame([2019, 2020, 2021, 2022])
        seen: list[int] = []
        real = TB._fit_predict

        def spy(arm, tr, tg):
            seen.extend(int(s) for s in tg["target_season"].unique())
            return real(arm, tr, tg)

        monkeypatch.setattr(TB, "_fit_predict", spy)
        monkeypatch.setattr(N, "_fit_predict", spy)
        N._choose_k(train, "RB")
        assert seen and max(seen) < 2023

    def test_choosing_alpha_never_reads_the_target_season(self, monkeypatch):
        train = _frame([2019, 2020, 2021, 2022])
        seen: list[int] = []
        real = TB._fit_predict

        def spy(arm, tr, tg):
            seen.extend(int(s) for s in tg["target_season"].unique())
            return real(arm, tr, tg)

        monkeypatch.setattr(TB, "_fit_predict", spy)
        monkeypatch.setattr(N, "_fit_predict", spy)
        N._choose_alpha(train)
        assert seen and max(seen) < 2023

    def test_chosen_values_stay_inside_the_registered_grids(self):
        train = _frame([2019, 2020, 2021, 2022])
        assert N._choose_k(train, "RB") in N.SHRINK_K_GRID
        assert N._choose_alpha(train) in N.BLEND_ALPHA_GRID


class TestSimpleArmsRun:
    @pytest.mark.parametrize("arm", ["N1", "N2", "N3", "N4", "N5"])
    def test_every_arm_returns_one_finite_prediction_per_target_row(self, arm):
        train, target = _frame([2019, 2020, 2021, 2022]), _frame([2023], seed=3)
        out = N.predict_arm(arm, train, target, "RB")
        assert out.shape == (len(target),)
        assert np.isfinite(out).all()

    def test_isotonic_is_monotone_in_prior_production_by_construction(self):
        """The property D79 phase 3 could only get from a tree by also changing the loss."""
        train = _frame([2019, 2020, 2021])
        target = pd.DataFrame(
            {
                "prior_weighted_total": [100.0, 200.0, 300.0, 400.0],
                "prior_ppg": [6.0, 12.0, 18.0, 24.0],
                "prior_games": [15.0] * 4,
                "preseason_ecr_rank": [40.0, 20.0, 5.0, 1.0],
            }
        )
        out = N.predict_arm("N2", train, target, "RB")
        assert all(out[i] <= out[i + 1] + 1e-9 for i in range(len(out) - 1))

    def test_ols_extrapolates_past_the_training_range(self):
        """The property a depth-3 tree structurally cannot have, and the reason N1 exists."""
        train = _frame([2019, 2020])
        top = float(train["prior_weighted_total"].max())
        target = pd.DataFrame(
            {
                "prior_weighted_total": [top, top + 150.0],
                "prior_ppg": [top / 17.0, (top + 150.0) / 17.0],
                "prior_games": [15.0, 15.0],
                "preseason_ecr_rank": [1.0, 1.0],
            }
        )
        out = N.predict_arm("N1", train, target, "RB")
        assert out[1] > out[0]
        tree = TB._fit_predict("H0", train, target)
        assert tree[1] == pytest.approx(tree[0])


class TestFeatureContract:
    def test_the_arms_use_m6s_features_and_target(self):
        assert FEATURES == [
            "prior_ppg",
            "prior_games",
            "prior_weighted_total",
            "preseason_ecr_rank",
        ]
        assert TARGET_COLUMN
