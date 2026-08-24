"""Model artifact persistence -- the missing inference-only serving path
`docs/CURRENT_STATE_AUDIT.md` found: no model was ever saved to disk anywhere in this codebase,
so every prediction (including what `/rankings` and `/rookies` actually serve) required a full
retrain in the same process, because no fitted model object ever survived past the training
function's return.

Fitted CatBoost models are saved in their native format (`.cbm`) under
`models/{model_version}/{model_name}_{position}.cbm` -- `models/` is gitignored, exactly like
`data/`/`predictions/`/`state/` (CLAUDE.md: reproducible from the pipeline, never committed).
`model_registry.artifact_path` records where; `model_registry.calibration_residuals_json`
optionally carries a JSON-serialized calibration-residual array alongside it, for models (like
the uncertainty model) whose full serving story needs more than the point prediction to
reconstruct without retraining.

This module is deliberately generic (regressor/classifier save+load, a path helper, a registry
upsert) rather than owning any position/season/feature logic -- callers in
`models/uncertainty/run.py` and `models/rookie/train.py` decide what and when to persist."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor

from alpha_squad.config.settings import get_settings
from alpha_squad.sources.base import utcnow

ArtifactModel = CatBoostRegressor | CatBoostClassifier


def artifact_path(model_name: str, position: str, model_version: str) -> Path:
    settings = get_settings()
    return settings.models_dir / model_version / f"{model_name}_{position}.cbm"


def save_model(model: ArtifactModel, model_name: str, position: str, model_version: str) -> str:
    """Saves in CatBoost's native format and returns the path as a string (what
    `model_registry.artifact_path` stores)."""
    path = artifact_path(model_name, position, model_version)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))
    return str(path)


def _load(
    cls: type[ArtifactModel], model_name: str, position: str, model_version: str
) -> ArtifactModel:
    path = artifact_path(model_name, position, model_version)
    if not path.exists():
        raise FileNotFoundError(
            f"No persisted model at {path} -- run the training command for "
            f"{model_name}/{position}/{model_version} with persist=True first."
        )
    model = cls()
    model.load_model(str(path))
    return model


def load_regressor(model_name: str, position: str, model_version: str) -> CatBoostRegressor:
    return _load(CatBoostRegressor, model_name, position, model_version)


def load_classifier(model_name: str, position: str, model_version: str) -> CatBoostClassifier:
    return _load(CatBoostClassifier, model_name, position, model_version)


def register_artifact(
    con,
    model_name: str,
    position: str,
    model_version: str,
    feature_version: str,
    training_season_start: int,
    training_season_end: int,
    artifact_path_str: str,
    *,
    validated: bool = True,
    notes: str = "",
    calibration_residuals: np.ndarray | None = None,
) -> None:
    """Upserts a `model_registry` row carrying the artifact path (and, when given, calibration
    residuals as JSON) -- the row a caller reads back via `load_regressor`/`load_classifier` +
    `load_calibration_residuals` to serve without retraining. Same upsert-on-(model_name,
    position, version) semantics the pre-existing per-module `_register_model` helpers already
    use, so re-running training for a later season naturally replaces the prior artifact with
    the one trained on more data -- there is deliberately only ever one "latest" artifact per
    key, not one per season."""
    residuals_json = (
        json.dumps([float(r) for r in calibration_residuals])
        if calibration_residuals is not None
        else None
    )
    con.execute(
        """
        INSERT INTO model_registry
            (model_name, position, version, feature_version, training_season_start,
             training_season_end, trained_at, validated, notes, artifact_path,
             calibration_residuals_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (model_name, position, version) DO UPDATE SET
            feature_version = excluded.feature_version,
            training_season_start = excluded.training_season_start,
            training_season_end = excluded.training_season_end,
            trained_at = excluded.trained_at,
            validated = excluded.validated,
            notes = excluded.notes,
            artifact_path = excluded.artifact_path,
            calibration_residuals_json = excluded.calibration_residuals_json
        """,
        [
            model_name,
            position,
            model_version,
            feature_version,
            training_season_start,
            training_season_end,
            utcnow(),
            validated,
            notes,
            artifact_path_str,
            residuals_json,
        ],
    )


def load_calibration_residuals(
    con, model_name: str, position: str, model_version: str
) -> np.ndarray:
    row = con.execute(
        "SELECT calibration_residuals_json FROM model_registry "
        "WHERE model_name = ? AND position = ? AND version = ?",
        [model_name, position, model_version],
    ).fetchone()
    if row is None or row[0] is None:
        raise FileNotFoundError(
            f"No persisted calibration residuals for {model_name}/{position}/{model_version} -- "
            "was this model registered with persist=True?"
        )
    return np.array(json.loads(row[0]), dtype=float)
