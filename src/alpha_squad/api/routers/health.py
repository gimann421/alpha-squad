"""GET /health/sources -- direct projection of `source_health_log` (M1), the latest check
per (source, dataset). Surfaces AVAILABLE/BLOCKED_BY_POLICY/NO_CREDENTIALS/ERROR honestly;
never hides a blocked source behind a generic "OK"."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import SourceHealthRow

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/sources", response_model=list[SourceHealthRow])
def get_source_health(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[SourceHealthRow]:
    rows = con.execute(
        """
        SELECT source, dataset, status, checked_at, detail FROM (
            SELECT *, row_number() OVER (PARTITION BY source, dataset ORDER BY checked_at DESC) AS rn
            FROM source_health_log
        ) WHERE rn = 1
        ORDER BY source, dataset
        """
    ).fetchall()
    return [
        SourceHealthRow(source=r[0], dataset=r[1], status=r[2], checked_at=str(r[3]), detail=r[4])
        for r in rows
    ]
