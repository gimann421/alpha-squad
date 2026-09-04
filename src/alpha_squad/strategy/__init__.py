"""Stage 1 Claude strategic decision layer (docs/DECISIONS.md D74).

This package sits ABOVE `league/draft.py`'s quantitative recommendation, never inside it:
Claude reasons over an already-computed Alpha recommendation and its decision trace, and can
agree with or strategically override it. It never recomputes VORP/MSV/replacement/survival,
never touches a model, and never talks to Sleeper. The user still manually approves every pick;
no code here submits a Sleeper action.

Modules:
- `contracts.py`  -- the typed request (`ClaudeDecisionContext`) and response
  (`ClaudeDraftDecision`) Claude is graded against.
- `context_builder.py` -- assembles `ClaudeDecisionContext` from an already-built
  `league.draft.DraftRecommendation` (its `.trace`) plus already-loaded league/roster facts.
  Computes nothing new.
- `provider.py` -- the LLM boundary: `ClaudeProvider` (abstract), `AnthropicClaudeProvider`
  (real SDK call), `FakeClaudeProvider` (deterministic test double).
- `review.py` -- orchestration: calls the provider, hard-validates the result against the
  candidate pool, persists a replayable row, and degrades to a clear "Claude unavailable"
  status on any failure -- Alpha's own recommendation is never affected."""
