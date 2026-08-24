"""Canonical player identity: the internal player_id spine and its ID-to-ID crosswalk.

Spine: nflverse `players`, keyed on `gsis_id` — verified 100% populated and unique across
all 25,046 rows (see docs/DECISIONS.md D11). `player_id` is deterministic
(`asq_<16 hex chars of md5(gsis_id)>`), not a persisted sequence counter, so rebuilding
identity from the same snapshots always reproduces the same IDs — required for the
"historical prediction must be reconstructable" acceptance criterion.

Every mapping insert goes through `insert_id_mappings`, which detects collisions *before*
writing: an external ID that would attach to two different canonical players, or a single
external entity whose own source data disagrees with itself, is quarantined into
identity_exceptions instead of silently picked-one/overwritten. Nothing here ever joins
production data on a name column — see tests/contracts/test_no_name_joins.py.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import duckdb

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.identity.exceptions import record_exception
from alpha_squad.sources.base import utcnow
from alpha_squad.storage.snapshots import latest_snapshot

# Native ID columns present directly on the nflverse `players` spine table.
NFLVERSE_NATIVE_ID_COLUMNS = {
    "gsis_id": "gsis_id",
    "pfr_id": "pfr_id",
    "espn_id": "espn_id",
    "otc_id": "otc_id",
    "esb_id": "esb_id",
    "nfl_id": "nfl_id",
    "smart_id": "smart_id",
    "pff_id": "pff_id",
}


def mint_player_id(gsis_id: str) -> str:
    """Must stay byte-for-byte identical to the SQL expression in build_players_spine
    (`'asq_' || substr(md5(gsis_id), 1, 16)`) — this Python version exists for code that
    needs a player_id without a DB round-trip (e.g. feature/model code joining on a
    known gsis_id). MD5 here is purely a deterministic surrogate-key generator, not used
    for anything security-sensitive; collision risk across tens of thousands of players is
    negligible. Regression-tested for parity with the SQL path in
    tests/unit/test_canonical_identity.py."""
    digest = hashlib.md5(gsis_id.encode("utf-8")).hexdigest()[:16]
    return f"asq_{digest}"


# Single source of truth for the SQL-side id-minting expression, so build_players_spine
# can't drift from mint_player_id() by editing one and not the other.
PLAYER_ID_SQL_EXPR = "'asq_' || substr(md5(gsis_id), 1, 16)"


def reader_expr(local_path: str) -> str:
    if local_path.endswith(".parquet"):
        return f"read_parquet('{local_path}')"
    # nullstr=['NA'] handles a real data-quality trap found in DynastyProcess's CSV export
    # (R/readr writes the literal string "NA" for missing values in every column type,
    # including ID columns) — see docs/DECISIONS.md D12.
    return f"read_csv_auto('{local_path}', nullstr=['NA'])"


def require_snapshot(con: duckdb.DuckDBPyConnection, source: str, dataset: str, **params) -> dict:
    snap = latest_snapshot(con, source, dataset, **params)
    if snap is None:
        raise RuntimeError(
            f"no snapshot found for {source}/{dataset}{params or ''}; "
            "run `alpha-squad sources ingest` first — identity is built only from stored "
            "immutable snapshots, never a live re-fetch, so it stays reproducible."
        )
    return snap


@dataclass
class MappingResult:
    id_type: str
    inserted: int = 0
    collisions_quarantined: int = 0


@dataclass
class BuildReport:
    players_upserted: int = 0
    mapping_results: list[MappingResult] = field(default_factory=list)
    exceptions_recorded: int = 0


def insert_id_mappings(
    con: duckdb.DuckDBPyConnection,
    *,
    id_type: str,
    candidates_view: str,
    id_value_expr: str,
    player_id_expr: str,
    source: str,
    snapshot_id: str,
) -> MappingResult:
    """Insert (id_type, id_value) -> player_id mappings from `candidates_view`, quarantining
    any id_value that would map to more than one distinct player_id — whether that
    ambiguity comes from the source data itself (two rows, same id_value, different
    player_id) or from colliding with a mapping already committed by an earlier source.
    Never overwrites an existing mapping and never picks a winner among conflicting ones.

    Entirely set-based (one GROUP BY pass, one INSERT...SELECT): an earlier version fetched
    the clean rows into Python and inserted them one `con.execute()` call at a time, which
    took 88s for 25k rows in profiling — per-call round-trip overhead dominates at that row
    count. Only the (expected-small) exception rows are ever pulled into Python.
    """
    # Materialize the group-by once; every downstream query reuses it instead of
    # recomputing GROUP BY id_value over the raw candidates 2-3 more times.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _mapping_grouped AS
        SELECT {id_value_expr} AS id_value,
               any_value({player_id_expr}) AS player_id,
               count(DISTINCT {player_id_expr}) AS distinct_player_ids
        FROM {candidates_view}
        WHERE {id_value_expr} IS NOT NULL AND {player_id_expr} IS NOT NULL
        GROUP BY {id_value_expr}
        """
    )

    # Ambiguous within this batch: the same id_value appears with >1 distinct player_id.
    # (Needs the actual list of conflicting IDs for the exception detail, so re-derive from
    # the raw candidates rather than _mapping_grouped, which only kept one via any_value.)
    ambiguous = con.execute(
        f"""
        SELECT {id_value_expr} AS id_value, list(DISTINCT {player_id_expr}) AS player_ids
        FROM {candidates_view}
        WHERE {id_value_expr} IN (SELECT id_value FROM _mapping_grouped WHERE distinct_player_ids > 1)
        GROUP BY {id_value_expr}
        """
    ).fetchall()
    for id_value, player_ids in ambiguous:
        record_exception(
            con,
            exception_type="ambiguous_source_mapping",
            subject=f"{id_type}:{id_value}",
            detail={
                "id_type": id_type,
                "id_value": id_value,
                "source": source,
                "conflicting_player_ids": player_ids,
            },
        )

    cross_source_conflicts = con.execute(
        """
        SELECT g.id_value, g.player_id, existing.player_id AS existing_player_id
        FROM _mapping_grouped g
        JOIN player_id_map existing
          ON existing.id_type = ? AND existing.id_value = g.id_value
        WHERE g.distinct_player_ids = 1 AND existing.player_id != g.player_id
        """,
        [id_type],
    ).fetchall()
    for id_value, new_pid, existing_pid in cross_source_conflicts:
        record_exception(
            con,
            exception_type="cross_source_id_collision",
            subject=f"{id_type}:{id_value}",
            detail={
                "id_type": id_type,
                "id_value": id_value,
                "source": source,
                "incoming_player_id": new_pid,
                "existing_player_id": existing_pid,
            },
        )

    inserted_rows = con.execute(
        """
        INSERT INTO player_id_map (id_type, id_value, player_id, source, source_snapshot_id, created_at)
        SELECT ?, g.id_value, g.player_id, ?, ?, ?
        FROM _mapping_grouped g
        LEFT JOIN player_id_map existing
          ON existing.id_type = ? AND existing.id_value = g.id_value
        WHERE g.distinct_player_ids = 1
          AND (existing.id_value IS NULL OR existing.player_id = g.player_id)
        ON CONFLICT (id_type, id_value) DO NOTHING
        RETURNING id_value
        """,
        [id_type, source, snapshot_id, utcnow(), id_type],
    ).fetchall()

    return MappingResult(
        id_type=id_type,
        inserted=len(inserted_rows),
        collisions_quarantined=len(ambiguous) + len(cross_source_conflicts),
    )


def build_players_spine(
    con: duckdb.DuckDBPyConnection, settings: Settings
) -> tuple[int, str, list[MappingResult]]:
    snap = require_snapshot(con, "nflverse", "players")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    # Draft capital is COALESCEd from `draft_picks` because nflverse's `players` file lags the
    # draft for the newest class: verified against real data, all 694 rookie_season=2026 rows
    # have a NULL draft_year while `draft_picks` already carries the full 257-pick 2026 draft.
    # Draft capital is the strongest single rookie feature, so without this the incoming class
    # cannot be projected at all (docs/DECISIONS.md D40).
    #
    # The join falls back to esb_id because `draft_picks.gsis_id` changes shape for the newest
    # class -- 2022-2025 hold real gsis ids ('00-%'), 2026 holds 230 esb-style ids and zero real
    # gsis ids (real ones are evidently assigned later). Done here, inside the spine build,
    # rather than as a later UPDATE: DuckDB implements UPDATE as delete+insert and refuses it on
    # a table other tables hold foreign keys into, which `players` is.
    picks = require_snapshot(con, "nflverse", "draft_picks")
    picks_src = reader_expr(picks["local_path"])
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE draft_capital AS
        SELECT source_id, any_value(round) AS round, any_value(pick) AS pick,
               any_value(team) AS team
        FROM (
            SELECT gsis_id AS source_id, round, pick, team
            FROM {picks_src}
            WHERE gsis_id IS NOT NULL AND round IS NOT NULL
        )
        GROUP BY source_id
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE spine_source AS
        SELECT
            p.gsis_id,
            p.display_name, p.first_name, p.last_name,
            p.position, p.position_group,
            p.birth_date,
            p.college_name,
            p.draft_year,
            COALESCE(p.draft_round, dc.round) AS draft_round,
            COALESCE(p.draft_pick, dc.pick) AS draft_pick,
            COALESCE(p.draft_team, dc.team) AS draft_team,
            p.rookie_season, p.last_season, p.status,
            p.pfr_id, p.espn_id, p.otc_id, p.esb_id, p.nfl_id, p.smart_id, p.pff_id
        FROM {src} p
        LEFT JOIN draft_capital dc
               ON dc.source_id = p.gsis_id
               OR (p.draft_round IS NULL AND dc.source_id = p.esb_id)
        WHERE p.gsis_id IS NOT NULL
        """
    )

    con.execute(
        f"""
        INSERT INTO players (
            player_id, gsis_id, display_name, first_name, last_name, position, position_group,
            birth_date, college_name, draft_year, draft_round, draft_pick, draft_team,
            rookie_season, last_season, status, source_snapshot_id
        )
        SELECT
            {PLAYER_ID_SQL_EXPR},
            gsis_id, display_name, first_name, last_name, position, position_group,
            birth_date, college_name, draft_year, draft_round, draft_pick, draft_team,
            rookie_season, last_season, status, '{snapshot_id}'
        FROM spine_source
        ON CONFLICT (player_id) DO UPDATE SET
            display_name = excluded.display_name,
            position = excluded.position,
            position_group = excluded.position_group,
            last_season = excluded.last_season,
            status = excluded.status,
            -- Draft capital has to refresh on re-run, not just on first insert: a rookie
            -- enters `players` before the draft data for their class is published, so a row
            -- first written with NULL capital would otherwise keep it forever -- which is
            -- exactly what left the 2026 class unprojectable (D40). COALESCE so a later
            -- snapshot that has gone NULL can never erase a value already known.
            draft_round = COALESCE(excluded.draft_round, players.draft_round),
            draft_pick = COALESCE(excluded.draft_pick, players.draft_pick),
            draft_team = COALESCE(excluded.draft_team, players.draft_team),
            draft_year = COALESCE(excluded.draft_year, players.draft_year),
            rookie_season = COALESCE(excluded.rookie_season, players.rookie_season),
            source_snapshot_id = excluded.source_snapshot_id
        """
    )
    players_count = con.execute("SELECT count(*) FROM players").fetchone()[0]

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE spine_with_player_id AS
        SELECT {PLAYER_ID_SQL_EXPR} AS player_id, *
        FROM spine_source
        """
    )

    results = []
    for id_type, column in NFLVERSE_NATIVE_ID_COLUMNS.items():
        results.append(
            insert_id_mappings(
                con,
                id_type=id_type,
                candidates_view="spine_with_player_id",
                id_value_expr=f"CAST({column} AS VARCHAR)",
                player_id_expr="player_id",
                source="nflverse_players",
                snapshot_id=snapshot_id,
            )
        )
    return players_count, snapshot_id, results


def build_identity(con: duckdb.DuckDBPyConnection, settings: Settings | None = None) -> BuildReport:
    settings = settings or get_settings()
    report = BuildReport()

    players_count, _spine_snapshot_id, spine_mappings = build_players_spine(con, settings)
    report.players_upserted = players_count
    report.mapping_results.extend(spine_mappings)

    # Imported here (not at module top) to avoid a circular import: crosswalk.py depends on
    # canonical.py's mint_player_id/insert_id_mappings/require_snapshot helpers.
    from alpha_squad.identity.crosswalk import (
        build_combine_bridge,
        build_draft_picks_bridge,
        build_dynastyprocess_crosswalk,
    )

    report.mapping_results.extend(build_dynastyprocess_crosswalk(con, settings))
    report.mapping_results.extend(build_draft_picks_bridge(con, settings))
    report.mapping_results.extend(build_combine_bridge(con, settings))

    report.exceptions_recorded = con.execute("SELECT count(*) FROM identity_exceptions").fetchone()[
        0
    ]
    return report
