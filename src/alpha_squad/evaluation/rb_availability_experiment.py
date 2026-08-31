"""D70: RB availability experiment (`docs/RB_AVAILABILITY_PREREGISTRATION.md`).

Implements exactly the pre-registered treatment and gates -- nothing more. Read the
pre-registration first; this module follows its section numbers.

What this is
------------
D69 abandoned RB-only projection *calibration* (a residual correction) but found the RB
residual strongly associated with games played, and recommended asking a model question
instead: does giving M6 preseason-knowable availability information (F1-F4) reduce RB
projection error, where a positional constant could not? A follow-up rank-conditioning
diagnostic (outside this codebase's tracked history) found the RB residual does not behave like
a winner's-curse artifact, which is what authorized this phase to proceed.

What varies, and what does not
-------------------------------
**RB only.** M6 is refit for RB alone with `FEATURES + AVAILABILITY_FEATURES`; QB, WR, TE, K
and DST projections are the untouched control (`X0`). This is not a simplification -- it is
what the pre-registration's own title and its "report the incremental value... not the value of
availability information in the abstract" language ask for, and it makes gate B2's "not made
worse at QB/WR/TE" hold by identity for those three positions rather than by measurement. If a
broader refit were wanted, that is a different, not-yet-pre-registered phase.

Same walk-forward split, same hyperparameters, same thresholds as `models/uncertainty/run.py`
(imported, not re-declared) -- section 4 and section 8.2 of the pre-registration. The draft
engine is untouched; the only insertion point is `draft_forensics.py::load_season_static`'s
`projections_override`, exactly as D68/D69 used it (section 6).

`TREATED_SEASONS = (2023, 2024, 2025)` is the entire scope of this module. Requesting any other
season raises -- "do not treat 2021-2022 for power" is an explicit prohibition (abandonment
condition 6), and this is its structural guard rather than a comment someone has to remember.

Layer ordering
--------------
`evaluate_projection_layer` (B1-B3) must be run, and must pass, before `rb_availability_static`
is ever called from the draft layer. That ordering -- not a convention, an actual dependency in
how these functions are meant to be invoked -- is what stops a feature set from being chosen by
draft outcome (section 6, "binding").
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
from catboost import CatBoostRegressor

from alpha_squad.evaluation.draft_forensics import SeasonStatic, load_season_static
from alpha_squad.evaluation.projection_calibration import band_edges, season_demand
from alpha_squad.features.availability import (
    AVAILABILITY_FEATURES,
    build_availability_features,
    validate_no_leakage,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)
from alpha_squad.models.uncertainty.run import MIN_CALIB_ROWS, MIN_TRAIN_ROWS
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

#: Section 4: "Treated seasons for the draft layer: 2023-2025 ... Fixed now." This module
#: fits for no other season -- see `fit_rb_availability_model`'s guard.
TREATED_SEASONS: tuple[int, ...] = (2023, 2024, 2025)

#: RB only (see module docstring). Section 5's closed feature list, appended to the existing
#: M6 features -- `prior_games` stays, F1 generalizes it, per section 5's own note.
TREATMENT_POSITION = "RB"
TREATMENT_FEATURES: list[str] = [*FEATURES, *AVAILABILITY_FEATURES]

#: Identical to `models/uncertainty/run.py`'s CatBoost configuration -- "same hyperparameters",
#: section 6. No architecture change, no sweep.
_MODEL_KWARGS: dict = {
    "iterations": 150,
    "depth": 3,
    "learning_rate": 0.08,
    "loss_function": "MAE",
    "verbose": False,
    "random_seed": 42,
}

#: B9: the committed practical-significance floor, section 7.
PRACTICAL_SIGNIFICANCE_FLOOR = 25.0
#: B5: at most this many treated seasons may be worse than control.
MAX_WORSE_SEASONS = 1


@dataclass(frozen=True)
class RBAvailabilityFit:
    """One target season's walk-forward RB refit -- predictions plus everything needed to
    audit how they were produced."""

    target_season: int
    point_predictions: dict[str, float]
    #: F1 itself (the multi-season games-played average), read as this treatment's
    #: "availability component" for gate B3 -- see `evaluate_projection_layer`.
    predicted_games: dict[str, float]
    training_seasons: tuple[int, ...]
    n_train: int
    n_calib: int


def fit_rb_availability_model(
    con: duckdb.DuckDBPyConnection, target_season: int, min_train_season: int = 2015
) -> RBAvailabilityFit:
    """Walk-forward RB refit with `TREATMENT_FEATURES`, for `target_season` only.

    Train/calib/target split is byte-for-byte the same shape as
    `models/uncertainty/run.py::run_uncertainty`'s loop body: train on target seasons strictly
    before `target_season - 1`, calibrate on `target_season - 1`, predict `target_season`."""
    if target_season not in TREATED_SEASONS:
        raise ValueError(
            f"D70 is pre-registered for TREATED_SEASONS={TREATED_SEASONS} only; fitting "
            f"{target_season} would treat a season the pre-registration forbids "
            f"(RB_AVAILABILITY_PREREGISTRATION.md, abandonment condition 6)."
        )
    calib_season = target_season - 1

    season_level = load_season_level_data(con, TREATMENT_POSITION, min_train_season, target_season)
    availability = build_availability_features(
        con, TREATMENT_POSITION, min_train_season, target_season
    )
    merged = season_level.merge(availability, on=["player_id", "target_season"], how="left")

    proper_train = merged[merged["target_season"] < calib_season]
    calib = merged[merged["target_season"] == calib_season]
    target = merged[merged["target_season"] == target_season]

    validate_no_leakage(
        [*proper_train["target_season"].tolist(), *calib["target_season"].tolist()],
        target_season,
    )

    if len(proper_train) < MIN_TRAIN_ROWS or len(calib) < MIN_CALIB_ROWS or target.empty:
        raise ValueError(
            f"insufficient data for {TREATMENT_POSITION}/{target_season}: "
            f"train={len(proper_train)} calib={len(calib)} target={len(target)} "
            f"(thresholds reused from models/uncertainty/run.py: "
            f"MIN_TRAIN_ROWS={MIN_TRAIN_ROWS}, MIN_CALIB_ROWS={MIN_CALIB_ROWS})"
        )

    model = CatBoostRegressor(**_MODEL_KWARGS)
    model.fit(proper_train[TREATMENT_FEATURES].to_numpy(), proper_train[TARGET_COLUMN].to_numpy())

    target_preds = model.predict(target[TREATMENT_FEATURES].to_numpy())
    point_predictions = dict(
        zip(target["player_id"].tolist(), (float(p) for p in target_preds), strict=True)
    )
    predicted_games = dict(
        zip(
            target["player_id"].tolist(),
            (float(g) for g in target["avail_games_played_history"]),
            strict=True,
        )
    )

    return RBAvailabilityFit(
        target_season=target_season,
        point_predictions=point_predictions,
        predicted_games=predicted_games,
        training_seasons=tuple(sorted(set(proper_train["target_season"].tolist()))),
        n_train=len(proper_train),
        n_calib=len(calib),
    )


def _control_rb_predictions(con: duckdb.DuckDBPyConnection, season: int) -> dict[str, float]:
    """RB `point_prediction` from the unmodified M6 model -- the `X0` control, same source
    D68/D69's `load_residual_rows` reads."""
    rows = con.execute(
        "SELECT player_id, point_prediction FROM uncertainty_predictions "
        "WHERE season = ? AND model_version = ? AND point_prediction IS NOT NULL",
        [season, UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    return dict(rows)


def _realized_rb(con: duckdb.DuckDBPyConnection, season: int) -> tuple[dict, dict]:
    rows = con.execute(
        "SELECT player_id, total_fantasy_points_ppr, games_played FROM player_season_stats "
        "WHERE season = ? AND position = ?",
        [season, TREATMENT_POSITION],
    ).fetchall()
    return ({r[0]: r[1] for r in rows}, {r[0]: r[2] for r in rows})


@dataclass(frozen=True)
class ProjectionLayerResult:
    per_season: list[dict] = field(default_factory=list)
    gates: dict = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        return bool(self.gates) and all(g["passes"] for g in self.gates.values())


def evaluate_projection_layer(
    con: duckdb.DuckDBPyConnection, league: LeagueContext
) -> ProjectionLayerResult:
    """Gates B1-B3, section 7. Must be evaluated -- and must pass -- before the draft layer is
    ever run; `rb_availability_static` is not safe to call otherwise.

    The evaluation universe is the same D68/D69 draftable cut (`band_edges`/`season_demand`,
    bands 1+2), ranked by the CONTROL projection -- so treatment and control are scored on an
    identical population, and the treatment cannot improve its own metrics by changing who
    counts as draftable."""
    per_season = []
    for season in TREATED_SEASONS:
        fit = fit_rb_availability_model(con, season)
        control = _control_rb_predictions(con, season)
        realized, games = _realized_rb(con, season)

        edges = band_edges(league, season_demand(con, league, season))[TREATMENT_POSITION]
        ranked = sorted(control, key=lambda pid: (-control[pid], pid))
        universe = {pid for i, pid in enumerate(ranked, start=1) if i <= edges[1]}
        common = sorted(universe & set(fit.point_predictions) & set(control) & set(realized))

        treat_err = [realized[p] - fit.point_predictions[p] for p in common]
        ctrl_err = [realized[p] - control[p] for p in common]

        b3_common = [
            p
            for p in common
            if p in fit.predicted_games
            and games.get(p) is not None
            and fit.predicted_games[p] == fit.predicted_games[p]  # drop NaN
        ]
        if len(b3_common) >= 3:
            b3_corr = float(
                np.corrcoef(
                    [fit.predicted_games[p] for p in b3_common],
                    [games[p] for p in b3_common],
                )[0, 1]
            )
        else:
            b3_corr = float("nan")

        per_season.append(
            {
                "season": season,
                "n": len(common),
                "treatment_mae": float(np.mean(np.abs(treat_err))),
                "control_mae": float(np.mean(np.abs(ctrl_err))),
                "treatment_rmse": float(np.sqrt(np.mean(np.square(treat_err)))),
                "control_rmse": float(np.sqrt(np.mean(np.square(ctrl_err)))),
                "treatment_mean_signed_residual": float(np.mean(treat_err)),
                "control_mean_signed_residual": float(np.mean(ctrl_err)),
                "b3_correlation": b3_corr,
                "b3_n": len(b3_common),
                "training_seasons": list(fit.training_seasons),
            }
        )

    gates = _gate_projection_layer(per_season)
    return ProjectionLayerResult(per_season=per_season, gates=gates)


def _gate_projection_layer(per_season: list[dict]) -> dict:
    pooled_treat_mae = float(np.mean([r["treatment_mae"] for r in per_season]))
    pooled_ctrl_mae = float(np.mean([r["control_mae"] for r in per_season]))
    pooled_treat_rmse = float(np.mean([r["treatment_rmse"] for r in per_season]))
    pooled_ctrl_rmse = float(np.mean([r["control_rmse"] for r in per_season]))
    worse_mae_seasons = sum(1 for r in per_season if r["treatment_mae"] > r["control_mae"])
    b1 = (
        pooled_treat_mae <= pooled_ctrl_mae
        and pooled_treat_rmse <= pooled_ctrl_rmse
        and worse_mae_seasons <= MAX_WORSE_SEASONS
    )

    pooled_treat_bias = float(
        np.mean([abs(r["treatment_mean_signed_residual"]) for r in per_season])
    )
    pooled_ctrl_bias = float(np.mean([abs(r["control_mean_signed_residual"]) for r in per_season]))
    not_worse_any_season = all(
        abs(r["treatment_mean_signed_residual"]) <= abs(r["control_mean_signed_residual"]) + 1e-9
        for r in per_season
    )
    b2 = pooled_treat_bias < pooled_ctrl_bias and not_worse_any_season

    b3_correlations = [r["b3_correlation"] for r in per_season]
    b3 = all(c == c and c > 0.0 for c in b3_correlations)  # c==c excludes NaN

    return {
        "B1_accuracy": {
            "passes": bool(b1),
            "pooled_treatment_mae": pooled_treat_mae,
            "pooled_control_mae": pooled_ctrl_mae,
            "pooled_treatment_rmse": pooled_treat_rmse,
            "pooled_control_rmse": pooled_ctrl_rmse,
            "seasons_worse_mae": worse_mae_seasons,
        },
        "B2_bias_falls": {
            "passes": bool(b2),
            "pooled_treatment_abs_bias": pooled_treat_bias,
            "pooled_control_abs_bias": pooled_ctrl_bias,
            "not_worse_in_any_season": not_worse_any_season,
        },
        "B3_availability_predicts_games": {
            "passes": bool(b3),
            "correlations_by_season": dict(zip(TREATED_SEASONS, b3_correlations, strict=True)),
        },
    }


def rb_availability_static(
    con: duckdb.DuckDBPyConnection, league: LeagueContext, season: int, control: SeasonStatic
) -> SeasonStatic:
    """The draft-layer treatment: `control`'s projections with RB entries replaced by the
    walk-forward availability-refit predictions, everything else byte-identical.

    **Must not be called before `evaluate_projection_layer` has been run and has passed.**
    Nothing here checks that at runtime -- the ordering is enforced by which functions the
    caller invokes, exactly as D68/D69's own layer ordering was, per the pre-registration's
    "binding" language rather than an in-code assertion that would only catch the mistake after
    the fact.

    Only player_ids the CONTROL board already carries are replaced (a treatment player absent
    from the control board would be a scope change no gate has evaluated)."""
    if season not in TREATED_SEASONS:
        return control
    fit = fit_rb_availability_model(con, season)
    calibrated = dict(control.projections)
    for player_id, value in fit.point_predictions.items():
        if player_id in calibrated:
            calibrated[player_id] = value
    return load_season_static(
        con, league, season, ecr_type=control.ecr_type, projections_override=calibrated
    )
