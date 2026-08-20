"""Unit tests for the FastAPI application against synthetic data (get_db overridden with an
in-memory DuckDB connection). The literal Gate 8 test lives here: `/rankings` and `/edge`
must return exactly what is stored in uncertainty_predictions/edge_snapshot, proving there is
no parallel scoring/ranking logic in the API layer."""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from alpha_squad.api.app import app
from alpha_squad.api.deps import get_db
from alpha_squad.storage.db import init_db


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


def _seed_player(con, player_id, display_name, position, gsis_id=None):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, ?)",
        [player_id, gsis_id or f"gsis_{player_id}", display_name, position],
    )


class TestRoot:
    def test_root_returns_service_metadata(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["service"] == "alpha-squad-api"


class TestPlayers:
    def test_get_player_404s_for_unknown_id(self, client):
        r = client.get("/players/nope")
        assert r.status_code == 404

    def test_get_player_returns_real_stored_fields_and_id_map(self, con, client):
        _seed_player(con, "p1", "Test Player", "WR")
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES ('pfr_id', 'TestP01', 'p1', 'test')"
        )
        r = client.get("/players/p1")
        assert r.status_code == 200
        body = r.json()
        assert body["display_name"] == "Test Player"
        assert body["id_map"] == {"pfr_id": "TestP01"}

    def test_list_players_filters_by_position_and_query(self, con, client):
        _seed_player(con, "p1", "Alpha Wideout", "WR")
        _seed_player(con, "p2", "Beta Runner", "RB")
        r = client.get("/players", params={"position": "WR"})
        assert [p["player_id"] for p in r.json()] == ["p1"]
        r2 = client.get("/players", params={"q": "beta"})
        assert [p["player_id"] for p in r2.json()] == ["p2"]


class TestRankingsAreADirectProjection:
    """The literal Gate 8 test: the API must not re-derive or re-rank -- it must return
    exactly the stored uncertainty_predictions row."""

    def test_rankings_returns_the_exact_stored_point_prediction(self, con, client):
        _seed_player(con, "p1", "Exact Player", "WR")
        con.execute(
            """
            INSERT INTO uncertainty_predictions
                (prediction_id, player_id, season, position, model_version, feature_version,
                 point_prediction, p10, p90, top24_prob, confidence, calibration_season, predicted_at)
            VALUES ('pred1', 'p1', 2025, 'WR', 'uncertainty_catboost_v1', 'fv1', 123.456, 90.0, 160.0, 0.42, 0.81, 2024, current_timestamp)
            """
        )
        r = client.get("/rankings", params={"season": 2025})
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["point_prediction"] == pytest.approx(123.456)
        assert body[0]["top24_prob"] == pytest.approx(0.42)
        assert body[0]["confidence"] == pytest.approx(0.81)
        assert body[0]["display_name"] == "Exact Player"

    def test_rankings_orders_by_the_stored_point_prediction_descending(self, con, client):
        for pid, pts in [("p1", 100.0), ("p2", 300.0), ("p3", 200.0)]:
            _seed_player(con, pid, pid, "RB")
            con.execute(
                "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
                "model_version, feature_version, point_prediction, calibration_season, predicted_at) "
                "VALUES (?, ?, 2025, 'RB', 'uncertainty_catboost_v1', 'fv1', ?, 2024, current_timestamp)",
                [f"pred_{pid}", pid, pts],
            )
        r = client.get("/rankings", params={"season": 2025})
        assert [row["player_id"] for row in r.json()] == ["p2", "p3", "p1"]


class TestEdgeIsADirectProjection:
    def test_edge_returns_the_exact_stored_action_and_reasons(self, con, client):
        _seed_player(con, "p1", "Edge Player", "WR")
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, projected_points_edge, evidence_score, confidence,
                 action, reasons_json, built_at)
            VALUES ('e1', 'p1', 2025, 'WR', 'rsf', 'edge_v1', 5, 50, 45, 30.0, 0.5, 0.8, 'BUY', '["real reason"]', current_timestamp)
            """
        )
        r = client.get("/edge", params={"season": 2025})
        assert r.status_code == 200
        body = r.json()
        assert body[0]["action"] == "BUY"
        assert body[0]["reasons"] == ["real reason"]
        assert body[0]["rank_edge"] == 45

    def test_edge_filters_by_action(self, con, client):
        for pid, action in [("p1", "BUY"), ("p2", "WATCH")]:
            _seed_player(con, pid, pid, "WR")
            con.execute(
                "INSERT INTO edge_snapshot (edge_id, player_id, season, position, ecr_type, "
                "model_version, model_rank, market_rank, rank_edge, evidence_score, action, reasons_json, built_at) "
                "VALUES (?, ?, 2025, 'WR', 'rsf', 'edge_v1', 1, 2, 1, 0.5, ?, '[]', current_timestamp)",
                [f"e_{pid}", pid, action],
            )
        r = client.get("/edge", params={"season": 2025, "action": "BUY"})
        assert [row["player_id"] for row in r.json()] == ["p1"]


class TestEvidence:
    def test_evidence_filters_by_player(self, con, client):
        _seed_player(con, "p1", "P1", "WR")
        con.execute(
            "INSERT INTO evidence_events (event_id, player_id, season, week, event_date, "
            "captured_at, event_type, source, strength_label, strength, direction, "
            "structured_impact_json, summary) VALUES ('ev1', 'p1', 2025, 5, '2025-10-01', "
            "current_timestamp, 'depth_chart_promotion', 'test', 'STRONG', 0.9, 1, '{}', 'promo')"
        )
        r = client.get("/evidence", params={"player_id": "p1"})
        assert r.status_code == 200
        assert r.json()[0]["event_type"] == "depth_chart_promotion"


class TestLeague:
    def test_unknown_league_id_returns_404_not_a_fabricated_answer(self, client):
        r = client.get("/league/not-a-real-league/context")
        assert r.status_code == 404

    def test_get_context_returns_the_real_target_league_config(self, client):
        r = client.get("/league/target_league/context")
        assert r.status_code == 200
        body = r.json()
        assert body["teams"] == 10
        assert body["lineup"] == {"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2}

    def test_roster_need_endpoint(self, client):
        r = client.get("/league/target_league/roster", params={"roster_positions": "QB"})
        assert r.status_code == 200
        assert r.json()["need"]["QB"] > 0  # only 1 of 2 required QB slots filled

    def test_draft_endpoint_calls_the_real_recommend_draft_pick_and_persists_a_decision(
        self, con, client
    ):
        _seed_player(con, "p1", "Draft Target", "QB")
        con.execute(
            "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
            "model_version, feature_version, point_prediction, calibration_season, predicted_at) "
            "VALUES ('pred1', 'p1', 2025, 'QB', 'uncertainty_catboost_v1', 'fv1', 300.0, 2024, current_timestamp)"
        )
        r = client.post(
            "/league/target_league/draft",
            json={"season": 2025, "roster_positions": [], "available_player_ids": ["p1"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["recommendation"] == "p1"
        assert body["reasons"]

        stored = con.execute(
            "SELECT recommendation FROM decisions WHERE decision_id = ?", [body["decision_id"]]
        ).fetchone()
        assert stored[0] == "p1"

    def test_draft_endpoint_422s_when_no_evaluable_candidates(self, client):
        r = client.post(
            "/league/target_league/draft",
            json={"season": 2025, "available_player_ids": ["nobody"]},
        )
        assert r.status_code == 422


class TestProvenance:
    def test_unknown_id_reports_not_found_rather_than_erroring(self, client):
        r = client.get("/provenance/totally-made-up-id")
        assert r.status_code == 200
        assert r.json()["found"] is False

    def test_finds_a_real_stored_edge_snapshot_row(self, con, client):
        _seed_player(con, "p1", "P1", "WR")
        con.execute(
            "INSERT INTO edge_snapshot (edge_id, player_id, season, position, ecr_type, "
            "model_version, model_rank, market_rank, rank_edge, evidence_score, action, reasons_json, built_at) "
            "VALUES ('edge123', 'p1', 2025, 'WR', 'rsf', 'edge_v1', 1, 2, 1, 0.5, 'BUY', '[]', current_timestamp)"
        )
        r = client.get("/provenance/edge123")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] is True
        assert body["entity_type"] == "edge_snapshot"
        assert body["record"]["action"] == "BUY"


class TestHealth:
    def test_source_health_returns_only_the_latest_check_per_source_dataset(self, con, client):
        con.execute(
            "INSERT INTO source_health_log (checked_at, source, dataset, status, detail) "
            "VALUES ('2026-01-01', 'nflverse', 'players', 'ERROR', 'old')"
        )
        con.execute(
            "INSERT INTO source_health_log (checked_at, source, dataset, status, detail) "
            "VALUES ('2026-01-02', 'nflverse', 'players', 'AVAILABLE', 'new')"
        )
        r = client.get("/health/sources")
        assert r.status_code == 200
        rows = [
            row for row in r.json() if row["source"] == "nflverse" and row["dataset"] == "players"
        ]
        assert len(rows) == 1
        assert rows[0]["status"] == "AVAILABLE"
