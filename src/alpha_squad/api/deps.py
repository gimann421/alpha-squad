"""FastAPI dependency injection: one DuckDB connection per request, reading and writing the
exact same tables the CLI does -- there is no parallel data path for the API to drift from
(ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass core model/decision logic")."""

from __future__ import annotations

from collections.abc import Iterator

import duckdb

from alpha_squad.config.settings import get_settings
from alpha_squad.storage.db import get_connection, init_db


def get_db() -> Iterator[duckdb.DuckDBPyConnection]:
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    try:
        yield con
    finally:
        con.close()
