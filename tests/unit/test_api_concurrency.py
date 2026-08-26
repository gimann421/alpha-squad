"""Regression test for two real concurrency bugs found running the actual app with Playwright
(not synthetic tests): concurrent requests each calling `duckdb.connect()` fresh raised a real
`BinderException: Unique file handle conflict`, and each running `init_db`'s migration DDL
raised a real `TransactionException: write-write conflict`. Fixed by opening one shared base
connection at app startup and deriving per-request connections via `.cursor()`
(api/app.py's lifespan, api/deps.py::get_db). This test exercises that real path end-to-end --
unlike every other API test, it does NOT override `get_db`, so it's the one place proving the
production connection-sharing code actually works under real concurrent load."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import duckdb
import pytest
from fastapi.testclient import TestClient

import alpha_squad.config.settings as settings_module
from alpha_squad.storage.db import init_db


@pytest.fixture
def real_app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "concurrency_test.duckdb"
    monkeypatch.setenv("ALPHA_SQUAD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALPHA_SQUAD_DB_PATH", str(db_path))
    monkeypatch.setattr(settings_module, "_settings", None)

    # Seed real schema + a few real players before the app's own lifespan opens its
    # connection, so the concurrent requests below have something real to read.
    seed_con = duckdb.connect(str(db_path))
    init_db(seed_con)
    for i in range(20):
        seed_con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, ?)",
            [f"p{i}", f"gsis{i}", f"Player {i}", "WR"],
        )
    seed_con.close()

    from alpha_squad.api.app import app

    with TestClient(app) as client:
        yield client

    monkeypatch.setattr(settings_module, "_settings", None)


class TestConcurrentRequestsDoNotRaceOnTheDatabaseConnection:
    def test_many_concurrent_requests_all_succeed(self, real_app_client):
        def hit(_i):
            return real_app_client.get("/players", params={"limit": 10})

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(hit, range(20)))

        statuses = [r.status_code for r in responses]
        assert all(s == 200 for s in statuses), f"expected all 200s, got {statuses}"
        assert all(len(r.json()) == 10 for r in responses)

    def test_concurrent_requests_across_different_endpoints_all_succeed(self, real_app_client):
        def hit(i):
            if i % 2 == 0:
                return real_app_client.get("/players")
            return real_app_client.get("/league")

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(hit, range(16)))

        statuses = [r.status_code for r in responses]
        assert all(s == 200 for s in statuses), f"expected all 200s, got {statuses}"
