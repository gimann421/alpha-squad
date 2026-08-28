"""Kicker and team-defense fantasy scoring (docs/DECISIONS.md D57).

The 1-QB target format (docs/TARGET_FORMAT_1QB.md) starts a K and a DEF. Neither existed in
this system before, for two different reasons, both verified against the real data rather
than assumed:

* **Kickers** are ingested -- `player_week_stats` has 125 of them back to 2012 -- but score
  0.0. nflverse's `fantasy_points_ppr` only prices passing/rushing/receiving, so every
  kicker's season total was exactly 0.0 (571 rows, 7 non-zero, all from incidental
  non-kicking plays). The kicking *components* are all present in the raw weekly file
  (`fg_made_0_19` ... `fg_made_60_`, `fg_missed`, `pat_made`, `pat_missed`), so the points
  are computed here from real stats, not sourced from anywhere that already has them.

* **Team defenses** did not exist as an entity at all -- absent from `players`,
  `player_id_map`, `player_season_stats`, and `market_snapshot`. A DST is not an NFL player,
  so it gets a synthetic canonical id built from the team's stable abbreviation
  (`asq_dst_KC`), never from a name (CLAUDE.md). Its stats come from nflverse
  `stats_team_week`'s `def_*` columns plus points allowed from `team_week_points`.

Scoring follows Sleeper's documented defaults, because Sleeper is the league source this
deployment actually integrates with (D33/D34) -- so a real connected league scores the way
the benchmark does. The rules are data, not code: a league whose config carries its own
`scoring` block overrides them per-league, the same way PPR value already does.

Built entirely from already-played games, so like `features/season_aggregate.py` this
carries no leakage risk of its own -- leakage is a property of which seasons a *model* is
allowed to read, enforced in models/, not here.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot

DST_POSITION = "DST"
KICKER_POSITION = "K"

# A DST's canonical id is derived from the team's abbreviation, which is a stable code (KC,
# BUF, ...), not a display name (CLAUDE.md forbids names as production keys). nflverse
# normalizes relocated franchises to their *current* code throughout history -- verified: the
# real team_week_stats set is exactly 32 codes with LV, LA and JAX, and no OAK, STL or SD at
# any season -- so one id covers a franchise across a relocation rather than splitting it.
DST_ID_PREFIX = "asq_dst_"

# FantasyPros uses its own abbreviations for three franchises. Mapping them explicitly, rather
# than fuzzy-matching names, is what lets DST market ranks join the same canonical entity the
# stats do. Verified against real data: these are the only three of 32 that differ.
FANTASYPROS_TEAM_ALIASES = {"JAC": "JAX", "LAR": "LA", "OAK": "LV"}


def dst_player_id(team: str) -> str:
    return f"{DST_ID_PREFIX}{team}"


@dataclass(frozen=True)
class KickerScoring:
    """Sleeper's default kicker scoring. Distance bands are what make kicker scoring worth
    computing properly rather than approximating from total FGs made."""

    fg_0_19: float = 3.0
    fg_20_29: float = 3.0
    fg_30_39: float = 3.0
    fg_40_49: float = 4.0
    fg_50_59: float = 5.0
    fg_60_plus: float = 5.0
    pat_made: float = 1.0
    fg_missed: float = -1.0
    pat_missed: float = -1.0


@dataclass(frozen=True)
class DstScoring:
    """Sleeper's default team-defense scoring, including the points-allowed tier table."""

    sack: float = 1.0
    interception: float = 2.0
    fumble_recovery: float = 2.0
    safety: float = 2.0
    defensive_td: float = 6.0
    special_teams_td: float = 6.0
    blocked_kick: float = 2.0
    # (max points allowed, fantasy points). Evaluated in order; the first band whose bound
    # the opponent's score falls at or under wins. The final entry is the open-ended tail.
    points_allowed_bands: tuple[tuple[int, float], ...] = (
        (0, 10.0),
        (6, 7.0),
        (13, 4.0),
        (20, 1.0),
        (27, 0.0),
        (34, -1.0),
    )
    points_allowed_tail: float = -4.0

    def points_allowed_score(self, points_allowed: float) -> float:
        for bound, score in self.points_allowed_bands:
            if points_allowed <= bound:
                return score
        return self.points_allowed_tail


DEFAULT_KICKER_SCORING = KickerScoring()
DEFAULT_DST_SCORING = DstScoring()


def build_kicker_week_points(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    seasons: list[int],
    scoring: KickerScoring = DEFAULT_KICKER_SCORING,
) -> int:
    """Compute real kicker fantasy points from the raw weekly FG/PAT components and write
    them onto the kicker rows `features/player.py` already ingested.

    An UPDATE rather than an INSERT: the rows exist, correctly identity-joined, with every
    other column already right -- only `fantasy_points`/`fantasy_points_ppr` were wrong (0.0,
    because nflverse does not score kicking). Kicking has no reception component, so the
    standard and PPR totals are the same number by construction, and both are written so a
    non-PPR consumer is not silently left with the stale zero."""
    total = 0
    for season in seasons:
        snap = require_snapshot(con, "nflverse", "stats_player_week", season=season)
        src = reader_expr(snap["local_path"])
        rows = con.execute(
            f"""
            WITH kicking AS (
                SELECT
                    s.player_id AS gsis_id, s.season, s.week,
                    COALESCE(s.fg_made_0_19, 0) * ? + COALESCE(s.fg_made_20_29, 0) * ?
                  + COALESCE(s.fg_made_30_39, 0) * ? + COALESCE(s.fg_made_40_49, 0) * ?
                  + COALESCE(s.fg_made_50_59, 0) * ? + COALESCE(s."fg_made_60_", 0) * ?
                  + COALESCE(s.pat_made, 0) * ? + COALESCE(s.fg_missed, 0) * ?
                  + COALESCE(s.pat_missed, 0) * ? AS points
                FROM {src} s
                WHERE s.position = ?
            )
            UPDATE player_week_stats t
            SET fantasy_points = k.points, fantasy_points_ppr = k.points
            FROM kicking k
            JOIN players p ON p.gsis_id = k.gsis_id
            WHERE t.player_id = p.player_id AND t.season = k.season AND t.week = k.week
            RETURNING t.player_id
            """,
            [
                scoring.fg_0_19,
                scoring.fg_20_29,
                scoring.fg_30_39,
                scoring.fg_40_49,
                scoring.fg_50_59,
                scoring.fg_60_plus,
                scoring.pat_made,
                scoring.fg_missed,
                scoring.pat_missed,
                KICKER_POSITION,
            ],
        ).fetchall()
        total += len(rows)
    return total


def ensure_dst_entities(con: duckdb.DuckDBPyConnection, seasons: list[int]) -> int:
    """Create one canonical `players` row per team that actually appears in `team_week_stats`
    for these seasons. Derived from real data rather than a hardcoded team list, so a
    relocation or expansion team needs no code change.

    `gsis_id` repeats the canonical id rather than holding a real NFL identifier, because a
    team defense has none -- see the `players` DDL. The 'asq_dst_' prefix makes that explicit
    and guarantees it can never be mistaken for, or collide with, a real GSIS id."""
    rows = con.execute(
        """
        INSERT INTO players (player_id, gsis_id, display_name, position)
        SELECT DISTINCT ? || t.team, ? || t.team, t.team || ' D/ST', ?
        FROM team_week_stats t
        WHERE t.season = ANY(?) AND t.team IS NOT NULL
        ON CONFLICT (player_id) DO NOTHING
        RETURNING player_id
        """,
        [DST_ID_PREFIX, DST_ID_PREFIX, DST_POSITION, seasons],
    ).fetchall()
    return len(rows)


def build_dst_week_stats(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    seasons: list[int],
    scoring: DstScoring = DEFAULT_DST_SCORING,
) -> int:
    """One `player_week_stats` row per team-defense per real regular-season game.

    Read from the raw nflverse `stats_team_week` snapshot rather than the normalized
    `team_week_stats` table: that table keeps only the offensive-environment columns the
    projection features need (plays, pass_rate, EPA), so the `def_*` counting stats a DST is
    scored on exist only at the source. A team's own row carries what its defense did, so
    `def_sacks` on team T's row is T's defense's sack count.

    Points allowed comes from `team_week_points.opponent_points` -- the same game, the other
    team's real final score -- which is the exact quantity the points-allowed tier is defined
    on, not an approximation from EPA or yards.

    Blocked kicks are `def_punt_blocks + def_pat_blocks + def_fg_blocks`, the three block
    types nflverse tracks separately; fantasy scoring prices them identically."""
    bands = scoring.points_allowed_bands
    case_sql = " ".join(f"WHEN wp.opponent_points <= {b} THEN {s}" for b, s in bands)
    total_rows = 0
    for season in seasons:
        snap = require_snapshot(con, "nflverse", "stats_team_week", season=season)
        src = reader_expr(snap["local_path"])
        rows = con.execute(
            f"""
        INSERT INTO player_week_stats (
            player_id, season, week, game_id, game_date, team, position,
            fantasy_points, fantasy_points_ppr, source_snapshot_id
        )
        SELECT
            ? || ts.team, ts.season, wp.week, ts.game_id, g.game_date, ts.team, ?,
            points.total, points.total, ?
        FROM {src} ts
        JOIN games g ON g.game_id = ts.game_id AND g.game_type = 'REG'
        JOIN team_week_points wp ON wp.game_id = ts.game_id AND wp.team = ts.team
        CROSS JOIN LATERAL (
            SELECT
                COALESCE(ts.def_sacks, 0) * ?
              + COALESCE(ts.def_interceptions, 0) * ?
              + COALESCE(ts.def_fumbles, 0) * ?
              + COALESCE(ts.def_safeties, 0) * ?
              + COALESCE(ts.def_tds, 0) * ?
              + COALESCE(ts.special_teams_tds, 0) * ?
              + (COALESCE(ts.def_punt_blocks, 0) + COALESCE(ts.def_pat_blocks, 0)
                 + COALESCE(ts.def_fg_blocks, 0)) * ?
              + (CASE {case_sql} ELSE ? END) AS total
        ) points
        WHERE ts.season = ?
        ON CONFLICT (player_id, season, week) DO UPDATE SET
            game_id = excluded.game_id,
            game_date = excluded.game_date,
            team = excluded.team,
            position = excluded.position,
            fantasy_points = excluded.fantasy_points,
            fantasy_points_ppr = excluded.fantasy_points_ppr,
            source_snapshot_id = excluded.source_snapshot_id
        RETURNING player_id
        """,
            [
                DST_ID_PREFIX,
                DST_POSITION,
                snap["snapshot_id"],
                scoring.sack,
                scoring.interception,
                scoring.fumble_recovery,
                scoring.safety,
                scoring.defensive_td,
                scoring.special_teams_td,
                scoring.blocked_kick,
                scoring.points_allowed_tail,
                season,
            ],
        ).fetchall()
        total_rows += len(rows)
    return total_rows


def build_kicking_and_defense(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> dict[str, int]:
    """Everything a league that starts a K and a DEF needs, in dependency order. Safe to
    re-run: each step upserts."""
    kicker_rows = build_kicker_week_points(con, settings, seasons)
    dst_entities = ensure_dst_entities(con, seasons)
    dst_rows = build_dst_week_stats(con, settings, seasons)
    return {
        "kicker_week_rows_scored": kicker_rows,
        "dst_entities_created": dst_entities,
        "dst_week_rows": dst_rows,
    }
