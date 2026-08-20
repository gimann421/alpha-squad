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

import yaml
from pydantic import BaseModel, ConfigDict, Field

# lineup slot name -> positions eligible to fill it. Any slot name not listed here (QB, RB,
# WR, TE, DST, K, ...) is a dedicated slot for that exact position abbreviation. This is the
# extensibility point for SUPERFLEX or other flex variants a future league config might use.
FLEX_ELIGIBILITY: dict[str, tuple[str, ...]] = {
    "FLEX": ("RB", "WR", "TE"),
    "SUPERFLEX": ("QB", "RB", "WR", "TE"),
    "WRRB_FLEX": ("RB", "WR"),
}

DEFAULT_TARGET_LEAGUE_PATH = Path(__file__).parent.parent / "config" / "league_configs" / "target_league.yaml"


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
