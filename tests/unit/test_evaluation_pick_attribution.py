"""Pick-level attribution of Alpha vs consensus (docs/DECISIONS.md D58)."""

from __future__ import annotations

import json

import duckdb
import pytest

from alpha_squad.evaluation.pick_attribution import (
    attribute_draft_picks,
    run_pick_attribution,
    write_pick_attribution_artifacts,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

SEASON = 2025


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league(**overrides) -> LeagueContext:
    base = dict(
        league_id="t",
        format="redraft",
        teams=2,
        scoring={"ppr": True},
        lineup={"QB": 1, "RB": 1, "WR": 1},
        roster={"bench": 1, "roster_size": 4},
    )
    base.update(overrides)
    return LeagueContext(**base)


def _seed(con, player_id, position, projected, realized, ecr_rank):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season,
             predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, 0.8, ?, current_timestamp)
        """,
        [f"p_{player_id}", player_id, SEASON, position, UNCERTAINTY_MODEL_VERSION,
         projected, SEASON - 1],
    )
    con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, "
        "page_type) VALUES (?, ?, 'ro', ?, ?, 'redraft-overall')",
        [player_id, f"{SEASON}-08-01", position, ecr_rank],
    )
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 17, ?, ?)",
        [player_id, SEASON, position, realized, realized / 17],
    )


def _seed_pool(con):
    """Alpha and the market disagree by construction: `alpha_love` projects best but the
    market ranks it last, so Alpha takes it and consensus does not."""
    _seed(con, "alpha_love", "WR", projected=400.0, realized=50.0, ecr_rank=9.0)
    _seed(con, "market_love", "WR", projected=100.0, realized=300.0, ecr_rank=1.0)
    for i, pos in enumerate(["QB", "RB", "WR", "TE"] * 3):
        _seed(con, f"filler{i}", pos, projected=90.0 - i, realized=80.0, ecr_rank=2.0 + i)


class TestAttributeDraftPicks:
    def test_one_row_per_pick_the_team_makes(self, con):
        _seed_pool(con)
        rows = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)
        assert len(rows) == _league().roster["roster_size"]
        assert [r.round_no for r in rows] == [1, 2, 3, 4]

    def test_snake_geometry_is_recorded(self, con):
        """Slot 1 in a 2-team league picks 1st, then 4th, then 5th, then 8th."""
        _seed_pool(con)
        rows = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)
        assert [r.overall_pick for r in rows] == [1, 4, 5, 8]

    def test_the_counterfactual_comes_from_the_same_pool_at_the_same_moment(self, con):
        """The method's whole point: consensus is asked what it would take from the pool
        Alpha actually faced, so no divergence has to be modelled."""
        _seed_pool(con)
        first = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)[0]
        assert first.alpha_player_id == "alpha_love"
        assert first.consensus_player_id == "market_love"
        assert not first.agreed

    def test_a_pick_that_cost_starter_points_reports_a_positive_delta(self, con):
        """`market_love` really outscored `alpha_love` 300 to 50, so swapping it in gains
        starter points and the delta on Alpha's pick is positive."""
        _seed_pool(con)
        first = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)[0]
        assert first.starter_points_delta > 0

    def test_an_agreed_pick_has_a_zero_delta_by_construction(self, con):
        _seed_pool(con)
        rows = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)
        for row in rows:
            if row.agreed:
                assert row.starter_points_delta == 0.0

    def test_projected_and_realized_values_are_recorded_for_both_sides(self, con):
        _seed_pool(con)
        first = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)[0]
        assert first.alpha_projected == pytest.approx(400.0)
        assert first.alpha_realized == pytest.approx(50.0)
        assert first.consensus_projected == pytest.approx(100.0)
        assert first.consensus_realized == pytest.approx(300.0)

    def test_roster_state_before_the_pick_is_recorded(self, con):
        _seed_pool(con)
        rows = attribute_draft_picks(con, _league(), SEASON, draft_slot=1)
        assert rows[0].roster_before == {}
        assert sum(rows[1].roster_before.values()) == 1
        assert sum(rows[-1].roster_before.values()) == len(rows) - 1

    def test_it_is_deterministic_across_repeat_runs(self, con):
        """D54: `available` is a set and PYTHONHASHSEED is unset, so anything iterating it
        without a tie-break can silently differ between runs."""
        _seed_pool(con)
        league = _league()
        first = attribute_draft_picks(con, league, SEASON, draft_slot=1)
        for _ in range(4):
            assert attribute_draft_picks(con, league, SEASON, draft_slot=1) == first

    def test_a_league_with_no_roster_size_fails_loudly(self, con):
        _seed_pool(con)
        with pytest.raises(RuntimeError, match="roster_size"):
            attribute_draft_picks(con, _league(roster={"bench": 1}), SEASON, draft_slot=1)


class TestRunAndArtifacts:
    def test_every_slot_is_covered_by_default(self, con):
        _seed_pool(con)
        league = _league()
        rows = run_pick_attribution(con, league, [SEASON])
        assert {r.draft_slot for r in rows} == {1, 2}

    def test_artifacts_are_written_and_reloadable(self, con, tmp_path):
        _seed_pool(con)
        rows = run_pick_attribution(con, _league(), [SEASON], slots=[1])
        json_path, report_path = tmp_path / "a.json", tmp_path / "a.md"
        write_pick_attribution_artifacts(rows, json_path, report_path)

        payload = json.loads(json_path.read_text())
        assert len(payload["picks"]) == len(rows)
        assert payload["picks"][0]["alpha_player_id"] == rows[0].alpha_player_id

        report = report_path.read_text()
        assert "Pick-level attribution" in report
        assert "Worst individual picks" in report

    def test_an_empty_result_renders_without_crashing(self, tmp_path):
        write_pick_attribution_artifacts([], tmp_path / "e.json", tmp_path / "e.md")
        assert "No picks recorded" in (tmp_path / "e.md").read_text()
