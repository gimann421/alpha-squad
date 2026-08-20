"""Central registry of every source adapter. `alpha-squad sources status` and `sources
ingest` both drive off this list so a new adapter only needs to be added here once."""

from __future__ import annotations

from alpha_squad.config.settings import Settings
from alpha_squad.sources.base import SourceAdapter
from alpha_squad.sources.cfbd import CfbdSource
from alpha_squad.sources.cfbfastr import CfbFastRSource
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.fantasypros import FantasyProsSource
from alpha_squad.sources.ffopportunity import FfOpportunitySource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.sources.sleeper import SleeperSource

# Sources verified reachable in this environment (docs/DATA_SOURCES.md).
AVAILABLE_SOURCE_NAMES = ("nflverse", "dynastyprocess", "cfbfastr", "ffopportunity")
# Sources implemented to spec but blocked by environment egress policy and/or missing
# credentials (docs/DECISIONS.md D3/D4/D5).
BLOCKED_SOURCE_NAMES = ("sleeper", "fantasypros", "cfbd")


def all_adapters(settings: Settings | None = None) -> list[SourceAdapter]:
    return [
        NflverseSource(settings),
        DynastyProcessSource(settings),
        CfbFastRSource(settings),
        FfOpportunitySource(settings),
        SleeperSource(settings),
        FantasyProsSource(settings),
        CfbdSource(settings),
    ]


def get_adapter(name: str, settings: Settings | None = None) -> SourceAdapter:
    for adapter in all_adapters(settings):
        if adapter.name == name:
            return adapter
    raise KeyError(f"no source adapter registered with name '{name}'")
