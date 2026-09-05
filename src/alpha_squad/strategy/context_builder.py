"""Builds `ClaudeDecisionContext` from an already-computed `league.draft.DraftRecommendation`.

Computes nothing new: every quantitative field is read off `rec.trace`
(`league/draft.py::DraftDecisionTrace`, added in the pre-Claude hardening pass specifically as
the observable seam for a future reasoning layer -- see docs/DECISIONS.md D73) or off
`league.roster.roster_need`, itself already called inside `recommend_draft_pick` for the exact
same `roster_positions`. Display names are the one extra read here (a `players` table lookup,
same pattern already used throughout `api/routers/league.py`) since the trace only carries ids."""

from __future__ import annotations

import hashlib

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import DraftRecommendation
from alpha_squad.league.opportunity_cost import picks_until_next_turn
from alpha_squad.league.roster import roster_need
from alpha_squad.strategy.contracts import (
    ClaudeAlphaRecommendation,
    ClaudeCandidateContext,
    ClaudeDecisionContext,
    ClaudeDraftState,
)


def _display_names(con: duckdb.DuckDBPyConnection, player_ids: list[str]) -> dict[str, str | None]:
    if not player_ids:
        return {}
    placeholders = ", ".join("?" for _ in player_ids)
    rows = con.execute(
        f"SELECT player_id, display_name FROM players WHERE player_id IN ({placeholders})",
        player_ids,
    ).fetchall()
    return dict(rows)


def _fingerprint(
    league_id: str, season: int, current_pick_overall: int | None, candidate_ids: list[str]
) -> str:
    """Identifies the exact board state a context was built against -- league/season/pick plus
    the candidate id SET (order-independent, since candidate ordering is a scoring detail, not
    a board-identity detail). Two contexts with the same fingerprint reasoned over the same
    board; a changed fingerprint (Phase 11) is this project's signal that a previously-approved
    Claude decision must not be treated as still valid."""
    digest_input = f"{league_id}:{season}:{current_pick_overall}:{','.join(sorted(candidate_ids))}"
    return hashlib.md5(digest_input.encode()).hexdigest()[:16]


def build_decision_context(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    roster_positions: list[str],
    rec: DraftRecommendation,
    *,
    is_users_turn: bool | None = None,
) -> ClaudeDecisionContext:
    trace = rec.trace
    candidate_ids = [c.player_id for c in trace.top_candidates]
    names = _display_names(con, [*candidate_ids, rec.recommendation])

    alpha_candidate = next(c for c in trace.top_candidates if c.player_id == rec.recommendation)

    draft_state = ClaudeDraftState(
        league_id=league.league_id,
        season=season,
        format=league.format,
        teams=league.teams,
        roster_size=league.roster.get("roster_size"),
        ecr_type=trace.ecr_type,
        current_pick_overall=trace.current_pick_overall,
        next_pick_overall=trace.next_pick_overall,
        picks_until_next_turn=picks_until_next_turn(
            trace.current_pick_overall, trace.next_pick_overall
        ),
        available_pool_size=trace.available_pool_size,
        roster_positions=roster_positions,
        roster_need=roster_need(league, roster_positions),
        is_users_turn=is_users_turn,
    )

    alpha_recommendation = ClaudeAlphaRecommendation(
        player_id=alpha_candidate.player_id,
        display_name=names.get(alpha_candidate.player_id),
        position=alpha_candidate.position,
        score=alpha_candidate.score,
        vorp=alpha_candidate.vorp,
        marginal_starter_value=alpha_candidate.marginal_starter_value,
        confidence=alpha_candidate.confidence,
        survival_probability=alpha_candidate.survival_probability,
        reasons=alpha_candidate.reasons,
    )

    candidates = [
        ClaudeCandidateContext(
            player_id=c.player_id,
            display_name=names.get(c.player_id),
            position=c.position,
            score=c.score,
            vorp=c.vorp,
            marginal_starter_value=c.marginal_starter_value,
            confidence=c.confidence,
            survival_probability=c.survival_probability,
        )
        for c in trace.top_candidates
    ]

    return ClaudeDecisionContext(
        context_fingerprint=_fingerprint(
            league.league_id, season, trace.current_pick_overall, candidate_ids
        ),
        draft=draft_state,
        alpha_recommendation=alpha_recommendation,
        runner_up_player_id=trace.runner_up_player_id,
        score_gap_to_runner_up=trace.score_gap_to_runner_up,
        candidates=candidates,
    )
