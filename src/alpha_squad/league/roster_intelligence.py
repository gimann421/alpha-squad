""" "What's wrong with my roster?" (PRODUCT_SPEC.md's Application section) -- joins a real
team's rostered players against the universal player intelligence already computed elsewhere
(projection, uncertainty, market/EDGE, evidence, dynasty value) plus real league-aware
value-based-drafting (positional need, replacement level, marginal value over the league's
actual replacement pool, and a real starter/bench split for THIS team's own roster). No new
scoring logic -- every number here is read from an already-persisted table or computed by an
already-tested M8-M10 function; this module only joins and organizes them per real rostered
player."""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from alpha_squad.config.settings import get_settings
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import (
    compute_league_starters,
    load_season_projections,
    marginal_value_over_replacement,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.roster import roster_need
from alpha_squad.league.roster_import import TeamRoster, teams_for_league
from alpha_squad.market.edge import DEFAULT_ECR_TYPE
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION


@dataclass
class RosterPlayerIntel:
    player_id: str
    display_name: str | None
    position: str | None
    projection: float | None
    p10: float | None
    p90: float | None
    confidence: float | None
    top24_prob: float | None
    market_rank: int | None
    rank_edge: int | None
    edge_action: str | None
    dynasty_value: float | None
    marginal_value: float | None
    is_starter: bool


@dataclass
class MyTeamReport:
    league_id: str
    roster_id: int
    season: int
    owner_display_name: str | None
    team_name: str | None
    players: list[RosterPlayerIntel] = field(default_factory=list)
    unmapped_player_count: int = 0
    positional_needs: dict[str, float] = field(default_factory=dict)
    positional_scarcity: dict[str, float] = field(default_factory=dict)
    replacement_levels: dict[str, float] = field(default_factory=dict)
    total_projected_points: float = 0.0


def _team_for(teams: list[TeamRoster], roster_id: int) -> TeamRoster:
    for t in teams:
        if t.roster_id == roster_id:
            return t
    known = ", ".join(str(t.roster_id) for t in teams) or "(none)"
    raise RuntimeError(f"no roster_id {roster_id} in this league; known roster ids: {known}")


def build_my_team_report(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    roster_id: int,
    *,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> MyTeamReport:
    teams = teams_for_league(con, get_settings(), league)
    if teams is None:
        raise RuntimeError(
            f"league {league.league_id!r} has no real per-team roster source "
            "(only Sleeper-connected leagues support roster_id)"
        )
    team = _team_for(teams, roster_id)

    projections, positions = load_season_projections(con, season)
    levels = replacement_level(league, projections, positions)
    scarcity = positional_scarcity(league, projections, positions)
    vorp = marginal_value_over_replacement(league, projections, positions)
    needs = roster_need(league, [p.position for p in team.players if p.position])

    # A real starter/bench split for THIS team's own roster: the exact same VBD/flex-allocation
    # algorithm replacement.py already uses league-wide, scoped to teams=1 and only this team's
    # own players -- "given only what I actually have, who would I start."
    my_ids = {p.player_id for p in team.players}
    my_projections = {pid: v for pid, v in projections.items() if pid in my_ids}
    my_positions = {pid: v for pid, v in positions.items() if pid in my_ids}
    single_team_league = league.model_copy(update={"teams": 1})
    starters_result = compute_league_starters(single_team_league, my_projections, my_positions)
    starter_ids = starters_result["starters"]

    if my_ids:
        placeholders = ", ".join("?" for _ in my_ids)
        params = list(my_ids)
        edge_rows = {
            r[0]: r[1:]
            for r in con.execute(
                f"""
                SELECT player_id, market_rank, rank_edge, action FROM (
                    SELECT player_id, market_rank, rank_edge, action,
                           row_number() OVER (PARTITION BY player_id ORDER BY built_at DESC) rn
                    FROM edge_snapshot
                    WHERE player_id IN ({placeholders}) AND season = ? AND ecr_type = ?
                ) WHERE rn = 1
                """,
                [*params, season, ecr_type],
            ).fetchall()
        }
        uncertainty_rows = {
            r[0]: r[1:]
            for r in con.execute(
                f"SELECT player_id, p10, p90, confidence, top24_prob FROM uncertainty_predictions "
                f"WHERE player_id IN ({placeholders}) AND season = ? AND model_version = ?",
                [*params, season, UNCERTAINTY_MODEL_VERSION],
            ).fetchall()
        }
        dynasty_rows = dict(
            con.execute(
                f"SELECT player_id, value_2qb FROM dynasty_values WHERE player_id IN ({placeholders})",
                params,
            ).fetchall()
        )
    else:
        edge_rows, uncertainty_rows, dynasty_rows = {}, {}, {}

    players: list[RosterPlayerIntel] = []
    total_points = 0.0
    for p in team.players:
        proj = projections.get(p.player_id)
        if proj is not None:
            total_points += proj
        p10, p90, confidence, top24 = uncertainty_rows.get(p.player_id, (None, None, None, None))
        market_rank, rank_edge, action = edge_rows.get(p.player_id, (None, None, None))
        players.append(
            RosterPlayerIntel(
                player_id=p.player_id,
                display_name=p.display_name,
                position=p.position,
                projection=proj,
                p10=p10,
                p90=p90,
                confidence=confidence,
                top24_prob=top24,
                market_rank=market_rank,
                rank_edge=rank_edge,
                edge_action=action,
                dynasty_value=dynasty_rows.get(p.player_id),
                marginal_value=vorp.get(p.player_id),
                is_starter=p.player_id in starter_ids,
            )
        )
    players.sort(key=lambda x: (-x.is_starter, -(x.projection or 0.0)))

    return MyTeamReport(
        league_id=league.league_id,
        roster_id=roster_id,
        season=season,
        owner_display_name=team.owner_display_name,
        team_name=team.team_name,
        players=players,
        unmapped_player_count=len(team.unmapped_sleeper_ids),
        positional_needs=needs,
        positional_scarcity=scarcity,
        replacement_levels=levels,
        total_projected_points=total_points,
    )


@dataclass
class DropCandidate:
    player_id: str
    display_name: str | None
    position: str | None
    marginal_value: float | None
    reasons: list[str]


def recommend_drops(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    roster_id: int,
    *,
    top_n: int = 5,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[DropCandidate]:
    """ "Who can I drop?" -- the worst bench players on a real roster by marginal value over the
    league's real replacement pool (the same VORP `build_my_team_report` already computes; no
    new scoring here, just picking the bottom of the existing bench). Never considers a starter
    a drop candidate, even a weak one -- dropping a starter isn't a "who's expendable" decision,
    it's a roster-construction decision this function doesn't make."""
    report = build_my_team_report(con, league, season, roster_id, ecr_type=ecr_type)
    bench = [p for p in report.players if not p.is_starter]
    bench.sort(key=lambda p: p.marginal_value if p.marginal_value is not None else float("-inf"))

    candidates: list[DropCandidate] = []
    for p in bench[:top_n]:
        if p.marginal_value is not None:
            reasons = [
                f"bench player, marginal value {p.marginal_value:+.1f} pts "
                f"vs {p.position or 'its position'} replacement"
            ]
        else:
            reasons = ["bench player with no current projection on record"]
        if p.dynasty_value is not None:
            reasons.append(f"dynasty value (2QB) {p.dynasty_value:.0f}")
        candidates.append(
            DropCandidate(
                player_id=p.player_id,
                display_name=p.display_name,
                position=p.position,
                marginal_value=p.marginal_value,
                reasons=reasons,
            )
        )
    return candidates
