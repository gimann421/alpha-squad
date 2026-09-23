"""Unit tests for W7's pre-Friday opportunity instruments.

This is the phase most exposed to leakage -- it is *about* whether information existed before
Friday -- so the tests pin the properties a result would be silently wrong without:

  * the feature sets are exactly the pre-registered ones, and NEW genuinely excludes what Alpha
    already holds (otherwise the double-counting test is rigged);
  * **T_XFP's baselines are built from lagged REALIZED fantasy points, not lagged usage-expected
    points** -- the latter are Class B (a fitted model's output) and must not leak into the main
    test through the back door of a "simple baseline";
  * no main-test feature or feature SQL reads injury, market, ECR or Vegas data;
  * a forecast for season S is fitted only on seasons before S, and the imputation it uses comes
    only from the training fold;
  * missing values are recognised whether DuckDB hands them back as None or as NaN.

The expensive, data-dependent half -- that nulling every outcome at/after a week leaves every
predictor for that week unchanged -- lives in `scripts/research/w7_validity_gates.py` (G2).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.weekly import opportunity as op
from alpha_squad.models.established.features import FULL_FEATURES


class TestFeatureSetsArePreregistered:
    def test_s0_is_exactly_alphas_features(self):
        assert list(op.S0) == list(FULL_FEATURES)
        assert len(op.S0) == 11

    def test_new_is_the_nine_preregistered_class_a_features(self):
        assert op.NEW == (
            "opp_last1",
            "snap_pct_last1",
            "opp_trend",
            "opp_sd_last3",
            "air_yards_share_avg_last3",
            "carry_share_avg_last3",
            "weeks_since_last_game",
            "opponent_opp_allowed_prior",
            "depth_team_prior",
        )

    def test_new_contains_nothing_alpha_already_has(self):
        """If NEW overlapped S0, the double-counting test would compare Alpha to itself."""
        assert not set(op.NEW) & set(op.S0)

    def test_redundant_re_expresses_alpha_and_nothing_new(self):
        assert not set(op.REDUNDANT) & set(op.NEW)
        assert not set(op.REDUNDANT) & set(op.S0)
        # every redundant feature is a longer-window version of a series S0 already summarises
        for f in op.REDUNDANT:
            assert f.endswith("_avg_last5")
            assert f.replace("_avg_last5", "_avg_last3") in op.S0

    def test_class_b_is_isolated_from_every_main_set(self):
        assert op.CLASS_B == ("xfp_avg_last3",)
        for model in ("M_S0", "M_NEW", "M_RED", "M_CB"):
            assert not set(op.CLASS_B) & set(op.feature_columns(model))
        assert set(op.CLASS_B) <= set(op.feature_columns("M_B"))

    def test_the_forecast_models_use_the_preregistered_feature_lists(self):
        assert op.feature_columns("M_S0") == list(op.S0)
        assert op.feature_columns("M_NEW") == list(op.S0) + list(op.NEW)
        assert op.feature_columns("M_CB") == op.feature_columns("M_NEW")
        assert op.feature_columns("M_RED") == list(op.S0) + list(op.REDUNDANT)
        with pytest.raises(ValueError, match="unknown forecast model"):
            op.feature_columns("M_TUNED")

    def test_no_tuning_knobs_moved(self):
        assert op.RIDGE_ALPHA == 1.0
        assert op.CATBOOST_KWARGS == {
            "iterations": 200,
            "depth": 4,
            "learning_rate": 0.05,
            "verbose": False,
            "random_seed": 42,
            "loss_function": "RMSE",
        }
        assert op.WMEAN3_WEIGHTS == (0.5, 0.3, 0.2)
        assert op.MIN_OPPONENT_WEEKS == 3


class TestClassBCannotLeakThroughTheBaselines:
    def test_usage_target_baselines_use_realized_points_not_lagged_xfp(self):
        """Lagged usage-expected points are Class B. A 'last-game' baseline for T_XFP built from
        them would smuggle Class B information into the main test under a harmless name."""
        assert op.BASELINE_SOURCE["T_XFP"] == "fp"
        assert op.BASELINE_SOURCE["T_XFP_HALF"] == "fp_half"
        assert "xfp" not in op.BASELINE_SOURCE.values()

    def test_the_primary_target_is_the_quantity_the_oracle_ranked_by(self):
        assert op.PRIMARY_TARGET == "T_XFP"
        assert op.TARGETS["T_XFP"] == "y_xfp"
        for position in ("RB", "WR", "TE"):
            assert op.TARGETS_BY_POSITION[position][0] == "T_XFP"


class TestNoForbiddenSources:
    @pytest.mark.parametrize("token", ["ecr", "market", "vegas", "spread", "_injuries", "practice"])
    def test_feature_sql_never_reads_it(self, token):
        sql = (op._panel_sql() + op._opponent_sql()).lower()
        assert token not in sql

    def test_every_window_excludes_the_current_row(self):
        """Every aggregate frame ends at `1 PRECEDING`; nothing ends at `CURRENT ROW`."""
        sql = op._panel_sql() + op._opponent_sql()
        assert "CURRENT ROW" not in sql.upper()
        assert sql.count("1 PRECEDING") >= 7


class TestMissingValues:
    @pytest.mark.parametrize("value", [None, float("nan"), np.nan])
    def test_none_and_nan_are_both_missing(self, value):
        assert op._missing(value)

    def test_a_real_zero_is_not_missing(self):
        assert not op._missing(0.0)
        assert not op._missing(0)

    def test_mean_and_sd_skip_missing(self):
        assert op._mean([1.0, float("nan"), 3.0]) == 2.0
        assert op._sd([2.0, None, 4.0]) == pytest.approx(math.sqrt(2.0))
        assert op._sd([5.0]) is None
        assert op._mean([None, float("nan")]) is None


class TestWeightedBaseline:
    def test_full_weights(self):
        s = op._weighted(pd.Series([10.0]), pd.Series([20.0]), pd.Series([30.0]))
        assert s.iloc[0] == pytest.approx(0.5 * 10 + 0.3 * 20 + 0.2 * 30)

    def test_renormalises_when_history_is_short(self):
        s = op._weighted(pd.Series([10.0]), pd.Series([20.0]), pd.Series([np.nan]))
        assert s.iloc[0] == pytest.approx((0.5 * 10 + 0.3 * 20) / 0.8)

    def test_no_history_is_missing_not_zero(self):
        s = op._weighted(pd.Series([np.nan]), pd.Series([np.nan]), pd.Series([np.nan]))
        assert pd.isna(s.iloc[0])


def _synthetic_panel() -> pd.DataFrame:
    """A small panel whose target is exactly predictable from one feature -- except in 2023,
    where it is shifted by +100. A forecast for 2023 that has seen any 2023 row would learn that
    shift; one that has not, cannot."""
    rows = []
    rng = np.random.default_rng(0)
    for season in (2019, 2020, 2021, 2022, 2023):
        for i in range(60):
            x = float(rng.normal())
            shift = 100.0 if season == 2023 else 0.0
            row = {c: 0.0 for c in op.S0}
            row.update({c: float(rng.normal()) for c in op.NEW})
            row["opp_last1"] = x
            row.update(
                {
                    "player_id": f"p{season}_{i}",
                    "season": season,
                    "week": 1 + i % 17,
                    "position": "RB",
                    "y_opp": 3.0 * x + shift,
                }
            )
            for b in ("BL_LAST", "BL_MEAN3", "BL_WMEAN3", "BL_TREND"):
                row[f"T_OPP__{b}"] = x
            rows.append(row)
    return pd.DataFrame(rows)


class TestWalkForwardIsCausal:
    def test_a_season_is_never_used_to_forecast_itself(self, monkeypatch):
        monkeypatch.setattr(op, "MIN_TRAIN_SEASON", 2019)
        panel = _synthetic_panel()
        fc = op.walk_forward(panel, "RB", "T_OPP", "M_NEW", (2023,))
        mask = panel.season == 2023
        # A model that had seen 2023 would predict ~+100 on average. One that has not predicts ~0.
        assert abs(float(fc[mask].mean())) < 5.0

    def test_seasons_before_the_forecast_are_left_unpredicted(self, monkeypatch):
        monkeypatch.setattr(op, "MIN_TRAIN_SEASON", 2019)
        panel = _synthetic_panel()
        fc = op.walk_forward(panel, "RB", "T_OPP", "M_NEW", (2022,))
        assert fc[panel.season == 2022].notna().all()
        assert fc[panel.season != 2022].isna().all()

    def test_imputation_comes_from_the_training_fold_only(self):
        train = pd.DataFrame({"opp_last1": [1.0, 2.0, 3.0], **{c: [0.0] * 3 for c in op.S0}})
        pred = pd.DataFrame({"opp_last1": [np.nan, 1000.0], **{c: [0.0] * 2 for c in op.S0}})
        x_tr, x_pr = op._design(train, pred, list(op.S0) + ["opp_last1"])
        # the missing prediction row is filled with the TRAINING median (2.0), not anything
        # derived from the prediction rows (which would put it near 1000)
        assert x_pr["opp_last1"].iloc[0] == 2.0
        assert x_pr["opp_last1__missing"].tolist() == [1.0, 0.0]
        assert "opp_last1__missing" in x_tr

    def test_baselines_need_no_fit_and_fall_back_to_the_training_median(self, monkeypatch):
        monkeypatch.setattr(op, "MIN_TRAIN_SEASON", 2019)
        panel = _synthetic_panel()
        panel.loc[panel.index[-1], "T_OPP__BL_LAST"] = np.nan
        fc = op.walk_forward(panel, "RB", "T_OPP", "BL_LAST", (2023,))
        train = panel[(panel.season >= 2019) & (panel.season < 2023)]
        assert fc.iloc[-1] == pytest.approx(float(train["y_opp"].median()))
        assert fc.iloc[-2] == pytest.approx(panel["T_OPP__BL_LAST"].iloc[-2])

    def test_forecasts_are_deterministic(self, monkeypatch):
        monkeypatch.setattr(op, "MIN_TRAIN_SEASON", 2019)
        panel = _synthetic_panel()
        a = op.walk_forward(panel, "RB", "T_OPP", "M_NEW", (2022, 2023))
        b = op.walk_forward(panel, "RB", "T_OPP", "M_NEW", (2022, 2023))
        assert a.equals(b)
