"""DuckDB connection management. One file-backed database at settings.db_path; callers get
their own connection (DuckDB supports concurrent readers / single writer) rather than sharing
a global singleton, so tests can point at isolated temp databases."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.storage.schema import (
    ADD_COLUMN_MIGRATIONS,
    ALL_DDL,
    MARKET_SNAPSHOT_REBUILD,
)


def get_connection(
    settings: Settings | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    settings = settings or get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(settings.db_path), read_only=read_only)


def _migrate(con: duckdb.DuckDBPyConnection) -> None:
    """Bring a pre-existing database up to the current schema. CREATE TABLE IF NOT EXISTS
    covers new tables but never alters an existing one, so a column added to schema.py is
    invisible to any database created before it (docs/DECISIONS.md D39)."""
    for statement in ADD_COLUMN_MIGRATIONS:
        con.execute(statement)

    # Widening market_snapshot's PRIMARY KEY needs a rebuild, not an ALTER. Detected by the
    # absence of the `source` column, which was added in the same change (D38).
    columns = {row[0] for row in con.execute("DESCRIBE market_snapshot").fetchall()}
    if "source" not in columns:
        con.execute("BEGIN TRANSACTION")
        try:
            for statement in MARKET_SNAPSHOT_REBUILD.strip().split(";"):
                if statement.strip():
                    con.execute(statement)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    for ddl in ALL_DDL:
        con.execute(ddl)
    _migrate(con)
