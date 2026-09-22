"""Unit tests for W5's top-of-board instruments.

The properties pinned here are the ones a result would be *wrong* without, and three of them
already caught defects during W5's construction:

  * the copula null must achieve the Spearman it is asked for **against the cell's own ties**.
    A first version was ~0.017 low, which would have handed the null a worse board than Alpha
    and flattered this phase's own pre-registered answer;
  * a conditional correlation may only be compared between systems whose scores share a scale.
    A first version correlated Alpha's compressed point predictions against outcomes on one side
    and a uniform RANK against the same outcomes on the other, making the null look 5x worse at
    the top purely through the mismatch;
  * an oracle must preserve the property it exists to isolate, through ties (W4's lesson, D112).

`docs/weekly/W5_PREREGISTRATION.md` §6 and §12 require all of these to hold before any result is
interpreted.
"""

from __future__ import annotations

import math
import statistics

import pytest

from alpha_squad.evaluation.weekly import nulls, topboard
from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow
from alpha_squad.evaluation.weekly.metrics import pairwise_accuracy, spearman


def _board(rows: list[tuple[str, str, float, float]]) -> Board:
    return Board(2024, 5, "RB", [BoardRow(p, pos, ecr, real) for p, pos, ecr, real in rows])


#: A realistic positional cell: heavy right tail, and a block of players who scored exactly 0.0,
#: which is what makes tie handling load-bearing rather than cosmetic.
def _realistic(n: int = 60, zeros: int = 12, seed: int = 11) -> list[float]:
    rng = nulls._Rng(seed)
    vals = sorted(
        (max(0.0, round(rng.normal() * 7 + 8, 1)) for _ in range(n - zeros)), reverse=True
    )
    return vals + [0.0] * zeros


class TestCopulaNullCalibration:
    """The null must be a ranker with ALPHA's overall ordering quality -- not approximately."""

    @pytest.mark.parametrize("target", [0.25, 0.45, 0.65, 0.80])
    def test_achieves_the_requested_spearman_against_real_tie_structure(self, target):
        real = _realistic()
        latent = nulls.calibrate_latent(real, target, 2024, 5, "RB")
        got = [
            spearman(
                nulls.draw_null_ranking(real, target, 2024, 5, "RB", d, latent=latent).pred_rank,
                real,
            )
            for d in range(nulls.N_SIM)
        ]
        assert statistics.fmean(got) == pytest.approx(target, abs=1e-3)

    def test_skipping_the_tie_calibration_is_biased_low(self):
        """The bias the calibration exists to remove is real and runs the dangerous way.

        Low by construction means the null gets a WORSE board than Alpha, which would make Alpha
        look better at the top than it is -- exactly the pre-registered expectation."""
        real = _realistic()
        target = 0.45
        closed = nulls.pearson_for_spearman(target)
        got = [
            spearman(
                nulls.draw_null_ranking(real, target, 2024, 5, "RB", d, latent=closed).pred_rank,
                real,
            )
            for d in range(nulls.N_SIM)
        ]
        assert statistics.fmean(got) < target - 0.005

    def test_is_deterministic(self):
        real = _realistic()
        a = nulls.calibrate_latent(real, 0.6, 2023, 9, "WR")
        b = nulls.calibrate_latent(real, 0.6, 2023, 9, "WR")
        assert a == b
        d1 = nulls.draw_null_ranking(real, 0.6, 2023, 9, "WR", 7, latent=a).pred_rank
        d2 = nulls.draw_null_ranking(real, 0.6, 2023, 9, "WR", 7, latent=b).pred_rank
        assert d1 == d2

    def test_different_cells_do_not_share_a_draw(self):
        real = _realistic()
        a = nulls.draw_null_ranking(real, 0.6, 2023, 9, "WR", 0, latent=0.62).pred_rank
        b = nulls.draw_null_ranking(real, 0.6, 2023, 10, "WR", 0, latent=0.62).pred_rank
        c = nulls.draw_null_ranking(real, 0.6, 2023, 9, "RB", 0, latent=0.62).pred_rank
        assert a != b and a != c

    def test_pearson_for_spearman_inverts_the_closed_form(self):
        for rho_s in (0.1, 0.35, 0.6, 0.9):
            rho_p = nulls.pearson_for_spearman(rho_s)
            assert (6.0 / math.pi) * math.asin(rho_p / 2.0) == pytest.approx(rho_s, abs=1e-12)

    def test_normal_scores_average_ties(self):
        """Tied outcomes must land on the same latent position, or the null quietly gains
        information the tied outcomes do not contain."""
        z = nulls.normal_scores([1.0, 0.0, 0.0, 5.0])
        assert z[1] == pytest.approx(z[2])
        assert z[3] > z[0] > z[1]


class TestOracleInvariants:
    """W4 (D112) lost a reportable number to oracle tie handling. These assert, not reason."""

    def _cell(self):
        board = _board(
            [
                ("rb_zz", "RB", 1.0, 9.0),
                ("rb_aa", "RB", 2.0, 9.0),
                ("rb_mm", "RB", 3.0, 21.0),
                ("rb_bb", "RB", 4.0, 0.0),
                ("rb_cc", "RB", 5.0, 0.0),
            ]
        )
        preds = {"rb_zz": 20.0, "rb_aa": 15.0, "rb_mm": 8.0, "rb_bb": 7.0, "rb_cc": 6.0}
        return board, preds

    def test_oracle_outcome_is_perfect(self):
        board, preds = self._cell()
        b = topboard.oracle_outcome(board, preds)
        pred, real = b.ranks_and_points()
        acc, pairs = pairwise_accuracy(pred, real)
        assert pairs > 0
        assert acc == 1.0

    def test_oracle_outcome_breaks_ties_toward_alpha_not_player_id(self):
        board, preds = self._cell()
        rank = {r.player_id: r.ecr for r in topboard.oracle_outcome(board, preds).rows}
        # rb_zz and rb_aa both scored 9.0; Alpha preferred rb_zz, which sorts LAST by player_id.
        assert rank["rb_zz"] < rank["rb_aa"]
        assert rank["rb_bb"] < rank["rb_cc"]

    def test_oracle_usage_is_invariant_to_monotone_rescaling_of_usage(self):
        board, preds = self._cell()
        usage = {"rb_zz": 3.0, "rb_aa": 11.0, "rb_mm": 7.0, "rb_bb": 1.0, "rb_cc": 2.0}
        a, _ = topboard.oracle_usage(board, preds, usage)
        b, _ = topboard.oracle_usage(board, preds, {k: math.exp(v / 4) for k, v in usage.items()})
        assert [r.player_id for r in a.rows] == [r.player_id for r in b.rows]

    def test_oracle_usage_keeps_the_universe_and_counts_its_coverage(self):
        board, preds = self._cell()
        b, covered = topboard.oracle_usage(board, preds, {"rb_mm": 30.0})
        assert {r.player_id for r in b.rows} == {r.player_id for r in board.rows}
        assert covered == 1
        # The uncovered players fall back to Alpha's own score -- never to 0.0, which would
        # fabricate a usage value and bury every uncovered player.
        assert b.rows[0].player_id == "rb_mm"
        assert [r.player_id for r in b.rows[1:]] == ["rb_zz", "rb_aa", "rb_bb", "rb_cc"]

    def test_every_board_ranks_the_identical_player_set(self):
        board, preds = self._cell()
        usage = {"rb_zz": 3.0, "rb_aa": 11.0}
        expect = {r.player_id for r in board.rows}
        assert {r.player_id for r in topboard.oracle_outcome(board, preds).rows} == expect
        assert {r.player_id for r in topboard.oracle_usage(board, preds, usage)[0].rows} == expect


class TestConditionalStatistics:
    def test_conditional_spearman_is_scale_free(self):
        preds = {f"p{i}": float(30 - i) for i in range(30)}
        real = {f"p{i}": float((i * 7) % 23) for i in range(30)}
        a = topboard.conditional_spearman(preds, real, depth=10)
        squashed = {k: math.log1p(v) for k, v in preds.items()}
        assert topboard.conditional_spearman(squashed, real, depth=10) == pytest.approx(a)

    def test_conditional_pearson_is_not_scale_free(self):
        """The reason a raw Pearson may not be compared between systems -- pinned so the
        comparability rule cannot be quietly dropped later."""
        preds = {f"p{i}": float(30 - i) for i in range(30)}
        real = {f"p{i}": float((i * 7) % 23) for i in range(30)}
        a = topboard.conditional_correlation(preds, real, depth=10)
        squashed = {k: math.exp(v / 3) for k, v in preds.items()}
        assert topboard.conditional_correlation(squashed, real, depth=10) != pytest.approx(a)

    def test_transplant_values_gives_the_target_value_curve(self):
        out = topboard.transplant_values(["c", "a", "b"], [1.0, 9.0, 5.0])
        assert out == {"c": 9.0, "a": 5.0, "b": 1.0}

    def test_conditional_statistics_need_a_full_depth(self):
        preds = {"a": 3.0, "b": 2.0}
        real = {"a": 1.0, "b": 5.0}
        assert topboard.conditional_correlation(preds, real, depth=10) is None
        assert topboard.conditional_spearman(preds, real, depth=10) is None


class TestDepthWindows:
    def test_a_perfect_ranking_scores_one_in_every_band(self):
        preds = {f"p{i}": float(100 - i) for i in range(60)}
        real = {f"p{i}": float(100 - i) for i in range(60)}
        for w in topboard.depth_windows(preds, real):
            assert w.accuracy is None or w.accuracy == 1.0

    def test_tied_outcomes_are_excluded_from_the_denominator(self):
        preds = {f"p{i}": float(10 - i) for i in range(10)}
        real = dict.fromkeys(preds, 0.0)
        for w in topboard.depth_windows(preds, real, windows=((1, 10),)):
            assert w.pairs == 0
            assert w.accuracy is None

    def test_windows_are_contiguous_and_non_overlapping(self):
        lo_hi = topboard.CURVE_WINDOWS
        for (_, hi), (lo2, _) in zip(lo_hi[:-1], lo_hi[1:], strict=True):
            assert lo2 == hi + 1
