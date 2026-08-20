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

# M2+ DDL is appended here as later milestones are implemented.
ALL_DDL: list[str] = [
    *M1_SNAPSHOTS_DDL,
]
