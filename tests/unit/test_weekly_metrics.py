"""The frozen W2 metric suite (`docs/weekly/W2_PREREGISTRATION.md`).

Every expectation here is hand-computed from the metric's definition, not read back from the
implementation. These tests are what make "the metrics were frozen before results" checkable
rather than merely asserted: they pin tie handling, depth handling and the exclusion of tied
pairs, which are exactly the conventions a later phase would be tempted to quietly adjust.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.weekly.metrics import (
    DECISIVE_POINT_GAP,
    DEPTHS,
    CellMetrics,
    evaluate_cell,
    kendall_tau_b,
    mean_rank_error,
    pairwise_accuracy,
    spearman,
    topk_points_capture,
    topk_precision,
)


class TestSpearman:
    def test_perfect_ordering_is_one(self):
        # predicted 1,2,3,4 and realized 40,30,20,10 -> identical orderings
        assert spearman([1, 2, 3, 4], [40.0, 30.0, 20.0, 10.0]) == pytest.approx(1.0)

    def test_exactly_reversed_is_minus_one(self):
        assert spearman([1, 2, 3, 4], [10.0, 20.0, 30.0, 40.0]) == pytest.approx(-1.0)

    def test_all_outcomes_tied_is_undefined_not_zero(self):
        """Every player scoring the same gives realized rank zero variance. Returning 0.0
        would report 'no skill' where the truth is 'unmeasurable'."""
        assert spearman([1, 2, 3, 4], [5.0, 5.0, 5.0, 5.0]) is None

    def test_too_few_players_returns_none(self):
        assert spearman([1, 2], [3.0, 1.0]) is None


class TestKendall:
    def test_perfect_and_reversed(self):
        assert kendall_tau_b([1, 2, 3, 4], [40.0, 30.0, 20.0, 10.0]) == pytest.approx(1.0)
        assert kendall_tau_b([1, 2, 3, 4], [10.0, 20.0, 30.0, 40.0]) == pytest.approx(-1.0)

    def test_one_swapped_pair_by_hand(self):
        """4 players, predicted 1,2,3,4; realized 40,20,30,10. Pairs = 6.
        Discordant: only (2nd, 3rd). Concordant = 5. tau-b = (5-1)/6."""
        assert kendall_tau_b([1, 2, 3, 4], [40.0, 20.0, 30.0, 10.0]) == pytest.approx(4 / 6)

    def test_ties_in_outcome_shrink_the_denominator(self):
        """tau-b must not treat a tied outcome as a miss."""
        tau = kendall_tau_b([1, 2, 3], [10.0, 10.0, 1.0])
        assert tau is not None and tau > 0


class TestPairwise:
    def test_tied_outcomes_are_excluded_from_the_denominator(self):
        """The convention that most changes the number. Three players, two tied on 5.0:
        only the pairs involving the 1.0 scorer are decidable -> 2 pairs, both correct."""
        acc, pairs = pairwise_accuracy([1, 2, 3], [5.0, 5.0, 1.0])
        assert pairs == 2
        assert acc == pytest.approx(1.0)

    def test_all_pairs_tied_returns_none_not_zero(self):
        acc, pairs = pairwise_accuracy([1, 2, 3], [4.0, 4.0, 4.0])
        assert pairs == 0 and acc is None

    def test_decisive_gap_filters_coin_flips(self):
        """Realized 12.0 / 11.0 / 2.0 with DECISIVE_POINT_GAP = 3.0: the 12-vs-11 pair is a
        coin flip and drops out; the other two pairs remain."""
        assert DECISIVE_POINT_GAP == 3.0
        _, all_pairs = pairwise_accuracy([1, 2, 3], [12.0, 11.0, 2.0])
        acc, dec_pairs = pairwise_accuracy([1, 2, 3], [12.0, 11.0, 2.0], min_gap=3.0)
        assert all_pairs == 3
        assert dec_pairs == 2
        assert acc == pytest.approx(1.0)

    def test_a_wrong_order_is_counted_wrong(self):
        acc, pairs = pairwise_accuracy([1, 2], [1.0, 9.0])
        assert pairs == 1 and acc == pytest.approx(0.0)


class TestTopK:
    def test_precision_by_hand(self):
        """Predicted top-2 = players 0,1. Realized top-2 by points = players 0,3.
        Overlap = {0} -> 1/2."""
        assert topk_precision([1, 2, 3, 4], [30.0, 5.0, 4.0, 20.0], 2) == pytest.approx(0.5)

    def test_precision_is_none_when_the_pool_is_smaller_than_k(self):
        """Prevents a 'top-25' computed on a 12-player board -- the exact way a depth metric
        becomes meaningless for K and DST."""
        assert topk_precision([1, 2, 3], [3.0, 2.0, 1.0], 25) is None

    def test_points_capture_prices_the_miss_rather_than_counting_names(self):
        """Predicted top-2 captures 30 + 5 = 35; best possible top-2 is 30 + 20 = 50."""
        cap = topk_points_capture([1, 2, 3, 4], [30.0, 5.0, 4.0, 20.0], 2)
        assert cap == pytest.approx(35 / 50)

    def test_capture_distinguishes_two_rankings_precision_cannot(self):
        """Both rankings get precision@1 = 0. Only capture sees that one missed by far more.
        This is the reason M6 is in the suite at all."""
        realized = [50.0, 30.0, 1.0]
        near = topk_points_capture([2, 1, 3], realized, 1)  # picked the 30
        far = topk_points_capture([3, 2, 1], realized, 1)  # picked the 1
        assert topk_precision([2, 1, 3], realized, 1) == 0.0
        assert topk_precision([3, 2, 1], realized, 1) == 0.0
        assert near == pytest.approx(30 / 50)
        assert far == pytest.approx(1 / 50)
        assert near > far

    def test_capture_returns_none_when_nobody_scored(self):
        """A 0/0 division must not become a fabricated perfect 1.0."""
        assert topk_points_capture([1, 2, 3], [0.0, 0.0, 0.0], 2) is None


class TestMeanRankError:
    def test_perfect_ranking_has_zero_error(self):
        assert mean_rank_error([1, 2, 3], [9.0, 5.0, 1.0]) == pytest.approx(0.0)

    def test_by_hand(self):
        """Predicted ranks 1,2,3; realized points 5,9,1 -> realized ranks 2,1,3.
        Errors 1,1,0 -> mean 2/3."""
        assert mean_rank_error([1, 2, 3], [5.0, 9.0, 1.0]) == pytest.approx(2 / 3)


class TestEvaluateCell:
    def test_reports_every_frozen_metric_and_depth(self):
        pred = list(range(1, 61))
        realized = [float(60 - i) for i in range(60)]
        cell = evaluate_cell(pred, realized)
        assert isinstance(cell, CellMetrics)
        row = cell.as_row()
        for k in DEPTHS:
            assert f"precision@{k}" in row and f"capture@{k}" in row
            assert row[f"precision@{k}"] == pytest.approx(1.0)
        assert row["spearman"] == pytest.approx(1.0)
        assert row["n"] == 60

    def test_depths_beyond_the_pool_are_none_not_computed(self):
        cell = evaluate_cell([1, 2, 3, 4, 5], [5.0, 4.0, 3.0, 2.0, 1.0])
        assert cell.precision[10] is None
        assert cell.capture[25] is None

    def test_no_point_error_metric_is_produced(self):
        """ECR publishes no point projection. A point-error metric here would be an invented
        quantity -- the suite must not contain one."""
        row = evaluate_cell([1, 2, 3], [3.0, 2.0, 1.0]).as_row()
        assert not any(t in key.lower() for key in row for t in ("mae", "rmse", "mape"))
