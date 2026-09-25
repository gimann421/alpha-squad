"""W9: durable features, decomposable anticipation, residualization, attribution, verdicts."""

from __future__ import annotations

import random

import pytest
from scipy import stats as scipy_stats

from alpha_squad.evaluation.weekly import advantage as adv
from alpha_squad.evaluation.weekly import mechanisms as mech

# ---------------------------------------------------------------------------------------
# Durable features and tiers
# ---------------------------------------------------------------------------------------


def _week(w, ppr, tgt, car, tsh, snap):
    return {
        "week": w,
        "ppr": ppr,
        "targets": tgt,
        "carries": car,
        "target_share": tsh,
        "snap": snap,
    }


def test_durable_features_are_order_independent_and_correct():
    rows = [
        _week(3, 10.0, 5, 2, 0.2, 0.8),
        _week(1, 0.1, 1, 0, None, 0.5),
        _week(2, 20.2, 8, 1, 0.3, 0.9),
    ]
    a = mech.durable_features(rows, position_rank=7)
    b = mech.durable_features(list(reversed(rows)), position_rank=7)
    assert a == b
    assert a["prior_games"] == 3.0 and a["has_prior"] == 1.0 and a["prior_rank"] == 7.0
    assert a["prior_ppg"] == pytest.approx((10.0 + 0.1 + 20.2) / 3)
    assert a["prior_opp_pg"] == pytest.approx((7 + 1 + 9) / 3)
    assert a["prior_tsh"] == pytest.approx(0.25)  # null target share is skipped, not zeroed


def test_no_prior_season_is_explicit():
    f = mech.durable_features([], position_rank=None)
    assert f["has_prior"] == 0.0
    assert all(f[k] is None for k in mech.DURABLE_FEATURES if k != "has_prior")


@pytest.mark.parametrize(
    ("rank", "tier"),
    [
        (1, "ELITE"),
        (12, "ELITE"),
        (13, "STARTER"),
        (36, "STARTER"),
        (37, "OTHER"),
        (None, "OTHER"),
        (float("nan"), "OTHER"),
    ],
)
def test_tiers(rank, tier):
    assert mech.tier_of(rank) == tier


@pytest.mark.parametrize(
    ("week", "period"),
    [(1, "EARLY"), (6, "EARLY"), (7, "MID"), (12, "MID"), (13, "LATE"), (17, "LATE")],
)
def test_periods(week, period):
    assert mech.period_of(week) == period


def test_period_outside_range_raises():
    with pytest.raises(ValueError):
        mech.period_of(18)


# ---------------------------------------------------------------------------------------
# Decomposable anticipation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_anticipation_terms_average_to_spearman_exactly(seed):
    rng = random.Random(seed)
    d = [float(rng.randint(-15, 15)) for _ in range(25)]  # integer rank gaps -> ties
    s = [rng.gauss(0, 4) for _ in range(25)]
    terms = mech.anticipation_terms(d, s)
    ref = scipy_stats.spearmanr(d, s).correlation
    assert sum(terms) / len(terms) == pytest.approx(ref, abs=1e-12)
    assert sum(terms) / len(terms) == pytest.approx(adv.spearman_values(d, s), abs=1e-12)


def test_anticipation_undefined_for_constant_input():
    assert mech.anticipation_terms([1.0] * 5, [1.0, 2, 3, 4, 5]) is None


# ---------------------------------------------------------------------------------------
# Residualization
# ---------------------------------------------------------------------------------------


def test_residualize_removes_the_linear_part_exactly():
    rng = random.Random(1)
    x = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(40)]
    y = [3.0 + 2.0 * a - 1.5 * b for a, b in x]
    assert max(abs(r) for r in mech.residualize(y, x)) < 1e-9


def test_raw_residualization_on_noise_is_biased_and_the_adjustment_removes_it():
    """Amendment A2's regression test. Residualizing on 7 noise columns within ~25 players
    shrinks rho by chance (the raw 'reduction' is clearly positive); the permutation-adjusted
    reduction is centred on zero."""
    rng = random.Random(2)
    raw, adjusted = [], []
    for _ in range(200):
        d = [rng.gauss(0, 1) for _ in range(25)]
        s = [0.4 * v + rng.gauss(0, 1) for v in d]
        noise = [[rng.gauss(0, 1) for _ in range(7)] for _ in range(25)]
        out = mech.adjusted_reduction(d, s, noise)
        raw.append(out["raw_reduction"])
        adjusted.append(out["adjusted_reduction"])
    assert sum(raw) / len(raw) > 0.03  # the hazard the amendment fixes
    assert abs(sum(adjusted) / len(adjusted)) < 0.01


def test_adjusted_reduction_detects_a_real_control():
    """When d is mostly a durable variable, controlling for it removes most of rho."""
    rng = random.Random(3)
    shares = []
    for _ in range(100):
        prior = [rng.gauss(0, 1) for _ in range(25)]
        d = [p + 0.3 * rng.gauss(0, 1) for p in prior]
        s = [0.6 * p + rng.gauss(0, 1) for p in prior]  # s linked to d ONLY through prior
        out = mech.adjusted_reduction(d, s, [[p] for p in prior])
        shares.append(out["adjusted_reduction"] / out["rho"])
    assert sum(shares) / len(shares) > 0.6


def test_adjusted_reduction_is_deterministic():
    rng = random.Random(4)
    d = [rng.gauss(0, 1) for _ in range(20)]
    s = [rng.gauss(0, 1) for _ in range(20)]
    x = [[rng.gauss(0, 1)] for _ in range(20)]
    assert mech.adjusted_reduction(d, s, x) == mech.adjusted_reduction(d, s, x)


def test_residualize_with_no_columns_centres():
    assert mech.residualize([1.0, 2.0, 3.0], []) == [-1.0, 0.0, 1.0]


# ---------------------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------------------


def _rows(n, seed):
    rng = random.Random(seed)
    out = {}
    for i in range(n):
        x = rng.uniform(0, 20)
        out[f"p{i:02d}"] = adv.PlayerWeek(f"p{i:02d}", x + rng.gauss(0, 5), x, x + rng.gauss(0, 3))
    return out


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("piece", ["G", "F", "S", "C"])
def test_piece_attribution_sums_to_the_piece(seed, piece):
    rows = _rows(30, seed)
    ids = sorted(rows)
    rng = random.Random(seed)
    a, b = ids[:], ids[:]
    rng.shuffle(a)
    rng.shuffle(b)
    groups = {p: rng.choice(mech.WEEKLY_CLASSES) for p in ids}
    dec = adv.decompose_gap(a, b, rows, 10)
    attr = mech.attribute_piece(a, b, rows, 10, groups, piece)
    key = "G" if piece == "G" else f"G_{piece}"
    assert sum(attr.values()) == pytest.approx(dec[key], abs=1e-12)


def test_weekly_class_precedence():
    assert mech.classify_weekly(True, True) == "A"
    assert mech.classify_weekly(False, True) == "C"
    assert mech.classify_weekly(False, False) == "B"


# ---------------------------------------------------------------------------------------
# Verdict rules
# ---------------------------------------------------------------------------------------


def _r(mean, lo, hi):
    return {"mean_diff": mean, "ci_low": lo, "ci_high": hi}


def test_durable_route_needs_all_three():
    sig, early = _r(0.05, 0.02, 0.08), _r(0.06, 0.01, 0.1)
    assert mech.durable_route(sig, 0.40, early, [0.1, 0.1, 0.1, 0.1, -0.1])["all"]
    assert not mech.durable_route(sig, 0.30, early, [0.1] * 5)["all"]  # share < 1/3
    assert not mech.durable_route(sig, 0.40, _r(0.06, -0.01, 0.1), [0.1] * 5)["all"]  # EARLY n.s.
    assert not mech.durable_route(sig, 0.40, early, [0.1, 0.1, 0.1, -0.1, -0.1])["all"]  # 3/5
    assert not mech.durable_route(_r(0.05, -0.01, 0.1), 0.40, early, [0.1] * 5)["all"]


def test_weekly_rule_not_measurable_is_its_own_outcome():
    out = mech.weekly_rule(0.8, False, None, None, None, None, [])
    assert out["status"] == "NOT MEASURABLE" and out["W-2"] is None


def test_weekly_rule_supported_and_its_failures():
    ok = dict(
        large_share_of_g=0.8,
        measurable=True,
        class_a_share_of_gs=0.4,
        class_a_attr=_r(0.01, 0.002, 0.02),
        class_a_swap_share=0.2,
        a_minus_b=_r(0.1, 0.02, 0.2),
        loso_a_minus_b=[0.1, 0.1, 0.1, 0.1, -0.1],
    )
    assert mech.weekly_rule(**ok)["status"] == "SUPPORTED"
    assert (
        mech.weekly_rule(**(ok | {"class_a_swap_share": 0.3}))["status"] == "NOT SUPPORTED"
    )  # < 1.5x
    assert mech.weekly_rule(**(ok | {"large_share_of_g": 0.4}))["status"] == "NOT SUPPORTED"
    assert (
        mech.weekly_rule(**(ok | {"a_minus_b": _r(0.1, -0.02, 0.2)}))["status"] == "NOT SUPPORTED"
    )
    assert (
        mech.weekly_rule(**(ok | {"loso_a_minus_b": [0.1, 0.1, 0.1, -0.1, -0.1]}))["status"]
        == "NOT SUPPORTED"
    )


def test_position_verdict_labels():
    assert mech.position_verdict(True, "NOT MEASURABLE", False)["verdict"] == "DURABLE"
    assert mech.position_verdict(True, "SUPPORTED", False)["verdict"] == "MIXED"
    v = mech.position_verdict(False, "NOT MEASURABLE", False)
    assert v["verdict"] == "INCONCLUSIVE" and v["weekly_not_measurable"]


def test_overall_and_recommendation():
    assert mech.overall("DURABLE", "DURABLE") == "DURABLE"
    assert mech.overall("DURABLE", "INCONCLUSIVE") == "DURABLE (RB only)"
    assert mech.overall("DURABLE", "EFFICIENCY") == "MIXED"
    assert mech.recommendation("DURABLE (RB only)", True, 0.5, durable_kind="D_EXPERT").startswith(
        "A"
    )
    assert mech.recommendation("INCONCLUSIVE", True, 0.2).startswith("E")
    assert mech.recommendation("INCONCLUSIVE", True, 0.5).startswith("B as a measurement")
    assert mech.recommendation("INCONCLUSIVE", False, 0.5).startswith("UNMAPPED")
    assert mech.recommendation("MIXED", False, 0.5, largest_component="DURABLE").startswith("D")
