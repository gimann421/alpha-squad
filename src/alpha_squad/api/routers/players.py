"""GET /players, GET /players/{id} -- reads directly from `players`/`player_id_map`
(canonical identity spine, M2). No business logic; a pure projection.

GET /players/{id}/detail is the one exception with real logic: it distinguishes UNIVERSAL
player value (projection/uncertainty/market/EDGE/evidence/rookie -- true regardless of league)
from LEAGUE-SPECIFIC value (dynasty trade action, roster fit) when a `league_id` is given,
per PRODUCT_SPEC.md's Application section. Every number is still read from an already-persisted
table or produced by an already-tested M6-M10 function -- this endpoint only joins them."""

from __future__ import annotations

import json

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import (
    EvidenceRow,
    PlayerDetail,
    PlayerDetailFull,
    PlayerEdgeInfo,
    PlayerLeagueValue,
    PlayerRankingInfo,
    PlayerRookieInfo,
    PlayerSummary,
)
from alpha_squad.config.settings import get_settings
from alpha_squad.league.context import resolve_league
from alpha_squad.league.roster import roster_need
from alpha_squad.league.roster_import import roster_positions_for, teams_for_league
from alpha_squad.league.trade import recommend_dynasty_trade
from alpha_squad.market.edge import DEFAULT_ECR_TYPE
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

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
            player_id=r[0],
            display_name=r[1],
            position=r[2],
            college_name=r[3],
            draft_year=r[4],
            status=r[5],
        )
        for r in rows
    ]


def _player_row_or_404(con: duckdb.DuckDBPyConnection, player_id: str) -> tuple:
    row = con.execute(
        "SELECT player_id, gsis_id, display_name, position, birth_date, college_name, "
        "draft_year, draft_round, draft_pick, draft_team, rookie_season, last_season, status "
        "FROM players WHERE player_id = ?",
        [player_id],
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"player {player_id} not found")
    return row


@router.get("/{player_id}/detail", response_model=PlayerDetailFull)
def get_player_detail(
    player_id: str,
    season: int = Query(...),
    ecr_type: str = Query(DEFAULT_ECR_TYPE),
    league_id: str | None = Query(None, description="Adds league-specific value/roster fit"),
    roster_id: int | None = Query(None, description="Requires league_id; adds is_mine"),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> PlayerDetailFull:
    row = _player_row_or_404(con, player_id)
    position = row[3]
    id_map = dict(
        con.execute(
            "SELECT id_type, id_value FROM player_id_map WHERE player_id = ?", [player_id]
        ).fetchall()
    )

    ranking_row = con.execute(
        "SELECT point_prediction, p10, p25, median, p75, p90, top12_prob, top24_prob, "
        "confidence, model_version FROM uncertainty_predictions "
        "WHERE player_id = ? AND season = ? AND model_version = ?",
        [player_id, season, UNCERTAINTY_MODEL_VERSION],
    ).fetchone()
    ranking = (
        PlayerRankingInfo(
            season=season,
            point_prediction=ranking_row[0],
            p10=ranking_row[1],
            p25=ranking_row[2],
            median=ranking_row[3],
            p75=ranking_row[4],
            p90=ranking_row[5],
            top12_prob=ranking_row[6],
            top24_prob=ranking_row[7],
            confidence=ranking_row[8],
            model_version=ranking_row[9],
        )
        if ranking_row
        else None
    )

    edge_row = con.execute(
        "SELECT model_rank, market_rank, rank_edge, action, reasons_json FROM edge_snapshot "
        "WHERE player_id = ? AND season = ? AND ecr_type = ? ORDER BY built_at DESC LIMIT 1",
        [player_id, season, ecr_type],
    ).fetchone()
    edge = (
        PlayerEdgeInfo(
            season=season,
            ecr_type=ecr_type,
            model_rank=edge_row[0],
            market_rank=edge_row[1],
            rank_edge=edge_row[2],
            action=edge_row[3],
            reasons=json.loads(edge_row[4]),
        )
        if edge_row
        else None
    )

    evidence_rows = con.execute(
        "SELECT event_id, player_id, season, week, event_date, event_type, strength_label, "
        "strength, direction, summary, source FROM evidence_events "
        "WHERE player_id = ? ORDER BY event_date DESC LIMIT 10",
        [player_id],
    ).fetchall()
    recent_evidence = [
        EvidenceRow(
            event_id=r[0],
            player_id=r[1],
            display_name=row[2],
            season=r[2],
            week=r[3],
            event_date=str(r[4]),
            event_type=r[5],
            strength_label=r[6],
            strength=r[7],
            direction=r[8],
            summary=r[9],
            source=r[10],
        )
        for r in evidence_rows
    ]

    rookie_class = row[10]  # rookie_season
    rookie_row = (
        con.execute(
            "SELECT predicted_rookie_points, breakout_probability FROM rookie_predictions "
            "WHERE player_id = ? AND draft_class = ? ORDER BY predicted_at DESC LIMIT 1",
            [player_id, rookie_class],
        ).fetchone()
        if rookie_class
        else None
    )
    rookie = (
        PlayerRookieInfo(
            draft_class=rookie_class,
            predicted_rookie_points=rookie_row[0],
            breakout_probability=rookie_row[1],
        )
        if rookie_row
        else None
    )

    league_value = None
    if league_id is not None:
        try:
            league = resolve_league(league_id, con=con)
        except RuntimeError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        trade_rec = recommend_dynasty_trade(con, player_id, season, ecr_type)
        is_mine: bool | None = None
        need: float | None = None
        if roster_id is not None:
            try:
                teams = teams_for_league(con, get_settings(), league)
                if teams is not None:
                    team = next((t for t in teams if t.roster_id == roster_id), None)
                    if team is not None:
                        is_mine = any(p.player_id == player_id for p in team.players)
                    my_positions = roster_positions_for(teams, roster_id)
                    if position:
                        need = roster_need(league, my_positions).get(position)
            except RuntimeError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        league_value = PlayerLeagueValue(
            league_id=league_id,
            is_mine=is_mine,
            roster_need=need,
            trade_action=trade_rec.action,
            trade_reasons=trade_rec.reasons,
            age_adjusted_dynasty_value=trade_rec.age_adjusted_value,
        )

    return PlayerDetailFull(
        player_id=row[0],
        display_name=row[2],
        position=row[3],
        college_name=row[5],
        draft_year=row[6],
        status=row[12],
        gsis_id=row[1],
        birth_date=str(row[4]) if row[4] else None,
        draft_round=row[7],
        draft_pick=row[8],
        draft_team=row[9],
        rookie_season=row[10],
        last_season=row[11],
        id_map=id_map,
        ranking=ranking,
        edge=edge,
        recent_evidence=recent_evidence,
        rookie=rookie,
        league_value=league_value,
    )


@router.get("/{player_id}", response_model=PlayerDetail)
def get_player(player_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> PlayerDetail:
    row = _player_row_or_404(con, player_id)
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
