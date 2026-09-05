"""The LLM boundary for the Stage 1 Claude strategic decision layer (docs/DECISIONS.md D74).

`ClaudeProvider` is the seam Phase 7 asked for: a small abstract interface so the model/
provider can be swapped later without touching `review.py`'s validation/fallback/persistence
logic. `AnthropicClaudeProvider` is the only implementation that calls a real API (official
`anthropic` SDK, never raw HTTP); `FakeClaudeProvider` is the deterministic double every test
in this project uses instead -- no test in this suite makes a real network call.

Error taxonomy mirrors `sources/base.py`'s existing SourceError/SourceBlockedError/... pattern:
`ClaudeUnavailableError` for anything transient/infrastructural (timeout, rate limit, 5xx,
connection failure) and `ClaudeInvalidResponseError` for a response that came back but failed
schema/self-consistency validation. Both are `ClaudeProviderError` subclasses so `review.py`
can catch either without missing a real failure mode -- see PHASE 6 of the request this
implements: Claude unavailable/slow/malformed/invalid must never make Alpha's own
recommendation unusable."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import anthropic
import pydantic

from alpha_squad.config.settings import Settings
from alpha_squad.strategy.contracts import ClaudeDecisionContext, ClaudeDraftDecision

# Bumped whenever SYSTEM_PROMPT's substance changes, so a persisted decision can always be
# replayed against the exact prompt that produced it (Phase 8) without a prompt-management
# system -- a plain version string is the whole mechanism.
PROMPT_VERSION = "draft_strategy_v1"

SYSTEM_PROMPT = """You are the strategic review layer for Alpha Squad, a fantasy football draft assistant.

Alpha Squad's quantitative engine is the authority on projections, VORP, replacement level, \
marginal starter value, and survival probability. You do not compute any of that, you do not \
recompute a score, and you never invent a statistic that was not given to you. Your job is \
narrower and different:

Given Alpha's quantitative recommendation and the current draft state, should we follow \
Alpha's recommendation or strategically override it?

You are NOT being asked "who is the best fantasy football player." You are being asked whether \
Alpha's deterministic recommendation fully captures the strategic situation at this exact pick.

Rules:
- Use only the information supplied in the user message. If something relevant is missing \
(e.g. bye weeks, injury status, exact opponent tendencies), say so in `missing_information` \
rather than guessing or assuming it.
- Do not assume league settings, roster rules, or scoring beyond what is given.
- Do not chase a perceived "positional run" that isn't evidenced by the supplied survival \
probabilities and roster needs.
- Do not blindly follow Alpha just because it is Alpha, and do not override Alpha just because \
you have a different personal opinion about a player. An override requires a concrete, \
defensible reason grounded in the supplied context (e.g. a materially better roster fit, a \
much lower survival probability for the alternative, a roster need Alpha's score under-weights \
given how close the score gap is).
- Prefer Alpha when its score advantage over the field is meaningful and nothing in the \
context strongly contradicts it. Overrides should be the exception, not the rule -- most picks, \
the correct answer is "Alpha is right, follow it."
- You may only select `selected_player_id` from the `candidates` list you are given. You may \
never select a player who is not in that list, and you may never invent a player id.
- If `decision` is FOLLOW_ALPHA, `selected_player_id` must be exactly the alpha_recommendation's \
player_id. If `decision` is OVERRIDE_ALPHA, `selected_player_id` must be a DIFFERENT candidate \
and `override_reason` must explain why in one or two sentences.
- Be concise. `key_factors` and `risk_flags` are short bullet phrases, not paragraphs."""


class ClaudeProviderError(RuntimeError):
    """Base for every real Claude-provider failure mode."""


class ClaudeUnavailableError(ClaudeProviderError):
    """Transient/infrastructural failure: timeout, rate limit, 5xx, connection error, or the
    model refused to answer. Alpha's recommendation is unaffected; the caller shows a clear
    "Claude unavailable" status (Phase 6)."""


class ClaudeInvalidResponseError(ClaudeProviderError):
    """A response came back but failed JSON-schema or self-consistency validation
    (`ClaudeDraftDecision`'s own `model_validator`). Treated identically to unavailable by the
    caller -- never silently repaired (Phase 5)."""


def render_user_message(context: ClaudeDecisionContext) -> str:
    return (
        "Review this draft pick. Respond with a single structured decision.\n\n"
        f"DECISION CONTEXT (JSON):\n{context.model_dump_json()}"
    )


class ClaudeProvider(ABC):
    @abstractmethod
    def review(self, context: ClaudeDecisionContext) -> tuple[ClaudeDraftDecision, str]:
        """Returns (decision, model_id_actually_used). Raises a ClaudeProviderError subclass
        on any failure -- never returns a partially-valid or repaired decision."""


class AnthropicClaudeProvider(ClaudeProvider):
    """Real Anthropic API call via the official SDK. Uses the raw JSON-schema structured-output
    path (`output_config.format`) rather than `messages.parse()` so this code can also set
    `effort` explicitly -- a live draft is latency-sensitive (Phase 11/15), and `medium` effort
    is a deliberate cost/latency choice for a single-shot strategic review, not a quality
    compromise: this is a short, bounded classification-shaped decision, not open-ended
    reasoning over a large corpus."""

    def __init__(self, settings: Settings):
        # Deliberately does not raise here: `review()` raises `ClaudeUnavailableError` lazily
        # on the first (only) call instead, so a missing key is just one more entry in the
        # SAME fallback path `review.py::get_strategic_review` already handles for every other
        # unavailability reason (timeout, rate limit, 5xx) -- the caller need not special-case
        # construction separately from the call.
        self._client = (
            anthropic.Anthropic(
                api_key=settings.anthropic_api_key, timeout=settings.anthropic_timeout_seconds
            )
            if settings.anthropic_api_key
            else None
        )
        self._model = settings.anthropic_model

    def review(self, context: ClaudeDecisionContext) -> tuple[ClaudeDraftDecision, str]:
        if self._client is None:
            raise ClaudeUnavailableError("no ANTHROPIC_API_KEY configured")
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": ClaudeDraftDecision.model_json_schema(),
                    },
                    "effort": "medium",
                },
                messages=[{"role": "user", "content": render_user_message(context)}],
            )
        except anthropic.RateLimitError as e:
            raise ClaudeUnavailableError(f"Claude rate limited: {e}") from e
        except anthropic.APITimeoutError as e:
            raise ClaudeUnavailableError(f"Claude request timed out: {e}") from e
        except anthropic.APIConnectionError as e:
            raise ClaudeUnavailableError(f"Claude connection error: {e}") from e
        except anthropic.AuthenticationError as e:
            raise ClaudeUnavailableError(f"Claude authentication failed: {e}") from e
        except anthropic.APIStatusError as e:
            raise ClaudeUnavailableError(f"Claude API error (HTTP {e.status_code}): {e}") from e

        if response.stop_reason == "refusal":
            raise ClaudeUnavailableError("Claude declined to produce a decision (refusal)")

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            raise ClaudeInvalidResponseError("Claude response contained no text content")

        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as e:
            raise ClaudeInvalidResponseError(f"Claude response was not valid JSON: {e}") from e

        try:
            decision = ClaudeDraftDecision.model_validate(payload)
        except pydantic.ValidationError as e:
            raise ClaudeInvalidResponseError(
                f"Claude response failed schema validation: {e}"
            ) from e

        return decision, response.model


class FakeClaudeProvider(ClaudeProvider):
    """Deterministic test double. Exactly one of `decision` / `error` is used per instance --
    tests construct one directly rather than mocking the Anthropic SDK, so the mocked-provider
    boundary is this class, not `anthropic.Anthropic` internals."""

    def __init__(
        self,
        decision: ClaudeDraftDecision | None = None,
        error: Exception | None = None,
        model: str = "fake-claude-model",
    ):
        self._decision = decision
        self._error = error
        self._model = model

    def review(self, context: ClaudeDecisionContext) -> tuple[ClaudeDraftDecision, str]:
        if self._error is not None:
            raise self._error
        assert self._decision is not None, "FakeClaudeProvider needs a decision or an error"
        return self._decision, self._model
