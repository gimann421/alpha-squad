"""W16 experimental weekly board: the pure parts. No I/O, no model fitting, no database.

`scripts/beta/weekly_board.py` gathers the inputs (schedule, weekly roster, injury report,
prospective feature rows, both arms' predictions) and hands them to the functions here, which
decide who is on the board, convert scoring, rank, and assemble the saved snapshot. Keeping them
pure is what lets `tests/beta/` pin every product rule on synthetic data.

The rules, and why (docs/weekly/W16_BETA_READINESS_AND_HOLDOUT.md):

* **Eligibility never depends on a box-score row.** The production weekly path ranks only
  players with a `player_week_stats` row for the week (W3 §2.1), so it cannot rank anyone before
  they play. Here the universe is the team's weekly roster at the cutoff, intersected with the
  week's schedule. A player who has never appeared is still eligible.
* **A bye is not an option.** A team with no game this week contributes nobody, and the snapshot
  lists the teams so the omission is visible.
* **Availability is shown, never multiplied in.** Roster status and the injury-report designation
  sit beside the projection; the projection is the model's expected points if he plays.
* **Started games stay on the board, flagged.** Their projections used only games before this
  week, so they are not contaminated; `game_started` lets a viewer hide them.
* **FLEX is RB/WR/TE pooled by projected points.** No FLEX model, no cross-position adjustment,
  the architecture W3 evaluated.
* **Half-PPR is an explicit approximation.** Both models are trained on the Full-PPR target. Exact
  scoring differs only by receptions (`evaluation/weekly/scoring.py`), so the Half-PPR estimate is
  `full_ppr - 0.5 * receptions_avg_last3`, the model's own recent-receptions input. It is labelled
  as such on every row; it is not a separately trained or validated projection.
* **Ties break by `player_id`**, so the same inputs always produce the same order.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

BETA_VERSION = "weekly_beta_v1"

#: The two selectable boards. The keys are what the API and viewer accept.
CONTROL = "alpha_control"
W10 = "w10_experimental"
MODELS: tuple[str, ...] = (CONTROL, W10)

FULL_PPR = "full_ppr"
HALF_PPR = "half_ppr"
SCORINGS: tuple[str, ...] = (FULL_PPR, HALF_PPR)
HALF_PPR_METHOD = "full_ppr_projection - 0.5 * receptions_avg_last3 (approximation)"

MODEL_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")
W10_POSITIONS: tuple[str, ...] = ("RB", "WR", "TE")
KDST_POSITIONS: tuple[str, ...] = ("K", "DST")
POSITIONS: tuple[str, ...] = (*MODEL_POSITIONS, *KDST_POSITIONS)
FLEX_POSITIONS: tuple[str, ...] = ("RB", "WR", "TE")
VIEWS: tuple[str, ...] = ("OVERALL", *POSITIONS, "FLEX")

#: Weekly-roster statuses that put a player on the board. ACT is the active 53; INA is a
#: game-day inactive, which only exists once that game's inactives are announced, and is shown as
#: availability rather than removing him. Everything else (reserve lists, practice squad, cut,
#: retired, exempt) is excluded and counted in the snapshot.
ELIGIBLE_ROSTER_STATUSES: frozenset[str] = frozenset({"ACT", "INA"})

ET = ZoneInfo("America/New_York")

DISCLAIMER = (
    "EXPERIMENTAL BETA. 'w10_experimental' adds last season's role and production to Alpha. It "
    "beat current Alpha on 2021-2025 history, and its 2026 holdout is still running: after 4 of "
    "the 8 weeks the pre-registered rule needs, the verdict is INCONCLUSIVE. It is NOT validated "
    "on 2026. 'alpha_control' is the current production weekly model. Projections are expected "
    "points if the player plays, not guarantees, and are not adjusted for injury status."
)


def dst_player_id(team: str) -> str:
    """D57's canonical DST id, built from the team code, never a name."""
    return f"asq_dst_{team}"


@dataclass(frozen=True)
class Game:
    team: str
    opponent: str
    home: bool
    kickoff_utc: dt.datetime
    game_id: str | None = None


def kickoff_utc(gameday: str, gametime: str) -> dt.datetime:
    """nflverse schedules give the local (Eastern) date and time; a missing time is an error, not
    a guess, because whether a game has started depends on it."""
    if not gameday or not gametime:
        raise ValueError(f"schedule row has no kickoff time: {gameday!r} {gametime!r}")
    local = dt.datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return local.astimezone(dt.UTC)


def week_games(schedule_rows: list[dict], season: int, week: int) -> dict[str, Game]:
    """team -> its REG game this week. A team absent from the result is on bye."""
    out: dict[str, Game] = {}
    for r in schedule_rows:
        if int(r["season"]) != season or int(r["week"]) != week or r["game_type"] != "REG":
            continue
        ko = kickoff_utc(str(r["gameday"]), r.get("gametime"))
        home, away = r["home_team"], r["away_team"]
        for team, opp, is_home in ((home, away, True), (away, home, False)):
            if team in out:
                raise ValueError(f"{team} scheduled twice in {season} week {week}")
            out[team] = Game(team, opp, is_home, ko, r.get("game_id"))
    return out


def roster_week_rows(roster_rows: list[dict], week: int) -> tuple[int | None, list[dict]]:
    """The latest weekly-roster week at or before `week`, and its rows. Early in a week the
    roster for that week may not be published yet; the previous week's is then the latest
    information, and the snapshot records which week was used."""
    weeks = sorted({int(r["week"]) for r in roster_rows if int(r["week"]) <= week})
    if not weeks:
        return None, []
    used = weeks[-1]
    return used, [r for r in roster_rows if int(r["week"]) == used]


@dataclass
class Entry:
    player_id: str
    gsis_id: str | None
    name: str
    position: str
    team: str
    opponent: str
    home: bool
    kickoff_utc: str
    game_started: bool
    roster_status: str
    injury_status: str | None = None


@dataclass
class Exclusions:
    bye_teams: list[str] = field(default_factory=list)
    bye_players: int = 0
    roster_status: dict[str, int] = field(default_factory=dict)
    unresolved_identity: list[dict] = field(default_factory=list)


def build_universe(
    roster_rows: list[dict],
    games: dict[str, Game],
    gsis_to_player: dict[str, str],
    generated_at: dt.datetime,
    injuries: dict[str, str] | None = None,
    season_teams: set[str] | None = None,
) -> tuple[list[Entry], Exclusions]:
    """Everyone eligible for this week's board, from the roster and the schedule only.

    `roster_rows` are one week's weekly-roster rows (see `roster_week_rows`). `injuries` maps a
    gsis id to this week's report status. Nothing here reads a stat, so a player who has not yet
    played is treated exactly like one who has. DSTs are added for every team with a game.

    `season_teams` (every team on the season's schedule) is what identifies the bye teams: the
    nflverse weekly roster for a week omits teams on bye entirely (verified on 2026 week 5: 30
    teams), so the roster alone cannot name them."""
    injuries = injuries or {}
    ex = Exclusions()
    entries: list[Entry] = []
    seen: set[str] = set()
    for r in sorted(roster_rows, key=lambda r: (str(r.get("gsis_id")), str(r.get("team")))):
        pos = r.get("position")
        if pos not in MODEL_POSITIONS and pos != "K":
            continue
        status = str(r.get("status") or "UNKNOWN")
        if status not in ELIGIBLE_ROSTER_STATUSES:
            ex.roster_status[status] = ex.roster_status.get(status, 0) + 1
            continue
        team = r.get("team")
        game = games.get(team)
        if game is None:
            ex.bye_players += 1
            continue
        gsis = r.get("gsis_id")
        pid = gsis_to_player.get(gsis) if gsis else None
        if pid is None:
            ex.unresolved_identity.append(
                {"gsis_id": gsis, "name": r.get("full_name"), "team": team, "position": pos}
            )
            continue
        if pid in seen:
            raise ValueError(f"{pid} appears twice on the week's roster")
        seen.add(pid)
        entries.append(
            Entry(
                player_id=pid,
                gsis_id=gsis,
                name=str(r.get("full_name")),
                position=pos,
                team=team,
                opponent=game.opponent,
                home=game.home,
                kickoff_utc=game.kickoff_utc.isoformat(),
                game_started=game.kickoff_utc <= generated_at,
                roster_status=status,
                injury_status=injuries.get(gsis),
            )
        )
    for team, game in sorted(games.items()):
        entries.append(
            Entry(
                player_id=dst_player_id(team),
                gsis_id=None,
                name=f"{team} D/ST",
                position="DST",
                team=team,
                opponent=game.opponent,
                home=game.home,
                kickoff_utc=game.kickoff_utc.isoformat(),
                game_started=game.kickoff_utc <= generated_at,
                roster_status="TEAM",
            )
        )
    teams = {r.get("team") for r in roster_rows if r.get("team")} | set(season_teams or ())
    ex.bye_teams = sorted(t for t in teams if t not in games)
    return entries, ex


def _finite(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def half_ppr(full_ppr: float, receptions_avg_last3) -> float:
    rec = float(receptions_avg_last3) if _finite(receptions_avg_last3) else 0.0
    return float(full_ppr) - 0.5 * rec


def scored(full_ppr: float | None, receptions_avg_last3) -> dict[str, float] | None:
    if full_ppr is None:
        return None
    return {
        FULL_PPR: round(float(full_ppr), 4),
        HALF_PPR: round(half_ppr(full_ppr, receptions_avg_last3), 4),
    }


def in_view(position: str, view: str) -> bool:
    if view == "OVERALL":
        return True
    if view == "FLEX":
        return position in FLEX_POSITIONS
    return position == view


def rank_view(players: list[dict], model: str, scoring: str, view: str) -> list[str]:
    """Player ids for one (model, scoring, view) board, best first. Players without a projection
    under `model` are left off the ranking (they are listed in the snapshot's `unprojected`)."""
    if model not in MODELS or scoring not in SCORINGS or view not in VIEWS:
        raise ValueError(f"unknown board {model}/{scoring}/{view}")
    rows = [
        p
        for p in players
        if in_view(p["position"], view) and p["projections"].get(model) is not None
    ]
    rows.sort(key=lambda p: (-p["projections"][model][scoring], p["player_id"]))
    return [p["player_id"] for p in rows]


def snapshot_id(content: dict) -> str:
    blob = json.dumps(content, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def assemble_snapshot(
    *,
    season: int,
    week: int,
    generated_at: dt.datetime,
    entries: list[Entry],
    exclusions: Exclusions,
    projections: dict[str, dict[str, float]],
    sources: dict[str, dict[str, str]],
    inputs: dict[str, dict],
    models: dict[str, dict],
    data_sources: list[dict],
    roster_week_used: int | None,
    checks: dict,
) -> dict:
    """The saved board. `projections[model][player_id]` is Full-PPR expected points;
    `sources[model][player_id]` names what produced it; `inputs[player_id]` holds the model inputs
    shown for inspection. Everything a viewer needs is precomputed here so the ranking rule exists
    in exactly one place."""
    players: list[dict] = []
    unprojected: dict[str, list[str]] = {m: [] for m in MODELS}
    for e in sorted(entries, key=lambda e: e.player_id):
        inp = inputs.get(e.player_id, {})
        rec = inp.get("receptions_avg_last3")
        proj = {m: scored(projections[m].get(e.player_id), rec) for m in MODELS}
        for m in MODELS:
            if proj[m] is None:
                unprojected[m].append(e.player_id)
        players.append(
            {
                **asdict(e),
                "projections": proj,
                "projection_source": {m: sources[m].get(e.player_id) for m in MODELS},
                "inputs": inp,
            }
        )
    boards = {
        m: {s: {v: rank_view(players, m, s, v) for v in VIEWS} for s in SCORINGS} for m in MODELS
    }
    content = {
        "beta_version": BETA_VERSION,
        "experimental": True,
        "disclaimer": DISCLAIMER,
        "season": season,
        "week": week,
        "generated_at": generated_at.isoformat(),
        "cutoff": generated_at.isoformat(),
        "roster_week_used": roster_week_used,
        "scoring": {FULL_PPR: "1.0 point per reception", HALF_PPR: HALF_PPR_METHOD},
        "models": models,
        "data_sources": data_sources,
        "exclusions": asdict(exclusions),
        "unprojected": unprojected,
        "checks": checks,
        "players": players,
        "boards": boards,
    }
    return {"snapshot_id": snapshot_id(content), **content}
