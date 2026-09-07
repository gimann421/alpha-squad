"""End-to-end league decision engine against real, live-fetched data. Deselected by
default; run with `make test-network`. Deliberately narrower (4 seasons, one target season)
than M6-M9's own live tests, which already validate the underlying models -- this test's
job is proving the league engine's real wiring on top of them, not re-proving statistics
those milestones already established."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.league.context import FLEX_ELIGIBILITY, load_league_context
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.replacement import (
    load_season_projections,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.trade import recommend_dynasty_trade
from alpha_squad.league.waiver import recommend_waiver_pickup
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.market.dynasty_values import build_dynasty_values
from alpha_squad.market.edge import run_edge_build
from alpha_squad.models.rookie.train import run_rookie_models
from alpha_squad.models.uncertainty.run import run_uncertainty
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network

SEASONS = list(range(2022, 2026))
TARGET_SEASON = 2025


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
    record_snapshot(con, dp.fetch("dynasty_values_players"))
    build_dynasty_values(con, settings)

    run_uncertainty(con, TARGET_SEASON, TARGET_SEASON, min_train_season=2022)
    run_rookie_models(con, TARGET_SEASON, TARGET_SEASON, min_train_class=2015)
    run_edge_build(con, TARGET_SEASON, TARGET_SEASON, ecr_type="rsf")

    yield con
    con.close()


def test_replacement_level_covers_exactly_the_positions_the_league_starts(con_ready):
    """Replacement levels must be derived from the league's own lineup, not a fixed list.

    This assertion used to hardcode {QB, RB, WR, TE}, which was correct while the default
    target league was the 2QB dynasty format. D58 retargeted it to a 1-QB redraft league that
    also starts a K and a DEF, and the assertion was never updated -- so it has been failing
    since that retarget, unnoticed because the network suite is not in CI (the open P2-3
    backlog item). Found by D78's pre-draft run of `make test-network`.

    Re-derived from the config rather than re-hardcoded to the new format, so it tracks the
    league instead of rotting again the next time the format changes.
    """
    con = con_ready
    league = load_league_context()
    projections, positions = load_season_projections(con, TARGET_SEASON)
    assert len(projections) > 50, "expected real projections across many players"

    levels = replacement_level(league, projections, positions)
    scarcity = positional_scarcity(league, projections, positions)

    flex_eligible: set[str] = set()
    for flex_name in league.flex_slots():
        flex_eligible.update(FLEX_ELIGIBILITY.get(flex_name, ()))
    expected = set(league.dedicated_slots()) | flex_eligible
    assert set(levels) == expected
    assert all(v >= 0 for v in scarcity.values())

    # Real structural check: QB is not flex-eligible in any shipped format, so its replacement
    # level sits at `teams x dedicated QB slots` deep -- far enough into the real NFL starter
    # pool that it must not be trivially zero, unlike a tiny synthetic pool.
    assert levels["QB"] > 0


def test_rookie_fallback_covers_players_established_ml_structurally_excludes(con_ready):
    con = con_ready
    established_ids = {
        r[0]
        for r in con.execute(
            "SELECT player_id FROM uncertainty_predictions WHERE season = ?", [TARGET_SEASON]
        ).fetchall()
    }
    rookie_ids = {
        r[0]
        for r in con.execute(
            "SELECT player_id FROM rookie_predictions WHERE draft_class = ?", [TARGET_SEASON]
        ).fetchall()
    }
    only_rookie = rookie_ids - established_ids
    if not only_rookie:
        pytest.skip("no rookie-only real player in this data slice to check the fallback with")

    projections, positions = load_season_projections(con, TARGET_SEASON)
    sample = next(iter(only_rookie))
    assert sample in projections
    assert positions[sample] in ("QB", "RB", "WR", "TE")


def test_draft_recommendation_is_real_and_explainable(con_ready):
    con = con_ready
    league = load_league_context()
    projections, _ = load_season_projections(con, TARGET_SEASON)
    available = set(list(projections)[:100])
    rec = recommend_draft_pick(con, league, TARGET_SEASON, ["QB"], available, next_pick_overall=20)
    assert rec.recommendation in available
    assert rec.reasons
    assert 0 <= rec.confidence <= 1


def test_dynasty_trade_recommendation_uses_real_edge_and_dynasty_value(con_ready):
    con = con_ready
    row = con.execute(
        "SELECT player_id FROM edge_snapshot WHERE season = ? AND action IN ('BUY', 'SELL') LIMIT 1",
        [TARGET_SEASON],
    ).fetchone()
    if row is None:
        pytest.skip("no real BUY/SELL EDGE in this data slice to check trade recs with")
    rec = recommend_dynasty_trade(con, row[0], TARGET_SEASON)
    assert rec.action in ("BUY", "SELL", "HOLD", "WATCH")
    assert rec.reasons


def test_waiver_recommendation_bid_is_bounded_on_real_data(con_ready):
    con = con_ready
    projections, positions = load_season_projections(con, TARGET_SEASON)
    # Pick a real mid-tier player (not the very top, which would saturate the bid cap
    # trivially) to check the bound holds on a realistic case.
    ranked = sorted(projections, key=lambda p: -projections[p])
    sample = ranked[len(ranked) // 2]
    league = load_league_context()
    rec = recommend_waiver_pickup(con, league, TARGET_SEASON, 5, sample, [])
    assert 0 <= rec.recommended_bid <= league.faab_budget * 0.40 + 1e-6
    assert rec.position == positions[sample]
