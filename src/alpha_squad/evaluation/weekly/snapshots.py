"""What a weekly ranking snapshot is, when it is, and who is eligible to be ranked in it (W1).

This module is the leakage boundary of the whole weekly program. Everything else --- metrics,
baselines, models --- is computed downstream of the universe this defines, so a mistake here
is not recoverable by anything later.

The cutoff is Friday, and that was measured, not chosen
------------------------------------------------------
The product brief asks for deliberate daily snapshots (Tue/Wed/Thu, Fri and Sat when there is
a game, Sun). W1 measured whether those are *historically reconstructable* and found they are
not, for two independent reasons that happen to agree:

**1. The ECR benchmark has exactly one vintage per week, and it is a Friday.** Across all 96
weekly boards in the mirror, the scrape dates are 82 Friday, 10 Thursday (every one of them in
2020), 2 Saturday, 1 Tuesday, 1 Wednesday. There is no Tuesday board and no Wednesday board to
compare against in any ordinary week, and later ECR may not be substituted to fill a missing
earlier one (the brief's rule, and D56's).

**2. The injury report cannot be rewound past its last edit.** nflverse's `injuries` file
carries one row per player-week --- verified 6,213 distinct `(season, week, gsis_id)` keys in
6,215 rows for 2024 --- whose `date_modified` is when that row was *last* touched. 4,818 of
2024's rows were last modified on a Friday. Filtering `date_modified <= Wednesday` therefore
does not reconstruct the Wednesday injury report; it deletes most of the report, because a row
that was updated again on Friday retains only its Friday state. A Wednesday snapshot built
this way would be systematically *healthier* than the real Wednesday, which is a bias, not a
leak, and is the more dangerous of the two because it flatters any system that uses injuries.

Both point at the same place: **Friday, after the Thursday night game, before the Sunday
slate**, is the one snapshot this repository can reconstruct honestly. W1 adopts it as the
single snapshot and records the daily cadence as a forward-only product capability.

Thursday-night players are excluded, and that is not optional
------------------------------------------------------------
A Friday cutoff sits *after* the week's Thursday game. W1 measured that the boards keep those
players on them: **81 of 96 weekly boards carry at least one player whose game had already
kicked off, 2,626 of 45,147 rows (5.8%)**. Their outcome is known at the cutoff, so leaving
them in would hand both the benchmark and Alpha a free, already-resolved row. They are removed
from the universe by `eligible_board_rows`, which is a property of the *cutoff*, not of any
system being measured, so every system is scored on the identical player set.

One canonical snapshot per week
-------------------------------
Four weeks in the mirror carry two scrape dates that both precede the same Sunday (2020 wk6,
2021 wk5, 2021 wk14, 2024 wk13). Using both would double-count those weeks and, worse, mix a
Tuesday vintage into a Friday series. `canonical_snapshots` keeps the **latest** snapshot
strictly before the week's first Sunday game, which is the Friday one in every case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb


@dataclass(frozen=True)
class WeeklySnapshot:
    """One ranking vintage: a board scraped on `scrape_date`, ranking `(season, week)`.

    `lead_days` is `first_sunday - scrape_date`, kept because it is the audit trail for the
    cutoff: a snapshot with an unusual lead is a snapshot whose information set differs from
    the rest of the series, and a comparison that silently mixes them is measuring two
    different questions."""

    season: int
    week: int
    scrape_date: date
    first_sunday: date
    lead_days: int


#: A snapshot is only a snapshot for the week whose Sunday slate it precedes by at most this
#: many days. Seven, so a board scraped the Monday after a Sunday attaches to the NEXT week
#: rather than reaching back over a completed one.
MAX_LEAD_DAYS = 7


def assign_snapshots(
    con: duckdb.DuckDBPyConnection,
    scrape_dates: list[date],
    *,
    seasons: tuple[int, ...] | None = None,
) -> list[WeeklySnapshot]:
    """Attach each scrape date to the `(season, week)` whose Sunday slate it precedes.

    The anchor is the week's **first Sunday game**, not its first game: the first game is
    often Thursday, and a Friday board sits after it. Anchoring on Thursday would assign a
    Friday board to the *following* week, which is off by one and silently compares a board to
    the wrong week's outcomes.

    `games` must be populated (`alpha-squad features build`). Only REG weeks are considered:
    there is no weekly ECR board for the postseason and week 18 has none either (verified: 0
    of 6 seasons)."""
    if not scrape_dates:
        return []
    # Parameter order follows the order the placeholders appear in the SQL text: the season
    # filter sits inside the `wk` CTE, which is written before `d`'s date array.
    season_filter = "AND season = ANY(?)" if seasons else ""
    params: list = [list(seasons)] if seasons else []
    params.append(sorted(set(scrape_dates)))
    rows = con.execute(
        f"""
        WITH wk AS (
            SELECT season, week, min(game_date) AS first_sunday
            FROM games
            WHERE game_type = 'REG' AND dayname(game_date) = 'Sunday' {season_filter}
            GROUP BY 1, 2
        ),
        d AS (SELECT UNNEST(?::DATE[]) AS scrape_date)
        SELECT d.scrape_date, wk.season, wk.week, wk.first_sunday,
               CAST(wk.first_sunday - d.scrape_date AS INTEGER) AS lead_days
        FROM d JOIN wk
          ON wk.first_sunday > d.scrape_date
         AND wk.first_sunday <= d.scrape_date + {MAX_LEAD_DAYS}
        QUALIFY row_number() OVER (PARTITION BY d.scrape_date ORDER BY wk.first_sunday) = 1
        ORDER BY wk.season, wk.week, d.scrape_date
        """,
        params,
    ).fetchall()
    return [WeeklySnapshot(int(r[1]), int(r[2]), r[0], r[3], int(r[4])) for r in rows]


def canonical_snapshots(snapshots: list[WeeklySnapshot]) -> list[WeeklySnapshot]:
    """One snapshot per `(season, week)`: the latest one before that week's Sunday slate.

    "Latest" is the smallest `lead_days`. That is the vintage with the most information, which
    is both the fairest benchmark to measure Alpha against and the one the other 92 weeks
    already are."""
    best: dict[tuple[int, int], WeeklySnapshot] = {}
    for snap in snapshots:
        key = (snap.season, snap.week)
        current = best.get(key)
        if current is None or snap.lead_days < current.lead_days:
            best[key] = snap
    return sorted(best.values(), key=lambda s: (s.season, s.week))


def teams_already_playing(
    con: duckdb.DuckDBPyConnection, snapshot: WeeklySnapshot
) -> frozenset[str]:
    """Teams whose `(season, week)` game kicked off strictly before the snapshot date.

    In practice this is the Thursday-night pair, and in the handful of Saturday-vintage weeks
    it is larger. Computed from `games.game_date` rather than assumed to be "the TNF teams",
    because W1 found two Saturday and one Wednesday vintage where that assumption is wrong.

    **Date, not kickoff time.** `games` stores `game_date` with no kickoff timestamp, so a
    same-day comparison is impossible and this uses a strict date inequality. That is the
    conservative direction: a game on the snapshot date itself is treated as NOT yet played,
    which cannot admit a completed game into the universe for a Friday board (no Friday games
    exist in any covered week) but would need revisiting for a Saturday or Sunday cutoff. See
    `docs/weekly/W1_FOUNDATION_AUDIT.md` on the missing kickoff-time column."""
    rows = con.execute(
        """
        SELECT DISTINCT t FROM games,
             UNNEST([home_team, away_team]) AS u(t)
        WHERE season = ? AND week = ? AND game_type = 'REG' AND game_date < ?
        """,
        [snapshot.season, snapshot.week, snapshot.scrape_date],
    ).fetchall()
    return frozenset(r[0] for r in rows if r[0])


def eligible_board_rows(
    board: list[tuple[str, str, str, float]],
    excluded_teams: frozenset[str],
) -> list[tuple[str, str, str, float]]:
    """Drop board rows for teams that already played. `board` rows are
    `(player_id, position, team, ecr_rank)`.

    Applied identically to every system under comparison --- ECR-alone, Alpha-without-ECR and
    Alpha-with-ECR --- because it defines the *question* (who could still be started), not any
    one system's answer."""
    return [row for row in board if row[2] not in excluded_teams]


def dense_rank(board: list[tuple[str, str, str, float]]) -> dict[str, int]:
    """Re-rank a filtered board 1..N by ascending ECR, ties broken by player id.

    Necessary because every board here is a *subset* of a published 1..N ranking once QBs
    and already-played teams are removed, and a subset's raw ECR values are no longer
    1..N. Comparing a system's dense rank against a benchmark's raw sparse rank would be
    comparing two different scales."""
    ordered = sorted(board, key=lambda r: (r[3], r[0]))
    return {row[0]: i for i, row in enumerate(ordered, start=1)}
