"""Orchestration for the Stage 1 Claude strategic decision layer (docs/DECISIONS.md D74):
calls the provider, hard-validates the result, persists a replayable row, and never lets a
Claude failure affect Alpha's own recommendation (Phase 6).

The core safety principle this module enforces (Phase 5): Claude can recommend, Claude cannot
make an invalid draft action. `_hard_validate` runs AFTER schema/self-consistency validation
already passed (`ClaudeDraftDecision`'s own `model_validator`) and checks the one thing a
JSON-schema constraint cannot: whether the selected player is actually one Claude was shown as
a candidate. A response that fails either layer is never repaired -- it is recorded with a
`status` other than "ok" and the caller falls back to Alpha's own recommendation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import duckdb

from alpha_squad.sources.base import utcnow
from alpha_squad.strategy.contracts import ClaudeDecisionContext, ClaudeDraftDecision
from alpha_squad.strategy.provider import (
    PROMPT_VERSION,
    ClaudeInvalidResponseError,
    ClaudeProvider,
    ClaudeUnavailableError,
)

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "claude_unavailable"
STATUS_INVALID_RESPONSE = "invalid_response"
STATUS_VALIDATION_FAILED = "validation_failed"


@dataclass
class StrategicReview:
    """What the API layer returns to the frontend. `status != STATUS_OK` means Claude's
    opinion could not be trusted for this pick -- the caller shows Alpha's recommendation with
    a clear "Claude unavailable" indicator (Phase 6, Phase 10) rather than blocking or guessing."""

    claude_decision_id: str
    status: str
    error_message: str | None
    context: ClaudeDecisionContext
    decision: ClaudeDraftDecision | None
    model: str | None
    prompt_version: str
    agrees_with_alpha: bool | None


def _hard_validate(decision: ClaudeDraftDecision, context: ClaudeDecisionContext) -> str | None:
    """Returns None when valid, else a human-readable rejection reason. Every check here is
    independent of `ClaudeDraftDecision`'s own pydantic validator -- that validator only knows
    the shape of one response object; this function is the one place that cross-checks it
    against the actual board (`context.candidates`), which a schema constraint alone cannot do."""
    candidate_ids = {c.player_id for c in context.candidates}
    if decision.selected_player_id not in candidate_ids:
        return (
            f"selected_player_id {decision.selected_player_id!r} is not one of the "
            f"{len(candidate_ids)} candidates Claude was shown"
        )
    if (
        decision.decision == "FOLLOW_ALPHA"
        and decision.selected_player_id != context.alpha_recommendation.player_id
    ):
        return (
            "decision=FOLLOW_ALPHA but selected_player_id "
            f"{decision.selected_player_id!r} does not match Alpha's recommendation "
            f"{context.alpha_recommendation.player_id!r}"
        )
    if (
        decision.decision == "OVERRIDE_ALPHA"
        and decision.selected_player_id == context.alpha_recommendation.player_id
    ):
        return (
            "decision=OVERRIDE_ALPHA but selected_player_id is identical to Alpha's recommendation"
        )
    return None


def _claude_decision_id(context_fingerprint: str, built_at: str) -> str:
    digest = hashlib.md5(f"{context_fingerprint}:{built_at}".encode()).hexdigest()[:16]
    return f"cdec_{digest}"


def _persist(
    con: duckdb.DuckDBPyConnection,
    *,
    alpha_decision_id: str | None,
    context: ClaudeDecisionContext,
    status: str,
    error_message: str | None,
    decision: ClaudeDraftDecision | None,
    model: str | None,
    agrees_with_alpha: bool | None,
) -> str:
    now = utcnow()
    claude_decision_id = _claude_decision_id(context.context_fingerprint, str(now))
    con.execute(
        """
        INSERT INTO claude_decisions
            (claude_decision_id, alpha_decision_id, league_id, season, context_fingerprint,
             current_pick_overall, alpha_player_id, status, error_message, decision,
             selected_player_id, agrees_with_alpha, confidence, override_reason,
             key_factors_json, risk_flags_json, missing_information_json, model,
             prompt_version, context_json, raw_decision_json, actual_pick_player_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        [
            claude_decision_id,
            alpha_decision_id,
            context.draft.league_id,
            context.draft.season,
            context.context_fingerprint,
            context.draft.current_pick_overall,
            context.alpha_recommendation.player_id,
            status,
            error_message,
            decision.decision if decision else None,
            decision.selected_player_id if decision else None,
            agrees_with_alpha,
            decision.confidence if decision else None,
            decision.override_reason if decision else None,
            json.dumps(decision.key_factors) if decision else None,
            json.dumps(decision.risk_flags) if decision else None,
            json.dumps(decision.missing_information) if decision else None,
            model,
            PROMPT_VERSION,
            context.model_dump_json(),
            decision.model_dump_json() if decision else None,
            now,
        ],
    )
    return claude_decision_id


def get_strategic_review(
    con: duckdb.DuckDBPyConnection,
    provider: ClaudeProvider,
    context: ClaudeDecisionContext,
    *,
    alpha_decision_id: str | None = None,
) -> StrategicReview:
    try:
        decision, model = provider.review(context)
    except ClaudeUnavailableError as e:
        claude_decision_id = _persist(
            con,
            alpha_decision_id=alpha_decision_id,
            context=context,
            status=STATUS_UNAVAILABLE,
            error_message=str(e),
            decision=None,
            model=None,
            agrees_with_alpha=None,
        )
        return StrategicReview(
            claude_decision_id=claude_decision_id,
            status=STATUS_UNAVAILABLE,
            error_message=str(e),
            context=context,
            decision=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            agrees_with_alpha=None,
        )
    except ClaudeInvalidResponseError as e:
        claude_decision_id = _persist(
            con,
            alpha_decision_id=alpha_decision_id,
            context=context,
            status=STATUS_INVALID_RESPONSE,
            error_message=str(e),
            decision=None,
            model=None,
            agrees_with_alpha=None,
        )
        return StrategicReview(
            claude_decision_id=claude_decision_id,
            status=STATUS_INVALID_RESPONSE,
            error_message=str(e),
            context=context,
            decision=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            agrees_with_alpha=None,
        )

    rejection = _hard_validate(decision, context)
    if rejection is not None:
        claude_decision_id = _persist(
            con,
            alpha_decision_id=alpha_decision_id,
            context=context,
            status=STATUS_VALIDATION_FAILED,
            error_message=rejection,
            decision=decision,
            model=model,
            agrees_with_alpha=None,
        )
        return StrategicReview(
            claude_decision_id=claude_decision_id,
            status=STATUS_VALIDATION_FAILED,
            error_message=rejection,
            context=context,
            decision=None,
            model=model,
            prompt_version=PROMPT_VERSION,
            agrees_with_alpha=None,
        )

    agrees_with_alpha = decision.selected_player_id == context.alpha_recommendation.player_id
    claude_decision_id = _persist(
        con,
        alpha_decision_id=alpha_decision_id,
        context=context,
        status=STATUS_OK,
        error_message=None,
        decision=decision,
        model=model,
        agrees_with_alpha=agrees_with_alpha,
    )
    return StrategicReview(
        claude_decision_id=claude_decision_id,
        status=STATUS_OK,
        error_message=None,
        context=context,
        decision=decision,
        model=model,
        prompt_version=PROMPT_VERSION,
        agrees_with_alpha=agrees_with_alpha,
    )
