"""Team-environment signal: normalizes nflverse `stats_team_week` into `team_week_stats`,
then computes leakage-safe trailing features into `team_week_features` using the same
window-frame technique as the player panel (features/panel.py) — a row's features reflect
only that team's strictly-prior games. Feeds the M5 team-environment model and gets joined
onto `player_week_features` by (team, season, week).

Regular-season games only (games.game_type = 'REG'): postseason games are excluded so a
trailing "last 3 games" window never silently pulls in a playoff game as one of a team's
last 3 games of the season, and so season-level aggregates stay comparable across teams
regardless of playoff participation."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot

_LAG3 = "ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING"


def build_team_week_stats(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> int:
    total = 0
    for season in seasons:
        snap = require_snapshot(con, "nflverse", "stats_team_week", season=season)
        src = reader_expr(snap["local_path"])
        rows = con.execute(
            f"""
            INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, pass_rate, passing_epa, rushing_epa, source_snapshot_id)
            SELECT
                t.team, t.season, t.week, t.game_id, g.game_date,
                t.attempts + t.carries AS plays,
                CASE WHEN (t.attempts + t.carries) > 0 THEN t.attempts / (t.attempts + t.carries) END AS pass_rate,
                t.passing_epa, t.rushing_epa, ?
            FROM {src} t
            JOIN games g ON g.game_id = t.game_id AND g.game_type = 'REG'
            ON CONFLICT (team, season, week) DO UPDATE SET
                plays = excluded.plays,
                pass_rate = excluded.pass_rate,
                passing_epa = excluded.passing_epa,
                rushing_epa = excluded.rushing_epa,
                source_snapshot_id = excluded.source_snapshot_id
            RETURNING team
            """,
            [snap["snapshot_id"]],
        ).fetchall()
        total += len(rows)
    return total


def build_team_week_features(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _team_panel AS
        SELECT
            team, season, week, game_date,
            AVG(plays) OVER (PARTITION BY team ORDER BY game_date, season, week {_LAG3}) AS team_plays_avg_last3,
            AVG(pass_rate) OVER (PARTITION BY team ORDER BY game_date, season, week {_LAG3}) AS team_pass_rate_avg_last3,
            AVG((passing_epa + rushing_epa)) OVER (
                PARTITION BY team ORDER BY game_date, season, week {_LAG3}
            ) AS team_epa_avg_last3
        FROM team_week_stats
        """
    )
    rows = con.execute(
        """
        INSERT INTO team_week_features (team, season, week, game_date, team_plays_avg_last3, team_pass_rate_avg_last3, team_epa_avg_last3)
        SELECT team, season, week, game_date, team_plays_avg_last3, team_pass_rate_avg_last3, team_epa_avg_last3
        FROM _team_panel
        ON CONFLICT (team, season, week) DO UPDATE SET
            game_date = excluded.game_date,
            team_plays_avg_last3 = excluded.team_plays_avg_last3,
            team_pass_rate_avg_last3 = excluded.team_pass_rate_avg_last3,
            team_epa_avg_last3 = excluded.team_epa_avg_last3
        RETURNING team
        """
    ).fetchall()
    return len(rows)


def attach_team_features_to_player_panel(con: duckdb.DuckDBPyConnection) -> int:
    """Backfills player_week_features.team_* columns by joining team_week_features on
    (team, season, week) — the player's own team for that game, from player_week_stats."""
    rows = con.execute(
        """
        UPDATE player_week_features f
        SET
            team = s.team,
            team_plays_avg_last3 = tf.team_plays_avg_last3,
            team_pass_rate_avg_last3 = tf.team_pass_rate_avg_last3,
            team_epa_avg_last3 = tf.team_epa_avg_last3
        FROM player_week_stats s
        LEFT JOIN team_week_features tf
          ON tf.team = s.team AND tf.season = s.season AND tf.week = s.week
        WHERE s.player_id = f.player_id AND s.season = f.season AND s.week = f.week
        RETURNING f.player_id
        """
    ).fetchall()
    return len(rows)
