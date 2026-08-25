"""Unit tests for league/roster_intelligence.py: joins a real roster (mocked Sleeper fetch)
against seeded uncertainty/EDGE/dynasty-value rows and a real starter/bench VBD split."""

from __future__ import annotations

import duckdb
import httpx
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster_intelligence import (
    build_action_center,
    build_my_team_report,
    recommend_drops,
)
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db
from tests.fixtures.httpx_fakes import FakeGetResponse

LEAGUE_ID = "555000111"
SEASON = 2025

# qb1/rb1/rb2/wr1/wr2/te1/rb3 fill every dedicated + the one flex slot; wr3 is the only bench
# player, given lineup QB1/RB2/WR2/TE1/FLEX1.
ROSTER_PLAYERS = {
    "qb1": ("QB", 300.0),
    "rb1": ("RB", 250.0),
    "rb2": ("RB", 200.0),
    "rb3": ("RB", 100.0),
    "wr1": ("WR", 220.0),
    "wr2": ("WR", 180.0),
    "te1": ("TE", 150.0),
    "wr3": ("WR", 50.0),
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    for player_id, (position, points) in ROSTER_PLAYERS.items():
        connection.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, ?)",
            [player_id, f"gsis_{player_id}", player_id, position],
        )
        connection.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
            "('sleeper_id', ?, ?, 'test')",
            [f"sl_{player_id}", player_id],
        )
        connection.execute(
            "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
            "model_version, feature_version, point_prediction, p10, p90, confidence, top24_prob, "
            "calibration_season, predicted_at) VALUES "
            "(?, ?, ?, ?, ?, 'fv1', ?, ?, ?, 0.8, 0.4, ?, current_timestamp)",
            [
                f"pred_{player_id}",
                player_id,
                SEASON,
                position,
                UNCERTAINTY_MODEL_VERSION,
                points,
                points * 0.8,
                points * 1.2,
                SEASON - 1,
            ],
        )
    # A real EDGE row and dynasty value for one player, to prove the join works.
    connection.execute(
        "INSERT INTO edge_snapshot (edge_id, player_id, season, position, ecr_type, "
        "model_version, model_rank, market_rank, rank_edge, evidence_score, action, "
        "reasons_json, built_at) VALUES "
        "('e1', 'rb1', ?, 'RB', 'rsf', 'edge_v1', 5, 20, 15, 0.5, 'BUY', '[]', current_timestamp)",
        [SEASON],
    )
    connection.execute(
        "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
        "VALUES ('rb1', '2026-08-01', 24.0, 8000, current_timestamp)"
    )
    # A real free agent -- projected, but never rostered by anyone -- so rank_waiver_targets
    # (via build_action_center) has a real "adds" candidate to surface.
    connection.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
        "('fa1', 'gsis_fa1', 'Free Agent One', 'WR')"
    )
    connection.execute(
        "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
        "model_version, feature_version, point_prediction, top24_prob, calibration_season, "
        "predicted_at) VALUES "
        "('pred_fa1', 'fa1', ?, 'WR', ?, 'fv1', 120.0, 0.3, ?, current_timestamp)",
        [SEASON, UNCERTAINTY_MODEL_VERSION, SEASON - 1],
    )
    yield connection
    connection.close()


def _league() -> LeagueContext:
    return LeagueContext(
        league_id=LEAGUE_ID,
        format="dynasty",
        teams=10,
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
        source="sleeper",
        sleeper_league_id=LEAGUE_ID,
    )


def _fake_get(monkeypatch):
    rosters_body = [
        {
            "roster_id": 1,
            "owner_id": "u1",
            "players": [f"sl_{p}" for p in ROSTER_PLAYERS] + ["unmapped_id_999"],
        }
    ]
    users_body = [{"user_id": "u1", "display_name": "gimann", "metadata": {"team_name": "My Team"}}]

    def fake_get(url, **kwargs):
        import json as _json

        if url.endswith("/rosters"):
            body = rosters_body
        elif url.endswith("/users"):
            body = users_body
        else:
            raise AssertionError(f"unexpected url {url}")
        return FakeGetResponse(200, body, _json.dumps(body).encode())

    monkeypatch.setattr(httpx, "get", fake_get)


class TestBuildMyTeamReport:
    def test_real_starter_bench_split_and_totals(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        report = build_my_team_report(con, _league(), SEASON, roster_id=1, ecr_type="rsf")

        assert report.owner_display_name == "gimann"
        assert report.team_name == "My Team"
        assert report.unmapped_player_count == 1

        starters = {p.player_id for p in report.players if p.is_starter}
        bench = {p.player_id for p in report.players if not p.is_starter}
        assert starters == {"qb1", "rb1", "rb2", "rb3", "wr1", "wr2", "te1"}
        assert bench == {"wr3"}

        expected_total = sum(pts for _, pts in ROSTER_PLAYERS.values())
        assert report.total_projected_points == pytest.approx(expected_total)

    def test_edge_and_dynasty_value_join_correctly(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        report = build_my_team_report(con, _league(), SEASON, roster_id=1, ecr_type="rsf")

        rb1 = next(p for p in report.players if p.player_id == "rb1")
        assert rb1.market_rank == 20
        assert rb1.rank_edge == 15
        assert rb1.edge_action == "BUY"
        assert rb1.dynasty_value == pytest.approx(8000)

        qb1 = next(p for p in report.players if p.player_id == "qb1")
        assert qb1.market_rank is None
        assert qb1.dynasty_value is None

    def test_positional_needs_reflect_the_real_roster(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        report = build_my_team_report(con, _league(), SEASON, roster_id=1)

        assert set(report.positional_needs) == {"QB", "RB", "WR", "TE"}
        assert set(report.replacement_levels) == {"QB", "RB", "WR", "TE"}

    def test_unknown_roster_id_raises(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        with pytest.raises(RuntimeError, match="no roster_id 999"):
            build_my_team_report(con, _league(), SEASON, roster_id=999)

    def test_yaml_league_raises_rather_than_fabricating_a_roster(self, con, settings):
        yaml_league = LeagueContext(league_id="target_league", format="dynasty", teams=10)
        with pytest.raises(RuntimeError, match="no real per-team roster source"):
            build_my_team_report(con, yaml_league, SEASON, roster_id=1)


class TestRecommendDrops:
    def test_only_the_real_bench_player_is_a_drop_candidate(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        candidates = recommend_drops(con, _league(), SEASON, roster_id=1, top_n=5)

        assert [c.player_id for c in candidates] == ["wr3"]
        assert candidates[0].reasons

    def test_never_recommends_dropping_a_starter(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        candidates = recommend_drops(con, _league(), SEASON, roster_id=1, top_n=20)

        starters = {"qb1", "rb1", "rb2", "rb3", "wr1", "wr2", "te1"}
        assert not (starters & {c.player_id for c in candidates})

    def test_top_n_limits_the_result(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        candidates = recommend_drops(con, _league(), SEASON, roster_id=1, top_n=0)
        assert candidates == []


class TestBuildActionCenter:
    """D53: pure aggregation of already-real engines, grouped by action type."""

    def test_aggregates_real_adds_drops_and_trade_signals(self, con, settings, monkeypatch):
        _fake_get(monkeypatch)
        report = build_action_center(con, _league(), SEASON, week=5, roster_id=1)

        assert [a.player_id for a in report.adds] == ["fa1"]
        assert [d.player_id for d in report.drops] == ["wr3"]
        assert [s.player_id for s in report.trade_signals] == ["rb1"]
        assert report.trade_signals[0].edge_action == "BUY"
        assert "undervalues" in report.trade_signals[0].summary

    def test_no_buy_sell_edge_rows_means_no_trade_signals(self, con, settings, monkeypatch):
        con.execute("DELETE FROM edge_snapshot")
        _fake_get(monkeypatch)
        report = build_action_center(con, _league(), SEASON, week=5, roster_id=1)
        assert report.trade_signals == []
