"""Unit tests for D119's power analysis and experiment gate
(`scripts/research/d119_market_correction_power.py`).

D119's decision rests on these properties, pinned here rather than asserted in prose:

  * the power function is a correct two-sided noncentral-t power (checked against Monte Carlo),
    symmetric in the effect's sign, and robust to scipy's NaN far tail;
  * the 80%-power MDE inverts it, and the CI half-width is this repository's D114 "MDE";
  * the season-SD model scales with sqrt(changed picks) and with the inflation factor;
  * the leave-one-arm-out variance check never feeds an arm its own inflation (that would
    reproduce it by construction);
  * the experiment mode REFUSES to run on NO-GO, and cannot silently run an improvised arm on GO;
  * the frozen treatment is D118's own slope with the intercept dropped, and nothing is tuned.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d119_market_correction_power")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d119_market_correction_power.py").read_text()


class TestPowerFunction:
    def test_size_at_zero_effect(self):
        assert M.power(0.0, 1.0) == pytest.approx(0.05, abs=1e-6)

    @pytest.mark.parametrize("effect", [1.0, 3.0, 5.0])
    def test_matches_monte_carlo(self, effect):
        rng = np.random.default_rng(7)
        k, sd = M.K_SEASONS, 2.0  # SE = sd / sqrt(k) = 1.0
        x = rng.normal(effect, sd, size=(100_000, k))
        t = x.mean(1) / (x.std(1, ddof=1) / math.sqrt(k))
        mc = float((np.abs(t) > M.t_crit(k)).mean())
        assert M.power(effect, 1.0) == pytest.approx(mc, abs=0.01)

    def test_symmetric_in_sign(self):
        assert M.power(-4.0, 1.0) == pytest.approx(M.power(4.0, 1.0))

    def test_no_nan_at_large_effects(self):
        """Regression: scipy's noncentral-t CDF returns NaN once the far tail underflows; the
        first D119 run crashed there."""
        for effect in (8.0, 20.0, 300.0):
            p = M.power(effect, 1.0)
            assert not math.isnan(p) and 0.0 <= p <= 1.0

    def test_mde_inverts_power(self):
        se = 2.5
        mde = M.mde_at_power(se)
        assert M.power(mde, se) == pytest.approx(M.TARGET_POWER, abs=1e-6)
        # roughly (t_.975 + t_.80) * SE for df = 3
        assert 4.0 * se < mde < 4.5 * se

    def test_ci_half_width_is_the_d114_convention(self):
        assert M.ci_half_width(1.0, k=5) == pytest.approx(2.776, abs=1e-3)
        assert M.ci_half_width(1.0, k=4) == pytest.approx(3.182, abs=1e-3)


class TestVarianceModel:
    def test_season_sd_scales_with_sqrt_changed_picks(self):
        a = M.season_sd(0.1, 60.0, 1.0)
        b = M.season_sd(0.4, 60.0, 1.0)
        assert b == pytest.approx(2 * a)

    def test_no_changes_means_no_variance(self):
        assert M.season_sd(0.0, 60.0, 2.0) == 0.0

    def test_inflation_multiplies(self):
        assert M.season_sd(0.2, 60.0, 2.0) == pytest.approx(2 * M.season_sd(0.2, 60.0, 1.0))

    def test_standard_error_uses_four_seasons(self):
        assert M.K_SEASONS == 4
        assert M.standard_error(0.2, 60.0, 1.0) == pytest.approx(M.season_sd(0.2, 60.0, 1.0) / 2)

    def _arm_rows(self, arm, deltas_by_season, changed_share=0.5):
        rows = []
        for season, deltas in deltas_by_season.items():
            for i, d in enumerate(deltas):
                rows.append(
                    {
                        "arm": arm,
                        "season": season,
                        "delta": d if i < len(deltas) * changed_share else 0.0,
                        "changed": i < len(deltas) * changed_share,
                    }
                )
        return rows

    def test_arm_variance_and_leave_one_out_never_use_own_inflation(self):
        rng = np.random.default_rng(1)
        rows = []
        for arm, scale in (("X2", 30.0), ("X3", 60.0), ("FP_ECR_Y1", 90.0)):
            rows += self._arm_rows(
                arm, {s: list(rng.normal(0, scale, 64)) for s in range(2021, 2026)}
            )
        var = M.arm_variance(rows)
        check = M.validate_variance_model(var)
        for arm in var:
            others = [v["inflation"] for a, v in var.items() if a != arm]
            assert check[arm]["inflation_from_other_arms"] == pytest.approx(sum(others) / 2)

    def test_the_validation_is_documented_as_leave_one_out(self):
        assert "LEAVE-ONE-ARM-OUT" in RUNNER_SOURCE


class TestCases:
    INPUTS = {
        "ECR<=200": {
            "flip_rate_all_pairs": 0.09,
            "flip_rate_close_pairs": 0.26,
            "flip_accuracy": 0.55,
            "gain_per_flip": 12.6,
            "gain_per_flip_ci": [-17.0, 45.3],
        }
    }
    VAR = {
        "X2": {"sigma_c": 55.0, "inflation": 1.6, "changed_rate": 0.08},
        "FP_ECR_Y1": {"sigma_c": 72.0, "inflation": 2.2, "changed_rate": 0.59},
    }

    def test_conservative_uses_the_largest_inflation_and_central_leverage(self):
        c = M.scenarios(self.INPUTS, self.VAR)
        assert c["conservative"]["infl"] == 2.2
        assert c["conservative"]["p_c"] == 0.26
        assert c["conservative"]["g"] == 12.6

    def test_go_favourable_uses_the_top_of_the_ci_and_no_inflation(self):
        c = M.scenarios(self.INPUTS, self.VAR)["go_favourable"]
        assert c["infl"] == 1.0 and c["g"] == 45.3 and c["p_c"] == 0.59

    def test_expected_counts_and_effect(self):
        res = M.evaluate_case(
            {"p_c": 0.25, "g": 12.0, "sigma_c": 60.0, "infl": 1.0}, spie_pts=3.0, flip_accuracy=0.55
        )
        assert res["expected_changed_picks"] == pytest.approx(64.0)
        assert res["expected_correct_changes"] == pytest.approx(0.55 * 64)
        assert res["expected_effect_per_pick"] == pytest.approx(3.0)
        assert res["expected_effect_per_draft"] == pytest.approx(48.0)
        assert res["draft_clustered_anticonservative"]["k"] == 16


class TestGate:
    def test_experiment_refuses_on_no_go(self, tmp_path, monkeypatch):
        (tmp_path / "d119_power.json").write_text(
            json.dumps(
                {"decision": "NO-GO", "decision_basis": {"power_at_spie": 0.08, "required": 0.8}}
            )
        )
        monkeypatch.setattr("sys.argv", ["d119", "--mode", "experiment", "--out", str(tmp_path)])
        with pytest.raises(M.NoGoError):
            M.main()

    def test_a_go_cannot_run_an_improvised_arm(self, tmp_path, monkeypatch):
        (tmp_path / "d119_power.json").write_text(
            json.dumps(
                {"decision": "GO", "decision_basis": {"power_at_spie": 0.9, "required": 0.8}}
            )
        )
        monkeypatch.setattr("sys.argv", ["d119", "--mode", "experiment", "--out", str(tmp_path)])
        with pytest.raises(M.UnreconstructibleError):
            M.main()

    def test_decision_threshold_is_power_not_the_d114_resolution(self):
        assert M.TARGET_POWER == 0.80
        assert "context only, never a threshold" in RUNNER_SOURCE


class TestFrozenTreatment:
    def test_the_signal_is_d118s_and_the_intercept_is_dropped(self):
        assert M.SIGNAL == "mkt_vs_model"
        assert "The INTERCEPT IS DROPPED" in RUNNER_SOURCE
        assert "refit does not reproduce D118's prediction" in RUNNER_SOURCE

    def test_no_tuning_anywhere(self):
        for forbidden in ("GridSearch", "cross_val", "for alpha in", "for threshold in"):
            assert forbidden not in RUNNER_SOURCE

    def test_2021_is_structurally_zero(self):
        assert "2021 has no prior season inside the window" in RUNNER_SOURCE

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()
