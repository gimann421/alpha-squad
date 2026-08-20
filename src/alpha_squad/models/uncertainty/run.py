"""Walk-forward uncertainty pipeline. For each target season S and position: train a point
model on seasons strictly before S-1, calibrate conformal residual quantiles on season S-1
(held out from training, never S itself), then produce p10-p90 + top-12/24 probabilities for
season S. Finally measures whether those intervals were actually well-calibrated by checking
empirical coverage against S's real outcomes — out-of-sample, since S was never used to fit
or calibrate anything."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import duckdb
from catboost import CatBoostRegressor

from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)
from alpha_squad.models.uncertainty.conformal import (
    apply_quantiles,
    confidence_from_interval_width,
    fit_conformal_quantiles,
    monte_carlo_top_n_probabilities,
)
from alpha_squad.sources.base import utcnow

MODEL_VERSION = "uncertainty_catboost_v1"
FEATURE_VERSION = "established_season_level_ml_v1"
POSITIONS = ("QB", "RB", "WR", "TE")
MIN_TRAIN_ROWS = 30
MIN_CALIB_ROWS = 15


def _prediction_id(player_id: str, season: int, model_version: str) -> str:
    digest = hashlib.md5(f"{player_id}:{season}:{model_version}".encode()).hexdigest()[:16]
    return f"pred_{digest}"


@dataclass
class UncertaintyRunReport:
    predictions_written: int = 0
    calibration_rows: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _store_prediction(
    con: duckdb.DuckDBPyConnection,
    player_id: str,
    season: int,
    position: str,
    point_pred: float,
    quantiles: dict[str, float],
    mc: dict[str, float],
    calib_season: int,
    now,
) -> None:
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, p10, p25, median, p75, p90, top12_prob, top24_prob,
             confidence, calibration_season, predicted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (player_id, season, model_version) DO UPDATE SET
            position = excluded.position, feature_version = excluded.feature_version,
            point_prediction = excluded.point_prediction, p10 = excluded.p10, p25 = excluded.p25,
            median = excluded.median, p75 = excluded.p75, p90 = excluded.p90,
            top12_prob = excluded.top12_prob, top24_prob = excluded.top24_prob,
            confidence = excluded.confidence, calibration_season = excluded.calibration_season,
            predicted_at = excluded.predicted_at
        """,
        [
            _prediction_id(player_id, season, MODEL_VERSION),
            player_id,
            season,
            position,
            MODEL_VERSION,
            FEATURE_VERSION,
            point_pred,
            quantiles["p10"],
            quantiles["p25"],
            quantiles["median"],
            quantiles["p75"],
            quantiles["p90"],
            mc["top12_prob"],
            mc["top24_prob"],
            confidence_from_interval_width(point_pred, quantiles["p10"], quantiles["p90"]),
            calib_season,
            now,
        ],
    )


def _record_calibration(
    con: duckdb.DuckDBPyConnection,
    season: int,
    position: str,
    predictions: dict[str, dict[str, float]],
    actual: dict[str, float],
) -> dict:
    common = sorted(set(predictions) & set(actual))
    n = len(common)
    if n == 0:
        return {"season": season, "position": position, "n": 0}

    in_10_90 = sum(1 for p in common if predictions[p]["p10"] <= actual[p] <= predictions[p]["p90"])
    in_25_75 = sum(1 for p in common if predictions[p]["p25"] <= actual[p] <= predictions[p]["p75"])
    widths = [predictions[p]["p90"] - predictions[p]["p10"] for p in common]

    coverage_10_90 = in_10_90 / n
    coverage_25_75 = in_25_75 / n
    mean_width = sum(widths) / n
    now = utcnow()

    con.execute(
        """
        INSERT INTO calibration_diagnostics
            (model_version, season, position, n, coverage_10_90, coverage_25_75,
             mean_interval_width_10_90, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (model_version, season, position) DO UPDATE SET
            n = excluded.n, coverage_10_90 = excluded.coverage_10_90,
            coverage_25_75 = excluded.coverage_25_75,
            mean_interval_width_10_90 = excluded.mean_interval_width_10_90,
            evaluated_at = excluded.evaluated_at
        """,
        [MODEL_VERSION, season, position, n, coverage_10_90, coverage_25_75, mean_width, now],
    )
    return {
        "season": season,
        "position": position,
        "n": n,
        "coverage_10_90": coverage_10_90,
        "coverage_25_75": coverage_25_75,
        "mean_interval_width_10_90": mean_width,
    }


def run_uncertainty(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int, min_train_season: int = 2015
) -> UncertaintyRunReport:
    report = UncertaintyRunReport()

    for target_season in range(season_start, season_end + 1):
        calib_season = target_season - 1
        for position in POSITIONS:
            all_data = load_season_level_data(con, position, min_train_season, target_season)
            proper_train = all_data[all_data["target_season"] < calib_season]
            calib = all_data[all_data["target_season"] == calib_season]
            target = all_data[all_data["target_season"] == target_season]

            if len(proper_train) < MIN_TRAIN_ROWS or len(calib) < MIN_CALIB_ROWS or target.empty:
                report.skipped.append(
                    f"{position}/{target_season}: train={len(proper_train)} calib={len(calib)} target={len(target)}"
                )
                continue

            model = CatBoostRegressor(
                iterations=150,
                depth=3,
                learning_rate=0.08,
                loss_function="MAE",
                verbose=False,
                random_seed=42,
            )
            model.fit(proper_train[FEATURES].to_numpy(), proper_train[TARGET_COLUMN].to_numpy())

            calib_preds = model.predict(calib[FEATURES].to_numpy())
            residuals = calib[TARGET_COLUMN].to_numpy() - calib_preds
            quantile_offsets = fit_conformal_quantiles(residuals)

            target_preds = model.predict(target[FEATURES].to_numpy())
            point_predictions = dict(
                zip(target["player_id"].tolist(), (float(p) for p in target_preds), strict=True)
            )

            mc_probs = monte_carlo_top_n_probabilities(point_predictions, residuals)

            now = utcnow()
            full_predictions: dict[str, dict[str, float]] = {}
            for player_id, point_pred in point_predictions.items():
                quantiles = apply_quantiles(point_pred, quantile_offsets)
                full_predictions[player_id] = quantiles
                _store_prediction(
                    con,
                    player_id,
                    target_season,
                    position,
                    point_pred,
                    quantiles,
                    mc_probs[player_id],
                    calib_season,
                    now,
                )
                report.predictions_written += 1

            actual_target = dict(
                zip(target["player_id"].tolist(), target[TARGET_COLUMN].tolist(), strict=True)
            )
            calib_row = _record_calibration(
                con, target_season, position, full_predictions, actual_target
            )
            report.calibration_rows.append(calib_row)

    return report
