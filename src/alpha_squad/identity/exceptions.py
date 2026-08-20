"""The ambiguity-quarantine queue. ARCHITECTURE.md §4: "Ambiguous mappings go into a
mapping-exception queue and block dependent pipelines until resolved or explicitly marked
unsupported." Nothing in identity/canonical.py or identity/crosswalk.py may resolve an
ambiguous mapping on its own — it can only record one here.

`exception_id` is deterministic (hash of type+subject), not a random UUID, so re-running
`identity build` on the same underlying conflict does not spawn duplicate rows, and — just
as importantly — never silently reverts a human's RESOLVED/UNSUPPORTED decision back to
PENDING. `record_exception` uses INSERT ... ON CONFLICT DO NOTHING for exactly that reason.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import duckdb

from alpha_squad.sources.base import utcnow


def exception_id_for(exception_type: str, subject: str) -> str:
    digest = hashlib.sha256(f"{exception_type}:{subject}".encode()).hexdigest()[:20]
    return f"exc_{digest}"


def record_exception(
    con: duckdb.DuckDBPyConnection,
    *,
    exception_type: str,
    subject: str,
    detail: dict[str, Any],
    detected_at: datetime | None = None,
) -> str:
    exc_id = exception_id_for(exception_type, subject)
    con.execute(
        """
        INSERT INTO identity_exceptions
            (exception_id, exception_type, status, subject, detail_json, detected_at)
        VALUES (?, ?, 'PENDING', ?, ?, ?)
        ON CONFLICT (exception_id) DO NOTHING
        """,
        [exc_id, exception_type, subject, json.dumps(detail, default=str), detected_at or utcnow()],
    )
    return exc_id


def resolve_exception(
    con: duckdb.DuckDBPyConnection, exception_id: str, *, status: str, note: str
) -> None:
    if status not in ("RESOLVED", "UNSUPPORTED"):
        raise ValueError(f"status must be RESOLVED or UNSUPPORTED, got {status!r}")
    con.execute(
        """
        UPDATE identity_exceptions
        SET status = ?, resolved_at = ?, resolution_note = ?
        WHERE exception_id = ?
        """,
        [status, utcnow(), note, exception_id],
    )


def list_exceptions(con: duckdb.DuckDBPyConnection, *, status: str | None = None) -> list[dict]:
    if status:
        rows = con.execute(
            "SELECT * FROM identity_exceptions WHERE status = ? ORDER BY detected_at", [status]
        ).fetchall()
    else:
        rows = con.execute("SELECT * FROM identity_exceptions ORDER BY detected_at").fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, row, strict=True)) for row in rows]


def pending_subjects(con: duckdb.DuckDBPyConnection, exception_type: str) -> set[str]:
    """Subjects (e.g. gsis_id values) currently quarantined for a given exception type,
    regardless of status — used by build code to skip re-processing something already
    flagged, whether or not a human has acted on it yet."""
    rows = con.execute(
        "SELECT DISTINCT subject FROM identity_exceptions WHERE exception_type = ?",
        [exception_type],
    ).fetchall()
    return {r[0] for r in rows}
