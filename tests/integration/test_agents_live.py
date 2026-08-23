"""End-to-end agent orchestrator against real, live-fetched data. Deselected by default; run
with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.agents.contracts import Task
from alpha_squad.agents.disagreement import (
    detect_baseline_vs_ml_disagreements,
    detect_model_vs_market_disagreements,
    resolve_and_record,
)
from alpha_squad.agents.orchestrator import run_pipeline
from alpha_squad.agents.state import reconstruct_run
from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.models.baselines.run import run_baselines
from alpha_squad.models.established.train import run_established_ml
from alpha_squad.models.uncertainty.run import run_uncertainty
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


def test_real_data_engineering_and_identity_agents_run_through_the_orchestrator(settings):
    tasks = [
        Task(
            task_id="data",
            agent="data_engineering",
            objective="ingest identity datasets",
            params={
                "datasets": [
                    ["nflverse", "players", {}],
                    ["nflverse", "draft_picks", {}],
                    ["nflverse", "combine", {}],
                    ["dynastyprocess", "player_ids", {}],
                ]
            },
        ),
        Task(
            task_id="identity",
            agent="player_identity",
            objective="build identity",
            depends_on=["data"],
        ),
    ]
    report = run_pipeline(settings, "live-run-1", tasks)
    assert report.results["data"].status == "COMPLETE"
    assert report.results["identity"].status == "COMPLETE"
    assert "identity build report" in report.results["identity"].findings[0]

    con = get_connection(settings)
    try:
        n_players = con.execute("SELECT count(*) FROM players").fetchone()[0]
        assert n_players > 1000, "expected the real nflverse players spine to be built"

        rebuilt = reconstruct_run(con, "live-run-1")
        assert len(rebuilt["tasks"]) == 2
        assert all(t["status"] == "COMPLETE" for t in rebuilt["tasks"])
        assert rebuilt["tasks"][1]["result"]["status"] == "COMPLETE"
    finally:
        con.close()


def test_unregistered_dataset_is_reported_as_a_finding_not_a_crash(settings):
    tasks = [
        Task(
            task_id="data",
            agent="data_engineering",
            objective="ingest a mix of real and bogus datasets",
            params={
                "datasets": [["nflverse", "players", {}], ["nflverse", "not_a_real_dataset", {}]]
            },
        )
    ]
    report = run_pipeline(settings, "live-run-2", tasks)
    result = report.results["data"]
    assert result.status == "COMPLETE"  # one real dataset succeeded
    assert any("not_a_real_dataset" in f for f in result.findings)


def test_real_disagreements_are_detected_and_resolved_preserving_minority(settings):
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

    seasons = list(range(2022, 2026))
    for season in seasons:
        for dataset in ("pbp", "stats_player_week", "snap_counts", "stats_team_week"):
            record_snapshot(con, nflverse.fetch(dataset, season=season))
    build_features(con, settings, seasons)
    record_snapshot(con, dp.fetch("fp_ecr_history"))
    build_market_snapshot(con, settings)

    run_baselines(con, [2025])
    run_established_ml(con, 2025, 2025, min_train_season=2022)
    run_uncertainty(con, 2025, 2025, min_train_season=2022)

    from alpha_squad.market.edge import run_edge_build

    run_edge_build(con, 2025, 2025, ecr_type="rsf")

    market_disagreements = detect_model_vs_market_disagreements(con, 2025, ecr_type="rsf")
    model_disagreements = []
    for position in ("QB", "RB", "WR", "TE"):
        model_disagreements.extend(detect_baseline_vs_ml_disagreements(con, 2025, position))

    all_disagreements = market_disagreements + model_disagreements
    assert all_disagreements, (
        "expected at least one real disagreement across a full season's real data"
    )

    for d in all_disagreements:
        disagreement_id = resolve_and_record(con, "live-run-3", d)
        row = con.execute(
            "SELECT majority_position, minority_position FROM agent_disagreements WHERE disagreement_id = ?",
            [disagreement_id],
        ).fetchone()
        assert row[0] != row[1]  # majority and minority are genuinely different positions

    con.close()
