"""Pre-registered walk-forward test of a MONOTONICITY CONSTRAINT on M6's estimator (D79).

**This module was committed to git before any arm was run against real data** -- the arms, the
constraint directions, the gates and the selection rule -- following the
D39/D54/D63/D66/D67/D68/D70/D78 discipline of fixing the decision rule before recording the
outcome. Its first pre-registered arm set was then VOIDED for an instrument defect before any
result was read as evidence; see "The voided C-arms" below. That is recorded here rather than
quietly replaced, for the same reason D56 and D61 label superseded numbers instead of restating
them.

Honesty note on the pre-registration, stated up front exactly as D78 did: the arms below were
motivated by a diagnostic that was run first (next section), so this is a diagnostic-informed
pre-registration, not a blind one. What it buys is the decision rule.

How this differs from D68 and D78, and why it is a third class of change
-----------------------------------------------------------------------
* **D68** changed the model's OUTPUT (`p' = p + b_pos` and relatives). Every arm carried a
  fitted per-position parameter; the sign-instability of that parameter is what killed them.
* **D78** changed WHICH ROWS the model trains on. No positional parameter, nothing tunable.
* **This phase** changes neither. It constrains the SHAPE OF THE FITTED FUNCTION, identically
  for every position, using directions fixed a priori and never estimated from data. There is
  no coefficient, no band, no shrinkage term and nothing that can be tuned toward a position.

The defect this phase targets
-----------------------------
Measured on the real 2026 board before this module existed. M6's estimator is a depth-3
gradient-boosted tree with MAE loss, fitted per position on four features. Trees cannot
extrapolate, and the top of the running-back feature space is very sparse: only **22 of 1120**
RB training rows carry `prior_weighted_total > 300`, and their realized outcomes run from 13.0
to 471.2 (mean 236.9), because that region holds both the elite repeats and the season-ending
injuries. The leaf covering it is fitted to a handful of high-variance points, and every player
above it falls into that same leaf.

The consequence is not "the expectation sits below the realized maximum" -- that is correct
behaviour, and it is what D78 concluded about the reported compression. It is that the fitted
function **inverts**: a strictly better input gets a lower projection. Partial dependence on the
real fitted 2026 RB model, sweeping one feature and holding the others at a real player's values:

    prior_weighted_total   150     250     300     320     340     360     380     420
    projection           227.9   232.2   221.5   209.2   180.6   169.2   169.2   169.2

    preseason_ecr_rank     1.0     2.5     5.0    10.0    20.0    40.0    80.0   150.0
    projection           138.1   169.2   231.7   224.2   225.7   221.0   213.2   192.2

Read the second row: a running back the market ranks **first overall** is projected 93.6 points
BELOW one it ranks fifth, holding everything else equal. On the live 2026 board that puts the
consensus RB1 -- 363 and 367 PPR points in the two prior seasons -- at projection 169.2 and board
rank **80**, and the consensus RB2 at rank 35.

Measured over the four evaluation seasons on the SHIPPED model, this is not an RB-only quirk:
13.7% of partial-dependence steps invert, and among the top 20 players by prior production at
each position-season, **272 of 2026 dominated pairs are ordered backwards** -- a pair where one
player is at least as good on every constrained feature, strictly better on one, and projected
lower. Worst single gap: 116.2 points (RB), 116.0 (WR), 79.6 (QB), 20.2 (TE).

Why a monotonicity constraint is the right instrument
-----------------------------------------------------
The three constrained features have directions that are unambiguous *before* looking at any
outcome, which is what makes this a structural rule and not a fitted correction:

* `prior_weighted_total` (+) -- more production last season cannot lower expected production.
* `prior_ppg` (+) -- likewise per game.
* `preseason_ecr_rank` (-) -- the rank is 1 = best, so a better consensus rank cannot lower it.

`prior_games` is deliberately left UNCONSTRAINED. Its direction is genuinely ambiguous -- 17
low-scoring games is a worse signal than 10 high-scoring ones -- and constraining a feature whose
direction is not known a priori is exactly the assumption this phase exists to avoid.

A constraint cannot manufacture optimism. Where the data really does fall at the top, the
constrained fit goes FLAT rather than rising; it can only refuse to invert. That is what makes it
safe to test against a compression complaint: it cannot inflate the top of the board.

The voided C-arms, and the trap that voided them
------------------------------------------------
The first pre-registered arm set (C0 control, C1/C2/C3 adding constraints to M6's estimator
unchanged) **could not be executed as specified**, and its numbers are void -- not disliked,
unmeasurable. **CatBoost cannot apply monotone constraints under M6's loss function at all.**

`loss_function="MAE"` requires `leaf_estimation_method="Exact"`, which is its default for that
loss, and CatBoost raises `"Monotone constraints are unsupported for Exact leaves estimation"`
for the combination. What it does when `leaf_estimation_method` is left unset is worse than
raising: it silently falls back to `Gradient`, and MAE-with-Gradient produces a **degenerate,
near-constant** fit. Measured on RB/2025: the shipped model scores MAE 43.94 with prediction
sd 69.9; the "constrained" one scores **MAE 74.96 with prediction sd 3.1**, every projection
falling in the range 49-57. The tell that this is the loss/method
interaction and not the constraint: `MAE + Gradient` is equally degenerate (75.01, sd 3.3) with
*no constraint at all*, and C1, C2 and C3 -- which constrain completely different features --
all returned the identical MAE, because all three had collapsed to the same constant.

Left unnoticed, that would have been reported as "monotone constraints are catastrophic
(+29 MAE)". It is the same class of defect D78 found in the paired-benchmark instrument, where
both arms silently scored identically and it looked like a null result. `_new_model` now raises
rather than allowing the combination, so the trap cannot be re-entered.

The corrected phase (E-arms)
----------------------------
Constraints are available under RMSE and Huber. Since the constraint therefore cannot be tested
without also changing the loss, the loss change is made an EXPLICIT, SEPARATE ARM rather than
being bundled -- otherwise a difference could not be attributed:

    E0  control: the shipped model -- MAE loss, unconstrained.
    E1  RMSE loss, unconstrained.        Isolates the LOSS change alone.
    E2  RMSE loss + all three constraints. Isolates the CONSTRAINT as E2 - E1.

The shipping decision is E2 versus E0 -- a candidate has to beat the model actually in
production, not merely its own unconstrained variant. E1 exists so the phase can report which
half of E2's difference is the loss and which is the constraint. D78 already measured RMSE loss
alone at +2.29 MAE versus MAE loss, so E2 starts from a known deficit that the constraint has to
overcome; that is stated here, before the run, so a failure is not later attributed to the
constraint when it belongs to the loss.

What is deliberately NOT tested here
------------------------------------
No capacity change, no new feature, no positional term, no output transform, and no change to
the training rows -- every arm draws its rows from the SHIPPED D78 specification
(`select_training_rows("Y1", ...)`), so E0 is the shipped model and a difference between arms is
attributable to the estimator and nothing else.

Leakage
-------
Row selection is delegated to `projection_specification.select_training_rows`, whose
`_assert_no_leakage` raises rather than warns. Nothing here touches the target season.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from alpha_squad.evaluation.projection_specification import (
    MIN_TRAIN_ROWS,
    POSITIONS,
    ArmMeasurement,
    ArmVerdict,
    evaluate_gates,
    select_training_rows,
)
from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)

Arm = str

#: M6's shipped loss. Named because the guard in `_new_model` is about this specific value.
SHIPPED_LOSS = "MAE"

#: Losses under which CatBoost 1.2 actually applies monotone constraints. `MAE` (and its
#: `Quantile:alpha=0.5` equivalent) is absent deliberately -- see the module docstring.
MONOTONE_CAPABLE_LOSSES: frozenset[str] = frozenset({"RMSE", "Huber"})

#: The three pre-registered arms. There is no fourth, and adding one after seeing results is a
#: protocol violation to be reported as a failed phase rather than patched around (D78's rule,
#: adopted verbatim). The voided C-arms are described in the module docstring and are
#: deliberately NOT runnable.
E_ARMS: tuple[Arm, ...] = ("E0", "E1", "E2")
PREREGISTERED_CONTROL: Arm = "E0"

#: The row selection every arm uses: the shipped D78 specification. Named rather than inlined so
#: the training set and the estimator cannot be changed in the same phase by accident.
SHIPPED_ROW_SPECIFICATION = "Y1"

#: A priori feature directions. +1 = the fitted function must be non-decreasing in this feature,
#: -1 = non-increasing, 0 = unconstrained. NOT estimated from data and not tunable: each entry is
#: a statement about what the feature means, and every one would have been written the same way
#: before any model was fitted.
MONOTONE_DIRECTIONS: dict[str, int] = {
    "prior_ppg": 1,
    "prior_games": 0,  # direction genuinely ambiguous -- see the module docstring
    "prior_weighted_total": 1,
    "preseason_ecr_rank": -1,  # rank 1 = best, so a better rank cannot lower the projection
}

#: {arm: (loss function, whether the three constraints are applied)}.
E_ARM_SPEC: dict[Arm, tuple[str, bool]] = {
    "E0": (SHIPPED_LOSS, False),  # the shipped model
    "E1": ("RMSE", False),  # the loss change alone
    "E2": ("RMSE", True),  # the loss change + the constraint
}

#: PRE-REGISTERED evaluation window, identical to D78's so the two phases are directly
#: comparable. Four target seasons x four positions = 16 paired observations.
PREREGISTERED_TARGET_SEASONS: tuple[int, ...] = (2022, 2023, 2024, 2025)


# --------------------------------------------------------------------------------------------
# PRE-REGISTERED GATES
#
# G1-G7 are D78's, REUSED VERBATIM by calling `projection_specification.evaluate_gates` with
# this phase's control rather than reimplementing them -- a second copy could silently diverge,
# and the gates are the part of a pre-registration that must not move:
#
#   G1  accuracy improves            mean paired dMAE < 0 AND mean paired dRMSE < 0
#   G2  not one season               mean dMAE < 0 in >= 3 of the 4 target seasons
#   G3  no position sacrificed       no position's 4-season mean MAE worse than control's
#   G4  ordering intact              mean dSpearman >= 0, no per-position drop > 0.01
#   G5  not noise                    paired two-sided t-test of dMAE, p < 0.05
#   G6  top-of-board not worse       no position's |top-decile signed bias| larger than control's
#   G7  robust to any one season     leave-one-season-out mean dMAE < 0 in all four folds
#
# SELECTION RULE: ship the LOWEST-NUMBERED arm clearing all seven gates (Occam, the project's
# standing rule since D63). If no arm clears them, NOTHING ships and M6 stays byte-identical.
#
# G1 is the gate this phase is most likely to fail, and that is stated in advance rather than
# discovered afterwards. The defect is concentrated in a handful of players at the very top of
# the board; MAE is averaged over ~150 players per position-season, most of them in a dense
# region no constraint can touch. A change that fixes the ordering of the top ten running backs
# and leaves everyone else alone SHOULD be nearly invisible in mean MAE -- and E2 additionally
# carries the RMSE loss's known +2.29 MAE deficit. It is still gated on mean MAE, because the
# alternative -- inventing a top-of-board metric now, after seeing which one the treatment would
# win -- is precisely the failure mode pre-registration exists to prevent.
#
# The monotonicity diagnostics below are REPORTED, NOT GATED. A constrained arm passes a
# monotonicity check by construction, so gating on one would be circular; the numbers exist to
# quantify the control's defect and to confirm the constraint does what it claims.
#
# The uncertainty layer is checked SEPARATELY and is not a gate here: `run_uncertainty`'s
# conformal residuals are fitted on a model that never saw the calibration season, and a shipped
# arm must be re-measured for interval coverage against `calibration_diagnostics` before it is
# called done.
# --------------------------------------------------------------------------------------------


def monotone_constraints_for(arm: Arm) -> list[int]:
    """CatBoost's per-feature constraint vector, in `FEATURES` order."""
    if arm not in E_ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    _loss, constrained = E_ARM_SPEC[arm]
    return [MONOTONE_DIRECTIONS[f] if constrained else 0 for f in FEATURES]


def _new_model(arm: Arm) -> CatBoostRegressor:
    """M6's estimator with only the loss and the constraint vector varying.

    Raises on `MAE` + constraints rather than letting CatBoost silently fall back from its
    `Exact` leaf-estimation method to `Gradient`, which produces a near-constant model. That
    fallback is the defect that voided this phase's first arm set; making it an exception is
    what stops the same broken measurement from being taken twice."""
    loss, constrained = E_ARM_SPEC[arm]
    if constrained and loss.split(":")[0] not in MONOTONE_CAPABLE_LOSSES:
        raise ValueError(
            f"arm {arm!r} asks for monotone constraints under loss {loss!r}. CatBoost applies "
            "them only under "
            f"{sorted(MONOTONE_CAPABLE_LOSSES)}; under MAE it silently switches leaf estimation "
            "from Exact to Gradient and fits a near-constant model (measured: prediction sd 3.1 "
            "against the shipped model's 69.9). See this module's docstring."
        )
    kwargs: dict = {
        "iterations": 150,
        "depth": 3,
        "learning_rate": 0.08,
        "loss_function": loss,
        "verbose": False,
        "random_seed": 42,
    }
    if constrained:
        kwargs["monotone_constraints"] = monotone_constraints_for(arm)
    return CatBoostRegressor(**kwargs)


def _fit_predict(arm: Arm, train: pd.DataFrame, target: pd.DataFrame) -> tuple:
    model = _new_model(arm)
    model.fit(train[FEATURES].to_numpy(), train[TARGET_COLUMN].to_numpy())
    return model, np.asarray(model.predict(target[FEATURES].to_numpy()), dtype=float)


#: Quantiles of the TRAINING distribution at which partial dependence is evaluated -- a grid in
#: quantile space rather than raw units, so the same code is meaningful for a 300-point feature
#: and for a 1-to-999 rank.
_PD_QUANTILES: tuple[float, ...] = (0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0)


def partial_dependence_inversions(
    model, train: pd.DataFrame, feature: str, *, base: np.ndarray | None = None
) -> tuple[int, int]:
    """(inversions, comparisons) for `feature` on the fitted `model`.

    Sweeps `feature` across `_PD_QUANTILES` of its training distribution, holding every other
    feature at the training median, and counts adjacent steps where the projection moves in the
    direction `MONOTONE_DIRECTIONS` says it must not. An unconstrained model can score > 0 here;
    a constrained one cannot, by construction."""
    direction = MONOTONE_DIRECTIONS[feature]
    if direction == 0:
        return 0, 0
    idx = FEATURES.index(feature)
    if base is None:
        base = train[FEATURES].median().to_numpy(dtype=float).reshape(1, -1)
    grid = [float(train[feature].quantile(q)) for q in _PD_QUANTILES]
    preds = []
    for value in grid:
        row = base.copy()
        row[0, idx] = value
        preds.append(float(model.predict(row)[0]))
    inversions = 0
    comparisons = 0
    for i in range(1, len(preds)):
        if grid[i] <= grid[i - 1]:
            continue  # duplicate quantile value; nothing to compare
        comparisons += 1
        # `direction * movement` is the movement in the direction the feature should push, so
        # one comparison covers both signs without an `elif` that hides the symmetry.
        if direction * (preds[i] - preds[i - 1]) < -1e-9:
            inversions += 1
    return inversions, comparisons


def dominated_pairs(predicted: np.ndarray, target: pd.DataFrame, top_n: int = 20) -> tuple:
    """(dominated pairs, comparisons, worst gap) among the `top_n` players by prior production.

    A pair (i, j) is DOMINATED when i is at least as good as j on every constrained feature and
    strictly better on one, yet is projected LOWER. This is the partial-dependence check's
    real-board counterpart: it uses actual player rows rather than a synthetic grid, so a nonzero
    count names a comparison a user could see on the board -- the reported 2026 case is exactly
    one of these."""
    if len(target) < 2:
        return 0, 0, 0.0
    frame = target.copy()
    frame["_pred"] = predicted
    frame = frame.sort_values("prior_weighted_total", ascending=False).head(top_n)
    rows = frame.to_dict("records")
    dominated = 0
    comparisons = 0
    worst = 0.0
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            better_or_equal = (
                a["prior_weighted_total"] >= b["prior_weighted_total"]
                and a["prior_ppg"] >= b["prior_ppg"]
                and a["preseason_ecr_rank"] <= b["preseason_ecr_rank"]
            )
            strictly_better = (
                a["prior_weighted_total"] > b["prior_weighted_total"]
                or a["prior_ppg"] > b["prior_ppg"]
                or a["preseason_ecr_rank"] < b["preseason_ecr_rank"]
            )
            if not (better_or_equal and strictly_better):
                continue
            comparisons += 1
            gap = b["_pred"] - a["_pred"]
            if gap > 1e-9:
                dominated += 1
                worst = max(worst, gap)
    return dominated, comparisons, worst


@dataclass(frozen=True)
class MonotonicityMeasurement:
    """`ArmMeasurement`'s fields plus this phase's own diagnostics."""

    measurement: ArmMeasurement
    pd_inversions: int
    pd_comparisons: int
    dominated: int
    dominated_comparisons: int
    worst_dominated_gap: float


def measure_arm(
    con: duckdb.DuckDBPyConnection,
    arm: Arm,
    season: int,
    position: str,
    min_train_season: int = 2015,
) -> MonotonicityMeasurement | None:
    """One (arm, season, position) walk-forward measurement, or None if M6 itself would skip.

    Training rows are the SHIPPED specification for every arm -- see `SHIPPED_ROW_SPECIFICATION`.
    """
    all_data = load_season_level_data(con, position, min_train_season, season)
    target = all_data[all_data["target_season"] == season]
    train = select_training_rows(SHIPPED_ROW_SPECIFICATION, all_data, season)
    if target.empty or len(train) < MIN_TRAIN_ROWS:
        return None

    model, predicted = _fit_predict(arm, train, target)
    actual = target[TARGET_COLUMN].to_numpy()

    order = np.argsort(-predicted)
    k = max(1, int(round(0.10 * len(predicted))))
    top = order[:k]

    inversions = comparisons = 0
    for feature, direction in MONOTONE_DIRECTIONS.items():
        if direction == 0:
            continue
        inv, cmp_ = partial_dependence_inversions(model, train, feature)
        inversions += inv
        comparisons += cmp_
    dom, dom_cmp, worst = dominated_pairs(predicted, target)

    return MonotonicityMeasurement(
        measurement=ArmMeasurement(
            arm=arm,
            season=season,
            position=position,
            n=len(actual),
            n_train=len(train),
            n_train_seasons=int(train["target_season"].nunique()),
            mae=float(np.abs(actual - predicted).mean()),
            rmse=float(np.sqrt(((actual - predicted) ** 2).mean())),
            spearman=float(pd.Series(predicted).corr(pd.Series(actual), method="spearman")),
            bias=float((actual - predicted).mean()),
            top_decile_bias=float((actual[top] - predicted[top]).mean()),
            max_projection=float(predicted.max()),
            fell_back=False,
        ),
        pd_inversions=inversions,
        pd_comparisons=comparisons,
        dominated=dom,
        dominated_comparisons=dom_cmp,
        worst_dominated_gap=worst,
    )


@dataclass
class MonotonicityReport:
    measurements: list[MonotonicityMeasurement] = field(default_factory=list)
    verdicts: list[ArmVerdict] = field(default_factory=list)
    selected: Arm | None = None

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([m.measurement.__dict__ for m in self.measurements])

    def diagnostics_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "arm": m.measurement.arm,
                    "season": m.measurement.season,
                    "position": m.measurement.position,
                    "pd_inversions": m.pd_inversions,
                    "pd_comparisons": m.pd_comparisons,
                    "dominated": m.dominated,
                    "dominated_comparisons": m.dominated_comparisons,
                    "worst_dominated_gap": m.worst_dominated_gap,
                }
                for m in self.measurements
            ]
        )


def run_monotonicity_experiment(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...] = PREREGISTERED_TARGET_SEASONS,
    positions: tuple[str, ...] = POSITIONS,
    arms: tuple[Arm, ...] = E_ARMS,
) -> MonotonicityReport:
    """Run every (arm, season, position) cell and apply the pre-registered gates."""
    report = MonotonicityReport()
    for arm in arms:
        for season in seasons:
            for position in positions:
                m = measure_arm(con, arm, season, position)
                if m is not None:
                    report.measurements.append(m)

    frame = report.frame()
    for arm in arms:
        if arm == PREREGISTERED_CONTROL:
            continue
        report.verdicts.append(evaluate_gates(frame, arm, PREREGISTERED_CONTROL))

    for arm in arms:  # E_ARMS is already in Occam order
        verdict = next((v for v in report.verdicts if v.arm == arm), None)
        if verdict is not None and verdict.passed:
            report.selected = arm
            break
    return report


ARM_DESCRIPTIONS: dict[Arm, str] = {
    "E0": "control -- the shipped model: Y1 training rows, MAE loss, unconstrained",
    "E1": "RMSE loss, unconstrained -- isolates the loss change alone",
    "E2": "RMSE loss + monotone in prior_ppg, prior_weighted_total and preseason_ecr_rank",
}
