"""Historical comps: for a given prospect, finds the K most statistically similar past
rookies (by standardized draft capital + combine testing) as an explanation artifact —
ARCHITECTURE.md's rookie pipeline calls for "historical comps as explanation." Only ever
draws from rookies whose class is strictly before the target prospect's, so a comp set is
itself a legitimate as-of view, not informed by outcomes that hadn't happened yet."""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from alpha_squad.models.rookie.data import load_rookie_class_data
from alpha_squad.models.rookie.features import FEATURES


def find_historical_comps(
    con: duckdb.DuckDBPyConnection, player_id: str, draft_class: int, position: str, k: int = 5
) -> list[dict]:
    pool = load_rookie_class_data(con, position, 1990, draft_class - 1)
    if pool.empty:
        return []

    target_row = con.execute(
        f"SELECT player_id, {', '.join(FEATURES)} FROM rookie_features WHERE player_id = ?",
        [player_id],
    ).fetchdf()
    if target_row.empty:
        return []

    # target_row comes straight from DuckDB (not through load_rookie_class_data's
    # imputation), so its integer columns can come back as pandas nullable Int64 rather than
    # float64 — concatenating with pool[FEATURES] before forcing a numeric dtype produced an
    # object-dtype array that np.linalg.norm can't take a sqrt over. Cast explicitly.
    stacked = pd.concat([pool[FEATURES], target_row[FEATURES]], ignore_index=True).astype(float)
    stacked = stacked.fillna(stacked.mean(numeric_only=True)).fillna(0.0)
    means = stacked.mean()
    stds = stacked.std().replace(0, 1.0)
    standardized = (stacked - means) / stds

    pool_vectors = standardized.iloc[:-1].to_numpy()
    target_vector = standardized.iloc[-1].to_numpy()

    distances = np.linalg.norm(pool_vectors - target_vector[None, :], axis=1)
    order = np.argsort(distances)[:k]

    results = []
    for idx in order:
        row = pool.iloc[idx]
        results.append(
            {
                "player_id": row["player_id"],
                "draft_class": int(row["draft_class"]),
                "rookie_year_ppr_points": float(row["rookie_year_ppr_points"]),
                "breakout_top24": bool(row["breakout_top24"]),
                "similarity_distance": float(distances[idx]),
            }
        )
    return results
