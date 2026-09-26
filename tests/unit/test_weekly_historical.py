"""W10: historical-only baseline, W5 misses, movement categories, and the §5 verdict order."""

from __future__ import annotations

import math

import pytest

from alpha_squad.evaluation.weekly import historical as hist


def test_categories_cover_exactly_w9s_seven_features():
    from alpha_squad.evaluation.weekly.mechanisms import DURABLE_FEATURES

    flat = [f for fs in hist.CATEGORIES.values() for f in fs]
    assert sorted(flat) == sorted(DURABLE_FEATURES)
    assert len(flat) == len(set(flat))


def test_historical_only_order():
    ids = ["c", "a", "b", "d"]
    ppg = {"a": 10.0, "b": 15.0, "c": None, "d": float("nan")}
    assert hist.historical_only_order(ids, ppg) == ["b", "a", "c", "d"]


def test_historical_only_order_breaks_ties_by_id():
    assert hist.historical_only_order(["z", "y"], {"z": 5.0, "y": 5.0}) == ["y", "z"]


def test_miss_counts_match_w5_definitions():
    # 30 players, realized points descending by index; the board reverses the top 10
    pts = {f"p{i:02d}": float(100 - i) for i in range(30)}
    order = sorted(pts)[::-1]  # predicts the WORST players first
    m = hist.miss_counts(order, pts)
    # predicted top-10 are realized ranks 21-30: those ranked 25-30 are false positives
    assert m["false_positive"] == 6
    # realized top-5 sit at predicted ranks 26-30 (> 24): all five are false negatives
    assert m["false_negative"] == 5
    perfect = hist.miss_counts(sorted(pts), pts)
    assert perfect == {"false_positive": 0, "false_negative": 0}


@pytest.mark.parametrize(
    ("rank", "last", "ppg", "expected"),
    [
        (5, 8.0, 15.0, True),
        (5, 16.0, 15.0, False),
        (13, 8.0, 15.0, False),
        (None, 8.0, 15.0, False),
        (5, math.nan, 15.0, False),
    ],
)
def test_quiet_star(rank, last, ppg, expected):
    assert hist.quiet_star(rank, last, ppg) is expected


def test_movement_category_precedence():
    assert hist.movement_category(3, 5.0, 15.0, 1, 20.0, 5.0) == "QUIET_STAR"
    assert hist.movement_category(30, 5.0, 15.0, 1, 20.0, 5.0) == "SMALL_SAMPLE"
    assert hist.movement_category(30, 5.0, 15.0, 5, 20.0, 15.0) == "ROLE_STRONGER_BEFORE"
    assert hist.movement_category(30, 5.0, 15.0, 5, 10.0, 15.0) == "ROLE_STRONGER_NOW"
    assert hist.movement_category(30, 5.0, 15.0, 5, 10.0, 11.0) == "OTHER"
    assert hist.movement_category(None, None, None, None, None, None) == "OTHER"


def _r(m, lo, hi):
    return {"mean_diff": m, "ci_low": lo, "ci_high": hi}


GOOD = {
    "full": _r(0.025, 0.008, 0.04),
    "seasons": [0.03, 0.02, 0.01, 0.04, -0.01],
    "loso": [_r(0.02, 0.001, 0.04)] * 4 + [_r(0.02, -0.001, 0.04)],
    "early": _r(0.04, 0.0, 0.08),
    "late": _r(0.01, -0.02, 0.04),
    "ecr_minus_a": 0.03,
}


def test_success_needs_every_condition():
    v = hist.verdict({"WR|capture@10": GOOD}, {"WR|capture@10": GOOD}, {})
    assert v["verdict"] == "SUCCESS" and v["success_cells"] == ["WR|capture@10"]
    for key, bad in (
        ("full", _r(0.015, 0.001, 0.03)),  # below the bar
        ("seasons", [0.03, 0.02, -0.01, -0.04, 0.01]),  # 3/5 positive
        ("loso", [_r(0.02, 0.001, 0.04)] * 3 + [_r(0.02, -0.001, 0.04)] * 2),
        ("early", _r(0.005, -0.02, 0.03)),  # smaller than late
        ("ecr_minus_a", 0.09),  # closes < 1/3
    ):
        cell = GOOD | {key: bad}
        assert (
            hist.verdict({"WR|capture@10": cell}, {"WR|capture@10": cell}, {})["verdict"]
            != "SUCCESS"
        )


def test_breach_blocks_success_and_becomes_a_tradeoff():
    v = hist.verdict(
        {"WR|capture@10": GOOD},
        {"WR|capture@10": GOOD},
        {"TE|capture@10": _r(-0.01, -0.02, -0.001)},
    )
    assert v["verdict"] == "PARTIAL" and v["tradeoff"] and v["breaches"] == ["TE|capture@10"]


def test_harm_requires_no_compensating_gain():
    null = {"full": _r(0.001, -0.01, 0.01), "early": _r(0.002, -0.02, 0.02)}
    v = hist.verdict(
        {"RB|capture@10": null}, {"RB|capture@10": null}, {"WR|spearman": _r(-0.01, -0.02, -0.004)}
    )
    assert v["verdict"] == "HARM"


def test_small_significant_degradation_is_not_a_breach():
    assert not hist.is_breach(_r(-0.003, -0.005, -0.001))
    assert hist.is_breach(_r(-0.006, -0.01, -0.001))


def test_early_only_gain_is_partial():
    cell = {"full": _r(0.01, -0.005, 0.025), "early": _r(0.03, 0.005, 0.06)}
    assert (
        hist.verdict({"RB|capture@10": cell}, {"RB|capture@10": cell}, {})["verdict"] == "PARTIAL"
    )


def test_no_effect():
    null = {"full": _r(0.001, -0.01, 0.01), "early": _r(0.002, -0.02, 0.02)}
    assert (
        hist.verdict({"RB|capture@10": null}, {"RB|capture@10": null}, {})["verdict"] == "NO EFFECT"
    )


def test_missing_rows_never_count():
    assert not hist.is_breach(None) and not hist.meets_s1(None)
    empty = {"full": None, "seasons": [], "loso": [], "early": None, "late": None}
    conds = hist.success_conditions(empty | {"ecr_minus_a": None})
    assert not any(conds.values())
    assert hist.verdict({"WR|capture@10": empty}, {"WR|capture@10": empty}, {"x": None})[
        "verdict"
    ] == ("NO EFFECT")


def test_ecr_gap_share_needs_ecr_ahead():
    # Alpha already level with or ahead of ECR: the "narrows the gap" condition cannot hold.
    for ecr in (0.0, -0.01):
        assert not hist.success_conditions(GOOD | {"ecr_minus_a": ecr})["S3"]
