"""K/DST projections must never see the season they are projecting (docs/DECISIONS.md D57).

Same adversarial posture as `test_player_week_features_leakage.py`: these try to disprove
leakage-safety rather than confirm the happy path. The DST baseline is the one that needs
watching, because it blends a player's own prior season with a *positional mean* -- and a
positional mean computed over the whole table is exactly the kind of aggregate that
silently carries the target season's outcomes back into its own projection.

All fixtures are synthetic and offline.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.features.kicking_defense import DST_POSITION, KICKER_POSITION
from alpha_squad.models.baselines.kicking_defense import (
    MIN_PROJECTABLE_SEASON,
    MODEL_NAME,
    build_kdst_projections,
    project_defenses,
    project_kickers,
)
from alpha_squad.storage.db import init_db

TARGET_SEASON = 2025


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed(con, player_id, season, position, points):
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 17, ?, ?)",
        [player_id, season, position, points, points / 17],
    )


class TestKickerProjectionLeakage:
    def test_the_target_seasons_own_outcome_does_not_change_the_projection(self, con):
        _seed(con, "k1", TARGET_SEASON - 1, KICKER_POSITION, 150.0)
        _seed(con, "k1", TARGET_SEASON - 2, KICKER_POSITION, 120.0)
        before = project_kickers(con, TARGET_SEASON)

        _seed(con, "k1", TARGET_SEASON, KICKER_POSITION, 9999.0)
        assert project_kickers(con, TARGET_SEASON) == before

    def test_a_future_season_does_not_change_the_projection(self, con):
        _seed(con, "k1", TARGET_SEASON - 1, KICKER_POSITION, 150.0)
        before = project_kickers(con, TARGET_SEASON)

        _seed(con, "k1", TARGET_SEASON + 1, KICKER_POSITION, 9999.0)
        _seed(con, "k1", TARGET_SEASON + 2, KICKER_POSITION, 9999.0)
        assert project_kickers(con, TARGET_SEASON) == before

    def test_a_kicker_with_no_prior_season_is_absent_rather_than_invented(self, con):
        _seed(con, "k_future_only", TARGET_SEASON, KICKER_POSITION, 200.0)
        assert project_kickers(con, TARGET_SEASON) == {}


class TestDefenseProjectionLeakage:
    def test_the_positional_mean_never_reads_the_target_season(self, con):
        """THE one to watch. The DST baseline is mostly a positional mean, so a mean taken
        over the whole table would carry the target season's outcomes into its own
        projection -- invisibly, since the per-player term would look correct."""
        _seed(con, "d1", TARGET_SEASON - 1, DST_POSITION, 100.0)
        before = project_defenses(con, TARGET_SEASON)

        for i in range(10):
            _seed(con, f"d_target_{i}", TARGET_SEASON, DST_POSITION, 9999.0)
        assert project_defenses(con, TARGET_SEASON) == before

    def test_the_positional_mean_never_reads_a_future_season(self, con):
        _seed(con, "d1", TARGET_SEASON - 1, DST_POSITION, 100.0)
        before = project_defenses(con, TARGET_SEASON)

        for i in range(10):
            _seed(con, f"d_future_{i}", TARGET_SEASON + 1, DST_POSITION, 9999.0)
        assert project_defenses(con, TARGET_SEASON) == before

    def test_the_positional_mean_does_read_every_prior_season(self, con):
        """The complement: excluding the target season must not accidentally exclude the
        history the baseline is supposed to use."""
        _seed(con, "d1", TARGET_SEASON - 1, DST_POSITION, 100.0)
        only_one_prior = project_defenses(con, TARGET_SEASON)["d1"]

        _seed(con, "d_old", TARGET_SEASON - 3, DST_POSITION, 0.0)
        assert project_defenses(con, TARGET_SEASON)["d1"] != only_one_prior

    def test_a_kickers_outcomes_do_not_leak_into_the_defense_mean(self, con):
        _seed(con, "d1", TARGET_SEASON - 1, DST_POSITION, 100.0)
        before = project_defenses(con, TARGET_SEASON)

        _seed(con, "k_huge", TARGET_SEASON - 1, KICKER_POSITION, 9999.0)
        assert project_defenses(con, TARGET_SEASON) == before


class TestPersistedProjectionsAreWalkForward:
    def test_each_persisted_season_matches_its_own_walk_forward_value(self, con):
        """Building a range at once must produce exactly what building each season alone
        does -- i.e. no season's projection is contaminated by a later one in the batch."""
        for season in range(2020, 2026):
            _seed(con, "d1", season, DST_POSITION, 100.0 + season)
            _seed(con, "k1", season, KICKER_POSITION, 50.0 + season)

        build_kdst_projections(con, list(range(2022, 2026)))
        persisted = dict(
            con.execute(
                "SELECT season, predicted_points FROM projection_snapshot "
                "WHERE model_name = ? AND player_id = 'd1' ORDER BY season",
                [MODEL_NAME],
            ).fetchall()
        )
        for season, value in persisted.items():
            assert value == pytest.approx(project_defenses(con, season)["d1"])

    def test_a_season_with_no_prior_history_is_skipped_rather_than_invented(self, con):
        _seed(con, "d1", MIN_PROJECTABLE_SEASON, DST_POSITION, 100.0)
        assert build_kdst_projections(con, [MIN_PROJECTABLE_SEASON - 1]) == 0
