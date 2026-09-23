"""W8: the ECR-advantage decomposition, buckets, pair tests and the pre-registered verdict."""

from __future__ import annotations

import random

import pytest
from scipy import stats as scipy_stats

from alpha_squad.evaluation.weekly import advantage as adv
from alpha_squad.evaluation.weekly.metrics import pairwise_accuracy, topk_points_capture


def _rows(n: int, seed: int) -> dict[str, adv.PlayerWeek]:
    rng = random.Random(seed)
    out = {}
    for i in range(n):
        x = rng.uniform(0, 20)
        out[f"p{i:02d}"] = adv.PlayerWeek(f"p{i:02d}", x + rng.gauss(0, 5), x, x + rng.gauss(0, 3))
    return out


def _shuffled(ids: list[str], seed: int) -> list[str]:
    ids = sorted(ids)
    random.Random(seed).shuffle(ids)
    return ids


def _capture(order: list[str], rows: dict[str, adv.PlayerWeek], k: int) -> float:
    rank = {p: float(n) for n, p in enumerate(order, start=1)}
    ids = sorted(rows)
    return topk_points_capture([rank[p] for p in ids], [rows[p].pts for p in ids], k)


# ---------------------------------------------------------------------------------------
# The decomposition
# ---------------------------------------------------------------------------------------


def test_player_week_components_add_up():
    r = adv.PlayerWeek("a", pts=15.0, x=11.0, f=9.0)
    assert r.s == 2.0
    assert r.c == 4.0
    assert r.f + r.s + r.c == r.pts


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("k", [5, 10, 20])
def test_decomposition_is_exact_and_decomposes_the_program_metric(seed, k):
    rows = _rows(35, seed)
    a, b = _shuffled(list(rows), seed + 100), _shuffled(list(rows), seed + 200)
    dec = adv.decompose_gap(a, b, rows, k)
    assert dec["G"] == pytest.approx(dec["G_F"] + dec["G_S"] + dec["G_C"], abs=1e-12)
    assert dec["capture_a"] == pytest.approx(_capture(a, rows, k), abs=1e-12)
    assert dec["capture_b"] == pytest.approx(_capture(b, rows, k), abs=1e-12)


def test_identical_boards_have_zero_gap_in_every_piece():
    rows = _rows(25, 3)
    order = sorted(rows)
    dec = adv.decompose_gap(order, order, rows, 10)
    assert all(dec[p] == 0.0 for p in ("G", "G_F", "G_S", "G_C"))


def test_decomposition_assigns_surprise_to_the_surprise_piece():
    # Two boards differ in one swap: A has "hit" (usage beat forecast), B has "miss" (it fell short).
    rows = {
        "hit": adv.PlayerWeek("hit", pts=20.0, x=20.0, f=10.0),  # s = +10, c = 0
        "miss": adv.PlayerWeek("miss", pts=10.0, x=10.0, f=10.0),  # s = 0,   c = 0
        "z": adv.PlayerWeek("z", pts=30.0, x=30.0, f=30.0),
    }
    dec = adv.decompose_gap(["z", "hit", "miss"], ["z", "miss", "hit"], rows, 2)
    assert dec["G_F"] == 0.0 and dec["G_C"] == 0.0
    assert dec["G_S"] == pytest.approx(dec["G"]) and dec["G"] > 0


def test_decomposition_refuses_mismatched_universes_and_short_boards():
    rows = _rows(12, 1)
    ids = sorted(rows)
    assert adv.decompose_gap(ids, ids[:-1] + ["ghost"], rows, 5) is None
    assert adv.decompose_gap(ids, ids, rows, 13) is None


@pytest.mark.parametrize("seed", range(10))
def test_bucket_attribution_sums_to_the_gap(seed):
    rows = _rows(30, seed)
    a, b = _shuffled(list(rows), seed + 1), _shuffled(list(rows), seed + 2)
    buckets = {p: random.Random(seed).choice(adv.OPP_BUCKETS) for p in rows}
    for k in (10, 20):
        attr = adv.attribute_gap(a, b, rows, k, buckets)
        assert sum(attr.values()) == pytest.approx(adv.decompose_gap(a, b, rows, k)["G"], abs=1e-12)
        counts = adv.swap_counts(a, b, k, buckets)
        assert sum(counts.values()) == len(set(a[:k]) ^ set(b[:k]))


def test_bucket_attribution_raises_on_an_unbucketed_swapped_player():
    rows = _rows(15, 4)
    a, b = sorted(rows), sorted(rows, reverse=True)
    with pytest.raises(KeyError):
        adv.attribute_gap(a, b, rows, 5, {})


# ---------------------------------------------------------------------------------------
# Thresholds and buckets
# ---------------------------------------------------------------------------------------


def test_quantile_matches_numpy_linear_rule():
    import numpy as np

    vals = [random.Random(9).uniform(-5, 5) for _ in range(101)]
    for q in (0.2, 1 / 3, 0.5, 2 / 3, 0.8):
        assert adv.quantile(sorted(vals), q) == pytest.approx(float(np.quantile(vals, q)))


def test_tercile_boundaries_are_inclusive_below_and_exclusive_above():
    cuts = (1.0, 2.0)
    assert adv.opportunity_bucket(-1.0, cuts) == "CLOSE"
    assert adv.opportunity_bucket(1.5, cuts) == "MODERATE"
    assert adv.opportunity_bucket(2.0, cuts) == "MODERATE"
    assert adv.opportunity_bucket(-2.5, cuts) == "LARGE"
    assert adv.signed_bucket(2.5, cuts) == "LARGE_UP"
    assert adv.signed_bucket(-2.5, cuts) == "LARGE_DOWN"
    assert adv.efficiency_bucket(-3.0, cuts) == "LOW"
    assert adv.efficiency_bucket(3.0, cuts) == "HIGH"


def test_terciles_split_the_pooled_distribution_into_thirds():
    vals = [float(i) for i in range(300)]
    cuts = adv.thresholds(vals, (1 / 3, 2 / 3))
    labels = [adv.tercile_bucket(v, cuts, ("L", "M", "H")) for v in vals]
    assert abs(labels.count("L") - 100) <= 1
    assert abs(labels.count("H") - 100) <= 1


# ---------------------------------------------------------------------------------------
# Pairs, concordance, correlation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(5))
def test_all_pairs_accuracy_equals_the_program_pairwise_metric(seed):
    rng = random.Random(seed)
    region = [f"p{i}" for i in range(20)]
    pts = {p: float(rng.randint(0, 25)) for p in region}  # integer points -> real ties
    ra = {p: float(n) for n, p in enumerate(_shuffled(region, seed), start=1)}
    rb = {p: float(n) for n, p in enumerate(_shuffled(region, seed + 7), start=1)}
    acc = adv.pair_accuracy_by_type(region, ra, rb, pts, lambda i, j: [])
    ids = sorted(region)
    ref_a, n_a = pairwise_accuracy([ra[p] for p in ids], [pts[p] for p in ids])
    ref_b, _ = pairwise_accuracy([rb[p] for p in ids], [pts[p] for p in ids])
    assert acc["ALL"]["acc_a"] == pytest.approx(ref_a)
    assert acc["ALL"]["acc_b"] == pytest.approx(ref_b)
    assert acc["ALL"]["n"] == n_a


def test_pair_types_partition_is_respected():
    region = ["a", "b", "c"]
    pts = {"a": 3.0, "b": 2.0, "c": 1.0}
    perfect = {"a": 1.0, "b": 2.0, "c": 3.0}
    reversed_ = {"a": 3.0, "b": 2.0, "c": 1.0}
    acc = adv.pair_accuracy_by_type(
        region, perfect, reversed_, pts, lambda i, j: ["CLOSE"] if "a" in (i, j) else []
    )
    assert acc["CLOSE"] == {"acc_a": 1.0, "acc_b": 0.0, "n": 2}
    assert acc["ALL"]["n"] == 3


def test_concordance_is_one_for_a_perfect_board():
    region = ["a", "b", "c", "d"]
    pts = {"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}
    perfect = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    assert set(adv.concordance(region, perfect, pts).values()) == {1.0}


def test_spearman_values_matches_scipy_with_ties():
    rng = random.Random(5)
    xs = [float(rng.randint(0, 6)) for _ in range(40)]
    ys = [x + rng.gauss(0, 2) for x in xs]
    ref = scipy_stats.spearmanr(xs, ys).correlation
    assert adv.spearman_values(xs, ys) == pytest.approx(ref)
    assert adv.spearman_values([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


# ---------------------------------------------------------------------------------------
# The pre-registered verdict (§7)
# ---------------------------------------------------------------------------------------


def _r(mean: float, lo: float, hi: float) -> dict:
    return {"mean_diff": mean, "ci_low": lo, "ci_high": hi}


def _summary(G, GF, GS, GC, omega, close, match, diff) -> dict:
    return {
        "decomp": {"G@10": G, "G_F@10": GF, "G_S@10": GS, "G_C@10": GC},
        "pairs": {"pair_ALL": omega, "pair_CLOSE": close, "pair_MATCHED": match},
        "omega": {"surp_minus_close": diff},
    }


SIG_G = _r(0.03, 0.01, 0.05)
SIG_OMEGA = _r(0.02, 0.01, 0.03)
NULL = _r(0.0, -0.01, 0.01)


def test_information_through_the_conditional_route():
    s = _summary(
        SIG_G, NULL, NULL, NULL, SIG_OMEGA, _r(0.005, -0.01, 0.02), NULL, _r(0.02, 0.005, 0.035)
    )
    v = adv.verdict(s)
    assert v["routes"]["I-1"] and not v["routes"]["E-1"]
    assert v["verdict"] == "INFORMATION"


def test_information_through_the_surprise_piece():
    s = _summary(
        SIG_G, NULL, _r(0.012, 0.002, 0.02), NULL, SIG_OMEGA, _r(0.004, -0.01, 0.02), NULL, NULL
    )
    v = adv.verdict(s)
    assert v["routes"]["I-2"] and v["verdict"] == "INFORMATION"


def test_efficiency_needs_both_the_close_pairs_and_a_surviving_share():
    close = _r(0.015, 0.005, 0.025)  # >= 1/2 of omega, significant
    only_close = _summary(SIG_G, NULL, NULL, NULL, SIG_OMEGA, close, NULL, NULL)
    assert adv.verdict(only_close)["verdict"] == "INCONCLUSIVE"
    with_match = _summary(SIG_G, NULL, NULL, NULL, SIG_OMEGA, close, _r(0.012, 0.004, 0.02), NULL)
    assert adv.verdict(with_match)["verdict"] == "EFFICIENCY"
    with_gc = _summary(SIG_G, NULL, NULL, _r(0.02, 0.005, 0.035), SIG_OMEGA, close, NULL, NULL)
    assert adv.verdict(with_gc)["verdict"] == "EFFICIENCY"


def test_mixed_arises_through_the_surprise_piece_plus_efficiency():
    close = _r(0.015, 0.005, 0.025)
    s = _summary(
        SIG_G, NULL, _r(0.012, 0.002, 0.02), NULL, SIG_OMEGA, close, _r(0.012, 0.004, 0.02), NULL
    )
    assert adv.verdict(s)["verdict"] == "MIXED"


def test_i1_and_e1_are_mutually_exclusive():
    for close_mean in (0.004, 0.0099, 0.0101, 0.018):
        close = _r(close_mean, 0.001, close_mean + 0.01)
        s = _summary(SIG_G, NULL, NULL, NULL, SIG_OMEGA, close, NULL, _r(0.02, 0.005, 0.035))
        routes = adv.verdict(s)["routes"]
        assert not (routes["I-1"] and routes["E-1"])


def test_no_gap_and_w_flag():
    s = _summary(NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
    assert adv.verdict(s)["verdict"] == "NO GAP TO EXPLAIN"
    w = _summary(SIG_G, _r(0.02, 0.005, 0.035), NULL, NULL, NULL, NULL, NULL, NULL)
    v = adv.verdict(w)
    assert v["w_flag"] and v["verdict"] == "INCONCLUSIVE"


def test_small_share_does_not_count_even_when_significant():
    s = _summary(SIG_G, NULL, _r(0.005, 0.001, 0.009), NULL, SIG_OMEGA, NULL, NULL, NULL)
    assert adv.verdict(s)["verdict"] == "INCONCLUSIVE"  # 0.005 < 0.03 / 3


def test_overall_and_recommendation_mapping():
    assert adv.overall("INFORMATION", "INFORMATION") == "INFORMATION"
    assert adv.overall("INFORMATION", "EFFICIENCY") == "MIXED"
    assert adv.overall("MIXED", "INCONCLUSIVE") == "MIXED"
    assert adv.overall("EFFICIENCY", "INCONCLUSIVE") == "EFFICIENCY (RB only)"
    assert adv.overall("NO GAP TO EXPLAIN", "INFORMATION") == "INFORMATION (WR only)"
    assert adv.overall("INCONCLUSIVE", "NO GAP TO EXPLAIN") == "INCONCLUSIVE"
    assert adv.recommendation("EFFICIENCY (RB only)", [False, False]).startswith("B")
    assert adv.recommendation("INCONCLUSIVE", [False, False]).startswith("D")
    assert adv.recommendation("INCONCLUSIVE", [True, False]).startswith("NEITHER")
    assert adv.recommendation("MIXED", [True, True]).startswith("C")
