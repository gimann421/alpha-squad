"""Unit tests for W5's regret decomposition and its pre-cutoff context.

Two kinds of property are pinned here, and they fail for different reasons if they break:

  * **the decomposition is exact.** A cohort's share of a week's top-K shortfall is a fact about
    that week, not an estimate, and it is only a fact if `sum_i regret_i` reproduces the
    shortfall to the last decimal. If it ever does not, every attribution in the phase is wrong
    by an unknown residual.
  * **the context is causal.** Every explanatory variable must be computable on the Friday it
    claims to belong to. `docs/weekly/W5_PREREGISTRATION.md` §12 requires zero current-week
    outcomes and zero future weeks in any of them.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.weekly import context, regret


class TestRegretIsExactlyAdditive:
    """`sum_i regret_i` IS the week's shortfall. Not approximately -- the attribution depends
    on there being no residual term to hide a cohort's contribution in."""

    def _cell(self):
        preds = {f"p{i}": float(50 - i) for i in range(30)}
        # Realized order deliberately scrambled against predicted, with ties and zeros.
        pts = [22.1, 3.0, 14.5, 0.0, 31.7, 8.2, 0.0, 19.9, 5.5, 12.0] * 3
        real = {f"p{i}": pts[i] for i in range(30)}
        return preds, real

    @pytest.mark.parametrize("depth", regret.REGRET_DEPTHS)
    def test_sum_of_player_regret_equals_the_shortfall(self, depth):
        preds, real = self._cell()
        rows = regret.player_regret(2024, 5, "RB", preds, real)
        universe = sorted(preds)
        pred_top = sorted(universe, key=lambda p: (-preds[p], p))[:depth]
        real_top = sorted(universe, key=lambda p: (-real[p], p))[:depth]
        shortfall = sum(real[p] for p in real_top) - sum(real[p] for p in pred_top)
        assert sum(r.regret[depth] for r in rows) == pytest.approx(shortfall, abs=1e-9)

    def test_a_perfect_board_has_zero_regret_everywhere(self):
        preds = {f"p{i}": float(30 - i) for i in range(30)}
        real = {f"p{i}": float(30 - i) for i in range(30)}
        rows = regret.player_regret(2024, 5, "RB", preds, real)
        assert all(v == 0.0 for r in rows for v in r.regret.values())
        assert not any(r.false_positive or r.false_negative for r in rows)

    def test_regret_sign_convention(self):
        """Positive = the board MISSED a player who belonged in the top-K.
        Negative = the board ranked a player in the top-K who did not belong, and he still
        delivered those points -- which is a CREDIT, not damage."""
        preds = {"missed": 1.0, "promoted": 99.0, **{f"f{i}": float(50 - i) for i in range(9)}}
        real = {"missed": 99.0, "promoted": 7.0, **{f"f{i}": float(20 - i) for i in range(9)}}
        rows = {r.player_id: r for r in regret.player_regret(2024, 5, "RB", preds, real)}
        assert rows["missed"].regret[5] == pytest.approx(99.0)
        assert rows["promoted"].regret[5] == pytest.approx(-7.0)

    def test_a_promoted_bust_who_scores_zero_carries_no_regret_at_all(self):
        """The cost of promoting a bust is the MISSED regret of whoever he displaced. Charging
        it to him as well would double-count the same shortfall, which is why `slot_credit` is
        named a credit and is never summed with `missed_regret`."""
        preds = {"bust": 99.0, "missed": 1.0, **{f"f{i}": float(50 - i) for i in range(9)}}
        real = {"bust": 0.0, "missed": 40.0, **{f"f{i}": float(20 - i) for i in range(9)}}
        rows = {r.player_id: r for r in regret.player_regret(2024, 5, "RB", preds, real)}
        assert rows["bust"].regret[5] == 0.0
        assert rows["missed"].regret[5] == pytest.approx(40.0)

    def test_cohort_shares_separate_missed_points_from_slot_credit(self):
        preds = {"a": 9.0, "b": 8.0, "c": 7.0, **{f"f{i}": float(6 - i * 0.1) for i in range(20)}}
        real = {"a": 1.0, "b": 40.0, "c": 2.0, **{f"f{i}": float(i) for i in range(20)}}
        rows = regret.player_regret(2024, 5, "RB", preds, real)
        shares = regret.cohort_shares(rows, {"X": {"a", "c"}}, 5)
        assert shares["X"]["missed_regret"] >= 0.0
        assert shares["X"]["slot_credit"] >= 0.0
        assert "over_promotion" not in shares["X"]

    def test_false_positive_and_negative_match_the_frozen_definitions(self):
        preds = {f"p{i}": float(100 - i) for i in range(40)}
        # Distinct realized values, deliberately the REVERSE of the predicted order, so p0 is
        # genuinely last and p39 genuinely first rather than tied into position.
        real = {f"p{i}": float(i) for i in range(40)}
        rows = {r.player_id: r for r in regret.player_regret(2024, 5, "RB", preds, real)}
        assert rows["p0"].predicted_rank <= regret.FP_PRED_DEPTH
        assert rows["p0"].realized_rank > regret.FP_REAL_DEPTH
        assert rows["p0"].false_positive
        assert rows["p39"].false_negative


class TestCohortDefinitions:
    def _ctx(self, **kw) -> context.PlayerContext:
        base = {"player_id": "x", "position": "RB"}
        base.update(kw)
        return context.PlayerContext(**base)

    def test_thresholds_match_the_preregistration(self):
        assert context.ELITE_DEPTH == 12
        assert context.HIGH_SNAP_PCT == 0.75
        assert context.LOW_SAMPLE_GAMES == 2
        assert context.RETURNING_GAP_WEEKS == 2

    def test_each_cohort_fires_on_its_own_condition(self):
        ctx = {
            "elite": self._ctx(player_id="elite", prior_season_rank=3),
            "deep": self._ctx(player_id="deep", prior_season_rank=99),
            "snap": self._ctx(player_id="snap", snap_pct_avg_last3=0.9),
            "new": self._ctx(player_id="new", games_played_prior=1),
            "rook": self._ctx(player_id="rook", rookie_season=2024, games_played_prior=9),
            "moved": self._ctx(player_id="moved", team="KC", prior_team="LV", games_played_prior=9),
            "back": self._ctx(player_id="back", weeks_since_last_game=3, games_played_prior=9),
        }
        for c in ctx.values():
            c.games_played_prior = c.games_played_prior or 9
        out = regret.assign_cohorts(2024, ctx, list(ctx))
        assert out["ELITE_PRIOR_SEASON"] == {"elite"}
        assert out["HIGH_SNAP"] == {"snap"}
        assert out["LOW_SAMPLE"] == {"new"}
        assert out["ROOKIE"] == {"rook"}
        assert out["TEAM_CHANGE"] == {"moved"}
        assert out["RETURNING"] == {"back"}

    def test_quintile_cohorts_are_about_a_fifth_of_the_cell(self):
        ctx = {
            f"p{i}": self._ctx(player_id=f"p{i}", fp_ppr_avg_last3=float(i), games_played_prior=9)
            for i in range(20)
        }
        out = regret.assign_cohorts(2024, ctx, list(ctx))
        assert len(out["HOT_L3"]) == 4

    def test_a_player_may_belong_to_several_cohorts(self):
        """Cohorts are deliberately non-exclusive; every share is reported against its own
        complement, never against the other cohorts."""
        ctx = {
            "r": self._ctx(
                player_id="r", rookie_season=2024, games_played_prior=1, snap_pct_avg_last3=0.9
            )
        }
        out = regret.assign_cohorts(2024, ctx, ["r"])
        assert {"ROOKIE", "LOW_SAMPLE", "HIGH_SNAP"} <= {c for c, m in out.items() if "r" in m}


class TestPriorWindowIsCausal:
    def test_window_excludes_the_evaluated_week_and_everything_after(self):
        sql = context.PriorWindow(2024, 5).sql("w")
        assert "w.season < 2024" in sql
        assert "w.season = 2024 AND w.week < 5" in sql
        assert "<=" not in sql

    def test_injury_variants_and_seasons_are_the_preregistered_ones(self):
        assert context.INJURY_VARIANTS == ("STRICT", "FRIDAY")
        # 2025's nflverse injury file has no `date_modified` column, so it cannot be cut off at
        # Friday and is excluded outright rather than imputed.
        assert 2025 not in context.INJURY_SEASONS
        assert context.INJURY_SEASONS == (2021, 2022, 2023, 2024)

    def test_opponent_measure_needs_a_minimum_history(self):
        assert context.MIN_OPPONENT_WEEKS >= 3


class TestUsageOracleIsScoringFormatAware:
    """`ffopportunity` publishes FULL PPR expected points.

    Verified against this repository's own realized column rather than assumed: mean absolute
    difference 0.0124 vs `fantasy_points_ppr`, 1.259 vs Half-PPR, 2.512 vs standard, over 4,686
    RB/WR/TE player-weeks. So a Half-PPR board must have the reception credit removed, by the
    same identity W1 established for realized points. Ranking a Half-PPR board by a full-PPR
    usage score would over-rank high-volume receivers inside the one oracle that exists to be
    scoring-format neutral -- and `ORACLE_USAGE` is what P2's whole headroom estimate rests on."""

    def _con(self):
        import duckdb

        con = duckdb.connect(":memory:")
        con.execute(
            "CREATE TEMP VIEW _usage AS SELECT * FROM (VALUES "
            "('p_catcher', 2024, 5, 20.0, 10.0), "
            "('p_runner',  2024, 5, 20.0,  1.0), "
            "('p_other',   2024, 6, 99.0, 99.0)"
            ") t(player_id, season, week, points_exp, receptions_exp)"
        )
        return con

    def test_full_ppr_is_the_published_value_unchanged(self):
        out = context.load_usage_points(self._con(), 2024, 5, 1.0)
        assert out == {"p_catcher": 20.0, "p_runner": 20.0}

    def test_half_ppr_removes_half_a_point_per_expected_reception(self):
        out = context.load_usage_points(self._con(), 2024, 5, 0.5)
        assert out["p_catcher"] == pytest.approx(15.0)
        assert out["p_runner"] == pytest.approx(19.5)

    def test_standard_removes_a_full_point_per_expected_reception(self):
        out = context.load_usage_points(self._con(), 2024, 5, 0.0)
        assert out["p_catcher"] == pytest.approx(10.0)
        assert out["p_runner"] == pytest.approx(19.0)

    def test_the_format_changes_the_ORDERING_not_only_the_scale(self):
        """The reason this matters: two players tied on full-PPR expected points are NOT tied
        once the reception credit is removed, so the oracle's board genuinely differs."""
        full = context.load_usage_points(self._con(), 2024, 5, 1.0)
        half = context.load_usage_points(self._con(), 2024, 5, 0.5)
        assert full["p_catcher"] == full["p_runner"]
        assert half["p_catcher"] < half["p_runner"]

    def test_only_the_requested_week_is_returned(self):
        assert set(context.load_usage_points(self._con(), 2024, 5, 1.0)) == {
            "p_catcher",
            "p_runner",
        }


# ---------------------------------------------------------------------------------------
# Regression (W8): a floating-point mean must not depend on the order its inputs arrive in
# ---------------------------------------------------------------------------------------


def test_exact_mean_is_independent_of_input_order():
    """W8's reproduction of W5 caught SQL `avg()` over DOUBLE moving in the last bit between
    runs (parallel partial sums combine in a planner-chosen order). The replacement must give a
    bit-identical result for every permutation -- including inputs where naive left-to-right
    summation does not."""
    import functools
    import itertools
    import operator
    import random

    from alpha_squad.evaluation.weekly.context import _exact_mean

    vals = [0.1, 0.2, 0.3, 12.34, 7.7, 3.05]
    # Plain left-to-right addition, as SQL partial sums do (Python 3.12's `sum()` compensates).
    naive = {functools.reduce(operator.add, p) / len(p) for p in itertools.permutations(vals)}
    assert len(naive) > 1  # the hazard is real for this input
    assert {_exact_mean(list(p)) for p in itertools.permutations(vals)} == {_exact_mean(vals)}
    rng = random.Random(0)
    pts = [round(rng.uniform(0, 30), 2) for _ in range(200)]
    shuffled = pts[:]
    rng.shuffle(shuffled)
    assert _exact_mean(pts) == _exact_mean(shuffled)


def test_exact_mean_ignores_nulls_like_sql_avg():
    from alpha_squad.evaluation.weekly.context import _exact_mean

    assert _exact_mean([None, 2.0, None, 4.0]) == 3.0
    assert _exact_mean([None, None]) is None
    assert _exact_mean([]) is None
