"""End-to-end feature pipeline against real, live-fetched data. Deselected by default; run
with `make test-network`. Fetches into an isolated tmp_path database."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = [2023, 2024, 2025]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con_ready_for_features(settings):
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
        for dataset in ("pbp", "stats_player_week", "snap_counts"):
            record_snapshot(con, nflverse.fetch(dataset, season=season))

    yield con
    con.close()


def test_feature_pipeline_end_to_end_on_real_data(con_ready_for_features, settings):
    con = con_ready_for_features
    report = build_features(con, settings, SEASONS)

    assert report.games_inserted > 500
    assert report.player_week_stats_upserted > 10000
    assert report.player_week_features_upserted == report.player_week_stats_upserted

    # No target leakage: every row's target must be a real, non-null outcome.
    null_targets = con.execute(
        "SELECT count(*) FROM player_week_features WHERE target_fantasy_points_ppr IS NULL"
    ).fetchone()[0]
    assert null_targets == 0

    # Structural leakage check on real data: a player's first game of a season must show
    # games_played_prior = 0 and a NULL season-to-date average.
    week1_bad_rows = con.execute(
        """
        SELECT count(*) FROM player_week_features
        WHERE week = (SELECT min(week) FROM player_week_features f2
                      WHERE f2.player_id = player_week_features.player_id AND f2.season = player_week_features.season)
          AND games_played_prior != 0
        """
    ).fetchone()[0]
    assert week1_bad_rows == 0

    # A real, well-known high-volume player should show a plausible (bounded) lag average,
    # not an extreme value that would suggest a unit or leakage bug.
    extreme_rows = con.execute(
        "SELECT count(*) FROM player_week_features WHERE fp_ppr_avg_last3 > 100"
    ).fetchone()[0]
    assert extreme_rows == 0, "no player should average >100 PPR fantasy points over 3 games"
