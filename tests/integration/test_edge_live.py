"""End-to-end model-vs-market EDGE against real, live-fetched data. Deselected by default;
run with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.market.dynasty_values import build_dynasty_values
from alpha_squad.market.edge import evaluate_historical_edge, run_edge_build
from alpha_squad.models.uncertainty.run import run_uncertainty
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = list(range(2018, 2026))


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

    record_snapshot(con, dp.fetch("fp_ecr_history"))
    build_market_snapshot(con, settings)  # now includes ro/do/rsf/dsf

    record_snapshot(con, dp.fetch("dynasty_values_players"))
    build_dynasty_values(con, settings)

    run_uncertainty(con, 2021, 2025, min_train_season=2018)

    yield con
    con.close()


def test_edge_build_produces_gated_actions_on_real_players(con_ready):
    con = con_ready
    report = run_edge_build(con, 2022, 2025, ecr_type="rsf")
    assert report.edges_written > 0, "expected real EDGE rows for at least one season"

    rows = con.execute(
        "SELECT action, rank_edge, projected_points_edge, confidence FROM edge_snapshot"
    ).fetchall()
    assert rows

    actions = {r[0] for r in rows}
    assert actions <= {"BUY", "SELL", "HOLD", "WATCH"}

    for action, rank_edge, points_edge, confidence in rows:
        if action in ("BUY", "SELL"):
            # The hard gating rule, re-verified against real stored output: BUY/SELL must
            # never occur on a small/absent points edge or low confidence.
            assert points_edge is not None
            assert abs(points_edge) >= 15.0
            assert abs(rank_edge) >= 15
            assert confidence is not None and confidence >= 0.5
            same_direction = (rank_edge > 0 and points_edge > 0) or (
                rank_edge < 0 and points_edge < 0
            )
            assert same_direction, "BUY/SELL action stored with disagreeing rank/points edges"


def test_dynasty_values_covers_real_current_players(con_ready):
    con = con_ready
    n = con.execute("SELECT count(*) FROM dynasty_values").fetchone()[0]
    assert n > 200, "expected several hundred real dynasty-valued players"
    row = con.execute(
        "SELECT value_1qb, value_2qb FROM dynasty_values WHERE value_2qb IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] > 0 and row[1] > 0


def test_historical_edge_validation_reports_real_outperformance_either_way(con_ready):
    con = con_ready
    run_edge_build(con, 2022, 2025, ecr_type="rsf")
    results = evaluate_historical_edge(con, 2022, 2025, ecr_type="rsf")
    assert results, "expected at least one scored (season, action) cohort"

    buy_results = [r for r in results if r["action"] == "BUY" and r["n"] > 0]
    assert buy_results, "expected at least one real BUY cohort with an evaluable outcome"
    for r in buy_results:
        assert r["mean_actual_points"] is not None
        # Not asserting outperformance is positive -- a negative result must be reported,
        # not hidden (CLAUDE.md). This just checks the pipeline produces a real, finite number.
        assert r["mean_outperformance_vs_market"] == r["mean_outperformance_vs_market"]  # not NaN

    stored = con.execute("SELECT count(*) FROM edge_validation_results").fetchone()[0]
    assert stored == len(results)
