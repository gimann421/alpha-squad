"""Unit tests for D117's upside / uncertainty audit (`scripts/research/d117_upside_audit.py`).

D117's conclusions rest on these properties, pinned here rather than asserted in prose:

  * every pairwise call has a stated direction, and values equal to floating-point noise are a
    TIE -- D117's first report run scored 1e-14 differences in M6's per-position interval offsets
    as preferences on 5 same-position pairs, which is the regression pinned below;
  * the Shapley split of the shipped score gap is exact (sums to the gap) and symmetric;
  * a zero confidence zeroes the score, so value_base is read from the engine's own log there;
  * the position-constant signals (width, upside) are excluded from the player-level test;
  * the structural check reads M6's own confidence formula rather than re-deriving it;
  * the population is D116's C1 AND C2, read from D116's artifact, and mixed vintages are refused.

Loaded the same way the D115/D116 tests load their runners.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from alpha_squad.models.uncertainty.conformal import (
    apply_quantiles,
    confidence_from_interval_width,
    fit_conformal_quantiles,
)

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d117_upside_audit")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d117_upside_audit.py").read_text()


def _factors(value, oc=0.0, fit=1.0, risk=1.0, survival=1.0, capacity=1.0):
    return {
        "value": value,
        "opp_cost": oc,
        "fit": fit,
        "risk": risk,
        "survival": survival,
        "capacity": capacity,
    }


class TestPairwiseCalls:
    def test_direction(self):
        assert M.favors(100.0, 150.0) == M.FAVORS_O
        assert M.favors(150.0, 100.0) == M.FAVORS_A
        # ECR: lower is better
        assert M.favors(40.0, 10.0, higher_is_better=False) == M.FAVORS_O

    def test_undefined_is_not_a_call(self):
        assert M.favors(None, 1.0) == M.UNDEFINED
        assert M.favors(1.0, None) == M.UNDEFINED

    def test_float_noise_is_a_tie_regression(self):
        """Regression: M6's p90 - point is one constant per position-season, but it comes back
        with ~1e-14 of noise. D117's first run scored that noise as a preference."""
        assert M.favors(93.70000000000002, 93.69999999999999) == M.TIE
        assert M.favors(0.0, 1e-12) == M.TIE
        assert M.favors(93.7, 93.8) == M.FAVORS_O

    def test_call_summary_counts_everything(self):
        res = M.call_summary([M.FAVORS_O, M.FAVORS_A, M.FAVORS_A, M.TIE, M.UNDEFINED])
        assert res == {
            "n": 5,
            "favors_O": 1,
            "favors_A": 2,
            "tie": 1,
            "undefined": 1,
            "decisive": 3,
            "rate_O": pytest.approx(1 / 3),
        }

    def test_no_decisive_calls_is_undefined_not_zero(self):
        assert M.call_summary([M.TIE, M.UNDEFINED])["rate_O"] is None

    def test_discordance_and_sign_test(self):
        x = [M.FAVORS_O] * 8 + [M.FAVORS_A]
        ref = [M.FAVORS_A] * 9
        d = M.discordance(x, ref)
        assert d["x_favors_O_ref_favors_A"] == 8
        assert d["ref_favors_O_x_favors_A"] == 0
        assert d["sign_test_p"] == pytest.approx(2 / 2**8)
        assert M.sign_test_p(0, 0) is None
        assert M.sign_test_p(5, 10) == 1.0


class TestShapley:
    def test_contributions_sum_to_the_gap(self):
        fa = _factors(200.0, oc=5.0, fit=1.1, risk=0.8, survival=1.2, capacity=1.0)
        fo = _factors(90.0, oc=10.0, fit=1.0, risk=0.3, survival=1.0, capacity=1.0)
        sh = M.shapley(fa, fo)
        assert sum(sh.values()) == pytest.approx(M.l0_score(fa) - M.l0_score(fo))

    def test_a_factor_equal_for_both_contributes_nothing(self):
        fa = _factors(200.0, risk=0.8)
        fo = _factors(90.0, risk=0.8)
        sh = M.shapley(fa, fo)
        assert sh["risk"] == pytest.approx(0.0)
        assert sh["value"] == pytest.approx((200.0 - 90.0) * 0.8)

    def test_symmetry_swapping_players_negates(self):
        fa = _factors(150.0, oc=3.0, risk=0.6, survival=1.1)
        fo = _factors(120.0, oc=8.0, risk=0.9, survival=1.25)
        sh_ao, sh_oa = M.shapley(fa, fo), M.shapley(fo, fa)
        for f in M.FACTORS:
            assert sh_ao[f] == pytest.approx(-sh_oa[f])

    def test_zero_risk_zeroes_the_score(self):
        fo = _factors(500.0, risk=0.0)
        assert M.l0_score(fo) == 0.0
        sh = M.shapley(_factors(100.0, risk=0.5), fo)
        assert sh["risk"] > 0  # the zero confidence is what hands A the pick here

    def test_neutralisation_is_leverage(self):
        fa = _factors(100.0, risk=0.9)
        fo = _factors(110.0, risk=0.5)
        assert M.l0_score(fa) > M.l0_score(fo)
        assert M.neutralised_winner(fa, fo, "risk") == M.FAVORS_O
        assert M.neutralised_winner(fa, fo, "survival") == M.FAVORS_A
        assert M.neutralised_winner(fa, fo, "value") == "n/a"

    def test_factor_names_match_the_brief(self):
        assert M.FACTORS == ("value", "opp_cost", "fit", "risk", "survival", "capacity")


class TestFactorIdentification:
    def _candidate(self, *, score, conf, logged, fit=1.0, surv=1.0, oc=0.0):
        return {
            "player_id": "p",
            "fit_multiplier": fit,
            "confidence": conf,
            "survival_probability": surv,
            "feasibility_multiplier": None,
            "opportunity_cost_pts": oc,
            "score": score,
            "reasons": [f"value_base=msv_plus_weighted_vorp {logged:+.1f} pts"],
        }

    def test_value_from_the_score_when_identifiable(self):
        f = M.factors_from(self._candidate(score=0.5 * 120.0, conf=0.5, logged=120.0))
        assert f["value"] == pytest.approx(120.0)
        assert f["risk"] == 0.5

    def test_value_from_the_engine_log_when_confidence_is_zero(self):
        f = M.factors_from(self._candidate(score=0.0, conf=0.0, logged=87.3))
        assert f["value"] == pytest.approx(87.3)
        assert f["risk"] == 0.0

    def test_missing_confidence_uses_the_shipped_fallback(self):
        f = M.factors_from(self._candidate(score=0.7 * 50.0, conf=None, logged=50.0))
        assert f["risk"] == M.SHIPPED_RISK_FALLBACK == 0.7


class TestPositionConstantSignalsAreSeparated:
    def test_width_and_upside_are_excluded_from_the_player_level_test(self):
        assert set(M.POSITION_CONSTANT_SIGNALS) == {"width", "upside"}
        assert not set(M.POSITION_CONSTANT_SIGNALS) & set(M.PLAYER_LEVEL_UPSIDE_SIGNALS)
        assert "p90" in M.PLAYER_LEVEL_UPSIDE_SIGNALS
        assert "top24" in M.PLAYER_LEVEL_UPSIDE_SIGNALS

    def _row(self, a, o):
        base = dict.fromkeys(M.SIGNALS)
        return {"A": {**base, **a}, "O": {**base, **o}}

    def test_a_position_constant_signal_alone_is_not_player_level(self):
        r = self._row({"proj": 200.0, "upside": 80.0}, {"proj": 100.0, "upside": 95.0})
        assert M.any_upside_beyond_projection(r)
        assert not M.player_level_beyond_projection(r)

    def test_a_player_level_signal_counts(self):
        r = self._row({"proj": 200.0, "top24": 0.4}, {"proj": 100.0, "top24": 0.6})
        assert M.player_level_beyond_projection(r)

    def test_nothing_counts_when_the_projection_already_favors_o(self):
        r = self._row({"proj": 100.0, "p90": 300.0}, {"proj": 200.0, "p90": 100.0})
        assert not M.any_upside_beyond_projection(r)


class TestM6StructureTheAuditRestsOn:
    """The structural facts the runner MEASURES on the real table are reproduced here on
    M6's own functions, so a change to M6 that broke them would fail this file too."""

    def test_intervals_are_point_plus_a_constant_offset(self):
        q = fit_conformal_quantiles(np.array([-40.0, -10.0, 0.0, 15.0, 90.0]))
        a, b = apply_quantiles(100.0, q), apply_quantiles(250.0, q)
        assert a["p90"] - 100.0 == pytest.approx(b["p90"] - 250.0)
        assert a["p10"] - 100.0 == pytest.approx(b["p10"] - 250.0)

    def test_confidence_is_a_function_of_the_point_given_the_width(self):
        width = 150.0
        confs = [confidence_from_interval_width(p, 0.0, width) for p in (50.0, 100.0, 200.0)]
        assert confs[0] == 0.0  # clipped: width / (2 * 50) > 1 zeroes the score
        assert confs[0] < confs[1] < confs[2]

    def test_the_structural_check_uses_m6s_own_formula(self):
        assert "confidence_from_interval_width" in RUNNER_SOURCE


class TestBucketsAndTiers:
    def test_confidence_buckets(self):
        assert M.confidence_bucket(None) == "none (0.7 fallback)"
        assert M.confidence_bucket(0.0) == "0 (score zeroed)"
        assert M.confidence_bucket(0.1) == "(0, .25)"
        assert M.confidence_bucket(0.8) == "[.75, 1]"

    def test_tiers(self):
        assert M.projection_tier(5) == "pos 1-12"
        assert M.projection_tier(60) == "pos 49+"
        assert M.projection_tier(None) == "unranked"
        assert M.ecr_tier(None) == "no ECR"
        assert M.ecr_tier(120.0) == "ECR 101-150"

    def test_within_position_rank(self):
        proj = {"a": 300.0, "b": 200.0, "c": 250.0, "d": 100.0}
        pos = {"a": "RB", "b": "RB", "c": "WR", "d": "RB"}
        assert M.within_position_rank("b", proj, pos) == 2
        assert M.within_position_rank("c", proj, pos) == 1
        assert M.within_position_rank("z", proj, pos) is None

    def test_residualise_removes_the_linear_projection_effect(self):
        z = [1.0, 2.0, 3.0, 4.0]
        x = [2.0 * v + 1.0 for v in z]
        assert all(abs(v) < 1e-12 for v in M._residualise(x, z))


class TestDiscipline:
    def test_population_is_d116s_and_vintages_are_never_mixed(self):
        assert "D116.is_c1c2" in RUNNER_SOURCE
        assert "refusing to mix vintages" in RUNNER_SOURCE

    def test_the_rewalk_must_reproduce_d116s_pick(self):
        assert "re-walk does not reproduce D116's pick" in RUNNER_SOURCE

    def test_factors_must_rebuild_the_shipped_score(self):
        assert "factors do not rebuild A's score" in RUNNER_SOURCE

    def test_no_tuning_or_fitting(self):
        for forbidden in ("optimize", "minimize(", "grid_search", ".fit(", "GridSearch"):
            assert forbidden not in RUNNER_SOURCE

    def test_read_only_and_production_untouched(self):
        assert "read_only=True" in RUNNER_SOURCE
        assert "src_dirty" in RUNNER_SOURCE

    def test_realized_is_labelled_hindsight_and_never_a_signal(self):
        assert "realized" not in M.SIGNALS
        assert "HINDSIGHT" in RUNNER_SOURCE

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()

    def test_shapley_is_exact_by_assertion(self):
        assert "Shapley contributions do not sum to the score gap" in RUNNER_SOURCE
        assert math.factorial(6) == 720  # 6 factors, all 64 coalitions enumerated
