"""Split-conformal prediction intervals for established-player season-level projections
(PRODUCT_SPEC.md §Uncertainty: "conformal prediction or another calibrated interval method").

Uses *signed* calibration-residual quantiles, not a symmetric absolute-residual margin, so
intervals can be properly asymmetric — fantasy scoring is right-skewed (a breakout's upside
is larger than a bust's downside, since points are bounded near zero but not above).

Three-way, strictly time-ordered split, never overlapping:
    proper-train (fit the point model) -> calibration (season the model never trained on,
    used only to measure its residuals) -> target (the season being projected).
This is what makes the resulting intervals a genuine out-of-sample uncertainty estimate
rather than the model grading its own homework."""

from __future__ import annotations

import numpy as np

QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)
QUANTILE_LABELS = {0.10: "p10", 0.25: "p25", 0.50: "median", 0.75: "p75", 0.90: "p90"}


def fit_conformal_quantiles(residuals: np.ndarray) -> dict[float, float]:
    """residuals = y_calib - point_predictions_on_calib (signed, not absolute)."""
    return {q: float(np.quantile(residuals, q)) for q in QUANTILE_LEVELS}


def apply_quantiles(
    point_prediction: float, residual_quantiles: dict[float, float]
) -> dict[str, float]:
    return {QUANTILE_LABELS[q]: point_prediction + residual_quantiles[q] for q in QUANTILE_LEVELS}


def confidence_from_interval_width(point_prediction: float, p10: float, p90: float) -> float:
    """A simple, documented heuristic (not a probability): a narrower [p10,p90] interval
    relative to the point prediction's magnitude means the model is more confident. Clamped
    to [0, 1]; deliberately not claimed as calibrated on its own — calibration_diagnostics
    is what actually measures whether the *intervals* are trustworthy."""
    width = max(p90 - p10, 0.0)
    scale = max(abs(point_prediction), 1.0)
    return float(np.clip(1.0 - (width / (2 * scale)), 0.0, 1.0))


def monte_carlo_top_n_probabilities(
    point_predictions: dict[str, float],
    residuals: np.ndarray,
    *,
    n_draws: int = 2000,
    rng: np.random.Generator | None = None,
) -> dict[str, dict[str, float]]:
    """For each player, resample from the empirical calibration-residual distribution
    `n_draws` times, add to their point prediction, and across draws compute how often they
    rank in the top-12/top-24 among the *other players in this same call* (i.e. their
    position peers for that season). Returns {player_id: {"top12_prob": ..., "top24_prob": ...}}.
    """
    rng = rng or np.random.default_rng(42)
    player_ids = list(point_predictions.keys())
    if len(player_ids) < 2:
        return {pid: {"top12_prob": None, "top24_prob": None} for pid in player_ids}

    base = np.array([point_predictions[pid] for pid in player_ids])
    noise = rng.choice(residuals, size=(n_draws, len(player_ids)), replace=True)
    simulated = base[None, :] + noise  # shape (n_draws, n_players)

    ranks = (-simulated).argsort(axis=1).argsort(axis=1)  # 0 = best, within each draw
    top12 = (ranks < 12).mean(axis=0)
    top24 = (ranks < 24).mean(axis=0)

    return {
        pid: {"top12_prob": float(top12[i]), "top24_prob": float(top24[i])}
        for i, pid in enumerate(player_ids)
    }
