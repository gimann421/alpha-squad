"""Unit tests for the failure-analysis module (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.failure_analysis import worst_edge_misses, worst_rookie_misses
from alpha_squad.market.edge import DEFAULT_ECR_TYPE
from alpha_squad.market.series import series_for_ecr_type
from alpha_squad.storage.db import init_db

MIN_CURVE_TRAINING_ROWS = 10


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_curve_training(con, season_before, ecr_type=DEFAULT_ECR_TYPE):
    for i in range(MIN_CURVE_TRAINING_ROWS + 5):
        player_id = f"train_{i}"
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES (?, ?, ?, 'WR', ?, ?)",
            [
                player_id,
                f"{season_before}-08-01",
                ecr_type,
                float(i + 1),
                series_for_ecr_type(ecr_type).page_type,
            ],
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'WR', 15, ?, ?)",
            [player_id, season_before, 300.0 - i * 10, (300.0 - i * 10) / 15],
        )


def _seed_edge_row(
    con,
    player_id,
    display_name,
    season,
    action,
    rank_edge,
    market_rank,
    actual_points,
    ecr_type=DEFAULT_ECR_TYPE,
):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, 'WR')",
        [player_id, f"gsis_{player_id}", display_name],
    )
    con.execute(
        """
        INSERT INTO edge_snapshot
            (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
             market_rank, rank_edge, projected_points_edge, probability_edge, evidence_score,
             confidence, action, reasons_json, built_at)
        VALUES (?, ?, ?, 'WR', ?, 'edge_v1', ?, ?, ?, 0.0, 0.0, 0.9, 0.9, ?, '[]', current_timestamp)
        """,
        [
            f"edge_{player_id}",
            player_id,
            season,
            ecr_type,
            max(int(market_rank) - rank_edge, 1),
            market_rank,
            rank_edge,
            action,
        ],
    )
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'WR', 15, ?, ?)",
        [player_id, season, actual_points, actual_points / 15],
    )


class TestWorstEdgeMisses:
    def test_bad_buy_call_ranks_above_a_good_buy_call(self, con):
        _seed_curve_training(con, 2022)
        _seed_edge_row(
            con, "bad_buy", "Bad Buy", 2023, "BUY", rank_edge=50, market_rank=100, actual_points=5.0
        )
        _seed_edge_row(
            con,
            "good_buy",
            "Good Buy",
            2023,
            "BUY",
            rank_edge=50,
            market_rank=100,
            actual_points=400.0,
        )
        misses = worst_edge_misses(con, 2023, 2023, top_n=10)
        names = [m.display_name for m in misses]
        assert names.index("Bad Buy") < names.index("Good Buy")

    def test_bad_sell_call_that_outperformed_ranks_as_a_miss(self, con):
        _seed_curve_training(con, 2022)
        _seed_edge_row(
            con,
            "bad_sell",
            "Bad Sell",
            2023,
            "SELL",
            rank_edge=-50,
            market_rank=5,
            actual_points=400.0,
        )
        misses = worst_edge_misses(con, 2023, 2023, top_n=10)
        assert any(m.display_name == "Bad Sell" and m.miss_magnitude > 0 for m in misses)

    def test_top_n_is_respected(self, con):
        _seed_curve_training(con, 2022)
        for i in range(5):
            _seed_edge_row(
                con,
                f"p{i}",
                f"P{i}",
                2023,
                "BUY",
                rank_edge=50,
                market_rank=100,
                actual_points=float(i),
            )
        misses = worst_edge_misses(con, 2023, 2023, top_n=2)
        assert len(misses) == 2

    def test_watch_hold_actions_are_excluded(self, con):
        _seed_curve_training(con, 2022)
        _seed_edge_row(
            con,
            "watcher",
            "Watcher",
            2023,
            "WATCH",
            rank_edge=50,
            market_rank=100,
            actual_points=5.0,
        )
        misses = worst_edge_misses(con, 2023, 2023, top_n=10)
        assert misses == []


class TestWorstRookieMisses:
    def test_ranks_by_absolute_error_descending(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, rookie_season) "
            "VALUES ('close', 'gsis_close', 'Close', 'WR', 2020)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('close', 2020, 'WR', 15, 100.0, 6.7)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, predicted_at) VALUES "
            "('p1', 'close', 2020, 'WR', 'v1', 105.0, current_timestamp)"
        )
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, rookie_season) "
            "VALUES ('far', 'gsis_far', 'Far', 'WR', 2020)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('far', 2020, 'WR', 15, 10.0, 0.7)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, predicted_at) VALUES "
            "('p2', 'far', 2020, 'WR', 'v1', 200.0, current_timestamp)"
        )
        misses = worst_rookie_misses(con, "v1", 2020, 2020, top_n=10)
        assert misses[0].display_name == "Far"
        assert misses[0].error == pytest.approx(190.0)

    def test_wrong_model_version_is_excluded(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, rookie_season) "
            "VALUES ('p', 'gsis_p', 'P', 'WR', 2020)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('p', 2020, 'WR', 15, 100.0, 6.7)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, predicted_at) VALUES "
            "('p1', 'p', 2020, 'WR', 'other_version', 300.0, current_timestamp)"
        )
        misses = worst_rookie_misses(con, "v1", 2020, 2020, top_n=10)
        assert misses == []
