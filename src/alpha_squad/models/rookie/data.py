"""Loads rookie training/prediction matrices from `rookie_features`, walk-forward by draft
class. Missing combine measurables (not every prospect gets fully tested) are imputed to 0
after standardization context is irrelevant for tree models (CatBoost handles NaN natively,
but the Ridge-free feature set here is deliberately small and tree-only — see train.py).
Missing draft capital (undrafted) is imputed to a deliberately bad round/pick, never 0."""

from __future__ import annotations

import duckdb
import pandas as pd

from alpha_squad.models.rookie.features import (
    FEATURES,
    UNDRAFTED_PICK_FALLBACK,
    UNDRAFTED_ROUND_FALLBACK,
)


def load_rookie_class_data(
    con: duckdb.DuckDBPyConnection, position: str, draft_class_start: int, draft_class_end: int
) -> pd.DataFrame:
    df = con.execute(
        f"""
        SELECT player_id, draft_class, {", ".join(FEATURES)}, rookie_year_ppr_points, breakout_top24
        FROM rookie_features
        WHERE position = ? AND draft_class BETWEEN ? AND ?
        """,
        [position, draft_class_start, draft_class_end],
    ).fetchdf()
    df["draft_round"] = df["draft_round"].fillna(UNDRAFTED_ROUND_FALLBACK)
    df["draft_pick"] = df["draft_pick"].fillna(UNDRAFTED_PICK_FALLBACK)
    other_features = [f for f in FEATURES if f not in ("draft_round", "draft_pick")]
    df[other_features] = df[other_features].fillna(0.0)
    return df
