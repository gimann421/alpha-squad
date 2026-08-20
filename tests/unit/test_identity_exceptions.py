"""Unit tests for the identity exception queue's idempotency and resolution-preservation
guarantees — the core promise behind "ambiguous mappings block dependent pipelines until
resolved... never silently discard.\""""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.identity.exceptions import (
    list_exceptions,
    pending_subjects,
    record_exception,
    resolve_exception,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def test_record_exception_is_idempotent_by_type_and_subject(con):
    id1 = record_exception(
        con, exception_type="ambiguous_source_mapping", subject="x:1", detail={"a": 1}
    )
    id2 = record_exception(
        con, exception_type="ambiguous_source_mapping", subject="x:1", detail={"a": 2}
    )
    assert id1 == id2
    assert con.execute("SELECT count(*) FROM identity_exceptions").fetchone()[0] == 1


def test_resolving_then_rerecording_never_reverts_to_pending(con):
    """The core regression this queue exists to prevent: a rebuild must never silently
    re-open something a human already resolved."""
    exc_id = record_exception(con, exception_type="orphan_gsis_id", subject="g:1", detail={})
    resolve_exception(con, exc_id, status="RESOLVED", note="manually mapped by an operator")

    # Simulate a second identity build run hitting the same conflict again.
    record_exception(con, exception_type="orphan_gsis_id", subject="g:1", detail={})

    row = list_exceptions(con, status="RESOLVED")
    assert len(row) == 1
    assert row[0]["exception_id"] == exc_id
    assert list_exceptions(con, status="PENDING") == []


def test_resolve_rejects_invalid_status(con):
    exc_id = record_exception(con, exception_type="orphan_gsis_id", subject="g:1", detail={})
    with pytest.raises(ValueError):
        resolve_exception(con, exc_id, status="PENDING", note="not allowed")


def test_pending_subjects_returns_all_regardless_of_status(con):
    record_exception(con, exception_type="orphan_gsis_id", subject="g:1", detail={})
    exc2 = record_exception(con, exception_type="orphan_gsis_id", subject="g:2", detail={})
    resolve_exception(con, exc2, status="UNSUPPORTED", note="not fixable")
    assert pending_subjects(con, "orphan_gsis_id") == {"g:1", "g:2"}
