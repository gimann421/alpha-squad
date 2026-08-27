"""Season projections for kickers and team defenses (docs/DECISIONS.md D57).

These two positions get a *baseline*, not an ML model, and the choice is measured rather
than asserted. Walk-forward over real 2015-2025 seasons, comparing every candidate against
the actual outcome:

    K    n=368  year-over-year r=0.406
         weighted-2yr MAE 33.60 | shrunk(0.5) 34.10 | shrunk(0.3) 34.98
         | prior-year 37.44 | positional-mean 38.37
    DST  n=352  year-over-year r=0.294
         shrunk(0.3) MAE 22.55 | shrunk(0.5) 23.01 | positional-mean 23.60
         | weighted-2yr 25.18 | prior-year 27.14

Two honest conclusions follow, and they differ by position, which is why this is not one
formula applied to both:

* A kicker's own history carries real signal (r=0.41), and two seasons of it beat one, so K
  uses the same 0.65/0.35 weighting PRODUCT_SPEC.md already specifies for skill positions.
* A defense's history carries much less (r=0.29), and shrinking hard toward the positional
  mean beats trusting the prior season by a wide margin (22.55 vs 27.14) -- so DST is mostly
  "expect an average defense", nudged by what this one did.

Both signals are weak in absolute terms. That is a real property of these positions, not a
deficiency to paper over: a K/DST projection is close to a coin flip, and the draft engine
should treat it that way rather than being handed a false precision. An ML model here would
imply an accuracy the data does not support.

Leakage safety: every value for season S is computed from seasons strictly before S,
including the positional mean, which is recomputed per target season rather than taken over
the whole table.
"""

from __future__ import annotations

import duckdb

from alpha_squad.features.kicking_defense import DST_POSITION, KICKER_POSITION
from alpha_squad.sources.base import utcnow

MODEL_NAME = "baseline_kdst"

# Measured above. K trusts its own two-season history; DST is mostly the positional mean.
KICKER_WEIGHTS = (0.65, 0.35)  # (season S-1, season S-2)
DST_PRIOR_WEIGHT = 0.3  # remainder goes to the walk-forward positional mean

# The earliest season with enough prior history for any of this to mean anything. Below it
# there is no prior season to read and the baseline would be inventing a number.
MIN_PROJECTABLE_SEASON = 2013


def _season_points(
    con: duckdb.DuckDBPyConnection, position: str, season: int
) -> dict[str, float]:
    rows = con.execute(
        "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
        "WHERE season = ? AND position = ?",
        [season, position],
    ).fetchall()
    return dict(rows)


def _positional_mean_before(
    con: duckdb.DuckDBPyConnection, position: str, season: int
) -> float:
    """Mean season total across every prior season. Strictly `< season`, so a projection for
    S never sees S's own outcomes."""
    row = con.execute(
        "SELECT avg(total_fantasy_points_ppr) FROM player_season_stats "
        "WHERE position = ? AND season < ?",
        [position, season],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def project_kickers(con: duckdb.DuckDBPyConnection, season: int) -> dict[str, float]:
    """0.65 * S-1 + 0.35 * S-2, with S-1 standing in for a missing S-2 (a kicker with one
    season of history is projected on that season rather than dropped -- dropping him would
    make him undraftable, which is a worse error than a noisy estimate)."""
    prev, prev2 = _season_points(con, KICKER_POSITION, season - 1), _season_points(
        con, KICKER_POSITION, season - 2
    )
    w1, w2 = KICKER_WEIGHTS
    return {pid: w1 * p1 + w2 * prev2.get(pid, p1) for pid, p1 in prev.items()}


def project_defenses(con: duckdb.DuckDBPyConnection, season: int) -> dict[str, float]:
    """0.3 * S-1 + 0.7 * the walk-forward positional mean. The heavy shrinkage is what the
    measurement supports, not conservatism for its own sake."""
    prev = _season_points(con, DST_POSITION, season - 1)
    pos_mean = _positional_mean_before(con, DST_POSITION, season)
    w = DST_PRIOR_WEIGHT
    return {pid: w * p1 + (1.0 - w) * pos_mean for pid, p1 in prev.items()}


def build_kdst_projections(con: duckdb.DuckDBPyConnection, seasons: list[int]) -> int:
    """Persist K and DST projections into `projection_snapshot`, the table every baseline and
    model already reports through, so they are queryable and comparable alongside the rest."""
    built_at = utcnow()
    total = 0
    for season in seasons:
        if season < MIN_PROJECTABLE_SEASON:
            continue
        for position, projections in (
            (KICKER_POSITION, project_kickers(con, season)),
            (DST_POSITION, project_defenses(con, season)),
        ):
            for player_id, points in projections.items():
                con.execute(
                    """
                    INSERT INTO projection_snapshot
                        (model_name, player_id, season, position, predicted_points, built_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (model_name, player_id, season) DO UPDATE SET
                        position = excluded.position,
                        predicted_points = excluded.predicted_points,
                        built_at = excluded.built_at
                    """,
                    [MODEL_NAME, player_id, season, position, points, built_at],
                )
                total += 1
    return total
