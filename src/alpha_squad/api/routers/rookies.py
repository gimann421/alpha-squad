"""GET /rookies -- direct projection of `rookie_predictions` (M7), plus the same real
nearest-neighbor historical comps `find_historical_comps` already computes."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import RookieComp, RookieRow
from alpha_squad.models.rookie.comps import find_historical_comps

router = APIRouter(prefix="/rookies", tags=["rookies"])


@router.get("", response_model=list[RookieRow])
def get_rookies(
    draft_class: int = Query(...),
    position: str | None = Query(None),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[RookieRow]:
    where = ["r.draft_class = ?"]
    params: list = [draft_class]
    if position:
        where.append("r.position = ?")
        params.append(position)
    rows = con.execute(
        f"""
        SELECT r.player_id, p.display_name, r.position, r.draft_class,
               r.predicted_rookie_points, r.breakout_probability, r.model_version
        FROM rookie_predictions r
        LEFT JOIN players p ON p.player_id = r.player_id
        WHERE {" AND ".join(where)}
        ORDER BY r.predicted_rookie_points DESC NULLS LAST
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        RookieRow(
            player_id=r[0], display_name=r[1], position=r[2], draft_class=r[3],
            predicted_rookie_points=r[4], breakout_probability=r[5], model_version=r[6],
        )
        for r in rows
    ]


@router.get("/{player_id}/comps", response_model=list[RookieComp])
def get_rookie_comps(
    player_id: str,
    draft_class: int = Query(...),
    position: str = Query(...),
    k: int = Query(5, le=20),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[RookieComp]:
    comps = find_historical_comps(con, player_id, draft_class, position, k=k)
    names = (
        dict(
            con.execute(
                "SELECT player_id, display_name FROM players WHERE player_id = ANY(?)",
                [[c["player_id"] for c in comps]],
            ).fetchall()
        )
        if comps
        else {}
    )
    return [
        RookieComp(
            player_id=c["player_id"],
            display_name=names.get(c["player_id"]),
            draft_class=c["draft_class"],
            similarity_distance=c["similarity_distance"],
        )
        for c in comps
    ]
