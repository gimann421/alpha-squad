"""Offline coverage for the M13 correlated team-season Monte Carlo simulation
(models/simulation/correlated.py, docs/DECISIONS.md D8/D29). All fixtures are synthetic and
hand-seeded directly into player_week_stats/team_week_stats/team_week_points -- no real
nflverse fetch -- covering both the public simulate_team_season entry point and the two
private share-computation helpers whose denominator bug (D29) is the whole reason this suite
exists: a share computed against only the "qualifying" players' own volume, then multiplied
against the team's full simulated volume, silently inflates every qualifying player's output."""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from alpha_squad.models.simulation.correlated import (
    MIN_TEAM_WEEKS,
    _pass_catcher_shares,
    _rb_shares,
    record_simulation_run,
    simulate_team_season,
)
from alpha_squad.storage.db import init_db

TEAM = "TST"
HIST_SEASON = 2024
SIM_SEASON = 2025

# Ten weeks of real-shaped, genuinely-varying team environment: pass volume and points move
# together by construction, so a test asserting a positive qb_wr1_correlation isn't hoping to
# get lucky with a degenerate (near-zero-variance) covariance matrix.
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


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_history(con, n_weeks: int = len(_HISTORY)) -> None:
    for wk, (plays, pass_rate, points) in enumerate(_HISTORY[:n_weeks], start=1):
        game_id = f"{HIST_SEASON}_{wk:02d}_{TEAM}_OPP"
        game_date = date(HIST_SEASON, 9, 1) + timedelta(weeks=wk - 1)
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
            "VALUES (?, ?, ?, 'REG', ?, ?, 'OPP') ON CONFLICT DO NOTHING",
            [game_id, HIST_SEASON, wk, game_date, TEAM],
        )
        con.execute(
            "INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, pass_rate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [TEAM, HIST_SEASON, wk, game_id, game_date, float(plays), pass_rate],
        )
        con.execute(
            "INSERT INTO team_week_points (team, season, week, game_id, points) VALUES (?, ?, ?, ?, ?)",
            [TEAM, HIST_SEASON, wk, game_id, points],
        )


def _seed_player_week(
    con,
    player_id,
    position,
    week,
    *,
    targets=0.0,
    carries=0.0,
    fantasy_points_ppr=0.0,
    offense_snap_pct=None,
) -> None:
    game_id = f"{SIM_SEASON}_{week:02d}_{TEAM}_OPP"
    game_date = date(SIM_SEASON, 9, 1) + timedelta(weeks=week - 1)
    con.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
        [player_id, f"00-test-{player_id}"],
    )
    con.execute(
        "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
        "VALUES (?, ?, ?, 'REG', ?, ?, 'OPP') ON CONFLICT DO NOTHING",
        [game_id, SIM_SEASON, week, game_date, TEAM],
    )
    # _starting_qb needs team_week_stats for the *simulated* season too (it divides that
    # season's real fantasy points by that season's real pass attempts), separate from
    # _seed_history's team_week_stats rows for HIST_SEASON (the environment draw's basis).
    con.execute(
        "INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, pass_rate) "
        "VALUES (?, ?, ?, ?, ?, 60.0, 0.6) ON CONFLICT DO NOTHING",
        [TEAM, SIM_SEASON, week, game_id, game_date],
    )
    con.execute(
        """
        INSERT INTO player_week_stats
            (player_id, season, week, game_id, game_date, team, position, targets, carries,
             fantasy_points_ppr, offense_snap_pct, source_snapshot_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test')
        """,
        [
            player_id,
            SIM_SEASON,
            week,
            game_id,
            game_date,
            TEAM,
            position,
            targets,
            carries,
            fantasy_points_ppr,
            offense_snap_pct,
        ],
    )


class TestSimulateTeamSeasonInsufficientHistory:
    def test_returns_none_below_min_team_weeks(self, con):
        _seed_history(con, n_weeks=MIN_TEAM_WEEKS - 1)
        result = simulate_team_season(con, TEAM, SIM_SEASON, n_simulations=50, seed=1)
        assert result is None

    def test_returns_none_for_an_unknown_team(self, con):
        _seed_history(con)
        result = simulate_team_season(con, "ZZZ", SIM_SEASON, n_simulations=50, seed=1)
        assert result is None


class TestSimulateTeamSeasonStructure:
    @pytest.fixture(autouse=True)
    def _seed(self, con):
        _seed_history(con)
        for wk in range(1, 9):
            _seed_player_week(con, "qb1", "QB", wk, fantasy_points_ppr=20.0, offense_snap_pct=0.95)
            _seed_player_week(con, "wr1", "WR", wk, targets=8.0, fantasy_points_ppr=14.0)
            _seed_player_week(con, "wr2", "WR", wk, targets=5.0, fantasy_points_ppr=8.0)
        self.con = con

    def test_returns_a_populated_result_with_plausible_shape(self):
        result = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=200, seed=1)
        assert result is not None
        assert result.team == TEAM
        assert result.season == SIM_SEASON
        assert result.mean_team_points > 0
        assert result.std_team_points > 0
        player_ids = {p.player_id for p in result.players}
        assert player_ids == {"qb1", "wr1", "wr2"}
        for p in result.players:
            assert p.p10 <= p.p50 <= p.p90
            assert p.std_points >= 0

    def test_qb_wr1_correlation_is_positive_on_a_positively_correlated_environment(self):
        result = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=500, seed=1)
        assert result.qb_wr1_correlation is not None
        assert result.qb_wr1_correlation > 0, (
            "QB and WR1 share the same pass_attempts draw each trial (docs/DECISIONS.md D29); "
            "on an environment where pass volume and points genuinely co-vary, the correlation "
            "must come out positive, not just close to zero"
        )

    def test_same_seed_is_bit_for_bit_reproducible(self):
        r1 = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=300, seed=7)
        r2 = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=300, seed=7)
        assert r1.mean_team_points == r2.mean_team_points
        assert r1.qb_wr1_correlation == r2.qb_wr1_correlation
        p1 = {p.player_id: (p.mean_points, p.std_points, p.p10, p.p50, p.p90) for p in r1.players}
        p2 = {p.player_id: (p.mean_points, p.std_points, p.p10, p.p50, p.p90) for p in r2.players}
        assert p1 == p2

    def test_different_seeds_produce_different_output(self):
        r1 = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=300, seed=1)
        r2 = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=300, seed=2)
        assert r1.mean_team_points != r2.mean_team_points

    def test_record_simulation_run_persists_the_team_level_summary(self):
        result = simulate_team_season(self.con, TEAM, SIM_SEASON, n_simulations=100, seed=3)
        run_id = record_simulation_run(self.con, result, seed=3)
        assert run_id.startswith("sim_")
        row = self.con.execute(
            "SELECT team, season, n_simulations, seed, mean_team_points, qb_wr1_correlation "
            "FROM team_simulation_runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        assert row == (TEAM, SIM_SEASON, 100, 3, result.mean_team_points, result.qb_wr1_correlation)


class TestShareDenominatorMatchesTeamTotalVolume:
    """Regression coverage for docs/DECISIONS.md D29: a qualifying player's share must be
    computed against the team's REAL TOTAL volume (all players, all positions), not just the
    sum of other qualifying players -- otherwise it gets multiplied against a differently-scaled
    number later (the team's full simulated pass_attempts/rush_attempts) and inflates."""

    def test_pass_catcher_share_denominator_includes_non_qualifying_targets(self, con):
        # wr1 qualifies (4 games). wr_below_threshold gets real targets but only 2 games, so it
        # does not qualify for its own share row -- but its targets must still count in the
        # denominator every qualifying player's share is computed against.
        for wk in range(1, 5):
            _seed_player_week(con, "wr1", "WR", wk, targets=6.0, fantasy_points_ppr=9.0)
        for wk in range(1, 3):
            _seed_player_week(
                con, "wr_below_threshold", "WR", wk, targets=6.0, fantasy_points_ppr=9.0
            )

        shares = _pass_catcher_shares(con, TEAM, SIM_SEASON)

        assert set(shares) == {"wr1"}
        team_total_targets = 4 * 6.0 + 2 * 6.0  # wr1's + the non-qualifying player's targets
        expected_share = (4 * 6.0) / team_total_targets
        _position, share, _efficiency = shares["wr1"]
        assert share == pytest.approx(expected_share)
        assert share < 1.0, "wr1 is not the only target on the team; its share must be < 100%"

    def test_rb_share_denominator_includes_non_qualifying_carries(self, con):
        for wk in range(1, 5):
            _seed_player_week(con, "rb1", "RB", wk, carries=15.0, fantasy_points_ppr=10.0)
        for wk in range(1, 3):
            _seed_player_week(
                con, "rb_below_threshold", "RB", wk, carries=15.0, fantasy_points_ppr=10.0
            )

        shares = _rb_shares(con, TEAM, SIM_SEASON)

        assert set(shares) == {"rb1"}
        team_total_carries = 4 * 15.0 + 2 * 15.0
        expected_share = (4 * 15.0) / team_total_carries
        _position, share, _efficiency = shares["rb1"]
        assert share == pytest.approx(expected_share)

    def test_empty_when_no_qualifying_players_exist(self, con):
        for wk in range(1, 3):
            _seed_player_week(
                con, "wr_below_threshold", "WR", wk, targets=6.0, fantasy_points_ppr=9.0
            )
        assert _pass_catcher_shares(con, TEAM, SIM_SEASON) == {}

    def test_empty_when_team_has_no_data_at_all(self, con):
        assert _pass_catcher_shares(con, TEAM, SIM_SEASON) == {}
        assert _rb_shares(con, TEAM, SIM_SEASON) == {}
