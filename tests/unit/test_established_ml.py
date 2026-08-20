"""Unit tests for established-player ML's walk-forward discipline — the models themselves
are standard sklearn/CatBoost/XGBoost, so the thing worth testing directly is that training
data never includes the target season (the same leakage discipline as M3/M4), using small
synthetic fixtures rather than real data."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from alpha_squad.models.established.data import load_position_week_data
from alpha_squad.models.established.features import FULL_FEATURES
from alpha_squad.models.established.season_level import load_season_level_data
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_week_feature_row(con, player_id, season, week, position, **overrides):
    values = {col: 0.0 for col in FULL_FEATURES}
    values.update(overrides)
    con.execute(
        f"""
        INSERT INTO player_week_features
            (player_id, season, week, game_date, position, {", ".join(FULL_FEATURES)},
             target_fantasy_points_ppr, feature_version, built_at)
        VALUES (?, ?, ?, ?, ?, {", ".join("?" for _ in FULL_FEATURES)}, ?, 'test', ?)
        """,
        [
            player_id,
            season,
            week,
            date(season, 9, 1),
            position,
            *[values[c] for c in FULL_FEATURES],
            values.get("target_fantasy_points_ppr", 10.0),
            date(season, 9, 1),
        ],
    )


def _seed_season(con, player_id, season, total_points, position="WR"):
    con.execute(
        """
        INSERT INTO player_season_stats
            (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game)
        VALUES (?, ?, ?, 15, ?, ?)
        """,
        [player_id, season, position, total_points, total_points / 15],
    )


class TestWeeklyDataLoaderWalkForward:
    def test_load_position_week_data_can_be_scoped_to_prior_seasons_only(self, con):
        _seed_week_feature_row(con, "p1", 2023, 1, "WR")
        _seed_week_feature_row(con, "p1", 2024, 1, "WR")
        train = load_position_week_data(con, "WR", 2015, 2023)
        assert set(train["season"]) == {2023}

    def test_missing_lag_values_are_imputed_to_zero_not_dropped(self, con):
        con.execute(
            f"""
            INSERT INTO player_week_features
                (player_id, season, week, game_date, position, {", ".join(FULL_FEATURES)},
                 target_fantasy_points_ppr, feature_version, built_at)
            VALUES ('p1', 2023, 1, '2023-09-01', 'WR', {", ".join("NULL" for _ in FULL_FEATURES)}, 5.0, 'test', '2023-09-01')
            """
        )
        df = load_position_week_data(con, "WR", 2015, 2023)
        assert len(df) == 1
        assert (df[FULL_FEATURES].fillna(-999) != -999).all().all(), (
            "NaNs should have been imputed to 0.0"
        )


class TestSeasonLevelWalkForward:
    def test_training_rows_never_include_the_target_season_itself(self, con):
        for season, pts in [
            (2020, 100.0),
            (2021, 110.0),
            (2022, 120.0),
            (2023, 130.0),
            (2024, 999.0),
        ]:
            _seed_season(con, "p1", season, pts, position="WR")

        df = load_season_level_data(con, "WR", 2015, 2024)
        # target_season = prior_season + 1, so a row with target_season==2024 uses season
        # 2023 as its "prior" features — the 999.0 poison value for season 2024 must only
        # ever appear as somebody's *target*, never as a feature input for an earlier row.
        assert 999.0 not in df["prior_weighted_total"].to_numpy()
        assert 999.0 not in df["prior_ppg"].to_numpy()

    def test_missing_preseason_ecr_is_imputed_to_a_deliberately_bad_rank(self, con):
        _seed_season(con, "p1", 2022, 100.0, position="WR")
        _seed_season(con, "p1", 2023, 110.0, position="WR")
        df = load_season_level_data(con, "WR", 2015, 2023)
        assert (df["preseason_ecr_rank"] == 999.0).all()
