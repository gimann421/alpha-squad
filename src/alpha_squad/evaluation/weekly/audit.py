"""The W1 foundation audit, as executable measurements (`docs/weekly/W1_FOUNDATION_AUDIT.md`).

Every empirical claim in the W1 report is produced by a function here, so the report can be
re-checked against a refreshed mirror rather than believed. D92 is the reason this exists as a
committed module instead of a notebook: that phase's finding had to be retracted because the
runner that produced it was never committed, and the numbers could not be reproduced.

Input contract
--------------
Each function takes a DuckDB connection on which two views are registered:

    ecr        the raw DynastyProcess `fp_ecr_history` mirror (columns `fp_page`, `page_type`,
               `ecr_type`, `scrape_date`, `id`, `pos`, `team`, `ecr`)
    xwalk      the DynastyProcess `db_playerids` crosswalk (`fantasypros_id`, `gsis_id`)

plus, for the schedule-dependent measurements, this project's own `games` table. The runner
`scripts/research/w1_weekly_foundation_audit.py` wires those views from the snapshots
`alpha-squad sources ingest` already records, so the audit reads the same immutable files the
rest of the pipeline reads and introduces no second data path.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import duckdb

from alpha_squad.evaluation.weekly.series import (
    ALL_WEEKLY_SERIES,
    FIRST_MODERN_WEEKLY_DATE,
    WEEKLY_OVERALL_SUPERFLEX,
    WeeklyMarketSeries,
)
from alpha_squad.evaluation.weekly.snapshots import (
    WeeklySnapshot,
    assign_snapshots,
    canonical_snapshots,
)

#: Modern `/nfl/rankings/*.php` pages only. The pre-2020-10-16 rows use different labels for
#: the same pages and are excluded by series definition, not by this filter -- this just keeps
#: the SQL from having to repeat the reasoning.
_MODERN = "fp_page LIKE '/nfl/%'"


@dataclass
class SeriesCoverage:
    """What one weekly series actually contains."""

    series: str
    fp_page: str
    rows: int
    scrape_dates: int
    first_date: str
    last_date: str


@dataclass
class WeekCoverage:
    """Which REG weeks have a canonical weekly board, and which do not."""

    covered: list[tuple[int, int]] = field(default_factory=list)
    uncovered: list[tuple[int, int]] = field(default_factory=list)
    snapshots: list[WeeklySnapshot] = field(default_factory=list)

    @property
    def n_covered(self) -> int:
        return len(self.covered)


def series_coverage(con: duckdb.DuckDBPyConnection) -> list[SeriesCoverage]:
    """Row/date coverage for each weekly series. Establishes that the weekly boards exist at
    all, and over what span."""
    out: list[SeriesCoverage] = []
    for s in ALL_WEEKLY_SERIES:
        row = con.execute(
            f"""
            SELECT count(*), count(DISTINCT scrape_date),
                   min(CAST(scrape_date AS VARCHAR)), max(CAST(scrape_date AS VARCHAR))
            FROM ecr
            WHERE ecr_type = ? AND page_type = ? AND {_MODERN}
            """,
            [s.ecr_type, s.page_type],
        ).fetchone()
        out.append(SeriesCoverage(str(s), s.fp_page, int(row[0]), int(row[1]), row[2], row[3]))
    return out


def scrape_date_weekday_mix(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Day-of-week histogram of every weekly scrape date.

    This is the measurement that decides the snapshot cadence question. If the mirror held
    Tuesday *and* Wednesday *and* Friday vintages, the brief's daily cadence would be
    historically testable; it does not."""
    rows = con.execute(
        f"""
        SELECT dayname(CAST(scrape_date AS DATE)) AS dow, count(DISTINCT scrape_date)
        FROM ecr
        WHERE page_type IN (SELECT UNNEST(?)) AND {_MODERN}
        GROUP BY 1 ORDER BY 2 DESC
        """,
        [[s.page_type for s in ALL_WEEKLY_SERIES]],
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def weekly_scrape_dates(con: duckdb.DuckDBPyConnection) -> list:
    """Every distinct scrape date on which any weekly board was captured."""
    return [
        r[0]
        for r in con.execute(
            f"""
            SELECT DISTINCT CAST(scrape_date AS DATE) AS d
            FROM ecr
            WHERE page_type IN (SELECT UNNEST(?)) AND {_MODERN} AND scrape_date >= ?
            ORDER BY 1
            """,
            [[s.page_type for s in ALL_WEEKLY_SERIES], FIRST_MODERN_WEEKLY_DATE],
        ).fetchall()
    ]


def week_coverage(con: duckdb.DuckDBPyConnection, seasons: tuple[int, ...]) -> WeekCoverage:
    """Which `(season, week)` pairs have a canonical weekly board.

    Needs this project's `games` table, so it reports honestly rather than inferring the NFL
    calendar from the boards themselves."""
    snaps = canonical_snapshots(assign_snapshots(con, weekly_scrape_dates(con), seasons=seasons))
    covered = {(s.season, s.week) for s in snaps}
    all_weeks = {
        (int(r[0]), int(r[1]))
        for r in con.execute(
            "SELECT DISTINCT season, week FROM games WHERE game_type = 'REG' AND season = ANY(?)",
            [list(seasons)],
        ).fetchall()
    }
    return WeekCoverage(
        covered=sorted(covered),
        uncovered=sorted(all_weeks - covered),
        snapshots=snaps,
    )


def already_played_contamination(
    con: duckdb.DuckDBPyConnection, snapshots: list[WeeklySnapshot]
) -> dict[str, float]:
    """How much of the benchmark board is already-resolved at the cutoff.

    A Friday vintage sits after the Thursday night game. Any row for a team that already
    played is an outcome the ranking cannot affect and the evaluation must not credit."""
    total = stale = weeks_with_stale = 0
    for snap in snapshots:
        row = con.execute(
            f"""
            SELECT count(*),
                   count(*) FILTER (
                       WHERE e.team IN (
                           SELECT t FROM games, UNNEST([home_team, away_team]) AS u(t)
                           WHERE season = ? AND week = ? AND game_type = 'REG' AND game_date < ?
                       ))
            FROM ecr e
            WHERE e.ecr_type = ? AND e.page_type = ? AND {_MODERN}
              AND CAST(e.scrape_date AS DATE) = ?
            """,
            [
                snap.season,
                snap.week,
                snap.scrape_date,
                WEEKLY_OVERALL_SUPERFLEX.ecr_type,
                WEEKLY_OVERALL_SUPERFLEX.page_type,
                snap.scrape_date,
            ],
        ).fetchone()
        total += int(row[0])
        stale += int(row[1])
        weeks_with_stale += 1 if int(row[1]) else 0
    return {
        "weeks": float(len(snapshots)),
        "weeks_with_already_played_rows": float(weeks_with_stale),
        "board_rows": float(total),
        "already_played_rows": float(stale),
        "already_played_pct": (100.0 * stale / total) if total else 0.0,
    }


def identity_join_rate(
    con: duckdb.DuckDBPyConnection, series: WeeklyMarketSeries, *, top_n: int = 24
) -> dict[str, float]:
    """Share of a weekly board that resolves to an nflverse `gsis_id`.

    A board row that cannot be joined to a player cannot be scored against realized points, so
    this is a hard feasibility gate, not a nice-to-have. Reported overall and restricted to the
    top `top_n`, because a benchmark that loses rows only at rank 300 is a very different
    problem from one that loses them at rank 5."""
    row = con.execute(
        f"""
        WITH b AS (
            SELECT id, ecr FROM ecr
            WHERE ecr_type = ? AND page_type = ? AND {_MODERN} AND ecr IS NOT NULL
        ),
        x AS (SELECT DISTINCT fantasypros_id, gsis_id FROM xwalk WHERE gsis_id IS NOT NULL)
        SELECT count(*), count(x.gsis_id),
               count(*) FILTER (WHERE b.ecr <= ?),
               count(x.gsis_id) FILTER (WHERE b.ecr <= ?)
        FROM b LEFT JOIN x ON x.fantasypros_id = b.id
        """,
        [series.ecr_type, series.page_type, top_n, top_n],
    ).fetchone()
    n, matched, n_top, matched_top = (int(v) for v in row)
    return {
        "rows": float(n),
        "matched": float(matched),
        "pct": (100.0 * matched / n) if n else 0.0,
        f"top{top_n}_rows": float(n_top),
        f"top{top_n}_matched": float(matched_top),
        f"top{top_n}_pct": (100.0 * matched_top / n_top) if n_top else 0.0,
    }


def flex_reconstruction_consistency(
    con: duckdb.DuckDBPyConnection, position: str, *, min_n: int = 10
) -> dict[str, float]:
    """Spearman between the superflex overall board's induced within-position order and the
    dedicated positional board, per board date.

    This is the evidence for --- and the stated limit of --- reconstructing a 1-QB FLEX
    benchmark by dropping QBs from the superflex board. High agreement shows the two boards
    are one product's two views. It does NOT show the superflex board's cross-position
    calibration matches a 1-QB board's, because no 1-QB weekly board exists to check."""
    from alpha_squad.evaluation.weekly.series import positional_series

    pos_series = positional_series(position)
    rows = con.execute(
        f"""
        SELECT op.scrape_date, op.ecr, pp.ecr
        FROM (SELECT scrape_date, id, ecr FROM ecr
              WHERE ecr_type = ? AND page_type = ? AND {_MODERN} AND pos = ?) op
        JOIN (SELECT scrape_date, id, ecr FROM ecr
              WHERE ecr_type = ? AND page_type = ? AND {_MODERN}) pp
          USING (scrape_date, id)
        """,
        [
            WEEKLY_OVERALL_SUPERFLEX.ecr_type,
            WEEKLY_OVERALL_SUPERFLEX.page_type,
            position,
            pos_series.ecr_type,
            pos_series.page_type,
        ],
    ).fetchall()
    by_date: dict[object, list[tuple[float, float]]] = {}
    for d, a, b in rows:
        if a is not None and b is not None:
            by_date.setdefault(d, []).append((float(a), float(b)))
    rhos: list[float] = []
    ns: list[int] = []
    for pairs in by_date.values():
        if len(pairs) < min_n:
            continue
        try:
            rhos.append(
                statistics.correlation(
                    [p[0] for p in pairs], [p[1] for p in pairs], method="ranked"
                )
            )
        except statistics.StatisticsError:  # pragma: no cover - degenerate constant board
            continue
        ns.append(len(pairs))
    if not rhos:
        return {"weeks": 0.0}
    rhos.sort()
    return {
        "weeks": float(len(rhos)),
        "median_n": float(statistics.median(ns)),
        "median_rho": statistics.median(rhos),
        "p10_rho": rhos[len(rhos) // 10],
        "min_rho": rhos[0],
    }


def scoring_format_availability(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Whether a Half-PPR or standard-scoring page exists in the mirror at any date.

    The weekly RB/WR/TE pages are the PPR pages. If this returns zero for `half`, a Half-PPR
    ECR benchmark does not exist historically and no amount of care in the harness can
    manufacture one."""
    out: dict[str, int] = {}
    for label, pattern in (
        ("half", "%half%"),
        ("standard", "%standard%"),
        ("non_ppr", "%non-ppr%"),
        ("flex", "%flex%"),
    ):
        out[label] = int(
            con.execute(
                "SELECT count(DISTINCT fp_page) FROM ecr WHERE lower(fp_page) LIKE ?", [pattern]
            ).fetchone()[0]
        )
    return out
