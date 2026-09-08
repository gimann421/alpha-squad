"""Pre-registered walk-forward test of M6's ELITE-TAIL behaviour, judged on TOP-OF-BOARD
metrics rather than pool-wide MAE (docs/DECISIONS.md D80).

**This module was committed to git before any arm was run against real data** -- the arms, the
tier definitions, the metrics, the gates and the selection rule. D39/D54/D63/D66/D67/D68/D70/D78
discipline. As D78 did, this is a *diagnostic-informed* pre-registration and says so: the arms
were chosen from a diagnosis run first (below). What the pre-registration buys is the decision
rule, fixed before the numbers exist.

Why this phase exists, and what D79 phase 3 got wrong about it
--------------------------------------------------------------
D79 phase 3 gated a monotonicity constraint on pool-wide mean MAE over ~150 players per
position-season, and it failed. That gate was a genuine methodological mismatch: the behaviour
under test lives in the ten or twenty players a draft actually consumes, and pool-wide MAE
averages it away. This phase fixes the mismatch by pre-registering tiered, draft-relevant
metrics FIRST -- before any candidate is scored -- so the choice of metric cannot be made after
seeing which arm it would favour.

THE DIAGNOSIS (run before this module existed; all figures from real 2015-2025 data)
------------------------------------------------------------------------------------
The elite RB projection is governed by an n=3 sample in the extreme tail of one feature.

Sorted by `prior_weighted_total`, the RB rows the 2026 model trains on end like this:

    player                 prior_weighted_total   ECR    realized   model (in-sample)
    Jonathan Taylor 2022          331.0           2.05      146.4        174.9
    Alvin Kamara    2021          332.6           3.39      234.7        234.7
    Austin Ekeler   2023          362.6           7.50      185.4        186.9
    C. McCaffrey    2024          379.1           1.81       47.8        117.8
    C. McCaffrey    2020          441.2           1.00       90.4        109.1

**The only three RBs in the training window who entered a season with >=360 weighted prior
production scored 185.4, 47.8 and 90.4.** Jahmyr Gibbs's 2026 row carries 365.5 -- between
Ekeler 2023 and McCaffrey 2024 -- so the model prices him at 170.7. One-at-a-time perturbation
of his row confirms the feature responsible:

    prior_weighted_total  200->265  250->255  300->262  330->245  365.5->171  400->171
    preseason_ecr_rank      1->142   2.48->171   5->204    8->196    12->197    40->189

Three things follow, and they matter for how this phase is framed:

1. **It is not a bug.** The model fits its own elite cell well in-sample: for the 12 RB rows
   with ECR<=12 AND prior>=300 it predicts mean 216.5 against a realized mean of 210.3. It is
   faithfully reproducing what the data says.
2. **It is not a CatBoost artifact.** An independent XGBoost fit on the same rows learns the
   same non-monotone ECR shape (peak at ECR~5, lower at ECR 1). Two implementations agreeing
   means the relationship is in the data, not the estimator.
3. **It rests on n=3.** A 90-point cliff supported by three observations is the textbook case
   for shrinkage. The football story behind it (attrition after a monster workload season) is
   real, but three rows cannot establish its size.

So the question this phase asks is narrow and answerable: **should a 90-point cliff supported by
three rows be believed as-is, shrunk, or overridden by an a-priori direction?** Each answer is an
arm.

The ECR band means that produce the second inversion are the same story at n=13:

    RB training rows   ECR [1,5): n=13, mean 227.8, sd 135.6   <- 5 of 13 are injury seasons,
                       ECR [5,12): n=17, mean 263.8, sd  74.5      4 of 13 are one player
    WR training rows   ECR [1,5): n= 9, mean 229.2
                       ECR [5,12): n=22, mean 277.4

The elite-band difference is 36.0 points with a standard error of ~41.7 (t=0.86). It is noise.

WHAT WAS RULED OUT FIRST, so this phase does not re-test it
-----------------------------------------------------------
* **ECR feature contamination.** `load_season_level_data` joins `ecr_type='ro'` with no
  `page_type` filter, and D56 established that `ro` labels two independently-ranked pages
  (redraft-overall and redraft-idp). Measured: across 2022-2026 x QB/RB/WR/TE, **zero** model
  rows draw their rank from the IDP page (the two pages' player sets are disjoint for offensive
  skill players). The omission is a latent hazard, not an active defect, and fixing it changes
  no projection. Not pursued here.
* **`min_data_in_leaf`.** Inert under CatBoost's default symmetric-tree grow policy -- byte-
  identical output at 10/20/30/50/80. Cannot be an arm.
* **Feature transforms of ECR** (log-rank etc.). CatBoost bins by quantile, so it is invariant
  to any monotone transform of a feature. Cannot change anything.
* **Deeper trees.** depth 4 and 5 both measured worse pool MAE in feasibility (45.03, 45.73 vs
  43.94 on RB/2025). Not carried as an arm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from xgboost import XGBRegressor

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

#: The five pre-registered arms. There is no sixth, and adding one after seeing results is a
#: protocol violation to be reported as a failed phase rather than patched around (D78's rule).
#:
#:   H0  control: the shipped Y1 model, unchanged.
#:   H1  shrinkage, l2_leaf_reg 3 -> 10.
#:   H2  shrinkage, l2_leaf_reg 3 -> 30.
#:   H3  XGBoost, SAME MAE loss, unconstrained  -- the library control for H4.
#:   H4  XGBoost, SAME MAE loss, monotone in prior production and ECR.
#:
#: H3 exists so H4 is attributable. D79 phase 3 could only test monotonicity by also switching
#: CatBoost's loss to RMSE, which confounded the constraint with a +2.62 MAE loss penalty and
#: made the result uninterpretable. XGBoost applies monotone constraints under
#: `reg:absoluteerror`, so H4 - H3 isolates the constraint at the SHIPPED loss, and H4 - H0 is
#: the shipping comparison.
H_ARMS: tuple[Arm, ...] = ("H0", "H1", "H2", "H3", "H4")
PREREGISTERED_CONTROL: Arm = "H0"

#: Row selection is the SHIPPED D78 specification for every arm, so the training set never
#: varies and a difference is attributable to the estimator alone.
SHIPPED_ROW_SPECIFICATION = "Y1"

#: A priori directions, identical to D79 phase 3's and for the same reason: each is a statement
#: about what the feature means, none is estimated. `prior_games` stays unconstrained because
#: its direction is genuinely ambiguous.
MONOTONE_DIRECTIONS: dict[str, int] = {
    "prior_ppg": 1,
    "prior_games": 0,
    "prior_weighted_total": 1,
    "preseason_ecr_rank": -1,
}

#: {arm: (library, l2_leaf_reg or None, monotone)}
H_ARM_SPEC: dict[Arm, tuple[str, float | None, bool]] = {
    "H0": ("catboost", None, False),
    "H1": ("catboost", 10.0, False),
    "H2": ("catboost", 30.0, False),
    "H3": ("xgboost", None, False),
    "H4": ("xgboost", None, True),
}

#: PRE-REGISTERED evaluation window, identical to D78/D79 so the phases are comparable.
PREREGISTERED_TARGET_SEASONS: tuple[int, ...] = (2022, 2023, 2024, 2025)

# --------------------------------------------------------------------------------------------
# PRE-REGISTERED TIER DEFINITIONS
#
# Tiers are cut by **preseason ECR rank within position**, NOT by predicted rank. That is the
# load-bearing methodological choice of this phase:
#
#   * ECR is EXOGENOUS to every arm, so all five arms are scored on the IDENTICAL set of
#     players in each tier and the comparison is genuinely paired. Cutting by predicted rank
#     would let each arm choose its own top ten and turn the metric into a selection effect.
#   * ECR is available before the draft, which is what makes the tier draft-relevant rather
#     than a hindsight construct.
#
# Players carrying the missing-ECR sentinel (999) sort last and therefore land in the deep tiers
# or outside them entirely, which is correct: a player with no market opinion is not a
# top-of-board player.
#
# A hindsight tier (by REALIZED points) is also computed and REPORTED, because "did we
# under-project the players who actually mattered" is a fair question -- but it is not gated,
# because it is not knowable at draft time and gating on it would reward hindsight.
# --------------------------------------------------------------------------------------------

#: {position: ((label, lo, hi), ...)} with 1-based, inclusive-exclusive ECR-rank-within-position
#: bounds. The user's stated draft-relevant tiers.
PREREGISTERED_TIERS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "RB": (("top10", 1, 11), ("11_24", 11, 25), ("25_60", 25, 61)),
    "WR": (("top10", 1, 11), ("11_24", 11, 25), ("25_60", 25, 61)),
    "QB": (("top10", 1, 11), ("11_24", 11, 25), ("25plus", 25, 10_000)),
    "TE": (("all", 1, 10_000),),
}

#: Overall (cross-position) tiers, cut by ECR rank across the whole board.
PREREGISTERED_OVERALL_TIERS: tuple[tuple[str, int, int], ...] = (
    ("top12", 1, 13),
    ("top24", 1, 25),
    ("top50", 1, 51),
    ("top100", 1, 101),
)

# --------------------------------------------------------------------------------------------
# PRE-REGISTERED GATES
#
# The user's hard acceptance requirement, stated as arithmetic. All deltas are
# (arm - control), pooled over the four target seasons, so NEGATIVE MAE deltas are improvements.
#
#   T1  TARGET IMPROVES        RB top10 MAE improves by at least MIN_TARGET_GAIN (2.0 pts).
#   T2  NO MID-TIER DAMAGE     RB 11_24 MAE worsens by at most TOLERANCE (1.0 pt), AND
#                              RB 25_60 MAE worsens by at most TOLERANCE, AND
#                              the combined RB 11-60 MAE does not worsen AT ALL.
#                              This is the user's "do not trade 11-60 accuracy for the top 10".
#   T3  NO OTHER POSITION      QB, WR and TE pool MAE each worsen by at most TOLERANCE.
#   T4  NO POOL DAMAGE         Overall pool MAE worsens by at most TOLERANCE.
#   T5  NOT ONE SEASON         RB top10 MAE improves in at least 3 of the 4 target seasons.
#   T6  LEAVE-ONE-SEASON-OUT   RB top10 improvement survives dropping any single season.
#   T7  NOT CONSENSUS-COPYING  within-RB Spearman(prediction, ECR) must not exceed the
#                              control's by more than MAX_ECR_SPEARMAN_GAIN (0.05). An arm that
#                              wins by reproducing the market's ordering is not a model
#                              improvement -- it is a slower way to read FantasyPros.
#   T8  TOP-END BIAS           RB top10 |signed bias| must not be larger than the control's.
#
# SELECTION RULE: ship the LOWEST-NUMBERED arm clearing every gate (Occam, standing since D63).
# If no arm clears them, NOTHING ships and M6 stays byte-identical to Y1.
#
# Stated before the run so it cannot be reinterpreted afterwards:
#   * T1's 2.0-point threshold is a REAL-EFFECT floor, not a significance test. RB top10 is ~40
#     player-seasons pooled; a sub-2-point move there is not distinguishable from fit noise.
#   * T2 is the gate most likely to kill an arm, and it is meant to. Every mechanism here works
#     by damping the elite tail, and the same damping necessarily touches the players just below
#     it. An arm that buys the top ten with the next fifty is explicitly disqualified.
#   * T7 is aimed at H4 in particular. Forcing monotonicity in ECR pushes the model toward the
#     market's ordering by construction, and "agrees with consensus" is not the objective.
#   * It is a fully acceptable outcome for this phase to ship nothing. The n=3 cliff may simply
#     be the best available estimate, and "believe it" is a legitimate answer.
# --------------------------------------------------------------------------------------------

MIN_TARGET_GAIN = 2.0
TOLERANCE = 1.0
MAX_ECR_SPEARMAN_GAIN = 0.05
PREREGISTERED_MIN_BETTER_SEASONS = 3


def _new_model(arm: Arm):
    """M6's estimator, varying ONLY what the arm specifies.

    The control passes no extra parameter at all, so H0 is bit-for-bit the shipped fit rather
    than 'the shipped fit with a default restated'."""
    if arm not in H_ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    library, l2, monotone = H_ARM_SPEC[arm]
    if library == "catboost":
        kwargs: dict = {
            "iterations": 150,
            "depth": 3,
            "learning_rate": 0.08,
            "loss_function": "MAE",
            "verbose": False,
            "random_seed": 42,
        }
        if l2 is not None:
            kwargs["l2_leaf_reg"] = l2
        return CatBoostRegressor(**kwargs)
    # XGBoost, matched to M6's hyperparameters and to its MAE loss (`reg:absoluteerror`), so the
    # only thing H4 adds over H3 is the constraint.
    kwargs = {
        "n_estimators": 150,
        "max_depth": 3,
        "learning_rate": 0.08,
        "random_state": 42,
        "objective": "reg:absoluteerror",
    }
    if monotone:
        kwargs["monotone_constraints"] = tuple(MONOTONE_DIRECTIONS[f] for f in FEATURES)
    return XGBRegressor(**kwargs)


def _fit_predict(arm: Arm, train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    model = _new_model(arm)
    model.fit(train[FEATURES].to_numpy(), train[TARGET_COLUMN].to_numpy())
    return np.asarray(model.predict(target[FEATURES].to_numpy()), dtype=float)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    return float(pd.Series(a).corr(pd.Series(b), method="spearman"))


@dataclass(frozen=True)
class TierMeasurement:
    arm: Arm
    season: int
    position: str
    tier: str
    n: int
    mae: float
    rmse: float
    bias: float  # mean(actual - predicted); negative = the model over-projects this tier
    spearman: float


def measure_arm_season(
    con: duckdb.DuckDBPyConnection,
    arm: Arm,
    season: int,
    min_train_season: int = 2015,
) -> tuple[list[TierMeasurement], dict[str, float]]:
    """All tier measurements for one (arm, season), plus per-position diagnostics.

    One fit per position, exactly as production does -- see `run_uncertainty`, which loops
    positions and trains a separate model for each with identical hyperparameters."""
    rows: list[TierMeasurement] = []
    extras: dict[str, float] = {}
    frames: list[pd.DataFrame] = []

    for position in POSITIONS:
        all_data = load_season_level_data(con, position, min_train_season, season)
        target = all_data[all_data["target_season"] == season]
        train = select_training_rows(SHIPPED_ROW_SPECIFICATION, all_data, season)
        if target.empty or len(train) < MIN_TRAIN_ROWS:
            continue
        predicted = _fit_predict(arm, train, target)
        frame = target.copy()
        frame["predicted"] = predicted
        frame["position"] = position
        frames.append(frame)

        # whole-position pool metrics (T3's input)
        actual = frame[TARGET_COLUMN].to_numpy()
        extras[f"pool_mae_{position}"] = float(np.abs(actual - predicted).mean())
        extras[f"ecr_spearman_{position}"] = _spearman(
            predicted, -frame["preseason_ecr_rank"].to_numpy()
        )

        ranked = frame.sort_values("preseason_ecr_rank").reset_index(drop=True)
        for label, lo, hi in PREREGISTERED_TIERS[position]:
            tier = ranked.iloc[lo - 1 : hi - 1]
            if tier.empty:
                continue
            a = tier[TARGET_COLUMN].to_numpy()
            p = tier["predicted"].to_numpy()
            rows.append(
                TierMeasurement(
                    arm=arm,
                    season=season,
                    position=position,
                    tier=label,
                    n=len(tier),
                    mae=float(np.abs(a - p).mean()),
                    rmse=float(np.sqrt(((a - p) ** 2).mean())),
                    bias=float((a - p).mean()),
                    spearman=_spearman(p, a),
                )
            )
        # the user's RB/WR "11-60 combined" non-degradation check
        combined = ranked.iloc[10:60]
        if not combined.empty:
            a = combined[TARGET_COLUMN].to_numpy()
            p = combined["predicted"].to_numpy()
            rows.append(
                TierMeasurement(
                    arm,
                    season,
                    position,
                    "11_60",
                    len(combined),
                    float(np.abs(a - p).mean()),
                    float(np.sqrt(((a - p) ** 2).mean())),
                    float((a - p).mean()),
                    _spearman(p, a),
                )
            )

    if frames:
        board = pd.concat(frames, ignore_index=True)
        actual = board[TARGET_COLUMN].to_numpy()
        pred = board["predicted"].to_numpy()
        extras["pool_mae_ALL"] = float(np.abs(actual - pred).mean())
        overall = board.sort_values("preseason_ecr_rank").reset_index(drop=True)
        for label, lo, hi in PREREGISTERED_OVERALL_TIERS:
            tier = overall.iloc[lo - 1 : hi - 1]
            if tier.empty:
                continue
            a = tier[TARGET_COLUMN].to_numpy()
            p = tier["predicted"].to_numpy()
            rows.append(
                TierMeasurement(
                    arm,
                    season,
                    "ALL",
                    label,
                    len(tier),
                    float(np.abs(a - p).mean()),
                    float(np.sqrt(((a - p) ** 2).mean())),
                    float((a - p).mean()),
                    _spearman(p, a),
                )
            )
    return rows, extras


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ArmVerdict:
    arm: Arm
    gates: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)


@dataclass
class TopBoardReport:
    tiers: list[TierMeasurement] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)
    verdicts: list[ArmVerdict] = field(default_factory=list)
    selected: Arm | None = None

    def tier_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.tiers])

    def extras_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.extras)


def _tier_mae(frame: pd.DataFrame, arm: Arm, position: str, tier: str) -> float:
    sel = frame[(frame.arm == arm) & (frame.position == position) & (frame.tier == tier)]
    return float(sel["mae"].mean()) if not sel.empty else float("nan")


def _tier_bias(frame: pd.DataFrame, arm: Arm, position: str, tier: str) -> float:
    sel = frame[(frame.arm == arm) & (frame.position == position) & (frame.tier == tier)]
    return float(sel["bias"].mean()) if not sel.empty else float("nan")


def evaluate_gates(
    tiers: pd.DataFrame, extras: pd.DataFrame, arm: Arm, control: Arm = PREREGISTERED_CONTROL
) -> ArmVerdict:
    """Apply T1-T8 mechanically. The rule is the module constants, fixed before any run."""
    verdict = ArmVerdict(arm=arm)
    if arm == control:
        return verdict

    d_top = _tier_mae(tiers, arm, "RB", "top10") - _tier_mae(tiers, control, "RB", "top10")
    verdict.gates.append(
        GateResult(
            "T1 RB top10 improves",
            bool(d_top <= -MIN_TARGET_GAIN),
            f"dMAE {d_top:+.2f} (needs <= {-MIN_TARGET_GAIN:+.1f})",
        )
    )

    d_mid = _tier_mae(tiers, arm, "RB", "11_24") - _tier_mae(tiers, control, "RB", "11_24")
    d_deep = _tier_mae(tiers, arm, "RB", "25_60") - _tier_mae(tiers, control, "RB", "25_60")
    d_comb = _tier_mae(tiers, arm, "RB", "11_60") - _tier_mae(tiers, control, "RB", "11_60")
    verdict.gates.append(
        GateResult(
            "T2 RB 11-60 not damaged",
            bool(d_mid <= TOLERANCE and d_deep <= TOLERANCE and d_comb <= 0.0),
            f"11_24 {d_mid:+.2f}, 25_60 {d_deep:+.2f}, combined 11_60 {d_comb:+.2f} "
            f"(needs <= +{TOLERANCE:.1f}, <= +{TOLERANCE:.1f}, <= 0)",
        )
    )

    others = {}
    for position in ("QB", "WR", "TE"):
        col = f"pool_mae_{position}"
        if col in extras.columns:
            a = float(extras[extras.arm == arm][col].mean())
            c = float(extras[extras.arm == control][col].mean())
            others[position] = a - c
    verdict.gates.append(
        GateResult(
            "T3 other positions intact",
            all(v <= TOLERANCE for v in others.values()),
            ", ".join(f"{k} {v:+.2f}" for k, v in others.items()),
        )
    )

    d_pool = float(extras[extras.arm == arm]["pool_mae_ALL"].mean()) - float(
        extras[extras.arm == control]["pool_mae_ALL"].mean()
    )
    verdict.gates.append(
        GateResult("T4 pool not damaged", bool(d_pool <= TOLERANCE), f"pool dMAE {d_pool:+.2f}")
    )

    per_season = {}
    for season in sorted(tiers.season.unique()):
        s = tiers[tiers.season == season]
        per_season[int(season)] = _tier_mae(s, arm, "RB", "top10") - _tier_mae(
            s, control, "RB", "top10"
        )
    better = sum(1 for v in per_season.values() if v < 0)
    verdict.gates.append(
        GateResult(
            "T5 not one season",
            better >= PREREGISTERED_MIN_BETTER_SEASONS,
            f"{better}/{len(per_season)} better: "
            + ", ".join(f"{s}:{v:+.1f}" for s, v in per_season.items()),
        )
    )

    loso = {}
    for held in sorted(tiers.season.unique()):
        kept = tiers[tiers.season != held]
        loso[int(held)] = _tier_mae(kept, arm, "RB", "top10") - _tier_mae(
            kept, control, "RB", "top10"
        )
    verdict.gates.append(
        GateResult(
            "T6 leave-one-season-out",
            all(v <= -MIN_TARGET_GAIN for v in loso.values()),
            ", ".join(f"drop {s}:{v:+.1f}" for s, v in loso.items()),
        )
    )

    a_sp = float(extras[extras.arm == arm]["ecr_spearman_RB"].mean())
    c_sp = float(extras[extras.arm == control]["ecr_spearman_RB"].mean())
    verdict.gates.append(
        GateResult(
            "T7 not consensus-copying",
            bool(a_sp - c_sp <= MAX_ECR_SPEARMAN_GAIN),
            f"RB Spearman(pred, -ECR) {c_sp:.3f} -> {a_sp:.3f} ({a_sp - c_sp:+.3f})",
        )
    )

    a_b = abs(_tier_bias(tiers, arm, "RB", "top10"))
    c_b = abs(_tier_bias(tiers, control, "RB", "top10"))
    verdict.gates.append(
        GateResult(
            "T8 RB top10 bias not worse",
            bool(a_b <= c_b + 1e-9),
            f"|bias| {c_b:.1f} -> {a_b:.1f}",
        )
    )
    return verdict


def run_topboard_experiment(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...] = PREREGISTERED_TARGET_SEASONS,
    arms: tuple[Arm, ...] = H_ARMS,
) -> TopBoardReport:
    report = TopBoardReport()
    for arm in arms:
        for season in seasons:
            tiers, extras = measure_arm_season(con, arm, season)
            report.tiers.extend(tiers)
            report.extras.append({"arm": arm, "season": season, **extras})

    tf, ef = report.tier_frame(), report.extras_frame()
    for arm in arms:
        if arm == PREREGISTERED_CONTROL:
            continue
        report.verdicts.append(evaluate_gates(tf, ef, arm))
    for arm in arms:  # H_ARMS is already in Occam order
        v = next((v for v in report.verdicts if v.arm == arm), None)
        if v is not None and v.passed:
            report.selected = arm
            break
    return report


ARM_DESCRIPTIONS: dict[Arm, str] = {
    "H0": "control -- the shipped Y1 model, unchanged",
    "H1": "CatBoost with l2_leaf_reg 3 -> 10 (shrink the n=3 elite leaf)",
    "H2": "CatBoost with l2_leaf_reg 3 -> 30 (stronger shrinkage)",
    "H3": "XGBoost at the SAME MAE loss, unconstrained -- the library control for H4",
    "H4": "XGBoost at the SAME MAE loss, monotone in prior production and ECR",
}
