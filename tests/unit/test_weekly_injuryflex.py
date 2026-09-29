"""W13: own Friday injury status and the FLEX top 10 -- status groups, permutation p, the decision."""

from __future__ import annotations

import math
import random

import pytest

from alpha_squad.evaluation.weekly import injuryflex as inj


def test_the_frozen_feature_is_w12s_own_category():
    assert inj.OWN_FEATURES == ("own_status", "own_practice")
    assert inj.MDE_BAR == 0.011


def test_status_groups():
    assert [inj.status_group(v) for v in (0.0, 1.0, 2.0, 3.0)] == ["NONE", "Q", "D", "O"]
    assert inj.status_group(None) == "NO_REPORT"
    assert inj.status_group(float("nan")) == "NO_REPORT"


def test_sign_flip_p_is_deterministic_and_sensible():
    rng = random.Random(0)
    null = [rng.gauss(0, 1) for _ in range(63)]
    strong = [abs(x) + 1.0 for x in null]
    p_null = inj.sign_flip_p(null, n=5000)
    p_strong = inj.sign_flip_p(strong, n=5000)
    assert p_null == inj.sign_flip_p(null, n=5000)
    assert p_null > 0.05 and p_strong < 0.001
    assert p_strong == pytest.approx(1 / 5001)
    assert math.isnan(inj.sign_flip_p([]))


def test_sign_flip_p_ignores_order():
    xs = [0.02, -0.01, 0.03, 0.0, 0.015, -0.005, 0.01]
    assert inj.sign_flip_p(xs, n=2000) == inj.sign_flip_p(xs, n=2000)
    assert 0.0 < inj.sign_flip_p(xs, n=2000) <= 1.0


def _r(m, lo, hi):
    return {"mean_diff": m, "ci_low": lo, "ci_high": hi}


GOOD = {
    "flex": _r(0.015, 0.004, 0.026),
    "loso": [_r(0.015, 0.002, 0.03)] * 3 + [_r(0.01, -0.002, 0.02)],
    "null": _r(0.012, 0.002, 0.022),
    "half": _r(0.013, 0.001, 0.025),
    "wr": _r(0.001, -0.008, 0.01),
    "wr_vs_prod": _r(0.02, 0.005, 0.035),
    "guard": {"RB|capture@10": _r(0.0, -0.01, 0.01)},
}


def test_confirmed_needs_all_six():
    assert inj.verdict(GOOD)["verdict"] == "CONFIRMED INCREMENTAL SIGNAL"
    for bad in (
        {"flex": _r(0.009, 0.001, 0.02)},  # below the MDE bar
        {"flex": _r(0.012, -0.001, 0.025)},  # CI includes 0
        {"loso": [_r(0.015, 0.002, 0.03)] * 2 + [_r(0.01, -0.002, 0.02)] * 2},
        {"loso": [_r(0.015, 0.002, 0.03)] * 3 + [_r(-0.001, -0.01, 0.01)]},  # a negative fold
        {"loso": [_r(0.015, 0.002, 0.03)] * 3},  # not four folds
        {"null": _r(0.008, -0.002, 0.02)},
        {"half": _r(-0.001, -0.01, 0.01)},
    ):
        assert inj.verdict(GOOD | bad)["verdict"] == "NO CONFIRMED INCREMENTAL SIGNAL"


def test_wr_damage_is_a_tradeoff_not_a_success():
    v = inj.verdict(GOOD | {"wr": _r(-0.012, -0.03, 0.004)})
    assert v["verdict"] == "TRADEOFF" and not v["conditions"]["C6_wr_guardrail"]
    v = inj.verdict(GOOD | {"wr_vs_prod": _r(0.01, -0.004, 0.02)})
    assert v["verdict"] == "TRADEOFF"
    v = inj.verdict(GOOD | {"guard": {"TE|spearman": _r(-0.01, -0.02, -0.006)}})
    assert v["verdict"] == "TRADEOFF" and v["breaches"] == ["TE|spearman"]


def test_small_significant_loss_is_not_a_breach():
    assert not inj.is_breach(_r(-0.003, -0.005, -0.001))
    assert inj.is_breach(_r(-0.006, -0.01, -0.001))
    assert not inj.is_breach(None)
