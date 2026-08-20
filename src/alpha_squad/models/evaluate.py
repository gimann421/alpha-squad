"""Shared evaluation harness. Every baseline (M4) and later model (M5 established-player ML,
M7 rookie, M8 EDGE) reports through this so results are directly, queryably comparable —
ACCEPTANCE_CRITERIA.md requires every model be compared against baselines using the same
yardstick, not a bespoke one per model."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
from scipy import stats as scipy_stats

from alpha_squad.sources.base import utcnow

ALL_POSITIONS_SENTINEL = "ALL"


@dataclass
class EvaluationMetrics:
    model_name: str
    season: int
    position: str
    n: int
    mae: float
    rmse: float
    r2: float
    spearman: float
    top12_hit_rate: float | None
    top24_hit_rate: float | None
    tier_accuracy: float | None


def evaluate_predictions(
    model_name: str,
    season: int,
    position: str,
    predicted: dict[str, float],
    actual: dict[str, float],
) -> EvaluationMetrics:
    common = sorted(set(predicted) & set(actual))
    n = len(common)
    nan = float("nan")
    if n == 0:
        return EvaluationMetrics(
            model_name, season, position, 0, nan, nan, nan, nan, None, None, None
        )

    y_pred = np.array([predicted[p] for p in common])
    y_true = np.array([actual[p] for p in common])

    mae = float(np.mean(np.abs(y_pred - y_true)))
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = (1 - ss_res / ss_tot) if ss_tot > 0 else nan
    spearman = float(scipy_stats.spearmanr(y_pred, y_true).correlation) if n > 1 else nan

    def hit_rate(top_n: int) -> float | None:
        if n < top_n:
            return None
        actual_top = set(sorted(common, key=lambda p: -actual[p])[:top_n])
        pred_top = set(sorted(common, key=lambda p: -predicted[p])[:top_n])
        return len(actual_top & pred_top) / top_n

    def tiers(scores: dict[str, float]) -> dict[str, int]:
        ranked = sorted(common, key=lambda p: -scores[p])
        return {p: i // 12 for i, p in enumerate(ranked)}

    actual_tiers = tiers(actual)
    pred_tiers = tiers(predicted)
    tier_accuracy = sum(1 for p in common if actual_tiers[p] == pred_tiers[p]) / n

    return EvaluationMetrics(
        model_name,
        season,
        position,
        n,
        mae,
        rmse,
        r2,
        spearman,
        hit_rate(12),
        hit_rate(24),
        tier_accuracy,
    )


def actuals_for_season(
    con: duckdb.DuckDBPyConnection, season: int, position: str | None = None
) -> dict[str, float]:
    if position:
        rows = con.execute(
            "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats WHERE season = ? AND position = ?",
            [season, position],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats WHERE season = ?",
            [season],
        ).fetchall()
    return dict(rows)


def positions_for(con: duckdb.DuckDBPyConnection, player_ids: set[str]) -> dict[str, str]:
    if not player_ids:
        return {}
    rows = con.execute(
        "SELECT player_id, mode(position) FROM player_season_stats WHERE player_id = ANY(?) GROUP BY player_id",
        [list(player_ids)],
    ).fetchall()
    return dict(rows)


def record_evaluation(con: duckdb.DuckDBPyConnection, m: EvaluationMetrics) -> None:
    con.execute(
        """
        INSERT INTO evaluation_results
            (model_name, season, position, n, mae, rmse, r2, spearman, top12_hit_rate,
             top24_hit_rate, tier_accuracy, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (model_name, season, position) DO UPDATE SET
            n = excluded.n, mae = excluded.mae, rmse = excluded.rmse, r2 = excluded.r2,
            spearman = excluded.spearman, top12_hit_rate = excluded.top12_hit_rate,
            top24_hit_rate = excluded.top24_hit_rate, tier_accuracy = excluded.tier_accuracy,
            evaluated_at = excluded.evaluated_at
        """,
        [
            m.model_name,
            m.season,
            m.position,
            m.n,
            m.mae,
            m.rmse,
            m.r2,
            m.spearman,
            m.top12_hit_rate,
            m.top24_hit_rate,
            m.tier_accuracy,
            utcnow(),
        ],
    )


def evaluate_and_record(
    con: duckdb.DuckDBPyConnection, model_name: str, season: int, predicted: dict[str, float]
) -> list[EvaluationMetrics]:
    """Evaluates `predicted` against real season outcomes, both overall (position='ALL') and
    broken out per position (QB/RB/WR/TE), and persists every row to evaluation_results."""
    results = []

    actual_all = actuals_for_season(con, season)
    m_all = evaluate_predictions(model_name, season, ALL_POSITIONS_SENTINEL, predicted, actual_all)
    record_evaluation(con, m_all)
    results.append(m_all)

    positions = positions_for(con, set(predicted) & set(actual_all))
    for position in ("QB", "RB", "WR", "TE"):
        pos_players = {p for p, pos in positions.items() if pos == position}
        pred_pos = {p: v for p, v in predicted.items() if p in pos_players}
        actual_pos = {p: v for p, v in actual_all.items() if p in pos_players}
        m_pos = evaluate_predictions(model_name, season, position, pred_pos, actual_pos)
        record_evaluation(con, m_pos)
        results.append(m_pos)

    return results
