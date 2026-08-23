"""End-to-end team-season Monte Carlo simulation against real, live-fetched data. Deselected
by default; run with `make test-network`. Deliberately narrow (one team, one target season,
3 prior seasons of history) -- this test's job is proving the simulation's real wiring against
genuine data (docs/DECISIONS.md D28/D29), not re-proving the underlying stats pipeline that
M3's own live test already covers."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.models.simulation.correlated import record_simulation_run, simulate_team_season
from alpha_squad.models.simulation.team_scores import build_team_week_points
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = [2022, 2023, 2024]
TARGET_SEASON = 2024
TEAM = "KC"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con_ready(settings):
    con = get_connection(settings)
    init_db(con)
    nflverse = NflverseSource(settings)
    dp = DynastyProcessSource(settings)

    for snap in [
        nflverse.fetch("players"),
        nflverse.fetch("draft_picks"),
        nflverse.fetch("combine"),
    ]:
        record_snapshot(con, snap)
    record_snapshot(con, dp.fetch("player_ids"))
    build_identity(con, settings)

    for season in SEASONS:
        for dataset in ("pbp", "stats_player_week", "snap_counts", "stats_team_week"):
            record_snapshot(con, nflverse.fetch(dataset, season=season))
    build_features(con, settings, SEASONS)
    build_team_week_points(con, settings, SEASONS)

    yield con
    con.close()


def test_team_week_points_excludes_postseason_on_real_data(con_ready):
    con = con_ready
    max_week = con.execute(
        "SELECT max(week) FROM team_week_points WHERE team = ? AND season = ?",
        [TEAM, TARGET_SEASON],
    ).fetchone()[0]
    # 2024 is an 18-week regular season; KC made a deep playoff run (weeks up to 22) that
    # docs/DECISIONS.md D28 requires never reach this table.
    assert max_week is not None and max_week <= 18

    game_types = con.execute(
        """
        SELECT DISTINCT g.game_type FROM team_week_points p
        JOIN games g ON g.game_id = p.game_id
        WHERE p.team = ? AND p.season = ?
        """,
        [TEAM, TARGET_SEASON],
    ).fetchall()
    assert game_types == [("REG",)]


def test_simulate_team_season_on_real_data_produces_a_positive_qb_wr1_correlation(con_ready):
    con = con_ready
    result = simulate_team_season(con, TEAM, TARGET_SEASON, n_simulations=500, seed=42)

    assert result is not None, "expected enough real prior-season history for KC"
    assert result.mean_team_points > 0
    assert result.std_team_points > 0
    assert len(result.players) >= 3, "expected multiple real skill players on the roster"

    for p in result.players:
        assert p.p10 <= p.p50 <= p.p90
        assert p.mean_points >= 0

    # The property this module exists to demonstrate empirically, not assume: a QB and his
    # top real pass-catcher share the same simulated pass-volume draw every trial, so they
    # must come out positively correlated (docs/DECISIONS.md D29).
    assert result.qb_wr1_correlation is not None
    assert result.qb_wr1_correlation > 0


def test_simulation_is_reproducible_on_real_data(con_ready):
    con = con_ready
    r1 = simulate_team_season(con, TEAM, TARGET_SEASON, n_simulations=300, seed=7)
    r2 = simulate_team_season(con, TEAM, TARGET_SEASON, n_simulations=300, seed=7)

    assert r1.mean_team_points == r2.mean_team_points
    assert r1.qb_wr1_correlation == r2.qb_wr1_correlation
    p1 = {p.player_id: p.mean_points for p in r1.players}
    p2 = {p.player_id: p.mean_points for p in r2.players}
    assert p1 == p2


def test_record_simulation_run_persists_a_real_summary_row(con_ready):
    con = con_ready
    result = simulate_team_season(con, TEAM, TARGET_SEASON, n_simulations=200, seed=1)
    run_id = record_simulation_run(con, result, seed=1)

    row = con.execute(
        "SELECT team, season, mean_team_points, qb_wr1_correlation FROM team_simulation_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    assert row == (TEAM, TARGET_SEASON, result.mean_team_points, result.qb_wr1_correlation)
