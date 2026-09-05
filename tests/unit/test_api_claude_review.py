"""API-level coverage for `POST /league/{id}/draft/claude-review` (Stage 1 Claude strategic
decision layer, docs/DECISIONS.md D74). The router's `AnthropicClaudeProvider` reference is
monkeypatched to a fake constructor per test -- no real Anthropic API call in this suite."""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

import alpha_squad.api.routers.league as league_router
from alpha_squad.api.app import app
from alpha_squad.api.deps import get_db
from alpha_squad.storage.db import init_db
from alpha_squad.strategy.contracts import ClaudeDraftDecision
from alpha_squad.strategy.provider import ClaudeInvalidResponseError, ClaudeUnavailableError


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def client(con):
    def override_get_db():
        yield con

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


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


def _patch_provider(monkeypatch, decision=None, error=None, model="fake-model"):
    class _FakeConstructedProvider:
        def __init__(self, settings):
            pass

        def review(self, context):
            if error is not None:
                raise error
            return decision, model

    monkeypatch.setattr(league_router, "AnthropicClaudeProvider", _FakeConstructedProvider)


class TestClaudeReviewEndpoint:
    def test_alpha_is_always_returned_and_matches_draft_endpoint(self, con, client, monkeypatch):
        """The `/draft/claude-review` and `/draft` endpoints must recommend the SAME player
        for the same inputs -- one Alpha engine, never a second decision path."""
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9
        )
        _patch_provider(monkeypatch, decision=decision)

        plain = client.post(
            "/league/target_league/draft",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        ).json()
        reviewed = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        ).json()

        assert reviewed["alpha"]["recommendation"] == plain["recommendation"]
        assert reviewed["alpha"]["expected_value"] == plain["expected_value"]

    def test_claude_agrees_with_alpha(self, con, client, monkeypatch):
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9
        )
        _patch_provider(monkeypatch, decision=decision, model="claude-opus-5")

        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["agrees_with_alpha"] is True
        assert body["decision"]["decision"] == "FOLLOW_ALPHA"
        assert body["model"] == "claude-opus-5"
        assert body["prompt_version"] == "draft_strategy_v1"
        assert body["alpha"]["decision_id"]  # a real decisions row was recorded

    def test_claude_overrides_alpha(self, con, client, monkeypatch):
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id="qb1",
            confidence=0.55,
            override_reason="qb1 fills a bigger roster need at this point in the draft",
            key_factors=["roster need", "small score gap"],
        )
        _patch_provider(monkeypatch, decision=decision)

        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        )
        body = r.json()
        assert body["status"] == "ok"
        assert body["agrees_with_alpha"] is False
        assert body["decision"]["selected_player_id"] == "qb1"
        assert body["decision"]["override_reason"]

    def test_claude_unavailable_still_returns_alpha_recommendation(self, con, client, monkeypatch):
        _seed_two_qbs(con)
        _patch_provider(monkeypatch, error=ClaudeUnavailableError("rate limited"))

        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "claude_unavailable"
        assert body["decision"] is None
        assert body["alpha"]["recommendation"] == "qb0"  # Alpha's own recommendation unaffected

    def test_claude_invalid_response_still_returns_alpha_recommendation(
        self, con, client, monkeypatch
    ):
        _seed_two_qbs(con)
        _patch_provider(monkeypatch, error=ClaudeInvalidResponseError("bad json"))

        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        )
        body = r.json()
        assert body["status"] == "invalid_response"
        assert body["decision"] is None
        assert body["alpha"]["recommendation"] == "qb0"

    def test_claude_selecting_a_player_outside_the_pool_is_rejected(self, con, client, monkeypatch):
        """Hard validation runs even through the API boundary -- a schema-valid response
        naming a player never shown to Claude must not reach the user as a usable decision."""
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="OVERRIDE_ALPHA",
            selected_player_id="not_a_real_candidate",
            confidence=0.9,
            override_reason="x",
        )
        _patch_provider(monkeypatch, decision=decision)

        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        )
        body = r.json()
        assert body["status"] == "validation_failed"
        assert body["decision"] is None
        assert body["alpha"]["recommendation"] == "qb0"

    def test_no_candidates_returns_422_same_as_draft_endpoint(self, con, client, monkeypatch):
        _patch_provider(monkeypatch, decision=None)
        r = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["nobody"]},
        )
        assert r.status_code == 422

    def test_unregistered_league_404s(self, client, monkeypatch):
        _patch_provider(monkeypatch, decision=None)
        r = client.post(
            "/league/not-a-real-league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["p1"]},
        )
        assert r.status_code == 404

    def test_context_fingerprint_is_present_and_stable_across_identical_requests(
        self, con, client, monkeypatch
    ):
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9
        )
        _patch_provider(monkeypatch, decision=decision)

        r1 = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        ).json()
        r2 = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        ).json()
        assert r1["context_fingerprint"] == r2["context_fingerprint"]

        r3 = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0"]},
        ).json()
        assert r3["context_fingerprint"] != r1["context_fingerprint"]

    def test_decisions_from_different_leagues_never_collide_or_contaminate(
        self, con, client, monkeypatch
    ):
        """Phase 8 of the 2026-09-05 pre-draft verification: two reviews from two DIFFERENT
        leagues must produce two distinct, independently-tagged rows in claude_decisions --
        never an overwrite, and never one league's row read back under the other's identity."""
        _seed_two_qbs(con)
        decision = ClaudeDraftDecision(
            decision="FOLLOW_ALPHA", selected_player_id="qb0", confidence=0.9
        )
        _patch_provider(monkeypatch, decision=decision)

        r1 = client.post(
            "/league/target_league/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"]},
        ).json()
        r2 = client.post(
            "/league/legacy_2qb_dynasty/draft/claude-review",
            json={"season": 2025, "available_player_ids": ["qb0", "qb1"], "ecr_type": "ro"},
        ).json()

        assert r1["claude_decision_id"] != r2["claude_decision_id"]
        assert r1["alpha"]["decision_id"] != r2["alpha"]["decision_id"]

        rows = con.execute(
            "SELECT claude_decision_id, league_id FROM claude_decisions "
            "WHERE claude_decision_id IN (?, ?)",
            [r1["claude_decision_id"], r2["claude_decision_id"]],
        ).fetchall()
        by_id = dict(rows)
        assert len(by_id) == 2  # two distinct rows, not one overwriting the other
        assert by_id[r1["claude_decision_id"]] == "target_league"
        assert by_id[r2["claude_decision_id"]] == "legacy_2qb_dynasty"
