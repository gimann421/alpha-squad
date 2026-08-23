"""Real final team scores per (team, season, week), derived from nflverse `pbp`'s running
score columns (`total_home_score`/`total_away_score`, max per game_id -- the final value of
a running total is the final score) and unpivoted into one row per team. This is not folded
into `features/team.py`'s `team_week_stats` pipeline (M5's already-validated team-environment
model input) -- a separate, self-contained table this module owns, so nothing already built
is touched by adding it.

Regular-season games only (`season_type = 'REG'`), matching `team_week_stats`/
`player_week_stats` -- see features/team.py's docstring for why postseason games are
excluded."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot


def build_team_week_points(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> int:
    total = 0
    for season in seasons:
        snap = require_snapshot(con, "nflverse", "pbp", season=season)
        src = reader_expr(snap["local_path"])
        rows = con.execute(
            f"""
            WITH final_scores AS (
                SELECT game_id, season, week, home_team, away_team,
                       max(total_home_score) AS home_points, max(total_away_score) AS away_points
                FROM {src}
                WHERE game_id IS NOT NULL AND season_type = 'REG'
                GROUP BY 1, 2, 3, 4, 5
            ),
            unpivoted AS (
                SELECT game_id, season, week, home_team AS team, home_points AS points, away_points AS opponent_points
                FROM final_scores
                UNION ALL
                SELECT game_id, season, week, away_team AS team, away_points AS points, home_points AS opponent_points
                FROM final_scores
            )
            INSERT INTO team_week_points (team, season, week, game_id, points, opponent_points, source_snapshot_id)
            SELECT team, season, week, game_id, points, opponent_points, ?
            FROM unpivoted
            WHERE points IS NOT NULL
            ON CONFLICT (team, season, week) DO UPDATE SET
                game_id = excluded.game_id, points = excluded.points,
                opponent_points = excluded.opponent_points, source_snapshot_id = excluded.source_snapshot_id
            RETURNING team
            """,
            [snap["snapshot_id"]],
        ).fetchall()
        total += len(rows)
    return total
