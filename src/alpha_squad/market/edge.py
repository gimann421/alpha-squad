"""Model-vs-market EDGE (AGENT_CONTRACTS.md's Edge contract; ACCEPTANCE_CRITERIA.md's
Market/EDGE section). Compares the M6 uncertainty model's single-season point/probability
predictions against the market's redraft-superflex ECR ('rsf' — an overall, cross-position
rank that values QBs the way the target league's 2QB format actually does; see D21), both
horizon-matched to a single season. A dynasty-horizon EDGE (using 'dsf' + dynasty_values'
value_2qb, blended with age curves) is left to M10's trade logic — mixing a single-season
point model against a multi-year dynasty value would conflate two different things the model
was never asked to predict.

Hard rule (ACCEPTANCE_CRITERIA.md: "a raw ranking discrepancy cannot alone produce a strong
EDGE"), encoded in `classify_action`: BUY/SELL requires rank edge AND points edge to agree in
direction AND both clear a materiality threshold AND model confidence to clear a floor AND
real structured evidence (M9, D23) to not actively contradict the action. `evidence_score` is
computed from real `evidence_events`, not a placeholder; it is genuinely neutral (0.5) for
this preseason-anchored EDGE in practice, since evidence detectors only ever produce
in-season events and this EDGE compares preseason market snapshots -- reported as-is, not
faked into looking more evidence-backed than the timing genuinely allows (D23)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
from sklearn.isotonic import IsotonicRegression

from alpha_squad.evidence.prior_update import evidence_score_for_action
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.sources.base import utcnow

EDGE_MODEL_VERSION = "edge_v1"
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_ECR_TYPE = "rsf"

RANK_EDGE_THRESHOLD = 15
POINTS_EDGE_THRESHOLD = 15.0
CONFIDENCE_THRESHOLD = 0.5
NEAR_ZERO_RANK = 5
NEAR_ZERO_POINTS = 5.0
# D23: real evidence_score is 0.5 (neutral) when no structured evidence exists yet, not a
# penalty -- only evidence that actively contradicts the candidate action vetoes it.
EVIDENCE_CONTRADICTION_THRESHOLD = 0.35

MIN_CURVE_TRAINING_ROWS = 10


@dataclass
class EdgeRecord:
    player_id: str
    season: int
    position: str
    ecr_type: str
    model_version: str
    model_rank: int
    market_rank: int
    rank_edge: int
    projected_points_edge: float | None
    probability_edge: float | None
    evidence_score: float
    confidence: float | None
    action: str
    reasons: list[str]
    prediction_id: str | None


@dataclass
class EdgeBuildReport:
    edges_written: int = 0
    seasons: list[int] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _edge_id(player_id: str, season: int, ecr_type: str, model_version: str) -> str:
    digest = hashlib.md5(f"{player_id}:{season}:{ecr_type}:{model_version}".encode()).hexdigest()[
        :16
    ]
    return f"edge_{digest}"


def _preseason_overall_market(
    con: duckdb.DuckDBPyConnection, ecr_type: str, season: int
) -> dict[str, tuple[str, float]]:
    """Latest Jul/Aug snapshot per player for `ecr_type` in `season` -> (position, ecr_rank).
    Preseason-only, mirroring models/baselines/market_implied.py's leakage-safe pattern: an
    EDGE "as of" a season never reads market movement that happened later in that season."""
    rows = con.execute(
        """
        SELECT player_id, position, ecr_rank FROM (
            SELECT player_id, position, ecr_rank,
                   row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)
        ) WHERE rn = 1
        """,
        [ecr_type, season],
    ).fetchall()
    return {player_id: (position, ecr_rank) for player_id, position, ecr_rank in rows}


def _historical_overall_rank_points(
    con: duckdb.DuckDBPyConnection, ecr_type: str, before_season: int
) -> list[tuple[float, float]]:
    return con.execute(
        """
        WITH preseason AS (
            SELECT player_id, year(scrape_date) AS season, ecr_rank,
                   row_number() OVER (
                       PARTITION BY player_id, year(scrape_date) ORDER BY scrape_date DESC
                   ) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND month(scrape_date) IN (7, 8)
        )
        SELECT p.ecr_rank, s.total_fantasy_points_ppr
        FROM preseason p
        JOIN player_season_stats s ON s.player_id = p.player_id AND s.season = p.season
        WHERE p.rn = 1 AND p.season < ?
        """,
        [ecr_type, before_season],
    ).fetchall()


def _market_implied_points_curve(
    con: duckdb.DuckDBPyConnection, ecr_type: str, before_season: int
) -> IsotonicRegression | None:
    """Overall (cross-position) rank -> actual PPR points, walk-forward. Pooled across
    positions rather than per-position (unlike M4's baseline): 'rsf' is itself an overall
    rank where a QB at rank 3 can legitimately outscore a WR at rank 3, so the curve has to
    be fit on the same pooled scale it was ranked on."""
    training = _historical_overall_rank_points(con, ecr_type, before_season)
    if len(training) < MIN_CURVE_TRAINING_ROWS:
        return None
    ranks = [r for r, _ in training]
    points = [p for _, p in training]
    curve = IsotonicRegression(increasing=False, out_of_bounds="clip")
    curve.fit(ranks, points)
    return curve


def _historical_position_rank_top24(
    con: duckdb.DuckDBPyConnection, ecr_type: str, position: str, before_season: int
) -> list[tuple[float, float]]:
    """Within-position rank (re-derived from the overall 'rsf' rank restricted to one
    position/season, since the raw series carries no explicit position rank) vs. a real
    top-24-at-position finish label, for seasons strictly before `before_season`."""
    return con.execute(
        """
        WITH preseason AS (
            SELECT player_id, year(scrape_date) AS season, ecr_rank,
                   row_number() OVER (
                       PARTITION BY player_id, year(scrape_date) ORDER BY scrape_date DESC
                   ) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND month(scrape_date) IN (7, 8) AND position = ?
        ),
        deduped AS (SELECT player_id, season, ecr_rank FROM preseason WHERE rn = 1),
        pos_ranked AS (
            SELECT player_id, season,
                   row_number() OVER (PARTITION BY season ORDER BY ecr_rank ASC) AS position_rank
            FROM deduped
        ),
        outcomes AS (
            SELECT player_id, season,
                   row_number() OVER (
                       PARTITION BY season ORDER BY total_fantasy_points_ppr DESC
                   ) AS finish_rank
            FROM player_season_stats WHERE position = ?
        )
        SELECT r.position_rank, CASE WHEN o.finish_rank <= 24 THEN 1.0 ELSE 0.0 END
        FROM pos_ranked r
        JOIN outcomes o ON o.player_id = r.player_id AND o.season = r.season
        WHERE r.season < ?
        """,
        [ecr_type, position, position, before_season],
    ).fetchall()


def _market_implied_probability_curve(
    con: duckdb.DuckDBPyConnection, ecr_type: str, position: str, before_season: int
) -> IsotonicRegression | None:
    training = _historical_position_rank_top24(con, ecr_type, position, before_season)
    if len(training) < MIN_CURVE_TRAINING_ROWS:
        return None
    ranks = [r for r, _ in training]
    labels = [label for _, label in training]
    curve = IsotonicRegression(increasing=False, y_min=0.0, y_max=1.0, out_of_bounds="clip")
    curve.fit(ranks, labels)
    return curve


def classify_action(
    rank_edge: int,
    points_edge: float | None,
    confidence: float | None,
    evidence_score: float = 0.5,
) -> tuple[str, list[str]]:
    """The hard gating rule: a raw rank discrepancy alone can never produce BUY/SELL.
    A same-direction, threshold-clearing points edge, a confidence floor, AND real evidence
    that does not actively contradict the action are all required. evidence_score defaults
    to neutral (0.5, "no evidence either way") so callers that don't pass it (or players with
    no recorded evidence) are unaffected -- only evidence_score below
    EVIDENCE_CONTRADICTION_THRESHOLD (real, contradicting evidence) vetoes an otherwise-valid
    BUY/SELL. See tests/unit/test_edge.py for the literal regression test of this rule."""
    reasons: list[str] = [
        f"rank edge {rank_edge:+d} (market rank minus model rank; positive = model more bullish than market)"
    ]

    if points_edge is None:
        reasons.append(
            "no market-implied points curve available for this season (insufficient walk-forward "
            "training history) -- a rank edge alone is never sufficient to act"
        )
        return "WATCH", reasons

    reasons.append(f"projected points edge {points_edge:+.1f} PPR vs. market-implied points")

    if abs(rank_edge) <= NEAR_ZERO_RANK and abs(points_edge) <= NEAR_ZERO_POINTS:
        reasons.append("model and market are in close agreement -- no meaningful edge")
        return "HOLD", reasons

    same_direction = (rank_edge > 0 and points_edge > 0) or (rank_edge < 0 and points_edge < 0)
    if not same_direction:
        reasons.append(
            "rank edge and points edge disagree in direction -- a raw ranking discrepancy "
            "cannot alone produce a strong EDGE (ACCEPTANCE_CRITERIA.md)"
        )
        return "WATCH", reasons

    if abs(rank_edge) < RANK_EDGE_THRESHOLD or abs(points_edge) < POINTS_EDGE_THRESHOLD:
        reasons.append(
            f"edge below the action threshold (requires rank>={RANK_EDGE_THRESHOLD} AND "
            f"points>={POINTS_EDGE_THRESHOLD}, both in the same direction)"
        )
        return "WATCH", reasons

    if confidence is None or confidence < CONFIDENCE_THRESHOLD:
        reasons.append(
            f"model confidence ({confidence}) below the {CONFIDENCE_THRESHOLD} floor required to act"
        )
        return "WATCH", reasons

    if evidence_score < EVIDENCE_CONTRADICTION_THRESHOLD:
        reasons.append(
            f"real structured evidence contradicts this action (evidence_score={evidence_score:.2f} "
            f"< {EVIDENCE_CONTRADICTION_THRESHOLD}) -- vetoed to WATCH"
        )
        return "WATCH", reasons

    action = "BUY" if points_edge > 0 else "SELL"
    reasons.append(
        f"{action}: rank and points edges agree, clear thresholds, confidence sufficient, "
        f"evidence does not contradict (evidence_score={evidence_score:.2f})"
    )
    return action, reasons


def compute_edges_for_season(
    con: duckdb.DuckDBPyConnection, target_season: int, ecr_type: str = DEFAULT_ECR_TYPE
) -> list[EdgeRecord]:
    market = _preseason_overall_market(con, ecr_type, target_season)
    if not market:
        return []

    model_rows = con.execute(
        """
        SELECT prediction_id, player_id, position, point_prediction, top24_prob, confidence
        FROM uncertainty_predictions
        WHERE model_version = ? AND season = ?
        """,
        [UNCERTAINTY_MODEL_VERSION, target_season],
    ).fetchall()
    if not model_rows:
        return []

    model_by_player = {
        player_id: {
            "prediction_id": prediction_id,
            "position": position,
            "point_prediction": point_prediction,
            "top24_prob": top24_prob,
            "confidence": confidence,
        }
        for prediction_id, player_id, position, point_prediction, top24_prob, confidence in model_rows
    }

    common = sorted(set(market) & set(model_by_player))
    if not common:
        return []

    # The model's own full ranking that season (not narrowed to the market-covered subset).
    model_overall_order = sorted(
        model_by_player, key=lambda p: -model_by_player[p]["point_prediction"]
    )
    model_overall_rank = {p: i + 1 for i, p in enumerate(model_overall_order)}

    # The market's own within-position rank, from the full preseason market set for this
    # ecr_type (not narrowed to the model-covered subset) -- used for probability_edge.
    by_position: dict[str, list[str]] = {}
    for player_id, (position, _rank) in market.items():
        by_position.setdefault(position, []).append(player_id)
    market_position_rank: dict[str, int] = {}
    for players in by_position.values():
        for i, player_id in enumerate(sorted(players, key=lambda p: market[p][1])):
            market_position_rank[player_id] = i + 1

    points_curve = _market_implied_points_curve(con, ecr_type, target_season)
    prob_curve_by_position = {
        position: _market_implied_probability_curve(con, ecr_type, position, target_season)
        for position in SKILL_POSITIONS
    }

    records: list[EdgeRecord] = []
    for player_id in common:
        position, raw_market_rank = market[player_id]
        market_rank = int(round(raw_market_rank))
        model = model_by_player[player_id]
        model_rank = model_overall_rank[player_id]
        rank_edge = market_rank - model_rank

        points_edge = None
        if points_curve is not None:
            market_points = float(points_curve.predict([raw_market_rank])[0])
            points_edge = model["point_prediction"] - market_points

        prob_edge = None
        prob_curve = prob_curve_by_position.get(position)
        if (
            prob_curve is not None
            and player_id in market_position_rank
            and model["top24_prob"] is not None
        ):
            market_prob = float(prob_curve.predict([market_position_rank[player_id]])[0])
            prob_edge = model["top24_prob"] - market_prob

        tentative_sign = (
            0 if points_edge is None else (1 if points_edge > 0 else (-1 if points_edge < 0 else 0))
        )
        evidence_score = evidence_score_for_action(con, player_id, target_season, tentative_sign)

        action, reasons = classify_action(
            rank_edge, points_edge, model["confidence"], evidence_score
        )
        reasons.append(f"evidence_score {evidence_score:.2f} (0.5 = no recorded evidence yet)")

        records.append(
            EdgeRecord(
                player_id=player_id,
                season=target_season,
                position=position,
                ecr_type=ecr_type,
                model_version=EDGE_MODEL_VERSION,
                model_rank=model_rank,
                market_rank=market_rank,
                rank_edge=rank_edge,
                projected_points_edge=points_edge,
                probability_edge=prob_edge,
                evidence_score=evidence_score,
                confidence=model["confidence"],
                action=action,
                reasons=reasons,
                prediction_id=model["prediction_id"],
            )
        )
    return records


def store_edges(con: duckdb.DuckDBPyConnection, records: list[EdgeRecord]) -> int:
    now = utcnow()
    for r in records:
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, projected_points_edge, probability_edge,
                 evidence_score, confidence, action, reasons_json, prediction_id, built_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (player_id, season, ecr_type, model_version) DO UPDATE SET
                position = excluded.position, model_rank = excluded.model_rank,
                market_rank = excluded.market_rank, rank_edge = excluded.rank_edge,
                projected_points_edge = excluded.projected_points_edge,
                probability_edge = excluded.probability_edge,
                evidence_score = excluded.evidence_score, confidence = excluded.confidence,
                action = excluded.action, reasons_json = excluded.reasons_json,
                prediction_id = excluded.prediction_id, built_at = excluded.built_at
            """,
            [
                _edge_id(r.player_id, r.season, r.ecr_type, r.model_version),
                r.player_id,
                r.season,
                r.position,
                r.ecr_type,
                r.model_version,
                r.model_rank,
                r.market_rank,
                r.rank_edge,
                r.projected_points_edge,
                r.probability_edge,
                r.evidence_score,
                r.confidence,
                r.action,
                json.dumps(r.reasons),
                r.prediction_id,
                now,
            ],
        )
    return len(records)


def run_edge_build(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> EdgeBuildReport:
    report = EdgeBuildReport()
    for season in range(season_start, season_end + 1):
        records = compute_edges_for_season(con, season, ecr_type)
        if not records:
            report.skipped.append(
                f"{season}: no overlapping model+market data for ecr_type={ecr_type}"
            )
            continue
        report.edges_written += store_edges(con, records)
        report.seasons.append(season)
    return report


def evaluate_historical_edge(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
) -> list[dict]:
    """For each (season, action) cohort already written to edge_snapshot, compares real
    outcomes to what the market implied at prediction time -- the empirical test of whether
    BUY signals actually beat market expectation (ACCEPTANCE_CRITERIA.md: 'historical EDGE
    performance is evaluated'). Published either way; a negative result is not suppressed."""
    results: list[dict] = []
    now = utcnow()
    for season in range(season_start, season_end + 1):
        points_curve = _market_implied_points_curve(con, ecr_type, season)
        rows = con.execute(
            """
            SELECT e.action, e.market_rank, s.total_fantasy_points_ppr
            FROM edge_snapshot e
            JOIN player_season_stats s ON s.player_id = e.player_id AND s.season = e.season
            WHERE e.season = ? AND e.ecr_type = ? AND e.model_version = ?
            """,
            [season, ecr_type, EDGE_MODEL_VERSION],
        ).fetchall()
        if not rows:
            continue

        by_action: dict[str, list[tuple[float, float | None]]] = {}
        for action, market_rank, actual_points in rows:
            market_points = (
                float(points_curve.predict([market_rank])[0]) if points_curve is not None else None
            )
            by_action.setdefault(action, []).append((actual_points, market_points))

        for action, pairs in by_action.items():
            n = len(pairs)
            mean_actual = sum(a for a, _ in pairs) / n
            implied = [m for _, m in pairs if m is not None]
            mean_implied = sum(implied) / len(implied) if implied else None
            mean_outperf = (
                sum(a - m for a, m in pairs if m is not None) / len(implied) if implied else None
            )
            con.execute(
                """
                INSERT INTO edge_validation_results
                    (model_version, ecr_type, season, action, n, mean_actual_points,
                     mean_market_implied_points, mean_outperformance_vs_market, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (model_version, ecr_type, season, action) DO UPDATE SET
                    n = excluded.n, mean_actual_points = excluded.mean_actual_points,
                    mean_market_implied_points = excluded.mean_market_implied_points,
                    mean_outperformance_vs_market = excluded.mean_outperformance_vs_market,
                    evaluated_at = excluded.evaluated_at
                """,
                [
                    EDGE_MODEL_VERSION,
                    ecr_type,
                    season,
                    action,
                    n,
                    mean_actual,
                    mean_implied,
                    mean_outperf,
                    now,
                ],
            )
            results.append(
                {
                    "season": season,
                    "action": action,
                    "n": n,
                    "mean_actual_points": mean_actual,
                    "mean_market_implied_points": mean_implied,
                    "mean_outperformance_vs_market": mean_outperf,
                }
            )
    return results


def _fmt(x) -> str:
    if x is None:
        return "-"
    try:
        if x != x:  # NaN
            return "-"
    except TypeError:
        return str(x)
    return f"{x:.2f}" if isinstance(x, float) else str(x)


def write_edge_validation_report(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Publishes edge_validation_results either way, per CLAUDE.md's no-hidden-failure rule:
    if BUY cohorts do not actually beat market expectation, that is reported, not buried."""
    rows = con.execute(
        """
        SELECT season, action, n, mean_actual_points, mean_market_implied_points,
               mean_outperformance_vs_market
        FROM edge_validation_results
        ORDER BY season, action
        """
    ).fetchall()

    headers = [
        "season",
        "action",
        "n",
        "mean_actual_pts",
        "mean_market_implied_pts",
        "mean_outperformance",
    ]
    lines = [
        "# Historical EDGE Validation",
        "",
        "Did each action cohort (BUY/SELL/HOLD/WATCH) actually beat what the market implied "
        "at prediction time? `mean_outperformance` = mean(actual points - market-implied "
        "points) within the cohort; positive means the cohort beat the market. Every EDGE was "
        "computed walk-forward (market-implied-points curve trained only on seasons strictly "
        "before the target season) so this is a genuine out-of-sample check.",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(v) for v in row) + " |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
