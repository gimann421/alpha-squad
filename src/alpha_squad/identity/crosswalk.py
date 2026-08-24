"""Crosswalk builders that enrich the canonical spine (identity/canonical.py) with
external IDs and the college bridge, from sources other than nflverse `players` itself.

Every join here is ID-to-ID: DynastyProcess maps to the spine via `gsis_id`, draft_picks via
`gsis_id` (falling back to `pfr_player_id` -> spine `pfr_id` when gsis_id is absent), and
combine via `pfr_id` -> spine `pfr_id` (combine carries no gsis_id at all — verified against
real data). A row that cannot be matched by any ID path is quarantined into
identity_exceptions, never dropped silently and never matched by name.
"""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import (
    MappingResult,
    insert_id_mappings,
    reader_expr,
    require_snapshot,
)
from alpha_squad.identity.exceptions import record_exception

DYNASTYPROCESS_ID_COLUMNS = {
    "mfl_id": "mfl_id",
    "sportradar_id": "sportradar_id",
    "fantasypros_id": "fantasypros_id",
    "sleeper_id": "sleeper_id",
    "yahoo_id": "yahoo_id",
    "fleaflicker_id": "fleaflicker_id",
    "cbs_id": "cbs_id",
    "cfbref_id": "cfbref_id",
    "rotowire_id": "rotowire_id",
    "rotoworld_id": "rotoworld_id",
    "ktc_id": "ktc_id",
    "stats_id": "stats_id",
    "stats_global_id": "stats_global_id",
    "fantasy_data_id": "fantasy_data_id",
    "swish_id": "swish_id",
    # espn_id doubles as CFBD's own athlete ID space (`player_usage.id`,
    # `recruiting_players.athleteId`, `draft/picks.collegeAthleteId`) -- verified against
    # real data 2026-08-23 (docs/DECISIONS.md D38): 4/4 checked players' CFBD collegeAthleteId
    # matched this exact espn_id, with no fuzzy name matching involved. This is the identity
    # bridge D20 found missing for college production.
    "espn_id": "espn_id",
}


def build_dynastyprocess_crosswalk(
    con: duckdb.DuckDBPyConnection, settings: Settings
) -> list[MappingResult]:
    snap = require_snapshot(con, "dynastyprocess", "player_ids")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    # DynastyProcess's own export sometimes disagrees with itself: the same gsis_id can
    # appear on multiple rows with different names/other-IDs (verified against real data —
    # e.g. gsis_id 00-0031320 mapped to both "Fred Williams" and "Kevin Smith"). Quarantine
    # every row for a gsis_id that isn't internally consistent before attempting any join,
    # rather than trusting whichever row happened to load first.
    inconsistent = con.execute(
        f"""
        SELECT gsis_id, list(DISTINCT name) AS names, count(*) AS n
        FROM {src}
        WHERE gsis_id IS NOT NULL
        GROUP BY gsis_id
        HAVING count(*) > 1
        """
    ).fetchall()
    for gsis_id, names, n in inconsistent:
        record_exception(
            con,
            exception_type="ambiguous_source_mapping",
            subject=f"dynastyprocess_gsis:{gsis_id}",
            detail={
                "gsis_id": gsis_id,
                "conflicting_names": names,
                "row_count": n,
                "source": "dynastyprocess",
            },
        )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE dp_clean AS
        SELECT dp.*
        FROM {src} dp
        WHERE dp.gsis_id IS NOT NULL
          AND dp.gsis_id NOT IN (
              SELECT gsis_id FROM {src} WHERE gsis_id IS NOT NULL GROUP BY gsis_id HAVING count(*) > 1
          )
        """
    )

    orphans = con.execute(
        """
        SELECT count(*) FROM dp_clean d
        WHERE d.gsis_id NOT IN (SELECT gsis_id FROM players)
        """
    ).fetchone()[0]
    if orphans:
        orphan_rows = con.execute(
            "SELECT gsis_id, name FROM dp_clean WHERE gsis_id NOT IN (SELECT gsis_id FROM players) LIMIT 200"
        ).fetchall()
        for gsis_id, name in orphan_rows:
            record_exception(
                con,
                exception_type="orphan_gsis_id",
                subject=f"dynastyprocess_gsis:{gsis_id}",
                detail={"gsis_id": gsis_id, "name": name, "source": "dynastyprocess"},
            )

    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE dp_with_player_id AS
        SELECT p.player_id, d.*
        FROM dp_clean d
        JOIN players p ON p.gsis_id = d.gsis_id
        """
    )

    results = []
    for id_type, column in DYNASTYPROCESS_ID_COLUMNS.items():
        results.append(
            insert_id_mappings(
                con,
                id_type=id_type,
                candidates_view="dp_with_player_id",
                id_value_expr=f"CAST({column} AS VARCHAR)",
                player_id_expr="player_id",
                source="dynastyprocess",
                snapshot_id=snapshot_id,
            )
        )
    return results


def _bulk_upsert_college_bridge(
    con: duckdb.DuckDBPyConnection,
    *,
    matched_table: str,
    id_column: str,
    cfb_player_id_expr: str,
    cfb_id_expr: str,
    snapshot_id: str,
) -> int:
    """Set-based upsert into player_college_bridge from an already-matched temp table.
    Deduplicates by player_id first (GROUP BY) since a batch INSERT...ON CONFLICT cannot
    affect the same primary-key row twice in one statement — a player with more than one
    draft_picks/combine row would otherwise error. An earlier version called this once per
    row from a Python loop, which took tens of seconds at ~10k rows (same per-call overhead
    diagnosed in insert_id_mappings); this is a single round trip."""
    rows = con.execute(
        f"""
        INSERT INTO player_college_bridge (player_id, cfb_player_id, cfb_id, source_snapshot_id)
        SELECT {id_column}, any_value({cfb_player_id_expr}), any_value({cfb_id_expr}), ?
        FROM {matched_table}
        WHERE {id_column} IS NOT NULL AND ({cfb_player_id_expr} IS NOT NULL OR {cfb_id_expr} IS NOT NULL)
        GROUP BY {id_column}
        ON CONFLICT (player_id) DO UPDATE SET
            cfb_player_id = COALESCE(excluded.cfb_player_id, player_college_bridge.cfb_player_id),
            cfb_id = COALESCE(excluded.cfb_id, player_college_bridge.cfb_id),
            source_snapshot_id = excluded.source_snapshot_id
        RETURNING player_id
        """,
        [snapshot_id],
    ).fetchall()
    return len(rows)


def build_draft_picks_bridge(
    con: duckdb.DuckDBPyConnection, settings: Settings
) -> list[MappingResult]:
    snap = require_snapshot(con, "nflverse", "draft_picks")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    # pfr_id lives in player_id_map (inserted by build_players_spine), not as a column on
    # players itself — every native nflverse ID is normalized into the crosswalk table, the
    # spine only carries the identity/biographical attributes.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE draft_matched AS
        SELECT
            COALESCE(p_by_gsis.player_id, m_by_pfr.player_id) AS player_id,
            d.gsis_id, d.pfr_player_id, d.cfb_player_id
        FROM {src} d
        LEFT JOIN players p_by_gsis ON p_by_gsis.gsis_id = d.gsis_id
        LEFT JOIN player_id_map m_by_pfr
          ON d.gsis_id IS NULL AND m_by_pfr.id_type = 'pfr_id' AND m_by_pfr.id_value = d.pfr_player_id
        """
    )

    unmatched = con.execute(
        "SELECT gsis_id, pfr_player_id, cfb_player_id FROM draft_matched WHERE player_id IS NULL"
    ).fetchall()
    for gsis_id, pfr_player_id, cfb_player_id in unmatched:
        subject = gsis_id or pfr_player_id or cfb_player_id or "unknown"
        record_exception(
            con,
            exception_type="unmapped_draft_pick",
            subject=f"draft_picks:{subject}",
            detail={
                "gsis_id": gsis_id,
                "pfr_player_id": pfr_player_id,
                "cfb_player_id": cfb_player_id,
                "reason": "no gsis_id or pfr_id match against the canonical players spine",
            },
        )

    _bulk_upsert_college_bridge(
        con,
        matched_table="draft_matched",
        id_column="player_id",
        cfb_player_id_expr="cfb_player_id",
        cfb_id_expr="NULL",
        snapshot_id=snapshot_id,
    )

    result = insert_id_mappings(
        con,
        id_type="cfb_player_id",
        candidates_view="draft_matched",
        id_value_expr="cfb_player_id",
        player_id_expr="player_id",
        source="nflverse_draft_picks",
        snapshot_id=snapshot_id,
    )
    return [result]


def build_combine_bridge(con: duckdb.DuckDBPyConnection, settings: Settings) -> list[MappingResult]:
    snap = require_snapshot(con, "nflverse", "combine")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    # combine carries no gsis_id at all (verified against real data) — the only ID bridge
    # back to the spine is pfr_id, which lives in player_id_map (see build_draft_picks_bridge).
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE combine_matched AS
        SELECT m.player_id, c.pfr_id, c.cfb_id
        FROM {src} c
        LEFT JOIN player_id_map m ON m.id_type = 'pfr_id' AND m.id_value = c.pfr_id
        """
    )

    unmatched = con.execute(
        "SELECT pfr_id, cfb_id FROM combine_matched WHERE player_id IS NULL AND pfr_id IS NOT NULL"
    ).fetchall()
    for pfr_id, cfb_id in unmatched:
        record_exception(
            con,
            exception_type="unmapped_combine_prospect",
            subject=f"combine_pfr:{pfr_id}",
            detail={
                "pfr_id": pfr_id,
                "cfb_id": cfb_id,
                "reason": "pfr_id has no match against the canonical players spine "
                "(likely a combine participant who never made an NFL roster)",
            },
        )

    _bulk_upsert_college_bridge(
        con,
        matched_table="combine_matched",
        id_column="player_id",
        cfb_player_id_expr="NULL",
        cfb_id_expr="cfb_id",
        snapshot_id=snapshot_id,
    )

    result = insert_id_mappings(
        con,
        id_type="cfb_id",
        candidates_view="combine_matched",
        id_value_expr="cfb_id",
        player_id_expr="player_id",
        source="nflverse_combine",
        snapshot_id=snapshot_id,
    )
    return [result]
