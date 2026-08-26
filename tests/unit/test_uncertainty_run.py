"""Walk-forward discipline test for the uncertainty pipeline: calibration must use a season
the point model never trained on, and predictions for the target season must never have
been available to either training or calibration."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.models.established.season_level import load_season_level_data
from alpha_squad.models.persistence import load_regressor
from alpha_squad.models.uncertainty.run import (
    ARTIFACT_MODEL_NAME,
    MIN_CALIB_ROWS,
    MIN_TRAIN_ROWS,
    MODEL_VERSION,
    run_uncertainty,
    score_with_persisted_model,
)
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


class TestPersistedModelInference:
    """The audit's P1 gap: no model was ever saved to disk, so every prediction required a
    full retrain. These prove the persisted-inference path actually reproduces what training
    produced -- a caller cannot tell the two apart from the output."""

    def _seed(self, con):
        for season in range(2015, 2025):
            for i in range(40):
                pts = 30.0 + (i % 7) * 5 + season * 0.1
                _seed_season(con, f"p{i}", season, pts, position="WR")

    def test_persist_true_writes_a_loadable_artifact_and_calibration_residuals(
        self, con, tmp_path, monkeypatch
    ):
        from alpha_squad.config.settings import get_settings

        monkeypatch.setattr(get_settings(), "models_dir", tmp_path / "models")
        self._seed(con)

        report = run_uncertainty(con, 2024, 2024, min_train_season=2015, persist=True)
        assert report.predictions_written > 0

        row = con.execute(
            "SELECT artifact_path, calibration_residuals_json FROM model_registry "
            "WHERE model_name = ? AND position = 'WR' AND version = ?",
            [ARTIFACT_MODEL_NAME, MODEL_VERSION],
        ).fetchone()
        assert row is not None
        artifact_path, residuals_json = row
        assert artifact_path is not None and (tmp_path / "models").as_posix() in artifact_path
        assert residuals_json is not None

        # Loadable, not just a path string that happens to be recorded.
        model = load_regressor(ARTIFACT_MODEL_NAME, "WR", MODEL_VERSION)
        assert model is not None

    def test_inference_only_scoring_exactly_reproduces_training_time_predictions(
        self, con, tmp_path, monkeypatch
    ):
        from alpha_squad.config.settings import get_settings

        monkeypatch.setattr(get_settings(), "models_dir", tmp_path / "models")
        self._seed(con)

        run_uncertainty(con, 2024, 2024, min_train_season=2015, persist=True)

        trained = con.execute(
            "SELECT player_id, point_prediction, p10, p90 FROM uncertainty_predictions "
            "WHERE season = 2024 AND position = 'WR' ORDER BY player_id"
        ).fetchall()
        assert trained

        # Rebuild the exact same feature rows a fresh call would have (no .fit() involved
        # anywhere below this line) and score them purely by loading the saved artifact.
        all_data = load_season_level_data(con, "WR", 2015, 2024)
        feature_rows = all_data[all_data["target_season"] == 2024]

        scored = score_with_persisted_model(con, "WR", 2024, feature_rows, store=False)

        for player_id, point_pred, p10, p90 in trained:
            assert player_id in scored
            assert scored[player_id]["point_prediction"] == pytest.approx(point_pred, abs=1e-6)
            assert scored[player_id]["p10"] == pytest.approx(p10, abs=1e-6)
            assert scored[player_id]["p90"] == pytest.approx(p90, abs=1e-6)

    def test_scoring_without_a_persisted_artifact_fails_loudly_not_silently(
        self, con, tmp_path, monkeypatch
    ):
        from alpha_squad.config.settings import get_settings

        monkeypatch.setattr(get_settings(), "models_dir", tmp_path / "models")
        self._seed(con)
        # Never called run_uncertainty(persist=True) -- no artifact exists for this DB/version.
        all_data = load_season_level_data(con, "WR", 2015, 2024)
        feature_rows = all_data[all_data["target_season"] == 2024]

        with pytest.raises(FileNotFoundError):
            score_with_persisted_model(con, "WR", 2024, feature_rows, store=False)
