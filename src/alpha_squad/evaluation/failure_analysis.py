"""Mandatory failure analysis (docs/DECISIONS.md D54, directive section 18): concrete named
misses, not just aggregate win/loss statistics. Every row here is a real player, a real
season, a real predicted value, and a real outcome -- pulled directly from the same
`edge_snapshot`/`rookie_predictions`/`player_season_stats` tables the rest of this phase's
reports already validate against, not a separately curated "highlight reel" of failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from alpha_squad.market.edge import (
    DEFAULT_ECR_TYPE,
    EDGE_MODEL_VERSION,
    _market_implied_points_curve,
)


@dataclass
class EdgeMiss:
    player_id: str
    display_name: str | None
    season: int
    action: str
    actual_points: float
    market_implied_points: float | None
    miss_magnitude: float  # negative outperformance for BUY, positive for SELL -- always "bad"


def worst_edge_misses(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    top_n: int = 10,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[EdgeMiss]:
    """Real BUY calls that badly underperformed the market's own expectation, and real SELL
    calls that badly outperformed it -- the two ways an evidence-gated EDGE signal (D21's
    gating already requires more than a raw rank gap) can still be wrong."""
    misses: list[EdgeMiss] = []
    for season in range(season_start, season_end + 1):
        points_curve = _market_implied_points_curve(con, ecr_type, season)
        if points_curve is None:
            continue
        rows = con.execute(
            """
            SELECT e.player_id, p.display_name, e.action, e.market_rank, s.total_fantasy_points_ppr
            FROM edge_snapshot e
            JOIN player_season_stats s ON s.player_id = e.player_id AND s.season = e.season
            LEFT JOIN players p ON p.player_id = e.player_id
            WHERE e.season = ? AND e.ecr_type = ? AND e.model_version = ? AND e.action IN ('BUY', 'SELL')
            """,
            [season, ecr_type, EDGE_MODEL_VERSION],
        ).fetchall()
        for player_id, display_name, action, market_rank, actual_points in rows:
            market_points = float(points_curve.predict([market_rank])[0])
            outperf = actual_points - market_points
            miss_magnitude = -outperf if action == "BUY" else outperf
            misses.append(
                EdgeMiss(
                    player_id,
                    display_name,
                    season,
                    action,
                    actual_points,
                    market_points,
                    miss_magnitude,
                )
            )
    misses.sort(key=lambda m: -m.miss_magnitude)
    return misses[:top_n]


@dataclass
class RookieMiss:
    player_id: str
    display_name: str | None
    draft_class: int
    position: str
    predicted_points: float
    actual_points: float
    error: float


def worst_rookie_misses(
    con: duckdb.DuckDBPyConnection,
    model_version: str,
    draft_class_start: int,
    draft_class_end: int,
    top_n: int = 10,
) -> list[RookieMiss]:
    rows = con.execute(
        """
        SELECT rp.player_id, p.display_name, rp.draft_class, rp.position,
               rp.predicted_rookie_points, s.total_fantasy_points_ppr
        FROM rookie_predictions rp
        JOIN players p ON p.player_id = rp.player_id
        JOIN player_season_stats s ON s.player_id = rp.player_id AND s.season = p.rookie_season
        WHERE rp.model_version = ? AND rp.draft_class BETWEEN ? AND ?
          AND rp.predicted_rookie_points IS NOT NULL
        """,
        [model_version, draft_class_start, draft_class_end],
    ).fetchall()
    misses = [
        RookieMiss(pid, name, dc, pos, pred, actual, abs(pred - actual))
        for pid, name, dc, pos, pred, actual in rows
    ]
    misses.sort(key=lambda m: -m.error)
    return misses[:top_n]


def write_failure_analysis_report(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    edge_season_start: int,
    edge_season_end: int,
    rookie_model_version: str,
    rookie_class_start: int,
    rookie_class_end: int,
) -> dict:
    edge_misses = worst_edge_misses(con, edge_season_start, edge_season_end)
    rookie_misses = worst_rookie_misses(
        con, rookie_model_version, rookie_class_start, rookie_class_end
    )

    lines = [
        "# Failure analysis: where Alpha was wrong, concretely",
        "",
        "This is not an appendix -- CLAUDE.md and this phase's directive both require it. Every "
        "row below is a real player and a real outcome, not a curated sample.",
        "",
        "## Worst EDGE misses (real BUY/SELL calls that went the wrong way)",
        "",
        "| Player | Season | Action | Actual pts | Market-implied pts | Miss magnitude |",
        "|---|---|---|---|---|---|",
    ]
    for m in edge_misses:
        lines.append(
            f"| {m.display_name or m.player_id} | {m.season} | {m.action} | {m.actual_points:.1f} | "
            f"{m.market_implied_points:.1f} | {m.miss_magnitude:.1f} |"
        )
    lines += [
        "",
        "Likely cause categorization: an EDGE miss with real supporting evidence at the time "
        "(the gate requires it, D21) that still didn't pan out is most plausibly a genuine "
        "**model/uncertainty** miss (the underlying projection or its confidence was wrong) or "
        "an **insufficient-information** miss (a real injury/role change after the signal was "
        "built that no snapshot could have captured) -- distinguishing the two for any specific "
        "row above requires reading that player's real evidence_events timeline "
        "(`GET /players/{id}/detail`), not guessed here.",
        "",
        "## Worst rookie misses",
        "",
        "| Player | Class | Position | Predicted pts | Actual pts | Error |",
        "|---|---|---|---|---|---|",
    ]
    for m in rookie_misses:
        lines.append(
            f"| {m.display_name or m.player_id} | {m.draft_class} | {m.position} | "
            f"{m.predicted_points:.1f} | {m.actual_points:.1f} | {m.error:.1f} |"
        )
    lines += [
        "",
        "Likely cause categorization: rookie misses cluster into **insufficient-information** "
        "(draft capital/college production genuinely cannot see an in-season role change, e.g. "
        "a starter's injury handing a rookie a starting job) and **model** (real signal was "
        "available -- landing spot, draft capital -- but the model under/overweighted it). "
        "D39's measured rejection of college-production features suggests the second category "
        "is not fixed by adding more of the same kind of preseason signal.",
        "",
        "## Categorization key (directive section 18)",
        "",
        "- **data**: a real input was missing, stale, or wrong at prediction time.",
        "- **identity**: a canonical-ID mismatch attributed a signal to the wrong player.",
        "- **model**: the underlying projection itself was wrong given the inputs it had.",
        "- **uncertainty**: the point prediction was reasonable but confidence was miscalibrated.",
        "- **market**: the market consensus itself was wrong, and Alpha inherited that error "
        "(e.g. `market_ecr` baselines above use the exact same market signal EDGE compares "
        "against).",
        "- **evidence**: real evidence existed but was misweighted or arrived too late.",
        "- **league context**: correct for the player, wrong for what this specific roster needed.",
        "- **decision logic**: the recommendation's arithmetic/gating itself was flawed.",
        "- **insufficient information**: nothing available at prediction time could have caught it.",
        "",
    ]
    path.write_text("\n".join(lines))
    return {
        "edge_misses": [m.__dict__ for m in edge_misses],
        "rookie_misses": [m.__dict__ for m in rookie_misses],
    }
