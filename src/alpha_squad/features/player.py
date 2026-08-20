"""Normalizes weekly player stats (nflverse `stats_player_week` + `snap_counts`) into
`player_week_stats`, identity-joined once here rather than re-joined ad hoc by every feature
query. `stats_player_week.player_id` is already gsis_id format (verified against real data)
so it joins directly to the `players` spine; `snap_counts` carries only `pfr_player_id`, so
it goes through `player_id_map` like every other non-gsis source (same pattern as the
draft_picks/combine college bridge in identity/crosswalk.py)."""

from __future__ import annotations

import contextlib

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot
from alpha_squad.identity.exceptions import record_exception


def build_player_week_stats(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> int:
    total_inserted = 0
    for season in seasons:
        stats_snap = require_snapshot(con, "nflverse", "stats_player_week", season=season)
        stats_src = reader_expr(stats_snap["local_path"])

        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE _stats_matched AS
            SELECT
                p.player_id, s.season, s.week, s.game_id, g.game_date, s.team, s.position,
                s.targets, s.carries, s.receptions, s.target_share, s.air_yards_share,
                s.passing_yards, s.passing_tds, s.passing_interceptions,
                s.rushing_yards, s.rushing_tds, s.receiving_yards, s.receiving_tds,
                s.fantasy_points, s.fantasy_points_ppr
            FROM {stats_src} s
            JOIN games g ON g.game_id = s.game_id
            LEFT JOIN players p ON p.gsis_id = s.player_id
            """
        )

        # player_id in _stats_matched is the *canonical* id post-join (NULL when unmatched);
        # the raw source gsis_id isn't retained there once unmatched, so re-derive unmatched
        # rows directly against the source for an accurate exception record.
        unmatched = con.execute(
            f"""
            SELECT DISTINCT s.player_id, s.player_display_name
            FROM {stats_src} s
            LEFT JOIN players p ON p.gsis_id = s.player_id
            WHERE p.player_id IS NULL
            """
        ).fetchall()
        for gsis_id, display_name in unmatched:
            record_exception(
                con,
                exception_type="unmapped_player_week_stat",
                subject=f"stats_player_week:{gsis_id}",
                detail={
                    "gsis_id": gsis_id,
                    "display_name": display_name,
                    "season": season,
                    "reason": "gsis_id not present in the canonical players spine",
                },
            )

        snap_snap = None
        with contextlib.suppress(RuntimeError):
            # snap_counts may not be ingested for every season; snap_pct stays NULL if so.
            snap_snap = require_snapshot(con, "nflverse", "snap_counts", season=season)

        if snap_snap is not None:
            snap_src = reader_expr(snap_snap["local_path"])
            con.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE _snap_matched AS
                SELECT m.player_id, sc.game_id, sc.offense_pct
                FROM {snap_src} sc
                JOIN player_id_map m ON m.id_type = 'pfr_id' AND m.id_value = sc.pfr_player_id
                """
            )
            con.execute(
                """
                CREATE OR REPLACE TEMP TABLE _stats_with_snaps AS
                SELECT sm.*, sn.offense_pct AS offense_snap_pct
                FROM _stats_matched sm
                LEFT JOIN _snap_matched sn ON sn.player_id = sm.player_id AND sn.game_id = sm.game_id
                """
            )
            final_table = "_stats_with_snaps"
        else:
            con.execute(
                "CREATE OR REPLACE TEMP TABLE _stats_with_snaps AS "
                "SELECT *, NULL::DOUBLE AS offense_snap_pct FROM _stats_matched"
            )
            final_table = "_stats_with_snaps"

        rows = con.execute(
            f"""
            INSERT INTO player_week_stats (
                player_id, season, week, game_id, game_date, team, position,
                targets, carries, receptions, target_share, air_yards_share,
                passing_yards, passing_tds, passing_interceptions,
                rushing_yards, rushing_tds, receiving_yards, receiving_tds,
                offense_snap_pct, fantasy_points, fantasy_points_ppr, source_snapshot_id
            )
            SELECT
                player_id, season, week, game_id, game_date, team, position,
                targets, carries, receptions, target_share, air_yards_share,
                passing_yards, passing_tds, passing_interceptions,
                rushing_yards, rushing_tds, receiving_yards, receiving_tds,
                offense_snap_pct, fantasy_points, fantasy_points_ppr, ?
            FROM {final_table}
            WHERE player_id IS NOT NULL
            ON CONFLICT (player_id, season, week) DO UPDATE SET
                targets = excluded.targets,
                carries = excluded.carries,
                receptions = excluded.receptions,
                target_share = excluded.target_share,
                air_yards_share = excluded.air_yards_share,
                passing_yards = excluded.passing_yards,
                passing_tds = excluded.passing_tds,
                passing_interceptions = excluded.passing_interceptions,
                rushing_yards = excluded.rushing_yards,
                rushing_tds = excluded.rushing_tds,
                receiving_yards = excluded.receiving_yards,
                receiving_tds = excluded.receiving_tds,
                offense_snap_pct = excluded.offense_snap_pct,
                fantasy_points = excluded.fantasy_points,
                fantasy_points_ppr = excluded.fantasy_points_ppr,
                source_snapshot_id = excluded.source_snapshot_id
            RETURNING player_id
            """,
            [stats_snap["snapshot_id"]],
        ).fetchall()
        total_inserted += len(rows)

    return total_inserted
