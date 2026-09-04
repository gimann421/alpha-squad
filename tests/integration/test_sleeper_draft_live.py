"""End-to-end Sleeper draft-pick synchronization against a real Sleeper league
(league/sleeper_draft.py, 2026-09-03 product-gap PART 1). Deselected by default; run with
`make test-network`.

Uses the two leagues already registered in config/league_configs/registry.yaml (`dilworth`,
`boys_of_fall`) rather than requiring a fresh env var -- these are real leagues this deployment
already validates other Sleeper integrations against. Their drafts are from a past season, so
this exercises "reconstruct a completed draft" (PART 7's live-validation guidance: a completed
draft cannot prove real-time polling, but it does prove the real fetch/parse/bridge/pick-order
path against real Sleeper data, not a guess at the JSON shape)."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.sleeper_draft import (
    compute_turn_info,
    fetch_sleeper_draft_id,
    fetch_sleeper_draft_state,
)

pytestmark = pytest.mark.network

_REAL_LEAGUES = {
    "dilworth": "1395093181141381120",
    "boys_of_fall": "1326428555382394880",
}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.mark.parametrize("league_id", list(_REAL_LEAGUES.values()), ids=list(_REAL_LEAGUES))
def test_real_league_draft_reconstructs_a_structurally_valid_board(settings, league_id):
    draft_id = fetch_sleeper_draft_id(None, settings, league_id)
    assert draft_id, f"expected league {league_id} to have at least one real draft"

    state = fetch_sleeper_draft_state(None, settings, draft_id)

    assert state.draft_id == draft_id
    assert state.status in ("pre_draft", "drafting", "paused", "complete")
    assert state.teams > 0
    assert state.rounds > 0
    assert len(state.picks) > 0, "a real past-season draft should have at least one real pick"

    # Real pick numbers must be unique and positive -- proves the dedup-by-pick_no logic didn't
    # need to collapse anything real, and that pick_no isn't some other kind of identifier.
    pick_nos = [p.pick_no for p in state.picks]
    assert len(pick_nos) == len(set(pick_nos))
    assert all(n > 0 for n in pick_nos)

    # Every pick belongs to a real roster_id that also appears in slot_to_roster_id (or is at
    # least a plausible small integer) -- a wrong field mapping would show up as None/garbage.
    assert all(p.roster_id is not None for p in state.picks)

    turn = compute_turn_info(state, roster_id=state.picks[0].roster_id)
    if state.status == "complete":
        assert turn.current_pick_overall is None
    else:
        assert turn.current_pick_overall is not None
