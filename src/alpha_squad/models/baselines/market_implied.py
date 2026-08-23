"""ECR-implied baseline (PRODUCT_SPEC.md §Modeling: "FantasyPros projections" /
"ADP-implied value where appropriate" — docs/DECISIONS.md D16/D17 record why ECR-implied is
the closest available substitute for a genuine ADP series in this environment).

FantasyPros ECR is a *rank*, not a points value, so this fits a rank-to-points calibration
curve per position — using only seasons strictly before the one being predicted (expanding
window), never the target season or anything after it. That walk-forward discipline is what
keeps this a legitimate baseline rather than a curve fit on the answer it's trying to
predict."""

from __future__ import annotations

import duckdb
from sklearn.isotonic import IsotonicRegression

MARKET_ECR_IMPLIED = "baseline_ecr_implied"

_POSITIONS = ("QB", "RB", "WR", "TE")
_MIN_TRAINING_ROWS = 10


def _historical_rank_points(con: duckdb.DuckDBPyConnection, position: str, before_season: int):
    """(ecr_rank, actual_total_points) pairs from each player's single latest July/August
    preseason ECR snapshot per season, joined to that season's real outcome — restricted to
    seasons strictly before `before_season`."""
    return con.execute(
        """
        WITH preseason_ecr AS (
            SELECT
                player_id, year(scrape_date) AS season, ecr_rank,
                row_number() OVER (
                    PARTITION BY player_id, year(scrape_date) ORDER BY scrape_date DESC
                ) AS rn
            FROM market_snapshot
            WHERE ecr_type = 'ro' AND month(scrape_date) IN (7, 8)
        )
        SELECT e.ecr_rank, s.total_fantasy_points_ppr
        FROM preseason_ecr e
        JOIN player_season_stats s ON s.player_id = e.player_id AND s.season = e.season
        WHERE e.rn = 1 AND e.season < ? AND s.position = ?
        """,
        [before_season, position],
    ).fetchall()


def _preseason_ranks_for_season(con: duckdb.DuckDBPyConnection, position: str, season: int):
    return con.execute(
        """
        SELECT player_id, ecr_rank FROM (
            SELECT
                player_id, ecr_rank, position,
                row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot
            WHERE ecr_type = 'ro' AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)
              AND position = ?
        ) WHERE rn = 1
        """,
        [season, position],
    ).fetchall()


def ecr_implied_baseline(con: duckdb.DuckDBPyConnection, target_season: int) -> dict[str, float]:
    predictions: dict[str, float] = {}
    for position in _POSITIONS:
        training = _historical_rank_points(con, position, target_season)
        if len(training) < _MIN_TRAINING_ROWS:
            continue  # not enough calibration history for this position/season yet

        ranks_train = [row[0] for row in training]
        points_train = [row[1] for row in training]
        curve = IsotonicRegression(increasing=False, out_of_bounds="clip")
        curve.fit(ranks_train, points_train)

        for player_id, rank in _preseason_ranks_for_season(con, position, target_season):
            predictions[player_id] = float(curve.predict([rank])[0])
    return predictions
