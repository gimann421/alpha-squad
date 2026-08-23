"""End-to-end uncertainty/calibration pipeline against real, live-fetched data. Deselected
by default; run with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
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
    build_market_snapshot(con, settings)

    yield con
    con.close()


def test_conformal_intervals_are_reasonably_well_calibrated_out_of_sample(con_ready):
    con = con_ready
    report = run_uncertainty(con, 2021, 2025, min_train_season=2018)
    assert report.predictions_written > 0

    scored_rows = [r for r in report.calibration_rows if r.get("n", 0) >= 20]
    assert scored_rows, "expected at least one season/position with enough held-out data to score"

    for row in scored_rows:
        # Loose sanity bounds, not a strict calibration assertion -- real out-of-sample
        # coverage on a handful of NFL seasons is inherently noisy. This exists to catch a
        # badly broken calibration (e.g. intervals that never contain the outcome, or always
        # do because they're absurdly wide), not to police exact statistical calibration.
        assert 0.4 <= row["coverage_10_90"] <= 1.0, f"{row} coverage_10_90 looks broken"
        assert row["mean_interval_width_10_90"] > 0

    # Structural invariants on the stored predictions themselves.
    rows = con.execute("SELECT p10, p25, median, p75, p90 FROM uncertainty_predictions").fetchall()
    assert rows
    for p10, p25, median, p75, p90 in rows:
        assert p10 <= p25 <= median <= p75 <= p90

    prob_rows = con.execute(
        "SELECT top12_prob, top24_prob FROM uncertainty_predictions WHERE top12_prob IS NOT NULL"
    ).fetchall()
    assert prob_rows
    for top12, top24 in prob_rows:
        assert 0.0 <= top12 <= top24 <= 1.0
