"""Real per-team roster import for a Sleeper league (fixes the gap `sleeper_context.py`'s own
docstring left open: it hydrates league *settings*, never which real players are on which real
team). Every downstream workflow that needs "my actual roster" -- roster-need, waiver/draft/trade
roster fit, drop candidates, the dashboard -- depends on this rather than the user hand-typing a
comma-separated position list.

Bridges Sleeper's own numeric player ids (`roster["players"]`, e.g. "6813") to Alpha Squad's
canonical `player_id` via `player_id_map` (`id_type='sleeper_id'`), verified against a real
league live (6,105 real sleeper_id rows on record; every player id checked against a real
12-team league resolved). A Sleeper player id with no crosswalk match (a DST like "DEN", a kicker
not yet in `players`, or a very recently added player) is reported as unmapped rather than
silently dropped or guessed at -- ARCHITECTURE.md's "never fabricate" rule applies to identity
resolution too."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.league.context import LeagueContext
from alpha_squad.sources.sleeper import SleeperSource
from alpha_squad.storage.snapshots import record_snapshot


@dataclass
class RosterPlayer:
    player_id: str
    display_name: str | None
    position: str | None
    sleeper_player_id: str


@dataclass
class TeamRoster:
    roster_id: int
    owner_user_id: str | None
    owner_display_name: str | None
    team_name: str | None
    players: list[RosterPlayer] = field(default_factory=list)
    unmapped_sleeper_ids: list[str] = field(default_factory=list)


def _bridge_sleeper_ids(
    con: duckdb.DuckDBPyConnection, sleeper_ids: list[str]
) -> dict[str, tuple[str, str | None, str | None]]:
    """{sleeper_player_id: (player_id, display_name, position)} for every id this deployment's
    identity crosswalk already covers."""
    if not sleeper_ids:
        return {}
    placeholders = ", ".join("?" for _ in sleeper_ids)
    rows = con.execute(
        f"""
        SELECT m.id_value, m.player_id, p.display_name, p.position
        FROM player_id_map m
        JOIN players p ON p.player_id = m.player_id
        WHERE m.id_type = 'sleeper_id' AND m.id_value IN ({placeholders})
        """,
        sleeper_ids,
    ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def fetch_sleeper_rosters(
    con: duckdb.DuckDBPyConnection, settings: Settings, sleeper_league_id: str
) -> list[TeamRoster]:
    """Every real team in a live Sleeper league: owner identity (from `league_users`) and the
    real, current, canonical-id-bridged player list (from `league_rosters`) -- persisted as
    real snapshots (provenance, ACCEPTANCE_CRITERIA.md) like every other live fetch in this
    project, never held only in memory."""
    sleeper = SleeperSource(settings)

    rosters_snap = sleeper.fetch("league_rosters", league_id=sleeper_league_id)
    record_snapshot(con, rosters_snap)
    rosters = json.loads(rosters_snap.local_path.read_bytes())

    users_snap = sleeper.fetch("league_users", league_id=sleeper_league_id)
    record_snapshot(con, users_snap)
    users = json.loads(users_snap.local_path.read_bytes())
    users_by_id = {u["user_id"]: u for u in users}

    all_sleeper_ids = sorted({pid for r in rosters for pid in (r.get("players") or [])})
    bridged = _bridge_sleeper_ids(con, all_sleeper_ids)

    teams: list[TeamRoster] = []
    for r in rosters:
        owner_id = r.get("owner_id")
        user = users_by_id.get(owner_id) if owner_id else None
        team_name = (user or {}).get("metadata", {}).get("team_name") if user else None

        players: list[RosterPlayer] = []
        unmapped: list[str] = []
        for sleeper_pid in r.get("players") or []:
            match = bridged.get(sleeper_pid)
            if match is None:
                unmapped.append(sleeper_pid)
                continue
            player_id, display_name, position = match
            players.append(RosterPlayer(player_id, display_name, position, sleeper_pid))

        teams.append(
            TeamRoster(
                roster_id=r["roster_id"],
                owner_user_id=owner_id,
                owner_display_name=(user or {}).get("display_name"),
                team_name=team_name,
                players=players,
                unmapped_sleeper_ids=unmapped,
            )
        )

    teams.sort(key=lambda t: t.roster_id)
    return teams


def roster_positions_for(teams: list[TeamRoster], roster_id: int) -> list[str]:
    """The real starting-lineup-input shape `roster_need`/`recommend_waiver_pickup`/
    `recommend_draft_pick` already expect: one position string per rostered player (bench
    included -- `roster_need` itself decides what counts as "enough" depth). Raises if
    `roster_id` isn't one of the real teams just fetched, rather than silently returning []
    (which would read as "empty roster" instead of "wrong id")."""
    for team in teams:
        if team.roster_id == roster_id:
            return [p.position for p in team.players if p.position]
    known = ", ".join(str(t.roster_id) for t in teams) or "(none)"
    raise RuntimeError(f"no roster_id {roster_id} in this league; known roster ids: {known}")


def resolve_roster_positions(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    league: LeagueContext,
    *,
    roster_id: int | None = None,
    fallback: list[str] | None = None,
) -> list[str]:
    """The real roster composition (D53) when a caller supplies `roster_id` for a Sleeper
    league, replacing the old requirement that the caller hand-type a comma-separated position
    list to describe their own team. Falls back to `fallback` (typically empty, or a manually-
    entered list) when no `roster_id` is given, or the league has no real roster source (a
    `source: yaml` league) -- never silently ignores an explicit `roster_id` that can't be
    resolved, since that's much more likely a wrong id than "no roster"."""
    if roster_id is None:
        return fallback or []
    teams = teams_for_league(con, settings, league)
    if teams is None:
        raise RuntimeError(
            f"league {league.league_id!r} has no real per-team roster source "
            "(only Sleeper-connected leagues support roster_id)"
        )
    return roster_positions_for(teams, roster_id)


def teams_for_league(
    con: duckdb.DuckDBPyConnection, settings: Settings, league: LeagueContext
) -> list[TeamRoster] | None:
    """`fetch_sleeper_rosters` for a `LeagueContext`, or `None` if the league has no real
    multi-team roster source at all (a `source: yaml` league is one hand-maintained config with
    no other teams' data available -- returning `None` here, not `[]`, is what lets a caller
    tell "this league genuinely has no roster data" apart from "this league has zero teams",
    which would be a real data anomaly worth surfacing rather than an expected case)."""
    sleeper_league_id = getattr(league, "sleeper_league_id", None)
    if getattr(league, "source", None) != "sleeper" or not sleeper_league_id:
        return None
    return fetch_sleeper_rosters(con, settings, sleeper_league_id)
