"""End-to-end Sleeper trending-adds/drops evidence detector against real, live-fetched data
(docs/DECISIONS.md D31/D32). Deselected by default; run with `make test-network`."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.evidence.prior_update import evidence_score_for_action
from alpha_squad.evidence.sleeper_trending import detect_sleeper_trending
from alpha_squad.identity.canonical import build_identity
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network


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

    yield con
    con.close()


def test_real_trending_data_resolves_to_real_players_as_weak_evidence(con_ready, settings):
    con = con_ready
    n = detect_sleeper_trending(con, settings, season=2026, week=1)

    assert n > 0, (
        "expected at least some real trending players to resolve via the identity crosswalk"
    )

    rows = con.execute(
        """
        SELECT e.player_id, p.display_name, e.strength_label, e.direction, e.source
        FROM evidence_events e JOIN players p ON p.player_id = e.player_id
        WHERE e.season = 2026 AND e.source LIKE 'sleeper_trending_%'
        """
    ).fetchall()
    assert len(rows) == n
    for _player_id, display_name, strength_label, direction, source in rows:
        assert strength_label == "WEAK"
        assert direction in (1, -1)
        assert display_name  # a real resolved player name, not a placeholder
        assert source in ("sleeper_trending_adds", "sleeper_trending_drops")


def test_real_trending_evidence_moves_the_edge_evidence_score(con_ready, settings):
    con = con_ready
    detect_sleeper_trending(con, settings, season=2026, week=1)

    # A real player can genuinely trend on *both* lists at once (different managers making
    # opposite moves) -- real conflicting evidence should cancel toward neutral, which is
    # correct, not a bug (verified: this happens live). Pick a player with unambiguous
    # evidence -- only adds, no drops for the same player -- so this assertion tests the
    # "evidence moves the score" property without depending on which specific players happen
    # to be trending both ways on any given real run.
    row = con.execute(
        """
        SELECT player_id, direction FROM evidence_events
        WHERE season = 2026 AND source = 'sleeper_trending_adds'
          AND player_id NOT IN (
              SELECT player_id FROM evidence_events
              WHERE season = 2026 AND source = 'sleeper_trending_drops'
          )
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        pytest.skip("every real trending-add player also appears in trending-drops this run")
    player_id, direction = row

    score = evidence_score_for_action(con, player_id, 2026, action_sign=direction)
    assert score > 0.5, "real trending evidence agreeing with the action must move the score up"
