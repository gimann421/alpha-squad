"""Real Sleeper draft-pick synchronization (PART 1 of the 2026-09-03 product-gap request):
Sleeper's `draft/{draft_id}/picks` endpoint is authoritative for which picks have happened, so
this module reconstructs the live draft board FROM that endpoint rather than asking the user to
retype every opposing team's pick. It never maintains a second, competing record of completed
Sleeper picks -- every call re-fetches live and the caller (the API route) treats the result as
the current truth, not something to merge with a locally-remembered pick list.

Field mapping, from Sleeper's documented public API (https://docs.sleeper.com):
  GET /league/{league_id}/drafts   -> list of drafts for the league, most recent first; this
                                       league's current/most recent draft_id.
  GET /draft/{draft_id}            -> status ("pre_draft"/"drafting"/"paused"/"complete"),
                                       type ("snake"/"linear"/"auction"), settings.teams,
                                       settings.rounds, slot_to_roster_id ({slot: roster_id}).
  GET /draft/{draft_id}/picks      -> one row per completed pick: pick_no, round, roster_id,
                                       draft_slot, player_id (Sleeper's own numeric id).

Snake order reconstruction (`_pick_order`) is what makes "whose turn is it" and "when is my next
pick" computable without waiting for Sleeper to report a pick that hasn't happened yet -- it is
derived purely from `slot_to_roster_id` + `type` + `teams` + `rounds`, the same information a
human would use to read a draft board on paper, not a guess."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.league.roster_import import bridge_sleeper_player_ids
from alpha_squad.sources.sleeper import SleeperSource
from alpha_squad.storage.snapshots import record_snapshot


@dataclass
class SleeperDraftPick:
    pick_no: int
    round: int
    roster_id: int | None
    sleeper_player_id: str
    player_id: str | None  # canonical id, None if unmapped


@dataclass
class SleeperDraftState:
    draft_id: str
    status: str  # "pre_draft" | "drafting" | "paused" | "complete"
    draft_type: str  # "snake" | "linear" | "auction"
    teams: int
    rounds: int
    slot_to_roster_id: dict[int, int] = field(default_factory=dict)
    picks: list[SleeperDraftPick] = field(default_factory=list)
    unmapped_sleeper_ids: list[str] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return self.teams * self.rounds

    @property
    def drafted_player_ids(self) -> list[str]:
        """Bridged canonical ids only -- an unmapped pick still counts as "off the board" for
        pick-order/turn bookkeeping (it occupies a real `pick_no`), but cannot be named, so it
        is reported separately in `unmapped_sleeper_ids` rather than silently omitted."""
        return [p.player_id for p in self.picks if p.player_id is not None]

    def player_ids_for_roster(self, roster_id: int) -> list[str]:
        return [
            p.player_id for p in self.picks if p.roster_id == roster_id and p.player_id is not None
        ]


def _pick_order(
    teams: int, rounds: int, draft_type: str, slot_to_roster_id: dict[int, int]
) -> list[int | None]:
    """overall pick number (1-indexed via list position+1) -> roster_id. Snake alternates
    direction every round (the real, documented Sleeper/standard-draft rule); any other
    `draft_type` (e.g. "linear", or "auction" where pick order is not fixed) keeps the same
    slot order every round rather than guessing a reversal that may not apply. A slot with no
    entry in `slot_to_roster_id` (not yet assigned, e.g. before the draft's lottery/order is
    set) yields `None` at that position rather than a fabricated roster id."""
    order: list[int | None] = []
    for rnd in range(1, rounds + 1):
        reverse = draft_type == "snake" and rnd % 2 == 0
        slots = range(teams, 0, -1) if reverse else range(1, teams + 1)
        for slot in slots:
            order.append(slot_to_roster_id.get(slot))
    return order


def fetch_sleeper_draft_id(
    con: duckdb.DuckDBPyConnection | None, settings: Settings, sleeper_league_id: str
) -> str | None:
    """The league's current (most recently created) draft id, or None if Sleeper has never
    generated one for this league -- a real, expected state (an unstarted redraft league before
    the commissioner has set the draft up), not an error."""
    sleeper = SleeperSource(settings)
    snap = sleeper.fetch("league_drafts", league_id=sleeper_league_id)
    if con is not None:
        record_snapshot(con, snap)
    drafts = json.loads(snap.local_path.read_bytes())
    if not drafts:
        return None
    return str(drafts[0]["draft_id"])


def fetch_sleeper_draft_state(
    con: duckdb.DuckDBPyConnection | None,
    settings: Settings,
    draft_id: str,
) -> SleeperDraftState:
    """Fetches the draft's own settings plus every completed pick and reconstructs the board.
    Raises `alpha_squad.sources.base.SourceError` (or its `SourceBlockedError`/`SourceNotFoundError`
    subclasses) on any real fetch failure -- the caller (the API route) is what decides how to
    surface "Sleeper temporarily unavailable" vs. "draft id not found" to the user; this
    function never swallows a failure into a fabricated empty board."""
    sleeper = SleeperSource(settings)

    draft_snap = sleeper.fetch("draft", draft_id=draft_id)
    if con is not None:
        record_snapshot(con, draft_snap)
    draft = json.loads(draft_snap.local_path.read_bytes())

    draft_settings = draft.get("settings") or {}
    teams = int(draft_settings.get("teams") or 0)
    rounds = int(draft_settings.get("rounds") or 0)
    draft_type = draft.get("type") or "snake"
    slot_to_roster_id = {
        int(slot): int(rid)
        for slot, rid in (draft.get("slot_to_roster_id") or {}).items()
        if rid is not None
    }

    picks_snap = sleeper.fetch("draft_picks", draft_id=draft_id)
    if con is not None:
        record_snapshot(con, picks_snap)
    raw_picks = json.loads(picks_snap.local_path.read_bytes())

    # Sleeper's picks feed is authoritative and keyed by pick_no; a duplicate pick_no in a raw
    # response (a genuine delayed/duplicated delivery, or two overlapping polls landing the
    # same content) is collapsed to one entry rather than double-counting a player as drafted
    # twice or inflating `total picks made`.
    by_pick_no: dict[int, dict] = {}
    for raw in raw_picks:
        pick_no = raw.get("pick_no")
        if pick_no is None:
            continue
        by_pick_no[int(pick_no)] = raw

    sleeper_ids = sorted(
        {str(raw["player_id"]) for raw in by_pick_no.values() if raw.get("player_id")}
    )
    bridged = bridge_sleeper_player_ids(con, sleeper_ids) if con is not None else {}

    picks: list[SleeperDraftPick] = []
    unmapped: list[str] = []
    for pick_no in sorted(by_pick_no):
        raw = by_pick_no[pick_no]
        sleeper_pid = str(raw.get("player_id")) if raw.get("player_id") else None
        if sleeper_pid is None:
            continue
        match = bridged.get(sleeper_pid)
        player_id = match[0] if match else None
        if match is None:
            unmapped.append(sleeper_pid)
        picks.append(
            SleeperDraftPick(
                pick_no=pick_no,
                round=int(raw.get("round") or 0),
                roster_id=raw.get("roster_id"),
                sleeper_player_id=sleeper_pid,
                player_id=player_id,
            )
        )

    return SleeperDraftState(
        draft_id=str(draft.get("draft_id", draft_id)),
        status=draft.get("status") or "pre_draft",
        draft_type=draft_type,
        teams=teams,
        rounds=rounds,
        slot_to_roster_id=slot_to_roster_id,
        picks=picks,
        unmapped_sleeper_ids=unmapped,
    )


@dataclass
class DraftTurnInfo:
    current_pick_overall: int | None
    on_the_clock_roster_id: int | None
    next_pick_overall_for_roster: int | None
    is_users_turn: bool | None


def compute_turn_info(state: SleeperDraftState, roster_id: int | None) -> DraftTurnInfo:
    """Where the draft is right now, and (when `roster_id` is known) when this team picks
    next. Degrades to `None` fields rather than guessing when the draft's own settings do not
    describe a full pick order (e.g. an auction draft, or teams/rounds not yet set) -- the same
    "unknown means None, not a guess" discipline `league/draft.py` already follows for
    `next_pick_survival_probability`."""
    total_picks_made = len(state.picks)
    if state.teams <= 0 or state.rounds <= 0:
        return DraftTurnInfo(None, None, None, None)

    order = _pick_order(state.teams, state.rounds, state.draft_type, state.slot_to_roster_id)
    total_slots = len(order)
    current_pick_overall = total_picks_made + 1 if total_picks_made < total_slots else None
    on_the_clock = order[total_picks_made] if current_pick_overall is not None else None

    if roster_id is None:
        return DraftTurnInfo(current_pick_overall, on_the_clock, None, None)

    is_users_turn = on_the_clock == roster_id if on_the_clock is not None else None
    next_pick_overall = None
    if current_pick_overall is not None:
        for idx in range(current_pick_overall, total_slots):  # strictly after the pick on the clock
            if order[idx] == roster_id:
                next_pick_overall = idx + 1
                break
    return DraftTurnInfo(current_pick_overall, on_the_clock, next_pick_overall, is_users_turn)
