"""The central product-thesis test (docs/DECISIONS.md D54): does Alpha systematically
identify players whose market valuation is wrong, and does the *magnitude* of that
disagreement (plus confidence, plus evidence backing) carry real predictive information --
or is a "strong disagreement" no more informative than a mild one?

Reuses the exact same walk-forward market-implied-points methodology `market/edge.py`
already uses for its own backtest (`_market_implied_points_curve`, trained only on strictly
prior seasons) and the same `edge_snapshot` rows M8 already computed and persisted -- this
module only re-buckets already-real, already-scored signals into five ordered disagreement
tiers instead of the three (BUY/SELL/WATCH) `market/edge.py` already reports, and tests
whether `mean_outperformance_vs_market` actually increases from tier 1 to tier 5.

Sign convention (shared with `market/edge.py::evaluate_historical_edge`):
`mean_outperformance_vs_market = mean(actual_points - market_implied_points)`, unflipped.
A good BUY call is a *positive* number; a good SELL call is a *negative* number (the player
underperformed what the market expected, exactly as a sell signal predicted). `signed_edge`
below flips SELL's sign so BUY and SELL pool onto one "was Alpha's disagreement direction
right, and by how much" axis -- the metric this module's tier test is actually about.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.market.edge import (
    DEFAULT_ECR_TYPE,
    EDGE_MODEL_VERSION,
    _market_implied_points_curve,
)

AGREE = "1_agrees_with_market"
MILD_DISAGREE = "2_mildly_disagrees"
STRONG_DISAGREE = "3_strongly_disagrees"
HIGH_CONFIDENCE_DISAGREE = "4_disagrees_high_confidence"
EVIDENCE_BACKED_DISAGREE = "5_disagrees_evidence_backed_action"

TIER_ORDER = (
    AGREE,
    MILD_DISAGREE,
    STRONG_DISAGREE,
    HIGH_CONFIDENCE_DISAGREE,
    EVIDENCE_BACKED_DISAGREE,
)

# Thresholds are on |rank_edge| (real rank positions, e.g. 402 real overall players in 2025's
# 'rsf' edge_snapshot -- see docs/EVALUATION_LIMITATIONS.md for the exact real counts this was
# checked against). Chosen as round, pre-registered-looking cut points BEFORE this module was
# run against real outcomes (see docs/DECISIONS.md D54) -- not tuned after seeing the tier
# results, which would defeat the entire point of this test.
MILD_THRESHOLD = 6
STRONG_THRESHOLD = 16
HIGH_CONFIDENCE_THRESHOLD = 0.75


def _tier_for(action: str, rank_edge: int, confidence: float | None) -> str:
    abs_edge = abs(rank_edge)
    if action in ("BUY", "SELL"):
        # classify_action already gates BUY/SELL behind evidence support (D21) -- an action
        # of BUY or SELL in edge_snapshot IS, by construction, an evidence-backed disagreement.
        return EVIDENCE_BACKED_DISAGREE
    if (
        abs_edge >= STRONG_THRESHOLD
        and confidence is not None
        and confidence >= HIGH_CONFIDENCE_THRESHOLD
    ):
        return HIGH_CONFIDENCE_DISAGREE
    if abs_edge >= STRONG_THRESHOLD:
        return STRONG_DISAGREE
    if abs_edge >= MILD_THRESHOLD:
        return MILD_DISAGREE
    return AGREE


@dataclass
class TierRow:
    tier: str
    n: int
    mean_actual_points: float
    mean_market_implied_points: float | None
    mean_outperformance_vs_market: float | None
    mean_signed_edge: float | None


def build_market_inefficiency_tiers(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[TierRow]:
    by_tier: dict[str, list[tuple[float, float | None, str]]] = {}

    for season in range(season_start, season_end + 1):
        points_curve = _market_implied_points_curve(con, ecr_type, season)
        rows = con.execute(
            """
            SELECT e.action, e.rank_edge, e.confidence, e.market_rank, s.total_fantasy_points_ppr
            FROM edge_snapshot e
            JOIN player_season_stats s ON s.player_id = e.player_id AND s.season = e.season
            WHERE e.season = ? AND e.ecr_type = ? AND e.model_version = ?
            """,
            [season, ecr_type, EDGE_MODEL_VERSION],
        ).fetchall()
        for action, rank_edge, confidence, market_rank, actual_points in rows:
            market_points = (
                float(points_curve.predict([market_rank])[0]) if points_curve is not None else None
            )
            tier = _tier_for(action, rank_edge, confidence)
            by_tier.setdefault(tier, []).append((actual_points, market_points, action))

    results = []
    for tier in TIER_ORDER:
        pairs = by_tier.get(tier, [])
        n = len(pairs)
        if n == 0:
            results.append(TierRow(tier, 0, float("nan"), None, None, None))
            continue
        mean_actual = sum(a for a, _, _ in pairs) / n
        implied = [m for _, m, _ in pairs if m is not None]
        mean_implied = sum(implied) / len(implied) if implied else None
        outperf_pairs = [(a, m, act) for a, m, act in pairs if m is not None]
        mean_outperf = (
            sum(a - m for a, m, _ in outperf_pairs) / len(outperf_pairs) if outperf_pairs else None
        )
        signed = [(a - m) if act != "SELL" else (m - a) for a, m, act in outperf_pairs]
        mean_signed = sum(signed) / len(signed) if signed else None
        results.append(TierRow(tier, n, mean_actual, mean_implied, mean_outperf, mean_signed))
    return results


def write_market_inefficiency_report(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    season_start: int,
    season_end: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[TierRow]:
    tiers = build_market_inefficiency_tiers(con, season_start, season_end, ecr_type)
    # `strict=True` is wrong for a list zipped against its own one-shifted tail -- the two
    # sides are always exactly one element apart by construction, so strict mode raises
    # ValueError as soon as the shorter side is exhausted, which happens precisely when
    # every comparison is True (`all()` only short-circuits earlier if it hits a False
    # first). See docs/DECISIONS.md D54 -- found live via evaluation/dynasty_validation.py's
    # identical pattern crashing on a real, perfectly monotonic result.
    monotonic = all(
        (
            a.mean_signed_edge is None
            or b.mean_signed_edge is None
            or a.mean_signed_edge <= b.mean_signed_edge
        )
        for a, b in zip(tiers, tiers[1:], strict=False)
    )

    lines = [
        "# Market inefficiency: does disagreement magnitude carry predictive information?",
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. Seasons {season_start}-{season_end}, "
        f"ecr_type=`{ecr_type}`. Thresholds (`|rank_edge| >= {MILD_THRESHOLD}` mild, "
        f"`>= {STRONG_THRESHOLD}` strong, confidence `>= {HIGH_CONFIDENCE_THRESHOLD}` high-confidence) "
        "were fixed before this module was run against outcomes -- see the module docstring.",
        "",
        "`mean_signed_edge` flips SELL's sign so BUY and SELL pool onto one axis: positive means "
        "Alpha's disagreement direction was actually right, by that many points, on average.",
        "",
        "| Tier | n | Mean actual pts | Mean market-implied pts | Mean signed edge |",
        "|---|---|---|---|---|",
    ]
    for t in tiers:
        implied_s = (
            f"{t.mean_market_implied_points:.1f}"
            if t.mean_market_implied_points is not None
            else "-"
        )
        signed_s = f"{t.mean_signed_edge:+.1f}" if t.mean_signed_edge is not None else "-"
        lines.append(
            f"| {t.tier} | {t.n} | {t.mean_actual_points:.1f} | {implied_s} | {signed_s} |"
        )

    lines += [
        "",
        f"**Monotonic (tier 1 <= tier 2 <= ... <= tier 5 on mean signed edge): {monotonic}.**",
        "",
        "If this is not monotonic, disagreement magnitude/confidence/evidence-backing do not "
        "cleanly predict outcome quality in this data -- report that plainly rather than "
        "reordering tiers or adjusting thresholds to force an appearance of monotonicity.",
        "",
    ]
    path.write_text("\n".join(lines))
    return tiers


def tiers_to_json(tiers: list[TierRow]) -> str:
    return json.dumps([t.__dict__ for t in tiers], indent=2, sort_keys=True, default=str)
