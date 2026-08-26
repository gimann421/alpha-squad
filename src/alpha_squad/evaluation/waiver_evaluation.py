"""Waiver/FAAB evaluation (docs/DECISIONS.md D54) -- and, up front, what this module honestly
cannot answer.

The directive's fullest version of this question (bid efficiency, opportunity cost,
competing-bid likelihood, hit rate against *actual* historical add/drop transactions) needs a
real historical log of what was rostered/available/bid on, week by week, in real leagues over
real past seasons. That data does not exist in this environment: the only real per-team roster
history reachable is two *current* live Sleeper leagues (see league/roster_import.py), and
`weekly_projection_snapshot` (Alpha's own weekly predictions) only covers season 2025 (D46's
first real run) -- one season is not a walk-forward waiver backtest.

What real data DOES support, and what this module actually builds: a **preseason waiver-tier
value-discovery proxy**. Using the season-level model's real walk-forward predictions
(2020-2025, six real seasons -- far more data than the one season the weekly pipeline has run
on) and real preseason market consensus, define "waiver tier" as players a standard league
would not have rostered off a startup draft, and ask whether Alpha's preseason ranking of
*that specific pool* finds real subsequent value better than the two most natural fallbacks:
doing nothing (the pool's own average) and a naive prior-year-points read of the same pool.
This is a real, checkable question with real data behind it -- it is deliberately NOT presented
as a simulation of in-season FAAB bidding, because that would overclaim what is actually being
tested here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.market.edge import DEFAULT_ECR_TYPE, _preseason_overall_market
from alpha_squad.models.baselines.simple import previous_year_baseline

# A standard 10-12 team single/2QB redraft startup draft rosters roughly 150-200 players
# overall; 150 is a conservative (i.e. *generous* toward calling more players "already
# rostered", making the waiver-tier pool harder for Alpha to find value in, not easier) real
# cutoff. Fixed here, before this module was run against outcomes -- not tuned afterward.
ROSTERED_ECR_THRESHOLD = 150
TOP_K = 20


@dataclass
class WaiverTierSeasonResult:
    season: int
    pool_size: int
    pool_mean_points: float
    pool_top24_hit_rate: float
    alpha_top_k_mean_points: float
    alpha_top_k_top24_hit_rate: float
    prior_year_top_k_mean_points: float
    prior_year_top_k_top24_hit_rate: float


def _actual_points(
    con: duckdb.DuckDBPyConnection, season: int, player_ids: list[str]
) -> dict[str, float]:
    if not player_ids:
        return {}
    rows = con.execute(
        "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
        "WHERE season = ? AND player_id = ANY(?)",
        [season, player_ids],
    ).fetchall()
    found = dict(rows)
    return {p: found.get(p, 0.0) for p in player_ids}


def _positions_for(
    con: duckdb.DuckDBPyConnection, season: int, player_ids: list[str]
) -> dict[str, str]:
    if not player_ids:
        return {}
    rows = con.execute(
        "SELECT player_id, position FROM player_season_stats WHERE season = ? AND player_id = ANY(?)",
        [season, player_ids],
    ).fetchall()
    return dict(rows)


def _top24_hit_rate(
    picks: list[str],
    actual: dict[str, float],
    positions: dict[str, str],
    full_season_pool: list[str],
) -> float:
    """Fraction of `picks` that finished top-24 at their real position among every player in
    `full_season_pool` who has a real season outcome -- the same top-24 convention
    `models/evaluate.py` uses elsewhere, applied within this waiver-tier universe."""
    if not picks:
        return float("nan")
    by_pos: dict[str, list[str]] = {}
    for p in full_season_pool:
        pos = positions.get(p)
        if pos:
            by_pos.setdefault(pos, []).append(p)
    top24_ids: set[str] = set()
    for ids in by_pos.values():
        ranked = sorted(ids, key=lambda p: -actual.get(p, 0.0))
        top24_ids.update(ranked[:24])
    hits = sum(1 for p in picks if p in top24_ids)
    return hits / len(picks)


def build_waiver_tier_evaluation(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[WaiverTierSeasonResult]:
    results = []
    for season in range(season_start, season_end + 1):
        projections, positions = load_season_projections(con, season)
        if not projections:
            continue
        market = _preseason_overall_market(con, ecr_type, season)
        prior_year = previous_year_baseline(con, season)

        waiver_pool = [
            p for p in projections if p not in market or market[p][1] > ROSTERED_ECR_THRESHOLD
        ]
        if len(waiver_pool) < TOP_K:
            continue

        actual = _actual_points(con, season, waiver_pool)
        real_positions = _positions_for(con, season, waiver_pool)

        alpha_top_k = sorted(waiver_pool, key=lambda p: -projections[p])[:TOP_K]
        prior_top_k = sorted(waiver_pool, key=lambda p: -prior_year.get(p, float("-inf")))[:TOP_K]

        pool_mean = sum(actual.values()) / len(actual) if actual else float("nan")
        pool_top24 = _top24_hit_rate(waiver_pool, actual, real_positions, waiver_pool)

        results.append(
            WaiverTierSeasonResult(
                season=season,
                pool_size=len(waiver_pool),
                pool_mean_points=pool_mean,
                pool_top24_hit_rate=pool_top24,
                alpha_top_k_mean_points=sum(actual.get(p, 0.0) for p in alpha_top_k) / TOP_K,
                alpha_top_k_top24_hit_rate=_top24_hit_rate(
                    alpha_top_k, actual, real_positions, waiver_pool
                ),
                prior_year_top_k_mean_points=sum(actual.get(p, 0.0) for p in prior_top_k) / TOP_K,
                prior_year_top_k_top24_hit_rate=_top24_hit_rate(
                    prior_top_k, actual, real_positions, waiver_pool
                ),
            )
        )
    return results


def write_waiver_evaluation_report(
    con: duckdb.DuckDBPyConnection, path: Path, season_start: int, season_end: int
) -> list[WaiverTierSeasonResult]:
    results = build_waiver_tier_evaluation(con, season_start, season_end)

    lines = [
        "# Waiver-tier value discovery (preseason proxy, not a FAAB-bidding simulation)",
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. See this module's docstring for "
        "why a real historical FAAB-bidding backtest is not feasible in this environment, and "
        "what this proxy actually tests instead.",
        "",
        f"Waiver tier = real preseason-evaluable players with overall ECR rank > "
        f"{ROSTERED_ECR_THRESHOLD} or no preseason consensus rank at all (deep sleepers). "
        f"Top-{TOP_K} compares Alpha's preseason ranking of that pool against a naive "
        "prior-year-points ranking of the identical pool, and against the pool's own average "
        "(the 'did nothing' baseline).",
        "",
        "| Season | Pool n | Pool mean pts | Alpha top-K mean pts | Alpha top-K top24 hit | Prior-yr top-K mean pts | Prior-yr top-K top24 hit |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.season} | {r.pool_size} | {r.pool_mean_points:.1f} | "
            f"{r.alpha_top_k_mean_points:.1f} | {r.alpha_top_k_top24_hit_rate:.0%} | "
            f"{r.prior_year_top_k_mean_points:.1f} | {r.prior_year_top_k_top24_hit_rate:.0%} |"
        )

    if results:
        n = len(results)
        mean_alpha = sum(r.alpha_top_k_mean_points for r in results) / n
        mean_prior = sum(r.prior_year_top_k_mean_points for r in results) / n
        mean_pool = sum(r.pool_mean_points for r in results) / n
        lines += [
            "",
            f"**Pooled across {n} seasons:** Alpha top-K mean {mean_alpha:.1f} pts vs. "
            f"prior-year top-K mean {mean_prior:.1f} pts vs. pool average {mean_pool:.1f} pts.",
        ]

    lines += [
        "",
        "## What this does NOT show",
        "",
        "This says nothing about FAAB bid sizing/efficiency, opportunity cost, or "
        "competing-bid likelihood -- those require real historical add/drop/bid transaction "
        "logs this environment does not have (see docs/EVALUATION_LIMITATIONS.md). Treat this "
        "as evidence about whether Alpha's preseason model, applied to the specific pool of "
        "players a standard league wouldn't roster, finds real subsequent value -- a necessary "
        "but not sufficient condition for the waiver/FAAB recommendation feature being useful.",
        "",
    ]
    path.write_text("\n".join(lines))
    return results
