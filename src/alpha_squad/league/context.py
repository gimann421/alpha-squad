"""League context, mirroring AGENT_CONTRACTS.md's League context contract byte-for-byte.
`lineup`/`scoring`/`roster`/`draft_state`/`waiver_state`/`faab`/`future_picks` are all free-form
dicts (extra="allow" on the model too) so arbitrary league settings can be represented
(ACCEPTANCE_CRITERIA.md), while still being able to load the target league (D7) exactly.

Sleeper (the natural live source for roster/draft/waiver state) is blocked in this
environment (D6); league context loads from a local YAML file conforming to this same
contract. The Sleeper adapter already implemented in sources/sleeper.py can hydrate the same
contract automatically once reachable -- no schema change required."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import duckdb

    from alpha_squad.config.settings import Settings

# lineup slot name -> positions eligible to fill it. Any slot name not listed here (QB, RB,
# WR, TE, DST, K, ...) is a dedicated slot for that exact position abbreviation. This is the
# extensibility point for SUPERFLEX or other flex variants a future league config might use.
FLEX_ELIGIBILITY: dict[str, tuple[str, ...]] = {
    "FLEX": ("RB", "WR", "TE"),
    "SUPERFLEX": ("QB", "RB", "WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),  # Sleeper's real roster_positions spelling (D33)
    "WRRB_FLEX": ("RB", "WR"),
}

_LEAGUE_CONFIGS_DIR = Path(__file__).parent.parent / "config" / "league_configs"
DEFAULT_TARGET_LEAGUE_PATH = _LEAGUE_CONFIGS_DIR / "target_league.yaml"
DEFAULT_REGISTRY_PATH = _LEAGUE_CONFIGS_DIR / "registry.yaml"
DEFAULT_LEAGUE_ID = "target_league"


class LeagueContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    league_id: str
    format: str
    teams: int
    scoring: dict = Field(default_factory=dict)
    lineup: dict[str, int] = Field(default_factory=dict)
    roster: dict = Field(default_factory=dict)
    draft_state: dict = Field(default_factory=dict)
    waiver_state: dict = Field(default_factory=dict)
    faab: dict = Field(default_factory=dict)
    future_picks: dict = Field(default_factory=dict)

    @property
    def is_ppr(self) -> bool:
        return bool(self.scoring.get("ppr", False))

    @property
    def bench_size(self) -> int:
        return int(self.roster.get("bench", 0))

    @property
    def faab_budget(self) -> float:
        return float(self.faab.get("budget", 0))

    def dedicated_slots(self) -> dict[str, int]:
        """{position: starting slot count} for non-flex slots only."""
        return {pos: n for pos, n in self.lineup.items() if pos not in FLEX_ELIGIBILITY}

    def flex_slots(self) -> dict[str, int]:
        """{flex_slot_name: slot count} for flex-type slots only."""
        return {pos: n for pos, n in self.lineup.items() if pos in FLEX_ELIGIBILITY}


def load_league_context(path: Path | str = DEFAULT_TARGET_LEAGUE_PATH) -> LeagueContext:
    path = Path(path)
    if not path.exists():
        raise RuntimeError(
            f"no league config at {path}; league-specific recommendations require an "
            "explicit league context -- ARCHITECTURE.md: missing league context must return "
            "the limitation rather than pretending a league-specific recommendation is universal."
        )
    with path.open() as f:
        raw = yaml.safe_load(f)
    return LeagueContext.model_validate(raw)


def _load_registry(registry_path: Path | str = DEFAULT_REGISTRY_PATH) -> dict[str, dict]:
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return {}
    with registry_path.open() as f:
        return yaml.safe_load(f) or {}


def list_registered_leagues(registry_path: Path | str = DEFAULT_REGISTRY_PATH) -> dict[str, dict]:
    """{league_id: {source, ...}} for every league this deployment knows about -- the "which
    leagues can I switch between" listing (CLI: `alpha-squad league list`)."""
    return _load_registry(registry_path)


def resolve_league(
    league_id: str = DEFAULT_LEAGUE_ID,
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    settings: Settings | None = None,
    registry_path: Path | str = DEFAULT_REGISTRY_PATH,
) -> LeagueContext:
    """The seamless-switching entry point (docs/DECISIONS.md D33): looks `league_id` up in
    the registry and dispatches to whichever source it declares -- a local YAML config
    (`load_league_context`, unchanged) or a live Sleeper league
    (`league/sleeper_context.py::load_sleeper_league_context`, hydrated fresh every call so it
    can never drift from what the league admin actually has configured). Every existing call
    site that only ever knew about the one hardcoded target_league.yaml keeps working
    unchanged by defaulting to DEFAULT_LEAGUE_ID, which the registry maps to that same file."""
    registry = _load_registry(registry_path)
    entry = registry.get(league_id)
    if entry is None:
        known = ", ".join(sorted(registry)) or "(none registered)"
        raise RuntimeError(
            f"no league registered as {league_id!r} in {registry_path}; known leagues: {known}"
        )

    source = entry.get("source")
    if source == "yaml":
        config_path = Path(entry["path"])
        if not config_path.is_absolute():
            config_path = Path(registry_path).parent / config_path
        return load_league_context(config_path)
    if source == "sleeper":
        from alpha_squad.config.settings import get_settings
        from alpha_squad.league.sleeper_context import load_sleeper_league_context

        return load_sleeper_league_context(
            con, settings or get_settings(), entry["sleeper_league_id"]
        )
    raise RuntimeError(f"league {league_id!r} has unknown source {source!r} in {registry_path}")
