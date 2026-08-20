"""DuckDB connection management. One file-backed database at settings.db_path; callers get
their own connection (DuckDB supports concurrent readers / single writer) rather than sharing
a global singleton, so tests can point at isolated temp databases."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.storage.schema import ALL_DDL


def get_connection(
    settings: Settings | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    settings = settings or get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(settings.db_path), read_only=read_only)


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    for ddl in ALL_DDL:
        con.execute(ddl)
