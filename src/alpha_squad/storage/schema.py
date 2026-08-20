"""DuckDB schema, grown milestone by milestone. Each milestone appends its DDL to ALL_DDL
rather than replacing earlier statements; `init_db()` applies all of them with
CREATE TABLE IF NOT EXISTS, so re-running it is always safe and idempotent."""

from __future__ import annotations

M1_SNAPSHOTS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS snapshot_registry (
        snapshot_id VARCHAR PRIMARY KEY,
        source VARCHAR NOT NULL,
        dataset VARCHAR NOT NULL,
        captured_at TIMESTAMP NOT NULL,
        url VARCHAR NOT NULL,
        local_path VARCHAR NOT NULL,
        sha256 VARCHAR NOT NULL,
        rows BIGINT,
        columns_json VARCHAR,
        params_json VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_health_log (
        checked_at TIMESTAMP NOT NULL,
        source VARCHAR NOT NULL,
        dataset VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        detail VARCHAR
    )
    """,
]

M2_IDENTITY_DDL = [
    """
    CREATE TABLE IF NOT EXISTS players (
        player_id VARCHAR PRIMARY KEY,
        gsis_id VARCHAR UNIQUE NOT NULL,
        display_name VARCHAR,
        first_name VARCHAR,
        last_name VARCHAR,
        position VARCHAR,
        position_group VARCHAR,
        birth_date DATE,
        college_name VARCHAR,
        draft_year INTEGER,
        draft_round INTEGER,
        draft_pick INTEGER,
        draft_team VARCHAR,
        rookie_season INTEGER,
        last_season INTEGER,
        status VARCHAR,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    # (id_type, id_value) is PRIMARY KEY: one external ID can belong to exactly one
    # canonical player. Build code must detect collisions and quarantine them into
    # identity_exceptions *before* insert (see identity/canonical.py) rather than relying
    # on this constraint to fail the whole build — but the constraint stays as a hard
    # backstop against a build-code bug silently corrupting the crosswalk.
    """
    CREATE TABLE IF NOT EXISTS player_id_map (
        id_type VARCHAR NOT NULL,
        id_value VARCHAR NOT NULL,
        player_id VARCHAR NOT NULL REFERENCES players(player_id),
        source VARCHAR NOT NULL,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
        PRIMARY KEY (id_type, id_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_college_bridge (
        player_id VARCHAR PRIMARY KEY REFERENCES players(player_id),
        cfb_player_id VARCHAR,
        cfb_id VARCHAR,
        source_snapshot_id VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS identity_exceptions (
        exception_id VARCHAR PRIMARY KEY,
        exception_type VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'PENDING',
        subject VARCHAR NOT NULL,
        detail_json VARCHAR NOT NULL,
        detected_at TIMESTAMP NOT NULL,
        resolved_at TIMESTAMP,
        resolution_note VARCHAR
    )
    """,
]

# M3+ DDL is appended here as later milestones are implemented.
ALL_DDL: list[str] = [
    *M1_SNAPSHOTS_DDL,
    *M2_IDENTITY_DDL,
]
