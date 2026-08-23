"""Aggregates `player_week_stats` (M3) into `player_season_stats` — the grain baselines
operate on (PRODUCT_SPEC.md's "previous-year fantasy points" / "weighted 2-year baseline"
are inherently season-level comparisons). Built entirely from already-played games, so this
carries no leakage risk on its own; leakage is a property of *which seasons* a baseline is
allowed to read (enforced in models/baselines/, not here)."""

from __future__ import annotations

import duckdb


def build_player_season_stats(con: duckdb.DuckDBPyConnection, seasons: list[int]) -> int:
    rows = con.execute(
        """
        INSERT INTO player_season_stats (
            player_id, season, position, games_played, total_fantasy_points_ppr,
            ppr_points_per_game, total_targets, total_carries, total_receptions
        )
        SELECT
            player_id, season,
            mode(position) AS position,
            count(*) AS games_played,
            sum(fantasy_points_ppr) AS total_fantasy_points_ppr,
            sum(fantasy_points_ppr) / count(*) AS ppr_points_per_game,
            sum(targets) AS total_targets,
            sum(carries) AS total_carries,
            sum(receptions) AS total_receptions
        FROM player_week_stats
        WHERE season = ANY(?)
        GROUP BY player_id, season
        ON CONFLICT (player_id, season) DO UPDATE SET
            position = excluded.position,
            games_played = excluded.games_played,
            total_fantasy_points_ppr = excluded.total_fantasy_points_ppr,
            ppr_points_per_game = excluded.ppr_points_per_game,
            total_targets = excluded.total_targets,
            total_carries = excluded.total_carries,
            total_receptions = excluded.total_receptions
        RETURNING player_id
        """,
        [seasons],
    ).fetchall()
    return len(rows)
