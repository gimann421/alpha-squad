"""End-to-end established-player ML against real, live-fetched data. Deselected by default;
run with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.models.established.season_level import run_season_level_established_ml
from alpha_squad.models.established.train import run_established_ml
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = list(range(2019, 2026))


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
    build_market_snapshot(con, settings)

    yield con
    con.close()


def test_weekly_established_ml_produces_plausible_metrics(con_ready):
    con = con_ready
    report = run_established_ml(con, 2023, 2025, min_train_season=2019)
    all_results = [m for m in report.metrics if m.n > 0]
    assert all_results, "expected at least one evaluable weekly ML result"
    for m in all_results:
        assert m.mae < 60, (
            f"{m.model_name}/{m.season} MAE {m.mae} implausibly high for an in-season model"
        )
        assert m.spearman > 0.5

    registry_rows = con.execute("SELECT count(*) FROM model_registry").fetchone()[0]
    assert registry_rows > 0, "trained models should be recorded in model_registry"


def test_season_level_ml_is_directly_comparable_to_m4_baselines(con_ready):
    con = con_ready
    report = run_season_level_established_ml(con, 2022, 2025, min_train_season=2019)
    all_results = [m for m in report.metrics if m.n > 0]
    assert all_results, "expected at least one evaluable season-level ML result"

    for m in all_results:
        # Same sanity floor as M4's baselines (tests/integration/test_baselines_live.py).
        assert m.mae < 120, f"{m.model_name}/{m.season} MAE {m.mae} implausibly high"
        assert m.spearman > 0.3
