"""Offline coverage for the Sleeper trending-adds/drops evidence detector
(evidence/sleeper_trending.py, docs/DECISIONS.md D31/D32). Mocks httpx.get with the exact
real response shape verified against the live API (a list of {"count": int, "player_id": str})
rather than the network -- real reachability is covered separately by
tests/integration/test_sleeper_trending_live.py."""

from __future__ import annotations

import json

import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.evidence.sleeper_trending import detect_sleeper_trending
from alpha_squad.sources.base import SourceBlockedError
from alpha_squad.storage.db import init_db
from tests.fixtures.httpx_fakes import FakeGetResponse, make_fake_get

SLEEPER_PLAYER_ID = "10218"
CANONICAL_PLAYER_ID = "asq_test_trending"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con(settings):
    import duckdb

    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, '00-9999999')", [CANONICAL_PLAYER_ID]
    )
    connection.execute(
        "INSERT INTO player_id_map (id_type, id_value, player_id, source) "
        "VALUES ('sleeper_id', ?, ?, 'test')",
        [SLEEPER_PLAYER_ID, CANONICAL_PLAYER_ID],
    )
    yield connection
    connection.close()


def _fake_get_sequence(adds_body, drops_body):
    """detect_sleeper_trending fetches trending_adds then trending_drops, in that order, and
    reads the *snapshot file on disk* (not the response's .json() directly) -- so `content`
    must be the real JSON-encoded bytes, matching what sleeper.py's fetch() actually writes."""
    responses = iter(
        [
            FakeGetResponse(200, adds_body, json.dumps(adds_body).encode()),
            FakeGetResponse(200, drops_body, json.dumps(drops_body).encode()),
        ]
    )

    def fake_get(url: str, **kwargs):
        return next(responses)

    return fake_get


class TestDetectSleeperTrending:
    def test_resolves_a_real_shaped_add_and_drop_into_weak_evidence_events(
        self, con, settings, monkeypatch
    ):
        adds = [{"count": 5000, "player_id": SLEEPER_PLAYER_ID}]
        drops: list[dict] = []
        monkeypatch.setattr(httpx, "get", _fake_get_sequence(adds, drops))

        n = detect_sleeper_trending(con, settings, season=2026, week=1)

        assert n == 1
        row = con.execute(
            "SELECT event_type, strength_label, strength, direction, source "
            "FROM evidence_events WHERE player_id = ?",
            [CANONICAL_PLAYER_ID],
        ).fetchone()
        assert row == ("social_media_buzz", "WEAK", pytest.approx(0.2), 1, "sleeper_trending_adds")

    def test_a_drop_is_recorded_with_negative_direction(self, con, settings, monkeypatch):
        adds: list[dict] = []
        drops = [{"count": 3000, "player_id": SLEEPER_PLAYER_ID}]
        monkeypatch.setattr(httpx, "get", _fake_get_sequence(adds, drops))

        detect_sleeper_trending(con, settings, season=2026, week=1)

        direction = con.execute(
            "SELECT direction FROM evidence_events WHERE player_id = ?", [CANONICAL_PLAYER_ID]
        ).fetchone()[0]
        assert direction == -1

    def test_unmapped_sleeper_player_id_is_silently_skipped_not_errored(
        self, con, settings, monkeypatch
    ):
        adds = [{"count": 1000, "player_id": "99999999"}]  # no player_id_map row exists for this
        monkeypatch.setattr(httpx, "get", _fake_get_sequence(adds, []))

        n = detect_sleeper_trending(con, settings, season=2026, week=1)

        assert n == 0
        assert con.execute("SELECT count(*) FROM evidence_events").fetchone()[0] == 0

    def test_feeds_evidence_score_for_action_like_any_other_event(self, con, settings, monkeypatch):
        """No special-casing needed downstream -- this is the whole point of reusing
        record_event()/the existing taxonomy rather than a parallel evidence path."""
        from alpha_squad.evidence.prior_update import evidence_score_for_action

        adds = [{"count": 5000, "player_id": SLEEPER_PLAYER_ID}]
        monkeypatch.setattr(httpx, "get", _fake_get_sequence(adds, []))
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
            "VALUES ('2026_01_AAA_BBB', 2026, 1, 'REG', '2026-09-10', 'AAA', 'BBB')"
        )

        detect_sleeper_trending(con, settings, season=2026, week=1)

        score = evidence_score_for_action(con, CANONICAL_PLAYER_ID, 2026, action_sign=1)
        assert score > 0.5

    def test_policy_block_propagates_rather_than_silently_producing_zero_events(
        self, con, settings, monkeypatch
    ):
        monkeypatch.setattr(
            httpx, "get", make_fake_get(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        with pytest.raises(SourceBlockedError):
            detect_sleeper_trending(con, settings, season=2026, week=1)
