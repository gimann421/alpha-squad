"""Unit tests for the trade-evaluation evidence summary (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.trade_evaluation import build_trade_evidence_summary
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_validation_row(
    con, season, action, n, mean_actual, mean_implied, mean_outperf, ecr_type="rsf"
):
    con.execute(
        """
        INSERT INTO edge_validation_results
            (model_version, ecr_type, season, action, n, mean_actual_points,
             mean_market_implied_points, mean_outperformance_vs_market, evaluated_at)
        VALUES ('edge_v1', ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [ecr_type, season, action, n, mean_actual, mean_implied, mean_outperf],
    )


class TestTradeEvidenceSummary:
    def test_only_buy_and_sell_actions_are_included(self, con):
        _seed_validation_row(con, 2023, "BUY", 10, 200.0, 150.0, 50.0)
        _seed_validation_row(con, 2023, "WATCH", 20, 100.0, 100.0, 0.0)
        _seed_validation_row(con, 2023, "HOLD", 5, 90.0, 90.0, 0.0)
        evidence = build_trade_evidence_summary(con, 2023, 2023)
        actions_seen = {row["action"] for row in evidence}
        assert actions_seen == {"BUY"}

    def test_respects_season_range(self, con):
        _seed_validation_row(con, 2021, "SELL", 5, 20.0, 40.0, -20.0)
        _seed_validation_row(con, 2024, "SELL", 5, 20.0, 40.0, -20.0)
        evidence = build_trade_evidence_summary(con, 2022, 2025)
        assert len(evidence) == 1
        assert evidence[0]["season"] == 2024

    def test_respects_ecr_type_filter(self, con):
        _seed_validation_row(con, 2023, "BUY", 10, 200.0, 150.0, 50.0, ecr_type="rsf")
        _seed_validation_row(con, 2023, "BUY", 10, 200.0, 150.0, 50.0, ecr_type="dsf")
        evidence = build_trade_evidence_summary(con, 2023, 2023, ecr_type="dsf")
        assert len(evidence) == 1

    def test_real_fields_pass_through_unmodified(self, con):
        _seed_validation_row(con, 2023, "SELL", 7, 33.0, 88.0, -55.0)
        evidence = build_trade_evidence_summary(con, 2023, 2023)
        assert evidence[0] == {
            "season": 2023,
            "action": "SELL",
            "n": 7,
            "mean_actual_points": 33.0,
            "mean_market_implied_points": 88.0,
            "mean_outperformance_vs_market": -55.0,
        }
