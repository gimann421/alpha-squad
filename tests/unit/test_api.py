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


class TestPlayerDetail:
    """D53: distinguishes universal player value from league-specific value, per
    PRODUCT_SPEC.md's Application section -- no new scoring, just joining real tables/
    already-tested M6-M10 functions per player."""

    def test_404s_for_unknown_player(self, client):
        r = client.get("/players/nope/detail", params={"season": 2025})
        assert r.status_code == 404

    def test_universal_value_without_a_league(self, con, client):
        _seed_player(con, "p1", "Full Detail Player", "WR")
        con.execute(
            "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
            "model_version, feature_version, point_prediction, p10, p90, confidence, top24_prob, "
            "calibration_season, predicted_at) VALUES "
            "('pred1', 'p1', 2025, 'WR', 'uncertainty_catboost_v1', 'fv1', 200.0, 160.0, 250.0, "
            "0.8, 0.6, 2024, current_timestamp)"
        )
        con.execute(
            "INSERT INTO edge_snapshot (edge_id, player_id, season, position, ecr_type, "
            "model_version, model_rank, market_rank, rank_edge, evidence_score, action, "
            "reasons_json, built_at) VALUES "
            "('e1', 'p1', 2025, 'WR', 'ro', 'edge_v1', 5, 20, 15, 0.5, 'BUY', "
            "'[\"real reason\"]', current_timestamp)"
        )
        con.execute(
            "INSERT INTO evidence_events (event_id, player_id, season, week, event_date, "
            "captured_at, event_type, source, strength_label, strength, direction, "
            "structured_impact_json, summary) VALUES "
            "('ev1', 'p1', 2025, 3, '2025-09-20', current_timestamp, 'usage_share_shift', "
            "'test', 'STRONG', 0.9, 1, '{}', 'real evidence summary')"
        )

        r = client.get("/players/p1/detail", params={"season": 2025})
        assert r.status_code == 200
        body = r.json()
        assert body["display_name"] == "Full Detail Player"
        assert body["ranking"]["point_prediction"] == pytest.approx(200.0)
        assert body["edge"]["action"] == "BUY"
        assert body["edge"]["reasons"] == ["real reason"]
        assert len(body["recent_evidence"]) == 1
        assert body["recent_evidence"][0]["summary"] == "real evidence summary"
        assert body["league_value"] is None

    def test_no_ranking_or_edge_on_record_is_null_not_an_error(self, con, client):
        _seed_player(con, "p1", "Sparse Player", "TE")
        r = client.get("/players/p1/detail", params={"season": 2025})
        assert r.status_code == 200
        body = r.json()
        assert body["ranking"] is None
        assert body["edge"] is None
        assert body["recent_evidence"] == []
        assert body["rookie"] is None

    def test_rookie_info_populated_from_rookie_season(self, con, client):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, rookie_season) "
            "VALUES ('p1', 'gsis_p1', 'Rookie Player', 'RB', 2026)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, breakout_probability, predicted_at) VALUES "
            "('rp1', 'p1', 2026, 'RB', 'rookie_v1', 140.0, 0.35, current_timestamp)"
        )
        r = client.get("/players/p1/detail", params={"season": 2026})
        assert r.status_code == 200
        body = r.json()
        assert body["rookie"]["draft_class"] == 2026
        assert body["rookie"]["predicted_rookie_points"] == pytest.approx(140.0)

    def test_unknown_league_id_404s(self, con, client):
        _seed_player(con, "p1", "X", "WR")
        r = client.get(
            "/players/p1/detail", params={"season": 2025, "league_id": "not-a-real-league"}
        )
        assert r.status_code == 404

    def test_league_value_uses_the_real_dynasty_trade_recommendation(self, con, client):
        _seed_player(con, "p1", "Trade Target", "RB")
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('p1', '2026-08-01', 24.0, 5000, current_timestamp)"
        )
        r = client.get("/players/p1/detail", params={"season": 2025, "league_id": "target_league"})
        assert r.status_code == 200
        body = r.json()
        assert body["league_value"]["league_id"] == "target_league"
        assert body["league_value"]["trade_action"] in ("BUY", "SELL", "HOLD", "WATCH")
        assert body["league_value"]["is_mine"] is None

    def test_is_mine_reflects_the_real_roster(self, con, client, monkeypatch):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        _seed_player(con, "asq_mine", "My Player", "WR")
        _seed_player(con, "asq_theirs", "Their Player", "WR")
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
            "('sleeper_id', 'sl_mine', 'asq_mine', 'test')"
        )
        league_body = {
            "league_id": "222",
            "total_rosters": 1,
            "roster_positions": ["WR", "BN"],
            "scoring_settings": {},
            "settings": {"type": 0},
        }
        rosters_body = [{"roster_id": 1, "owner_id": "u1", "players": ["sl_mine"]}]
        users_body = [{"user_id": "u1", "display_name": "me", "metadata": {}}]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters_body
            elif url.endswith("/users"):
                body = users_body
            else:
                body = league_body
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)
        client.post("/league/register", json={"sleeper_league_id": "222", "league_id": "im_test"})

        r_mine = client.get(
            "/players/asq_mine/detail",
            params={"season": 2025, "league_id": "im_test", "roster_id": 1},
        )
        assert r_mine.json()["league_value"]["is_mine"] is True

        r_theirs = client.get(
            "/players/asq_theirs/detail",
            params={"season": 2025, "league_id": "im_test", "roster_id": 1},
        )
        assert r_theirs.json()["league_value"]["is_mine"] is False


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


class TestWeeklyRankingsSurfaceEvidenceAdjustment:
    """D46: `/rankings/weekly` is the closed loop the audit found missing -- evidence
    computed a bounded adjustment (M9) but nothing served it. This must return the real
    adjusted value (not the raw base) when a projection_deltas row exists, and fall back to
    the base value untouched when it doesn't."""

    def test_returns_the_evidence_adjusted_value_when_a_delta_exists(self, con, client):
        _seed_player(con, "p1", "Adjusted Player", "WR")
        con.execute(
            "INSERT INTO weekly_projection_snapshot "
            "(player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2025, 8, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        con.execute(
            "INSERT INTO projection_deltas "
            "(delta_id, player_id, season, week, base_model_name, base_value, adjusted_value, "
            "adjustment_pct, evidence_score, reason, evidence_ids_json, built_at) "
            "VALUES ('d1', 'p1', 2025, 8, 'ml_catboost', 10.0, 11.5, 0.15, 1.0, "
            "'real evidence reason', '[]', current_timestamp)"
        )
        r = client.get("/rankings/weekly", params={"season": 2025, "week": 8})
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["base_value"] == pytest.approx(10.0)
        assert body[0]["adjusted_value"] == pytest.approx(11.5)
        assert body[0]["adjustment_pct"] == pytest.approx(0.15)
        assert body[0]["reason"] == "real evidence reason"

    def test_falls_back_to_the_unadjusted_base_value_when_no_delta_exists(self, con, client):
        _seed_player(con, "p1", "No Evidence Player", "RB")
        con.execute(
            "INSERT INTO weekly_projection_snapshot "
            "(player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2025, 8, 'ml_catboost', 'RB', 7.0, current_timestamp)"
        )
        r = client.get("/rankings/weekly", params={"season": 2025, "week": 8})
        body = r.json()
        assert len(body) == 1
        assert body[0]["base_value"] == pytest.approx(7.0)
        assert body[0]["adjusted_value"] == pytest.approx(7.0)
        assert body[0]["adjustment_pct"] is None
        assert body[0]["reason"] is None

    def test_orders_by_the_evidence_adjusted_value_not_the_base_value(self, con, client):
        _seed_player(con, "low_base_big_boost", "Riser", "WR")
        _seed_player(con, "high_base_no_evidence", "Faller", "WR")
        con.execute(
            "INSERT INTO weekly_projection_snapshot "
            "(player_id, season, week, model_name, position, predicted_points, built_at) VALUES "
            "('low_base_big_boost', 2025, 8, 'ml_catboost', 'WR', 8.0, current_timestamp), "
            "('high_base_no_evidence', 2025, 8, 'ml_catboost', 'WR', 9.0, current_timestamp)"
        )
        con.execute(
            "INSERT INTO projection_deltas "
            "(delta_id, player_id, season, week, base_model_name, base_value, adjusted_value, "
            "adjustment_pct, evidence_score, reason, evidence_ids_json, built_at) "
            "VALUES ('d1', 'low_base_big_boost', 2025, 8, 'ml_catboost', 8.0, 9.2, 0.15, 1.0, "
            "'boosted', '[]', current_timestamp)"
        )
        r = client.get("/rankings/weekly", params={"season": 2025, "week": 8})
        # Base-value order would put high_base_no_evidence (9.0) first; adjusted-value order
        # (9.2 vs 9.0) must put low_base_big_boost first instead.
        assert [row["player_id"] for row in r.json()] == [
            "low_base_big_boost",
            "high_base_no_evidence",
        ]


class TestEdgeIsADirectProjection:
    def test_edge_returns_the_exact_stored_action_and_reasons(self, con, client):
        _seed_player(con, "p1", "Edge Player", "WR")
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, projected_points_edge, evidence_score, confidence,
                 action, reasons_json, built_at)
            VALUES ('e1', 'p1', 2025, 'WR', 'ro', 'edge_v1', 5, 50, 45, 30.0, 0.5, 0.8, 'BUY', '["real reason"]', current_timestamp)
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
                "VALUES (?, ?, 2025, 'WR', 'ro', 'edge_v1', 1, 2, 1, 0.5, ?, '[]', current_timestamp)",
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
    def test_list_leagues_returns_the_real_registry(self, client):
        r = client.get("/league")
        assert r.status_code == 200
        body = r.json()
        assert any(
            entry["league_id"] == "target_league" and entry["source"] == "yaml" for entry in body
        )

    def test_register_league_validates_and_persists_then_shows_up_in_list(
        self, con, client, monkeypatch
    ):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        body = {
            "league_id": "555",
            "name": "API Test League",
            "total_rosters": 6,
            "roster_positions": ["QB", "RB", "WR", "BN"],
            "scoring_settings": {"rec": 1.0},
            "settings": {"type": 2, "waiver_budget": 100},
        }

        def fake_get(url, **kwargs):
            import json as _json

            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

        r = client.post(
            "/league/register",
            json={"sleeper_league_id": "555", "league_id": "api_test_league"},
        )
        assert r.status_code == 200
        assert r.json()["league_id"] == "api_test_league"

        listed = client.get("/league").json()
        assert any(entry["league_id"] == "api_test_league" for entry in listed)

    def test_register_league_unreachable_returns_422_not_a_silent_success(
        self, client, monkeypatch
    ):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        monkeypatch.setattr(httpx, "get", lambda url, **kwargs: FakeGetResponse(404, None, b""))

        r = client.post("/league/register", json={"sleeper_league_id": "does-not-exist"})
        assert r.status_code == 422

    def test_unknown_league_id_returns_404_not_a_fabricated_answer(self, client):
        r = client.get("/league/not-a-real-league/context")
        assert r.status_code == 404

    def test_teams_endpoint_unsupported_for_a_yaml_league(self, client):
        r = client.get("/league/target_league/teams")
        assert r.status_code == 200
        body = r.json()
        assert body["supported"] is False
        assert body["teams"] == []

    def test_teams_endpoint_returns_real_bridged_rosters_for_a_sleeper_league(
        self, con, client, monkeypatch
    ):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        _seed_player(con, "asq_qb1", "Real QB", "QB")
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) "
            "VALUES ('sleeper_id', '6813', 'asq_qb1', 'test')"
        )
        league_body = {
            "league_id": "777",
            "name": "Teams Test League",
            "total_rosters": 2,
            "roster_positions": ["QB", "BN"],
            "scoring_settings": {"rec": 1.0},
            "settings": {"type": 2, "waiver_budget": 100},
        }
        rosters_body = [
            {"roster_id": 1, "owner_id": "u1", "players": ["6813"]},
            {"roster_id": 2, "owner_id": "u2", "players": []},
        ]
        users_body = [
            {"user_id": "u1", "display_name": "gimann", "metadata": {"team_name": "Squad A"}},
            {"user_id": "u2", "display_name": "rival", "metadata": {}},
        ]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters_body
            elif url.endswith("/users"):
                body = users_body
            else:
                body = league_body
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

        reg = client.post(
            "/league/register", json={"sleeper_league_id": "777", "league_id": "teams_test"}
        )
        assert reg.status_code == 200

        r = client.get("/league/teams_test/teams")
        assert r.status_code == 200
        body = r.json()
        assert body["supported"] is True
        assert len(body["teams"]) == 2
        team1 = next(t for t in body["teams"] if t["roster_id"] == 1)
        assert team1["owner_display_name"] == "gimann"
        assert team1["team_name"] == "Squad A"
        assert team1["players"] == [
            {"player_id": "asq_qb1", "display_name": "Real QB", "position": "QB"}
        ]

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

    def test_roster_id_on_a_yaml_league_returns_422_rather_than_silently_ignoring_it(self, client):
        r = client.get("/league/target_league/roster", params={"roster_id": 1})
        assert r.status_code == 422

    def test_roster_id_on_a_sleeper_league_derives_real_positions(self, con, client, monkeypatch):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        _seed_player(con, "asq_qb1", "Real QB", "QB")
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) "
            "VALUES ('sleeper_id', '6813', 'asq_qb1', 'test')"
        )
        league_body = {
            "league_id": "888",
            "total_rosters": 1,
            "roster_positions": ["QB", "BN"],
            "scoring_settings": {},
            "settings": {"type": 2},
        }
        rosters_body = [{"roster_id": 1, "owner_id": "u1", "players": ["6813"]}]
        users_body = [{"user_id": "u1", "display_name": "gimann", "metadata": {}}]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters_body
            elif url.endswith("/users"):
                body = users_body
            else:
                body = league_body
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)
        client.post("/league/register", json={"sleeper_league_id": "888", "league_id": "rid_test"})

        r = client.get("/league/rid_test/roster", params={"roster_id": 1})
        assert r.status_code == 200
        assert r.json()["roster_positions"] == ["QB"]

    def test_waiver_targets_endpoint_excludes_rostered_players(self, con, client, monkeypatch):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        _seed_player(con, "asq_rostered", "Rostered WR", "WR")
        _seed_player(con, "asq_free_agent", "Free Agent WR", "WR")
        for pid, pts in [("asq_rostered", 200.0), ("asq_free_agent", 180.0)]:
            con.execute(
                "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, "
                "position, model_version, feature_version, point_prediction, top24_prob, "
                "calibration_season, predicted_at) VALUES "
                "(?, ?, 2025, 'WR', 'uncertainty_catboost_v1', 'fv1', ?, 0.3, 2024, current_timestamp)",
                [f"pred_{pid}", pid, pts],
            )
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
            "('sleeper_id', 'sl_rostered', 'asq_rostered', 'test')"
        )
        league_body = {
            "league_id": "999",
            "total_rosters": 2,
            "roster_positions": ["WR", "BN"],
            "scoring_settings": {},
            "settings": {"type": 0, "waiver_budget": 100},
        }
        rosters_body = [
            {"roster_id": 1, "owner_id": "u1", "players": ["sl_rostered"]},
            {"roster_id": 2, "owner_id": "u2", "players": []},
        ]
        users_body = [
            {"user_id": "u1", "display_name": "them", "metadata": {}},
            {"user_id": "u2", "display_name": "me", "metadata": {}},
        ]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters_body
            elif url.endswith("/users"):
                body = users_body
            else:
                body = league_body
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)
        client.post("/league/register", json={"sleeper_league_id": "999", "league_id": "wt_test"})

        r = client.get(
            "/league/wt_test/waiver-targets",
            params={"season": 2025, "week": 5, "roster_id": 2},
        )
        assert r.status_code == 200
        body = r.json()
        ids = [row["player_id"] for row in body]
        assert "asq_rostered" not in ids
        assert "asq_free_agent" in ids
        row = next(row for row in body if row["player_id"] == "asq_free_agent")
        assert row["display_name"] == "Free Agent WR"
        assert row["reasons"]

    def test_drop_candidates_endpoint_returns_only_the_real_bench_player(
        self, con, client, monkeypatch
    ):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        _seed_player(con, "asq_starter", "Starter WR", "WR")
        _seed_player(con, "asq_bench", "Bench WR", "WR")
        for pid, pts in [("asq_starter", 200.0), ("asq_bench", 20.0)]:
            con.execute(
                "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, "
                "position, model_version, feature_version, point_prediction, top24_prob, "
                "calibration_season, predicted_at) VALUES "
                "(?, ?, 2025, 'WR', 'uncertainty_catboost_v1', 'fv1', ?, 0.1, 2024, current_timestamp)",
                [f"pred_{pid}", pid, pts],
            )
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
            "('sleeper_id', 'sl_starter', 'asq_starter', 'test'), "
            "('sleeper_id', 'sl_bench', 'asq_bench', 'test')"
        )
        league_body = {
            "league_id": "444",
            "total_rosters": 1,
            "roster_positions": ["WR", "BN"],
            "scoring_settings": {},
            "settings": {"type": 0, "waiver_budget": 100},
        }
        rosters_body = [{"roster_id": 1, "owner_id": "u1", "players": ["sl_starter", "sl_bench"]}]
        users_body = [{"user_id": "u1", "display_name": "me", "metadata": {}}]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters_body
            elif url.endswith("/users"):
                body = users_body
            else:
                body = league_body
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)
        client.post("/league/register", json={"sleeper_league_id": "444", "league_id": "dc_test"})

        r = client.get("/league/dc_test/drop-candidates", params={"season": 2025, "roster_id": 1})
        assert r.status_code == 200
        body = r.json()
        assert [row["player_id"] for row in body] == ["asq_bench"]
        assert body[0]["display_name"] == "Bench WR"
        assert body[0]["reasons"]

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

    def test_trade_endpoint_returns_the_real_action(self, con, client):
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('star', '2026-08-01', 24.0, 9000, current_timestamp)"
        )
        con.execute(
            "INSERT INTO edge_snapshot (edge_id, player_id, season, position, ecr_type, "
            "model_version, model_rank, market_rank, rank_edge, evidence_score, action, "
            "reasons_json, built_at) VALUES "
            "('e1', 'star', 2025, 'WR', 'ro', 'edge_v1', 5, 20, 15, 0.5, 'BUY', '[]', current_timestamp)"
        )
        r = client.post("/league/target_league/trade", json={"season": 2025, "player_id": "star"})
        assert r.status_code == 200
        body = r.json()
        assert body["action"] == "BUY"
        assert body["expected_value"] == pytest.approx(9000)

    def test_trade_package_endpoint_calls_the_real_evaluate_trade_package(self, con, client):
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('star', '2026-08-01', 24.0, 9000, current_timestamp)"
        )
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('scrub', '2026-08-01', 30.0, 50, current_timestamp)"
        )
        r = client.post(
            "/league/target_league/trade-package",
            json={
                "season": 2025,
                "side_a": {"player_ids": ["star"], "picks": []},
                "side_b": {"player_ids": ["scrub"], "picks": [{"round": 1, "pick_in_round": 1}]},
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["side_a_value"] > 0
        assert body["side_b_value"] > 0
        assert body["favors"] in ("side_a", "side_b", "even")
        assert body["side_a_reasons"] and body["side_b_reasons"]

    def test_trade_package_unknown_league_404s(self, client):
        r = client.post(
            "/league/not-a-real-league/trade-package",
            json={"season": 2025, "side_a": {}, "side_b": {}},
        )
        assert r.status_code == 404


class TestSimulation:
    """P1-4: the same real `simulate_team_season` the CLI's `simulate team-season` calls,
    over a synthetic history shaped like tests/unit/test_simulation.py's fixture -- proving
    the API is a thin wrapper (no parallel simulation logic), not re-testing the Monte Carlo
    math itself (that's test_simulation.py's job)."""

    TEAM = "TST"
    HIST_SEASON = 2024
    SIM_SEASON = 2025
    _HISTORY = [
        (55, 0.50, 20.0),
        (60, 0.55, 24.0),
        (65, 0.60, 28.0),
        (70, 0.65, 32.0),
        (50, 0.45, 16.0),
        (58, 0.52, 22.0),
        (63, 0.58, 26.0),
        (68, 0.62, 30.0),
        (52, 0.48, 18.0),
        (66, 0.61, 29.0),
    ]

    def _seed_history(self, con):
        from datetime import date, timedelta

        for wk, (plays, pass_rate, points) in enumerate(self._HISTORY, start=1):
            game_id = f"{self.HIST_SEASON}_{wk:02d}_{self.TEAM}_OPP"
            game_date = date(self.HIST_SEASON, 9, 1) + timedelta(weeks=wk - 1)
            con.execute(
                "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, "
                "away_team) VALUES (?, ?, ?, 'REG', ?, ?, 'OPP') ON CONFLICT DO NOTHING",
                [game_id, self.HIST_SEASON, wk, game_date, self.TEAM],
            )
            con.execute(
                "INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, "
                "pass_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [self.TEAM, self.HIST_SEASON, wk, game_id, game_date, float(plays), pass_rate],
            )
            con.execute(
                "INSERT INTO team_week_points (team, season, week, game_id, points) "
                "VALUES (?, ?, ?, ?, ?)",
                [self.TEAM, self.HIST_SEASON, wk, game_id, points],
            )

    def _seed_player_week(self, con, player_id, display_name, position, week, **kw):
        from datetime import date, timedelta

        game_id = f"{self.SIM_SEASON}_{week:02d}_{self.TEAM}_OPP"
        game_date = date(self.SIM_SEASON, 9, 1) + timedelta(weeks=week - 1)
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
            "(?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [player_id, f"00-test-{player_id}", display_name, position],
        )
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, "
            "away_team) VALUES (?, ?, ?, 'REG', ?, ?, 'OPP') ON CONFLICT DO NOTHING",
            [game_id, self.SIM_SEASON, week, game_date, self.TEAM],
        )
        con.execute(
            "INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, "
            "pass_rate) VALUES (?, ?, ?, ?, ?, 60.0, 0.6) ON CONFLICT DO NOTHING",
            [self.TEAM, self.SIM_SEASON, week, game_id, game_date],
        )
        con.execute(
            "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, "
            "team, position, targets, carries, fantasy_points_ppr, offense_snap_pct, "
            "source_snapshot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')",
            [
                player_id,
                self.SIM_SEASON,
                week,
                game_id,
                game_date,
                self.TEAM,
                position,
                kw.get("targets", 0.0),
                kw.get("carries", 0.0),
                kw.get("fantasy_points_ppr", 0.0),
                kw.get("offense_snap_pct"),
            ],
        )

    def test_endpoint_calls_the_real_simulate_team_season_and_persists_a_run(self, con, client):
        self._seed_history(con)
        for wk in range(1, 5):
            self._seed_player_week(
                con, "wr1", "Wide Receiver One", "WR", wk, targets=8.0, fantasy_points_ppr=14.0
            )
            self._seed_player_week(
                con,
                "qb1",
                "Quarterback One",
                "QB",
                wk,
                fantasy_points_ppr=18.0,
                offense_snap_pct=0.95,
            )

        r = client.post(
            "/simulate/team-season",
            json={"team": self.TEAM, "season": self.SIM_SEASON, "n_simulations": 200, "seed": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["team"] == self.TEAM
        assert body["n_simulations"] == 200
        assert body["run_id"].startswith("sim_")
        player_ids = {p["player_id"] for p in body["players"]}
        assert player_ids == {"wr1", "qb1"}
        wr1 = next(p for p in body["players"] if p["player_id"] == "wr1")
        assert wr1["display_name"] == "Wide Receiver One"
        assert wr1["mean_points"] > 0
        assert wr1["p10"] <= wr1["p50"] <= wr1["p90"]

        stored = con.execute(
            "SELECT team, season, n_simulations FROM team_simulation_runs WHERE run_id = ?",
            [body["run_id"]],
        ).fetchone()
        assert stored == (self.TEAM, self.SIM_SEASON, 200)

    def test_insufficient_history_returns_422_not_a_fabricated_result(self, client):
        r = client.post(
            "/simulate/team-season",
            json={"team": "ZZZ", "season": 2025, "n_simulations": 50},
        )
        assert r.status_code == 422


class TestLatestSeasons:
    """D48: the real newest season each table has data for, so the frontend can default to
    it instead of a hardcoded value that silently goes stale every year (the same failure
    mode D40 already fixed once for the rookie-class default)."""

    def test_returns_the_real_max_season_per_table(self, con, client):
        con.execute(
            "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
            "model_version, feature_version, point_prediction, calibration_season, predicted_at) "
            "VALUES ('p1', 'x1', 2024, 'WR', 'v1', 'fv1', 100.0, 2023, current_timestamp), "
            "('p2', 'x2', 2025, 'WR', 'v1', 'fv1', 100.0, 2024, current_timestamp)"
        )
        r = client.get("/seasons/latest")
        assert r.status_code == 200
        body = r.json()
        assert body["uncertainty"] == 2025

    def test_empty_tables_return_null_not_an_error(self, client):
        r = client.get("/seasons/latest")
        assert r.status_code == 200
        body = r.json()
        assert body["uncertainty"] is None
        assert body["edge"] is None
        assert body["evidence"] is None
        assert body["weekly"] is None


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
            "VALUES ('edge123', 'p1', 2025, 'WR', 'ro', 'edge_v1', 1, 2, 1, 0.5, 'BUY', '[]', current_timestamp)"
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


class TestRookiesModelVersionFiltering:
    """docs/DECISIONS.md D39: `rookie_predictions` holds one row per
    (player, draft_class, model_version), and since the college-production ablation that is
    several versions -- the production feature set plus each experimental arm. The endpoint
    must serve ONE of them, or every rookie appears once per arm and reads as duplicate
    players. Found by running the real API against a real database; no test covered it."""

    def _seed_prediction(self, con, player_id, model_version, points):
        con.execute(
            """
            INSERT INTO rookie_predictions
                (prediction_id, player_id, draft_class, position, model_version,
                 predicted_rookie_points, breakout_probability, predicted_at)
            VALUES (?, ?, 2025, 'RB', ?, ?, 0.5, current_timestamp)
            """,
            [f"rp_{player_id}_{model_version}", player_id, model_version, points],
        )

    def test_defaults_to_the_production_model_version_only(self, con, client):
        from alpha_squad.models.rookie.features import FEATURE_VERSION

        _seed_player(con, "r1", "Rookie One", "RB")
        self._seed_prediction(con, "r1", FEATURE_VERSION, 200.0)
        self._seed_prediction(con, "r1", "rookie_features_v2_college", 111.0)
        self._seed_prediction(con, "r1", "some_stale_version", 222.0)

        rows = client.get("/rookies?draft_class=2025").json()

        assert len(rows) == 1, "one row per player, not one per trained arm"
        assert rows[0]["model_version"] == FEATURE_VERSION
        assert rows[0]["predicted_rookie_points"] == 200.0

    def test_an_ablation_arm_can_still_be_inspected_explicitly(self, con, client):
        from alpha_squad.models.rookie.features import FEATURE_VERSION

        _seed_player(con, "r1", "Rookie One", "RB")
        self._seed_prediction(con, "r1", FEATURE_VERSION, 200.0)
        self._seed_prediction(con, "r1", "rookie_features_v2_college", 111.0)

        rows = client.get(
            "/rookies?draft_class=2025&model_version=rookie_features_v2_college"
        ).json()

        assert len(rows) == 1
        assert rows[0]["predicted_rookie_points"] == 111.0
