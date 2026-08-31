"""Preseason-knowable RB availability features (D70, `docs/RB_AVAILABILITY_PREREGISTRATION.md`).

Implements exactly the closed feature list section 5 of the pre-registration committed --
**F1-F4, no more, no fifth feature, no sweep**:

    F1  avail_games_played_history   mean games played over up to 3 prior seasons (S-1..S-3)
    F2  avail_age                    age at the target season's Sept 1, from `players.birth_date`
    F3  avail_position_cohort_games  mean games played across the WHOLE position cohort in S-1
                                      (a population statistic, identical for every player-row
                                      sharing a position/target_season -- not player-specific)
    F4  avail_workload_per_game      (carries + receptions) / games_played in season S-1

Every one of these is computable from data timestamped strictly before the target season began:
`birth_date` is static, and every other input is drawn from `player_season_stats` seasons
`<= target_season - 1`. Target-season games played -- the quantity D69 found associated with
the RB residual -- is never a feature; it is what B3 checks these features against, out of fold.

Leakage guard
-------------
The SQL in `build_availability_features` can only ever join to `s1.season = target_season - 1`
and earlier (every subquery/join condition is bounded by `s1.season`), so it cannot reach the
target season by construction. `validate_no_leakage` is the same structural guard
`projection_calibration.py::fit_arm` uses (raise if any season handed to it is
`>= target_season`), applied at the point a caller assembles a training set from this module's
output -- exactly where a mistake (e.g. forgetting to exclude the target season's own row)
would actually leak, and exactly what the pre-registration's "requesting a target-season
feature raises" requirement is testing.
"""

from __future__ import annotations

from collections.abc import Iterable

import duckdb
import pandas as pd

#: The closed feature list. Order matches the pre-registration's table; nothing may be added
#: to this list without a new pre-registration.
AVAILABILITY_FEATURES: list[str] = [
    "avail_games_played_history",
    "avail_age",
    "avail_position_cohort_games",
    "avail_workload_per_game",
]

#: F1's lookback window -- up to 3 prior seasons (S-1, S-2, S-3), including whichever of those
#: exist. Matches the pre-registration's "prior 2-3 seasons" language; a player with only one
#: prior season available gets a 1-season average rather than being dropped, since
#: `load_season_level_data`'s own INNER JOIN already requires at least an S-1 row to exist.
GAMES_HISTORY_LOOKBACK_SEASONS = 3


def validate_no_leakage(source_seasons: Iterable[int], target_season: int) -> None:
    """Raise if any season in `source_seasons` is `>= target_season`.

    Call this at the point a training/calibration set is assembled from this module's output,
    the same way `projection_calibration.py::fit_arm` guards its own training rows. It is a
    redundant, defense-in-depth check on top of the SQL's own structural boundary -- if the SQL
    were ever edited to loosen that boundary, this is what would catch it."""
    leaked = sorted({s for s in source_seasons if s >= target_season})
    if leaked:
        raise ValueError(
            f"leakage: availability features for target season {target_season} were handed "
            f"source data from season(s) {leaked}. Feature construction may only use strictly "
            f"earlier seasons."
        )


def build_availability_features(
    con: duckdb.DuckDBPyConnection, position: str, season_start: int, season_end: int
) -> pd.DataFrame:
    """One row per (player_id, target_season) for `target_season` in `[season_start, season_end]`,
    with F1-F4. Mirrors `models/established/season_level.py::load_season_level_data`'s shape
    (same `target_season = s1.season + 1` convention) so the two frames merge on
    `(player_id, target_season)` with no reindexing.

    F3 (`avail_position_cohort_games`) is a population statistic -- the same value for every
    player at `position` in a given `target_season` -- computed by a separate GROUP BY subquery
    rather than a window function, so it is legible as exactly what it is: a season-level
    covariate, not a per-player one."""
    df = con.execute(
        """
        SELECT
            s1.player_id,
            s1.season + 1 AS target_season,
            (
                SELECT avg(h.games_played)
                FROM player_season_stats h
                WHERE h.player_id = s1.player_id
                  AND h.season BETWEEN s1.season - (? - 1) AND s1.season
            ) AS avail_games_played_history,
            date_diff('year', p.birth_date, make_date(s1.season + 1, 9, 1)) AS avail_age,
            cohort.cohort_mean_games AS avail_position_cohort_games,
            CASE
                WHEN s1.games_played > 0
                THEN (coalesce(s1.total_carries, 0) + coalesce(s1.total_receptions, 0))
                     / s1.games_played
                ELSE NULL
            END AS avail_workload_per_game
        FROM player_season_stats s1
        LEFT JOIN players p ON p.player_id = s1.player_id
        LEFT JOIN (
            SELECT season, avg(games_played) AS cohort_mean_games
            FROM player_season_stats
            WHERE position = ?
            GROUP BY season
        ) cohort ON cohort.season = s1.season
        WHERE s1.position = ? AND s1.season + 1 BETWEEN ? AND ?
        """,
        [GAMES_HISTORY_LOOKBACK_SEASONS, position, position, season_start, season_end],
    ).fetchdf()
    return df
