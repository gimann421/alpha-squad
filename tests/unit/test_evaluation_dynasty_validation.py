"""Unit tests for pick-value/age-curve heuristic validation against real-shaped synthetic
history (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.dynasty_validation import (
    build_age_curve_validation,
    build_pick_value_validation,
    write_dynasty_validation_report,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_player(con, player_id, position, draft_year, draft_round, rookie_season, birth_date=None):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position, draft_year, "
        "draft_round, draft_pick, rookie_season, birth_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            player_id,
            f"gsis_{player_id}",
            player_id,
            position,
            draft_year,
            draft_round,
            draft_round * 30,
            rookie_season,
            birth_date,
        ],
    )


def _seed_stats(con, player_id, season, position, points, games=15):
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, ?, ?, ?)",
        [player_id, season, position, games, points, points / games],
    )


class TestPickValueValidation:
    def test_round_1_outscores_round_3_when_real_data_says_so(self, con):
        _seed_player(con, "r1_pick", "WR", 2015, 1, 2015)
        _seed_stats(con, "r1_pick", 2015, "WR", 300.0)
        _seed_player(con, "r3_pick", "WR", 2015, 3, 2015)
        _seed_stats(con, "r3_pick", 2015, "WR", 50.0)

        results = build_pick_value_validation(con, draft_year_start=2012, draft_year_end=2020)
        by_round = {r.round: r for r in results}
        assert by_round[1].mean_rookie_season_points > by_round[3].mean_rookie_season_points

    def test_reports_the_real_reversal_when_data_contradicts_the_heuristic(self, con):
        """The whole point of this module is to report reality, even when a late-round pick
        actually outscored an early one -- it must not silently reorder or hide that."""
        _seed_player(con, "r1_bust", "RB", 2015, 1, 2015)
        _seed_stats(con, "r1_bust", 2015, "RB", 10.0)
        _seed_player(con, "r4_steal", "RB", 2015, 4, 2015)
        _seed_stats(con, "r4_steal", 2015, "RB", 200.0)

        results = build_pick_value_validation(con, draft_year_start=2012, draft_year_end=2020)
        by_round = {r.round: r for r in results}
        assert by_round[1].mean_rookie_season_points < by_round[4].mean_rookie_season_points

    def test_player_with_no_real_outcome_is_excluded_not_zero_filled(self, con):
        _seed_player(con, "never_played", "WR", 2015, 2, 2015)
        # no player_season_stats row at all
        results = build_pick_value_validation(con, draft_year_start=2012, draft_year_end=2020)
        by_round = {r.round: r for r in results}
        assert 2 not in by_round or by_round[2].n_players == 0

    def test_best_of_first_3_seasons_takes_the_real_max(self, con):
        _seed_player(con, "grower", "TE", 2015, 2, 2015)
        _seed_stats(con, "grower", 2015, "TE", 20.0)
        _seed_stats(con, "grower", 2016, "TE", 150.0)
        _seed_stats(con, "grower", 2017, "TE", 80.0)
        results = build_pick_value_validation(con, draft_year_start=2012, draft_year_end=2020)
        by_round = {r.round: r for r in results}
        assert by_round[2].mean_rookie_season_points == 20.0
        assert by_round[2].mean_best_of_first3_points == 150.0


class TestAgeCurveValidation:
    def test_excludes_seasons_below_min_games(self, con):
        _seed_player(con, "injured", "RB", 2018, 1, 2018, birth_date="1996-01-01")
        _seed_stats(con, "injured", 2020, "RB", 20.0, games=1)  # below MIN_GAMES_FOR_AGE_CURVE
        points = build_age_curve_validation(con, season_start=2020, season_end=2020)
        assert points == []

    def test_includes_a_real_qualifying_season(self, con):
        _seed_player(con, "healthy", "WR", 2018, 1, 2018, birth_date="1996-01-01")
        _seed_stats(con, "healthy", 2020, "WR", 150.0, games=16)
        points = build_age_curve_validation(con, season_start=2020, season_end=2020)
        assert len(points) == 1
        assert points[0].position == "WR"
        assert points[0].age == 24  # 1996 birth, age as of Sept 1 2020

    def test_excludes_players_with_no_birth_date(self, con):
        _seed_player(con, "unknown_age", "RB", 2018, 1, 2018, birth_date=None)
        _seed_stats(con, "unknown_age", 2020, "RB", 150.0, games=16)
        points = build_age_curve_validation(con, season_start=2020, season_end=2020)
        assert points == []

    def test_averages_multiple_players_at_the_same_age(self, con):
        _seed_player(con, "p1", "RB", 2018, 1, 2018, birth_date="1996-01-01")
        _seed_stats(con, "p1", 2020, "RB", 160.0, games=16)  # 10.0 ppg
        _seed_player(con, "p2", "RB", 2019, 1, 2019, birth_date="1996-06-01")
        _seed_stats(con, "p2", 2020, "RB", 320.0, games=16)  # 20.0 ppg
        points = build_age_curve_validation(con, season_start=2020, season_end=2020)
        assert len(points) == 1
        assert points[0].n == 2
        assert points[0].mean_ppr_points_per_game == pytest.approx(15.0)


class TestWriteDynastyValidationReport:
    def test_does_not_crash_on_a_cleanly_monotonic_real_result(self, con, tmp_path):
        """Regression (D54): `write_dynasty_validation_report`'s monotonic check used
        `zip(pick_outcomes, pick_outcomes[1:], strict=True)` -- comparing a list against its
        own one-shifted tail always differs in length by exactly one, so `strict=True` raises
        ValueError as soon as the shorter side is exhausted. That happens precisely when every
        single comparison is True (`all()` only short-circuits earlier if it hits a False),
        i.e. exactly the *cleanly monotonic* case this report is designed to detect and
        celebrate. Found live: a real 7-round pick-value result, perfectly monotonically
        decreasing, crashed this exact line. Three-plus rounds are needed to actually exercise
        multiple zip pairs (with only two rounds there is only one pair, which never reaches
        the failure mode)."""
        for round_no, points in ((1, 300.0), (2, 200.0), (3, 100.0), (4, 50.0)):
            player_id = f"r{round_no}"
            _seed_player(con, player_id, "WR", 2015, round_no, 2015)
            _seed_stats(con, player_id, 2015, "WR", points)
        _seed_player(con, "aged", "RB", 2018, 1, 2018, birth_date="1996-01-01")
        _seed_stats(con, "aged", 2020, "RB", 150.0, games=16)

        report_path = tmp_path / "dynasty_report.md"
        result = write_dynasty_validation_report(con, report_path, draft_year_end=2020)

        assert report_path.exists()
        assert "Monotonic" in report_path.read_text()
        assert len(result["pick_outcomes"]) == 4
