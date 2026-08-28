"""Unit tests for the simple historical baselines and the ECR-implied baseline's
walk-forward calibration discipline — the latter is effectively a leakage test for the
market-implied baseline (it must never fit its rank-to-points curve on the season it's
predicting)."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from alpha_squad.models.baselines.market_implied import ecr_implied_baseline
from alpha_squad.models.baselines.simple import previous_year_baseline, weighted_two_year_baseline
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_season(con, player_id: str, season: int, total_points: float, position: str = "WR"):
    con.execute(
        """
        INSERT INTO player_season_stats
            (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game)
        VALUES (?, ?, ?, 15, ?, ?)
        """,
        [player_id, season, position, total_points, total_points / 15],
    )


class TestSimpleBaselines:
    def test_previous_year_uses_only_season_minus_one(self, con):
        _seed_season(con, "p1", 2022, 100.0)
        _seed_season(con, "p1", 2023, 200.0)
        preds = previous_year_baseline(con, 2024)
        assert preds == {"p1": 200.0}

    def test_previous_year_excludes_players_without_a_prior_season(self, con):
        _seed_season(con, "p1", 2023, 200.0)
        preds = previous_year_baseline(con, 2024)
        assert "p1" in preds
        preds_next = previous_year_baseline(con, 2023)
        assert preds_next == {}

    def test_weighted_two_year_matches_hand_computation(self, con):
        _seed_season(con, "p1", 2022, 100.0)
        _seed_season(con, "p1", 2023, 200.0)
        preds = weighted_two_year_baseline(con, 2024, w1=0.65, w2=0.35)
        assert preds["p1"] == pytest.approx(0.65 * 200.0 + 0.35 * 100.0)

    def test_weighted_two_year_requires_both_prior_seasons(self, con):
        _seed_season(con, "p1", 2023, 200.0)  # only S-1, no S-2
        preds = weighted_two_year_baseline(con, 2024)
        assert preds == {}


class TestEcrImpliedWalkForwardDiscipline:
    def _seed_market(self, con, player_id: str, season: int, position: str, rank: float):
        con.execute(
            """
            INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type)
            VALUES (?, ?, 'ro', ?, ?, 'redraft-overall')
            """,
            [player_id, date(season, 8, 15), position, rank],
        )

    def test_calibration_never_uses_the_target_season(self, con):
        """If the target season's own (rank, actual points) pair leaked into the
        calibration set, a rank that only appears in the target season would still produce
        a fitted curve; this seeds enough *other* seasons for a real curve and then checks
        the target season's own data point doesn't change the outcome."""
        # Needs >= _MIN_TRAINING_ROWS (10) distinct rows for the calibration curve to fit
        # at all; spread across several ranks/seasons so it's a plausible curve, not a
        # degenerate single-point fit.
        for season in (2020, 2021, 2022, 2023):
            for i, rank in enumerate((1.0, 5.0, 10.0, 15.0)):
                _seed_season(con, f"train_{season}_{i}", season, 100.0 - rank * 3, position="WR")
                self._seed_market(con, f"train_{season}_{i}", season, "WR", rank=rank)

        # A poisoned target-season entry: if this leaked into training, the curve would be
        # pulled toward 99999.0 for rank 10.
        _seed_season(con, "target_player", 2024, 99999.0, position="WR")
        self._seed_market(con, "target_player", 2024, "WR", rank=10.0)
        self._seed_market(con, "query_player", 2024, "WR", rank=10.0)

        preds = ecr_implied_baseline(con, 2024)
        assert preds["query_player"] < 1000.0, (
            "target season's own outcome leaked into the calibration curve"
        )

    def test_insufficient_history_skips_a_position_rather_than_guessing(self, con):
        for i in range(3):
            _seed_season(con, f"p{i}", 2023, 50.0 + i, position="TE")
            self._seed_market(con, f"p{i}", 2023, "TE", rank=float(i + 1))
        self._seed_market(con, "query", 2024, "TE", rank=1.0)
        preds = ecr_implied_baseline(con, 2024)
        assert "query" not in preds, "should not produce a prediction from <10 training rows"
