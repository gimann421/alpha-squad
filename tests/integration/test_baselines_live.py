"""End-to-end baseline pipeline against real, live-fetched data. Deselected by default; run
with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.models.baselines.run import run_baselines
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
def con_ready_for_baselines(settings):
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
    build_features(con, settings, SEASONS)

    record_snapshot(con, dp.fetch("fp_ecr_history"))
    build_market_snapshot(con, settings)

    yield con
    con.close()


def test_baselines_beat_a_trivial_zero_predictor_on_real_data(con_ready_for_baselines):
    con = con_ready_for_baselines
    results = run_baselines(con, list(range(2019, 2026)))
    all_position_results = [r for r in results if r.position == "ALL" and r.n > 0]
    assert all_position_results, "expected at least one baseline to produce evaluable predictions"

    for m in all_position_results:
        # A trivial "predict 0 points for everyone" baseline would have MAE equal to the
        # mean actual points (~50-150 for a broad player pool); every real baseline should
        # do meaningfully better than that sanity floor.
        assert m.mae < 100, f"{m.model_name}/{m.season} MAE {m.mae} looks implausibly bad"
        assert m.spearman > 0.3, (
            f"{m.model_name}/{m.season} shows no rank correlation with outcomes"
        )

    previous_year_results = [
        r for r in all_position_results if r.model_name == "baseline_previous_year"
    ]
    assert previous_year_results, (
        "previous_year baseline should have produced results across these seasons"
    )
    for m in previous_year_results:
        assert m.spearman > 0.6, (
            "previous-year points should correlate strongly with next-year points"
        )
