"""Unit tests for D122's continuation-aware MSV audit
(`scripts/research/d122_continuation_aware_msv.py`).

D122's conclusions rest on these properties, pinned here rather than asserted in prose:

  * leave-one-out CA(c) = BL(final) - BL(final - c) with the production allocator, and exactly one
    player (possibly through a FLEX reshuffle) enters when c leaves -- or none, when the
    continuation left no eligible body, which is the case the amendment exists for;
  * the pairwise "otherwise" decomposition sums exactly to the one-step gap, by position and by
    slot, and never assumes a player's slot from his position;
  * the whole-board re-rank with a lazily evaluated CA is the exact argmax (brute force agrees)
    and refuses a CA above its proven bound;
  * the final roster is captured from the unmodified rollout's single scoring call;
  * the pre-registered A-D rule and the overcredit criterion behave as written.
"""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

from alpha_squad.league.context import resolve_league
from alpha_squad.league.replacement import best_lineup_points

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d122_continuation_aware_msv")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d122_continuation_aware_msv.py").read_text()
LEAGUE = resolve_league("target_league")  # QB1 RB2 WR2 TE1 FLEX2 K1 DST1, bench 6

POS = {
    "qb1": "QB",
    "rb1": "RB",
    "rb2": "RB",
    "rb3": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "wr3": "WR",
    "wr4": "WR",
    "wr5": "WR",
    "te1": "TE",
    "k1": "K",
    "d1": "DST",
}
PTS = {
    "qb1": 300.0,
    "rb1": 250.0,
    "rb2": 200.0,
    "rb3": 150.0,
    "wr1": 240.0,
    "wr2": 220.0,
    "wr3": 180.0,
    "wr4": 140.0,
    "wr5": 100.0,
    "te1": 120.0,
    "k1": 130.0,
    "d1": 110.0,
}
BASE = ["qb1", "rb1", "rb2", "wr1", "wr2", "wr3", "wr4", "te1", "k1", "d1"]


class TestLineup:
    def test_value_is_best_lineup_points_and_slots_come_from_the_allocator(self):
        value, slots = M.lineup(LEAGUE, BASE, PTS, POS)
        assert value == pytest.approx(best_lineup_points(LEAGUE, BASE, PTS, POS))
        assert slots["rb1"] == "RB" and slots["wr3"] == "FLEX" and slots["wr4"] == "FLEX"
        assert slots["d1"] == "DST"


class TestLeaveOneOut:
    def test_no_eligible_body_leaves_the_slot_empty_and_ca_equals_points(self):
        # Two RBs and two WRs in FLEX: removing rb1 leaves RB2 empty -- no bench RB exists.
        loo = M.leave_one_out(LEAGUE, BASE, "rb1", PTS, POS)
        assert loo["entrant"] is None
        assert loo["ca_msv"] == pytest.approx(PTS["rb1"])
        assert M.entrant_origin(None, [], loo["slot_in_final"]) == "no_entrant_slot_left_empty"

    def test_a_bench_body_enters_and_ca_is_the_difference(self):
        roster = [*BASE, "wr5"]
        loo = M.leave_one_out(LEAGUE, roster, "wr1", PTS, POS)
        # wr1 out: wr3 moves FLEX -> WR, wr5 enters the FLEX.
        assert loo["entrant"] == "wr5" and loo["entrant_slot"] == "FLEX"
        assert "wr3" in loo["reshuffled"]
        assert loo["ca_msv"] == pytest.approx(PTS["wr1"] - PTS["wr5"])

    def test_a_flex_rb_is_the_replacement_for_a_dedicated_rb(self):
        roster = [*BASE, "rb3", "wr5"]
        loo = M.leave_one_out(LEAGUE, roster, "rb1", PTS, POS)
        # FLEX was wr3 + rb3 (150 > wr4 140); removing rb1 moves rb3 to RB and the best bench
        # flex body, wr4, enters -- the replacement for an RB is a WR, through the FLEX.
        assert loo["entrant"] == "wr4" and loo["entrant_slot"] == "FLEX"
        assert loo["reshuffled"] == ["rb3"]
        assert loo["ca_msv"] == pytest.approx(PTS["rb1"] - PTS["wr4"])

    def test_a_bench_candidate_has_zero_ca(self):
        roster = [*BASE, "wr5"]
        loo = M.leave_one_out(LEAGUE, roster, "wr5", PTS, POS)
        assert loo["slot_in_final"] == M.BENCH and loo["ca_msv"] == pytest.approx(0.0)
        assert M.entrant_origin(None, [], M.BENCH) == "not_a_starter_in_final"

    def test_origin_distinguishes_rostered_from_continuation_bodies(self):
        assert M.entrant_origin("x", ["x"], "RB") == "rostered_at_state"
        assert M.entrant_origin("x", ["y"], "RB") == "drafted_by_continuation"


class TestPairwise:
    def test_groups_sum_to_the_gap_and_expose_the_otherwise_player(self):
        f_p = [*BASE]  # took rb1
        f_o = [p for p in BASE if p != "rb1"] + ["rb3", "wr5"]  # took wr5; drafted rb3 later
        pw = M.pairwise_otherwise(LEAGUE, f_p, f_o, "rb1", "wr5", PTS, POS)
        gap = M.lineup(LEAGUE, f_p, PTS, POS)[0] - M.lineup(LEAGUE, f_o, PTS, POS)[0]
        assert sum(pw["delta_by_position"].values()) == pytest.approx(gap)
        assert sum(pw["delta_by_slot"].values()) == pytest.approx(gap)
        # The continuation would otherwise have started rb3 at RB.
        assert [x["player_id"] for x in pw["otherwise_for_P_position"]] == ["rb3"]
        assert pw["P_increment_over_otherwise"] == pytest.approx(PTS["rb1"] - PTS["rb3"])
        # leave-one-out on f_p cannot see rb3: CA(rb1) is his full points.
        assert M.leave_one_out(LEAGUE, f_p, "rb1", PTS, POS)["ca_msv"] == pytest.approx(250.0)

    def test_attach_pairwise_terms_keeps_da_vorp_and_the_other_factors(self):
        f = {
            "value": 0.0,
            "opp_cost": 0.0,
            "fit": 1.0,
            "risk": 0.5,
            "survival": 1.0,
            "capacity": 1.0,
        }
        rp = {"da_vorp": 10.0, "factors": f}
        ro = {"da_vorp": -5.0, "factors": f}
        M.attach_pairwise_terms(
            rp, ro, {"P_increment_over_otherwise": 100.0, "O_increment_over_otherwise": 80.0}
        )
        assert rp["pw_value"] == pytest.approx(110.0) and ro["pw_value"] == pytest.approx(75.0)
        assert rp["pw_score"] == pytest.approx(55.0)


class TestRerank:
    @staticmethod
    def _board(seed: int, n: int = 40):
        rng = random.Random(seed)
        factors, da, pts, ca = {}, {}, {}, {}
        for i in range(n):
            pid = f"p{i:02d}"
            pts[pid] = rng.uniform(-1.0, 300.0)
            ca[pid] = pts[pid] - rng.uniform(0.0, 200.0)
            da[pid] = rng.uniform(-50.0, 100.0)
            factors[pid] = {
                "value": 0.0,
                "opp_cost": rng.uniform(0.0, 20.0),
                "fit": rng.uniform(0.5, 1.2),
                "risk": rng.choice([0.0, rng.uniform(0.2, 1.0)]),
                "survival": rng.uniform(1.0, 1.3),
                "capacity": 1.0,
            }
        return factors, da, pts, ca

    @pytest.mark.parametrize("seed", range(20))
    def test_lazy_argmax_equals_brute_force(self, seed):
        factors, da, pts, ca = self._board(seed)
        slack = 1.0
        evaluated = []

        def ca_of(pid):
            evaluated.append(pid)
            return ca[pid]

        pick, n = M.rerank(factors, da, pts, slack, ca_of)
        brute = min(
            factors,
            key=lambda p: (-M.D117.l0_score({**factors[p], "value": ca[p] + da[p]}), p),
        )
        assert pick == brute
        assert n == len(evaluated) <= len(factors)

    def test_a_ca_above_its_bound_is_refused(self):
        factors, da, pts, _ = self._board(0, n=3)
        with pytest.raises(M.UnreconstructibleError):
            M.rerank(factors, da, pts, 0.0, lambda pid: pts[pid] + 10.0)


class TestContinuationCapture:
    def test_the_final_roster_is_captured_from_the_single_scoring_call(self, monkeypatch):
        def fake_roll(con, league, season, static, slot, state, pick, realized, scorer):
            return scorer([*state["drafted"], pick, "later"], realized)[0]

        monkeypatch.setattr(M.D115, "roll_from_state", fake_roll)
        sl = lambda d, a: (float(len(d)), 0.0, 0)  # noqa: E731
        wk = lambda d, a: (2.0 * len(d), 0.0, 0)  # noqa: E731
        ctx = (None, None, 2023, None, 1, {"drafted": ["a"]}, {}, sl, wk)
        run = M.Continuation(ctx)("b")
        assert run["final"] == ["a", "b", "later"]
        assert run["v_sl"] == 3.0 and run["v_wk"] == 6.0

    def test_two_scoring_calls_are_refused(self, monkeypatch):
        def fake_roll(con, league, season, static, slot, state, pick, realized, scorer):
            scorer(["x"], realized)
            return scorer(["y"], realized)[0]

        monkeypatch.setattr(M.D115, "roll_from_state", fake_roll)
        sl = lambda d, a: (1.0, 0.0, 0)  # noqa: E731
        ctx = (None, None, 2023, None, 1, {"drafted": []}, {}, sl, sl)
        with pytest.raises(M.UnreconstructibleError):
            M.Continuation(ctx)("b")


class TestStatistics:
    def test_season_ci_reports_both_mdes(self):
        s = M.season_ci({2021: 1.0, 2022: 3.0, 2023: 2.0, 2024: 4.0, 2025: 0.0})
        assert s["k"] == 5 and s["mean"] == pytest.approx(2.0)
        assert s["ci"][0] == pytest.approx(2.0 - s["mde_half"])
        assert s["mde_80"] > s["mde_half"] > 0

    def test_rank_correlations(self):
        assert M.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
        assert M.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
        assert M.pearson([1, 2], [1, 2]) is None

    def test_gap_error(self):
        e = M.gap_error([10.0, -5.0, 3.0], [8.0, 5.0, 3.0])
        assert e["sign_agreement"] == 2
        assert e["mean_abs_error"] == pytest.approx(4.0)


class TestClassification:
    FLOWS = ("PRIMARY RB->QB", "PRIMARY RB->WR")
    FMTS = ("target_league", "dynasty_1qb")

    def _oc(self, qb, wr):
        return {(f, m): (qb if f == self.FLOWS[0] else wr) for f in self.FLOWS for m in self.FMTS}

    def test_a_needs_both_flows_and_decision_relevance(self):
        rel = dict.fromkeys(self.FMTS, True)
        assert M.classify_structure(self._oc(True, True), rel)["letter"] == "A"
        rel_no = dict.fromkeys(self.FMTS, False)
        assert M.classify_structure(self._oc(True, True), rel_no)["letter"] == "B"

    def test_d_when_the_flows_differ(self):
        rel = dict.fromkeys(self.FMTS, False)
        assert M.classify_structure(self._oc(True, False), rel)["letter"] == "D"

    def test_b_when_partial(self):
        oc = self._oc(False, False)
        oc[(self.FLOWS[0], self.FMTS[0])] = True
        assert M.classify_structure(oc, {})["letter"] == "B"

    def test_c_when_nowhere(self):
        assert M.classify_structure(self._oc(False, False), {})["letter"] == "C"

    def test_overcredit_needs_ci_and_a_smaller_critical_cell(self):
        entry = {
            "overstatement_G": {"ca_msv": {"season": {"ci": (1.0, 9.0)}}},
            "critical_cell": {"ca_msv": {"n": 2}, "msv": {"n": 5}},
        }
        assert M.overcredit_supported(entry, "ca_msv") is True
        entry["critical_cell"]["ca_msv"]["n"] = 5
        assert M.overcredit_supported(entry, "ca_msv") is False
        entry["critical_cell"]["ca_msv"]["n"] = 2
        entry["overstatement_G"]["ca_msv"]["season"]["ci"] = (-1.0, 9.0)
        assert M.overcredit_supported(entry, "ca_msv") is False
        assert M.overcredit_supported(None, "ca_msv") is False


class TestReportPieces:
    @staticmethod
    def _row(msv_p, msv_o, ca_p, ca_o, v_p, v_o):
        side = lambda msv, ca, v: {  # noqa: E731
            "msv": msv,
            "ca_msv": ca,
            "onestep": v,
            "onestep_weekly": v,
        }
        return {
            "season": 2023,
            "regret": v_o - v_p,
            "P": side(msv_p, ca_p, v_p),
            "O": side(msv_o, ca_o, v_o),
        }

    def test_critical_cell_shrinks_when_the_term_follows_one_step(self):
        rows = [self._row(300, 200, 150, 200, 1000, 1080), self._row(300, 200, 250, 200, 1000, 990)]
        assert M.critical(rows, "msv") == {"n": 1, "regret": pytest.approx(80.0)}
        assert M.critical(rows, "ca_msv")["n"] == 0
        cells = M.two_by_two(rows, "msv")
        assert cells["msv_prefers_Alpha|onestep_prefers_Oracle"]["n"] == 1


class TestDiscipline:
    def test_reproduction_is_a_stop_condition(self):
        for needle in (
            "-- STOP",
            "ARM 4 rollout != D120's",
            "oracle rollout != D115's",
            "BL(final) on ARM 4 projections != season-long scorer",
            "CA identity fails",
            "D121 population differs",
            "ARM 4 projections are not realized points",
        ):
            assert needle in RUNNER_SOURCE

    def test_amendment_is_recorded_and_both_letters_are_reported(self):
        assert "AMENDMENT -- after a one-draft smoke run" in RUNNER_SOURCE
        assert "preregistered" in RUNNER_SOURCE and "amended" in RUNNER_SOURCE

    def test_no_tuning_and_read_only(self):
        for forbidden in ("GridSearch", "for weight in", "for alpha in", "optimize("):
            assert forbidden not in RUNNER_SOURCE
        assert "read_only=True" in RUNNER_SOURCE
        assert "src_dirty" in RUNNER_SOURCE or "_src_tree" in RUNNER_SOURCE

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()


class TestOtherwiseKind:
    def test_the_same_player_drafted_later_is_sequencing_not_valuation(self):
        # Taking wr5 now, the continuation still gets rb1 later: rb1's increment is 0.
        f_p = [*BASE]
        f_o = [*BASE, "wr5"]
        pw = M.pairwise_otherwise(LEAGUE, f_p, f_o, "rb1", "wr5", PTS, POS)
        assert pw["P_in_F_O"] == "RB"
        assert pw["P_otherwise_kind"] == "same_player_drafted_later"
        assert pw["P_increment_over_otherwise"] == pytest.approx(0.0)

    def test_kinds_are_exclusive(self):
        assert M.otherwise_kind("RB", [{"x": 1}], 5.0) == "same_player_drafted_later"
        assert M.otherwise_kind(None, [{"x": 1}], 5.0) == "position_refilled_by_another_player"
        assert M.otherwise_kind(None, [], 5.0) == "position_not_refilled"
        assert M.otherwise_kind(None, [], 0.0) == "no_starter_change_at_position"
