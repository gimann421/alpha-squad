"""FastAPI dependency injection: one DuckDB connection per request, reading and writing the
exact same tables the CLI does -- there is no parallel data path for the API to drift from
(ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass core model/decision logic").

Schema initialization (`init_db`) runs once at app startup (`api/app.py`'s lifespan), not here.
Per-request connections come from `request.app.state.db_connection.cursor()`, not a fresh
`duckdb.connect()` call -- two real bugs, both found running the real app with Playwright under
real concurrent traffic (not synthetic tests), made both of these necessary: concurrent
`duckdb.connect()` calls against the same file raise a real `BinderException: Unique file handle
conflict`, and concurrent per-request `init_db` calls raise a real
`TransactionException: write-write conflict`. See api/app.py's lifespan docstring for the full
detail."""

from __future__ import annotations

from collections.abc import Iterator

import duckdb
from fastapi import Request


def get_db(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    base: duckdb.DuckDBPyConnection = request.app.state.db_connection
    con = base.cursor()
    try:
        yield con
    finally:
        con.close()
