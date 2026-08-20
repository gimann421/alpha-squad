"""Persistence for the snapshot registry and source-health log — the durable record of
"what data do we actually have, and where did it come from" that reproducibility and
provenance depend on."""

from __future__ import annotations

import json

import duckdb

from alpha_squad.sources.base import RawSnapshot, SourceHealth


def record_snapshot(con: duckdb.DuckDBPyConnection, snap: RawSnapshot) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO snapshot_registry
        (snapshot_id, source, dataset, captured_at, url, local_path, sha256, rows,
         columns_json, params_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            snap.snapshot_id,
            snap.source,
            snap.dataset,
            snap.captured_at,
            snap.url,
            str(snap.local_path),
            snap.sha256,
            snap.rows,
            json.dumps(list(snap.columns)) if snap.columns else None,
            json.dumps(dict(snap.params)),
        ],
    )


def record_health(con: duckdb.DuckDBPyConnection, health: SourceHealth) -> None:
    con.execute(
        """
        INSERT INTO source_health_log (checked_at, source, dataset, status, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        [health.checked_at, health.source, health.dataset, health.status.value, health.detail],
    )


def latest_snapshot(
    con: duckdb.DuckDBPyConnection, source: str, dataset: str, **params
) -> dict | None:
    """Most recent snapshot for (source, dataset[, params]). If params are given, matches on
    the exact params_json produced by RawSnapshot.params (sorted key/value string pairs)."""
    if params:
        params_json = json.dumps({k: str(v) for k, v in sorted(params.items())})
        row = con.execute(
            """
            SELECT * FROM snapshot_registry
            WHERE source = ? AND dataset = ? AND params_json = ?
            ORDER BY captured_at DESC LIMIT 1
            """,
            [source, dataset, params_json],
        ).fetchone()
    else:
        row = con.execute(
            """
            SELECT * FROM snapshot_registry
            WHERE source = ? AND dataset = ?
            ORDER BY captured_at DESC LIMIT 1
            """,
            [source, dataset],
        ).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in con.description]
    return dict(zip(cols, row, strict=True))
