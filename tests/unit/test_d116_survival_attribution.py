"""Unit tests for D116's survival / opportunity-cost attribution
(`scripts/research/d116_survival_attribution.py`).

D116's conclusions rest on these properties, pinned here rather than asserted in prose:

  * each signal's pairwise call follows its stated direction (lower survival, higher
    multiplier / cost / score, better market rank = "disappears first"), and ties and undefined
    values are COUNTED separately rather than scored right or wrong;
  * the survival multiplier is exactly the one the shipped L0 score applies, None included;
  * the score factorisation is checked against the value_base the engine logs, and a mismatch
    raises instead of producing an attribution for a formula the engine does not use;
  * the H2 "which disappears first" truth is symmetric in the two players, never lets Alpha
    remove either, and censors players the field never takes;
  * the population is D115's C1 AND C2 exactly, including its exclusion of O == A.

Loaded the same way the D104/D114/D115 tests load their runners.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_squad.evaluation.draft_oracle import SHIPPED_TIER
from alpha_squad.league.context import resolve_league

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d116_survival_attribution")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d116_survival_attribution.py").read_text()
FORENSICS_SOURCE = (ROOT / "src" / "alpha_squad" / "evaluation" / "draft_forensics.py").read_text()


def _candidate(pid, *, score, fit=1.0, conf=0.8, surv=0.5, feas=None, oc=0.0, logged=None):
    reasons = [f"tier {SHIPPED_TIER}: x"]
    if logged is not None:
        reasons.append(f"value_base=msv_plus_weighted_vorp {logged:+.1f} pts")
    return {
        "player_id": pid,
        "fit_multiplier": fit,
        "confidence": conf,
        "survival_probability": surv,
        "feasibility_multiplier": feas,
        "opportunity_cost_pts": oc,
        "score": score,
        "reasons": reasons,
    }


class TestPairwiseCallDirections:
    def test_lower_survival_disappears_first(self):
        assert M.lower_goes_first(0.2, 0.8) == M.A_FIRST
        assert M.lower_goes_first(0.8, 0.2) == M.O_FIRST

    def test_higher_urgency_disappears_first(self):
        assert M.higher_goes_first(40.0, 10.0) == M.A_FIRST
        assert M.higher_goes_first(10.0, 40.0) == M.O_FIRST

    def test_equal_values_are_a_tie_not_a_call(self):
        assert M.lower_goes_first(1.0, 1.0) == M.TIE
        assert M.higher_goes_first(9.8, 9.8) == M.TIE

    def test_missing_values_are_undefined_not_a_call(self):
        assert M.lower_goes_first(None, 0.5) == M.UNDEFINED
        assert M.higher_goes_first(0.5, None) == M.UNDEFINED

    def test_same_position_opportunity_cost_is_always_a_tie(self):
        """OC is a per-POSITION figure; a same-position pair necessarily carries the same one."""
        pair = {
            "S_A": 0.3,
            "S_O": 0.6,
            "SM_A": 1.21,
            "SM_O": 1.12,
            "OC_A": 9.8,
            "OC_O": 9.8,
            "R_A": True,
            "R_O": True,
            "SC_A": 2.0,
            "SC_O": 1.0,
            "MR_A": 40.0,
            "MR_O": 50.0,
        }
        calls = M.predictions(pair)
        assert calls["OC"] == M.TIE
        assert calls["R"] == M.TIE
        assert calls["S"] == M.A_FIRST
        assert calls["SM"] == M.A_FIRST
        assert calls["SC"] == M.A_FIRST
        assert calls["MR"] == M.A_FIRST

    def test_replay_membership_missing_player_goes_first(self):
        pair = {
            "S_A": 0.5,
            "S_O": 0.5,
            "SM_A": 1.15,
            "SM_O": 1.15,
            "OC_A": 0.0,
            "OC_O": 0.0,
            "R_A": True,
            "R_O": False,
            "SC_A": 2.0,
            "SC_O": 1.0,
            "MR_A": None,
            "MR_O": 10.0,
        }
        calls = M.predictions(pair)
        assert calls["R"] == M.O_FIRST
        assert calls["MR"] == M.UNDEFINED


class TestSurvivalMultiplierIsTheShippedOne:
    def test_formula(self):
        assert M.survival_multiplier(1.0) == 1.0
        assert M.survival_multiplier(0.0) == pytest.approx(1.3)
        assert M.survival_multiplier(0.5) == pytest.approx(1.15)

    def test_none_is_neutral_exactly_as_score_candidate(self):
        assert M.survival_multiplier(None) == 1.0

    def test_the_bonus_is_quoted_from_the_engine_not_invented(self):
        assert M.SHIPPED_SURVIVAL_BONUS == 0.3
        assert "else 0.3" in FORENSICS_SOURCE
        assert "(1.0 + survival_bonus * (1.0 - survival))" in FORENSICS_SOURCE

    def test_multiplier_can_disagree_with_survival_only_through_none(self):
        """S=None is UNDEFINED for S but a neutral 1.0 for SM -- the one place they can differ."""
        assert M.lower_goes_first(None, 0.9) == M.UNDEFINED
        assert M.higher_goes_first(M.survival_multiplier(None), M.survival_multiplier(0.9)) == (
            M.O_FIRST
        )


class TestTruths:
    def test_h2_earlier_removal_disappears_first(self):
        assert M.truth_first(3, 7) == M.A_FIRST
        assert M.truth_first(7, 3) == M.O_FIRST

    def test_h2_censoring(self):
        assert M.truth_first(None, 5) == M.O_FIRST
        assert M.truth_first(5, None) == M.A_FIRST
        assert M.truth_first(None, None) == M.TIE

    def test_h1_the_non_survivor_disappears_first(self):
        assert M.truth_next_pick(a_survives=True, o_survives=False) == M.O_FIRST
        assert M.truth_next_pick(a_survives=False, o_survives=True) == M.A_FIRST

    def test_h1_is_a_tie_on_every_c1_and_c2_pick(self):
        """The load-bearing structural fact: on D115's sequencing population both survive, so the
        next-pick truth never distinguishes them and ranking accuracy there is undefined."""
        assert M.truth_next_pick(a_survives=True, o_survives=True) == M.TIE

    def test_h2_separation_places_censored_players_past_the_end(self):
        pair = {"removed_A": (20, 3), "removed_O": None, "n_opp_remaining": 100}
        assert M.h2_separation(pair) == 101 - 3
        pair = {"removed_A": (20, 3), "removed_O": (40, 9), "n_opp_remaining": 100}
        assert M.h2_separation(pair) == 6


class TestScoring:
    def test_ties_and_undefined_are_counted_not_scored(self):
        preds = [M.A_FIRST, M.O_FIRST, M.TIE, M.UNDEFINED, M.O_FIRST]
        truths = [M.A_FIRST, M.A_FIRST, M.A_FIRST, M.O_FIRST, M.TIE]
        res = M.score_pairs(preds, truths)
        assert res["n"] == 5
        assert res["n_decisive"] == 2
        assert res["n_correct"] == 1
        assert res["accuracy"] == 0.5
        assert res["pred_tie"] == 1
        assert res["pred_undefined"] == 1
        assert res["truth_tie"] == 1
        assert res["pred_tie_rate"] == pytest.approx(2 / 5)

    def test_no_decisive_pairs_is_undefined_not_zero(self):
        res = M.score_pairs([M.TIE, M.A_FIRST], [M.A_FIRST, M.TIE])
        assert res["accuracy"] is None

    def test_misaligned_inputs_raise(self):
        with pytest.raises(ValueError):
            M.score_pairs([M.A_FIRST], [])

    def test_wilson_brackets_the_point_estimate(self):
        lo, hi = M.wilson(30, 50)
        assert lo < 0.6 < hi
        assert M.wilson(0, 0) is None

    def test_season_clustered_uses_k5_t(self):
        res = M.season_clustered({2021: 0.5, 2022: 0.6, 2023: 0.7, 2024: 0.4, 2025: 0.8})
        se = 0.15811388300841897 / math.sqrt(5)
        assert res["mean"] == pytest.approx(0.6)
        assert res["mde"] == pytest.approx(2.776 * se)

    def test_a_single_season_cannot_manufacture_an_interval(self):
        assert M.season_clustered({2021: 0.5})["ci"] is None

    def test_brier_and_ece(self):
        assert M.brier([1.0, 0.0], [True, False]) == 0.0
        err, table = M.ece([0.05, 0.05, 0.95, 0.95], [False, False, True, True])
        assert err == pytest.approx(0.05)
        assert {b["bin"] for b in table} == {0, 9}


class TestScoreFactorisation:
    def test_parts_reproduce_the_logged_value_base(self):
        # value_base 100, oc 10 -> additive 110; fit 1.1, conf 0.8, surv 0.5 (SM 1.15)
        score = 110 * 1.1 * 0.8 * 1.15
        parts = M.score_parts(
            _candidate("p", score=score, fit=1.1, conf=0.8, surv=0.5, oc=10.0, logged=100.0)
        )
        assert parts["value_base"] == pytest.approx(100.0)
        assert parts["sm"] == pytest.approx(1.15)

    def test_a_factorisation_the_engine_did_not_use_raises(self):
        score = 110 * 1.1 * 0.8 * 1.15
        with pytest.raises(M.UnreconstructibleError):
            M.score_parts(
                _candidate("p", score=score, fit=1.1, conf=0.8, surv=0.5, oc=10.0, logged=90.0)
            )

    def test_missing_confidence_uses_the_engines_0_7(self):
        parts = M.score_parts(_candidate("p", score=70.0, conf=None, surv=1.0, logged=100.0))
        assert parts["risk"] == 0.7
        assert parts["value_base"] == pytest.approx(100.0)

    def test_zero_confidence_leaves_the_additive_term_unknown(self):
        parts = M.score_parts(_candidate("p", score=0.0, conf=0.0, surv=1.0))
        assert parts["additive"] is None
        assert M.log_decomposition(parts, parts) is None

    def test_log_terms_sum_to_the_score_ratio(self):
        a = M.score_parts(_candidate("a", score=110 * 1.1 * 0.8 * 1.15, fit=1.1, surv=0.5, oc=10))
        o = M.score_parts(_candidate("o", score=90 * 1.0 * 0.9 * 1.3, conf=0.9, surv=0.0, oc=0))
        d = M.log_decomposition(a, o)
        assert sum(d.values()) == pytest.approx(
            math.log(a["additive"] * 1.1 * 0.8 * 1.15 / (90 * 0.9 * 1.3))
        )
        assert d["survival"] < 0  # O's lower survival pushed toward O

    def test_logged_value_base_parser(self):
        assert M.logged_value_base(["value_base=msv_plus_weighted_vorp +509.3 pts"]) == 509.3
        assert M.logged_value_base(["value_base=x -12.0 pts"]) == -12.0
        assert M.logged_value_base(["draft-aware replacement 1.0"]) is None


class TestPositionalDrop:
    def test_clamped_at_replacement_like_production(self):
        positions = {"a": "RB", "b": "RB", "c": "WR"}
        value = {"a": 50.0, "b": -20.0, "c": 5.0}
        assert M.positional_drop({"a", "b", "c"}, {"b", "c"}, positions, value, "RB") == 50.0
        # both below replacement -> no cost, as `positional_opportunity_cost` clamps
        value = {"a": -5.0, "b": -20.0}
        assert M.positional_drop({"a", "b"}, {"b"}, positions, value, "RB") == 0.0


def _synthetic_state(n_players: int = 300):
    league = resolve_league("target_league")
    positions = {}
    cycle = ["QB", "RB", "WR", "WR", "RB", "TE", "WR", "RB", "K", "DST"]
    for i in range(n_players):
        positions[f"p{i:03d}"] = cycle[i % len(cycle)]
    market_rank = {p: (positions[p], float(i + 1)) for i, p in enumerate(sorted(positions))}
    static = SimpleNamespace(market_rank=market_rank, positions=positions)
    state = {
        "overall_pick": 1,
        "available": set(positions),
        "opponents": {s: [] for s in range(2, league.teams + 1)},
    }
    return league, static, state


class TestOpponentExposure:
    def test_alpha_never_removes_either_player_and_market_order_decides(self):
        league, static, state = _synthetic_state()
        removed = M.opponent_exposure(state, static, league, 1, ("p000", "p005"))
        # Alpha is slot 1 and has just passed at overall 1; opponents take p000 at overall 2.
        assert removed["p000"] == (2, 1)
        assert removed["p005"][1] == 6
        assert M.truth_first(removed["p000"][1], removed["p005"][1]) == M.A_FIRST

    def test_symmetric_in_the_two_players(self):
        league, static, state = _synthetic_state()
        r1 = M.opponent_exposure(state, static, league, 1, ("p010", "p020"))
        r2 = M.opponent_exposure(state, static, league, 1, ("p020", "p010"))
        assert r1 == r2

    def test_alpha_seats_are_skipped(self):
        league, static, state = _synthetic_state()
        removed = M.opponent_exposure(state, static, league, 1, ("p008", "p009"))
        # Slot 1 picks at overall 1 and 20 in a 10-team snake: overall 20 is Alpha's, skipped.
        assert removed["p008"] == (10, 9)
        assert removed["p009"] == (11, 10)
        assert all(r[0] != 20 for r in removed.values())

    def test_remaining_opponent_picks_excludes_alphas_seats(self):
        league, _static, state = _synthetic_state()
        total = int(league.roster["roster_size"]) * league.teams
        assert M.opponent_picks_remaining(state, league, 1) == total - int(
            league.roster["roster_size"]
        )


class TestPopulationAndDiscipline:
    def test_c1_and_c2_requires_both_and_excludes_none(self):
        assert M.is_c1c2({"C1": True, "C2": True})
        assert not M.is_c1c2({"C1": True, "C2": False})
        assert not M.is_c1c2({"C1": True, "C2": None})  # O == A, excluded as in D115
        assert not M.is_c1c2({"C1": False, "C2": True})

    def test_o_fate(self):
        states = [
            {"available": {"o", "a", "x"}, "alpha_pick": "a"},
            {"available": {"o", "x"}, "alpha_pick": "x"},
            {"available": {"o"}, "alpha_pick": "o"},
        ]
        assert M.o_fate(states, 0, "o") == "alpha_took_O_later"
        states[1]["alpha_pick"] = "o"
        assert M.o_fate(states, 0, "o") == "alpha_took_O_next"
        states = [
            {"available": {"o", "a"}, "alpha_pick": "a"},
            {"available": set(), "alpha_pick": "z"},
        ]
        assert M.o_fate(states, 0, "o") == "opponent_took_O"

    def test_regret_terciles(self):
        assert M.regret_tercile(10.0, (50.0, 150.0)) == "T1 low"
        assert M.regret_tercile(100.0, (50.0, 150.0)) == "T2 mid"
        assert M.regret_tercile(200.0, (50.0, 150.0)) == "T3 high"

    def test_the_d115_population_is_read_not_redefined(self):
        assert '"C1_oracle_survives_to_next_pick"' in RUNNER_SOURCE
        assert '"C2_alpha_survives_if_oracle_taken"' in RUNNER_SOURCE
        assert "D115.replay_states" in RUNNER_SOURCE

    def test_artifacts_from_mixed_vintages_are_refused(self):
        assert "span more than one vintage" in RUNNER_SOURCE

    def test_the_rescored_state_must_reproduce_the_replay_pick(self):
        assert "re-scoring chose" in RUNNER_SOURCE

    def test_the_counterfactual_step_is_checked_against_d115s_c2(self):
        assert "disagrees with D115's C2" in RUNNER_SOURCE

    def test_no_tuning_or_fitting_anywhere(self):
        for forbidden in ("optimize", "minimize(", "grid_search", ".fit(", "GridSearch"):
            assert forbidden not in RUNNER_SOURCE

    def test_production_is_never_written(self):
        assert "read_only=True" in RUNNER_SOURCE
        assert "src_dirty" in RUNNER_SOURCE

    def test_the_uppercase_arm_name_d114_guards_is_absent(self):
        """D114/D115 guard a git-history search for a retired arm's uppercase name; D116 must not
        re-introduce the string or the guard starts matching this file."""
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()
