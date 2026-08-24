"""Offline coverage for CFBD college-usage ingestion
(features/college_production.py, docs/DECISIONS.md D38). Mocks httpx.get with the real
response shape verified against the live API rather than the network -- real reachability is
covered separately by
tests/integration/test_sources_live.py::test_cfbd_with_key_is_really_reachable."""

from __future__ import annotations

import json

import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.college_production import (
    build_college_usage,
    seasons_needed_for_rookies,
)
from alpha_squad.sources.base import SourceBlockedError
from alpha_squad.storage.db import init_db
from tests.fixtures.httpx_fakes import make_fake_get

CFBD_ID = "4431611"
CANONICAL_PLAYER_ID = "asq_test_qb"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb", cfbd_api_key="fake-key"
    )


@pytest.fixture
def con(settings):
    import duckdb

    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, '00-9999997')",
        [CANONICAL_PLAYER_ID],
    )
    connection.execute(
        "INSERT INTO player_id_map (id_type, id_value, player_id, source) "
        "VALUES ('espn_id', ?, ?, 'test')",
        [CFBD_ID, CANONICAL_PLAYER_ID],
    )
    yield connection
    connection.close()


def _usage_entry(**overrides):
    entry = {
        "id": CFBD_ID,
        "name": "Test QB",
        "position": "QB",
        "season": 2023,
        "team": "USC",
        "usage": {"overall": 0.624, "pass": 0.915, "rush": 0.222},
    }
    entry.update(overrides)
    return entry


def _fake_get(body):
    def fake_get(url: str, **kwargs):
        from tests.fixtures.httpx_fakes import FakeGetResponse

        return FakeGetResponse(200, body, json.dumps(body).encode())

    return fake_get


class TestBuildCollegeUsage:
    def test_resolves_a_real_shaped_entry_via_the_espn_id_bridge(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get([_usage_entry()]))

        n = build_college_usage(con, settings, [2023])

        assert n == 1
        row = con.execute(
            "SELECT season, usage_overall, usage_pass, usage_rush FROM college_usage "
            "WHERE player_id = ?",
            [CANONICAL_PLAYER_ID],
        ).fetchone()
        assert row == (2023, 0.624, 0.915, 0.222)

    def test_loops_over_every_requested_season_as_a_separate_fetch(
        self, con, settings, monkeypatch
    ):
        calls = []

        def fake_get(url, **kwargs):
            from tests.fixtures.httpx_fakes import FakeGetResponse

            year = kwargs["params"]["year"]
            calls.append(year)
            body = [_usage_entry(season=year)]
            return FakeGetResponse(200, body, json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

        n = build_college_usage(con, settings, [2022, 2023])

        assert calls == [2022, 2023]
        assert n == 2
        seasons = {
            r[0]
            for r in con.execute(
                "SELECT season FROM college_usage WHERE player_id = ?", [CANONICAL_PLAYER_ID]
            ).fetchall()
        }
        assert seasons == {2022, 2023}

    def test_unmapped_cfbd_id_is_silently_skipped_not_errored(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get([_usage_entry(id="99999999")]))

        n = build_college_usage(con, settings, [2023])

        assert n == 0
        assert con.execute("SELECT count(*) FROM college_usage").fetchone()[0] == 0

    def test_rerun_is_idempotent_not_a_duplicate_row(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get([_usage_entry()]))

        n1 = build_college_usage(con, settings, [2023])
        n2 = build_college_usage(con, settings, [2023])

        assert n1 == 1 and n2 == 1
        assert con.execute("SELECT count(*) FROM college_usage").fetchone()[0] == 1

    def test_policy_block_propagates_rather_than_silently_producing_zero_rows(
        self, con, settings, monkeypatch
    ):
        monkeypatch.setattr(
            httpx, "get", make_fake_get(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        with pytest.raises(SourceBlockedError):
            build_college_usage(con, settings, [2023])


class TestSeasonsNeededForRookies:
    def test_returns_distinct_final_college_seasons_for_skill_position_rookies(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('a', 'g_a', 'QB', 2024)"
        )
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('b', 'g_b', 'WR', 2023)"
        )
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('c', 'g_c', 'RB', 2024)"
        )  # same season as 'a' -- must be deduped
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('d', 'g_d', 'K', 2024)"
        )  # non-skill position -- must be excluded
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('e', 'g_e', 'QB', NULL)"
        )  # not a rookie -- must be excluded

        seasons = seasons_needed_for_rookies(con)

        assert seasons == [2022, 2023]

    def test_seasons_before_cfbd_coverage_are_floored_out(self, con):
        """Regression (D39): `players` spans nflverse's full history, so an unfloored version
        issued ~40 real CFBD requests for pre-2013 seasons that all return an empty list."""
        from alpha_squad.features.college_production import CFBD_USAGE_FIRST_SEASON

        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('old', 'g_old', 'RB', 1974)"
        )
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
            "VALUES ('new', 'g_new', 'RB', 2024)"
        )

        seasons = seasons_needed_for_rookies(con)

        assert 1973 not in seasons
        assert all(s >= CFBD_USAGE_FIRST_SEASON for s in seasons)
        assert 2023 in seasons
