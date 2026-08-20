"""Walk-forward discipline test for the uncertainty pipeline: calibration must use a season
the point model never trained on, and predictions for the target season must never have
been available to either training or calibration."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.models.uncertainty.run import MIN_CALIB_ROWS, MIN_TRAIN_ROWS, run_uncertainty
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_season(con, player_id, season, total_points, position="WR"):
    con.execute(
        """
        INSERT INTO player_season_stats
            (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game)
        VALUES (?, ?, ?, 15, ?, ?)
        """,
        [player_id, season, position, total_points, total_points / 15],
    )


def test_skips_when_insufficient_data_rather_than_producing_a_prediction(con):
    # Only a handful of rows -- nowhere near MIN_TRAIN_ROWS/MIN_CALIB_ROWS.
    for i in range(5):
        _seed_season(con, f"p{i}", 2022, 50.0 + i, position="WR")
        _seed_season(con, f"p{i}", 2023, 55.0 + i, position="WR")

    report = run_uncertainty(con, 2024, 2024, min_train_season=2015)
    assert report.predictions_written == 0
    assert report.skipped, "should report why every position/season was skipped"

    n_predictions = con.execute("SELECT count(*) FROM uncertainty_predictions").fetchone()[0]
    assert n_predictions == 0


def test_calibration_season_is_recorded_and_strictly_before_target(con):
    """With enough synthetic data to actually run, verify the stored calibration_season is
    target_season - 1, never the target season itself or later. Uses the *same* player_ids
    across every season, since load_season_level_data joins consecutive-season rows for the
    same player -- distinct ids per season would never join and the run would (correctly)
    skip everything for lack of data, which would defeat the point of this test."""
    for season in range(2015, 2025):
        for i in range(40):
            pts = 30.0 + (i % 7) * 5 + season * 0.1
            _seed_season(con, f"p{i}", season, pts, position="WR")

    report = run_uncertainty(con, 2024, 2024, min_train_season=2015)
    assert report.predictions_written > 0, (
        f"expected predictions with this much synthetic data; skipped={report.skipped}"
    )

    rows = con.execute(
        "SELECT DISTINCT season, calibration_season FROM uncertainty_predictions"
    ).fetchall()
    for season, calib_season in rows:
        assert calib_season == season - 1

    # sanity: constants are what the docstrings claim
    assert MIN_TRAIN_ROWS > 0
    assert MIN_CALIB_ROWS > 0
