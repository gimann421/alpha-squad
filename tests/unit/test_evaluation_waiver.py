"""Unit tests for the waiver-tier value-discovery proxy (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.waiver_evaluation import (
    ROSTERED_ECR_THRESHOLD,
    TOP_K,
    build_waiver_tier_evaluation,
)
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_player(
    con,
    player_id,
    season,
    position,
    projection,
    actual_points,
    ecr_rank=None,
    prior_year_points=None,
):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season, predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.1, 0.2, 0.7, ?, current_timestamp)
        """,
        [
            f"pred_{player_id}",
            player_id,
            season,
            position,
            UNCERTAINTY_MODEL_VERSION,
            projection,
            season - 1,
        ],
    )
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 15, ?, ?)",
        [player_id, season, position, actual_points, actual_points / 15],
    )
    if ecr_rank is not None:
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES (?, ?, 'ro', ?, ?, 'redraft-overall')",
            [player_id, f"{season}-08-01", position, ecr_rank],
        )
    if prior_year_points is not None:
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 15, ?, ?)",
            [player_id, season - 1, position, prior_year_points, prior_year_points / 15],
        )


class TestWaiverTierPool:
    def test_rostered_player_is_excluded_from_the_waiver_pool(self, con):
        # Rostered: real preseason ECR rank well inside the threshold.
        _seed_player(con, "star", 2023, "WR", projection=250.0, actual_points=250.0, ecr_rank=5.0)
        # Waiver-tier: no consensus rank at all.
        for i in range(TOP_K):
            _seed_player(
                con, f"sleeper_{i}", 2023, "WR", projection=50.0 + i, actual_points=50.0 + i
            )

        results = build_waiver_tier_evaluation(con, 2023, 2023)
        assert len(results) == 1
        assert results[0].pool_size == TOP_K  # "star" excluded, only the unranked sleepers remain

    def test_player_beyond_rostered_threshold_is_included(self, con):
        _seed_player(
            con,
            "deep_bench",
            2023,
            "WR",
            projection=50.0,
            actual_points=50.0,
            ecr_rank=ROSTERED_ECR_THRESHOLD + 1.0,
        )
        for i in range(TOP_K - 1):
            _seed_player(con, f"other_{i}", 2023, "WR", projection=40.0, actual_points=40.0)
        results = build_waiver_tier_evaluation(con, 2023, 2023)
        assert results[0].pool_size == TOP_K

    def test_seasons_below_top_k_pool_size_are_skipped(self, con):
        for i in range(TOP_K - 1):  # one short of TOP_K
            _seed_player(con, f"few_{i}", 2023, "WR", projection=40.0, actual_points=40.0)
        results = build_waiver_tier_evaluation(con, 2023, 2023)
        assert results == []

    def test_alpha_top_k_selects_highest_projected_points_within_the_pool(self, con):
        for i in range(TOP_K + 5):
            # Alpha's projection strictly increasing with i; real outcome deliberately
            # *inverted* so the test can tell whether Alpha's own ranking (not actual
            # outcome) drove the top-K selection.
            _seed_player(
                con, f"p_{i}", 2023, "WR", projection=float(i), actual_points=float(100 - i)
            )
        results = build_waiver_tier_evaluation(con, 2023, 2023)
        # Alpha picks the TOP_K highest-projection players (i = 5..24), whose real points are
        # the *lowest* in the pool (100-i for high i) -- so alpha's top-K mean must be below
        # the naive pool average given this deliberately adversarial setup.
        assert results[0].alpha_top_k_mean_points < results[0].pool_mean_points
