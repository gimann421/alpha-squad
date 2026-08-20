"""Builds the `games` lookup table — the anchor for every as-of/leakage check downstream.

nflverse publishes no separate schedules/games release tag (verified: `schedules` and
`games` both 404 under the standard release-asset path). Every game's real calendar date is
present in `pbp` (`game_id`, `game_date`, `season`, `week`, `season_type`), so `games` is
derived from there — reading only the handful of game-identifying columns, not the full
372-column play-by-play detail, which keeps this cheap even though pbp files are large."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot


def build_games_table(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> int:
    total_inserted = 0
    for season in seasons:
        snap = require_snapshot(con, "nflverse", "pbp", season=season)
        src = reader_expr(snap["local_path"])
        rows = con.execute(
            f"""
            INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team, source_snapshot_id)
            SELECT DISTINCT game_id, season, week, season_type, game_date, home_team, away_team, ?
            FROM {src}
            WHERE game_id IS NOT NULL AND game_date IS NOT NULL
            ON CONFLICT (game_id) DO NOTHING
            RETURNING game_id
            """,
            [snap["snapshot_id"]],
        ).fetchall()
        total_inserted += len(rows)
    return total_inserted
