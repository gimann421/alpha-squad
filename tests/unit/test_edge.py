"""Unit tests for model-vs-market EDGE: the gating rule (ACCEPTANCE_CRITERIA.md's "a raw
ranking discrepancy cannot alone produce a strong EDGE") against hand-picked numbers, and the
end-to-end rank/points/probability wiring against a synthetic fixture."""

from __future__ import annotations

import json

import duckdb
import pytest

from alpha_squad.market.edge import (
    CONFIDENCE_THRESHOLD,
    MIN_CURVE_TRAINING_ROWS,
    POINTS_EDGE_THRESHOLD,
    RANK_EDGE_THRESHOLD,
    classify_action,
    compute_edges_for_season,
    evaluate_historical_edge,
    run_edge_build,
    store_edges,
)
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


class TestClassifyActionGatingRule:
    """The hard requirement: a raw rank discrepancy alone can never yield BUY/SELL."""

    def test_large_rank_edge_with_zero_points_edge_is_never_buy_or_sell(self):
        action, reasons = classify_action(rank_edge=200, points_edge=0.0, confidence=0.95)
        assert action not in {"BUY", "SELL"}

    def test_large_rank_edge_with_missing_points_curve_is_watch(self):
        action, reasons = classify_action(rank_edge=200, points_edge=None, confidence=0.95)
        assert action == "WATCH"
        assert any("rank edge alone is never sufficient" in r for r in reasons)

    def test_agreeing_large_edges_with_high_confidence_is_buy(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 5,
            points_edge=POINTS_EDGE_THRESHOLD + 5,
            confidence=CONFIDENCE_THRESHOLD + 0.1,
        )
        assert action == "BUY"

    def test_agreeing_large_negative_edges_with_high_confidence_is_sell(self):
        action, reasons = classify_action(
            rank_edge=-(RANK_EDGE_THRESHOLD + 5),
            points_edge=-(POINTS_EDGE_THRESHOLD + 5),
            confidence=CONFIDENCE_THRESHOLD + 0.1,
        )
        assert action == "SELL"

    def test_disagreeing_sign_never_produces_buy_or_sell_even_with_large_magnitudes(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50,
            points_edge=-(POINTS_EDGE_THRESHOLD + 50),
            confidence=0.99,
        )
        assert action == "WATCH"
        assert any("disagree in direction" in r for r in reasons)

    def test_edges_below_threshold_are_watch_not_buy(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD - 1, points_edge=POINTS_EDGE_THRESHOLD - 1, confidence=0.9
        )
        assert action == "WATCH"

    def test_low_confidence_blocks_buy_even_with_large_agreeing_edges(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50,
            points_edge=POINTS_EDGE_THRESHOLD + 50,
            confidence=CONFIDENCE_THRESHOLD - 0.1,
        )
        assert action == "WATCH"
        assert any("confidence" in r for r in reasons)

    def test_near_zero_edges_are_hold(self):
        action, reasons = classify_action(rank_edge=1, points_edge=1.0, confidence=0.9)
        assert action == "HOLD"

    def test_contradicting_evidence_vetoes_an_otherwise_valid_buy(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50,
            points_edge=POINTS_EDGE_THRESHOLD + 50,
            confidence=0.95,
            evidence_score=0.1,
        )
        assert action == "WATCH"
        assert any("contradicts" in r for r in reasons)

    def test_neutral_evidence_does_not_block_an_otherwise_valid_buy(self):
        action, reasons = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50,
            points_edge=POINTS_EDGE_THRESHOLD + 50,
            confidence=0.95,
            evidence_score=0.5,
        )
        assert action == "BUY"

    def test_evidence_score_defaults_to_neutral_and_does_not_change_prior_behavior(self):
        with_default, _ = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50, points_edge=POINTS_EDGE_THRESHOLD + 50, confidence=0.95
        )
        explicit_neutral, _ = classify_action(
            rank_edge=RANK_EDGE_THRESHOLD + 50,
            points_edge=POINTS_EDGE_THRESHOLD + 50,
            confidence=0.95,
            evidence_score=0.5,
        )
        assert with_default == explicit_neutral == "BUY"


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_market(con, ecr_type, season, month, rows):
    for player_id, position, ecr_rank in rows:
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
            "VALUES (?, ?, ?, ?, ?)",
            [player_id, f"{season}-{month:02d}-01", ecr_type, position, ecr_rank],
        )


def _seed_season_stats(con, season, rows):
    for player_id, position, points in rows:
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 15, ?, ?)",
            [player_id, season, position, points, points / 15],
        )


def _seed_prediction(con, player_id, season, position, point_pred, top24_prob, confidence):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season, predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.1, ?, ?, ?, current_timestamp)
        """,
        [
            f"pred_{player_id}_{season}",
            player_id,
            season,
            position,
            UNCERTAINTY_MODEL_VERSION,
            point_pred,
            top24_prob,
            confidence,
            season - 1,
        ],
    )


class TestComputeEdgesForSeason:
    def test_ranks_and_points_edge_computed_against_real_wiring(self, con):
        # Training season (2020): overall (cross-position) rank strictly decreasing in
        # points, so the pooled isotonic curve is exact with no PAVA pooling ambiguity.
        training_market = []
        training_stats = []
        overall_rank = 0
        for position in ("QB", "RB", "WR", "TE"):
            for i in range(4):
                overall_rank += 1
                pid = f"{position}_train{i}"
                training_market.append((pid, position, float(overall_rank)))
                training_stats.append((pid, position, 400.0 - overall_rank * 20))
        _seed_market(con, "rsf", 2020, 7, training_market)
        _seed_season_stats(con, 2020, training_stats)

        # Target season (2021): one player the model loves far more than the market does.
        _seed_market(
            con,
            "rsf",
            2021,
            7,
            [("underrated_wr", "WR", 80.0), ("agree_qb", "QB", 5.0)],
        )
        _seed_prediction(con, "underrated_wr", 2021, "WR", point_pred=250.0, top24_prob=0.6, confidence=0.9)
        _seed_prediction(con, "agree_qb", 2021, "QB", point_pred=50.0, top24_prob=0.05, confidence=0.9)

        records = compute_edges_for_season(con, 2021, ecr_type="rsf")
        by_player = {r.player_id: r for r in records}

        underrated = by_player["underrated_wr"]
        # market_rank (80) is far worse than model_rank (model ranks this player #1 of the 2
        # target predictions since it has the higher point_prediction).
        assert underrated.market_rank == 80
        assert underrated.model_rank == 1
        assert underrated.rank_edge == 79
        assert underrated.projected_points_edge is not None
        assert underrated.projected_points_edge > 0
        assert underrated.action == "BUY"

        agree = by_player["agree_qb"]
        assert agree.model_rank == 2  # the lower-point_prediction of the two target players

    def test_no_overlap_between_model_and_market_returns_empty(self, con):
        _seed_market(con, "rsf", 2021, 7, [("only_market", "WR", 10.0)])
        _seed_prediction(con, "only_model", 2021, "WR", point_pred=100.0, top24_prob=0.5, confidence=0.8)
        assert compute_edges_for_season(con, 2021, ecr_type="rsf") == []


class TestStoreAndBuildEdge:
    def test_store_edges_is_idempotent_on_rerun(self, con):
        _seed_market(con, "rsf", 2021, 7, [("p1", "WR", 5.0)])
        _seed_prediction(con, "p1", 2021, "WR", point_pred=100.0, top24_prob=0.5, confidence=0.8)
        records = compute_edges_for_season(con, 2021, ecr_type="rsf")
        store_edges(con, records)
        store_edges(con, records)
        n = con.execute("SELECT count(*) FROM edge_snapshot").fetchone()[0]
        assert n == 1

    def test_reasons_json_is_valid_and_reports_evidence_score(self, con):
        _seed_market(con, "rsf", 2021, 7, [("p1", "WR", 5.0)])
        _seed_prediction(con, "p1", 2021, "WR", point_pred=100.0, top24_prob=0.5, confidence=0.8)
        records = compute_edges_for_season(con, 2021, ecr_type="rsf")
        store_edges(con, records)
        raw = con.execute("SELECT reasons_json FROM edge_snapshot WHERE player_id='p1'").fetchone()[0]
        reasons = json.loads(raw)
        assert isinstance(reasons, list) and reasons
        assert any("evidence_score" in r for r in reasons)

    def test_run_edge_build_skips_seasons_with_no_data_rather_than_erroring(self, con):
        report = run_edge_build(con, 2030, 2031, ecr_type="rsf")
        assert report.edges_written == 0
        assert len(report.skipped) == 2


class TestEvaluateHistoricalEdge:
    def test_mean_outperformance_matches_hand_computation(self, con):
        # Training season 2020 for the points curve (needs >= MIN_CURVE_TRAINING_ROWS).
        training_market = [
            (f"t{i}", "WR", float(i + 1)) for i in range(MIN_CURVE_TRAINING_ROWS)
        ]
        training_stats = [
            (f"t{i}", "WR", 400.0 - i * 20) for i in range(MIN_CURVE_TRAINING_ROWS)
        ]
        _seed_market(con, "rsf", 2020, 7, training_market)
        _seed_season_stats(con, 2020, training_stats)

        # A pre-built edge_snapshot row for 2021, action=BUY, at market_rank=5 (curve implies
        # the training points at rank 5: 400 - 4*20 = 320.0).
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, projected_points_edge, probability_edge,
                 evidence_score, confidence, action, reasons_json, prediction_id, built_at)
            VALUES ('e1', 'buy_hit', 2021, 'WR', 'rsf', 'edge_v1', 1, 5, 4, 50.0, 0.1, 0.5, 0.9,
                    'BUY', '[]', NULL, current_timestamp)
            """
        )
        _seed_season_stats(con, 2021, [("buy_hit", "WR", 370.0)])

        results = evaluate_historical_edge(con, 2021, 2021, ecr_type="rsf")
        assert len(results) == 1
        r = results[0]
        assert r["action"] == "BUY"
        assert r["mean_actual_points"] == pytest.approx(370.0)
        assert r["mean_market_implied_points"] == pytest.approx(320.0)
        assert r["mean_outperformance_vs_market"] == pytest.approx(50.0)

        stored = con.execute(
            "SELECT mean_outperformance_vs_market FROM edge_validation_results "
            "WHERE season=2021 AND action='BUY'"
        ).fetchone()
        assert stored[0] == pytest.approx(50.0)
