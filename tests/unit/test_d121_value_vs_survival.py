"""Unit tests for D121's value-term vs survival attribution
(`scripts/research/d121_value_vs_survival.py`).

D121's conclusions rest on these properties, pinned here rather than asserted in prose:

  * the neutralisation re-ranking reproduces the engine's own ordering (max score, `player_id`
    tie key) and neutralises exactly one component for EVERY candidate;
  * DA-VORP is value_base - MSV exactly (shipped weight 1.0), and the draft-aware level each
    player is measured against is projection - DA-VORP;
  * the score-gap classes are mutually exclusive and follow the pre-registered rule, and every
    class maps to one of the brief's categories A-G;
  * the population filter is rounds 1-6 with RB->WR / RB->QB primary and the reverse as context;
  * exact value bases replace engine-implied ones only when they agree (1e-6 where the score
    identifies value_base, 0.051 where confidence 0 hides it).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d121_value_vs_survival")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d121_value_vs_survival.py").read_text()


def _f(value, oc=0.0, fit=1.0, risk=1.0, survival=1.0, capacity=1.0):
    return {
        "value": value,
        "opp_cost": oc,
        "fit": fit,
        "risk": risk,
        "survival": survival,
        "capacity": capacity,
    }


class TestReRanking:
    def test_argmax_is_the_engines_order(self):
        board = {"b": _f(100.0), "a": _f(100.0), "c": _f(90.0)}
        assert M.argmax_pick(board) == "a"  # tie on score -> lowest player_id, as the engine

    def test_neutralising_survival_can_flip_the_pick(self):
        board = {"rb": _f(100.0, survival=1.3), "wr": _f(120.0, survival=1.0)}
        assert M.argmax_pick(board) == "rb"
        assert M.argmax_pick(board, "survival") == "wr"

    def test_neutral_values(self):
        assert M.NEUTRAL == {
            "survival": 1.0,
            "opp_cost": 0.0,
            "fit": 1.0,
            "risk": 1.0,
            "capacity": 1.0,
        }
        f = _f(50.0, oc=10.0, fit=1.2)
        assert M.neutralised(f, "opp_cost")["opp_cost"] == 0.0
        assert M.neutralised(f, "opp_cost")["fit"] == 1.2  # only one component moves

    def test_the_value_term_is_never_a_neutralisation_arm(self):
        assert "value" not in M.COMPONENTS


class TestValueSplit:
    def test_da_vorp_is_value_base_minus_msv(self):
        cand = {"player_id": "p", "marginal_starter_value": 180.0, "projection": 180.0}
        s = M.value_split(cand, {"value": 250.0})
        assert s["da_vorp"] == pytest.approx(70.0)
        assert s["msv_equals_projection"] is True

    def test_msv_below_projection_when_the_slot_is_filled(self):
        cand = {"player_id": "p", "marginal_starter_value": 40.0, "projection": 180.0}
        assert M.value_split(cand, {"value": 100.0})["msv_equals_projection"] is False

    def test_missing_msv_raises(self):
        with pytest.raises(M.UnreconstructibleError):
            M.value_split(
                {"player_id": "p", "marginal_starter_value": None, "projection": 1.0},
                {"value": 1.0},
            )

    def test_the_shipped_weight_is_asserted(self):
        assert "DECISION_ARM_VORP_WEIGHT != 1.0" in RUNNER_SOURCE


class TestClasses:
    SHAP = {
        "value": 60.0,
        "opp_cost": 5.0,
        "fit": 10.0,
        "risk": 0.0,
        "survival": 25.0,
        "capacity": 0.0,
    }

    def test_large_value_disagreement(self):
        assert M.score_gap_class(1, self.SHAP, {}) == "1_large_value_disagreement"

    def test_small_value_amplified_by_survival(self):
        shap = {**self.SHAP, "value": 20.0, "survival": 60.0}
        assert M.score_gap_class(1, shap, {}) == "2_small_value_amplified_by_survival"

    def test_small_value_amplified_by_other(self):
        shap = {**self.SHAP, "value": 20.0, "fit": 60.0, "survival": 5.0}
        assert M.score_gap_class(1, shap, {}) == "2_small_value_amplified_by_other"

    def test_correct_value_overturned_by_survival(self):
        assert (
            M.score_gap_class(-1, self.SHAP, {"survival": True, "fit": True})
            == "3_correct_value_overturned_by_survival"
        )

    def test_correct_value_overturned_by_another_component(self):
        assert (
            M.score_gap_class(-1, self.SHAP, {"survival": False, "fit": True})
            == "4_correct_value_overturned_by_fit"
        )

    def test_combination(self):
        assert M.score_gap_class(-1, self.SHAP, {c: False for c in M.COMPONENTS}) == "5_combination"

    def test_every_producible_class_maps_to_a_category(self):
        produced = {
            "1_large_value_disagreement",
            "2_small_value_amplified_by_survival",
            "2_small_value_amplified_by_other",
            "3_correct_value_overturned_by_survival",
            "5_combination",
            *(f"4_correct_value_overturned_by_{c}" for c in M.COMPONENTS if c != "survival"),
        }
        assert produced == set(M.CATEGORY_OF_CLASS)
        assert set(M.CATEGORY_OF_CLASS.values()) <= {
            "A_value_construction",
            "B_survival",
            "C_opportunity_cost",
            "D_roster_fit",
            "E_risk",
            "F_capacity",
            "G_combination",
        }


class TestPopulation:
    def test_primary_and_context_flows(self):
        assert M.flow_of("RB", "WR", 3) == "PRIMARY RB->WR"
        assert M.flow_of("RB", "QB", 1) == "PRIMARY RB->QB"
        assert M.flow_of("WR", "RB", 6) == "CONTEXT WR->RB"
        assert M.flow_of("QB", "RB", 2) == "CONTEXT QB->RB"

    def test_outside_rounds_1_to_6_or_other_flows_are_excluded(self):
        assert M.flow_of("RB", "WR", 7) is None
        assert M.flow_of("WR", "TE", 2) is None
        assert M.flow_of("RB", "RB", 2) is None


class TestExactValueBases:
    def _setup(self, monkeypatch, level):
        monkeypatch.setattr(M, "consumption_replacement", lambda demand: lambda *a: {"RB": level})
        board = SimpleNamespace(
            consumption_demand={}, projections={}, positions={}, replacement_levels={"RB": 0.0}
        )
        cands = {"p": {"position": "RB", "marginal_starter_value": 200.0, "projection": 200.0}}
        return board, cands

    def test_replaces_with_the_exact_value_when_they_agree(self, monkeypatch):
        board, cands = self._setup(monkeypatch, level=120.0)
        factors = {"p": {**_f(280.0000001)}}
        M.exact_value_bases(factors, cands, board, None, {"available": set()})
        assert factors["p"]["value"] == pytest.approx(280.0)

    def test_raises_when_the_engine_used_a_different_value(self, monkeypatch):
        board, cands = self._setup(monkeypatch, level=120.0)
        factors = {"p": {**_f(275.0)}}
        with pytest.raises(M.UnreconstructibleError):
            M.exact_value_bases(factors, cands, board, None, {"available": set()})

    def test_zero_confidence_uses_the_logged_tolerance(self, monkeypatch):
        board, cands = self._setup(monkeypatch, level=120.0)
        factors = {"p": {**_f(280.04, risk=0.0)}}
        M.exact_value_bases(factors, cands, board, None, {"available": set()})
        assert factors["p"]["value"] == pytest.approx(280.0)


class TestReportPieces:
    def _row(self, vb_p, vb_o, v_p, v_o, flow="PRIMARY RB->QB"):
        return {
            "flow": flow,
            "season": 2023,
            "value_split_P": {
                "value_base": vb_p,
                "msv": vb_p / 2,
                "da_vorp": vb_p / 2,
                "msv_equals_projection": True,
            },
            "value_split_O": {
                "value_base": vb_o,
                "msv": vb_o / 2,
                "da_vorp": vb_o / 2,
                "msv_equals_projection": True,
            },
            "projection_P": 200.0,
            "projection_O": 250.0,
            "onestep_P": v_p,
            "onestep_O": v_o,
            "onestep_weekly_P": v_p,
            "onestep_weekly_O": v_o,
            "score_P": 10.0,
            "score_O": 5.0,
            "regret": v_o - v_p,
        }

    def test_two_by_two_places_the_critical_cell(self):
        rows = [self._row(300.0, 250.0, 1000.0, 1080.0), self._row(200.0, 250.0, 1000.0, 1020.0)]
        t = M.two_by_two(rows)
        assert t["value_prefers_P|onestep_prefers_O"]["n"] == 1
        assert t["value_prefers_P|onestep_prefers_O"]["regret"] == pytest.approx(80.0)
        assert t["value_prefers_O|onestep_prefers_O"]["n"] == 1

    def test_level_gap_is_projection_minus_da_vorp(self):
        rows = [self._row(300.0, 250.0, 1000.0, 1080.0)]
        vd = M.value_decomposition(rows)
        # level_O - level_P = (250 - 125) - (200 - 150) = 75
        assert vd["draft_aware_level_gap_O_minus_P"]["mean"] == pytest.approx(75.0)


class TestDiscipline:
    def test_reproduction_is_a_stop_condition(self):
        assert "-- STOP" in RUNNER_SOURCE
        assert "re-ranking from factors does not reproduce the engine" in RUNNER_SOURCE
        assert "ARM 4 rollout != D120's" in RUNNER_SOURCE

    def test_no_tuning_and_read_only(self):
        for forbidden in ("GridSearch", "for weight in", "for alpha in", "optimize("):
            assert forbidden not in RUNNER_SOURCE
        assert "read_only=True" in RUNNER_SOURCE
        assert "src_dirty" in RUNNER_SOURCE

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()
