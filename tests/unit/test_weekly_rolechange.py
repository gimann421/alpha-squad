"""W11 role-change instrument: role state, classes, movers, the ratio-difference bootstrap and the
pre-registered verdicts."""

from __future__ import annotations

import functools
import math
import operator
import random

import pytest

from alpha_squad.evaluation.weekly import rolechange as rc

TAU = rc.THRESHOLDS["PRIMARY"]
PRIOR = {"has_prior": 1.0, "prior_opp_pg": 10.0, "prior_snap": 0.60, "prior_ppg": 12.0}


def _g(week, opp, snap=0.60, ppr=12.0):
    return {"week": week, "opp": opp, "snap": snap, "ppr": ppr}


def test_thresholds_are_the_preregistered_three():
    assert rc.THRESHOLDS == {"PRIMARY": (3.0, 0.15), "LOOSE": (2.0, 0.10), "STRICT": (4.0, 0.20)}
    assert rc.WINDOW == 3 and rc.PERSISTENCE == 2
    assert rc.ROLE_FEATURES == ("role_d_opp", "role_d_snap", "role_shift")


def test_no_prior_and_too_early():
    assert rc.role_state({"has_prior": 0.0}, [_g(1, 20)], *TAU)["cls"] == "NO_PRIOR"
    assert rc.role_state({"has_prior": float("nan")}, [], *TAU)["cls"] == "NO_PRIOR"
    s = rc.role_state(PRIOR, [_g(1, 20)], *TAU)
    assert s["cls"] == "TOO_EARLY" and s["role_shift"] is None
    assert s["role_d_opp"] == pytest.approx(10.0)  # one game still gives a delta


def test_week_one_has_no_current_role():
    s = rc.role_state(PRIOR, [], *TAU)
    assert s["cls"] == "TOO_EARLY" and s["role_d_opp"] is None and s["role_d_snap"] is None


def test_sustained_up_needs_both_last_two_games():
    assert rc.role_state(PRIOR, [_g(1, 14), _g(2, 13)], *TAU)["cls"] == "ROLE_UP"
    assert rc.role_state(PRIOR, [_g(1, 14), _g(2, 13)], *TAU)["role_shift"] == 1.0
    # only the last game: transient
    s = rc.role_state(PRIOR, [_g(1, 10), _g(2, 14)], *TAU)
    assert s["cls"] == "TRANSIENT" and s["transient_dir"] == "UP" and s["role_shift"] == 0.0
    # an old deviation that reverted: not transient, not a change
    assert rc.role_state(PRIOR, [_g(1, 14), _g(2, 14), _g(3, 10)], *TAU)["cls"] in (
        "QUIET",
        "STABLE",
    )


def test_snap_share_alone_can_carry_a_change():
    games = [_g(1, 10, snap=0.40), _g(2, 10, snap=0.42)]
    s = rc.role_state(PRIOR, games, *TAU)
    assert s["cls"] == "ROLE_DOWN" and s["role_shift"] == -1.0
    assert s["role_d_snap"] == pytest.approx(0.41 - 0.60)


def test_conflicting_measures_are_mixed():
    games = [_g(1, 14, snap=0.40), _g(2, 14, snap=0.40)]
    assert rc.role_state(PRIOR, games, *TAU)["cls"] == "ROLE_MIXED"


def test_quiet_vs_stable():
    assert rc.role_state(PRIOR, [_g(1, 10, ppr=6), _g(2, 11, ppr=8)], *TAU)["cls"] == "QUIET"
    assert rc.role_state(PRIOR, [_g(1, 10, ppr=15), _g(2, 11, ppr=13)], *TAU)["cls"] == "STABLE"


def test_window_is_last_three_and_order_free():
    games = [_g(w, o) for w, o in ((1, 30), (2, 10), (3, 11), (4, 12))]
    a = rc.role_state(PRIOR, games, *TAU)
    b = rc.role_state(PRIOR, list(reversed(games)), *TAU)
    assert a == b
    assert a["role_d_opp"] == pytest.approx((10 + 11 + 12) / 3 - 10.0)


def test_missing_snap_is_skipped_not_zero():
    games = [_g(1, 10, snap=None), _g(2, 10, snap=None)]
    s = rc.role_state(PRIOR, games, *TAU)
    assert s["role_d_snap"] is None and s["cls"] in ("QUIET", "STABLE")


def test_thresholds_are_inclusive_and_ordered():
    loose, strict = rc.THRESHOLDS["LOOSE"], rc.THRESHOLDS["STRICT"]
    games = [_g(1, 12.5), _g(2, 12.5)]
    assert rc.role_state(PRIOR, games, *loose)["cls"] == "ROLE_UP"
    assert rc.role_state(PRIOR, games, *TAU)["cls"] != "ROLE_UP"
    assert rc.role_state(PRIOR, [_g(1, 13), _g(2, 13)], *TAU)["cls"] == "ROLE_UP"  # >= tau
    assert rc.role_state(PRIOR, [_g(1, 13), _g(2, 13)], *strict)["cls"] != "ROLE_UP"


def test_groups():
    assert {rc.group_of(c) for c in rc.CHANGE_CLASSES} == {"CHANGE"}
    assert {rc.group_of(c) for c in rc.STABLE_CLASSES} == {"STABLE"}
    for c in ("NO_PRIOR", "TOO_EARLY", "TRANSIENT"):
        assert rc.group_of(c) is None


def test_movers_and_outcomes():
    assert rc.is_mover(20, 23) and not rc.is_mover(20, 22) and not rc.is_mover(25, 40)
    assert rc.is_mover(26, 22)
    assert rc.move_outcome(10, 5, 4) == "RIGHT"
    assert rc.move_outcome(10, 5, 12) == "WRONG"
    assert rc.move_outcome(10, 6, 8) is None


def test_ratio_diff_ci_point_and_determinism():
    rng = random.Random(3)
    weeks = [f"2021-{w}" for w in range(1, 18)]
    n1 = {w: float(rng.randint(2, 6)) for w in weeks}
    d1 = {w: 10.0 for w in weeks}
    n2 = {w: float(rng.randint(0, 3)) for w in weeks}
    d2 = {w: 10.0 for w in weeks}
    r = rc.ratio_diff_ci(n1, d1, n2, d2)
    naive = (
        functools.reduce(operator.add, n1.values()) / 170
        - functools.reduce(operator.add, n2.values()) / 170
    )
    assert r["diff"] == pytest.approx(naive)
    assert r["ci_low"] < r["diff"] < r["ci_high"]
    assert r == rc.ratio_diff_ci(n1, d1, n2, d2)
    # dict insertion order must not matter
    rev = {w: n1[w] for w in reversed(weeks)}
    assert rc.ratio_diff_ci(rev, d1, n2, d2) == r


def test_ratio_diff_ci_missing_weeks_count_as_zero():
    n1 = {"a": 1.0, "b": 1.0, "c": 1.0}
    d1 = {"a": 2.0, "b": 2.0, "c": 2.0}
    n2 = {"a": 0.0}
    d2 = {"a": 1.0, "b": 1.0, "c": 1.0}
    assert rc.ratio_diff_ci(n1, d1, n2, d2)["diff"] == pytest.approx(0.5)
    assert rc.ratio_diff_ci({}, {}, {}, {}) is None


def _r(m, lo, hi):
    return {"mean_diff": m, "ci_low": lo, "ci_high": hi}


def test_mechanism_needs_m1_and_m2():
    good = rc.mechanism(_r(0.03, 0.01, 0.05), _r(-0.04, -0.06, -0.02), None, None)
    assert good["established"] and not good["conditions"]["M3"]
    assert not rc.mechanism(_r(0.03, -0.01, 0.05), _r(-0.04, -0.06, -0.02), None, None)[
        "established"
    ]
    assert not rc.mechanism(_r(0.03, 0.01, 0.05), _r(-0.04, -0.06, 0.01), None, None)["established"]
    m3 = {"diff": 0.1, "ci_low": 0.02, "ci_high": 0.2}
    assert rc.mechanism(None, None, m3, m3)["conditions"] == {
        "M1": False,
        "M2": False,
        "M3": True,
        "R": True,
    }


GOOD = {
    "mechanism_established": True,
    "rb": _r(0.025, 0.008, 0.04),
    "rb_role_up": _r(0.02, 0.005, 0.035),
    "rb_null": _r(0.02, 0.004, 0.036),
    "rb_seasons": [0.03, 0.02, 0.01, 0.04, -0.01],
    "rb_loso": [_r(0.02, 0.001, 0.04)] * 4 + [_r(0.02, -0.001, 0.04)],
    "wr": _r(-0.002, -0.01, 0.006),
    "wr_vs_a": _r(0.02, 0.005, 0.035),
    "guard": {"TE|capture@10": _r(0.0, -0.01, 0.01)},
    "any_gain": {},
}


def test_success_needs_every_condition():
    assert rc.model_verdict(GOOD)["verdict"] == "SUCCESS"
    weak_up = {"rb_role_up": _r(0.005, -0.002, 0.012)}
    for bad in (
        {"rb": _r(0.015, 0.001, 0.03)} | weak_up,  # below the bar, not carried by ROLE_UP
        {"rb_null": _r(0.01, -0.005, 0.03)},
        {"rb_seasons": [0.03, -0.02, -0.01, 0.04, 0.01]},
        {"wr_vs_a": _r(0.01, -0.005, 0.02)},
    ):
        assert rc.model_verdict(GOOD | bad)["verdict"] != "SUCCESS"


def test_small_total_gain_can_pass_through_the_targeted_class():
    v = rc.model_verdict(GOOD | {"rb": _r(0.012, 0.002, 0.022)})
    assert v["conditions"]["S1_rb_improves"] and v["verdict"] == "SUCCESS"
    v = rc.model_verdict(GOOD | {"rb": _r(0.012, 0.002, 0.022), "rb_role_up": _r(0.01, 0.0, 0.02)})
    assert not v["conditions"]["S1_rb_improves"]


def test_mechanism_gate_comes_first():
    assert (
        rc.model_verdict(GOOD | {"mechanism_established": False})["verdict"]
        == "MECHANISM NOT ESTABLISHED"
    )


def test_rb_gain_with_wr_loss_is_a_tradeoff_not_an_average():
    v = rc.model_verdict(GOOD | {"wr": _r(-0.015, -0.03, -0.001)})
    assert v["verdict"] == "TRADEOFF" and v["wr_harm"]
    v = rc.model_verdict(GOOD | {"guard": {"TE|spearman": _r(-0.01, -0.02, -0.006)}})
    assert v["verdict"] == "TRADEOFF" and v["breaches"] == ["TE|spearman"]


def test_harm_without_rb_gain():
    v = rc.model_verdict(GOOD | {"rb": _r(0.0, -0.01, 0.01), "wr": _r(-0.02, -0.03, -0.01)})
    assert v["verdict"] == "HARM"
    # a material WR point loss is harm even when its CI straddles 0
    v = rc.model_verdict(GOOD | {"rb": _r(0.0, -0.01, 0.01), "wr": _r(-0.012, -0.03, 0.005)})
    assert v["verdict"] == "HARM"


def test_partial_routes_and_no_effect():
    null_rb = {"rb": _r(0.002, -0.01, 0.014), "rb_role_up": _r(0.001, -0.004, 0.006)}
    assert rc.model_verdict(GOOD | null_rb)["verdict"] == "NO EFFECT"
    assert (
        rc.model_verdict(GOOD | null_rb | {"rb_role_up": _r(0.008, 0.002, 0.014)})["verdict"]
        == "PARTIAL"
    )
    assert (
        rc.model_verdict(GOOD | null_rb | {"rb": _r(0.021, -0.001, 0.04)})["verdict"] == "PARTIAL"
    )
    gain = {"WR|capture@10": _r(0.025, 0.01, 0.04)}
    assert rc.model_verdict(GOOD | null_rb | {"any_gain": gain})["verdict"] == "PARTIAL"
    # S1 met but inconsistent -> PARTIAL
    assert rc.model_verdict(GOOD | {"rb_loso": []})["verdict"] == "PARTIAL"


def test_small_significant_loss_is_not_a_breach():
    assert not rc.is_breach(_r(-0.003, -0.005, -0.001))
    assert rc.is_breach(_r(-0.006, -0.01, -0.001))
    assert not rc.is_breach(None)
    assert math.isclose(rc.BREACH_FLOOR, 0.005)


def test_reliability_tag_survives_a_dataframe_round_trip():
    # Regression (W11 A1): pandas turns a missing transient direction into NaN, and a lookup
    # keyed on None then silently matched nothing, so the R test was empty.
    nan = float("nan")
    assert rc.reliability_tag("ROLE_UP", nan) == "up"
    assert rc.reliability_tag("ROLE_UP", None) == "up"
    assert rc.reliability_tag("ROLE_DOWN", nan) == "down"
    assert rc.reliability_tag("TRANSIENT", "UP") == "tup"
    assert rc.reliability_tag("TRANSIENT", "DOWN") == "tdown"
    assert rc.reliability_tag("TRANSIENT", "MIXED") is None
    assert rc.reliability_tag("QUIET", nan) is None
