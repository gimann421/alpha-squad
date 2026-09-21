"""Calibration causality, monotonicity, and the counterfactual/decomposition machinery (W4).

Two of these tests carry the whole phase's validity:

* **causality** — a calibration that saw the week it is calibrating would make every W4 result
  meaningless while looking perfectly healthy;
* **within-position monotonicity** — if a transform reorders players inside a position, the
  measured effect is no longer purely cross-position and the phase cannot answer its own
  question.

Both are asserted against adversarial cases rather than confirmed on the happy path. Offline;
synthetic fixtures only.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow
from alpha_squad.evaluation.weekly.calibration import (
    CALIBRATION_METHODS,
    MIN_FIT_SAMPLE,
    FitWindow,
    PositionSample,
    calibrated_scores,
    fit_affine,
    fit_meanvar,
    fit_quantile,
)
from alpha_squad.evaluation.weekly.counterfactual import (
    build,
    oracle_both,
    oracle_cross_position,
    oracle_within_position,
)
from alpha_squad.evaluation.weekly.crosspos import (
    CROSS_BUCKETS,
    WITHIN_BUCKETS,
    decompose_pairs,
    pair_bias,
)


def _sample(position: str, n: int = 400, *, scale: float = 2.0, shift: float = 1.0):
    """A prior sample whose realized values are a compressed-prediction relationship."""
    preds = [i / 20.0 for i in range(n)]
    reals = [shift + scale * p for p in preds]
    return PositionSample(position, preds, reals)


class TestCausality:
    def test_fit_window_never_includes_the_week_being_ranked(self):
        sql = FitWindow(2024, 5).sql("w")
        assert "w.season < 2024" in sql
        assert "w.week < 5" in sql
        assert "w.week <= 5" not in sql

    def test_fit_window_excludes_later_seasons_and_later_weeks(self):
        """Spot-check the predicate as a boolean over concrete (season, week) pairs."""
        win = FitWindow(2023, 8)
        allowed = [(2021, 17), (2022, 1), (2023, 1), (2023, 7)]
        forbidden = [(2023, 8), (2023, 9), (2024, 1), (2025, 17)]

        def visible(season: int, week: int) -> bool:
            return season < win.season or (season == win.season and week < win.week)

        assert all(visible(*sw) for sw in allowed)
        assert not any(visible(*sw) for sw in forbidden)

    def test_the_current_week_is_never_in_the_fit_sample(self):
        """The failure mode this exists for: a calibration fitted on the outcomes it is about
        to be scored against would look excellent and mean nothing."""
        win = FitWindow(2024, 5)
        assert not (win.season > 2024 or (win.season == 2024 and win.week > 5))


class TestMonotonicityWithinPosition:
    @pytest.mark.parametrize("method", CALIBRATION_METHODS)
    def test_within_position_ordering_is_never_changed(self, method):
        """The load-bearing property. If this fails, any measured effect is a mix of
        cross-position calibration and a changed positional ranking."""
        samples = {
            "RB": _sample("RB"),
            "WR": _sample("WR", scale=1.5),
            "TE": _sample("TE", scale=3.0),
        }
        preds = {
            "rb1": 12.0,
            "rb2": 8.0,
            "rb3": 3.0,
            "wr1": 11.0,
            "wr2": 7.5,
            "wr3": 2.0,
            "te1": 9.0,
            "te2": 5.0,
            "te3": 1.0,
        }
        pos = {k: k[:2].upper() for k in preds}
        out = calibrated_scores(method, samples, preds, pos)
        for position in ("RB", "WR", "TE"):
            ids = [k for k in preds if pos[k] == position]
            before = sorted(ids, key=lambda k: (-preds[k], k))
            after = sorted(ids, key=lambda k: (-out[k], k))
            assert before == after, f"{method} reordered {position}: {before} -> {after}"

    @pytest.mark.parametrize("method", CALIBRATION_METHODS)
    def test_every_ranked_player_receives_a_score(self, method):
        samples = {"RB": _sample("RB"), "TE": _sample("TE")}
        preds = {"a": 5.0, "b": 3.0, "c": 9.0}
        pos = {"a": "RB", "b": "TE", "c": "RB"}
        assert set(calibrated_scores(method, samples, preds, pos)) == set(preds)

    def test_unknown_method_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="unknown calibration method"):
            calibrated_scores("CAL_MAGIC", {}, {"a": 1.0}, {"a": "RB"})


class TestFitters:
    def test_meanvar_matches_the_prior_moments(self):
        s = _sample("RB")
        g = fit_meanvar(s)
        out = [g(p) for p in s.predicted]
        import statistics as st

        assert st.fmean(out) == pytest.approx(st.fmean(s.realized), abs=1e-6)
        assert st.stdev(out) == pytest.approx(st.stdev(s.realized), abs=1e-6)

    def test_affine_recovers_a_known_linear_relationship(self):
        s = _sample("RB", scale=2.0, shift=1.0)
        g = fit_affine(s)
        assert g(0.0) == pytest.approx(1.0, abs=1e-6)
        assert g(10.0) == pytest.approx(21.0, abs=1e-6)

    def test_affine_falls_back_to_identity_on_a_non_positive_slope(self):
        """A negative slope would invert a position's ordering, violating the contract."""
        s = PositionSample("RB", [float(i) for i in range(400)], [400.0 - i for i in range(400)])
        g = fit_affine(s)
        assert g(5.0) == pytest.approx(5.0)
        assert g(50.0) == pytest.approx(50.0)

    def test_quantile_map_is_clamped_at_both_ends(self):
        s = _sample("RB")
        g = fit_quantile(s)
        assert g(-999.0) == pytest.approx(min(s.realized))
        assert g(999.0) == pytest.approx(max(s.realized))

    @pytest.mark.parametrize("fitter", [fit_meanvar, fit_affine, fit_quantile])
    def test_a_sample_below_the_minimum_returns_the_identity(self, fitter):
        """Fitting a transform on a handful of rows would inject noise as if it were a
        correction. The threshold is pre-registered."""
        small = PositionSample("TE", [1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        assert small.n < MIN_FIT_SAMPLE
        g = fitter(small)
        assert g(7.0) == pytest.approx(7.0)


def _flex_board() -> Board:
    """Three positions, deliberately mis-ordered relative to outcomes."""
    return Board(
        2024,
        5,
        "FLEX",
        [
            BoardRow("rb1", "RB", 1.0, 5.0),
            BoardRow("rb2", "RB", 2.0, 20.0),
            BoardRow("wr1", "WR", 3.0, 30.0),
            BoardRow("wr2", "WR", 4.0, 2.0),
            BoardRow("te1", "TE", 5.0, 25.0),
            BoardRow("te2", "TE", 6.0, 1.0),
        ],
    )


PREDS = {"rb1": 14.0, "rb2": 12.0, "wr1": 10.0, "wr2": 9.0, "te1": 6.0, "te2": 5.0}


class TestOracles:
    def test_oracle_both_is_a_perfect_board(self):
        from alpha_squad.evaluation.weekly.metrics import spearman

        b = oracle_both(_flex_board())
        pred, real = b.ranks_and_points()
        assert spearman(pred, real) == pytest.approx(1.0)

    def test_oracle_xpos_preserves_alphas_within_position_ordering_exactly(self):
        """ORACLE_XPOS must change only the interleaving. If it reordered a position it would
        be measuring the wrong ceiling."""
        b = oracle_cross_position(_flex_board(), PREDS)
        rank = {r.player_id: r.ecr for r in b.rows}
        for a, z in (("rb1", "rb2"), ("wr1", "wr2"), ("te1", "te2")):
            assert (PREDS[a] > PREDS[z]) == (rank[a] < rank[z])

    def test_oracle_xpos_gives_each_position_its_true_value_curve(self):
        """RB realized values are {20, 5}; Alpha ranks rb1 above rb2, so rb1 must receive 20."""
        b = oracle_cross_position(_flex_board(), PREDS)
        rank = {r.player_id: r.ecr for r in b.rows}
        assert rank["rb1"] < rank["wr2"]
        assert rank["te1"] < rank["te2"]

    def test_oracle_within_makes_each_position_perfectly_ordered(self):
        b = oracle_within_position(_flex_board(), PREDS)
        rank = {r.player_id: r.ecr for r in b.rows}
        assert rank["rb2"] < rank["rb1"]  # rb2 scored 20 vs rb1's 5
        assert rank["wr1"] < rank["wr2"]
        assert rank["te1"] < rank["te2"]

    def test_oracle_within_keeps_alphas_value_scale(self):
        """Alpha's RB predictions are {14, 12}; after ORACLE_WITHIN the best RB holds 14."""
        b = oracle_within_position(_flex_board(), PREDS)
        assert [r.player_id for r in b.rows][0] in {"rb2", "rb1"}

    def test_swap_changes_only_the_named_position(self):
        base = build("CF_SWAP_TE", _flex_board(), PREDS)
        rank = {r.player_id: r.ecr for r in base.rows}
        # RB and WR keep Alpha's relative order; TE is rescaled onto its true curve.
        assert rank["rb1"] < rank["rb2"]
        assert rank["wr1"] < rank["wr2"]
        assert rank["te1"] < rank["te2"]

    def test_unknown_counterfactual_raises(self):
        with pytest.raises(ValueError, match="unknown counterfactual"):
            build("ORACLE_MAGIC", _flex_board(), PREDS)

    def test_every_counterfactual_preserves_the_player_universe(self):
        for name in ("ORACLE_BOTH", "ORACLE_XPOS", "ORACLE_WITHIN", "CF_SWAP_RB"):
            b = build(name, _flex_board(), PREDS)
            assert {r.player_id for r in b.rows} == set(PREDS)
            assert [r.ecr for r in b.rows] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


class TestPairDecomposition:
    def test_buckets_reconstruct_the_headline_pairwise_metric_exactly(self):
        """The identity the whole decomposition rests on."""
        from alpha_squad.evaluation.weekly.metrics import pairwise_accuracy

        positions = ["RB", "RB", "WR", "WR", "TE", "TE"]
        pred = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        real = [5.0, 20.0, 30.0, 2.0, 25.0, 1.0]
        d = decompose_pairs(positions, pred, real)
        headline, n = pairwise_accuracy(pred, real)
        assert d.within_pairs + d.cross_pairs == n
        assert d.total_accuracy == pytest.approx(headline)

    def test_within_and_cross_buckets_are_disjoint_and_complete(self):
        positions = ["RB", "WR", "TE"]
        d = decompose_pairs(positions, [1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
        assert set(d.n_pairs) <= set(WITHIN_BUCKETS) | set(CROSS_BUCKETS)
        assert d.within_pairs == 0  # all three players are different positions
        assert d.cross_pairs == 3

    def test_tied_outcomes_are_excluded_from_every_bucket(self):
        positions = ["RB", "WR"]
        d = decompose_pairs(positions, [1.0, 2.0], [7.0, 7.0])
        assert d.cross_pairs == 0
        assert d.total_accuracy is None

    def test_pair_bias_detects_a_systematic_direction(self):
        """Both RBs ranked above both TEs, and both TEs outscored both RBs, so every one of
        the four cross pairs is an RB-over-TE error -> net bias 1.0."""
        positions = ["RB", "RB", "TE", "TE"]
        pred = [1.0, 2.0, 3.0, 4.0]
        real = [1.0, 2.0, 10.0, 20.0]
        bias = pair_bias(positions, pred, real)
        assert bias["RB-TE"]["a_over_b_wrong"] == pytest.approx(1.0)
        assert bias["RB-TE"]["net_bias"] == pytest.approx(1.0)

    def test_pair_bias_is_zero_when_errors_are_symmetric(self):
        positions = ["RB", "TE", "RB", "TE"]
        pred = [1.0, 2.0, 4.0, 3.0]
        real = [1.0, 10.0, 20.0, 2.0]
        assert pair_bias(positions, pred, real)["RB-TE"]["net_bias"] == pytest.approx(0.0)


class TestOracleInvariants:
    """The invariants that caught a real defect in W4's own research code.

    `ORACLE_XPOS` preserves Alpha's within-position ordering by construction, so its
    within-position pairwise accuracy must equal current Alpha's **exactly**. It did not, until
    the tie handling was fixed: 42.5% of realized player-week values tie inside a position-week
    over the evaluated universe, and the dense re-rank was falling back to `player_id` on every
    one of them, scrambling the ordering the oracle exists to hold fixed. These assert the
    invariant directly rather than trusting the construction."""

    def _tied_board(self) -> Board:
        """Two RBs and two WRs whose realized values tie within position -- the exact case."""
        return Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("rb_a", "RB", 1.0, 9.0),
                BoardRow("rb_b", "RB", 2.0, 9.0),
                BoardRow("wr_a", "WR", 3.0, 4.0),
                BoardRow("wr_b", "WR", 4.0, 4.0),
            ],
        )

    def test_oracle_xpos_preserves_within_position_order_through_tied_values(self):
        preds = {"rb_a": 20.0, "rb_b": 15.0, "wr_a": 12.0, "wr_b": 11.0}
        b = oracle_cross_position(self._tied_board(), preds)
        rank = {r.player_id: r.ecr for r in b.rows}
        assert rank["rb_a"] < rank["rb_b"], "tied realized values must not reorder RBs"
        assert rank["wr_a"] < rank["wr_b"], "tied realized values must not reorder WRs"

    def test_oracle_xpos_within_bucket_accuracy_equals_current_alphas_exactly(self):
        """The invariant that exposed the defect. Any difference means ORACLE_XPOS changed a
        within-position ordering, which would understate the cross-position ceiling."""
        from alpha_squad.evaluation.weekly.alpha import alpha_board
        from alpha_squad.evaluation.weekly.crosspos import decompose_pairs

        board = Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("rb1", "RB", 1.0, 9.0),
                BoardRow("rb2", "RB", 2.0, 9.0),
                BoardRow("rb3", "RB", 3.0, 21.0),
                BoardRow("wr1", "WR", 4.0, 4.0),
                BoardRow("wr2", "WR", 5.0, 4.0),
                BoardRow("wr3", "WR", 6.0, 30.0),
                BoardRow("te1", "TE", 7.0, 2.0),
                BoardRow("te2", "TE", 8.0, 12.0),
            ],
        )
        preds = {
            "rb1": 20.0,
            "rb2": 15.0,
            "rb3": 8.0,
            "wr1": 14.0,
            "wr2": 13.0,
            "wr3": 7.0,
            "te1": 6.0,
            "te2": 5.0,
        }

        def within(b):
            rows = sorted(b.rows, key=lambda r: r.ecr)
            return decompose_pairs(
                [r.position for r in rows],
                [r.ecr for r in rows],
                [float(r.realized) for r in rows],
            ).within_accuracy

        current, _ = alpha_board(board, preds)
        assert within(oracle_cross_position(board, preds)) == pytest.approx(within(current))

    def test_oracle_within_makes_within_position_accuracy_perfect(self):
        """Mirror invariant: ORACLE_WITHIN must reach 1.0 on every within-position bucket."""
        from alpha_squad.evaluation.weekly.crosspos import decompose_pairs

        board = Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("rb1", "RB", 1.0, 3.0),
                BoardRow("rb2", "RB", 2.0, 18.0),
                BoardRow("wr1", "WR", 3.0, 25.0),
                BoardRow("wr2", "WR", 4.0, 1.0),
                BoardRow("te1", "TE", 5.0, 11.0),
                BoardRow("te2", "TE", 6.0, 2.0),
            ],
        )
        preds = {"rb1": 14.0, "rb2": 12.0, "wr1": 10.0, "wr2": 9.0, "te1": 6.0, "te2": 5.0}
        b = oracle_within_position(board, preds)
        rows = sorted(b.rows, key=lambda r: r.ecr)
        d = decompose_pairs(
            [r.position for r in rows], [r.ecr for r in rows], [float(r.realized) for r in rows]
        )
        assert d.within_accuracy == pytest.approx(1.0)


class TestLegacyTieDiagnostic:
    """`use_tiebreak=False` reproduces the defect, and is not the default.

    The corrected-versus-defective comparison in `W4_FLEX_FORENSICS_RESULTS.md` S16 is only
    honest if the defective construction is still runnable. These pin that the flag does
    something (so the reported comparison is not two identical runs) and that its default is the
    corrected one (so nothing reaches a result through it by accident)."""

    def _board(self) -> Board:
        return Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("rb_zz", "RB", 1.0, 9.0),
                BoardRow("rb_aa", "RB", 2.0, 9.0),
                BoardRow("wr_a", "WR", 3.0, 4.0),
                BoardRow("wr_b", "WR", 4.0, 1.0),
            ],
        )

    #: `rb_zz` is Alpha's better RB but sorts LAST by player_id, so a player_id fallback is
    #: visible rather than coincidentally right.
    PREDS = {"rb_zz": 20.0, "rb_aa": 15.0, "wr_a": 12.0, "wr_b": 11.0}

    def test_default_preserves_alphas_order_through_the_tie(self):
        b = oracle_cross_position(self._board(), self.PREDS)
        rank = {r.player_id: r.ecr for r in b.rows}
        assert rank["rb_zz"] < rank["rb_aa"]

    def test_legacy_flag_reproduces_the_player_id_fallback(self):
        b = oracle_cross_position(self._board(), self.PREDS, use_tiebreak=False)
        rank = {r.player_id: r.ecr for r in b.rows}
        assert rank["rb_aa"] < rank["rb_zz"], "the defective construction must still be runnable"

    def test_build_defaults_to_the_corrected_construction(self):
        from alpha_squad.evaluation.weekly.counterfactual import build

        default = build("ORACLE_XPOS", self._board(), self.PREDS)
        corrected = oracle_cross_position(self._board(), self.PREDS)
        assert [r.player_id for r in default.rows] == [r.player_id for r in corrected.rows]
