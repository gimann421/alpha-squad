"""D70 availability features (docs/RB_AVAILABILITY_PREREGISTRATION.md).

Written alongside the pre-registered implementation, before any model was fitted against real
outcomes. Pins the leakage guard and the closed feature list -- the two properties the
pre-registration names explicitly ("structural, not procedural" leakage protection; "committed
as a closed list, no sweep, no post-hoc additions"). In-memory schema + synthetic fixture rows,
matching `test_uncertainty_run.py`'s convention -- this module has nothing to do with real
outcomes, so it does not need real data to verify."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.features.availability import (
    AVAILABILITY_FEATURES,
    GAMES_HISTORY_LOOKBACK_SEASONS,
    build_availability_features,
    validate_no_leakage,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_season(
    con, player_id, season, games_played=15, carries=0.0, receptions=0.0, position="RB"
):
    total_points = games_played * 10.0
    con.execute(
        """
        INSERT INTO player_season_stats
            (player_id, season, position, games_played, total_fantasy_points_ppr,
             ppr_points_per_game, total_carries, total_receptions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            player_id,
            season,
            position,
            games_played,
            total_points,
            total_points / games_played,
            carries,
            receptions,
        ],
    )


def _seed_player(con, player_id, birth_date="1998-05-01"):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, birth_date) VALUES (?, ?, ?)",
        [player_id, player_id, birth_date],
    )


class TestClosedFeatureList:
    def test_exactly_four_features(self):
        """F1-F4, no fifth. Adding one after seeing results is a protocol violation."""
        assert AVAILABILITY_FEATURES == [
            "avail_games_played_history",
            "avail_age",
            "avail_position_cohort_games",
            "avail_workload_per_game",
        ]

    def test_lookback_is_three_seasons(self):
        assert GAMES_HISTORY_LOOKBACK_SEASONS == 3


class TestLeakageGuard:
    """The guard the pre-registration requires: 'a test that requesting a target-season
    feature raises'. `validate_no_leakage` is called at the point a caller assembles a
    training/calibration set, mirroring `projection_calibration.py::fit_arm`."""

    def test_target_season_in_source_raises(self):
        with pytest.raises(ValueError, match="leakage"):
            validate_no_leakage([2020, 2021, 2023], target_season=2023)

    def test_a_season_after_target_raises(self):
        with pytest.raises(ValueError, match="leakage"):
            validate_no_leakage([2020, 2024], target_season=2023)

    def test_the_error_names_the_offending_seasons(self):
        with pytest.raises(ValueError, match=r"\[2023, 2024\]"):
            validate_no_leakage([2020, 2021, 2023, 2024], target_season=2023)

    def test_strictly_earlier_seasons_are_accepted(self):
        validate_no_leakage([2020, 2021, 2022], target_season=2023)  # must not raise

    def test_empty_source_is_accepted(self):
        validate_no_leakage([], target_season=2023)  # must not raise


class TestBuildAvailabilityFeatures:
    def test_returns_exactly_the_closed_feature_columns_plus_keys(self, con):
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2022, games_played=14, carries=200, receptions=20)
        df = build_availability_features(con, "RB", 2015, 2025)
        assert set(df.columns) == {"player_id", "target_season", *AVAILABILITY_FEATURES}

    def test_target_season_is_source_season_plus_one(self, con):
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2022, games_played=14, carries=200, receptions=20)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["player_id"] == "p1"].iloc[0]
        assert row["target_season"] == 2023

    def test_only_the_requested_position_and_range(self, con):
        _seed_player(con, "rb1")
        _seed_player(con, "wr1")
        _seed_season(con, "rb1", 2022, position="RB")
        _seed_season(con, "wr1", 2022, position="WR")
        df = build_availability_features(con, "RB", 2015, 2025)
        assert set(df["player_id"]) == {"rb1"}

    def test_games_history_averages_available_prior_seasons(self, con):
        """F1: mean games played over up to 3 prior seasons (S-1..S-3)."""
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2020, games_played=10)
        _seed_season(con, "p1", 2021, games_played=12)
        _seed_season(con, "p1", 2022, games_played=14)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["target_season"] == 2023].iloc[0]
        assert row["avail_games_played_history"] == pytest.approx((10 + 12 + 14) / 3)

    def test_games_history_ignores_a_fourth_prior_season(self, con):
        """Lookback is exactly 3 seasons -- a 4th-prior season must not enter the average."""
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2019, games_played=1)  # outside the 3-season window for 2023
        _seed_season(con, "p1", 2020, games_played=10)
        _seed_season(con, "p1", 2021, games_played=12)
        _seed_season(con, "p1", 2022, games_played=14)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["target_season"] == 2023].iloc[0]
        assert row["avail_games_played_history"] == pytest.approx((10 + 12 + 14) / 3)

    def test_age_is_computed_from_birth_date_at_target_season_sept_1(self, con):
        """F2, reusing the existing convention from evaluation/dynasty_validation.py."""
        _seed_player(con, "p1", birth_date="2000-01-01")
        _seed_season(con, "p1", 2022)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["target_season"] == 2023].iloc[0]
        assert row["avail_age"] == 23  # 2000-01-01 -> 2023-09-01

    def test_position_cohort_is_a_population_statistic_not_player_specific(self, con):
        """F3: identical for every player at the position in that target season."""
        _seed_player(con, "p1")
        _seed_player(con, "p2")
        _seed_season(con, "p1", 2022, games_played=10)
        _seed_season(con, "p2", 2022, games_played=16)
        df = build_availability_features(con, "RB", 2015, 2025)
        rows = df[df["target_season"] == 2023]
        assert rows["avail_position_cohort_games"].nunique() == 1
        assert rows["avail_position_cohort_games"].iloc[0] == pytest.approx((10 + 16) / 2)

    def test_workload_per_game_uses_prior_season_touches(self, con):
        """F4: (carries + receptions) / games_played, from season S-1."""
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2022, games_played=14, carries=200, receptions=30)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["target_season"] == 2023].iloc[0]
        assert row["avail_workload_per_game"] == pytest.approx((200 + 30) / 14)

    def test_no_prior_season_before_the_start_of_a_players_history_leaks_zero_games(self, con):
        """A rookie's F1 draws only from the one season that exists -- never a fabricated
        zero for the seasons that don't."""
        _seed_player(con, "p1")
        _seed_season(con, "p1", 2022, games_played=10)
        df = build_availability_features(con, "RB", 2015, 2025)
        row = df[df["target_season"] == 2023].iloc[0]
        assert row["avail_games_played_history"] == pytest.approx(10.0)
