"""Pre-registered walk-forward test of SEED-ENSEMBLING M6 (D83).

**Committed to git before any arm was run against real data.**

Why this candidate, and why it is not another guess
---------------------------------------------------
Three phases have now failed in two different directions:

  D79/D80  changed the ESTIMATOR (monotone constraints, shrinkage, XGBoost, deeper trees).
           Every arm failed.
  D82      changed the INFORMATION (age/career/draft capital, workload volume, usage share).
           Every arm failed, and in the elite tail the added-feature arms were WORSE than the
           control (RB top10 +8.4 / +6.3 / +6.3 MAE for F1/F2/F4).

Both directions failing is evidence of one common cause rather than two coincidences, and D82's
mechanism test measured it. Refitting the SHIPPED model while varying nothing but CatBoost's
random seed gives, averaged over 2022-2025 and over positions:

    tier      seed-to-seed prediction sd (fantasy points), control model
    top10                 9.66
    11_24                 6.89
    25_60                 5.72
    61_plus               2.42

The head of the board is **four times less determined by the data** than the body. That is a
variance problem, and it exists before any feature or estimator change is made. Added features
make it worse -- across 40 arm x position x tier cells, added seed instability and added error
are positively associated (Pearson r=+0.376, p=0.017, slope +1.23 MAE points per point of added
sd), which is a real but partial channel: it explains some of D82's damage, not all of it.

The response the diagnosis actually implies is neither more information nor a different
estimator. It is **averaging**, which is the one lever that attacks prediction variance directly
and cannot introduce bias of its own. Averaging k independent fits cuts the seed component of
prediction sd by roughly sqrt(k).

The arms
--------
Nested, so each arm is "production plus more seeds" rather than "a different seed":

    S0  seeds (42,)                  the shipped Y1 model, byte-identical to production
    S1  seeds 42..45   (4 fits)
    S2  seeds 42..53   (12 fits)
    S3  seeds 42..65   (24 fits)

Nothing else varies: same four features, same hyperparameters, same row specification, same
target, same walk-forward window. The prediction is the arithmetic mean of the member fits.

SELECTION RULE: ship the SMALLEST ensemble clearing every gate, because every extra seed is
linear extra training cost for a production pipeline. If no arm clears them, nothing ships and
M6 stays byte-identical to Y1.

Registered expectations, so the result cannot be reinterpreted afterwards
------------------------------------------------------------------------
* Averaging under an MAE objective is NOT guaranteed to help. The mean minimises squared error,
  not absolute error; a bias-free variance reduction improves MAE only to the extent the error
  distribution is not already centred. A null result here is a real and reportable finding.
* If it helps, it should help MOST in the head tiers, where seed sd is largest. An arm that
  improves only the body would be evidence the mechanism story is wrong, and must be reported
  as such rather than shipped on the pooled number.
* Shipping an ensemble would ALSO require refitting the conformal interval model on the
  ensemble's residuals before being called done (D78's separation of the point and interval
  fits). That is a follow-up condition, not a gate here, and is recorded so it cannot be
  forgotten.
* Shipping nothing is an explicitly acceptable outcome.

The gates are IMPORTED from D82 rather than restated, so they are literally the same thresholds
and the same code: P1 material and significant pooled gain, P2 no tier damaged, P3 no position
damaged, P4 RB top10 not worse, P5 TE preserved, P6 not one season, P7 leave-one-season-out,
P8 ordering intact, P9 not consensus-copying.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from alpha_squad.evaluation.projection_features import (
    PREREGISTERED_OVERALL_TIERS,
    PREREGISTERED_TARGET_SEASONS,
    PREREGISTERED_TIERS,
    SHIPPED_ROW_SPECIFICATION,
    ArmVerdict,
    TierRow,
    _spearman,
    evaluate_gates,
)
from alpha_squad.evaluation.projection_specification import (
    MIN_TRAIN_ROWS,
    POSITIONS,
    select_training_rows,
)
from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)

Arm = str

#: The shipped production seed. S0 must reproduce Y1 exactly.
PRODUCTION_SEED = 42

S_ARMS: tuple[Arm, ...] = ("S0", "S1", "S2", "S3")
PREREGISTERED_CONTROL: Arm = "S0"

#: Nested seed sets: every arm contains the production seed, so each is production PLUS seeds.
S_ARM_SEEDS: dict[Arm, tuple[int, ...]] = {
    "S0": (PRODUCTION_SEED,),
    "S1": tuple(range(PRODUCTION_SEED, PRODUCTION_SEED + 4)),
    "S2": tuple(range(PRODUCTION_SEED, PRODUCTION_SEED + 12)),
    "S3": tuple(range(PRODUCTION_SEED, PRODUCTION_SEED + 24)),
}

ARM_DESCRIPTIONS: dict[Arm, str] = {
    "S0": "control -- the shipped Y1 model, a single fit at seed 42",
    "S1": "mean of 4 fits (seeds 42-45)",
    "S2": "mean of 12 fits (seeds 42-53)",
    "S3": "mean of 24 fits (seeds 42-65)",
}


def seeds_for(arm: Arm) -> tuple[int, ...]:
    if arm not in S_ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    return S_ARM_SEEDS[arm]


def _new_model(seed: int) -> CatBoostRegressor:
    """M6's estimator, byte-identical to production apart from the seed, which is the only
    thing this phase varies."""
    return CatBoostRegressor(
        iterations=150,
        depth=3,
        learning_rate=0.08,
        loss_function="MAE",
        verbose=False,
        random_seed=seed,
    )


def _fit_predict(train: pd.DataFrame, target: pd.DataFrame, seeds: tuple[int, ...]) -> np.ndarray:
    """Arithmetic mean of the member fits' predictions, and the member spread."""
    xt = train[list(FEATURES)].to_numpy(dtype=float)
    yt = train[TARGET_COLUMN].to_numpy()
    xe = target[list(FEATURES)].to_numpy(dtype=float)
    members = [
        np.asarray(_new_model(seed).fit(xt, yt).predict(xe), dtype=float) for seed in seeds
    ]
    return np.vstack(members)


@dataclass
class EnsembleReport:
    tiers: list[TierRow] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)
    verdicts: list[ArmVerdict] = field(default_factory=list)
    selected: Arm | None = None

    def tier_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.tiers])

    def extras_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.extras)


def measure_arm_season(
    con: duckdb.DuckDBPyConnection, arm: Arm, season: int, min_train_season: int = 2015
) -> tuple[list[TierRow], dict]:
    rows: list[TierRow] = []
    extras: dict = {"arm": arm, "season": season}
    frames = []
    seeds = seeds_for(arm)

    for position in POSITIONS:
        data = load_season_level_data(con, position, min_train_season, season)
        if data.empty:
            continue
        target = data[data["target_season"] == season]
        train = select_training_rows(SHIPPED_ROW_SPECIFICATION, data, season)
        if target.empty or len(train) < MIN_TRAIN_ROWS:
            continue
        members = _fit_predict(train, target, seeds)
        pred = members.mean(axis=0)

        frame = target.copy()
        frame["predicted"] = pred
        frame["position"] = position
        frames.append(frame)

        actual = frame[TARGET_COLUMN].to_numpy()
        extras[f"pool_mae_{position}"] = float(np.abs(actual - pred).mean())
        extras[f"spearman_{position}"] = _spearman(pred, actual)
        extras[f"ecr_spearman_{position}"] = _spearman(
            pred, -frame["preseason_ecr_rank"].to_numpy()
        )
        # Sanity instrument, not a gate: the realised member spread, which should be ~unchanged
        # by averaging while the ensemble's own seed sensitivity falls.
        extras[f"member_sd_{position}"] = (
            float(members.std(axis=0, ddof=1).mean()) if len(seeds) > 1 else 0.0
        )

        ranked = frame.sort_values("preseason_ecr_rank").reset_index(drop=True)
        for label, lo, hi in PREREGISTERED_TIERS[position]:
            tier = ranked.iloc[lo - 1 : hi - 1]
            if tier.empty:
                continue
            a, p = tier[TARGET_COLUMN].to_numpy(), tier["predicted"].to_numpy()
            rows.append(TierRow(arm, season, position, label, len(tier),
                                float(np.abs(a - p).mean()),
                                float(np.sqrt(((a - p) ** 2).mean())),
                                float((a - p).mean())))

    if frames:
        board = pd.concat(frames, ignore_index=True)
        a, p = board[TARGET_COLUMN].to_numpy(), board["predicted"].to_numpy()
        extras["pool_mae_ALL"] = float(np.abs(a - p).mean())
        extras["rmse_ALL"] = float(np.sqrt(((a - p) ** 2).mean()))
        overall = board.sort_values("preseason_ecr_rank").reset_index(drop=True)
        for label, lo, hi in PREREGISTERED_OVERALL_TIERS:
            tier = overall.iloc[lo - 1 : hi - 1]
            if tier.empty:
                continue
            aa, pp = tier[TARGET_COLUMN].to_numpy(), tier["predicted"].to_numpy()
            rows.append(TierRow(arm, season, "ALL", label, len(tier),
                                float(np.abs(aa - pp).mean()),
                                float(np.sqrt(((aa - pp) ** 2).mean())),
                                float((aa - pp).mean())))
    return rows, extras


def run_ensemble_experiment(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...] = PREREGISTERED_TARGET_SEASONS,
    arms: tuple[Arm, ...] = S_ARMS,
) -> EnsembleReport:
    report = EnsembleReport()
    for arm in arms:
        for season in seasons:
            rows, extras = measure_arm_season(con, arm, season)
            report.tiers.extend(rows)
            report.extras.append(extras)
    tf, ef = report.tier_frame(), report.extras_frame()
    for arm in arms:
        if arm == PREREGISTERED_CONTROL:
            continue
        report.verdicts.append(evaluate_gates(tf, ef, arm, control=PREREGISTERED_CONTROL))
    # Smallest clearing ensemble wins: S_ARMS is ordered by seed count.
    for arm in arms:
        v = next((v for v in report.verdicts if v.arm == arm), None)
        if v is not None and v.passed:
            report.selected = arm
            break
    return report
