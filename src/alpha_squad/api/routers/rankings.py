"""GET /rankings -- direct projection of `uncertainty_predictions` (M6). No re-ranking or
re-scoring logic here; the ORDER BY is the same point_prediction the model produced."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import RankingRow

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.get("", response_model=list[RankingRow])
def get_rankings(
    season: int = Query(...),
    position: str | None = Query(None),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[RankingRow]:
    where = ["u.season = ?"]
    params: list = [season]
    if position:
        where.append("u.position = ?")
        params.append(position)
    rows = con.execute(
        f"""
        SELECT u.prediction_id, u.player_id, p.display_name, u.position, u.season,
               u.point_prediction, u.p10, u.p25, u.median, u.p75, u.p90, u.top12_prob,
               u.top24_prob, u.confidence, u.model_version, u.feature_version
        FROM uncertainty_predictions u
        LEFT JOIN players p ON p.player_id = u.player_id
        WHERE {" AND ".join(where)}
        ORDER BY u.point_prediction DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        RankingRow(
            prediction_id=r[0], player_id=r[1], display_name=r[2], position=r[3], season=r[4],
            point_prediction=r[5], p10=r[6], p25=r[7], median=r[8], p75=r[9], p90=r[10],
            top12_prob=r[11], top24_prob=r[12], confidence=r[13], model_version=r[14],
            feature_version=r[15],
        )
        for r in rows
    ]
