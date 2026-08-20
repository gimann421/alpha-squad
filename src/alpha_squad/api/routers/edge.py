"""GET /edge -- direct projection of `edge_snapshot` (M8/M9). BUY/SELL/HOLD/WATCH and their
reasons are read exactly as `edge build` computed and stored them."""

from __future__ import annotations

import json

import duckdb
from fastapi import APIRouter, Depends, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import EdgeRow
from alpha_squad.market.edge import DEFAULT_ECR_TYPE

router = APIRouter(prefix="/edge", tags=["edge"])


@router.get("", response_model=list[EdgeRow])
def get_edge(
    season: int = Query(...),
    action: str | None = Query(None),
    ecr_type: str = Query(DEFAULT_ECR_TYPE),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[EdgeRow]:
    where = ["e.season = ?", "e.ecr_type = ?"]
    params: list = [season, ecr_type]
    if action:
        where.append("e.action = ?")
        params.append(action)
    rows = con.execute(
        f"""
        SELECT e.player_id, p.display_name, e.season, e.position, e.ecr_type, e.model_rank,
               e.market_rank, e.rank_edge, e.projected_points_edge, e.probability_edge,
               e.evidence_score, e.confidence, e.action, e.reasons_json, e.prediction_id
        FROM edge_snapshot e
        LEFT JOIN players p ON p.player_id = e.player_id
        WHERE {" AND ".join(where)}
        ORDER BY abs(e.rank_edge) DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        EdgeRow(
            player_id=r[0],
            display_name=r[1],
            season=r[2],
            position=r[3],
            ecr_type=r[4],
            model_rank=r[5],
            market_rank=r[6],
            rank_edge=r[7],
            projected_points_edge=r[8],
            probability_edge=r[9],
            evidence_score=r[10],
            confidence=r[11],
            action=r[12],
            reasons=json.loads(r[13]),
            prediction_id=r[14],
        )
        for r in rows
    ]
