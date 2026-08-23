"""Walk-forward rookie model training, strictly by draft class: predicting draft class C
trains only on classes < C, never C itself or later — the rookie analog of M4/M5's
season-based walk-forward discipline. Two targets, matching PRODUCT_SPEC.md's rookie
modeling requirements: rookie-year PPR points (regression) and top-24-at-position breakout
(classification)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import duckdb
from catboost import CatBoostClassifier, CatBoostRegressor

from alpha_squad.models.evaluate import (
    evaluate_and_record,
    evaluate_classification,
    record_classification,
)
from alpha_squad.models.rookie.data import load_rookie_class_data
from alpha_squad.models.rookie.features import (
    CLASSIFICATION_TARGET,
    FEATURE_VERSION,
    FEATURES,
    POSITIONS,
    REGRESSION_TARGET,
)
from alpha_squad.sources.base import utcnow

REGRESSION_MODEL_NAME = "ml_rookie_regression"
CLASSIFICATION_MODEL_NAME = "ml_rookie_breakout"
MIN_TRAIN_ROWS = 25


def _register_model(con, model_name, position, class_start, class_end, notes, feature_version):
    con.execute(
        """
        INSERT INTO model_registry
            (model_name, position, version, feature_version, training_season_start,
             training_season_end, trained_at, validated, notes)
        VALUES (?, ?, 'v1', ?, ?, ?, ?, true, ?)
        ON CONFLICT (model_name, position, version) DO UPDATE SET
            feature_version = excluded.feature_version,
            training_season_start = excluded.training_season_start,
            training_season_end = excluded.training_season_end,
            trained_at = excluded.trained_at, notes = excluded.notes
        """,
        [model_name, position, feature_version, class_start, class_end, utcnow(), notes],
    )


def _prediction_id(player_id: str, draft_class: int, feature_version: str) -> str:
    """feature_version is part of the hash because `rookie_predictions` is UNIQUE on
    (player_id, draft_class, model_version) but PRIMARY KEY on prediction_id -- two feature
    sets predicting the same player/class are legitimately distinct rows, and without this
    they collide on the PK (the UNIQUE-targeted ON CONFLICT clause doesn't catch it, so it
    surfaces as a raw constraint violation). Latent until the D39 ablation ran two arms."""
    digest = hashlib.md5(f"{player_id}:{draft_class}:{feature_version}".encode()).hexdigest()[:16]
    return f"rookiepred_{digest}"


@dataclass
class RookieTrainReport:
    regression_metrics: list = field(default_factory=list)
    classification_metrics: list = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def run_rookie_models(
    con: duckdb.DuckDBPyConnection,
    class_start: int,
    class_end: int,
    min_train_class: int = 2000,
    *,
    features: list[str] | None = None,
    feature_version: str = FEATURE_VERSION,
    model_suffix: str = "",
) -> RookieTrainReport:
    """`features`/`feature_version`/`model_suffix` default to the current production feature
    set, so existing callers are unaffected. They exist so an ablation can train a second
    feature set over identical walk-forward folds under distinct model names -- necessary
    because evaluation_results/classification_results are keyed on
    (model_name, season|cohort, position) and would otherwise overwrite the first arm (D39)."""
    features = features if features is not None else FEATURES
    report = RookieTrainReport()

    for target_class in range(class_start, class_end + 1):
        for position in POSITIONS:
            train_df = load_rookie_class_data(
                con, position, min_train_class, target_class - 1, features
            )
            target_df = load_rookie_class_data(con, position, target_class, target_class, features)

            if len(train_df) < MIN_TRAIN_ROWS or target_df.empty:
                report.skipped.append(f"{position}/{target_class}: {len(train_df)} training rows")
                continue

            x_train = train_df[features].to_numpy()
            x_target = target_df[features].to_numpy()

            reg = CatBoostRegressor(
                iterations=150,
                depth=3,
                learning_rate=0.08,
                loss_function="MAE",
                verbose=False,
                random_seed=42,
            )
            reg.fit(x_train, train_df[REGRESSION_TARGET].to_numpy())
            reg_preds = reg.predict(x_target)
            predicted_points = dict(
                zip(target_df["player_id"].tolist(), (float(p) for p in reg_preds), strict=True)
            )
            reg_metrics = evaluate_and_record(
                con,
                f"{REGRESSION_MODEL_NAME}_{position.lower()}{model_suffix}",
                target_class,
                predicted_points,
            )
            report.regression_metrics.extend(m for m in reg_metrics if m.position == "ALL")
            _register_model(
                con,
                f"{REGRESSION_MODEL_NAME}{model_suffix}",
                position,
                min_train_class,
                target_class - 1,
                f"walk-forward by draft class; {len(features)} features ({feature_version})",
                feature_version,
            )

            clf = CatBoostClassifier(
                iterations=150,
                depth=3,
                learning_rate=0.08,
                loss_function="Logloss",
                verbose=False,
                random_seed=42,
            )
            clf.fit(x_train, train_df[CLASSIFICATION_TARGET].astype(int).to_numpy())
            clf_probs = clf.predict_proba(x_target)[:, 1]
            predicted_breakout = dict(
                zip(target_df["player_id"].tolist(), (float(p) for p in clf_probs), strict=True)
            )
            actual_breakout = dict(
                zip(
                    target_df["player_id"].tolist(),
                    target_df[CLASSIFICATION_TARGET].tolist(),
                    strict=True,
                )
            )
            clf_metrics = evaluate_classification(
                f"{CLASSIFICATION_MODEL_NAME}_{position.lower()}{model_suffix}",
                target_class,
                position,
                predicted_breakout,
                actual_breakout,
            )
            record_classification(con, clf_metrics)
            report.classification_metrics.append(clf_metrics)
            _register_model(
                con,
                f"{CLASSIFICATION_MODEL_NAME}{model_suffix}",
                position,
                min_train_class,
                target_class - 1,
                "walk-forward by draft class; predicts top-24-at-position finish in rookie year "
                f"({len(features)} features, {feature_version})",
                feature_version,
            )

            now = utcnow()
            for player_id in target_df["player_id"]:
                con.execute(
                    """
                    INSERT INTO rookie_predictions
                        (prediction_id, player_id, draft_class, position, model_version,
                         predicted_rookie_points, breakout_probability, predicted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (player_id, draft_class, model_version) DO UPDATE SET
                        predicted_rookie_points = excluded.predicted_rookie_points,
                        breakout_probability = excluded.breakout_probability,
                        predicted_at = excluded.predicted_at
                    """,
                    [
                        _prediction_id(player_id, target_class, feature_version),
                        player_id,
                        target_class,
                        position,
                        feature_version,
                        predicted_points.get(player_id),
                        predicted_breakout.get(player_id),
                        now,
                    ],
                )

    return report
