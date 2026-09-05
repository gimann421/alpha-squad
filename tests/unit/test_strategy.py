"""Stage 1 Claude strategic decision layer (docs/DECISIONS.md D74). No real Anthropic API
calls anywhere in this file -- `AnthropicClaudeProvider`'s SDK boundary is exercised with a
mocked `anthropic.Anthropic` client, and every other test uses `FakeClaudeProvider`."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import anthropic
import duckdb
import pytest

from alpha_squad.league.context import load_league_context
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.storage.db import init_db
from alpha_squad.strategy.context_builder import build_decision_context
from alpha_squad.strategy.contracts import ClaudeDraftDecision
from alpha_squad.strategy.provider import (
    AnthropicClaudeProvider,
    ClaudeInvalidResponseError,
    ClaudeUnavailableError,
    FakeClaudeProvider,
)
from alpha_squad.strategy.review import (
    STATUS_INVALID_RESPONSE,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    STATUS_VALIDATION_FAILED,
    get_strategic_review,
)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_two_qbs(con):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
        "('qb0', 'g0', 'QB Zero', 'QB'), ('qb1', 'g1', 'QB One', 'QB')"
    )
    for player_id, points in [("qb0", 300.0), ("qb1", 250.0)]:
        con.execute(
            "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
            "model_version, feature_version, point_prediction, confidence, calibration_season, "
            "predicted_at) VALUES (?, ?, 2025, 'QB', 'uncertainty_catboost_v1', 'fv1', ?, 0.8, "
            "2024, current_timestamp)",
            [f"pred_{player_id}", player_id, points],
        )


def _context(con):
    league = load_league_context()
    rec = recommend_draft_pick(
        con, league, 2025, [], {"qb0", "qb1"}, next_pick_overall=25, current_pick_overall=10
    )
    return build_decision_context(con, league, 2025, [], rec, is_users_turn=True), rec


class TestClaudeDraftDecisionContract:
    """Contract-level validation: valid response, malformed shape, missing fields, invalid
    enum, override without a reason."""

    def test_valid_follow_decision(self):
        d = ClaudeDraftDecision(decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9)
        assert d.override_reason is None

    def test_valid_override_decision_requires_a_reason(self):
        with pytest.raises(ValueError, match="OVERRIDE_ALPHA requires"):
            ClaudeDraftDecision(decision="OVERRIDE_ALPHA", selected_player_id="qb1", confidence=0.6)

    def test_override_with_a_reason_is_valid(self):
        d = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id="qb1",
            confidence=0.6,
            override_reason="fills a bigger positional need",
        )
        assert d.override_reason

    def test_invalid_enum_value_rejected(self):
        with pytest.raises(ValueError):
            ClaudeDraftDecision(decision="MAYBE", selected_player_id="qb0", confidence=0.5)

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            ClaudeDraftDecision(decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=1.5)

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValueError):
            ClaudeDraftDecision.model_validate({"decision": "FOLLOW_ALPHA", "confidence": 0.5})

    def test_unknown_field_rejected(self):
        """extra='forbid' -- Claude cannot smuggle an extra field past the schema."""
        with pytest.raises(ValueError):
            ClaudeDraftDecision.model_validate(
                {
                    "decision": "FOLLOW_ALPHA",
                    "selected_player_id": "qb0",
                    "confidence": 0.5,
                    "extra_field": "nope",
                }
            )


class TestContextBuilder:
    def test_context_reflects_alpha_recommendation_and_candidates(self, con):
        _seed_two_qbs(con)
        context, rec = _context(con)
        assert context.alpha_recommendation.player_id == rec.recommendation
        assert {c.player_id for c in context.candidates} == {"qb0", "qb1"}
        assert context.draft.current_pick_overall == 10
        assert context.draft.next_pick_overall == 25
        assert context.draft.picks_until_next_turn == 14
        assert context.draft.league_id == "target_league"

    def test_fingerprint_is_deterministic_for_the_same_board(self, con):
        _seed_two_qbs(con)
        context1, _ = _context(con)
        context2, _ = _context(con)
        assert context1.context_fingerprint == context2.context_fingerprint

    def test_fingerprint_changes_when_the_candidate_pool_changes(self, con):
        _seed_two_qbs(con)
        context1, _ = _context(con)
        league = load_league_context()
        rec2 = recommend_draft_pick(
            con, league, 2025, [], {"qb0"}, next_pick_overall=25, current_pick_overall=10
        )
        context2 = build_decision_context(con, league, 2025, [], rec2, is_users_turn=True)
        assert context1.context_fingerprint != context2.context_fingerprint


class TestFakeClaudeProvider:
    def test_returns_configured_decision(self, con):
        _seed_two_qbs(con)
        context, _ = _context(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9
        )
        provider = FakeClaudeProvider(decision=decision, model="fake-x")
        result, model = provider.review(context)
        assert result is decision
        assert model == "fake-x"

    def test_raises_configured_error(self, con):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider = FakeClaudeProvider(error=ClaudeUnavailableError("boom"))
        with pytest.raises(ClaudeUnavailableError):
            provider.review(context)


class TestAnthropicClaudeProviderErrorTranslation:
    """Every real Claude failure mode this project's fallback path must be able to catch,
    exercised against a mocked `anthropic.Anthropic` client -- never a real network call."""

    def _provider(self, monkeypatch):
        from alpha_squad.config.settings import Settings

        settings = Settings(anthropic_api_key="sk-ant-test-fake", anthropic_model="claude-opus-5")
        provider = AnthropicClaudeProvider(settings)
        mock_client = MagicMock()
        provider._client = mock_client
        return provider, mock_client

    def test_no_api_key_raises_unavailable(self, con):
        from alpha_squad.config.settings import Settings

        _seed_two_qbs(con)
        context, _ = _context(con)
        provider = AnthropicClaudeProvider(Settings(anthropic_api_key=None))
        with pytest.raises(ClaudeUnavailableError, match="no ANTHROPIC_API_KEY"):
            provider.review(context)

    def test_rate_limit_raises_unavailable(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        mock_client.messages.create.side_effect = anthropic.RateLimitError(
            "rate limited", response=MagicMock(status_code=429, headers={}), body=None
        )
        with pytest.raises(ClaudeUnavailableError):
            provider.review(context)

    def test_timeout_raises_unavailable(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(request=MagicMock())
        with pytest.raises(ClaudeUnavailableError):
            provider.review(context)

    def test_connection_error_raises_unavailable(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        mock_client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        with pytest.raises(ClaudeUnavailableError):
            provider.review(context)

    def test_server_5xx_raises_unavailable(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        mock_client.messages.create.side_effect = anthropic.InternalServerError(
            "server error", response=MagicMock(status_code=503, headers={}), body=None
        )
        with pytest.raises(ClaudeUnavailableError):
            provider.review(context)

    def test_refusal_raises_unavailable(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        response = MagicMock()
        response.stop_reason = "refusal"
        mock_client.messages.create.return_value = response
        with pytest.raises(ClaudeUnavailableError, match="refusal"):
            provider.review(context)

    def test_no_text_block_raises_invalid_response(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        response = MagicMock()
        response.stop_reason = "end_turn"
        response.content = []
        mock_client.messages.create.return_value = response
        with pytest.raises(ClaudeInvalidResponseError, match="no text content"):
            provider.review(context)

    def test_malformed_json_raises_invalid_response(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        response = MagicMock()
        response.stop_reason = "end_turn"
        block = MagicMock()
        block.type = "text"
        block.text = "not json{"
        response.content = [block]
        mock_client.messages.create.return_value = response
        with pytest.raises(ClaudeInvalidResponseError, match="not valid JSON"):
            provider.review(context)

    def test_json_missing_required_fields_raises_invalid_response(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, _ = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        response = MagicMock()
        response.stop_reason = "end_turn"
        block = MagicMock()
        block.type = "text"
        block.text = json.dumps(
            {"decision": "FOLLOW_ALPHA"}
        )  # missing selected_player_id/confidence
        response.content = [block]
        mock_client.messages.create.return_value = response
        with pytest.raises(ClaudeInvalidResponseError, match="schema validation"):
            provider.review(context)

    def test_valid_response_parses_successfully(self, con, monkeypatch):
        _seed_two_qbs(con)
        context, rec = _context(con)
        provider, mock_client = self._provider(monkeypatch)
        response = MagicMock()
        response.stop_reason = "end_turn"
        response.model = "claude-opus-5"
        block = MagicMock()
        block.type = "text"
        block.text = json.dumps(
            {
                "decision": "FOLLOW_ALPHA",
                "selected_player_id": rec.recommendation,
                "confidence": 0.85,
                "key_factors": ["clear score gap"],
                "risk_flags": [],
                "missing_information": [],
            }
        )
        response.content = [block]
        mock_client.messages.create.return_value = response
        decision, model = provider.review(context)
        assert decision.decision == "FOLLOW_ALPHA"
        assert decision.selected_player_id == rec.recommendation
        assert model == "claude-opus-5"


class TestGetStrategicReview:
    """Fallback + hard validation + persistence, per Phase 5/6/9."""

    def test_agree_case_persists_ok_and_agrees_true(self, con):
        _seed_two_qbs(con)
        context, rec = _context(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id=rec.recommendation, confidence=0.9
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_OK
        assert review.agrees_with_alpha is True
        row = con.execute(
            "SELECT status, agrees_with_alpha, decision, selected_player_id FROM claude_decisions "
            "WHERE claude_decision_id = ?",
            [review.claude_decision_id],
        ).fetchone()
        assert row == ("ok", True, "FOLLOW_ALPHA", rec.recommendation)

    def test_override_case_persists_ok_and_agrees_false(self, con):
        _seed_two_qbs(con)
        context, rec = _context(con)
        other = next(c.player_id for c in context.candidates if c.player_id != rec.recommendation)
        decision = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id=other,
            confidence=0.6,
            override_reason="fills a bigger positional need",
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_OK
        assert review.agrees_with_alpha is False
        assert review.decision.selected_player_id == other

    def test_claude_unavailable_falls_back_and_alpha_is_untouched(self, con):
        _seed_two_qbs(con)
        context, rec = _context(con)
        review = get_strategic_review(
            con, FakeClaudeProvider(error=ClaudeUnavailableError("timed out")), context
        )
        assert review.status == STATUS_UNAVAILABLE
        assert review.decision is None
        assert context.alpha_recommendation.player_id == rec.recommendation  # unaffected

    def test_invalid_response_falls_back(self, con):
        _seed_two_qbs(con)
        context, _ = _context(con)
        review = get_strategic_review(
            con, FakeClaudeProvider(error=ClaudeInvalidResponseError("bad json")), context
        )
        assert review.status == STATUS_INVALID_RESPONSE
        assert review.decision is None

    def test_player_outside_candidate_pool_is_rejected_not_silently_repaired(self, con):
        """The hard-validation floor (Phase 5): a schema-valid response naming a player Claude
        was never shown must never reach the user as a usable decision."""
        _seed_two_qbs(con)
        context, _ = _context(con)
        decision = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id="ghost_player_not_in_pool",
            confidence=0.9,
            override_reason="x",
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_VALIDATION_FAILED
        assert review.decision is None
        row = con.execute(
            "SELECT status, selected_player_id FROM claude_decisions WHERE claude_decision_id = ?",
            [review.claude_decision_id],
        ).fetchone()
        # The raw (rejected) selection is retained for debugging, never surfaced as `review.decision`.
        assert row == ("validation_failed", "ghost_player_not_in_pool")

    def test_follow_alpha_naming_a_different_player_is_rejected(self, con):
        """Self-consistency: FOLLOW_ALPHA must actually name Alpha's own recommendation."""
        _seed_two_qbs(con)
        context, rec = _context(con)
        other = next(c.player_id for c in context.candidates if c.player_id != rec.recommendation)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id=other, confidence=0.9
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_VALIDATION_FAILED

    def test_override_alpha_naming_the_same_player_is_rejected(self, con):
        """Self-consistency: OVERRIDE_ALPHA must actually name a DIFFERENT player."""
        _seed_two_qbs(con)
        context, rec = _context(con)
        decision = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id=rec.recommendation,
            confidence=0.9,
            override_reason="x",
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_VALIDATION_FAILED

    def test_low_confidence_decision_is_still_accepted(self, con):
        """Low confidence is a legitimate signal to surface to the user, not a rejection
        reason -- validity and confidence are independent axes."""
        _seed_two_qbs(con)
        context, rec = _context(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id=rec.recommendation, confidence=0.15
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        assert review.status == STATUS_OK
        assert review.decision.confidence == pytest.approx(0.15)

    def test_context_fingerprint_is_stored_for_replay(self, con):
        _seed_two_qbs(con)
        context, rec = _context(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id=rec.recommendation, confidence=0.9
        )
        review = get_strategic_review(con, FakeClaudeProvider(decision=decision), context)
        row = con.execute(
            "SELECT context_fingerprint, model, prompt_version, context_json FROM claude_decisions "
            "WHERE claude_decision_id = ?",
            [review.claude_decision_id],
        ).fetchone()
        fingerprint, model, prompt_version, context_json = row
        assert fingerprint == context.context_fingerprint
        assert model == "fake-claude-model"
        assert prompt_version == "draft_strategy_v1"
        assert json.loads(context_json)["context_fingerprint"] == context.context_fingerprint


class TestStaleDecisionCannotBeAppliedToAChangedBoard:
    """Case D of the 2026-09-05 pre-draft verification: a Claude decision computed against
    one board must not be treated as valid once the board has materially changed (a real pick
    landed) -- Phase 11's "do not blindly apply the old Claude response to the new board."

    There is no server-side "apply this decision" endpoint at all (Stage 1 is recommend-only),
    so the concrete, testable version of this requirement is: hard-validating an old decision
    against a freshly-built context for the changed board must reject it, exactly the same as
    a genuinely invalid player would be rejected."""

    def test_fingerprint_changes_and_old_selection_is_rejected_against_the_new_board(self, con):
        _seed_two_qbs(con)
        league = load_league_context()

        # Board 1: qb0 and qb1 both available. Claude follows Alpha's pick of qb0.
        rec1 = recommend_draft_pick(
            con, league, 2025, [], {"qb0", "qb1"}, next_pick_overall=25, current_pick_overall=10
        )
        context1 = build_decision_context(con, league, 2025, [], rec1, is_users_turn=True)
        old_decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id=rec1.recommendation, confidence=0.9
        )
        first_review = get_strategic_review(
            con, FakeClaudeProvider(decision=old_decision), context1
        )
        assert first_review.status == STATUS_OK

        # The board changes: qb0 gets drafted by someone else before the user acts. A fresh
        # Alpha recommendation for the new board no longer has qb0 as a candidate at all.
        rec2 = recommend_draft_pick(
            con, league, 2025, [], {"qb1"}, next_pick_overall=25, current_pick_overall=11
        )
        context2 = build_decision_context(con, league, 2025, [], rec2, is_users_turn=True)

        assert context2.context_fingerprint != context1.context_fingerprint
        assert rec1.recommendation not in {c.player_id for c in context2.candidates}

        # Attempting to apply the OLD (stale) Claude decision against the NEW board must be
        # rejected -- it names a player who is no longer even a candidate, let alone available.
        stale_review = get_strategic_review(
            con, FakeClaudeProvider(decision=old_decision), context2
        )
        assert stale_review.status == STATUS_VALIDATION_FAILED
        assert stale_review.decision is None
        assert "not one of the" in (stale_review.error_message or "")
