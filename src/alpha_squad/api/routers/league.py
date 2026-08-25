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
    ActionCenterResponse,
    DecisionResponse,
    DraftRequest,
    DropCandidateRow,
    LeagueSummary,
    LeagueTeamsResponse,
    MyTeamPlayerRow,
    MyTeamResponse,
    RegisterLeagueRequest,
    RosterPlayerRow,
    TeamRosterRow,
    TradePackageRequest,
    TradePackageResponse,
    TradeRequest,
    TradeSignalRow,
    WaiverRequest,
    WaiverTargetRow,
)
from alpha_squad.config.settings import get_settings
from alpha_squad.league.context import (
    LeagueContext,
    list_registered_leagues,
    register_sleeper_league,
    resolve_league,
)
from alpha_squad.league.decisions import record_decision
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.league.roster import roster_need
from alpha_squad.league.roster_import import resolve_roster_positions, teams_for_league
from alpha_squad.league.roster_intelligence import (
    build_action_center,
    build_my_team_report,
    recommend_drops,
)
from alpha_squad.league.trade import (
    PickAsset,
    TradePackageSide,
    evaluate_trade_package,
    recommend_dynasty_trade,
)
from alpha_squad.league.waiver import rank_waiver_targets, recommend_waiver_pickup

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
def list_leagues(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> list[LeagueSummary]:
    """Every league this deployment knows about -- the curated YAML set plus anything
    connected at runtime through the app (`registered_leagues`, D53) -- the seamless-switching
    listing (D33) the frontend's league selector reads to populate its dropdown, matching
    `alpha-squad league list`."""
    registry = list_registered_leagues(con=con)
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


@router.post("/register", response_model=LeagueSummary)
def register_league(
    body: RegisterLeagueRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> LeagueSummary:
    """The "Connect League" onboarding action (D53): validates a real Sleeper league is
    reachable (never trusts the id blind) and persists it so it shows up in `list_leagues`
    from then on. A bad/unreachable league id returns 422 with the real underlying error,
    never a silent no-op."""
    try:
        league = register_sleeper_league(con, body.sleeper_league_id, league_id=body.league_id)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # The registered (URL-addressable) id, not `league.league_id` -- those differ whenever a
    # friendly id was requested, since LeagueContext.league_id always reflects Sleeper's own
    # real league id (the same existing behavior every YAML-registered `source: sleeper` entry
    # already has, e.g. "dilworth" -> a LeagueContext whose own .league_id is the raw Sleeper id).
    registered_id = body.league_id or league.league_id
    return LeagueSummary(league_id=registered_id, source="sleeper", detail=body.sleeper_league_id)


@router.get("/{league_id}/teams", response_model=LeagueTeamsResponse)
def get_league_teams(
    league_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> LeagueTeamsResponse:
    """Every real team in this league, with real rostered players (D53) -- the onboarding
    "pick your team" listing, and the same data the dashboard/my-team/action-center endpoints
    resolve `roster_id` against. A `source: yaml` league has no multi-team data source at all
    (one hand-maintained config, not a full league of real rosters) -- `supported=false` with
    an empty team list, never a fabricated roster."""
    league = _league_or_404(league_id, con)
    teams = teams_for_league(con, get_settings(), league)
    if teams is None:
        return LeagueTeamsResponse(league_id=league_id, supported=False, teams=[])
    return LeagueTeamsResponse(
        league_id=league_id,
        supported=True,
        teams=[
            TeamRosterRow(
                roster_id=t.roster_id,
                owner_display_name=t.owner_display_name,
                team_name=t.team_name,
                players=[
                    RosterPlayerRow(
                        player_id=p.player_id, display_name=p.display_name, position=p.position
                    )
                    for p in t.players
                ],
                unmapped_count=len(t.unmapped_sleeper_ids),
            )
            for t in teams
        ],
    )


@router.get("/{league_id}/my-team", response_model=MyTeamResponse)
def get_my_team(
    league_id: str,
    season: int = Query(...),
    roster_id: int = Query(..., description="Real team id, from GET /league/{id}/teams"),
    ecr_type: str = Query("rsf"),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> MyTeamResponse:
    """ "What's wrong with my roster?" -- every rostered player joined with real projection/
    uncertainty/EDGE/dynasty-value (M6/M8), plus real positional need/scarcity/replacement
    level (M10) and a real starter/bench split computed for this team's own roster alone. No
    new scoring logic -- see league/roster_intelligence.py's module docstring."""
    league = _league_or_404(league_id, con)
    try:
        report = build_my_team_report(con, league, season, roster_id, ecr_type=ecr_type)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return MyTeamResponse(
        league_id=report.league_id,
        roster_id=report.roster_id,
        season=report.season,
        owner_display_name=report.owner_display_name,
        team_name=report.team_name,
        players=[
            MyTeamPlayerRow(
                player_id=p.player_id,
                display_name=p.display_name,
                position=p.position,
                projection=p.projection,
                p10=p.p10,
                p90=p.p90,
                confidence=p.confidence,
                top24_prob=p.top24_prob,
                market_rank=p.market_rank,
                rank_edge=p.rank_edge,
                edge_action=p.edge_action,
                dynasty_value=p.dynasty_value,
                marginal_value=p.marginal_value,
                is_starter=p.is_starter,
            )
            for p in report.players
        ],
        unmapped_player_count=report.unmapped_player_count,
        positional_needs=report.positional_needs,
        positional_scarcity=report.positional_scarcity,
        replacement_levels=report.replacement_levels,
        total_projected_points=report.total_projected_points,
    )


@router.get("/{league_id}/drop-candidates", response_model=list[DropCandidateRow])
def get_drop_candidates(
    league_id: str,
    season: int = Query(...),
    roster_id: int = Query(..., description="Real team id, from GET /league/{id}/teams"),
    top_n: int = Query(5, le=20),
    ecr_type: str = Query("rsf"),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[DropCandidateRow]:
    """ "Who can I drop?" -- the worst real bench players by marginal value over replacement
    (league/roster_intelligence.py::recommend_drops), never a starter."""
    league = _league_or_404(league_id, con)
    try:
        candidates = recommend_drops(con, league, season, roster_id, top_n=top_n, ecr_type=ecr_type)
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [
        DropCandidateRow(
            player_id=c.player_id,
            display_name=c.display_name,
            position=c.position,
            marginal_value=c.marginal_value,
            reasons=c.reasons,
        )
        for c in candidates
    ]


@router.get("/{league_id}/actions", response_model=ActionCenterResponse)
def get_action_center(
    league_id: str,
    season: int = Query(...),
    week: int = Query(...),
    roster_id: int = Query(..., description="Real team id, from GET /league/{id}/teams"),
    add_top_n: int = Query(10, le=50),
    drop_top_n: int = Query(5, le=20),
    ecr_type: str = Query("rsf"),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> ActionCenterResponse:
    """ "What should I pay attention to right now?" -- pure aggregation of the waiver-target,
    drop-candidate, and per-rostered-player EDGE signals above (D53); see
    league/roster_intelligence.py::build_action_center's docstring for why the three groups
    aren't forced onto one fabricated cross-type ranking."""
    league = _league_or_404(league_id, con)
    try:
        report = build_action_center(
            con,
            league,
            season,
            week,
            roster_id,
            add_top_n=add_top_n,
            drop_top_n=drop_top_n,
            ecr_type=ecr_type,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    add_ids = [r.player_id for r in report.adds]
    names: dict[str, str | None] = {}
    if add_ids:
        placeholders = ", ".join("?" for _ in add_ids)
        names = dict(
            con.execute(
                f"SELECT player_id, display_name FROM players WHERE player_id IN ({placeholders})",
                add_ids,
            ).fetchall()
        )

    return ActionCenterResponse(
        league_id=report.league_id,
        roster_id=report.roster_id,
        season=report.season,
        adds=[
            WaiverTargetRow(
                player_id=r.player_id,
                display_name=names.get(r.player_id),
                position=r.position,
                expected_points=r.expected_points,
                meaningful_role_probability=r.meaningful_role_probability,
                dynasty_value=r.dynasty_value,
                value_spike_probability=r.value_spike_probability,
                marginal_value=r.marginal_value,
                roster_fit_multiplier=r.roster_fit_multiplier,
                competing_bid_likelihood=r.competing_bid_likelihood,
                recommended_bid=r.recommended_bid,
                reasons=r.reasons,
            )
            for r in report.adds
        ],
        drops=[
            DropCandidateRow(
                player_id=c.player_id,
                display_name=c.display_name,
                position=c.position,
                marginal_value=c.marginal_value,
                reasons=c.reasons,
            )
            for c in report.drops
        ],
        trade_signals=[
            TradeSignalRow(
                player_id=s.player_id,
                display_name=s.display_name,
                position=s.position,
                edge_action=s.edge_action,
                rank_edge=s.rank_edge,
                dynasty_value=s.dynasty_value,
                summary=s.summary,
            )
            for s in report.trade_signals
        ],
    )


@router.get("/{league_id}/context")
def get_league_context(league_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict:
    return _league_or_404(league_id, con).model_dump()


@router.get("/{league_id}/roster")
def get_roster_need(
    league_id: str,
    roster_positions: str = Query("", description="Comma-separated positions, e.g. 'QB,RB,RB'"),
    roster_id: int | None = Query(
        None, description="Real team id (Sleeper leagues only) -- overrides roster_positions"
    ),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> dict:
    league = _league_or_404(league_id, con)
    fallback = [p.strip() for p in roster_positions.split(",") if p.strip()]
    try:
        positions = resolve_roster_positions(
            con, get_settings(), league, roster_id=roster_id, fallback=fallback
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
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
        roster_positions = resolve_roster_positions(
            con, get_settings(), league, roster_id=body.roster_id, fallback=body.roster_positions
        )
        rec = recommend_draft_pick(
            con,
            league,
            body.season,
            roster_positions,
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
        roster_positions = resolve_roster_positions(
            con, get_settings(), league, roster_id=body.roster_id, fallback=body.roster_positions
        )
        rec = recommend_waiver_pickup(
            con, league, body.season, body.week, body.player_id, roster_positions
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


@router.get("/{league_id}/waiver-targets", response_model=list[WaiverTargetRow])
def get_waiver_targets(
    league_id: str,
    season: int = Query(...),
    week: int = Query(...),
    roster_id: int = Query(..., description="Real team id, from GET /league/{id}/teams"),
    position: str | None = Query(None, description="Restrict to one position, e.g. 'RB'"),
    top_n: int = Query(25, le=100),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[WaiverTargetRow]:
    """Every real free agent ranked by the exact same `recommend_waiver_pickup` scoring a
    single-player lookup already uses (league/waiver.py::rank_waiver_targets) -- the Action
    Center's "who should I add" data source, not a second decision engine."""
    league = _league_or_404(league_id, con)
    try:
        recs = rank_waiver_targets(
            con,
            league,
            season,
            week,
            roster_id,
            positions={position} if position else None,
            top_n=top_n,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    names: dict[str, str | None] = {}
    if recs:
        placeholders = ", ".join("?" for _ in recs)
        names = dict(
            con.execute(
                f"SELECT player_id, display_name FROM players WHERE player_id IN ({placeholders})",
                [r.player_id for r in recs],
            ).fetchall()
        )
    return [
        WaiverTargetRow(
            player_id=r.player_id,
            display_name=names.get(r.player_id),
            position=r.position,
            expected_points=r.expected_points,
            meaningful_role_probability=r.meaningful_role_probability,
            dynasty_value=r.dynasty_value,
            value_spike_probability=r.value_spike_probability,
            marginal_value=r.marginal_value,
            roster_fit_multiplier=r.roster_fit_multiplier,
            competing_bid_likelihood=r.competing_bid_likelihood,
            recommended_bid=r.recommended_bid,
            reasons=r.reasons,
        )
        for r in recs
    ]


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


@router.post("/{league_id}/trade-package", response_model=TradePackageResponse)
def post_trade_package(
    league_id: str, body: TradePackageRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> TradePackageResponse:
    """Multi-asset trade comparison (D45): players + future draft picks on each side, summed
    on the same value_2qb scale `recommend_dynasty_trade` already uses. `future_picks` is not
    read from the league's own context here -- it's always empty in this deployment (no traded-
    picks data source is wired) -- so pick assets are explicit request input, the same way
    `available_player_ids` is explicit rather than inferred in `post_draft`."""
    league = _league_or_404(league_id, con)
    result = evaluate_trade_package(
        con,
        TradePackageSide(
            player_ids=body.side_a.player_ids,
            picks=[PickAsset(p.round, p.pick_in_round, p.years_out) for p in body.side_a.picks],
        ),
        TradePackageSide(
            player_ids=body.side_b.player_ids,
            picks=[PickAsset(p.round, p.pick_in_round, p.years_out) for p in body.side_b.picks],
        ),
        body.season,
        league.teams,
        body.ecr_type,
    )
    return TradePackageResponse(
        side_a_value=result.side_a_value,
        side_b_value=result.side_b_value,
        delta=result.delta,
        favors=result.favors,
        side_a_reasons=result.side_a_reasons,
        side_b_reasons=result.side_b_reasons,
    )
