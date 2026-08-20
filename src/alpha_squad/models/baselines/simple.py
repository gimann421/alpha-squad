"""Simple historical baselines (PRODUCT_SPEC.md §Modeling: "previous-season baseline",
"weighted 2-year baseline"). Both operate purely on `player_season_stats`, which is itself
built only from completed games — the only leakage discipline needed here is which *seasons*
a prediction for season S is allowed to read (always S-1 and earlier, never S itself)."""

from __future__ import annotations

import duckdb

PREVIOUS_YEAR = "baseline_previous_year"
WEIGHTED_2YR = "baseline_weighted_2yr"


def previous_year_baseline(con: duckdb.DuckDBPyConnection, target_season: int) -> dict[str, float]:
    """Predict season S's total PPR points as season S-1's actual total. Scoped to players
    who actually played in S-1 — an established-player baseline by definition; rookies are
    out of scope here and get their own pipeline (M7)."""
    rows = con.execute(
        "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats WHERE season = ?",
        [target_season - 1],
    ).fetchall()
    return {player_id: points for player_id, points in rows}


def weighted_two_year_baseline(
    con: duckdb.DuckDBPyConnection, target_season: int, *, w1: float = 0.65, w2: float = 0.35
) -> dict[str, float]:
    """0.65 * season S-1 + 0.35 * season S-2 (PRODUCT_SPEC.md's suggested weighting).
    Requires both prior seasons, so this is a stricter subset of previous_year_baseline's
    players."""
    rows = con.execute(
        """
        SELECT s1.player_id, ? * s1.total_fantasy_points_ppr + ? * s2.total_fantasy_points_ppr
        FROM player_season_stats s1
        JOIN player_season_stats s2 ON s2.player_id = s1.player_id AND s2.season = s1.season - 1
        WHERE s1.season = ?
        """,
        [w1, w2, target_season - 1],
    ).fetchall()
    return {player_id: points for player_id, points in rows}
