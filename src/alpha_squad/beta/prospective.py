"""Prospective weekly feature rows, computed by production's own feature builders (W16).

Production's `player_week_features` has a row for (player, season, week) only if the player has a
`player_week_stats` row for that week, i.e. only after he has played (W3 §2.1). Every feature
column is a window over STRICTLY PRIOR rows (`ROWS ... AND 1 PRECEDING`), so the features of a
week-`w` row never depend on week `w` itself -- only the row's existence does.

This module removes that dependency without re-implementing a single feature. In a throwaway
in-memory database it loads every stats row strictly before week `w`, appends one placeholder row
per eligible player (and per scheduled team) for week `w` with every stat NULL, and runs
production's unmodified builders (`build_player_week_features`, `build_team_week_features`,
`attach_team_features_to_player_panel`). The placeholder's own NULL stats sit in the excluded
current row of every window, so each placeholder receives exactly the features production would
have stored had the player played. `equivalence_check` verifies that claim on a completed week,
cell for cell, against production's stored rows.

The source connection is only read. Nothing is written outside the in-memory database.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import duckdb
import pandas as pd

from alpha_squad.features.panel import build_player_week_features
from alpha_squad.features.team import (
    attach_team_features_to_player_panel,
    build_team_week_features,
)
from alpha_squad.models.established.features import FULL_FEATURES
from alpha_squad.storage.db import init_db

PLACEHOLDER_GAME_ID = "beta_prospective"
FEATURE_COLUMNS: tuple[str, ...] = tuple(FULL_FEATURES)
OUTPUT_COLUMNS: tuple[str, ...] = (
    "player_id",
    "season",
    "week",
    "game_date",
    "position",
    "team",
    *FEATURE_COLUMNS,
)


@dataclass(frozen=True)
class PlayerSlot:
    player_id: str
    position: str
    team: str
    game_date: dt.date


@dataclass(frozen=True)
class TeamSlot:
    team: str
    game_date: dt.date


def _history(src: duckdb.DuckDBPyConnection, table: str, season: int, week: int) -> pd.DataFrame:
    return src.execute(
        f"SELECT * FROM {table} WHERE season < ? OR (season = ? AND week < ?)",
        [season, season, week],
    ).fetchdf()


def prospective_feature_rows(
    src: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    players: list[PlayerSlot],
    teams: list[TeamSlot],
) -> pd.DataFrame:
    """One feature row per `players` entry for (season, week), from games before `week` only.

    Raises if any requested player comes back without a row: a missing feature row would silently
    drop an eligible player, which is exactly the defect this module exists to remove."""
    if len({p.player_id for p in players}) != len(players):
        raise ValueError("duplicate player in prospective slots")
    stats = _history(src, "player_week_stats", season, week)
    team_stats = _history(src, "team_week_stats", season, week)

    scratch = duckdb.connect()
    try:
        init_db(scratch)
        for table, frame in (("player_week_stats", stats), ("team_week_stats", team_stats)):
            # The production tables carry foreign keys to `players`/`games`; the placeholders
            # reference no real game, so the scratch copies are plain tables of the same columns.
            scratch.execute(f"DROP TABLE {table}")
            scratch.register("_frame", frame)
            scratch.execute(f"CREATE TABLE {table} AS SELECT * FROM _frame")
            scratch.unregister("_frame")

        scratch.executemany(
            "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, team, "
            "position) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                [p.player_id, season, week, PLACEHOLDER_GAME_ID, p.game_date, p.team, p.position]
                for p in players
            ],
        )
        if teams:
            scratch.executemany(
                "INSERT INTO team_week_stats (team, season, week, game_id, game_date) "
                "VALUES (?, ?, ?, ?, ?)",
                [[t.team, season, week, PLACEHOLDER_GAME_ID, t.game_date] for t in teams],
            )

        build_player_week_features(scratch)
        build_team_week_features(scratch)
        attach_team_features_to_player_panel(scratch)

        cols = ", ".join(OUTPUT_COLUMNS)
        scratch.register("_want", pd.DataFrame({"player_id": [p.player_id for p in players]}))
        out = scratch.execute(
            f"SELECT {cols} FROM player_week_features f JOIN _want USING (player_id) "
            "WHERE f.season = ? AND f.week = ? ORDER BY player_id",
            [season, week],
        ).fetchdf()
    finally:
        scratch.close()

    missing = {p.player_id for p in players} - set(out["player_id"])
    if missing:
        raise RuntimeError(
            f"{len(missing)} eligible players got no feature row: {sorted(missing)[:5]}"
        )
    return out


def equivalence_check(
    src: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE"),
) -> dict:
    """For a COMPLETED week: rebuild every played player's row as if he had not played yet and
    compare it with production's stored row. Exact equality on every feature is required."""
    stored = src.execute(
        f"SELECT f.player_id, s.team, s.game_date, f.position, "
        f"{', '.join('f.' + c for c in FEATURE_COLUMNS)} "
        "FROM player_week_features f JOIN player_week_stats s USING (player_id, season, week) "
        "WHERE f.season = ? AND f.week = ? AND f.position IN (SELECT unnest(?)) "
        "ORDER BY f.player_id",
        [season, week, list(positions)],
    ).fetchdf()
    team_games = src.execute(
        "SELECT team, game_date FROM team_week_stats WHERE season = ? AND week = ?",
        [season, week],
    ).fetchall()
    players = [
        PlayerSlot(r.player_id, r.position, r.team, r.game_date)
        for r in stored.itertuples(index=False)
    ]
    rebuilt = prospective_feature_rows(
        src, season, week, players, [TeamSlot(t, d) for t, d in team_games]
    ).set_index("player_id")
    stored = stored.set_index("player_id")
    mismatched: list[str] = []
    for pid in stored.index:
        for c in FEATURE_COLUMNS:
            a, b = stored.at[pid, c], rebuilt.at[pid, c]
            if not ((pd.isna(a) and pd.isna(b)) or a == b):
                mismatched.append(f"{pid}:{c}")
    return {
        "season": season,
        "week": week,
        "rows_compared": len(stored),
        "cells_compared": len(stored) * len(FEATURE_COLUMNS),
        "cells_mismatched": len(mismatched),
        "examples": mismatched[:10],
        "exact": not mismatched,
    }
