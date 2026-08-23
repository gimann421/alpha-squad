"""GET /evidence -- direct projection of `evidence_events` (M9)."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import EvidenceRow

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("", response_model=list[EvidenceRow])
def get_evidence(
    player_id: str | None = Query(None),
    season: int | None = Query(None),
    week: int | None = Query(None),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[EvidenceRow]:
    where = []
    params: list = []
    if player_id:
        where.append("e.player_id = ?")
        params.append(player_id)
    if season is not None:
        where.append("e.season = ?")
        params.append(season)
    if week is not None:
        where.append("e.week = ?")
        params.append(week)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = con.execute(
        f"""
        SELECT e.event_id, e.player_id, p.display_name, e.season, e.week, e.event_date,
               e.event_type, e.strength_label, e.strength, e.direction, e.summary, e.source
        FROM evidence_events e
        LEFT JOIN players p ON p.player_id = e.player_id
        {clause}
        ORDER BY e.event_date DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        EvidenceRow(
            event_id=r[0],
            player_id=r[1],
            display_name=r[2],
            season=r[3],
            week=r[4],
            event_date=str(r[5]),
            event_type=r[6],
            strength_label=r[7],
            strength=r[8],
            direction=r[9],
            summary=r[10],
            source=r[11],
        )
        for r in rows
    ]
