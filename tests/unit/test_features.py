"""Regression coverage for docs/DECISIONS.md D28: `build_player_week_stats` and
`build_team_week_stats` must exclude postseason games. Found via M13's team-season simulation
(a real player's simulated output was inflated by his own real Super Bowl outlier game being
pooled into a "per-game" rate and extrapolated across a full season) -- both builders' `games`
join now requires `game_type = 'REG'`. These tests seed a fake local snapshot (a small CSV, not
a real nflverse fetch) so they run offline, exercising the real builder SQL rather than
re-asserting a property of hand-seeded data."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.player import build_player_week_stats
from alpha_squad.features.team import build_team_week_stats
from alpha_squad.sources.base import RawSnapshot
from alpha_squad.storage.db import init_db
from alpha_squad.storage.snapshots import record_snapshot

SEASON = 2024
REG_GAME = "2024_01_TST_OPP"
POST_GAME = "2024_20_TST_OPP"
GSIS_ID = "00-9999002"
PLAYER_ID = "asq_test_reg_post"


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, ?)", [PLAYER_ID, GSIS_ID]
    )
    connection.execute(
        """
        INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team)
        VALUES
            (?, ?, 1, 'REG', '2024-09-08', 'TST', 'OPP'),
            (?, ?, 20, 'POST', '2025-01-19', 'TST', 'OPP')
        """,
        [REG_GAME, SEASON, POST_GAME, SEASON],
    )
    yield connection
    connection.close()


def _register_csv_snapshot(
    con, tmp_path, filename: str, dataset: str, header: str, rows: list[str]
) -> None:
    path = tmp_path / filename
    path.write_text(header + "\n" + "\n".join(rows) + "\n")
    snap = RawSnapshot(
        source="nflverse",
        dataset=dataset,
        captured_at=datetime.now(UTC),
        url="file://test-fixture",
        local_path=path,
        sha256="test",
        rows=len(rows),
        columns=None,
        params=(("season", str(SEASON)),),
    )
    record_snapshot(con, snap)


class TestPlayerWeekStatsExcludesPostseason:
    def test_postseason_game_never_reaches_player_week_stats(self, con, tmp_path):
        header = (
            "player_id,season,week,game_id,team,position,targets,carries,receptions,"
            "target_share,air_yards_share,passing_yards,passing_tds,passing_interceptions,"
            "rushing_yards,rushing_tds,receiving_yards,receiving_tds,fantasy_points,"
            "fantasy_points_ppr,player_display_name"
        )
        rows = [
            f"{GSIS_ID},{SEASON},1,{REG_GAME},TST,WR,8,0,6,0.2,0.15,0,0,0,0,0,80,1,14.0,14.0,Test Player",
            f"{GSIS_ID},{SEASON},20,{POST_GAME},TST,WR,20,0,18,0.5,0.4,0,0,0,0,0,250,3,60.0,60.0,Test Player",
        ]
        _register_csv_snapshot(
            con, tmp_path, "stats_player_week.csv", "stats_player_week", header, rows
        )

        settings = Settings()
        inserted = build_player_week_stats(con, settings, [SEASON])

        assert inserted == 1
        game_ids = {
            r[0]
            for r in con.execute(
                "SELECT game_id FROM player_week_stats WHERE player_id = ?", [PLAYER_ID]
            ).fetchall()
        }
        assert game_ids == {REG_GAME}, (
            "a postseason game's stats must never reach player_week_stats (docs/DECISIONS.md D28)"
        )

    def test_a_player_who_only_appears_in_postseason_data_produces_no_rows_and_no_exception(
        self, con, tmp_path
    ):
        header = (
            "player_id,season,week,game_id,team,position,targets,carries,receptions,"
            "target_share,air_yards_share,passing_yards,passing_tds,passing_interceptions,"
            "rushing_yards,rushing_tds,receiving_yards,receiving_tds,fantasy_points,"
            "fantasy_points_ppr,player_display_name"
        )
        rows = [
            f"00-8888999,{SEASON},20,{POST_GAME},TST,WR,3,0,2,0.1,0.05,0,0,0,0,0,20,0,4.0,4.0,Unmapped Guy",
        ]
        _register_csv_snapshot(
            con, tmp_path, "stats_player_week.csv", "stats_player_week", header, rows
        )

        settings = Settings()
        inserted = build_player_week_stats(con, settings, [SEASON])

        assert inserted == 0
        exceptions = con.execute(
            "SELECT count(*) FROM identity_exceptions WHERE subject LIKE '%00-8888999%'"
        ).fetchone()[0]
        assert exceptions == 0, (
            "a player who only appears in postseason data (which is entirely discarded) "
            "should not generate a spurious identity exception"
        )


class TestTeamWeekStatsExcludesPostseason:
    def test_postseason_game_never_reaches_team_week_stats(self, con, tmp_path):
        header = "team,season,week,game_id,attempts,carries,passing_epa,rushing_epa"
        rows = [
            f"TST,{SEASON},1,{REG_GAME},30,25,5.0,2.0",
            f"TST,{SEASON},20,{POST_GAME},45,30,15.0,8.0",
        ]
        _register_csv_snapshot(
            con, tmp_path, "stats_team_week.csv", "stats_team_week", header, rows
        )

        settings = Settings()
        inserted = build_team_week_stats(con, settings, [SEASON])

        assert inserted == 1
        game_ids = {
            r[0]
            for r in con.execute(
                "SELECT game_id FROM team_week_stats WHERE team = 'TST'"
            ).fetchall()
        }
        assert game_ids == {REG_GAME}, (
            "a postseason game's team stats must never reach team_week_stats "
            "(docs/DECISIONS.md D28)"
        )
