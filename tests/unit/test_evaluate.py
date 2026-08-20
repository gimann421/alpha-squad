"""Unit tests for the shared evaluation harness against hand-computed expected values."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.models.evaluate import evaluate_and_record, evaluate_predictions, record_evaluation
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


class TestEvaluatePredictions:
    def test_perfect_predictions_have_zero_error_and_perfect_correlation(self):
        actual = {"p1": 100.0, "p2": 80.0, "p3": 60.0, "p4": 40.0}
        m = evaluate_predictions("test", 2024, "ALL", dict(actual), actual)
        assert m.mae == pytest.approx(0.0)
        assert m.rmse == pytest.approx(0.0)
        assert m.r2 == pytest.approx(1.0)
        assert m.spearman == pytest.approx(1.0)
        assert m.tier_accuracy == pytest.approx(1.0)

    def test_mae_matches_hand_computation(self):
        actual = {"p1": 100.0, "p2": 50.0}
        predicted = {"p1": 90.0, "p2": 60.0}
        m = evaluate_predictions("test", 2024, "ALL", predicted, actual)
        assert m.mae == pytest.approx(10.0)
        assert m.rmse == pytest.approx(10.0)

    def test_only_common_players_are_scored(self):
        actual = {"p1": 100.0, "p2": 50.0, "p3": 30.0}
        predicted = {"p1": 100.0, "p4": 999.0}  # p4 not in actual, p2/p3 not predicted
        m = evaluate_predictions("test", 2024, "ALL", predicted, actual)
        assert m.n == 1
        assert m.mae == pytest.approx(0.0)

    def test_empty_overlap_returns_zero_n_and_nan_metrics(self):
        m = evaluate_predictions("test", 2024, "ALL", {"p1": 1.0}, {"p2": 2.0})
        assert m.n == 0
        assert m.mae != m.mae  # NaN

    def test_top12_hit_rate_counts_overlap_not_order(self):
        # 24 players; predicted top-12 differs from actual top-12 by exactly 2 swaps.
        actual = {f"p{i}": float(24 - i) for i in range(24)}  # p0 highest .. p23 lowest
        predicted = dict(actual)
        # swap p11 (12th best) and p12 (13th best) predicted scores so p12 now ranks ahead
        predicted["p11"], predicted["p12"] = predicted["p12"], predicted["p11"]
        m = evaluate_predictions("test", 2024, "ALL", predicted, actual)
        assert m.top12_hit_rate == pytest.approx(11 / 12)

    def test_top12_hit_rate_is_none_when_fewer_than_12_common_players(self):
        actual = {f"p{i}": float(i) for i in range(5)}
        m = evaluate_predictions("test", 2024, "ALL", dict(actual), actual)
        assert m.top12_hit_rate is None

    def test_tier_accuracy_penalizes_cross_tier_misrank(self):
        # 24 players in rank order; predicted flips the #1 and #13 (different tiers).
        actual = {f"p{i}": float(24 - i) for i in range(24)}
        predicted = dict(actual)
        predicted["p0"], predicted["p12"] = predicted["p12"], predicted["p0"]
        m = evaluate_predictions("test", 2024, "ALL", predicted, actual)
        assert m.tier_accuracy < 1.0


def test_all_positions_rollup_excludes_non_skill_positions(con):
    """Regression test for a real bug: player_season_stats holds every position (LB, CB, K,
    etc.), most of which correctly score ~0 PPR points. Pooling them into the 'ALL' rollup
    diluted it with hundreds of trivially-correct near-zero pairs, making 'ALL' MAE look far
    better than any individual skill position's real MAE. The fix scopes 'ALL' to
    QB/RB/WR/TE only."""
    rows = [
        ("qb1", "QB", 300.0),
        ("wr1", "WR", 150.0),
        ("wr2", "WR", 5.0),
    ] + [(f"lb{i}", "LB", 0.0) for i in range(50)]
    for pid, pos, pts in rows:
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, 2024, ?, 15, ?, ?)",
            [pid, pos, pts, pts / 15],
        )

    # A deliberately bad model: way off on the skill players, perfectly correct on every LB
    # (who all score exactly 0, easy to "predict").
    predicted = {"qb1": 100.0, "wr1": 50.0, "wr2": 55.0, **{f"lb{i}": 0.0 for i in range(50)}}

    results = evaluate_and_record(con, "bad_model", 2024, predicted)
    all_metric = next(m for m in results if m.position == "ALL")

    assert all_metric.n == 3, "the ALL rollup must only include the 3 skill-position players"
    # True MAE over just qb1/wr1/wr2: (200 + 100 + 50) / 3 = 116.67. If the 50 perfectly-
    # predicted LBs leaked in, this would collapse toward ~6.6.
    assert all_metric.mae == pytest.approx(350 / 3)


def test_record_evaluation_upserts_without_duplicating(con):
    m1 = evaluate_predictions("test_model", 2024, "ALL", {"p1": 10.0}, {"p1": 12.0})
    record_evaluation(con, m1)
    record_evaluation(con, m1)
    n = con.execute(
        "SELECT count(*) FROM evaluation_results WHERE model_name='test_model' AND season=2024"
    ).fetchone()[0]
    assert n == 1
