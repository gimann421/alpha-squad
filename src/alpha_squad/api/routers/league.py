"""GET /league/{id}/context, /roster; POST /league/{id}/draft, /waivers, /trade -- every
recommendation calls the exact M10 function the CLI calls (recommend_draft_pick,
recommend_waiver_pickup, recommend_dynasty_trade). Zero parallel decision logic
(ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass core model/decision logic"); a
missing league context returns 404, never a fabricated universal answer (ARCHITECTURE.md)."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import (
    DecisionResponse,
    DraftRequest,
    LeagueSummary,
    TradeRequest,
    WaiverRequest,
)
from alpha_squad.league.context import LeagueContext, list_registered_leagues, resolve_league
from alpha_squad.league.decisions import record_decision
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.league.roster import roster_need
from alpha_squad.league.trade import recommend_dynasty_trade
from alpha_squad.league.waiver import recommend_waiver_pickup

router = APIRouter(prefix="/league", tags=["league"])


def _league_or_404(league_id: str, con: duckdb.DuckDBPyConnection) -> LeagueContext:
    """Looks `league_id` up in the real registry (config/league_configs/registry.yaml) and
    resolves it -- a local YAML config or a live Sleeper league, D33 -- rather than the M10-era
    behavior of always loading the one hardcoded target_league.yaml and merely checking
    whether its own id happened to match the URL. A missing/unregistered league_id returns
    404, never a fabricated universal answer (ARCHITECTURE.md)."""
    try:
        return resolve_league(league_id, con=con)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("", response_model=list[LeagueSummary])
def list_leagues() -> list[LeagueSummary]:
    """Every league this deployment knows about -- the seamless-switching listing (D33) the
    frontend's league selector reads to populate its dropdown, matching
    `alpha-squad league list`."""
    registry = list_registered_leagues()
    return [
        LeagueSummary(
            league_id=league_id,
            source=entry.get("source", "?"),
            detail=entry.get("path")
            if entry.get("source") == "yaml"
            else entry.get("sleeper_league_id"),
        )
        for league_id, entry in sorted(registry.items())
    ]


@router.get("/{league_id}/context")
def get_league_context(league_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    return _league_or_404(league_id, con).model_dump()


@router.get("/{league_id}/roster")
def get_roster_need(
    league_id: str,
    roster_positions: str = Query("", description="Comma-separated positions, e.g. 'QB,RB,RB'"),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    league = _league_or_404(league_id, con)
    positions = [p.strip() for p in roster_positions.split(",") if p.strip()]
    return {
        "league_id": league_id,
        "roster_positions": positions,
        "need": roster_need(league, positions),
    }


@router.post("/{league_id}/draft", response_model=DecisionResponse)
def post_draft(
    league_id: str, body: DraftRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> DecisionResponse:
    league = _league_or_404(league_id, con)
    if body.available_player_ids is not None:
        available = set(body.available_player_ids)
    else:
        projections, _ = load_season_projections(con, body.season)
        available = set(projections)
    try:
        rec = recommend_draft_pick(
            con,
            league,
            body.season,
            body.roster_positions,
            available,
            body.next_pick_overall,
            body.ecr_type,
            body.top_n,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    decision_id = record_decision(
        con,
        "draft_pick",
        league.league_id,
        body.season,
        rec.recommendation,
        rec.alternatives,
        rec.expected_value,
        rec.confidence,
        rec.reasons,
        {"source": "api"},
    )
    return DecisionResponse(
        decision_id=decision_id,
        recommendation=rec.recommendation,
        alternatives=rec.alternatives,
        expected_value=rec.expected_value,
        confidence=rec.confidence,
        reasons=rec.reasons,
    )


@router.post("/{league_id}/waivers", response_model=DecisionResponse)
def post_waiver(
    league_id: str, body: WaiverRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> DecisionResponse:
    league = _league_or_404(league_id, con)
    try:
        rec = recommend_waiver_pickup(
            con, league, body.season, body.week, body.player_id, body.roster_positions
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    decision_id = record_decision(
        con,
        "waiver_bid",
        league.league_id,
        body.season,
        rec.player_id,
        [],
        rec.recommended_bid,
        rec.meaningful_role_probability,
        rec.reasons,
        {"source": "api"},
    )
    return DecisionResponse(
        decision_id=decision_id,
        recommendation=rec.player_id,
        alternatives=[],
        expected_value=rec.recommended_bid,
        confidence=rec.meaningful_role_probability,
        reasons=rec.reasons,
    )


@router.post("/{league_id}/trade", response_model=DecisionResponse)
def post_trade(
    league_id: str, body: TradeRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> DecisionResponse:
    league = _league_or_404(league_id, con)
    rec = recommend_dynasty_trade(con, body.player_id, body.season, body.ecr_type)
    decision_id = record_decision(
        con,
        "dynasty_trade",
        league.league_id,
        body.season,
        rec.player_id,
        [],
        rec.age_adjusted_value,
        None,
        rec.reasons,
        {"source": "api"},
    )
    return DecisionResponse(
        decision_id=decision_id,
        recommendation=rec.player_id,
        alternatives=[],
        expected_value=rec.age_adjusted_value,
        confidence=None,
        reasons=rec.reasons,
    )
