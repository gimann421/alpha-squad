"""End-to-end FastAPI app against real, live-fetched data (get_db overridden to point at a
real tmp_path-isolated DuckDB the fixture actually ingests into, so requests exercise the
real SQL against real rows). Deselected by default; run with `make test-network`."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alpha_squad.api.app import app
from alpha_squad.api.deps import get_db
from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.models.uncertainty.run import run_uncertainty
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = list(range(2022, 2026))
TARGET_SEASON = 2025


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def client(settings):
    con = get_connection(settings)
    init_db(con)
    nflverse = NflverseSource(settings)
    dp = DynastyProcessSource(settings)

    for snap in [
        nflverse.fetch("players"),
        nflverse.fetch("draft_picks"),
        nflverse.fetch("combine"),
    ]:
        record_snapshot(con, snap)
    record_snapshot(con, dp.fetch("player_ids"))
    build_identity(con, settings)

    for season in SEASONS:
        for dataset in ("pbp", "stats_player_week", "snap_counts", "stats_team_week"):
            record_snapshot(con, nflverse.fetch(dataset, season=season))
    build_features(con, settings, SEASONS)
    record_snapshot(con, dp.fetch("fp_ecr_history"))
    build_market_snapshot(con, settings)
    run_uncertainty(con, TARGET_SEASON, TARGET_SEASON, min_train_season=2022)

    def override_get_db():
        yield con

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    con.close()


def test_rankings_returns_real_players_in_real_projected_order(client):
    r = client.get("/rankings", params={"season": TARGET_SEASON, "position": "QB", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    assert all(row["display_name"] for row in body)
    points = [row["point_prediction"] for row in body]
    assert points == sorted(points, reverse=True)


def test_player_detail_returns_a_real_identity_crosswalk(client):
    players = client.get("/players", params={"position": "QB", "limit": 1}).json()
    assert players
    detail = client.get(f"/players/{players[0]['player_id']}")
    assert detail.status_code == 200
    assert detail.json()["gsis_id"].startswith("00-")


def test_league_draft_endpoint_matches_the_real_recommend_draft_pick_function(client):
    rankings = client.get("/rankings", params={"season": TARGET_SEASON, "limit": 20}).json()
    available = [r["player_id"] for r in rankings]
    r = client.post(
        "/league/target_league/draft",
        json={"season": TARGET_SEASON, "available_player_ids": available, "roster_positions": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation"] in available
    assert body["reasons"]


def test_provenance_traces_a_real_ranking_back_to_its_prediction_id(client):
    row = client.get("/rankings", params={"season": TARGET_SEASON, "limit": 1}).json()[0]
    prov = client.get(f"/provenance/{row['prediction_id']}")
    assert prov.status_code == 200
    body = prov.json()
    assert body["found"] is True
    assert body["entity_type"] == "uncertainty_prediction"
    assert body["record"]["player_id"] == row["player_id"]
