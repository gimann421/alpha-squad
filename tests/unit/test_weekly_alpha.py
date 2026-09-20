"""Alpha's weekly board construction and W3's declared reporting additions.

The universe rules are the part of W3 most able to produce a wrong answer quietly: if Alpha
were scored on a different player set from ECR, every comparison in the phase would be
meaningless while still looking fine. These tests pin that, plus the hand-computable parts of
the paired test and the FLEX composition diagnostic.

Offline; synthetic fixtures only.
"""

from __future__ import annotations

import math

import pytest

from alpha_squad.evaluation.weekly.alpha import (
    ALPHA_POSITIONS,
    alpha_board,
    restrict_board,
)
from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow
from alpha_squad.evaluation.weekly.diagnostics import (
    flex_composition,
    paired_outcome,
    point_diagnostics,
    wilcoxon_signed_rank,
)


def _ref() -> Board:
    """An ECR-shaped reference board: ECR order a < b < c < d, mixed outcomes."""
    return Board(
        2024,
        5,
        "FLEX",
        [
            BoardRow("a", "RB", 1.0, 10.0),
            BoardRow("b", "WR", 2.0, 25.0),
            BoardRow("c", "TE", 3.0, 3.0),
            BoardRow("d", "RB", 4.0, 18.0),
        ],
    )


class TestAlphaBoard:
    def test_ranks_by_predicted_points_descending(self):
        board, _ = alpha_board(_ref(), {"a": 5.0, "b": 20.0, "c": 1.0, "d": 12.0})
        assert [r.player_id for r in board.rows] == ["b", "d", "a", "c"]
        assert [r.ecr for r in board.rows] == [1.0, 2.0, 3.0, 4.0]

    def test_realized_outcomes_travel_with_the_player(self):
        """A reordering must not detach a player from his own outcome — the failure that would
        silently score every system against the wrong points."""
        board, _ = alpha_board(_ref(), {"a": 5.0, "b": 20.0, "c": 1.0, "d": 12.0})
        assert {r.player_id: r.realized for r in board.rows} == {
            "a": 10.0,
            "b": 25.0,
            "c": 3.0,
            "d": 18.0,
        }

    def test_a_player_alpha_cannot_predict_is_dropped_and_counted_never_imputed(self):
        """Imputing a prediction would fabricate the quantity under test."""
        board, cov = alpha_board(_ref(), {"a": 5.0, "b": 20.0})
        assert [r.player_id for r in board.rows] == ["b", "a"]
        assert cov.universe == 4
        assert cov.alpha_ranked == 2
        assert set(cov.missing_player_ids) == {"c", "d"}
        assert cov.coverage == pytest.approx(0.5)

    def test_ties_break_deterministically(self):
        board, _ = alpha_board(_ref(), {"a": 9.0, "b": 9.0, "c": 9.0, "d": 9.0})
        assert [r.player_id for r in board.rows] == ["a", "b", "c", "d"]

    def test_universe_comes_from_the_reference_not_from_alphas_predictions(self):
        """Alpha predicts a player who is not on the ECR board; he must NOT appear. Otherwise
        the systems would rank different player sets and the pairing would be broken."""
        board, cov = alpha_board(_ref(), {"a": 5.0, "b": 20.0, "c": 1.0, "d": 12.0, "zz": 99.0})
        assert "zz" not in [r.player_id for r in board.rows]
        assert cov.universe == 4

    def test_restrict_board_shrinks_ecr_to_alphas_coverage_preserving_order(self):
        out = restrict_board(_ref(), {"a", "d"})
        assert [r.player_id for r in out.rows] == ["a", "d"]
        assert [r.ecr for r in out.rows] == [1.0, 2.0]

    def test_alpha_covers_only_the_four_skill_positions(self):
        """K and DST are absent from the model by design and are not retrofitted in W3."""
        assert ALPHA_POSITIONS == ("QB", "RB", "WR", "TE")
        assert "K" not in ALPHA_POSITIONS and "DST" not in ALPHA_POSITIONS


class TestWilcoxon:
    def test_all_differences_positive_gives_a_small_p_and_effect_of_one(self):
        w, p, rb = wilcoxon_signed_rank([0.1 * i for i in range(1, 16)])
        assert w == 0.0
        assert p < 0.001
        assert rb == pytest.approx(1.0)

    def test_symmetric_differences_are_not_significant(self):
        diffs = [0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4, 0.5, -0.5]
        _, p, rb = wilcoxon_signed_rank(diffs)
        assert p > 0.5
        assert rb == pytest.approx(0.0)

    def test_zero_differences_are_dropped_not_counted_as_agreement(self):
        """Wilcoxon's standard treatment. Counting them would dilute the statistic toward
        no-effect and understate a real difference."""
        w_with, p_with, _ = wilcoxon_signed_rank([0.0] * 8 + [0.1 * i for i in range(1, 9)])
        w_without, p_without, _ = wilcoxon_signed_rank([0.1 * i for i in range(1, 9)])
        assert (w_with, p_with) == (w_without, p_without)

    def test_too_few_pairs_returns_nan_rather_than_a_fake_p_value(self):
        assert all(math.isnan(v) for v in wilcoxon_signed_rank([0.1, 0.2, 0.3]))


class TestPairedOutcome:
    def test_win_loss_tie_counts_are_exact(self):
        a = {f"w{i}": v for i, v in enumerate([0.6, 0.5, 0.7, 0.5, 0.9])}
        b = {f"w{i}": v for i, v in enumerate([0.5, 0.6, 0.7, 0.4, 0.8])}
        out = paired_outcome("spearman", "Alpha", "ECR", a, b)
        assert (out.a_wins, out.b_wins, out.ties) == (3, 1, 1)
        assert out.n_weeks == 5
        assert out.median_diff == pytest.approx(0.1)

    def test_only_weeks_both_systems_cover_are_compared(self):
        a = {f"w{i}": 0.6 for i in range(10)}
        b = {f"w{i}": 0.5 for i in range(4)}
        assert paired_outcome("m", "A", "B", a, b).n_weeks == 4


class TestPointDiagnostics:
    def test_mae_rmse_and_bias_by_hand(self):
        pred = [10.0] * 5 + [20.0] * 5
        real = [12.0] * 5 + [18.0] * 5
        d = point_diagnostics(pred, real)
        assert d.mae == pytest.approx(2.0)
        assert d.rmse == pytest.approx(2.0)
        assert d.mean_signed_bias == pytest.approx(0.0)

    def test_signed_bias_keeps_its_sign(self):
        d = point_diagnostics([10.0] * 20, [7.0] * 20)
        assert d.mean_signed_bias == pytest.approx(3.0)
        assert d.mae == pytest.approx(3.0)

    def test_too_small_a_sample_returns_none(self):
        assert point_diagnostics([1.0, 2.0], [1.0, 2.0]) is None


class TestFlexComposition:
    def test_over_representation_is_predicted_minus_realized(self):
        """The concrete cross-position calibration signal: a position that fills more of the
        predicted top-k than it does of the realized top-k is being over-valued by the pooled
        ordering."""
        positions = ["RB", "RB", "WR", "WR"]
        pred_rank = [1.0, 2.0, 3.0, 4.0]  # RBs predicted best
        realized = [1.0, 2.0, 30.0, 40.0]  # WRs actually best
        comp = flex_composition(positions, pred_rank, realized, 2)
        assert comp["RB"]["predicted_share"] == pytest.approx(1.0)
        assert comp["RB"]["realized_share"] == pytest.approx(0.0)
        assert comp["RB"]["over_representation"] == pytest.approx(1.0)
        assert comp["WR"]["over_representation"] == pytest.approx(-1.0)

    def test_pool_share_is_reported_as_the_reference(self):
        positions = ["RB", "WR", "WR", "TE"]
        comp = flex_composition(positions, [1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0], 2)
        assert comp["WR"]["pool_share"] == pytest.approx(0.5)
        assert comp["TE"]["pool_share"] == pytest.approx(0.25)

    def test_none_when_the_pool_is_smaller_than_k(self):
        assert flex_composition(["RB"], [1.0], [5.0], 10) is None
