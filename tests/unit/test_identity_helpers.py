"""Unit tests for small identity helpers not covered elsewhere."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.identity.canonical import reader_expr, require_snapshot
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def test_reader_expr_uses_read_parquet_for_parquet_files():
    assert reader_expr("/tmp/x.parquet") == "read_parquet('/tmp/x.parquet')"


def test_reader_expr_uses_read_csv_auto_with_na_nullstr_for_csv_files():
    expr = reader_expr("/tmp/x.csv")
    assert expr == "read_csv_auto('/tmp/x.csv', nullstr=['NA'])"


def test_require_snapshot_raises_actionable_error_when_missing(con):
    with pytest.raises(RuntimeError, match="sources ingest"):
        require_snapshot(con, "nflverse", "players")
