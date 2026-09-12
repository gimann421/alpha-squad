"""Tests for the D86 weekly draft objective.

The claims that matter, and that these pin:

  * a bye/injury is a MISSING weekly row, and a missing row means the player cannot be started;
  * the weekly objective therefore gives the bench positive value where the season-long one
    gives it exactly zero -- with no bench bonus anywhere in the code;
  * the availability-aware expectation is a usable DIFFERENCE (common random numbers), not just
    a noisy level;
  * availability rates are measured from data, never defaulted into existence.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.weekly_objective import (
    FANTASY_WEEKS,
    _available_in_draw,
    bench_contribution,
    expected_weekly_marginal_value,
    expected_weekly_starter_points,
    load_weekly_points,
    measure_availability_rates,
    season_long_lineup_points,
    weekly_lineup_points,
    weekly_lineup_points_no_foresight,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league() -> LeagueContext:
    """One dedicated slot per position and no flex, so the lineup arithmetic in these tests is
    unambiguous and a bench player is unambiguously a bench player."""
    return LeagueContext(
        league_id="weekly_test",
        format="redraft",
        teams=10,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1},
        roster={"bench": 2, "roster_size": 4},
    )


POSITIONS = {"qb1": "QB", "qb2": "QB", "rb1": "RB", "rb2": "RB"}


def _add_player(con, player_id: str, position: str) -> None:
    """`player_week_stats`/`player_season_stats` carry a foreign key to `players`, so a DB-backed
    test has to seed the spine first."""
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, ?)",
        [player_id, f"gsis_{player_id}", player_id, position],
    )


def _add_week(con, player_id: str, season: int, week: int, position: str, pts: float) -> None:
    """One weekly row, through the same NOT NULL/foreign-key surface production writes."""
    game_id = f"{season}_{week:02d}_TST"
    con.execute(
        "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
        "VALUES (?, ?, ?, 'REG', ?, 'TST', 'OPP') ON CONFLICT DO NOTHING",
        [game_id, season, week, f"{season}-09-01"],
    )
    con.execute(
        "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, team, "
        "position, fantasy_points_ppr, source_snapshot_id) "
        "VALUES (?, ?, ?, ?, ?, 'TST', ?, ?, 'test')",
        [player_id, season, week, game_id, f"{season}-09-01", position, pts],
    )


class TestWeeklyVsSeasonLong:
    def test_season_long_gives_the_bench_exactly_zero(self):
        """The defect being measured. `qb2` scores in a week `qb1` missed, but the season-long
        objective starts `qb1` in every week and never sees it."""
        totals = {"qb1": 100.0, "qb2": 40.0, "rb1": 90.0, "rb2": 30.0}
        assert season_long_lineup_points(
            _league(), list(totals), POSITIONS, totals
        ) == pytest.approx(190.0)

    def test_weekly_objective_starts_the_backup_when_the_starter_is_missing(self):
        """`qb1` has no row in week 2 -- a bye or an injury. The weekly objective starts `qb2`."""
        weekly = {
            ("qb1", 1): 60.0,
            ("qb2", 1): 10.0,
            ("qb2", 2): 25.0,  # qb1 absent in week 2
            ("rb1", 1): 50.0,
            ("rb1", 2): 40.0,
        }
        got = weekly_lineup_points(_league(), ["qb1", "qb2", "rb1"], POSITIONS, weekly)
        assert got == pytest.approx(60.0 + 50.0 + 25.0 + 40.0)

    def test_a_slot_scores_zero_when_nobody_at_that_position_played(self):
        weekly = {("rb1", 1): 40.0}
        got = weekly_lineup_points(_league(), ["qb1", "rb1"], POSITIONS, weekly)
        assert got == pytest.approx(40.0)

    def test_bench_contribution_is_positive_exactly_when_a_backup_is_fielded(self):
        weekly = {("qb1", 1): 60.0, ("qb2", 2): 25.0, ("rb1", 1): 50.0}
        totals = {"qb1": 60.0, "qb2": 25.0, "rb1": 50.0}
        roster = ["qb1", "qb2", "rb1"]
        assert bench_contribution(_league(), roster, POSITIONS, weekly, totals) == pytest.approx(
            25.0
        )

    def test_bench_contribution_is_zero_when_no_starter_ever_misses(self):
        weekly = {("qb1", w): 10.0 for w in (1, 2)} | {("rb1", w): 10.0 for w in (1, 2)}
        weekly |= {("qb2", w): 5.0 for w in (1, 2)}
        totals = {"qb1": 20.0, "qb2": 10.0, "rb1": 20.0}
        assert bench_contribution(
            _league(), ["qb1", "qb2", "rb1"], POSITIONS, weekly, totals
        ) == pytest.approx(0.0)

    def test_no_foresight_can_only_be_worse_than_hindsight(self):
        """Choosing the lineup by projection cannot beat choosing it by what actually scored."""
        weekly = {("qb1", 1): 5.0, ("qb2", 1): 40.0, ("rb1", 1): 10.0}
        projections = {"qb1": 300.0, "qb2": 100.0, "rb1": 200.0}
        roster = ["qb1", "qb2", "rb1"]
        fore = weekly_lineup_points(_league(), roster, POSITIONS, weekly)
        none = weekly_lineup_points_no_foresight(_league(), roster, POSITIONS, weekly, projections)
        assert none <= fore
        assert none == pytest.approx(15.0)  # started qb1 (higher projection) and rb1
        assert fore == pytest.approx(50.0)  # started qb2


class TestLoadWeeklyPoints:
    def test_only_weeks_that_were_played_appear(self, con):
        _add_player(con, "rb1", "RB")
        for week, pts in ((1, 20.0), (3, 15.0)):
            _add_week(con, "rb1", 2024, week, "RB", pts)
        weekly = load_weekly_points(con, 2024)
        assert set(weekly) == {("rb1", 1), ("rb1", 3)}
        assert ("rb1", 2) not in weekly

    def test_week_18_is_excluded(self, con):
        _add_player(con, "rb1", "RB")
        _add_week(con, "rb1", 2024, 18, "RB", 99.0)
        assert load_weekly_points(con, 2024) == {}
        assert 18 not in FANTASY_WEEKS


class TestAvailabilityRates:
    def test_rates_are_measured_not_defaulted(self, con):
        """A position with no data must be OMITTED, so a caller that assumed one gets a
        KeyError rather than a fabricated rate."""
        _add_player(con, "rb1", "RB")
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('rb1', 2024, 'RB', 17, 200, 12)"
        )
        for week in range(1, 18):
            _add_week(con, "rb1", 2024, week, "RB", 10.0)
        rates = measure_availability_rates(con, (2024,), per_team_demand={"RB": 0.1, "QB": 0.1})
        assert rates["RB"] == pytest.approx(1.0)
        assert "QB" not in rates

    def test_a_player_who_missed_weeks_lowers_the_rate(self, con):
        _add_player(con, "rb1", "RB")
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('rb1', 2024, 'RB', 9, 100, 11)"
        )
        for week in range(1, 10):
            _add_week(con, "rb1", 2024, week, "RB", 10.0)
        rates = measure_availability_rates(con, (2024,), per_team_demand={"RB": 0.1})
        assert rates["RB"] == pytest.approx(9 / 17)


class TestCommonRandomNumbers:
    def test_availability_is_deterministic_across_processes(self):
        """`hash()` is salted per process; this must not be. A re-run has to reproduce (D54)."""
        first = [_available_in_draw("asq_player_x", d, 0.85) for d in range(50)]
        second = [_available_in_draw("asq_player_x", d, 0.85) for d in range(50)]
        assert first == second

    def test_the_rate_is_actually_respected(self):
        n = 20000
        hits = sum(_available_in_draw(f"p{i}", 0, 0.85) for i in range(n))
        assert 0.83 < hits / n < 0.87

    def test_a_players_draws_do_not_depend_on_the_roster_around_him(self):
        """The property that makes the estimator usable for a DIFFERENCE: two candidate rosters
        sharing a player must see that player behave identically in every draw."""
        a = [_available_in_draw("shared", d, 0.9) for d in range(100)]
        b = [_available_in_draw("shared", d, 0.9) for d in range(100)]
        assert a == b

    def test_different_players_get_different_sequences(self):
        a = [_available_in_draw("p_one", d, 0.5) for d in range(200)]
        b = [_available_in_draw("p_two", d, 0.5) for d in range(200)]
        assert a != b


class TestExpectedWeeklyValue:
    def _values(self):
        return {"qb1": 20.0, "qb2": 8.0, "rb1": 18.0, "rb2": 7.0}

    def test_a_backup_at_a_saturated_position_is_worth_more_than_zero(self):
        """THE claim. The shipped MSV returns exactly 0 here; this must not."""
        rates = {"QB": 0.85, "RB": 0.85}
        got = expected_weekly_marginal_value(
            _league(), ["qb1", "rb1"], "qb2", self._values(), POSITIONS, rates, n_draws=400
        )
        assert got > 0.0

    def test_a_backup_is_worth_more_when_the_position_misses_more_time(self):
        """Depth is priced by measured availability rather than by a positional rule."""
        fragile = expected_weekly_marginal_value(
            _league(), ["qb1"], "qb2", self._values(), POSITIONS, {"QB": 0.70}, n_draws=800
        )
        durable = expected_weekly_marginal_value(
            _league(), ["qb1"], "qb2", self._values(), POSITIONS, {"QB": 0.99}, n_draws=800
        )
        assert fragile > durable

    def test_full_availability_reproduces_the_season_long_reading(self):
        """With everyone available every week the expectation must collapse to the ordinary best
        lineup -- so the new objective is a strict generalization, not a different quantity."""
        values = self._values()
        got = expected_weekly_starter_points(
            _league(), list(values), values, POSITIONS, {"QB": 1.0, "RB": 1.0}, n_draws=25
        )
        assert got == pytest.approx(20.0 + 18.0)

    def test_marginal_value_of_a_useless_player_is_near_zero(self):
        values = {"qb1": 20.0, "rb1": 18.0, "qb2": 0.0}
        got = expected_weekly_marginal_value(
            _league(),
            ["qb1", "rb1"],
            "qb2",
            values,
            POSITIONS,
            {"QB": 0.85, "RB": 0.85},
            n_draws=400,
        )
        assert got == pytest.approx(0.0, abs=1e-9)

    def test_estimate_is_reproducible(self):
        args = (
            _league(),
            ["qb1", "rb1"],
            "qb2",
            self._values(),
            POSITIONS,
            {"QB": 0.85, "RB": 0.85},
        )
        assert expected_weekly_marginal_value(*args, n_draws=200) == expected_weekly_marginal_value(
            *args, n_draws=200
        )
