"""Unit tests for the rookie-vs-baseline evaluation (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.rookie_benchmark import (
    DRAFT_CAPITAL_BASELINE,
    MARKET_ECR_BASELINE,
    build_round_tier_breakdown,
    draft_capital_baseline,
    rookie_market_ecr_baseline,
    run_rookie_baselines,
)
from alpha_squad.market.series import series_for_ecr_type
from alpha_squad.models.rookie.features import FEATURE_VERSION
from alpha_squad.storage.db import init_db

MIN_TRAINING_ROWS = 15


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_training_class(con, position, draft_year, n=MIN_TRAINING_ROWS, ecr_type="do"):
    """`n` real-shaped prior-class players for `position`: draft_pick and real dynasty ECR
    rank both strictly increasing (worse) alongside strictly decreasing real points, so both
    baselines' isotonic curves fit cleanly."""
    for i in range(n):
        player_id = f"{position}_train_{draft_year}_{i}"
        pick = i + 1
        points = 300.0 - i * 5
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, draft_year, "
            "draft_pick, rookie_season) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [player_id, f"gsis_{player_id}", player_id, position, draft_year, pick, draft_year],
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 15, ?, ?)",
            [player_id, draft_year, position, points, points / 15],
        )
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [player_id, f"{draft_year}-08-01", ecr_type, position, float(pick),
             series_for_ecr_type(ecr_type).page_type],
        )


def _seed_target_rookie(con, player_id, position, draft_year, pick, ecr_rank=None, ecr_type="do"):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position, draft_year, "
        "draft_pick, rookie_season) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [player_id, f"gsis_{player_id}", player_id, position, draft_year, pick, draft_year],
    )
    if ecr_rank is not None:
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [player_id, f"{draft_year}-08-01", ecr_type, position, ecr_rank,
             series_for_ecr_type(ecr_type).page_type],
        )


class TestDraftCapitalBaseline:
    def test_no_predictions_when_training_data_is_too_thin(self, con):
        _seed_training_class(con, "WR", 2019, n=5)  # below the 15-row minimum
        _seed_target_rookie(con, "target", "WR", 2020, pick=1)
        assert draft_capital_baseline(con, 2020) == {}

    def test_predicts_only_from_strictly_prior_classes(self, con):
        _seed_training_class(con, "WR", 2019)
        _seed_target_rookie(con, "target_2020", "WR", 2020, pick=1)
        preds = draft_capital_baseline(con, 2020)
        assert "target_2020" in preds
        # An early pick (1) should predict close to the best training outcome (300 pts).
        assert preds["target_2020"] > 250.0

    def test_later_picks_predict_lower_value_than_earlier_picks(self, con):
        _seed_training_class(con, "RB", 2019)
        _seed_target_rookie(con, "early", "RB", 2020, pick=1)
        _seed_target_rookie(con, "late", "RB", 2020, pick=14)
        preds = draft_capital_baseline(con, 2020)
        assert preds["early"] > preds["late"]


class TestRookieMarketEcrBaseline:
    def test_predicts_only_from_strictly_prior_classes(self, con):
        _seed_training_class(con, "TE", 2019)
        _seed_target_rookie(con, "target_2020", "TE", 2020, pick=1, ecr_rank=1.0)
        preds = rookie_market_ecr_baseline(con, 2020)
        assert "target_2020" in preds
        assert preds["target_2020"] > 250.0

    def test_no_prediction_without_a_real_preseason_ecr_row(self, con):
        _seed_training_class(con, "QB", 2019)
        _seed_target_rookie(con, "no_ecr", "QB", 2020, pick=1, ecr_rank=None)
        preds = rookie_market_ecr_baseline(con, 2020)
        assert "no_ecr" not in preds


class TestRunRookieBaselines:
    def test_writes_through_the_shared_evaluation_harness(self, con):
        _seed_training_class(con, "WR", 2019)
        _seed_target_rookie(con, "target", "WR", 2020, pick=1, ecr_rank=1.0)
        # a real outcome for the target class, so evaluate_and_record has something to score
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('target', 2020, 'WR', 15, 200.0, 13.3)"
        )
        run_rookie_baselines(con, [2020])
        rows = con.execute(
            "SELECT model_name FROM evaluation_results WHERE season = 2020 AND model_name = ANY(?)",
            [[DRAFT_CAPITAL_BASELINE, MARKET_ECR_BASELINE]],
        ).fetchall()
        assert len(rows) >= 1


class TestRoundTierBreakdown:
    def test_tiers_come_out_by_real_draft_round(self, con):
        _seed_training_class(con, "WR", 2019)
        _seed_target_rookie(con, "early_pick", "WR", 2020, pick=5)  # round-1-ish pick number
        con.execute("UPDATE players SET draft_round = 1 WHERE player_id = 'early_pick'")
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('early_pick', 2020, 'WR', 15, 180.0, 12.0)"
        )
        breakdown = build_round_tier_breakdown(con, 2020, 2020)
        tiers_seen = {row["tier"] for row in breakdown}
        assert "early (rounds 1-2)" in tiers_seen

    def test_alpha_production_model_uses_the_real_feature_version(self, con):
        _seed_target_rookie(con, "alpha_pred", "RB", 2020, pick=10)
        con.execute("UPDATE players SET draft_round = 2 WHERE player_id = 'alpha_pred'")
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('alpha_pred', 2020, 'RB', 15, 150.0, 10.0)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, predicted_at) VALUES "
            "('pred1', 'alpha_pred', 2020, 'RB', ?, 140.0, current_timestamp)",
            [FEATURE_VERSION],
        )
        breakdown = build_round_tier_breakdown(con, 2020, 2020)
        alpha_rows = [r for r in breakdown if r["model"] == "ml_rookie_regression (production)"]
        assert len(alpha_rows) == 1
        assert alpha_rows[0]["mae"] == pytest.approx(10.0)

    def test_wrong_feature_version_is_not_picked_up(self, con):
        _seed_target_rookie(con, "stale_pred", "RB", 2020, pick=10)
        con.execute("UPDATE players SET draft_round = 2 WHERE player_id = 'stale_pred'")
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('stale_pred', 2020, 'RB', 15, 150.0, 10.0)"
        )
        con.execute(
            "INSERT INTO rookie_predictions (prediction_id, player_id, draft_class, position, "
            "model_version, predicted_rookie_points, predicted_at) VALUES "
            "('pred1', 'stale_pred', 2020, 'RB', 'some_old_version', 140.0, current_timestamp)"
        )
        breakdown = build_round_tier_breakdown(con, 2020, 2020)
        alpha_rows = [r for r in breakdown if r["model"] == "ml_rookie_regression (production)"]
        assert alpha_rows == []
