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
    con: duckdb.DuckDBPyConnection,
    position: str,
    draft_class_start: int,
    draft_class_end: int,
    features: list[str] | None = None,
) -> pd.DataFrame:
    """`features` defaults to the production set. It is a parameter because the D39 ablation
    trains a *different* set (baseline + college production) over the same folds: this SELECT
    used to hardcode FEATURES, so any arm asking for a column outside the production set got a
    DataFrame silently missing it and died on a pandas KeyError at fit time."""
    features = features if features is not None else FEATURES
    df = con.execute(
        f"""
        SELECT player_id, draft_class, {", ".join(features)}, rookie_year_ppr_points, breakout_top24
        FROM rookie_features
        WHERE position = ? AND draft_class BETWEEN ? AND ?
        """,
        [position, draft_class_start, draft_class_end],
    ).fetchdf()
    return _impute(df, features)


def _impute(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    df["draft_round"] = df["draft_round"].fillna(UNDRAFTED_ROUND_FALLBACK)
    df["draft_pick"] = df["draft_pick"].fillna(UNDRAFTED_PICK_FALLBACK)
    other_features = [f for f in features if f not in ("draft_round", "draft_pick")]
    df[other_features] = df[other_features].fillna(0.0)
    return df


def load_rookie_projection_data(
    con: duckdb.DuckDBPyConnection,
    position: str,
    draft_class: int,
    features: list[str] | None = None,
) -> pd.DataFrame:
    """Loads an unplayed draft class from `rookie_projection_features` for scoring. Shares
    `_impute` with the training loader so an undrafted 2026 prospect is imputed exactly the
    way an undrafted 2019 prospect was during training -- if these diverged, the model would
    see inputs that don't mean what it learned (docs/DECISIONS.md D40)."""
    features = features if features is not None else FEATURES
    df = con.execute(
        f"""
        SELECT player_id, draft_class, {", ".join(features)}
        FROM rookie_projection_features
        WHERE position = ? AND draft_class = ?
        """,
        [position, draft_class],
    ).fetchdf()
    return _impute(df, features)
