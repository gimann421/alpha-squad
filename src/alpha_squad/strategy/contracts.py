"""Typed contract between Alpha's quantitative engine and the Claude strategic reviewer
(Stage 1, docs/DECISIONS.md D74).

`ClaudeDecisionContext` is the ONLY thing Claude receives. Every field is either copied
directly from `league.draft.DraftDecisionTrace` (already computed and already discarded once
before this hardening pass exposed it, see D73) or from already-loaded league/roster facts
(`league.roster.roster_need`, `league.context.LeagueContext`) -- nothing here is fabricated,
independently fetched, or re-derived by a parallel calculation. `ClaudeDraftDecision` is the
ONLY thing Claude is allowed to return; `strategy/provider.py` constrains the model to this
exact JSON schema and `strategy/review.py` hard-validates it before it is ever shown to a user."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaudeCandidateContext(BaseModel):
    """One scored candidate from Alpha's own top-N shortlist (`DraftCandidateTrace`) --
    Claude's selectable universe is bounded to exactly this list (see review.py), never the
    full draft board, so it can only ever recommend a player Alpha itself already vetted."""

    player_id: str
    display_name: str | None
    position: str
    score: float
    vorp: float
    marginal_starter_value: float | None
    confidence: float | None
    survival_probability: float | None


class ClaudeAlphaRecommendation(BaseModel):
    """Alpha's own top pick, mirrored from the same candidate the API already returned as
    `DecisionResponse.recommendation` -- never a second, independently-derived opinion."""

    player_id: str
    display_name: str | None
    position: str
    score: float
    vorp: float
    marginal_starter_value: float | None
    confidence: float | None
    survival_probability: float | None
    reasons: list[str]


class ClaudeDraftState(BaseModel):
    """Draft/league facts available at recommendation time -- league config and the same
    `current_pick_overall`/`next_pick_overall`/`available_pool_size` already in the trace,
    plus `roster_need` (already-computed positional need, `league/roster.py`)."""

    league_id: str
    season: int
    format: str
    teams: int
    roster_size: int | None
    ecr_type: str
    current_pick_overall: int | None
    next_pick_overall: int | None
    picks_until_next_turn: int
    available_pool_size: int
    roster_positions: list[str]
    roster_need: dict[str, float]
    is_users_turn: bool | None = None


class ClaudeDecisionContext(BaseModel):
    """The full input Claude reasons over for one pick. `context_fingerprint` identifies the
    exact board state this was built against (league/season/pick/candidate-id-set) -- echoed
    back in the response so a caller can detect a stale approval if the board moves before the
    user acts (Phase 11's staleness requirement)."""

    context_fingerprint: str
    draft: ClaudeDraftState
    alpha_recommendation: ClaudeAlphaRecommendation
    runner_up_player_id: str | None
    score_gap_to_runner_up: float | None
    candidates: list[ClaudeCandidateContext]


class ClaudeDraftDecision(BaseModel):
    """The ONLY shape Claude is allowed to return (enforced via a JSON-schema-constrained
    request, `provider.py`). `selected_player_id` must be one of the `candidates` ids Claude
    was shown -- enforced again, independently, in `review.py`'s hard validation, since a
    schema-valid response can still name a player outside the pool the model was told to
    choose from."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["FOLLOW_ALPHA", "OVERRIDE_ALPHA"]
    selected_player_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    override_reason: str | None = Field(
        default=None,
        description="Required and non-empty when decision=OVERRIDE_ALPHA; must be null/omitted otherwise.",
    )
    key_factors: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Information Claude would have wanted but was not supplied -- never fabricated.",
    )

    @model_validator(mode="after")
    def _override_requires_a_reason(self) -> ClaudeDraftDecision:
        if self.decision == "OVERRIDE_ALPHA" and not (self.override_reason or "").strip():
            raise ValueError("decision=OVERRIDE_ALPHA requires a non-empty override_reason")
        return self
