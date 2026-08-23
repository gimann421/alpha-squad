"""Unit tests for rookie modeling's walk-forward-by-draft-class discipline and the
historical comps nearest-neighbor logic, against synthetic fixtures."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.features.rookie import build_rookie_features
from alpha_squad.models.rookie.comps import find_historical_comps
from alpha_squad.models.rookie.data import load_rookie_class_data
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_rookie(
    con, player_id, draft_class, position, points, breakout, round_=3, pick=80, forty=4.6
):
    con.execute(
        """
        INSERT INTO rookie_features
            (player_id, draft_class, position, draft_round, draft_pick, forty, breakout_top24,
             rookie_year_ppr_points, rookie_year_games, built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 15, current_timestamp)
        """,
        [player_id, draft_class, position, round_, pick, forty, breakout, points],
    )


class TestWalkForwardByDraftClass:
    def test_load_rookie_class_data_scopes_to_the_requested_class_range(self, con):
        _seed_rookie(con, "p1", 2022, "WR", 100.0, False)
        _seed_rookie(con, "p2", 2023, "WR", 150.0, True)
        df = load_rookie_class_data(con, "WR", 2015, 2022)
        assert set(df["draft_class"]) == {2022}

    def test_undrafted_players_get_a_deliberately_bad_capital_not_zero(self, con):
        con.execute(
            """
            INSERT INTO rookie_features
                (player_id, draft_class, position, draft_round, draft_pick, breakout_top24,
                 rookie_year_ppr_points, built_at)
            VALUES ('udfa1', 2023, 'RB', NULL, NULL, false, 20.0, current_timestamp)
            """
        )
        df = load_rookie_class_data(con, "RB", 2015, 2023)
        row = df[df["player_id"] == "udfa1"].iloc[0]
        assert row["draft_round"] > 7  # worse than any real drafted round
        assert row["draft_pick"] > 260  # worse than any real drafted pick


class TestHistoricalComps:
    def test_comps_never_include_players_from_the_same_or_later_class(self, con):
        _seed_rookie(con, "early1", 2020, "RB", 100.0, False)
        _seed_rookie(con, "early2", 2021, "RB", 110.0, False)
        _seed_rookie(con, "target", 2023, "RB", 200.0, True)
        _seed_rookie(con, "future1", 2024, "RB", 50.0, False)  # must never appear as a comp

        comps = find_historical_comps(con, "target", 2023, "RB", k=5)
        classes = {c["draft_class"] for c in comps}
        assert all(c < 2023 for c in classes)
        assert "future1" not in {c["player_id"] for c in comps}

    def test_most_similar_player_is_ranked_first(self, con):
        _seed_rookie(con, "near", 2020, "WR", 100.0, False, round_=3, pick=80, forty=4.55)
        _seed_rookie(con, "far", 2021, "WR", 100.0, False, round_=7, pick=250, forty=4.9)
        _seed_rookie(con, "target", 2023, "WR", 100.0, False, round_=3, pick=82, forty=4.56)

        comps = find_historical_comps(con, "target", 2023, "WR", k=2)
        assert comps[0]["player_id"] == "near"
        assert comps[0]["similarity_distance"] < comps[1]["similarity_distance"]

    def test_empty_pool_returns_no_comps_rather_than_erroring(self, con):
        _seed_rookie(con, "only_class", 2023, "TE", 50.0, False)
        comps = find_historical_comps(con, "only_class", 2023, "TE", k=5)
        assert comps == []


def test_build_rookie_features_marks_breakout_correctly_against_real_position_ranks(con):
    """Integration-flavored unit test: seed a realistic player_season_stats pool and verify
    build_rookie_features derives breakout_top24 from actual within-position rank, not from
    a hardcoded points threshold."""
    con.execute(
        "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, draft_pick, rookie_season) VALUES ('r1', 'g1', 'WR', 'KC', 1, 5, 2023)"
    )
    for i in range(30):
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game) "
            "VALUES (?, 2023, 'WR', 15, ?, ?)",
            [f"other{i}", 300.0 - i * 5, (300.0 - i * 5) / 15],
        )
    # r1 finishes 5th overall among WRs (inserted at rank ~5 by score) -> should be top24.
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game) "
        "VALUES ('r1', 2023, 'WR', 15, 280.0, 18.67)"
    )
    build_rookie_features(con)
    row = con.execute("SELECT breakout_top24 FROM rookie_features WHERE player_id='r1'").fetchone()
    assert row == (True,)


class TestCollegeUsageJoin:
    """docs/DECISIONS.md D38: college_usage (CFBD, espn_id-bridged) joined into
    rookie_features for the rookie's *final college season only* (rookie_season - 1)."""

    def test_college_usage_for_the_final_college_season_is_joined_in(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO college_usage (player_id, season, usage_overall, usage_pass, usage_rush) "
            "VALUES ('r1', 2023, 0.624, 0.915, 0.222)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall, college_usage_pass, college_usage_rush "
            "FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (0.624, 0.915, 0.222)

    def test_the_rookies_own_nfl_season_year_is_never_used_as_the_join_key(self, con):
        """A college_usage row that happens to share the rookie's *NFL* season number (not
        their final *college* season, rookie_season - 1) must not leak in -- that would be a
        look-ahead the same way using the rookie's own NFL-season team stats would be."""
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO college_usage (player_id, season, usage_overall, usage_pass, usage_rush) "
            "VALUES ('r1', 2024, 0.999, 0.999, 0.999)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (None,)

    def test_missing_college_usage_leaves_the_columns_null_not_erroring(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall, college_usage_pass, college_usage_rush "
            "FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (None, None, None)
