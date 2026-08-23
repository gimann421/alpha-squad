"""End-to-end evidence engine against real, live-fetched data. Deselected by default; run
with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.evidence.events import build_evidence_events_range
from alpha_squad.evidence.prior_update import MAX_ADJUSTMENT_PCT, run_prior_update
from alpha_squad.evidence.taxonomy import EVENT_TYPE_STRENGTH
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.models.established.train import run_established_ml
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = list(range(2019, 2025))


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
        for dataset in (
            "pbp",
            "stats_player_week",
            "snap_counts",
            "stats_team_week",
            "depth_charts",
            "injuries",
            "weekly_rosters",
        ):
            record_snapshot(con, nflverse.fetch(dataset, season=season))
    build_features(con, settings, SEASONS)

    yield con
    con.close()


def test_evidence_detectors_produce_real_structurally_valid_events(con_ready):
    con = con_ready
    report = build_evidence_events_range(con, 2023, 2024)
    assert report.events_written > 0, "expected real evidence events across real 2023-2024 data"
    assert set(report.by_type) & {
        "depth_chart_promotion/demotion",
        "injury_events",
        "roster_transaction",
        "usage_share_shift",
    }

    rows = con.execute(
        "SELECT event_type, direction, strength_label, strength, event_date, week, season FROM evidence_events"
    ).fetchall()
    assert rows
    for event_type, direction, strength_label, strength, _event_date, week, season in rows:
        assert event_type in EVENT_TYPE_STRENGTH
        assert direction in (-1, 0, 1)
        assert strength_label in ("STRONG", "MEDIUM", "WEAK")
        assert 0.0 < strength <= 1.0
        assert season in (2023, 2024)
        assert week >= 1


def test_injury_teammate_opportunity_events_are_real_and_directional(con_ready):
    con = con_ready
    build_evidence_events_range(con, 2023, 2024)
    rows = con.execute(
        "SELECT direction FROM evidence_events WHERE event_type = 'injury_teammate_opportunity'"
    ).fetchall()
    assert rows, "expected at least one real teammate-opportunity event across 2023-2024"
    assert all(direction == 1 for (direction,) in rows)


def test_evidence_never_overwrites_the_real_weekly_projection(con_ready):
    con = con_ready
    build_evidence_events_range(con, 2023, 2024)
    run_established_ml(con, 2024, 2024, min_train_season=2019)

    n_base = con.execute(
        "SELECT count(*) FROM weekly_projection_snapshot WHERE model_name='ml_catboost' AND season=2024"
    ).fetchone()[0]
    assert n_base > 0, "expected real persisted weekly ml_catboost predictions for 2024"

    before = {
        (r[0], r[1]): r[2]
        for r in con.execute(
            "SELECT player_id, week, predicted_points FROM weekly_projection_snapshot "
            "WHERE model_name='ml_catboost' AND season=2024"
        ).fetchall()
    }

    deltas = run_prior_update(con, 2024, 8)
    assert deltas, "expected real deltas for at least one player in week 8"

    after = {
        (r[0], r[1]): r[2]
        for r in con.execute(
            "SELECT player_id, week, predicted_points FROM weekly_projection_snapshot "
            "WHERE model_name='ml_catboost' AND season=2024"
        ).fetchall()
    }
    assert before == after, "weekly_projection_snapshot must never be mutated by evidence"

    for d in deltas:
        assert abs(d.adjustment_pct) <= MAX_ADJUSTMENT_PCT + 1e-9
        if abs(d.adjustment_pct) > 1e-9:
            assert d.reason
            assert d.evidence_ids

    stored = con.execute(
        "SELECT count(*) FROM projection_deltas WHERE season=2024 AND week=8"
    ).fetchone()[0]
    assert stored == len(deltas)
