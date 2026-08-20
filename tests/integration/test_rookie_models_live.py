"""End-to-end rookie modeling against real, live-fetched data. Deselected by default; run
with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.models.rookie.comps import find_historical_comps
from alpha_squad.models.rookie.train import run_rookie_models
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

    yield con
    con.close()


def test_rookie_models_produce_plausible_results_on_real_draft_classes(con_ready):
    con = con_ready
    n_rookie_rows = con.execute("SELECT count(*) FROM rookie_features").fetchone()[0]
    assert n_rookie_rows > 200, "expected several hundred real rookie-seasons across 2018-2025"

    report = run_rookie_models(con, 2021, 2025, min_train_class=2010)
    reg_results = [m for m in report.regression_metrics if m.n > 0]
    assert reg_results, "expected at least one evaluable rookie regression result"
    for m in reg_results:
        assert m.mae < 150, f"{m.model_name}/{m.season} MAE {m.mae} implausibly high"

    clf_results = [c for c in report.classification_metrics if c.n > 0]
    assert clf_results, "expected at least one evaluable breakout classification result"
    for c in clf_results:
        assert 0.0 <= c.brier_score <= 1.0
        assert 0.0 <= c.base_rate <= 1.0


def test_historical_comps_for_a_real_recent_rookie_are_plausible(con_ready):
    con = con_ready
    candidate = con.execute(
        "SELECT player_id FROM rookie_features WHERE draft_class = 2023 AND position = 'RB' LIMIT 1"
    ).fetchone()
    if candidate is None:
        pytest.skip("no 2023 RB rookie in this data slice")
    comps = find_historical_comps(con, candidate[0], 2023, "RB", k=5)
    assert comps
    assert all(c["draft_class"] < 2023 for c in comps)
    assert all(c["similarity_distance"] >= 0 for c in comps)
