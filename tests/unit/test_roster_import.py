"""Offline coverage for league/roster_import.py (real per-team Sleeper roster fetch). Mocks
httpx.get with realistic Sleeper `/league/{id}/rosters` and `/league/{id}/users` bodies, shaped
from a real live fetch against a real 10-team league (`boys_of_fall`) during development, not
guessed -- see the module docstring."""

from __future__ import annotations

import json

import duckdb
import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster_import import (
    fetch_sleeper_rosters,
    resolve_roster_positions,
    roster_positions_for,
)
from alpha_squad.storage.db import init_db

LEAGUE_ID = "1234567890"

ROSTERS = [
    {
        "roster_id": 1,
        "owner_id": "user_1",
        "players": ["6813", "9999999", "6819"],  # 9999999 has no crosswalk match
        "starters": ["6813", "6819"],
        "settings": {"wins": 0, "losses": 0},
    },
    {
        "roster_id": 2,
        "owner_id": "user_2",
        "players": [],
        "starters": [],
        "settings": {"wins": 0, "losses": 0},
    },
]

USERS = [
    {
        "user_id": "user_1",
        "display_name": "gimann",
        "metadata": {"team_name": "The Dynasty"},
    },
    {
        "user_id": "user_2",
        "display_name": "rival_gm",
        "metadata": {},
    },
]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
        "('asq_qb1', '00-01', 'Real QB', 'QB'), ('asq_wr1', '00-02', 'Real WR', 'WR')"
    )
    connection.execute(
        "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
        "('sleeper_id', '6813', 'asq_qb1', 'test'), ('sleeper_id', '6819', 'asq_wr1', 'test')"
    )
    yield connection
    connection.close()


def _fake_get_by_url():
    def fake_get(url: str, **kwargs):
        if url.endswith("/rosters"):
            body = ROSTERS
        elif url.endswith("/users"):
            body = USERS
        else:
            raise AssertionError(f"unexpected URL in test: {url}")
        return _FakeResponse(200, body)

    return fake_get


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = json.dumps(body).encode()

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


class TestFetchSleeperRosters:
    def test_bridges_real_players_and_flags_unmapped_ones(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())

        teams = fetch_sleeper_rosters(con, settings, LEAGUE_ID)

        assert len(teams) == 2
        team1 = teams[0]
        assert team1.roster_id == 1
        assert team1.owner_display_name == "gimann"
        assert team1.team_name == "The Dynasty"
        mapped_ids = {p.player_id for p in team1.players}
        assert mapped_ids == {"asq_qb1", "asq_wr1"}
        assert team1.unmapped_sleeper_ids == ["9999999"]

    def test_empty_roster_maps_to_no_players_not_an_error(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())

        teams = fetch_sleeper_rosters(con, settings, LEAGUE_ID)

        team2 = next(t for t in teams if t.roster_id == 2)
        assert team2.players == []
        assert team2.unmapped_sleeper_ids == []

    def test_records_real_snapshots_for_provenance(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())

        fetch_sleeper_rosters(con, settings, LEAGUE_ID)

        n = con.execute(
            "SELECT count(*) FROM snapshot_registry WHERE source = 'sleeper' "
            "AND dataset IN ('league_rosters', 'league_users')"
        ).fetchone()[0]
        assert n == 2


class TestRosterPositionsFor:
    def test_returns_real_positions_for_a_known_roster(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        teams = fetch_sleeper_rosters(con, settings, LEAGUE_ID)

        positions = roster_positions_for(teams, 1)
        assert sorted(positions) == ["QB", "WR"]

    def test_unknown_roster_id_raises_rather_than_returning_empty(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        teams = fetch_sleeper_rosters(con, settings, LEAGUE_ID)

        with pytest.raises(RuntimeError, match="no roster_id 999"):
            roster_positions_for(teams, 999)


def _sleeper_league() -> LeagueContext:
    return LeagueContext(
        league_id=LEAGUE_ID,
        format="dynasty",
        teams=2,
        source="sleeper",
        sleeper_league_id=LEAGUE_ID,
    )


def _yaml_league() -> LeagueContext:
    return LeagueContext(league_id="target_league", format="dynasty", teams=10)


class TestResolveRosterPositions:
    def test_no_roster_id_returns_the_fallback_unchanged(self, con, settings):
        positions = resolve_roster_positions(
            con, settings, _sleeper_league(), roster_id=None, fallback=["QB", "RB"]
        )
        assert positions == ["QB", "RB"]

    def test_no_roster_id_and_no_fallback_is_an_empty_list_not_an_error(self, con, settings):
        assert resolve_roster_positions(con, settings, _sleeper_league()) == []

    def test_roster_id_on_a_sleeper_league_returns_real_positions_ignoring_fallback(
        self, con, settings, monkeypatch
    ):
        monkeypatch.setattr(httpx, "get", _fake_get_by_url())
        positions = resolve_roster_positions(
            con, settings, _sleeper_league(), roster_id=1, fallback=["K"]
        )
        assert sorted(positions) == ["QB", "WR"]

    def test_roster_id_on_a_yaml_league_raises_rather_than_silently_falling_back(
        self, con, settings
    ):
        with pytest.raises(RuntimeError, match="no real per-team roster source"):
            resolve_roster_positions(con, settings, _yaml_league(), roster_id=1)
