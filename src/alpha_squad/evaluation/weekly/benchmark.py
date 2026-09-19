"""The ECR-alone weekly benchmark, and the reference baselines that give it a scale (W2).

Measures **one system** — the published consensus — plus two deliberately trivial references.
No Alpha model is built, fitted or compared here; that is W3. The point of the phase is that a
later "Alpha beat ECR by X" is uninterpretable until X can be read against this benchmark's own
week-to-week variation.

Universe, in one place
----------------------
Every board this module produces goes through `board_for_week`, which applies the
pre-registered eligibility rules in the pre-registered order: drop players whose game already
kicked off at the cutoff, resolve identity, restrict positions, re-rank densely. Because all
three systems read the same function, they are scored on byte-identical player sets by
construction rather than by convention.

Two ECR artifacts, never pooled
-------------------------------
* **mirror** — `wsf/weekly-op` minus QBs, a *reconstruction*, full depth, **Friday** vintage.
* **FantasyPros API `FLX`** — the *real* published FLEX board, **Sunday ~12:59 ET** vintage,
  **top 10 only** (the configured key is `public_api_limited`). Used to validate the
  reconstruction, never merged into it: the vintages differ by two days.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS, ScoringFormat
from alpha_squad.evaluation.weekly.series import (
    WEEKLY_OVERALL_SUPERFLEX,
    WeeklyMarketSeries,
    positional_series,
)
from alpha_squad.evaluation.weekly.snapshots import WeeklySnapshot, teams_already_playing

#: FantasyPros' own abbreviations for three franchises, mirrored from
#: `features/kicking_defense.py::FANTASYPROS_TEAM_ALIASES` rather than imported, so the weekly
#: research package stays free of any import into production feature code. Verified in W1 to be
#: the only three of 32 that differ.
TEAM_ALIASES = {"JAC": "JAX", "LAR": "LA", "OAK": "LV"}

#: A cell with fewer than this many evaluable players is invalid and excluded (pre-registered
#: §5). It is what keeps a "top 25" off a board that never had 25 live players.
MIN_EVALUABLE = 10


@dataclass
class BoardRow:
    player_id: str
    position: str
    ecr: float
    realized: float | None


@dataclass
class Board:
    """One week's eligible, densely-ranked board with realized outcomes attached."""

    season: int
    week: int
    label: str
    rows: list[BoardRow]

    @property
    def evaluable(self) -> list[BoardRow]:
        """Ranked players who actually played. A ranked player with no realized row did not
        play; he is excluded from production-forecast metrics and counted by `availability`,
        never imputed to 0.0."""
        return [r for r in self.rows if r.realized is not None]

    @property
    def availability(self) -> float | None:
        return len(self.evaluable) / len(self.rows) if self.rows else None

    def ranks_and_points(self) -> tuple[list[float], list[float]]:
        """Dense 1..N predicted ranks over the evaluable set, with realized points.

        Re-ranked over the *evaluable* set, not the full board: a metric computed on sparse
        ranks (1, 4, 9, …) is not on the same scale as one computed on 1..N, and every
        reference baseline here produces dense ranks."""
        ordered = sorted(self.evaluable, key=lambda r: (r.ecr, r.player_id))
        return [float(i) for i in range(1, len(ordered) + 1)], [float(r.realized) for r in ordered]


def _ecr_rows(
    con: duckdb.DuckDBPyConnection,
    snapshot: WeeklySnapshot,
    series: WeeklyMarketSeries,
) -> list[tuple[str, str, str, float]]:
    """Raw `(player_id, position, team, ecr)` for one series on one snapshot date.

    Identity is resolved here: players through `fantasypros_id`, team defenses through the
    team-code alias path (a DST is not an NFL player and has no gsis id — D57)."""
    if series.team_coded:
        alias_sql = " ".join(f"WHEN e.team = '{k}' THEN '{v}'" for k, v in TEAM_ALIASES.items())
        rows = con.execute(
            f"""
            SELECT 'asq_dst_' || (CASE {alias_sql} ELSE e.team END) AS player_id,
                   'DST' AS position,
                   CASE {alias_sql} ELSE e.team END AS team,
                   e.ecr
            FROM ecr e
            WHERE e.ecr_type = ? AND e.page_type = ? AND e.fp_page LIKE '/nfl/%'
              AND CAST(e.scrape_date AS DATE) = ? AND e.ecr IS NOT NULL AND e.team IS NOT NULL
            """,
            [series.ecr_type, series.page_type, snapshot.scrape_date],
        ).fetchall()
        return [(r[0], r[1], r[2], float(r[3])) for r in rows]

    rows = con.execute(
        """
        WITH x AS (SELECT DISTINCT fantasypros_id, gsis_id FROM xwalk WHERE gsis_id IS NOT NULL)
        SELECT p.player_id, e.pos, e.team, e.ecr
        FROM ecr e
        JOIN x ON x.fantasypros_id = e.id
        JOIN players p ON p.gsis_id = x.gsis_id
        WHERE e.ecr_type = ? AND e.page_type = ? AND e.fp_page LIKE '/nfl/%'
          AND CAST(e.scrape_date AS DATE) = ? AND e.ecr IS NOT NULL
        """,
        [series.ecr_type, series.page_type, snapshot.scrape_date],
    ).fetchall()
    return [(r[0], r[1], r[2], float(r[3])) for r in rows]


def _realized(
    con: duckdb.DuckDBPyConnection, season: int, week: int, fmt: ScoringFormat
) -> dict[str, float]:
    rows = con.execute(
        f"""
        SELECT s.player_id, {fmt.sql_expr("s")}
        FROM player_week_stats s WHERE s.season = ? AND s.week = ?
        """,
        [season, week],
    ).fetchall()
    return {r[0]: float(r[1] or 0.0) for r in rows}


def board_for_week(
    con: duckdb.DuckDBPyConnection,
    snapshot: WeeklySnapshot,
    *,
    positions: tuple[str, ...],
    series: WeeklyMarketSeries,
    fmt: ScoringFormat,
    label: str,
) -> Board:
    """Build one week's eligible board, applying the pre-registered rules in order.

    The already-played exclusion uses **nflverse `games`**, never the board's own team column:
    the team a board reports is not reliable as a historical fact (the FantasyPros API returns
    *current* teams for historical weeks, and the mirror's team column is only as good as its
    scrape), and excluding the wrong teams would silently corrupt every week."""
    excluded_teams = teams_already_playing(con, snapshot)
    realized = _realized(con, snapshot.season, snapshot.week, fmt)

    # Which players actually played in a game that had already kicked off. Derived from the
    # schedule + the player's real week-w team, not from the board.
    already_played_ids = {
        r[0]
        for r in con.execute(
            """
            SELECT s.player_id FROM player_week_stats s
            WHERE s.season = ? AND s.week = ? AND s.team = ANY(?)
            """,
            [snapshot.season, snapshot.week, list(excluded_teams) or [""]],
        ).fetchall()
    }

    rows: list[BoardRow] = []
    seen: set[str] = set()
    for player_id, pos, _team, ecr in _ecr_rows(con, snapshot, series):
        if pos not in positions:
            continue
        if player_id in already_played_ids:
            continue
        if player_id in seen:
            continue
        seen.add(player_id)
        rows.append(BoardRow(player_id, pos, ecr, realized.get(player_id)))
    rows.sort(key=lambda r: (r.ecr, r.player_id))
    return Board(snapshot.season, snapshot.week, label, rows)


def flex_board(
    con: duckdb.DuckDBPyConnection, snapshot: WeeklySnapshot, fmt: ScoringFormat
) -> Board:
    """The FLEX benchmark: the superflex board with QBs removed (W1 §4.5).

    A *reconstruction*, because no 1-QB weekly cross-position board is mirrored. Its fidelity
    is measured against the real FantasyPros FLEX board in `w2_ecr_benchmark.py`."""
    return board_for_week(
        con,
        snapshot,
        positions=FLEX_POSITIONS,
        series=WEEKLY_OVERALL_SUPERFLEX,
        fmt=fmt,
        label="FLEX",
    )


def positional_board(
    con: duckdb.DuckDBPyConnection, snapshot: WeeklySnapshot, position: str, fmt: ScoringFormat
) -> Board:
    """One position's dedicated weekly board."""
    return board_for_week(
        con,
        snapshot,
        positions=(position,),
        series=positional_series(position),
        fmt=fmt,
        label=position,
    )


# ---------------------------------------------------------------------------------------
# Reference baselines (pre-registered §7.2). Neither is "Alpha"; both exist only to give the
# benchmark a scale, because a Spearman of 0.4 means nothing until you know what the obvious
# thing scores. They use strictly prior information and no fitting of any kind.
# ---------------------------------------------------------------------------------------


def _prior_ppg(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    fmt: ScoringFormat,
    *,
    mode: str,
) -> dict[str, float]:
    if mode == "season_to_date":
        where, params = "s.season = ? AND s.week < ?", [season, week]
    elif mode == "prior_season":
        where, params = "s.season = ?", [season - 1]
    else:  # pragma: no cover - guarded by caller
        raise ValueError(mode)
    rows = con.execute(
        f"""
        SELECT s.player_id, avg({fmt.sql_expr("s")}) FROM player_week_stats s
        WHERE {where} GROUP BY 1
        """,
        params,
    ).fetchall()
    return {r[0]: float(r[1] or 0.0) for r in rows}


def rerank_board(board: Board, key: dict[str, float]) -> Board:
    """Re-order an existing board's *same players* by an alternative signal.

    Holding the player universe fixed is the whole point: the reference baselines must answer
    "could a trivial ordering of THESE players have done as well", not "could a different
    player pool have". A player absent from `key` sorts last (he has no prior production),
    ties broken by `player_id` for determinism."""
    missing = min(key.values(), default=0.0) - 1.0
    rows = sorted(board.rows, key=lambda r: (-key.get(r.player_id, missing), r.player_id))
    return Board(
        board.season,
        board.week,
        board.label,
        [BoardRow(r.player_id, r.position, float(i), r.realized) for i, r in enumerate(rows, 1)],
    )


def baseline_boards(
    con: duckdb.DuckDBPyConnection, board: Board, fmt: ScoringFormat
) -> dict[str, Board]:
    """B0 (season-to-date PPG) and B1 (prior-season PPG) over the same universe."""
    return {
        "B0_season_to_date_ppg": rerank_board(
            board, _prior_ppg(con, board.season, board.week, fmt, mode="season_to_date")
        ),
        "B1_prior_season_ppg": rerank_board(
            board, _prior_ppg(con, board.season, board.week, fmt, mode="prior_season")
        ),
    }
