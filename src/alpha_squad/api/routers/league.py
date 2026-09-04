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
    DraftCandidateTraceRow,
    DraftDecisionTrace,
    DraftRequest,
    DropCandidateRow,
    LeagueSummary,
    LeagueTeamsResponse,
    MyTeamPlayerRow,
    MyTeamResponse,
    RegisterLeagueRequest,
    RosterPlayerRow,
    SleeperDraftPickRow,
    SleeperDraftStateResponse,
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
from alpha_squad.league.roster_import import (
    resolve_roster_positions,
    resolve_roster_selection,
    teams_for_league,
)
from alpha_squad.league.roster_intelligence import (
    build_action_center,
    build_my_team_report,
    recommend_drops,
)
from alpha_squad.league.sleeper_draft import (
    compute_turn_info,
    fetch_sleeper_draft_id,
    fetch_sleeper_draft_state,
)
from alpha_squad.league.trade import (
    PickAsset,
    TradePackageSide,
    evaluate_trade_package,
    recommend_dynasty_trade,
)
from alpha_squad.league.waiver import rank_waiver_targets, recommend_waiver_pickup
from alpha_squad.market.edge import DEFAULT_ECR_TYPE
from alpha_squad.sources.base import SourceError

router = APIRouter(prefix="/league", tags=["league"])


def _augment_with_live_draft_picks(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    roster_id: int,
    roster_positions: list[str],
    roster_player_ids: list[str] | None,
) -> tuple[list[str], list[str] | None]:
    """Sleeper's own API docs do not state that `GET /league/{id}/rosters` (what
    `resolve_roster_selection` above reads) updates its `players` array incrementally as a
    LIVE draft progresses -- only that `GET /draft/{id}/picks` does (verified against
    docs.sleeper.com, 2026-09-04 hardening pass). If rosters lag the draft, a mid-draft
    recommendation would price marginal starter value (D60/D63/D67) against a roster that is
    missing this team's own picks so far -- exactly the "recommendation reflects the correct
    roster state" failure mode this hardening pass targets.

    Unions in this roster's players from the SAME authoritative picks feed
    `GET /league/{id}/sleeper-draft` already uses (proven live-accurate,
    `tests/unit/test_sleeper_draft.py`), rather than replacing the `league_rosters` read
    outright -- a keeper/dynasty roster's pre-draft players (never in the picks feed, since
    they weren't drafted THIS draft) still need `league_rosters` to be represented at all.
    Best-effort: any Sleeper failure here is swallowed rather than failing the whole
    recommendation, since `resolve_roster_selection`'s roster is still a real answer on its
    own -- this is a completeness improvement, not the only source of roster truth."""
    sleeper_league_id = getattr(league, "sleeper_league_id", None)
    if getattr(league, "source", None) != "sleeper" or not sleeper_league_id:
        return roster_positions, roster_player_ids
    try:
        draft_id = fetch_sleeper_draft_id(con, get_settings(), sleeper_league_id)
        if draft_id is None:
            return roster_positions, roster_player_ids
        state = fetch_sleeper_draft_state(con, get_settings(), draft_id)
    except SourceError:
        return roster_positions, roster_player_ids

    live_picks = state.player_ids_for_roster(roster_id)
    known = set(roster_player_ids or [])
    new_ids = [pid for pid in live_picks if pid not in known]
    if not new_ids:
        return roster_positions, roster_player_ids

    placeholders = ", ".join("?" for _ in new_ids)
    rows = con.execute(
        f"SELECT player_id, position FROM players WHERE player_id IN ({placeholders})",
        new_ids,
    ).fetchall()
    position_by_id = dict(rows)
    augmented_ids = [*(roster_player_ids or []), *new_ids]
    augmented_positions = [
        *roster_positions,
        *(position_by_id[pid] for pid in new_ids if pid in position_by_id),
    ]
    return augmented_positions, augmented_ids


def _league_or_404(league_id: str, con: duckdb.DuckDBPyConnection) -> LeagueContext:
    """Looks `league_id` up in the real registry (config/league_configs/registry.yaml) and
    resolves it -- a local YAML config or a live Sleeper league, D33 -- rather than the M10-era
    behavior of always loading the one hardcoded target_league.yaml and merely checking
    whether its own id happened to match the URL. A missing/unregistered league_id returns
    404, never a fabricated universal answer (ARCHITECTURE.md).

    A `source: sleeper` league is re-hydrated live on every call (D33), so a transient Sleeper
    outage surfaces here too -- as `SourceError`, which is itself a `RuntimeError` subclass.
    Caught separately as 503 (2026-09-03 product-gap PART 1: "handle API unavailable / temporary
    Sleeper errors") rather than falling into the generic branch, which would otherwise
    misreport "Sleeper is down right now" as "this league doesn't exist"."""
    try:
        return resolve_league(league_id, con=con)
    except SourceError as e:
        raise HTTPException(status_code=503, detail=f"Sleeper temporarily unavailable: {e}") from e
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


@router.get("/{league_id}/sleeper-draft", response_model=SleeperDraftStateResponse)
def get_sleeper_draft(
    league_id: str,
    roster_id: int | None = Query(
        None, description="This team's real roster_id, to compute my-picks/turn/next-pick"
    ),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> SleeperDraftStateResponse:
    """PART 1 of the 2026-09-03 product-gap request: reconstructs the live draft board from
    Sleeper's own authoritative `draft/{id}/picks` feed (league/sleeper_draft.py) instead of the
    user re-typing every opposing team's pick. No decision logic here -- this only reports facts
    Sleeper already knows (who's been picked, whose turn it is); `POST /league/{id}/draft` is
    still the one place a recommendation gets computed, using this endpoint's
    `drafted_player_ids`/`current_pick_overall`/`next_pick_overall` as its inputs.

    `status="no_draft"` (not an error) covers both "not a Sleeper league" being asked anyway and
    a real Sleeper league that has no draft yet -- both are "nothing to sync", not a failure.
    A real Sleeper fetch failure (blocked egress, transient error, bad draft id) surfaces as 503
    with the real underlying message rather than a silently empty/fabricated board."""
    league = _league_or_404(league_id, con)
    sleeper_league_id = getattr(league, "sleeper_league_id", None)
    if getattr(league, "source", None) != "sleeper" or not sleeper_league_id:
        return SleeperDraftStateResponse(
            league_id=league_id,
            draft_id=None,
            status="no_draft",
            draft_type=None,
            teams=None,
            rounds=None,
            picks=[],
            drafted_player_ids=[],
            unmapped_sleeper_ids=[],
        )

    try:
        draft_id = fetch_sleeper_draft_id(con, get_settings(), sleeper_league_id)
        if draft_id is None:
            return SleeperDraftStateResponse(
                league_id=league_id,
                draft_id=None,
                status="no_draft",
                draft_type=None,
                teams=None,
                rounds=None,
                picks=[],
                drafted_player_ids=[],
                unmapped_sleeper_ids=[],
            )
        state = fetch_sleeper_draft_state(con, get_settings(), draft_id)
    except SourceError as e:
        raise HTTPException(
            status_code=503, detail=f"Sleeper draft sync temporarily unavailable: {e}"
        ) from e

    turn = compute_turn_info(state, roster_id)

    names: dict[str, str | None] = {}
    picked_ids = [p.player_id for p in state.picks if p.player_id]
    if picked_ids:
        placeholders = ", ".join("?" for _ in picked_ids)
        names = dict(
            con.execute(
                f"SELECT player_id, display_name FROM players WHERE player_id IN ({placeholders})",
                picked_ids,
            ).fetchall()
        )

    return SleeperDraftStateResponse(
        league_id=league_id,
        draft_id=state.draft_id,
        status=state.status,
        draft_type=state.draft_type,
        teams=state.teams or None,
        rounds=state.rounds or None,
        picks=[
            SleeperDraftPickRow(
                pick_no=p.pick_no,
                round=p.round,
                roster_id=p.roster_id,
                player_id=p.player_id,
                display_name=names.get(p.player_id) if p.player_id else None,
            )
            for p in state.picks
        ],
        drafted_player_ids=state.drafted_player_ids,
        unmapped_sleeper_ids=state.unmapped_sleeper_ids,
        my_player_ids=state.player_ids_for_roster(roster_id) if roster_id is not None else None,
        current_pick_overall=turn.current_pick_overall,
        on_the_clock_roster_id=turn.on_the_clock_roster_id,
        next_pick_overall=turn.next_pick_overall_for_roster,
        is_users_turn=turn.is_users_turn,
    )


@router.get("/{league_id}/my-team", response_model=MyTeamResponse)
def get_my_team(
    league_id: str,
    season: int = Query(...),
    roster_id: int = Query(..., description="Real team id, from GET /league/{id}/teams"),
    ecr_type: str = Query(DEFAULT_ECR_TYPE),
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
    ecr_type: str = Query(DEFAULT_ECR_TYPE),
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
    ecr_type: str = Query(DEFAULT_ECR_TYPE),
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
        # `roster_id` already resolves this team's real players in order to read their
        # positions (D53); the canonical ids come from that SAME fetch. Passing them is what
        # lets the served engine run the benchmarked D63/D67 roster-aware value base
        # (`msv + draft_aware_vorp`) instead of silently falling back to the VORP-only path
        # that no benchmark selected. An explicit `roster_id` wins over an explicit
        # `roster_player_ids` for exactly the reason it already wins over `roster_positions`:
        # it is the real roster, not a client's picture of one.
        selection = resolve_roster_selection(
            con, get_settings(), league, roster_id=body.roster_id, fallback=body.roster_positions
        )
        roster_player_ids = (
            selection.player_ids if selection.player_ids is not None else body.roster_player_ids
        )
        roster_positions = selection.positions
        if body.roster_id is not None:
            roster_positions, roster_player_ids = _augment_with_live_draft_picks(
                con, league, body.roster_id, roster_positions, roster_player_ids
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
            current_pick_overall=body.current_pick_overall,
            roster_player_ids=roster_player_ids,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    trace_row = DraftDecisionTrace(
        season=rec.trace.season,
        ecr_type=rec.trace.ecr_type,
        current_pick_overall=rec.trace.current_pick_overall,
        next_pick_overall=rec.trace.next_pick_overall,
        available_pool_size=rec.trace.available_pool_size,
        roster_size=rec.trace.roster_size,
        runner_up_player_id=rec.trace.runner_up_player_id,
        score_gap_to_runner_up=rec.trace.score_gap_to_runner_up,
        top_candidates=[
            DraftCandidateTraceRow(
                player_id=c.player_id,
                position=c.position,
                score=c.score,
                vorp=c.vorp,
                marginal_starter_value=c.marginal_starter_value,
                confidence=c.confidence,
                survival_probability=c.survival_probability,
                reasons=c.reasons,
            )
            for c in rec.trace.top_candidates
        ],
    )
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
        # `trace` (the same structured trace returned to the caller below) is persisted here
        # too, into the existing free-form `provenance_json` column -- no schema migration --
        # so a decision recorded during a real draft can still be reconstructed afterward, per
        # Phase 5 of the 2026-09-04 hardening pass ("why did Alpha recommend this player at
        # this exact moment"), not just observed in the moment via the API response.
        {"source": "api", "trace": trace_row.model_dump()},
    )
    return DecisionResponse(
        decision_id=decision_id,
        recommendation=rec.recommendation,
        alternatives=rec.alternatives,
        expected_value=rec.expected_value,
        confidence=rec.confidence,
        reasons=rec.reasons,
        trace=trace_row,
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
        action=rec.action,
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
