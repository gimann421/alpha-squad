"""Builds `player_week_features`: the leakage-safe engineered feature panel used by
baselines/ML (M4/M5) for training and walk-forward evaluation.

Every non-target column is computed with a SQL window frame
`ROWS BETWEEN N PRECEDING AND 1 PRECEDING` (or `UNBOUNDED PRECEDING AND 1 PRECEDING` for
season-to-date), ordered by `game_date`. That frame excludes the current row by construction
— a row's features cannot reflect its own or any future game's outcome no matter what data
gets appended later. `target_fantasy_points_ppr` is this week's real, unlagged outcome, kept
only as the training target — never read back in as a feature for the same row (enforced by
tests/leakage/test_target_isolation.py).

FEATURE_VERSION must be bumped whenever the feature definitions below change, so stored
predictions stay attributable to the feature logic that produced them (ARCHITECTURE.md §10
provenance requirement)."""

from __future__ import annotations

import duckdb

from alpha_squad.sources.base import utcnow

FEATURE_VERSION = "player_week_features_v1"

_LAG3 = "ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING"
_SEASON_TO_DATE = "ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING"


def build_player_week_features(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _panel AS
        SELECT
            player_id, season, week, game_date, position,
            CAST(COUNT(*) OVER (
                PARTITION BY player_id, season ORDER BY game_date, week {_SEASON_TO_DATE}
            ) AS INTEGER) AS games_played_prior,
            AVG(fantasy_points_ppr) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS fp_ppr_avg_last3,
            AVG(fantasy_points_ppr) OVER (
                PARTITION BY player_id, season ORDER BY game_date, week {_SEASON_TO_DATE}
            ) AS fp_ppr_avg_season_to_date,
            AVG(targets) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS targets_avg_last3,
            AVG(carries) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS carries_avg_last3,
            AVG(receptions) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS receptions_avg_last3,
            AVG(target_share) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS target_share_avg_last3,
            AVG(offense_snap_pct) OVER (
                PARTITION BY player_id ORDER BY game_date, season, week {_LAG3}
            ) AS snap_pct_avg_last3,
            fantasy_points_ppr AS target_fantasy_points_ppr
        FROM player_week_stats
        """
    )

    rows = con.execute(
        """
        INSERT INTO player_week_features (
            player_id, season, week, game_date, position, games_played_prior,
            fp_ppr_avg_last3, fp_ppr_avg_season_to_date, targets_avg_last3,
            carries_avg_last3, receptions_avg_last3, target_share_avg_last3,
            snap_pct_avg_last3, target_fantasy_points_ppr, feature_version, built_at
        )
        SELECT
            player_id, season, week, game_date, position, games_played_prior,
            fp_ppr_avg_last3, fp_ppr_avg_season_to_date, targets_avg_last3,
            carries_avg_last3, receptions_avg_last3, target_share_avg_last3,
            snap_pct_avg_last3, target_fantasy_points_ppr, ?, ?
        FROM _panel
        ON CONFLICT (player_id, season, week) DO UPDATE SET
            game_date = excluded.game_date,
            position = excluded.position,
            games_played_prior = excluded.games_played_prior,
            fp_ppr_avg_last3 = excluded.fp_ppr_avg_last3,
            fp_ppr_avg_season_to_date = excluded.fp_ppr_avg_season_to_date,
            targets_avg_last3 = excluded.targets_avg_last3,
            carries_avg_last3 = excluded.carries_avg_last3,
            receptions_avg_last3 = excluded.receptions_avg_last3,
            target_share_avg_last3 = excluded.target_share_avg_last3,
            snap_pct_avg_last3 = excluded.snap_pct_avg_last3,
            target_fantasy_points_ppr = excluded.target_fantasy_points_ppr,
            feature_version = excluded.feature_version,
            built_at = excluded.built_at
        RETURNING player_id
        """,
        [FEATURE_VERSION, utcnow()],
    ).fetchall()
    return len(rows)


def features_as_of(con: duckdb.DuckDBPyConnection, as_of_date) -> list[dict]:
    """Row-level as-of filter: even though each row's *features* are leakage-safe by
    construction, a caller reconstructing "what did we know as of date D" must not see rows
    for games that hadn't been played yet as of D. This is the second, independent safety
    layer (docs/DECISIONS.md D-features-1)."""
    rows = con.execute(
        "SELECT * FROM player_week_features WHERE game_date < ? ORDER BY player_id, season, week",
        [as_of_date],
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, row, strict=True)) for row in rows]
