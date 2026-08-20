"""Walk-forward training and evaluation for established-player ML.

For each target season S and position, every model trains only on player_week_features rows
from seasons < S (an expanding window — never S itself or later), predicts every row in
season S, then aggregates those weekly predictions into a season-total per player to compare
against player_season_stats.total_fantasy_points_ppr through the exact same evaluation
harness M4's baselines use (models/evaluate.py) — so "did ML beat the baseline" is a direct,
apples-to-apples comparison at the same grain, not a different metric.

Ensemble use is gated on evidence (ARCHITECTURE.md §5: "ensemble methods only when
validation justifies them") — it is only registered `validated=True` if it beats every
individual component model's MAE out of sample; otherwise it's still reported (never hidden)
but marked unvalidated, per ARCHITECTURE.md §12's "unvalidated model... barred from being the
default decision source.\""""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
from catboost import CatBoostRegressor
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from alpha_squad.models.established.data import load_position_week_data
from alpha_squad.models.established.features import (
    FEATURE_VERSION,
    FULL_FEATURES,
    OPPORTUNITY_FEATURES,
    POSITIONS,
    TARGET_COLUMN,
    TEAM_FEATURES,
)
from alpha_squad.models.evaluate import EvaluationMetrics, evaluate_and_record
from alpha_squad.sources.base import utcnow

MODEL_SPECS: dict[str, tuple[type, dict, list[str]]] = {
    "ml_ridge": (Ridge, {"alpha": 5.0}, FULL_FEATURES),
    "ml_catboost": (
        CatBoostRegressor,
        {
            "iterations": 200,
            "depth": 4,
            "learning_rate": 0.05,
            "loss_function": "MAE",
            "verbose": False,
            "random_seed": 42,
        },
        FULL_FEATURES,
    ),
    "ml_xgboost": (
        XGBRegressor,
        {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05, "random_state": 42},
        FULL_FEATURES,
    ),
    "ml_opportunity_only": (Ridge, {"alpha": 1.0}, OPPORTUNITY_FEATURES),
    "ml_team_environment_only": (Ridge, {"alpha": 1.0}, TEAM_FEATURES),
}
COMPONENT_MODELS_FOR_ENSEMBLE = ("ml_ridge", "ml_catboost", "ml_xgboost")
MIN_TRAINING_ROWS = 50


@dataclass
class TrainRunReport:
    metrics: list[EvaluationMetrics] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _season_totals_from_weekly(player_ids, weeks_predicted: np.ndarray) -> dict[str, float]:
    totals: dict[str, float] = {}
    for pid, pred in zip(player_ids, weeks_predicted, strict=True):
        totals[pid] = totals.get(pid, 0.0) + float(pred)
    return totals


def _register_model(
    con: duckdb.DuckDBPyConnection,
    model_name: str,
    position: str,
    season_start: int,
    season_end: int,
    validated: bool,
    notes: str,
) -> None:
    con.execute(
        """
        INSERT INTO model_registry
            (model_name, position, version, feature_version, training_season_start,
             training_season_end, trained_at, validated, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (model_name, position, version) DO UPDATE SET
            training_season_start = excluded.training_season_start,
            training_season_end = excluded.training_season_end,
            trained_at = excluded.trained_at,
            validated = excluded.validated,
            notes = excluded.notes
        """,
        [
            model_name,
            position,
            "v1",
            FEATURE_VERSION,
            season_start,
            season_end,
            utcnow(),
            validated,
            notes,
        ],
    )


def run_established_ml(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int, min_train_season: int = 2015
) -> TrainRunReport:
    report = TrainRunReport()

    for target_season in range(season_start, season_end + 1):
        for position in POSITIONS:
            train_df = load_position_week_data(con, position, min_train_season, target_season - 1)
            if len(train_df) < MIN_TRAINING_ROWS:
                report.skipped.append(
                    f"{position}/{target_season}: only {len(train_df)} training rows"
                )
                continue

            predict_df = load_position_week_data(con, position, target_season, target_season)
            if predict_df.empty:
                continue

            component_predictions: dict[str, dict[str, float]] = {}

            for model_name, (model_cls, kwargs, feature_cols) in MODEL_SPECS.items():
                x_train = train_df[feature_cols].to_numpy()
                y_train = train_df[TARGET_COLUMN].to_numpy()
                x_pred = predict_df[feature_cols].to_numpy()

                model = model_cls(**kwargs)
                model.fit(x_train, y_train)
                weekly_preds = model.predict(x_pred)

                season_totals = _season_totals_from_weekly(
                    predict_df["player_id"].tolist(), weekly_preds
                )
                component_predictions[model_name] = season_totals

                metrics = evaluate_and_record(
                    con, f"{model_name}_{position.lower()}", target_season, season_totals
                )
                report.metrics.extend(m for m in metrics if m.position == "ALL")
                _register_model(
                    con,
                    model_name,
                    position,
                    min_train_season,
                    target_season - 1,
                    validated=True,
                    notes="individual model",
                )

            ensemble_totals: dict[str, float] = {}
            for pid in component_predictions[COMPONENT_MODELS_FOR_ENSEMBLE[0]]:
                if all(pid in component_predictions[m] for m in COMPONENT_MODELS_FOR_ENSEMBLE):
                    ensemble_totals[pid] = float(
                        np.mean(
                            [component_predictions[m][pid] for m in COMPONENT_MODELS_FOR_ENSEMBLE]
                        )
                    )
            if ensemble_totals:
                ensemble_metrics = evaluate_and_record(
                    con, f"ml_ensemble_{position.lower()}", target_season, ensemble_totals
                )
                report.metrics.extend(m for m in ensemble_metrics if m.position == "ALL")

                ensemble_mae = next(m.mae for m in ensemble_metrics if m.position == "ALL")
                component_maes = []
                for comp in COMPONENT_MODELS_FOR_ENSEMBLE:
                    comp_rows = con.execute(
                        "SELECT mae FROM evaluation_results WHERE model_name = ? AND season = ? AND position = 'ALL'",
                        [f"{comp}_{position.lower()}", target_season],
                    ).fetchone()
                    if comp_rows:
                        component_maes.append(comp_rows[0])
                beats_all_components = bool(component_maes) and all(
                    ensemble_mae == ensemble_mae and cm == cm and ensemble_mae < cm
                    for cm in component_maes
                )
                _register_model(
                    con,
                    "ml_ensemble",
                    position,
                    min_train_season,
                    target_season - 1,
                    validated=beats_all_components,
                    notes=(
                        "beats all component models on MAE this season"
                        if beats_all_components
                        else "does NOT beat every component model out of sample; not used as a default decision source"
                    ),
                )

    return report
