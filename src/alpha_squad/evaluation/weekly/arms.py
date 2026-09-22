"""W6 research arms: the same weekly model trained on a different part of the outcome.

**Research only. Nothing here writes to the database, and no production module imports it.**

What this module is for
-----------------------
W5 found that Alpha's top-of-board failure at RB and WR is a *selection* problem: it ranks by
expected **floor** while points-captured@10 is decided by **ceiling**. The obvious single-variable
test is to change what the model is asked to predict -- from the middle of the outcome
distribution to its upper part -- and change **nothing else**.

So this module re-implements the weekly walk-forward prediction loop from
`models/established/train.py::run_established_ml` with exactly one substitution: the CatBoost
`loss_function`. Same 11 features, same target column, same `iterations`/`depth`/`learning_rate`/
`random_seed`, same per-position split, same `[min_train_season, S-1]` window, same
`fillna(0.0)`, same prediction frame.

Why it is a re-implementation rather than a call into production
---------------------------------------------------------------
`run_established_ml` fits five model specs, writes to `weekly_projection_snapshot`,
`model_registry` and `evaluation_results`, and computes season aggregates. W6 needs none of that
and must not touch any of it. The re-implementation is the narrow slice that produces weekly
predictions -- and because a re-implementation can silently drift from the thing it claims to
mirror, **the `A_MAE` arm must reproduce the stored production predictions exactly**, which is
W6's first validity gate. If that gate fails, every arm comparison is meaningless, so it runs
before anything is interpreted.

The arms
--------
``A_MAE``    the production loss. MAE fits the conditional **median**.
``B0_RMSE``  the conditional **mean** -- a *discriminating control*, not a candidate. Without it,
             a win for an upper quantile cannot be separated from "anything other than MAE helps".
``B1_Q60`` / ``B2_Q70`` / ``B3_Q80``  quantile regression above the median, the direct
             implementation of "care more about high-end outcomes". ``B2_Q70`` is the
             pre-registered **primary** arm; the other two exist to show whether the effect is
             monotone in how far up the distribution the target sits.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
from catboost import CatBoostRegressor

from alpha_squad.models.established.data import load_position_week_data
from alpha_squad.models.established.features import FULL_FEATURES, POSITIONS, TARGET_COLUMN
from alpha_squad.models.established.train import MIN_TRAINING_ROWS

#: Every hyperparameter is production's, copied from `MODEL_SPECS["ml_catboost"]`. Only
#: `loss_function` is substituted per arm, and `thread_count` is NOT set here for the same reason
#: production does not set it: matching production exactly is the point.
BASE_KWARGS: dict = {
    "iterations": 200,
    "depth": 4,
    "learning_rate": 0.05,
    "verbose": False,
    "random_seed": 42,
}

#: Arm -> CatBoost loss. Fixed in `docs/weekly/W6_PREREGISTRATION.md` before any result existed.
ARM_LOSS: dict[str, str] = {
    "A_MAE": "MAE",
    "B0_RMSE": "RMSE",
    "B1_Q60": "Quantile:alpha=0.6",
    "B2_Q70": "Quantile:alpha=0.7",
    "B3_Q80": "Quantile:alpha=0.8",
}
ARMS: tuple[str, ...] = tuple(ARM_LOSS)
#: The single pre-registered primary arm. The others cannot rescue it (pre-registration §7).
PRIMARY_ARM = "B2_Q70"
#: The arm that must reproduce production bit-for-bit.
CONTROL_ARM = "A_MAE"

TRAIN_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)
MIN_TRAIN_SEASON = 2015


@dataclass
class ArmPredictions:
    """One arm's weekly predictions, keyed exactly as `weekly_projection_snapshot` is.

    `position_by_key` is carried alongside rather than derived from a player id, because the panel
    is built per position and a player id is not guaranteed to map to one position across seasons.
    Every board W6 scores is positional, so the filter has to be exact."""

    arm: str
    loss: str
    by_key: dict[tuple[str, int, int], float]
    position_by_key: dict[tuple[str, int, int], str]
    by_position: dict[str, int]
    skipped: list[str]

    def for_week(self, season: int, week: int, position: str | None = None) -> dict[str, float]:
        """One week's predictions as `player_id -> value`, optionally one position only."""
        return {
            pid: value
            for (pid, s, w), value in self.by_key.items()
            if s == season
            and w == week
            and (position is None or self.position_by_key[(pid, s, w)] == position)
        }


def train_arm(
    con: duckdb.DuckDBPyConnection,
    arm: str,
    *,
    seasons: tuple[int, ...] = TRAIN_SEASONS,
    min_train_season: int = MIN_TRAIN_SEASON,
    positions: tuple[str, ...] = POSITIONS,
) -> ArmPredictions:
    """Walk-forward weekly predictions for one arm.

    Mirrors `run_established_ml`'s loop shape exactly: for each target season, for each position,
    fit on `[min_train_season, season - 1]` and predict that season's rows. The model is refit
    **once per season** and never sees a week of the season it predicts -- a property of the
    production design, preserved here rather than improved, because W6 changes one thing."""
    if arm not in ARM_LOSS:
        known = ", ".join(ARMS)
        raise ValueError(f"unknown arm {arm!r}; known: {known}")
    loss = ARM_LOSS[arm]
    out: dict[tuple[str, int, int], float] = {}
    pos_of: dict[tuple[str, int, int], str] = {}
    counts: dict[str, int] = {}
    skipped: list[str] = []

    for target_season in seasons:
        for position in positions:
            train_df = load_position_week_data(con, position, min_train_season, target_season - 1)
            if len(train_df) < MIN_TRAINING_ROWS:
                skipped.append(f"{position}/{target_season}: only {len(train_df)} training rows")
                continue
            predict_df = load_position_week_data(con, position, target_season, target_season)
            if predict_df.empty:
                continue
            model = CatBoostRegressor(loss_function=loss, **BASE_KWARGS)
            model.fit(train_df[FULL_FEATURES].to_numpy(), train_df[TARGET_COLUMN].to_numpy())
            preds = model.predict(predict_df[FULL_FEATURES].to_numpy())
            for pid, season, week, pred in zip(
                predict_df["player_id"].tolist(),
                predict_df["season"].tolist(),
                predict_df["week"].tolist(),
                preds,
                strict=True,
            ):
                key = (pid, int(season), int(week))
                out[key] = float(pred)
                pos_of[key] = position
                counts[position] = counts.get(position, 0) + 1
    return ArmPredictions(
        arm=arm,
        loss=loss,
        by_key=out,
        position_by_key=pos_of,
        by_position=counts,
        skipped=skipped,
    )


def load_production_predictions(
    con: duckdb.DuckDBPyConnection, model_name: str = "ml_catboost"
) -> dict[tuple[str, int, int], float]:
    """The predictions the unmodified production path actually wrote, for the control gate."""
    return {
        (pid, int(season), int(week)): float(value)
        for pid, season, week, value in con.execute(
            "SELECT player_id, season, week, predicted_points "
            "FROM weekly_projection_snapshot WHERE model_name = ?",
            [model_name],
        ).fetchall()
    }


def compare_to_production(
    trained: ArmPredictions, stored: dict[tuple[str, int, int], float]
) -> dict:
    """How closely the re-implemented control matches what production stored.

    Reported in full rather than as a boolean, because *how* it differs is the diagnosis: a
    handful of keys means a universe mismatch, a small uniform epsilon means floating-point
    non-determinism inside CatBoost, and a large spread means the re-implementation is wrong."""
    only_trained = set(trained.by_key) - set(stored)
    only_stored = set(stored) - set(trained.by_key)
    shared = sorted(set(trained.by_key) & set(stored))
    diffs = [abs(trained.by_key[k] - stored[k]) for k in shared]
    exact = sum(1 for d in diffs if d == 0.0)
    return {
        "n_trained": len(trained.by_key),
        "n_stored": len(stored),
        "n_shared": len(shared),
        "only_in_trained": len(only_trained),
        "only_in_stored": len(only_stored),
        "exact_matches": exact,
        "exact_share": exact / len(shared) if shared else None,
        "max_abs_diff": max(diffs) if diffs else None,
        "mean_abs_diff": (sum(diffs) / len(diffs)) if diffs else None,
    }
