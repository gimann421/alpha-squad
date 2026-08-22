"""Offline coverage for the Sleeper-hydrated LeagueContext mapping
(league/sleeper_context.py, docs/DECISIONS.md D33). Mocks httpx.get with a realistic Sleeper
`/league/{id}` response body, built from the documented public API shape
(https://docs.sleeper.com) -- real reachability and the exact real shape are covered
separately by tests/integration/test_sleeper_league_context_live.py once a real league id is
available to verify against."""

from __future__ import annotations

import json

import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.sleeper_context import load_sleeper_league_context
from tests.fixtures.httpx_fakes import FakeGetResponse

DYNASTY_SUPERFLEX_LEAGUE = {
    "league_id": "999888777666555444",
    "name": "The Dynasty Dynasty",
    "season": "2026",
    "total_rosters": 12,
    "roster_positions": [
        "QB",
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "TE",
        "FLEX",
        "FLEX",
        "SUPER_FLEX",
        "BN",
        "BN",
        "BN",
        "BN",
        "BN",
        "BN",
        "BN",
        "BN",
        "TAXI",
        "TAXI",
        "IR",
    ],
    "scoring_settings": {"rec": 1.0, "pass_td": 4, "rush_td": 6},
    "settings": {"type": 2, "waiver_budget": 100},
}

REDRAFT_STANDARD_LEAGUE = {
    "league_id": "111222333444555666",
    "name": "Redraft Standard",
    "season": "2026",
    "total_rosters": 10,
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN"],
    "scoring_settings": {"rec": 0.0},
    "settings": {"type": 0, "waiver_budget": 0},
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


def _fake_get(body: dict):
    def fake_get(url: str, **kwargs):
        return FakeGetResponse(200, body, json.dumps(body).encode())

    return fake_get


class TestLoadSleeperLeagueContext:
    def test_dynasty_superflex_league_maps_correctly(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get(DYNASTY_SUPERFLEX_LEAGUE))

        league = load_sleeper_league_context(None, settings, "999888777666555444")

        assert league.league_id == "999888777666555444"
        assert league.format == "dynasty"
        assert league.teams == 12
        assert league.is_ppr
        assert league.scoring["ppr_value"] == pytest.approx(1.0)
        assert league.dedicated_slots() == {"QB": 2, "RB": 2, "WR": 2, "TE": 1}
        assert league.lineup["SUPER_FLEX"] == 1
        assert league.lineup["FLEX"] == 2
        assert league.bench_size == 8
        assert league.roster["ir_slots"] == 1
        assert league.roster["taxi_slots"] == 2
        assert league.faab_budget == 100
        assert league.source == "sleeper"

    def test_redraft_standard_league_maps_correctly(self, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get(REDRAFT_STANDARD_LEAGUE))

        league = load_sleeper_league_context(None, settings, "111222333444555666")

        assert league.format == "redraft"
        assert league.teams == 10
        assert not league.is_ppr
        assert league.faab_budget == 0
        assert league.dedicated_slots() == {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
        assert league.flex_slots() == {"FLEX": 1}
        assert league.bench_size == 3

    def test_a_flex_slot_name_not_in_flex_eligibility_is_flagged_not_silently_dropped(
        self, settings, monkeypatch
    ):
        """SUPER_FLEX is registered (context.py's FLEX_ELIGIBILITY); this proves the safety
        net for a real Sleeper flex-variant name that *isn't* registered yet -- it must still
        show up somewhere (as its own dedicated-looking slot), not vanish."""
        body = {
            **REDRAFT_STANDARD_LEAGUE,
            "league_id": "1",
            "roster_positions": ["QB", "RB", "WR", "REC_FLEX", "BN"],
        }
        monkeypatch.setattr(httpx, "get", _fake_get(body))

        league = load_sleeper_league_context(None, settings, "1")

        assert "REC_FLEX" in league.unrecognized_flex_slots
        assert league.lineup.get("REC_FLEX") == 1, (
            "an unrecognized slot must still be counted, not dropped"
        )

    def test_league_id_falls_back_to_the_requested_sleeper_id_if_missing_from_the_response(
        self, settings, monkeypatch
    ):
        body = {k: v for k, v in REDRAFT_STANDARD_LEAGUE.items() if k != "league_id"}
        monkeypatch.setattr(httpx, "get", _fake_get(body))

        league = load_sleeper_league_context(None, settings, "111222333444555666")
        assert league.league_id == "111222333444555666"
