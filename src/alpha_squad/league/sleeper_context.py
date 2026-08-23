"""Hydrates a real LeagueContext from Sleeper's real API (docs/DECISIONS.md D31/D33) --
exactly what league/context.py's own docstring anticipated back in M10: "The Sleeper adapter
already implemented in sources/sleeper.py can hydrate the same contract automatically once
reachable -- no schema change required." No local YAML needed for a Sleeper league: every
field comes from the real, current league settings, so it can never drift out of sync with
what the league admin actually configured.

Field mapping, from Sleeper's documented public API (https://docs.sleeper.com), a stable,
widely-used, unauthenticated read API -- no guessed shape, matched against real fetched data
the first time this ran against an actual league (see D33 for the specific league verified
against):
  settings.type        0 = redraft, 1 = keeper, 2 = dynasty -> format string
  roster_positions      a flat list with one entry per starting slot (e.g. "QB","QB","RB",
                         "FLEX","BN", repeated) -- counted into dedicated lineup slots, the
                         flex-type slots already registered in FLEX_ELIGIBILITY, and bench
                         size. "BN" = bench, "IR"/"TAXI" are excluded from `lineup` (they are
                         not starting slots) and folded into `roster` instead.
  scoring_settings.rec  points per reception -> is_ppr / ppr_value
  settings.waiver_budget FAAB budget (0 for a non-FAAB league)
"""

from __future__ import annotations

import json

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.league.context import FLEX_ELIGIBILITY, LeagueContext
from alpha_squad.sources.sleeper import SleeperSource
from alpha_squad.storage.snapshots import record_snapshot

_NON_STARTING_SLOTS = {"BN", "IR", "TAXI"}
_FORMAT_BY_TYPE = {0: "redraft", 1: "keeper", 2: "dynasty"}


def _lineup_and_roster_from_positions(
    roster_positions: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    counts: dict[str, int] = {}
    for slot in roster_positions:
        counts[slot] = counts.get(slot, 0) + 1

    lineup = {slot: n for slot, n in counts.items() if slot not in _NON_STARTING_SLOTS}
    starting_slots = sum(lineup.values())
    roster = {
        "bench": counts.get("BN", 0),
        "ir_slots": counts.get("IR", 0),
        "taxi_slots": counts.get("TAXI", 0),
        "roster_size": starting_slots
        + counts.get("BN", 0)
        + counts.get("IR", 0)
        + counts.get("TAXI", 0),
    }
    return lineup, roster


def load_sleeper_league_context(
    con: duckdb.DuckDBPyConnection | None, settings: Settings, sleeper_league_id: str
) -> LeagueContext:
    sleeper = SleeperSource(settings)
    snap = sleeper.fetch("league", league_id=sleeper_league_id)
    if con is not None:
        record_snapshot(con, snap)
    league = json.loads(snap.local_path.read_bytes())

    roster_positions = league.get("roster_positions") or []
    lineup, roster = _lineup_and_roster_from_positions(roster_positions)

    # Any lineup slot name Sleeper returns that isn't already a known flex type or a plain
    # position abbreviation still lands correctly: dedicated_slots()/flex_slots() (context.py)
    # split on FLEX_ELIGIBILITY membership, not a fixed list, so a Sleeper flex variant not
    # yet in FLEX_ELIGIBILITY would fall into dedicated_slots() (treated as its own position)
    # rather than being dropped -- never silently lost, worth registering explicitly if seen.
    unrecognized_flex_like = [
        slot for slot in lineup if "FLEX" in slot and slot not in FLEX_ELIGIBILITY
    ]

    scoring_settings = league.get("scoring_settings") or {}
    ppr_value = float(scoring_settings.get("rec", 0.0) or 0.0)

    league_settings = league.get("settings") or {}
    league_type = league_settings.get("type", 0)
    faab_budget = float(league_settings.get("waiver_budget", 0) or 0)

    return LeagueContext(
        league_id=str(league.get("league_id", sleeper_league_id)),
        format=_FORMAT_BY_TYPE.get(league_type, "redraft"),
        teams=int(league.get("total_rosters", 0) or 0),
        scoring={"ppr": ppr_value > 0, "ppr_value": ppr_value},
        lineup=lineup,
        roster=roster,
        draft_state={},
        waiver_state={},
        faab={"budget": faab_budget},
        future_picks={},
        source="sleeper",
        sleeper_league_id=sleeper_league_id,
        sleeper_league_name=league.get("name"),
        sleeper_season=league.get("season"),
        unrecognized_flex_slots=unrecognized_flex_like,
    )
