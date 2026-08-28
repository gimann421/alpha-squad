"""Unit tests for the market-inefficiency 5-tier stratification (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.market_inefficiency import (
    AGREE,
    EVIDENCE_BACKED_DISAGREE,
    HIGH_CONFIDENCE_DISAGREE,
    HIGH_CONFIDENCE_THRESHOLD,
    MILD_DISAGREE,
    MILD_THRESHOLD,
    STRONG_DISAGREE,
    STRONG_THRESHOLD,
    _tier_for,
    build_market_inefficiency_tiers,
    write_market_inefficiency_report,
)
from alpha_squad.market.edge import DEFAULT_ECR_TYPE
from alpha_squad.market.series import series_for_ecr_type
from alpha_squad.storage.db import init_db


class TestTierBoundaries:
    def test_below_mild_threshold_is_agree(self):
        assert _tier_for("WATCH", MILD_THRESHOLD - 1, confidence=0.9) == AGREE

    def test_at_mild_threshold_is_mild_disagree(self):
        assert _tier_for("WATCH", MILD_THRESHOLD, confidence=0.9) == MILD_DISAGREE

    def test_at_strong_threshold_is_strong_disagree(self):
        assert _tier_for("WATCH", STRONG_THRESHOLD, confidence=0.5) == STRONG_DISAGREE

    def test_strong_plus_high_confidence_is_high_confidence_tier(self):
        assert (
            _tier_for("WATCH", STRONG_THRESHOLD, confidence=HIGH_CONFIDENCE_THRESHOLD)
            == HIGH_CONFIDENCE_DISAGREE
        )

    def test_negative_rank_edge_uses_absolute_value(self):
        assert _tier_for("WATCH", -STRONG_THRESHOLD, confidence=0.5) == STRONG_DISAGREE

    def test_buy_action_is_always_evidence_backed_regardless_of_magnitude(self):
        assert _tier_for("BUY", rank_edge=1, confidence=0.1) == EVIDENCE_BACKED_DISAGREE

    def test_sell_action_is_always_evidence_backed(self):
        assert _tier_for("SELL", rank_edge=1, confidence=0.1) == EVIDENCE_BACKED_DISAGREE

    def test_hold_with_no_confidence_never_crashes(self):
        assert _tier_for("HOLD", STRONG_THRESHOLD, confidence=None) == STRONG_DISAGREE


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_edge_row(
    con,
    player_id,
    season,
    action,
    rank_edge,
    market_rank,
    confidence,
    actual_points,
    ecr_type=DEFAULT_ECR_TYPE,
):
    con.execute(
        """
        INSERT INTO edge_snapshot
            (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
             market_rank, rank_edge, projected_points_edge, probability_edge, evidence_score,
             confidence, action, reasons_json, built_at)
        VALUES (?, ?, ?, 'WR', ?, 'edge_v1', ?, ?, ?, 0.0, 0.0, 0.5, ?, ?, '[]', current_timestamp)
        """,
        [
            f"edge_{player_id}_{season}",
            player_id,
            season,
            ecr_type,
            max(int(market_rank) - rank_edge, 1),
            market_rank,
            rank_edge,
            confidence,
            action,
        ],
    )
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'WR', 15, ?, ?)",
        [player_id, season, actual_points, actual_points / 15],
    )


def _seed_market_curve_training(con, season_before, ecr_type=DEFAULT_ECR_TYPE):
    """A minimal training set so `_market_implied_points_curve` (built on 'ro'-shaped
    preseason rank->points history) has enough rows to fit -- real seasons strictly before
    the target season, matching the module's own leakage-safe pattern."""
    for i in range(15):
        player_id = f"train_{i}"
        rank = float(i + 1)
        points = 300.0 - i * 10
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES (?, ?, ?, 'WR', ?, ?)",
            [
                player_id,
                f"{season_before}-08-01",
                ecr_type,
                rank,
                series_for_ecr_type(ecr_type).page_type,
            ],
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'WR', 15, ?, ?)",
            [player_id, season_before, points, points / 15],
        )


class TestBuildMarketInefficiencyTiers:
    def test_empty_data_returns_zero_n_for_every_tier(self, con):
        tiers = build_market_inefficiency_tiers(con, 2023, 2023)
        assert len(tiers) == 5
        assert all(t.n == 0 for t in tiers)

    def test_buy_and_sell_rows_land_in_evidence_backed_tier(self, con):
        _seed_market_curve_training(con, 2022)
        _seed_edge_row(
            con,
            "buyer",
            2023,
            "BUY",
            rank_edge=50,
            market_rank=100,
            confidence=0.9,
            actual_points=400.0,
        )
        _seed_edge_row(
            con,
            "seller",
            2023,
            "SELL",
            rank_edge=-50,
            market_rank=50,
            confidence=0.9,
            actual_points=10.0,
        )
        tiers = build_market_inefficiency_tiers(con, 2023, 2023)
        by_tier = {t.tier: t for t in tiers}
        assert by_tier[EVIDENCE_BACKED_DISAGREE].n == 2

    def test_watch_row_with_small_edge_lands_in_agree_tier(self, con):
        _seed_market_curve_training(con, 2022)
        _seed_edge_row(
            con,
            "neutral",
            2023,
            "WATCH",
            rank_edge=1,
            market_rank=100,
            confidence=0.5,
            actual_points=200.0,
        )
        tiers = build_market_inefficiency_tiers(con, 2023, 2023)
        by_tier = {t.tier: t for t in tiers}
        assert by_tier[AGREE].n == 1
        assert by_tier[MILD_DISAGREE].n == 0

    def test_sell_signed_edge_rewards_underperformance(self, con):
        """A good SELL call (player scored far below what the market implied) must produce a
        *positive* signed_edge -- the whole point of flipping SELL's sign."""
        _seed_market_curve_training(con, 2022)
        _seed_edge_row(
            con,
            "goodsell",
            2023,
            "SELL",
            rank_edge=-50,
            market_rank=5,
            confidence=0.9,
            actual_points=1.0,
        )
        tiers = build_market_inefficiency_tiers(con, 2023, 2023)
        by_tier = {t.tier: t for t in tiers}
        assert by_tier[EVIDENCE_BACKED_DISAGREE].mean_signed_edge > 0


class TestWriteMarketInefficiencyReport:
    def test_does_not_crash_on_a_cleanly_monotonic_real_result(self, con, tmp_path):
        """Regression (D54): the monotonic check used
        `zip(tiers, tiers[1:], strict=True)` -- comparing the fixed 5-tier list against its
        own one-shifted tail always differs in length by exactly one, so `strict=True` raises
        ValueError as soon as the shorter side is exhausted. That happens precisely when every
        tier-to-tier comparison is True (`all()` only short-circuits earlier on a False), i.e.
        exactly the *cleanly monotonic* result this report exists to detect. Found live: a
        real 7-round dynasty pick-value result hit the identical pattern and crashed; this
        test reproduces the same shape for the 5-tier market-inefficiency report specifically,
        with a real signed_edge that increases at every one of the 5 tiers."""
        _seed_market_curve_training(con, 2022)
        # market_rank=100 clips to the same implied-points constant for every row below (all
        # same season/market_rank), so a widening spread of real actual_points alone produces
        # a strictly increasing signed_edge across tiers regardless of that constant's value.
        _seed_edge_row(
            con,
            "agree",
            2023,
            "WATCH",
            rank_edge=1,
            market_rank=100,
            confidence=0.5,
            actual_points=50.0,
        )
        _seed_edge_row(
            con,
            "mild",
            2023,
            "WATCH",
            rank_edge=MILD_THRESHOLD,
            market_rank=100,
            confidence=0.5,
            actual_points=100.0,
        )
        _seed_edge_row(
            con,
            "strong",
            2023,
            "WATCH",
            rank_edge=STRONG_THRESHOLD,
            market_rank=100,
            confidence=0.5,
            actual_points=150.0,
        )
        _seed_edge_row(
            con,
            "highconf",
            2023,
            "WATCH",
            rank_edge=STRONG_THRESHOLD,
            market_rank=100,
            confidence=HIGH_CONFIDENCE_THRESHOLD,
            actual_points=200.0,
        )
        _seed_edge_row(
            con,
            "evidence",
            2023,
            "BUY",
            rank_edge=1,
            market_rank=100,
            confidence=0.9,
            actual_points=250.0,
        )

        report_path = tmp_path / "market_inefficiency_report.md"
        tiers = write_market_inefficiency_report(con, report_path, 2023, 2023)

        assert report_path.exists()
        assert "Monotonic" in report_path.read_text()
        assert [t.n for t in tiers] == [1, 1, 1, 1, 1]
