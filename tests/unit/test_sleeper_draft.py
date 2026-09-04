"""Offline coverage for league/sleeper_draft.py (real Sleeper draft-pick synchronization,
2026-09-03 product-gap PART 1). Mocks httpx.get with realistic Sleeper `/draft/{id}`,
`/draft/{id}/picks`, and `/league/{id}/drafts` bodies, shaped from the documented public API
(https://docs.sleeper.com)."""

from __future__ import annotations

import json

import duckdb
import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.sleeper_draft import (
    _pick_order,
    compute_turn_info,
    fetch_sleeper_draft_id,
    fetch_sleeper_draft_state,
)
from alpha_squad.sources.base import SourceBlockedError
from alpha_squad.storage.db import init_db

LEAGUE_ID = "1234567890"
DRAFT_ID = "555000111"

# 4-team snake draft, 3 rounds: order should be 1,2,3,4 | 4,3,2,1 | 1,2,3,4
DRAFT_OBJECT = {
    "draft_id": DRAFT_ID,
    "league_id": LEAGUE_ID,
    "type": "snake",
    "status": "drafting",
    "settings": {"teams": 4, "rounds": 3},
    "slot_to_roster_id": {"1": 10, "2": 20, "3": 30, "4": 40},
}

# Picks 1-3 made: slot1->roster10 took player A, slot2->roster20 took player B (unmapped),
# slot3->roster30 took player C. Pick 4 (slot4/roster40) not yet made.
DRAFT_PICKS = [
    {"pick_no": 1, "round": 1, "roster_id": 10, "draft_slot": 1, "player_id": "1001"},
    {"pick_no": 2, "round": 1, "roster_id": 20, "draft_slot": 2, "player_id": "9999999"},
    {"pick_no": 3, "round": 1, "roster_id": 30, "draft_slot": 3, "player_id": "1003"},
]

LEAGUE_DRAFTS = [{"draft_id": DRAFT_ID, "status": "drafting"}]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
        "('asq_p1', '00-01', 'Player A', 'RB'), ('asq_p3', '00-03', 'Player C', 'WR')"
    )
    connection.execute(
        "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
        "('sleeper_id', '1001', 'asq_p1', 'test'), ('sleeper_id', '1003', 'asq_p3', 'test')"
    )
    yield connection
    connection.close()


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = json.dumps(body).encode()

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


def _fake_get_by_url():
    def fake_get(url: str, **kwargs):
        if url.endswith("/picks"):
            return _FakeResponse(200, DRAFT_PICKS)
        if url.endswith("/drafts"):
            return _FakeResponse(200, LEAGUE_DRAFTS)
        if f"/draft/{DRAFT_ID}" in url:
            return _FakeResponse(200, DRAFT_OBJECT)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_get


class TestPickOrder:
    def test_snake_order_alternates_direction_each_round(self):
        order = _pick_order(4, 3, "snake", {1: 10, 2: 20, 3: 30, 4: 40})
        assert order == [10, 20, 30, 40, 40, 30, 20, 10, 10, 20, 30, 40]

    def test_linear_order_repeats_each_round(self):
        order = _pick_order(3, 2, "linear", {1: 10, 2: 20, 3: 30})
        assert order == [10, 20, 30, 10, 20, 30]

    def test_unassigned_slot_yields_none_not_a_fabricated_roster_id(self):
        order = _pick_order(2, 1, "snake", {1: 10})
        assert order == [10, None]


class TestFetchSleeperDraftId:
    def test_returns_most_recent_draft_id(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        assert fetch_sleeper_draft_id(None, settings, LEAGUE_ID) == DRAFT_ID

    def test_no_drafts_returns_none_not_an_error(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", lambda url, **kw: _FakeResponse(200, []))
        assert fetch_sleeper_draft_id(None, settings, LEAGUE_ID) is None


class TestFetchSleeperDraftState:
    def test_bridges_picks_and_flags_unmapped(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())

        state = fetch_sleeper_draft_state(con, settings, DRAFT_ID)

        assert state.status == "drafting"
        assert state.draft_type == "snake"
        assert state.teams == 4
        assert state.rounds == 3
        assert len(state.picks) == 3
        assert state.drafted_player_ids == ["asq_p1", "asq_p3"]
        assert state.unmapped_sleeper_ids == ["9999999"]
        assert state.player_ids_for_roster(10) == ["asq_p1"]
        assert state.player_ids_for_roster(30) == ["asq_p3"]

    def test_duplicate_pick_no_in_raw_response_is_collapsed_not_double_counted(
        self, con, settings, monkeypatch
    ):
        duplicated = [*DRAFT_PICKS, dict(DRAFT_PICKS[0])]  # same pick_no=1 twice
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **kw: (
                _FakeResponse(200, duplicated)
                if url.endswith("/picks")
                else _FakeResponse(200, DRAFT_OBJECT)
            ),
        )

        state = fetch_sleeper_draft_state(con, settings, DRAFT_ID)
        assert len(state.picks) == 3, "a duplicated pick_no must not inflate the pick count"

    def test_blocked_egress_raises_source_blocked_error_not_a_fabricated_board(
        self, settings, monkeypatch
    ):
        def raise_blocked(url, **kw):
            raise httpx.ProxyError("blocked")

        monkeypatch.setattr(httpx, "get", raise_blocked)
        with pytest.raises(SourceBlockedError):
            fetch_sleeper_draft_state(None, settings, DRAFT_ID)


class TestComputeTurnInfo:
    def test_current_pick_and_on_the_clock(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        state = fetch_sleeper_draft_state(con, settings, DRAFT_ID)

        turn = compute_turn_info(state, roster_id=40)
        assert turn.current_pick_overall == 4
        assert turn.on_the_clock_roster_id == 40
        assert turn.is_users_turn is True
        # roster 40's NEXT pick after #4 is #5 (round 2, snake reversal keeps slot4 first)
        assert turn.next_pick_overall_for_roster == 5

    def test_not_users_turn_and_next_pick_is_a_future_turn(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        state = fetch_sleeper_draft_state(con, settings, DRAFT_ID)

        turn = compute_turn_info(state, roster_id=10)
        assert turn.current_pick_overall == 4
        assert turn.is_users_turn is False
        # roster 10 (slot 1) picks again at overall #8 (round 2 reversal) and #9 (round 3)
        assert turn.next_pick_overall_for_roster == 8

    def test_unknown_teams_or_rounds_degrades_to_none_not_a_guess(self):
        from alpha_squad.league.sleeper_draft import SleeperDraftState

        state = SleeperDraftState(
            draft_id="x", status="pre_draft", draft_type="snake", teams=0, rounds=0
        )
        turn = compute_turn_info(state, roster_id=10)
        assert turn.current_pick_overall is None
        assert turn.on_the_clock_roster_id is None
        assert turn.next_pick_overall_for_roster is None
        assert turn.is_users_turn is None

    def test_draft_complete_has_no_current_pick(self, con, settings, monkeypatch):
        all_picks_made = [
            {
                "pick_no": n,
                "round": (n - 1) // 4 + 1,
                "roster_id": r,
                "draft_slot": s,
                "player_id": str(1000 + n),
            }
            for n, (s, r) in enumerate([(1, 10), (2, 20), (3, 30), (4, 40)] * 3, start=1)
        ]
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **kw: (
                _FakeResponse(200, all_picks_made)
                if url.endswith("/picks")
                else _FakeResponse(200, DRAFT_OBJECT)
            ),
        )
        state = fetch_sleeper_draft_state(con, settings, DRAFT_ID)
        turn = compute_turn_info(state, roster_id=10)
        assert turn.current_pick_overall is None
        assert turn.on_the_clock_roster_id is None
