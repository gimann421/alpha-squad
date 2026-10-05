"""W14: the untouched-2026 validation of W10 -- eligibility, exact sign-flip p, the band, the rule."""

from __future__ import annotations

import datetime as dt
import math
import random

import pytest

from alpha_squad.evaluation.weekly import holdout as ho

UTC = dt.UTC
CAP = dt.datetime(2026, 10, 5, 12, 33, tzinfo=UTC)


def test_a_week_with_an_unplayed_game_is_not_eligible():
    sched = {("KC", "BUF"), ("DAL", "NYG")}
    ok, why = ho.week_eligibility(
        sched, {("KC", "BUF")}, {"KC", "BUF", "DAL", "NYG"}, CAP - dt.timedelta(days=1), CAP
    )
    assert not ok and "not in the data" in why
    ok, why = ho.week_eligibility(
        sched, sched, {"KC", "BUF", "DAL"}, CAP - dt.timedelta(days=1), CAP
    )
    assert not ok and "NYG" in why
    # Monday night kicks off after the capture: incomplete even if a row exists
    ok, why = ho.week_eligibility(
        sched, sched, {"KC", "BUF", "DAL", "NYG"}, CAP + dt.timedelta(hours=12), CAP
    )
    assert not ok
    ok, why = ho.week_eligibility(
        sched, sched, {"KC", "BUF", "DAL", "NYG"}, CAP - dt.timedelta(hours=5), CAP
    )
    assert not ok  # inside the 6-hour buffer
    ok, why = ho.week_eligibility(
        sched, sched, {"KC", "BUF", "DAL", "NYG"}, CAP - dt.timedelta(days=1), CAP
    )
    assert ok and why == "complete"


def test_exact_sign_flip_p_and_its_floor():
    r = ho.sign_flip_p([0.05, 0.02, 0.08])
    assert r["method"] == "exact" and r["patterns"] == 8
    assert r["p"] == pytest.approx(0.25) and r["min_attainable"] == pytest.approx(0.25)
    r = ho.sign_flip_p([0.05, -0.05, 0.0])
    assert r["p"] == pytest.approx(1.0)
    assert math.isnan(ho.sign_flip_p([])["p"])


def test_sign_flip_p_matches_a_brute_force_count():
    rng = random.Random(3)
    xs = [rng.gauss(0.01, 0.05) for _ in range(9)]
    obs = abs(sum(xs)) / 9
    count = 0
    for mask in range(2**9):
        s = sum(x if (mask >> i) & 1 else -x for i, x in enumerate(xs))
        count += abs(s) / 9 >= obs - 1e-12
    assert ho.sign_flip_p(xs)["p"] == pytest.approx(count / 2**9)


def test_monte_carlo_above_the_exact_limit_is_deterministic():
    xs = [0.01 * ((-1) ** i) + 0.002 for i in range(ho.EXACT_MAX_N + 1)]
    a, b = ho.sign_flip_p(xs), ho.sign_flip_p(xs)
    assert a == b and a["method"] == "monte_carlo"


def test_predictive_band():
    hist = [0.02] * 50 + [-0.05] * 10 + [0.1] * 19
    band = ho.predictive_band(hist, 3, value=-0.2)
    assert band["p025"] <= band["p50"] <= band["p975"]
    assert band["percentile"] == 0.0
    assert ho.predictive_band(hist, 3, value=1.0)["percentile"] == 1.0
    assert ho.predictive_band(hist, 3) == ho.predictive_band(hist, 3)


def _r(m, lo, hi):
    return {"mean_diff": m, "ci_low": lo, "ci_high": hi}


BASE = {
    "valid": True,
    "final": False,
    "n_weeks": 3,
    "wr10": _r(0.03, -0.05, 0.11),
    "wr5": _r(0.02, -0.08, 0.12),
    "band": {"p025": -0.06, "p975": 0.10},
    "guard": {},
}


def test_an_early_interim_look_cannot_replicate_or_partially_replicate():
    assert ho.classify(BASE)["verdict"] == ho.INCONCLUSIVE_CONTINUE
    big = BASE | {"wr10": _r(0.12, 0.02, 0.22), "wr5": _r(0.1, 0.01, 0.2)}
    v = ho.classify(big)
    assert v["verdict"] == ho.INCONCLUSIVE_CONTINUE and v["section9_holds"] is None


def test_invalid_or_too_short():
    assert ho.classify(BASE | {"valid": False})["verdict"] == ho.INCONCLUSIVE
    assert ho.classify(BASE | {"n_weeks": 2})["verdict"] == ho.INCONCLUSIVE


def test_material_contradiction_is_not_replicated_at_any_look():
    v = ho.classify(BASE | {"wr10": _r(-0.09, -0.15, -0.01)})
    assert v["verdict"] == ho.NOT_REPLICATED
    v = ho.classify(BASE | {"wr10": _r(-0.07, -0.15, 0.01)})  # below the band, CI includes 0
    assert v["verdict"] == ho.NOT_REPLICATED
    v = ho.classify(BASE | {"wr10": _r(-0.02, -0.1, 0.06)})  # negative but plausible: continue
    assert v["verdict"] == ho.INCONCLUSIVE_CONTINUE


def test_interim_direction_needs_eight_weeks():
    v = ho.classify(BASE | {"n_weeks": 8})
    assert v["verdict"] == ho.PARTIAL
    v = ho.classify(BASE | {"n_weeks": 8, "wr5": _r(-0.01, -0.1, 0.08)})
    assert v["verdict"] == ho.INCONCLUSIVE_CONTINUE


def test_final_look():
    fin = BASE | {"final": True, "n_weeks": 17}
    assert ho.classify(fin)["verdict"] == ho.PARTIAL
    rep = fin | {"wr10": _r(0.03, 0.002, 0.06), "wr5": _r(0.01, -0.03, 0.05)}
    v = ho.classify(rep)
    assert v["verdict"] == ho.REPLICATED and v["section9_holds"] is True
    v = ho.classify(rep | {"guard": {"RB|capture@10": _r(-0.01, -0.02, -0.002)}})
    assert v["verdict"] == ho.PARTIAL and v["breaches"] == ["RB|capture@10"]
    v = ho.classify(fin | {"wr10": _r(-0.001, -0.03, 0.03)})
    assert v["verdict"] == ho.NOT_REPLICATED


def test_section9_is_w10s_rule_verbatim():
    assert ho.section9(_r(0.03, 0.001, 0.06), _r(0.001, -0.1, 0.1))
    assert not ho.section9(_r(0.03, -0.001, 0.06), _r(0.02, 0.0, 0.1))
    assert not ho.section9(_r(0.03, 0.001, 0.06), _r(0.0, -0.1, 0.1))
    assert not ho.section9(None, _r(0.02, 0.0, 0.1))
