"""GET /players, GET /players/{id} -- reads directly from `players`/`player_id_map`
(canonical identity spine, M2). No business logic; a pure projection."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import PlayerDetail, PlayerSummary

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=list[PlayerSummary])
def list_players(
    position: str | None = Query(None),
    q: str | None = Query(None, description="Case-insensitive substring match on display_name"),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[PlayerSummary]:
    where = []
    params: list = []
    if position:
        where.append("position = ?")
        params.append(position)
    if q:
        where.append("lower(display_name) LIKE ?")
        params.append(f"%{q.lower()}%")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = con.execute(
        f"SELECT player_id, display_name, position, college_name, draft_year, status "
        f"FROM players {clause} ORDER BY display_name LIMIT ?",
        [*params, limit],
    ).fetchall()
    return [
        PlayerSummary(
            player_id=r[0], display_name=r[1], position=r[2], college_name=r[3],
            draft_year=r[4], status=r[5],
        )
        for r in rows
    ]


@router.get("/{player_id}", response_model=PlayerDetail)
def get_player(player_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> PlayerDetail:
    row = con.execute(
        "SELECT player_id, gsis_id, display_name, position, birth_date, college_name, "
        "draft_year, draft_round, draft_pick, draft_team, rookie_season, last_season, status "
        "FROM players WHERE player_id = ?",
        [player_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"player {player_id} not found")
    id_map = dict(
        con.execute(
            "SELECT id_type, id_value FROM player_id_map WHERE player_id = ?", [player_id]
        ).fetchall()
    )
    return PlayerDetail(
        player_id=row[0],
        gsis_id=row[1],
        display_name=row[2],
        position=row[3],
        birth_date=str(row[4]) if row[4] else None,
        college_name=row[5],
        draft_year=row[6],
        draft_round=row[7],
        draft_pick=row[8],
        draft_team=row[9],
        rookie_season=row[10],
        last_season=row[11],
        status=row[12],
        id_map=id_map,
    )
