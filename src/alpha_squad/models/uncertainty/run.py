"""Walk-forward uncertainty pipeline. For each target season S and position: fit a point model
and a conformal interval model, then produce p10-p90 + top-12/24 probabilities for season S.
Finally measures whether those intervals were actually well-calibrated by checking empirical
coverage against S's real outcomes — out-of-sample, since S was never used to fit or calibrate
anything.

Two models, not one (D78)
-------------------------
The interval model trains on target seasons strictly before S-1 and its residuals are measured
on S-1, so those residuals are genuinely out-of-sample — that is the property split-conformal
needs and it is unchanged from D67.

The POINT model additionally trains on S-1 itself. D67's single-model version spent the most
recent completed season entirely on calibration and never let the point model see it, which in
a drifting positional environment discards the most relevant season available. D78 measured
that as a real cost (walk-forward MAE 41.88 → 40.73 over 2022-2025, better at every position
and in every season, paired p=0.026) and the pre-registered gates in
`evaluation/projection_specification.py` selected this arm.

The two fits are related in the safe direction: the interval model is trained on strictly less
data than the point model, so its residual spread is an over-estimate of the point model's, and
the resulting intervals are conservative rather than optimistic. `calibration_diagnostics`
measures the real coverage either way and is the check that this stayed true.

`SPEC_LEGACY` reproduces D67's exact single-model behaviour, writing under
`LEGACY_MODEL_VERSION`, so every pre-D78 backtest (D68's residual universe in particular)
stays reproducible rather than being silently redefined."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
    load_season_level_projection_data,
)
from alpha_squad.models.persistence import (
    load_calibration_residuals,
    load_regressor,
    register_artifact,
    save_model,
)
from alpha_squad.models.uncertainty.conformal import (
    apply_quantiles,
    confidence_from_interval_width,
    fit_conformal_quantiles,
    monte_carlo_top_n_probabilities,
)
from alpha_squad.sources.base import utcnow

#: D78 specification: the point model also trains on the calibration season.
SPEC_D78 = "d78"
#: D67 specification: one model, trained strictly before the calibration season.
SPEC_LEGACY = "legacy"

MODEL_VERSION = "uncertainty_catboost_v2"
#: What every pre-D78 run wrote. Kept so D67/D68-era rows stay addressable and reproducible.
LEGACY_MODEL_VERSION = "uncertainty_catboost_v1"
FEATURE_VERSION = "established_season_level_ml_v1"
POSITIONS = ("QB", "RB", "WR", "TE")
MIN_TRAIN_ROWS = 30
MIN_CALIB_ROWS = 15
ARTIFACT_MODEL_NAME = "uncertainty_catboost"


def model_version_for(specification: str) -> str:
    """Predictions from two different specifications must never share a key. `model_version` is
    what `load_season_projections` filters on, so giving each specification its own value is
    what stops a legacy backtest and a D78 projection from being read as one series."""
    if specification == SPEC_D78:
        return MODEL_VERSION
    if specification == SPEC_LEGACY:
        return LEGACY_MODEL_VERSION
    raise ValueError(f"unknown specification {specification!r}")


def _new_model() -> CatBoostRegressor:
    """M6's estimator. Identical for the point and interval fits -- D78 varies the training
    rows only, never the estimator, the features or the loss."""
    return CatBoostRegressor(
        iterations=150,
        depth=3,
        learning_rate=0.08,
        loss_function="MAE",
        verbose=False,
        random_seed=42,
    )


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
    model_version: str = MODEL_VERSION,
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
            _prediction_id(player_id, season, model_version),
            player_id,
            season,
            position,
            model_version,
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
    model_version: str = MODEL_VERSION,
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
        [model_version, season, position, n, coverage_10_90, coverage_25_75, mean_width, now],
    )
    return {
        "season": season,
        "position": position,
        "n": n,
        "coverage_10_90": coverage_10_90,
        "coverage_25_75": coverage_25_75,
        "mean_interval_width_10_90": mean_width,
    }


def _fit_point_and_interval_models(
    proper_train: pd.DataFrame, calib: pd.DataFrame, specification: str
) -> tuple[CatBoostRegressor, np.ndarray]:
    """Returns (point model, out-of-sample calibration residuals).

    `proper_train` is strictly before the calibration season; `calib` is the calibration season.
    Under `SPEC_LEGACY` there is one model and the point model IS the interval model (D67).
    Under `SPEC_D78` the interval model still trains on `proper_train` alone -- so the residuals
    it produces on `calib` remain genuinely out-of-sample -- while the point model additionally
    trains on `calib`."""
    interval_model = _new_model()
    interval_model.fit(proper_train[FEATURES].to_numpy(), proper_train[TARGET_COLUMN].to_numpy())
    residuals = calib[TARGET_COLUMN].to_numpy() - interval_model.predict(calib[FEATURES].to_numpy())

    if specification == SPEC_LEGACY:
        return interval_model, residuals

    point_train = pd.concat([proper_train, calib], ignore_index=True)
    point_model = _new_model()
    point_model.fit(point_train[FEATURES].to_numpy(), point_train[TARGET_COLUMN].to_numpy())
    return point_model, residuals


def run_uncertainty(
    con: duckdb.DuckDBPyConnection,
    season_start: int,
    season_end: int,
    min_train_season: int = 2015,
    *,
    persist: bool = False,
    specification: str = SPEC_D78,
) -> UncertaintyRunReport:
    """`persist=True` saves the fitted model (and the calibration residuals needed to
    reconstruct quantiles/probabilities) for every (position, target_season) processed, keyed
    by (model_name, position, model_version) -- so the LAST target_season in the requested
    range naturally ends up the one on disk when this is called in season order (upsert
    semantics, same as `model_registry` already used before persistence existed). That is the
    servable production artifact `score_with_persisted_model` reads: whichever season this was
    most recently run through. Walk-forward *evaluation* callers (comparing many historical
    seasons against each other) should leave this False -- there is no reason to write dozens
    of intermediate artifacts to disk just to compute historical metrics.

    `specification` selects D78's two-model split (default) or D67's single-model behaviour;
    see the module docstring. The two write under different `model_version` values, so a
    legacy backtest and a D78 run can coexist in `uncertainty_predictions` without either
    silently redefining the other."""
    report = UncertaintyRunReport()
    model_version = model_version_for(specification)

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

            model, residuals = _fit_point_and_interval_models(proper_train, calib, specification)
            quantile_offsets = fit_conformal_quantiles(residuals)

            if persist:
                path = save_model(model, ARTIFACT_MODEL_NAME, position, model_version)
                register_artifact(
                    con,
                    ARTIFACT_MODEL_NAME,
                    position,
                    model_version,
                    FEATURE_VERSION,
                    min_train_season,
                    target_season,
                    path,
                    notes=f"servable uncertainty model, trained through {calib_season}, "
                    f"scoring {target_season}",
                    calibration_residuals=residuals,
                )

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
                    model_version,
                )
                report.predictions_written += 1

            actual_target = dict(
                zip(target["player_id"].tolist(), target[TARGET_COLUMN].tolist(), strict=True)
            )
            calib_row = _record_calibration(
                con, target_season, position, full_predictions, actual_target, model_version
            )
            report.calibration_rows.append(calib_row)

    return report


@dataclass
class UncertaintyProjectionReport:
    target_season: int = 0
    predictions_written: int = 0
    trained_through: int = 0
    skipped: list[str] = field(default_factory=list)


def project_uncertainty_season(
    con: duckdb.DuckDBPyConnection,
    target_season: int,
    min_train_season: int = 2015,
    *,
    persist: bool = True,
    specification: str = SPEC_D78,
) -> UncertaintyProjectionReport:
    """Score a season that has not been played yet -- the established-player counterpart to
    `project_rookie_class` (docs/DECISIONS.md D40).

    `run_uncertainty` is a backtest: for each target season in its range it trains, calibrates,
    predicts, AND checks the predictions against that season's real outcomes
    (`_record_calibration`). That last step is why `load_season_level_data`'s target join is an
    INNER JOIN requiring `target_season`'s own `player_season_stats` to already exist -- correct
    for walk-forward evaluation, but it structurally excludes a genuinely future season (an
    empty `target` DataFrame, silently skipped) -- the same shape of gap D25 found for rookies.

    This trains and calibrates exactly the way `run_uncertainty` does -- the interval model
    strictly before `calib_season = target_season - 1` and, under `SPEC_D78`, the point model
    through `calib_season` itself (for a real future `target_season` that is always a season
    which has already been played) -- then scores `load_season_level_projection_data`'s
    LEFT-JOIN feature rows for `target_season` instead of requiring its own actuals. It
    deliberately writes no `calibration_diagnostics` row: there is no real outcome yet to check
    coverage against, and reporting one would be fabricating a metric (same reasoning as
    `project_rookie_class`)."""
    calib_season = target_season - 1
    report = UncertaintyProjectionReport(target_season=target_season, trained_through=calib_season)
    model_version = model_version_for(specification)

    for position in POSITIONS:
        train_calib = load_season_level_data(con, position, min_train_season, calib_season)
        proper_train = train_calib[train_calib["target_season"] < calib_season]
        calib = train_calib[train_calib["target_season"] == calib_season]
        target = load_season_level_projection_data(con, position, target_season)

        if len(proper_train) < MIN_TRAIN_ROWS or len(calib) < MIN_CALIB_ROWS or target.empty:
            report.skipped.append(
                f"{position}/{target_season}: train={len(proper_train)} calib={len(calib)} "
                f"target={len(target)}"
            )
            continue

        model, residuals = _fit_point_and_interval_models(proper_train, calib, specification)
        quantile_offsets = fit_conformal_quantiles(residuals)

        if persist:
            path = save_model(model, ARTIFACT_MODEL_NAME, position, model_version)
            register_artifact(
                con,
                ARTIFACT_MODEL_NAME,
                position,
                model_version,
                FEATURE_VERSION,
                min_train_season,
                target_season,
                path,
                notes=f"servable uncertainty model, trained through {calib_season}, "
                f"projecting unplayed season {target_season}",
                calibration_residuals=residuals,
            )

        target_preds = model.predict(target[FEATURES].to_numpy())
        point_predictions = dict(
            zip(target["player_id"].tolist(), (float(p) for p in target_preds), strict=True)
        )
        mc_probs = monte_carlo_top_n_probabilities(point_predictions, residuals)

        now = utcnow()
        for player_id, point_pred in point_predictions.items():
            quantiles = apply_quantiles(point_pred, quantile_offsets)
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
                model_version,
            )
            report.predictions_written += 1

    return report


def score_with_persisted_model(
    con: duckdb.DuckDBPyConnection,
    position: str,
    season: int,
    feature_rows: pd.DataFrame,
    *,
    model_version: str = MODEL_VERSION,
    calibration_season: int | None = None,
    store: bool = True,
) -> dict[str, dict[str, float]]:
    """Inference-only path: loads the already-fitted model `run_uncertainty(persist=True)`
    saved (no `.fit()` call here at all) and scores `feature_rows` -- a DataFrame with
    `player_id` plus every column in `FEATURES`, e.g. a handful of players whose situation
    changed since the last full walk-forward run. This is what closes the gap the audit found:
    previously the *only* way to get any updated prediction was to re-run the entire
    multi-season walk-forward training loop, even to refresh a single player.

    Reconstructs the same p10-p90/top-12/24 output `run_uncertainty` writes, from the same
    persisted calibration residuals (not re-derived, not approximated) -- a caller cannot tell
    from the output whether a row came from this path or from a full training run, which is
    exactly the property a real inference-only serving path needs. Writes to
    `uncertainty_predictions` the same way `run_uncertainty` does unless `store=False`."""
    if feature_rows.empty:
        return {}

    model = load_regressor(ARTIFACT_MODEL_NAME, position, model_version)
    residuals = load_calibration_residuals(con, ARTIFACT_MODEL_NAME, position, model_version)
    quantile_offsets = fit_conformal_quantiles(residuals)

    preds = model.predict(feature_rows[FEATURES].to_numpy())
    point_predictions = dict(
        zip(feature_rows["player_id"].tolist(), (float(p) for p in preds), strict=True)
    )
    mc_probs = monte_carlo_top_n_probabilities(point_predictions, residuals)

    now = utcnow()
    full_predictions: dict[str, dict[str, float]] = {}
    for player_id, point_pred in point_predictions.items():
        quantiles = apply_quantiles(point_pred, quantile_offsets)
        # point_prediction alongside the quantiles (apply_quantiles itself only returns
        # p10/p25/median/p75/p90 -- the same contract `run_uncertainty`'s own calibration path
        # relies on -- so it's added here rather than changed there).
        full_predictions[player_id] = {**quantiles, "point_prediction": point_pred}
        if store:
            _store_prediction(
                con,
                player_id,
                season,
                position,
                point_pred,
                quantiles,
                mc_probs[player_id],
                calibration_season if calibration_season is not None else season - 1,
                now,
                model_version,
            )
    return full_predictions
