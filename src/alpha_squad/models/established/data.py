"""Loads position-specific training/prediction matrices from `player_week_features`
(M3/M5). Missing lag values (a player/team with no prior games yet) are imputed to 0 — a
truthful choice, not a guess: "no trailing opportunity data" and "zero opportunity" are the
same signal for a model, and every model here is expected to also see games_played_prior=0
as an explicit low-history marker."""

from __future__ import annotations

import duckdb
import pandas as pd

from alpha_squad.models.established.features import FULL_FEATURES, TARGET_COLUMN


def load_position_week_data(
    con: duckdb.DuckDBPyConnection,
    position: str,
    season_start: int,
    season_end: int,
    feature_cols: list[str] = FULL_FEATURES,
) -> pd.DataFrame:
    cols_sql = ", ".join(feature_cols)
    df = con.execute(
        f"""
        SELECT player_id, season, week, {cols_sql}, {TARGET_COLUMN}
        FROM player_week_features
        WHERE position = ? AND season BETWEEN ? AND ?
        """,
        [position, season_start, season_end],
    ).fetchdf()
    df[feature_cols] = df[feature_cols].fillna(0.0)
    return df
