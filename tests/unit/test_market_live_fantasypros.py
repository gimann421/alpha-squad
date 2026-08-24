"""Offline coverage for the live FantasyPros consensus-rankings capture
(market/consensus.py::build_live_fantasypros_snapshot, docs/DECISIONS.md D38). Mocks
httpx.get with the real response shape verified against the live API rather than the
network -- real reachability is covered separately by
tests/integration/test_sources_live.py::test_fantasypros_with_key_is_really_reachable."""

from __future__ import annotations

import json

import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.market.consensus import build_live_fantasypros_snapshot
from alpha_squad.sources.base import SourceBlockedError
from alpha_squad.storage.db import init_db
from tests.fixtures.httpx_fakes import FakeGetResponse, make_fake_get

FP_PLAYER_ID = 19788
CANONICAL_PLAYER_ID = "asq_test_chase"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        db_path=tmp_path / "data" / "x.duckdb",
        fantasypros_api_key="fake-key-for-test",
    )


@pytest.fixture
def con(settings):
    import duckdb

    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, '00-9999998')",
        [CANONICAL_PLAYER_ID],
    )
    connection.execute(
        "INSERT INTO player_id_map (id_type, id_value, player_id, source) "
        "VALUES ('fantasypros_id', ?, ?, 'test')",
        [str(FP_PLAYER_ID), CANONICAL_PLAYER_ID],
    )
    yield connection
    connection.close()


def _fake_get(body):
    def fake_get(url: str, **kwargs):
        return FakeGetResponse(200, body, json.dumps(body).encode())

    return fake_get


def _rankings_body(**player_overrides):
    player = {
        "player_id": FP_PLAYER_ID,
        "player_name": "Ja'Marr Chase",
        "player_position_id": "WR",
        "rank_ecr": 1,
        "rank_min": "1",
        "rank_max": "6",
    }
    player.update(player_overrides)
    return {
        "sport": "NFL",
        "type": "Draft",
        "position_id": "ALL",
        "scoring": "PPR",
        "players": [player],
    }


class TestBuildLiveFantasyprosSnapshot:
    def test_resolves_a_real_shaped_player_into_market_snapshot(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get(_rankings_body()))

        n = build_live_fantasypros_snapshot(con, settings)

        assert n == 1
        row = con.execute(
            "SELECT ecr_type, position, ecr_rank, ecr_best, ecr_worst, source "
            "FROM market_snapshot WHERE player_id = ?",
            [CANONICAL_PLAYER_ID],
        ).fetchone()
        assert row == ("draft_overall", "WR", 1.0, 1.0, 6.0, "fantasypros_live")

    def test_never_collides_with_a_dynastyprocess_row_for_the_same_player_date_ecr_type(
        self, con, settings, monkeypatch
    ):
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, source) "
            "VALUES (?, CURRENT_DATE, 'draft_overall', 'WR', 5.0, 'dynastyprocess')",
            [CANONICAL_PLAYER_ID],
        )
        monkeypatch.setattr(httpx, "get", _fake_get(_rankings_body()))

        build_live_fantasypros_snapshot(con, settings)

        rows = con.execute(
            "SELECT source, ecr_rank FROM market_snapshot WHERE player_id = ? ORDER BY source",
            [CANONICAL_PLAYER_ID],
        ).fetchall()
        assert rows == [("dynastyprocess", 5.0), ("fantasypros_live", 1.0)]

    def test_rerun_is_idempotent_not_a_duplicate_row(self, con, settings, monkeypatch):
        monkeypatch.setattr(httpx, "get", _fake_get(_rankings_body()))

        n1 = build_live_fantasypros_snapshot(con, settings)
        n2 = build_live_fantasypros_snapshot(con, settings)

        assert n1 == 1 and n2 == 1
        assert (
            con.execute(
                "SELECT count(*) FROM market_snapshot WHERE source = 'fantasypros_live'"
            ).fetchone()[0]
            == 1
        )

    def test_unmapped_fantasypros_player_id_is_silently_skipped_not_errored(
        self, con, settings, monkeypatch
    ):
        body = _rankings_body(player_id=99999999)  # no player_id_map row exists for this
        monkeypatch.setattr(httpx, "get", _fake_get(body))

        n = build_live_fantasypros_snapshot(con, settings)

        assert n == 0
        assert con.execute("SELECT count(*) FROM market_snapshot").fetchone()[0] == 0

    def test_policy_block_propagates_rather_than_silently_producing_zero_rows(
        self, con, settings, monkeypatch
    ):
        monkeypatch.setattr(
            httpx, "get", make_fake_get(raise_exc=httpx.ProxyError("403 Forbidden"))
        )
        with pytest.raises(SourceBlockedError):
            build_live_fantasypros_snapshot(con, settings)
