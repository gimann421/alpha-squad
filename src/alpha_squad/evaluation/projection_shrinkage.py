"""PRE-REGISTRATION — experiment N: is the elite-RB tail a *model-family* problem?

Committed BEFORE any arm is run. Arms, estimators, metrics, gates and the selection rule are
all fixed here; nothing in this module reads a result.

--------------------------------------------------------------------------------------------
Why this phase, given D79/D80/D82/D83
--------------------------------------------------------------------------------------------

Four phases have now attacked M6's elite-RB under-projection and none shipped:

* D79 phase 3 -- monotone constraints on the shipped tree. Fixed the inversions completely
  (18.0% -> 0.0%) and cost +3.20 pool MAE. Failed.
* D80 -- `l2_leaf_reg` shrinkage inside CatBoost, and XGBoost with/without constraints. Best
  RB-top10 gain was -1.04 against a 2.0-point floor. Failed.
* D82 -- more information (age, career, draft capital, prior volume, usage share). Three of
  five arms made the RB elite tail WORSE by +6.3 to +8.4 MAE. Failed.
* D83 -- seed ensembling. Confirmed the head is variance-limited (seed-to-seed prediction sd
  9.66 in the top-10 tier against 2.42 in the body) and still failed the effect-size floor.

Every one of those arms is a **gradient-boosted tree**, or a tree averaged with itself. D80's
own diagnosis says why that might be the binding constraint rather than a coincidence: a
depth-3 GBT is a step function that **cannot extrapolate**, and the top of the RB feature space
is sparse (22 of 1120 RB training rows above `prior_weighted_total` 300, from 14 distinct
players). A step function fitted on a sparse tail must flatten or invert there; that is what
step functions do. No amount of regularisation inside the family changes the family.

So this phase asks the question the previous four did not: **is a different functional form
better in the tail?** Three answers, each an arm:

  (i)  A model that extrapolates by construction (linear).
  (ii) A model that is monotone by construction but non-parametric (isotonic).
  (iii) A model that keeps the tree's flexibility in the body and borrows strength toward a
        pooled estimate in the sparse tail (shrinkage / partial pooling), or averages the two
        families (hybrid).

Registered in advance, because it is the honest prior: **(i) and (ii) are very likely to lose
pool-wide MAE.** A linear fit cannot represent the body of the distribution as well as a tree
does, and the gates below are pool-protective. The interesting outcome is not "linear wins" --
it is whether the tail behaviour of a linear or isotonic fit is materially better while the
body is materially worse, which would locate the problem precisely in the functional form and
point at the hybrid as the only viable shape. Also registered in advance: a hybrid winning on
RB top-10 while failing T2 (the 11-60 band) is a FAILURE, not a partial success.

--------------------------------------------------------------------------------------------
Arms
--------------------------------------------------------------------------------------------

N0  CONTROL -- the shipped Y1 CatBoost fit. Asserted to reproduce D80's `H0` exactly by a test,
    so this phase's control is provably the same control the previous phase used.

N1  Ordinary least squares on M6's four features, unchanged. The simplest estimator that can
    extrapolate. No hyperparameter.

N2  Isotonic regression on `prior_weighted_total` alone, constrained non-decreasing. Monotone
    by construction, non-parametric, and -- unlike D79 phase 3's tree constraint -- it does not
    require changing the loss function, so it carries no confound.

N3  SHRINKAGE. The shipped CatBoost prediction pulled toward the position's own walk-forward
    training mean, with the shrink weight per player set by how sparse that player's
    neighbourhood is: `w = k / (k + n_near)`, where `n_near` is the number of training rows
    within a fixed window of the player's `prior_weighted_total` and `k` is estimated by
    walk-forward MAE on seasons strictly before the target. This is textbook partial pooling:
    a prediction supported by three rows is shrunk hard, one supported by three hundred is
    barely moved. `k` is ESTIMATED, never assumed, and never from the target season.

N4  HYBRID, fixed 50/50: the mean of N0 and N1. The Occam blend, no free parameter.

N5  HYBRID, walk-forward weight: `alpha * N0 + (1 - alpha) * N1`, with `alpha` chosen on
    seasons strictly before the target by MAE. Registered as the arm most at risk of overfitting
    a four-point grid; it is included because a fixed 50/50 that fails is uninformative about
    whether any blend could work.

Every arm uses the shipped Y1 training rows and the same walk-forward split as D80, so a
difference is attributable to the estimator alone.

--------------------------------------------------------------------------------------------
Metrics, gates, selection
--------------------------------------------------------------------------------------------

Tiers, metrics and gates are IMPORTED from `evaluation/projection_topboard.py` (D80) rather
than restated, and a test asserts the imported objects are the same ones -- so a threshold
cannot silently drift between the two phases. That is D83's precedent (it imported D82's gates
for the same reason).

Gates, restated here for readability only -- `projection_topboard.evaluate_gates` is the
authority:

  T1  RB top10 MAE improves by >= 2.0 points
  T2  RB 11_24 and RB 25_60 each worsen by <= 1.0, and RB 11-60 combined does not worsen at all
  T3  QB, WR, TE pool MAE each worsen by <= 1.0
  T4  overall pool MAE worsens by <= 1.0
  T5  RB top10 improves in >= 3 of the 4 target seasons
  T6  the RB top10 improvement survives leave-one-season-out
  T7  within-RB Spearman against ECR does not exceed the control's by more than 0.05
  T8  RB top10 |signed bias| is not larger than the control's

SELECTION: the lowest-numbered arm clearing every gate ships. If none clears, NOTHING ships
and M6 stays byte-identical to Y1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LinearRegression

from alpha_squad.evaluation.projection_topboard import (
    MIN_TARGET_GAIN,
    PREREGISTERED_OVERALL_TIERS,
    PREREGISTERED_TARGET_SEASONS,
    PREREGISTERED_TIERS,
    TOLERANCE,
    _fit_predict,
)
from alpha_squad.models.established.season_level import FEATURES, TARGET_COLUMN

#: Arms in Occam/selection order. `N0` is the control.
N_ARMS: tuple[str, ...] = ("N0", "N1", "N2", "N3", "N4", "N5")
PREREGISTERED_CONTROL = "N0"

ARM_DESCRIPTIONS: dict[str, str] = {
    "N0": "control -- the shipped Y1 CatBoost fit, unchanged (identical to D80's H0)",
    "N1": "ordinary least squares on M6's four features",
    "N2": "isotonic regression on prior_weighted_total, non-decreasing",
    "N3": "shipped fit shrunk toward the training mean by local data density (partial pooling)",
    "N4": "hybrid: 0.5 * shipped + 0.5 * OLS",
    "N5": "hybrid with the blend weight chosen walk-forward by MAE",
}

#: N3's neighbourhood half-width, in `prior_weighted_total` points. Fixed in advance at a round
#: number rather than swept: it defines what "nearby training data" means, and sweeping it would
#: turn a structural choice into a second fitted parameter on the same four seasons.
NEIGHBOURHOOD_HALF_WIDTH = 40.0

#: N3's candidate shrink strengths and N5's candidate blend weights. Both are chosen on seasons
#: STRICTLY BEFORE the target season, never on the target season itself.
SHRINK_K_GRID: tuple[float, ...] = (2.0, 5.0, 10.0, 25.0, 50.0)
BLEND_ALPHA_GRID: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0)

# Re-exported so a caller reads this phase's thresholds from one place; they are the D80
# objects, not copies.
__all__ = [
    "ARM_DESCRIPTIONS",
    "BLEND_ALPHA_GRID",
    "MIN_TARGET_GAIN",
    "NEIGHBOURHOOD_HALF_WIDTH",
    "N_ARMS",
    "PREREGISTERED_CONTROL",
    "PREREGISTERED_OVERALL_TIERS",
    "PREREGISTERED_TARGET_SEASONS",
    "PREREGISTERED_TIERS",
    "SHRINK_K_GRID",
    "TOLERANCE",
    "shrinkage_predict",
]


def _ols(train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    model = LinearRegression()
    model.fit(train[FEATURES].to_numpy(), train[TARGET_COLUMN].to_numpy())
    return np.asarray(model.predict(target[FEATURES].to_numpy()), dtype=float)


def _isotonic(train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    model = IsotonicRegression(increasing=True, out_of_bounds="clip")
    model.fit(
        train["prior_weighted_total"].to_numpy(),
        train[TARGET_COLUMN].to_numpy(),
    )
    return np.asarray(model.predict(target["prior_weighted_total"].to_numpy()), dtype=float)


def local_density(
    train_values: np.ndarray, target_values: np.ndarray, half_width: float
) -> np.ndarray:
    """How many training rows sit within `half_width` of each target value.

    This is the quantity that makes N3 partial pooling rather than a flat blend: it is the
    per-player sample size behind that player's own prediction. On the real RB board it is in
    the hundreds through the body of the distribution and in the low single digits in the elite
    tail, which is exactly where D80 located the defect."""
    return np.array(
        [int(np.sum(np.abs(train_values - v) <= half_width)) for v in target_values],
        dtype=float,
    )


def shrinkage_predict(
    base: np.ndarray,
    pooled_mean: float,
    n_near: np.ndarray,
    k: float,
) -> np.ndarray:
    """`w * pooled_mean + (1 - w) * base` with `w = k / (k + n_near)`.

    The James-Stein shape: shrink in inverse proportion to the evidence behind the estimate.
    `k` is the number of "prior observations" the pooled mean is worth; at `n_near == k` the
    prediction is the midpoint."""
    w = k / (k + np.maximum(n_near, 0.0))
    return w * pooled_mean + (1.0 - w) * base


def _walk_forward_seasons(train: pd.DataFrame, target_season: int) -> list[int]:
    seasons = sorted({int(s) for s in train["target_season"].unique() if int(s) < target_season})
    return seasons[1:] if len(seasons) > 1 else seasons


def _choose_k(train: pd.DataFrame, position: str) -> float:
    """Pick `k` by MAE on the LAST season strictly before the target, fitting only on seasons
    before that. Never sees the target season."""
    seasons = _walk_forward_seasons(train, int(train["target_season"].max()) + 1)
    if not seasons:
        return SHRINK_K_GRID[len(SHRINK_K_GRID) // 2]
    holdout_season = seasons[-1]
    inner_train = train[train["target_season"] < holdout_season]
    holdout = train[train["target_season"] == holdout_season]
    if inner_train.empty or holdout.empty:
        return SHRINK_K_GRID[len(SHRINK_K_GRID) // 2]
    base = _fit_predict("H0", inner_train, holdout)
    n_near = local_density(
        inner_train["prior_weighted_total"].to_numpy(),
        holdout["prior_weighted_total"].to_numpy(),
        NEIGHBOURHOOD_HALF_WIDTH,
    )
    pooled = float(inner_train[TARGET_COLUMN].mean())
    actual = holdout[TARGET_COLUMN].to_numpy()
    best_k, best_mae = SHRINK_K_GRID[0], float("inf")
    for k in SHRINK_K_GRID:
        mae = float(np.abs(actual - shrinkage_predict(base, pooled, n_near, k)).mean())
        if mae < best_mae:
            best_k, best_mae = k, mae
    return best_k


def _choose_alpha(train: pd.DataFrame) -> float:
    seasons = _walk_forward_seasons(train, int(train["target_season"].max()) + 1)
    if not seasons:
        return 0.5
    holdout_season = seasons[-1]
    inner_train = train[train["target_season"] < holdout_season]
    holdout = train[train["target_season"] == holdout_season]
    if inner_train.empty or holdout.empty:
        return 0.5
    tree = _fit_predict("H0", inner_train, holdout)
    linear = _ols(inner_train, holdout)
    actual = holdout[TARGET_COLUMN].to_numpy()
    best_alpha, best_mae = BLEND_ALPHA_GRID[0], float("inf")
    for alpha in BLEND_ALPHA_GRID:
        mae = float(np.abs(actual - (alpha * tree + (1.0 - alpha) * linear)).mean())
        if mae < best_mae:
            best_alpha, best_mae = alpha, mae
    return best_alpha


def predict_arm(arm: str, train: pd.DataFrame, target: pd.DataFrame, position: str) -> np.ndarray:
    """The `PredictFn` this phase hands to `projection_topboard.measure_arm_season`.

    `N0` delegates to D80's `_fit_predict("H0", ...)` verbatim, so this phase's control is the
    same fit, produced by the same code, as the previous phase's."""
    if arm == "N0":
        return _fit_predict("H0", train, target)
    if arm == "N1":
        return _ols(train, target)
    if arm == "N2":
        return _isotonic(train, target)
    if arm == "N3":
        base = _fit_predict("H0", train, target)
        n_near = local_density(
            train["prior_weighted_total"].to_numpy(),
            target["prior_weighted_total"].to_numpy(),
            NEIGHBOURHOOD_HALF_WIDTH,
        )
        return shrinkage_predict(
            base, float(train[TARGET_COLUMN].mean()), n_near, _choose_k(train, position)
        )
    if arm == "N4":
        return 0.5 * _fit_predict("H0", train, target) + 0.5 * _ols(train, target)
    if arm == "N5":
        alpha = _choose_alpha(train)
        return alpha * _fit_predict("H0", train, target) + (1.0 - alpha) * _ols(train, target)
    raise ValueError(f"unknown arm {arm!r}; known: {N_ARMS}")
