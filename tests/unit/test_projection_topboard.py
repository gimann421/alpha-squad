"""Unit tests for the D80 top-of-board phase (`evaluation/projection_topboard.py`).

The load-bearing tests are the ones that guard the *instrument*, not the result: H0 must be the
shipped estimator, tiers must be cut by an exogenous key so all arms are scored on the same
players, and each gate must actually fire on the failure it exists to catch. A phase whose
control is not production, or whose tiers are chosen per-arm, measures nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.projection_topboard import (
    ARM_DESCRIPTIONS,
    H_ARM_SPEC,
    H_ARMS,
    MAX_ECR_SPEARMAN_GAIN,
    MIN_TARGET_GAIN,
    MONOTONE_DIRECTIONS,
    PREREGISTERED_CONTROL,
    PREREGISTERED_OVERALL_TIERS,
    PREREGISTERED_TARGET_SEASONS,
    PREREGISTERED_TIERS,
    SHIPPED_ROW_SPECIFICATION,
    TOLERANCE,
    _new_model,
    evaluate_gates,
)
from alpha_squad.models.established.season_level import FEATURES, MODEL_SPECS


class TestPreRegistration:
    def test_the_control_is_the_shipped_model(self):
        assert PREREGISTERED_CONTROL == "H0"
        assert H_ARMS[0] == "H0"
        assert H_ARM_SPEC["H0"] == ("catboost", None, False)

    def test_the_control_matches_m6s_real_hyperparameters(self):
        """H0 must be production, not a lookalike. If M6's estimator is ever retuned, this test
        fails and the phase's control has to be re-derived rather than silently drifting."""
        shipped = MODEL_SPECS["ml_season_catboost"][1]
        params = _new_model("H0").get_params()
        for key in ("iterations", "depth", "learning_rate", "loss_function", "random_seed"):
            assert params[key] == shipped[key], key
        # the control must not carry the treatment's knob at all
        assert "l2_leaf_reg" not in params
        assert "monotone_constraints" not in params

    def test_every_arm_trains_on_the_shipped_row_specification(self):
        assert SHIPPED_ROW_SPECIFICATION == "Y1"

    def test_the_monotone_arm_has_an_unconstrained_library_control(self):
        """D79 phase 3 could only test monotonicity by also switching loss, which confounded the
        constraint with the loss penalty. H3 is the same library and loss as H4 without the
        constraint, so H4 - H3 isolates it."""
        lib3, _, mono3 = H_ARM_SPEC["H3"]
        lib4, _, mono4 = H_ARM_SPEC["H4"]
        assert lib3 == lib4 == "xgboost"
        assert mono3 is False and mono4 is True

    def test_both_xgboost_arms_use_the_shipped_mae_loss(self):
        for arm in ("H3", "H4"):
            assert _new_model(arm).get_params()["objective"] == "reg:absoluteerror"

    def test_prior_games_is_never_constrained(self):
        assert MONOTONE_DIRECTIONS["prior_games"] == 0

    def test_constraint_directions_match_feature_meaning(self):
        assert MONOTONE_DIRECTIONS["prior_ppg"] == 1
        assert MONOTONE_DIRECTIONS["prior_weighted_total"] == 1
        assert MONOTONE_DIRECTIONS["preseason_ecr_rank"] == -1

    def test_the_monotone_arm_passes_constraints_in_feature_order(self):
        expected = tuple(MONOTONE_DIRECTIONS[f] for f in FEATURES)
        assert _new_model("H4").get_params()["monotone_constraints"] == expected

    def test_every_arm_is_described_and_specified(self):
        assert set(ARM_DESCRIPTIONS) == set(H_ARMS) == set(H_ARM_SPEC)

    def test_unknown_arm_raises(self):
        with pytest.raises(ValueError, match="unknown arm"):
            _new_model("H9")

    def test_the_window_matches_the_earlier_phases(self):
        assert PREREGISTERED_TARGET_SEASONS == (2022, 2023, 2024, 2025)

    def test_the_user_facing_tiers_are_present(self):
        assert [t[0] for t in PREREGISTERED_TIERS["RB"]] == ["top10", "11_24", "25_60"]
        assert [t[0] for t in PREREGISTERED_TIERS["WR"]] == ["top10", "11_24", "25_60"]
        assert [t[0] for t in PREREGISTERED_TIERS["QB"]] == ["top10", "11_24", "25plus"]
        assert [t[0] for t in PREREGISTERED_TIERS["TE"]] == ["all"]
        assert [t[0] for t in PREREGISTERED_OVERALL_TIERS] == [
            "top12",
            "top24",
            "top50",
            "top100",
        ]


def _tiers(overrides: dict | None = None) -> pd.DataFrame:
    """A control/arm measurement frame where, by default, the arm equals the control exactly.
    Each test perturbs one cell so the gate under test is the only thing that can fire."""
    overrides = overrides or {}
    base = {
        ("RB", "top10"): 80.0,
        ("RB", "11_24"): 67.0,
        ("RB", "25_60"): 56.0,
        ("RB", "11_60"): 59.0,
    }
    rows = []
    for season in PREREGISTERED_TARGET_SEASONS:
        for (pos, tier), mae in base.items():
            for arm in ("H0", "H1"):
                value = overrides.get(
                    (arm, pos, tier, season), overrides.get((arm, pos, tier), mae)
                )
                rows.append(
                    {
                        "arm": arm,
                        "season": season,
                        "position": pos,
                        "tier": tier,
                        "n": 10,
                        "mae": value,
                        "rmse": value,
                        "bias": 10.0,
                        "spearman": 0.5,
                    }
                )
    return pd.DataFrame(rows)


def _extras(overrides: dict | None = None) -> pd.DataFrame:
    overrides = overrides or {}
    rows = []
    for season in PREREGISTERED_TARGET_SEASONS:
        for arm in ("H0", "H1"):
            rows.append(
                {
                    "arm": arm,
                    "season": season,
                    "pool_mae_QB": overrides.get((arm, "QB"), 54.0),
                    "pool_mae_WR": overrides.get((arm, "WR"), 37.0),
                    "pool_mae_TE": overrides.get((arm, "TE"), 26.0),
                    "pool_mae_ALL": overrides.get((arm, "ALL"), 39.0),
                    "ecr_spearman_RB": overrides.get((arm, "sp"), 0.928),
                    "ecr_spearman_WR": 0.94,
                    "ecr_spearman_QB": 0.93,
                }
            )
    return pd.DataFrame(rows)


def _gate(verdict, name_prefix):
    return next(g for g in verdict.gates if g.name.startswith(name_prefix))


class TestGatesFireOnWhatTheyGuard:
    def test_an_identical_arm_fails_only_the_target_gate(self):
        """An arm that changes nothing cannot improve the target, but must not trip any
        non-degradation gate."""
        v = evaluate_gates(_tiers(), _extras(), "H1")
        assert not _gate(v, "T1").passed
        for prefix in ("T2", "T3", "T4", "T7", "T8"):
            assert _gate(v, prefix).passed, prefix

    def test_t1_needs_the_full_preregistered_gain(self):
        just_under = evaluate_gates(
            _tiers({("H1", "RB", "top10"): 80.0 - MIN_TARGET_GAIN + 0.01}), _extras(), "H1"
        )
        assert not _gate(just_under, "T1").passed
        exactly = evaluate_gates(
            _tiers({("H1", "RB", "top10"): 80.0 - MIN_TARGET_GAIN}), _extras(), "H1"
        )
        assert _gate(exactly, "T1").passed

    def test_t2_rejects_buying_the_top_ten_with_the_next_fifty(self):
        """The user's hard requirement, and the whole point of the phase: a big top-10 gain paid
        for by 11-60 is NOT an improvement."""
        v = evaluate_gates(
            _tiers(
                {
                    ("H1", "RB", "top10"): 60.0,  # huge target gain
                    ("H1", "RB", "11_24"): 67.5,  # within per-tier tolerance
                    ("H1", "RB", "25_60"): 56.5,  # within per-tier tolerance
                    ("H1", "RB", "11_60"): 59.5,  # but combined got WORSE
                }
            ),
            _extras(),
            "H1",
        )
        assert _gate(v, "T1").passed
        assert not _gate(v, "T2").passed

    def test_t2_allows_a_genuinely_harmless_change(self):
        v = evaluate_gates(
            _tiers({("H1", "RB", "top10"): 70.0, ("H1", "RB", "11_60"): 58.9}), _extras(), "H1"
        )
        assert _gate(v, "T2").passed

    def test_t3_catches_damage_to_another_position(self):
        v = evaluate_gates(_tiers(), _extras({("H1", "WR"): 37.0 + TOLERANCE + 0.1}), "H1")
        assert not _gate(v, "T3").passed

    def test_t4_catches_pool_damage(self):
        v = evaluate_gates(_tiers(), _extras({("H1", "ALL"): 39.0 + TOLERANCE + 0.1}), "H1")
        assert not _gate(v, "T4").passed

    def test_t5_rejects_an_effect_carried_by_one_season(self):
        one_season = {("H1", "RB", "top10", s): 80.0 for s in PREREGISTERED_TARGET_SEASONS}
        one_season[("H1", "RB", "top10", 2025)] = 20.0
        v = evaluate_gates(_tiers(one_season), _extras(), "H1")
        assert _gate(v, "T1").passed  # the pooled mean looks excellent
        assert not _gate(v, "T5").passed  # ... and only one season produced it

    def test_t6_requires_the_gain_to_survive_dropping_any_season(self):
        one_season = {("H1", "RB", "top10", s): 80.0 for s in PREREGISTERED_TARGET_SEASONS}
        one_season[("H1", "RB", "top10", 2025)] = 20.0
        v = evaluate_gates(_tiers(one_season), _extras(), "H1")
        assert not _gate(v, "T6").passed

    def test_t7_disqualifies_an_arm_that_just_reproduces_consensus(self):
        v = evaluate_gates(
            _tiers({("H1", "RB", "top10"): 70.0}),
            _extras({("H1", "sp"): 0.928 + MAX_ECR_SPEARMAN_GAIN + 0.01}),
            "H1",
        )
        assert not _gate(v, "T7").passed

    def test_t8_catches_a_worse_top_end_bias(self):
        t = _tiers({("H1", "RB", "top10"): 70.0})
        t.loc[(t.arm == "H1") & (t.tier == "top10"), "bias"] = -40.0  # larger magnitude
        v = evaluate_gates(t, _extras(), "H1")
        assert not _gate(v, "T8").passed

    def test_the_control_itself_is_never_gated(self):
        v = evaluate_gates(_tiers(), _extras(), PREREGISTERED_CONTROL)
        assert v.gates == []
        assert not v.passed


class TestTiersAreExogenous:
    """Tiers are cut by preseason ECR, which no arm can influence. If they were cut by predicted
    rank, each arm would score itself on a different set of players and the paired comparison
    would become a selection effect."""

    def test_tier_bounds_do_not_reference_any_prediction(self):
        for tiers in PREREGISTERED_TIERS.values():
            for label, lo, hi in tiers:
                assert isinstance(lo, int) and isinstance(hi, int) and lo < hi, label

    def test_the_rb_tiers_partition_the_first_sixty_without_overlap(self):
        bounds = [(lo, hi) for label, lo, hi in PREREGISTERED_TIERS["RB"]]
        assert bounds == [(1, 11), (11, 25), (25, 61)]
        covered = [i for lo, hi in bounds for i in range(lo, hi)]
        assert covered == list(range(1, 61))
        assert len(covered) == len(set(covered))


class TestModelsFitAndPredict:
    @pytest.mark.parametrize("arm", H_ARMS)
    def test_every_arm_produces_a_non_degenerate_fit(self, arm):
        """Guards the D79-phase-3 failure mode, where a mis-specified arm silently fitted a
        near-constant model and the resulting metric looked like a real result."""
        rng = np.random.default_rng(0)
        n = 300
        X = np.column_stack(
            [
                rng.uniform(0, 25, n),
                rng.integers(1, 18, n).astype(float),
                rng.uniform(0, 400, n),
                rng.uniform(1, 999, n),
            ]
        )
        y = 0.7 * X[:, 2] + rng.normal(0, 25, n)
        model = _new_model(arm)
        model.fit(X, y)
        pred = np.asarray(model.predict(X), dtype=float)
        assert pred.std() > 0.2 * y.std(), f"{arm} fitted a near-constant model"
