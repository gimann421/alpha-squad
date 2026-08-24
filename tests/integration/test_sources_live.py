"""Live network tests against the real external sources. Deselected by default
(pytest addopts = "-m 'not network'"); run explicitly with `make test-network`.

These encode the reachability findings recorded in docs/DATA_SOURCES.md as a durable,
re-runnable check rather than a one-time manual curl session — if the environment's egress
policy or an upstream schema ever changes, this is what should catch it.
"""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.sources.base import SourceCredentialsError
from alpha_squad.sources.cfbd import CfbdSource
from alpha_squad.sources.cfbfastr import CfbFastRSource
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.fantasypros import FantasyProsSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.sources.sleeper import SleeperSource

pytestmark = pytest.mark.network


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


def test_nflverse_players_is_really_reachable(settings):
    snap = NflverseSource(settings).fetch("players")
    assert snap.rows and snap.rows > 20000
    assert "gsis_id" in snap.columns
    assert snap.local_path.exists()


def test_nflverse_current_season_datasets_are_reachable(settings):
    adapter = NflverseSource(settings)
    rosters = adapter.fetch("rosters", season=2026)
    depth = adapter.fetch("depth_charts", season=2026)
    assert rosters.rows and rosters.rows > 0
    assert depth.rows and depth.rows > 0


def test_dynastyprocess_id_crosswalk_is_reachable(settings):
    snap = DynastyProcessSource(settings).fetch("player_ids")
    assert snap.rows and snap.rows > 5000
    assert "sleeper_id" in snap.columns
    assert "gsis_id" in snap.columns


def test_cfbfastr_college_stats_reachable(settings):
    snap = CfbFastRSource(settings).fetch("player_stats", season=2025)
    assert snap.rows and snap.rows > 1000


def test_sleeper_is_really_reachable(settings):
    """Sleeper was BLOCKED_BY_POLICY through M13 (this test used to assert exactly that,
    with an explicit note that a passing fetch here would be good news requiring a docs
    update). The environment's egress policy changed; re-verified 2026-08-22 (D31) with real
    data returned across every no-credential endpoint. If this ever reverts, docs/DATA_SOURCES.md
    and docs/DECISIONS.md D31 need updating and this assertion should flip back."""
    snap = SleeperSource(settings).fetch("state")
    assert snap.rows == 1
    assert snap.local_path.exists()


def test_fantasypros_without_key_reports_no_credentials(settings):
    settings = settings.model_copy(update={"fantasypros_api_key": None})
    assert settings.fantasypros_api_key is None
    with pytest.raises(SourceCredentialsError):
        FantasyProsSource(settings).fetch("consensus_rankings", season=2026)


def test_fantasypros_with_key_is_really_reachable(settings):
    """A real FANTASYPROS_API_KEY was configured and confirmed live 2026-08-23 (D37) — the
    earlier 403 Forbidden (D36) was a wrong adapter base URL (missing `/public`), not a
    credentials or policy problem; fixed in `sources/fantasypros.py`. Skips (not fails) when
    no key is configured, since a paid key isn't guaranteed to exist in every environment."""
    if not settings.fantasypros_api_key:
        pytest.skip("FANTASYPROS_API_KEY not configured in this environment")
    snap = FantasyProsSource(settings).fetch(
        "consensus_rankings", season=2026, position="WR", type="ros"
    )
    assert snap.rows and snap.rows > 0
    assert snap.local_path.exists()


def test_cfbd_with_key_is_really_reachable(settings):
    """A real CFBD_API_KEY was configured and confirmed live 2026-08-23 (D36). Skips (not
    fails) when no key is configured, since a free key still isn't guaranteed to exist in
    every environment."""
    if not settings.cfbd_api_key:
        pytest.skip("CFBD_API_KEY not configured in this environment")
    snap = CfbdSource(settings).fetch("teams")
    assert snap.rows and snap.rows > 100
    assert "school" in (snap.columns or ())
