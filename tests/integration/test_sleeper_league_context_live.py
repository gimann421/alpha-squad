"""End-to-end Sleeper league hydration against a real Sleeper league
(league/sleeper_context.py, docs/DECISIONS.md D33). Deselected by default; run with
`make test-network`.

Needs a real Sleeper league id to test against -- set ALPHA_SQUAD_TEST_SLEEPER_LEAGUE_ID to
one of your own league ids (the numeric id at the end of the league's Sleeper URL) to run
this for real; skipped otherwise, since there is no way to discover a real league id without
one being supplied (Sleeper has no public "any real league" listing endpoint)."""

from __future__ import annotations

import os

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.league.context import FLEX_ELIGIBILITY
from alpha_squad.league.sleeper_context import load_sleeper_league_context

pytestmark = pytest.mark.network

_LEAGUE_ID_ENV_VAR = "ALPHA_SQUAD_TEST_SLEEPER_LEAGUE_ID"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def real_sleeper_league_id() -> str:
    league_id = os.environ.get(_LEAGUE_ID_ENV_VAR)
    if not league_id:
        pytest.skip(f"set {_LEAGUE_ID_ENV_VAR} to a real Sleeper league id to run this live test")
    return league_id


def test_real_sleeper_league_hydrates_a_structurally_valid_league_context(
    settings, real_sleeper_league_id
):
    league = load_sleeper_league_context(None, settings, real_sleeper_league_id)

    assert league.league_id
    assert league.format in ("redraft", "keeper", "dynasty")
    assert league.teams > 0
    assert league.source == "sleeper"
    assert league.sleeper_league_id == real_sleeper_league_id
    assert isinstance(league.scoring["ppr"], bool)
    assert league.bench_size >= 0
    assert league.faab_budget >= 0

    # Every real flex-type slot this league actually uses must be a *known* one --
    # this is the live check that FLEX_ELIGIBILITY's registered Sleeper spellings
    # (SUPER_FLEX etc., added in D33 against a best-effort understanding of the real API,
    # not real data at the time) are actually correct, not just plausible-looking.
    assert league.unrecognized_flex_slots == [], (
        f"real Sleeper flex slot name(s) not registered in FLEX_ELIGIBILITY: "
        f"{league.unrecognized_flex_slots} -- add them to league/context.py, "
        f"now backed by real verified data (see FLEX_ELIGIBILITY: {list(FLEX_ELIGIBILITY)})"
    )

    total_lineup_slots = sum(league.lineup.values())
    assert total_lineup_slots > 0, "a real league must have at least one starting slot"
