"""Pre-registered walk-forward test of M6's TRAINING SPECIFICATION (docs/DECISIONS.md D78).

**This module was committed to git before any confirmatory arm was run against real data** --
the arms, the eligibility rule, the gates and the selection rule -- following the
D39/D54/D63/D66/D67/D68/D70 discipline of fixing the decision rule before recording the
outcome.

How this differs from D68, and why it is a different class of change
--------------------------------------------------------------------
D68 (`evaluation/projection_calibration.py`) tested five POST-HOC ADJUSTMENTS to the model's
output -- `p' = p + b_pos` and relatives. Every one of them carries a fitted per-position
parameter, which is why the sign-instability of that parameter at QB/WR/TE is what killed
them, and why an RB-only version would have been an unprincipled positional bonus.

This phase changes **no output**. It changes **which rows M6 is allowed to train on**, and it
does so identically for every position. There is no positional parameter, no bias term, no
band, no shrinkage coefficient and nothing that can be tuned toward RB. An arm here either
improves the model at every position or it does not; it cannot improve one position at the
expense of another by construction, because there is nothing position-specific in it.

The two defects this phase tests
--------------------------------
Both were found by read-only diagnostics on real 2019-2025 data before this module existed,
and both are properties of the training data rather than of the estimator:

**Defect 1 -- the ECR sentinel is doing two different jobs.**
`models/established/season_level.py::load_season_level_data` left-joins the preseason
FantasyPros `ro` board and fills a missing rank with 999, so that "no market opinion" does not
look like "elite consensus". That is right for a player who is genuinely absent from a board
that exists. It is wrong for a season in which **no board exists at all**: `market_snapshot`
has no Jul/Aug `ro` rows before 2020, so every training row with a target season of 2016-2019
carries `preseason_ecr_rank = 999` regardless of who the player was. Those rows teach the
model that a bottom-of-the-board consensus rank is compatible with an elite season, because in
them it always is. They are ~44% of the RB training rows for a 2026 projection.

Measured: `preseason_ecr_rank` is M6's most valuable feature (dropping it costs +1.83 MAE),
and the seasons that carry it degenerately are the ones this arm removes.

**Defect 2 -- the most recent completed season never reaches the point model.**
`run_uncertainty` sets `proper_train = target_season < calib_season` where
`calib_season = S - 1`, so season S-1's outcomes are used ONLY to fit conformal residual
quantiles and never as training rows. For a 2026 projection that discards 2025 entirely -- the
single most relevant season, in a sport whose positional environment demonstrably drifts (the
top-decile RB residual ran -33.8, +37.2, +2.8, +52.6, +64.2 over 2021-2025). The conformal
step needs S-1 held out from the model whose residuals it measures; it does not need S-1 held
out from the model that produces the point prediction, and those can be two different fits.

What is deliberately NOT tested here
------------------------------------
No loss-function change, no capacity change, no new feature, no positional term, no output
transform. Those were measured in the diagnostics (RMSE loss costs +2.29 MAE, Huber +0.61,
a ppg x games decomposition +0.69, dropping ECR +1.83, recency SAMPLE WEIGHTS +0.16 to +0.59)
and none of them is an improvement; they are recorded in D78 as measured-and-rejected rather
than carried forward as arms.

Honesty note on the pre-registration
------------------------------------
The two arms below were identified by exploratory analysis, so this is a diagnostic-informed
pre-registration, not a blind one, and D78 says so explicitly. What the pre-registration buys
is the decision rule: the gates are fixed here, they are strictly harder than "beats control on
average", and they include per-position and per-season non-regression requirements that a
change tuned toward one position or one season cannot pass.

Leakage
-------
Every arm is defined by a filter over training rows whose target season is strictly less than
the target season being predicted. `_assert_no_leakage` enforces that structurally and raises
rather than warns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)

Arm = str

#: The four pre-registered arms. There is no fifth, and adding one after seeing results is a
#: protocol violation to be reported as a failed phase rather than patched around.
#:
#:   Y0  control: production. Train on every season <= S-2, ECR sentinel 999 kept.
#:   Y1  train through S-1 (defect 2 only).
#:   Y2  drop ECR-degenerate training seasons (defect 1 only).
#:   Y3  both.
Y_ARMS: tuple[Arm, ...] = ("Y0", "Y1", "Y2", "Y3")
PREREGISTERED_CONTROL: Arm = "Y0"

#: Positions M6 covers. K and DST are baselines by D57 and are untouched by this phase.
POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: PRE-REGISTERED evaluation window. 2022 is the earliest target season at which Y2 has at
#: least one eligible training season (the `ro` board begins in 2020, and a target season of
#: 2021 draws its training rows from target seasons <= 2019). 2025 is the last completed
#: season. Four target seasons x four positions = 16 paired observations.
PREREGISTERED_TARGET_SEASONS: tuple[int, ...] = (2022, 2023, 2024, 2025)

#: A training season is ECR-degenerate if fewer than this fraction of its rows carry a real
#: preseason rank. **This is not a tuned parameter.** On real data the per-season coverage is
#: exactly 0.00 for 2016-2019 and 0.71-0.95 for 2020-2024, so every threshold in (0.00, 0.71)
#: produces the identical partition; `tests/unit/test_projection_specification.py` asserts that
#: invariance over 0.05-0.70 rather than trusting the prose. Stated as a coverage rule and not
#: as "seasons >= 2020" so it keeps working when the board's history changes.
ECR_COVERAGE_FLOOR = 0.5

#: The sentinel `load_season_level_data` writes for a missing preseason rank.
ECR_MISSING_SENTINEL = 999.0

#: Matches `models/uncertainty/run.py::MIN_TRAIN_ROWS`. An arm that would starve a position
#: below this falls back to the control's training set for that position-season rather than
#: fitting noise -- declared here so the fallback cannot look like a rescue invented later.
MIN_TRAIN_ROWS = 30

#: An arm must leave at least this many distinct training seasons, for the same reason D68
#: required two: with one season an estimator cannot separate a stable relationship from that
#: season. Below it, the arm falls back to control for that position-season.
MIN_TRAIN_SEASONS = 2


# --------------------------------------------------------------------------------------------
# PRE-REGISTERED GATES
#
#   G1  accuracy improves. Mean paired dMAE < 0 AND mean paired dRMSE < 0 versus control over
#       the 16 position-seasons.
#   G2  the improvement is not one season. Mean dMAE < 0 in at least 3 of the 4 target seasons.
#   G3  no position is sacrificed. No position's 4-season mean MAE is worse than control's.
#       This is the gate that makes a positional bonus impossible to pass off as an
#       improvement: an arm that buys RB accuracy with WR accuracy fails here.
#   G4  ordering is not damaged. Mean paired dSpearman >= 0, and no position's 4-season mean
#       Spearman falls by more than 0.01.
#   G5  it is not noise. Paired two-sided t-test of dMAE over the 16 position-seasons, p < 0.05.
#   G6  top-of-board calibration does not get worse. For every position, the 4-season mean
#       |top-decile signed bias| is not larger than control's. This is the gate aimed at the
#       reported symptom; note it is stated as "not worse", because the diagnostics say the
#       residual RB top-of-board effect is shared with the market consensus and is therefore
#       not something a training-set fix is expected to remove.
#   G7  robust to any one season. Leave-one-season-out: mean dMAE < 0 in all four folds.
#
# SELECTION RULE: ship the LOWEST-NUMBERED arm clearing all seven gates (Occam, the project's
# standing rule since D63). If no arm clears them, NOTHING ships and M6 stays byte-identical.
#
# The uncertainty layer is checked SEPARATELY and is not a gate here, because no arm in this
# module changes it: `run_uncertainty`'s conformal residuals stay fitted on a model that never
# saw the calibration season. A shipped arm must still be re-measured for coverage against the
# existing `calibration_diagnostics` table before it is called done.
# --------------------------------------------------------------------------------------------

PREREGISTERED_MIN_BETTER_SEASONS = 3
PREREGISTERED_MAX_SPEARMAN_DROP = 0.01
PREREGISTERED_ALPHA = 0.05


def _assert_no_leakage(train: pd.DataFrame, target_season: int) -> None:
    """Structural guard, not a convention: raises if any training row's outcome comes from the
    target season or later."""
    if train.empty:
        return
    worst = int(train["target_season"].max())
    if worst >= target_season:
        raise ValueError(
            f"leakage: training row with target_season={worst} used to predict {target_season}"
        )


def ecr_coverage_by_season(train: pd.DataFrame) -> dict[int, float]:
    """{target_season: fraction of rows carrying a real preseason ECR rank}."""
    real = train["preseason_ecr_rank"] < ECR_MISSING_SENTINEL
    return {
        int(season): float(group.mean())
        for season, group in real.groupby(train["target_season"], observed=True)
    }


def eligible_ecr_seasons(train: pd.DataFrame, floor: float = ECR_COVERAGE_FLOOR) -> list[int]:
    """Target seasons whose preseason board actually exists, best-first by season."""
    return sorted(s for s, cov in ecr_coverage_by_season(train).items() if cov >= floor)


def select_training_rows(
    arm: Arm, all_data: pd.DataFrame, target_season: int, floor: float = ECR_COVERAGE_FLOOR
) -> pd.DataFrame:
    """The training frame `arm` prescribes for `target_season`.

    Y0/Y2 stop at S-2 (production's split); Y1/Y3 include S-1. Y2/Y3 additionally drop
    ECR-degenerate seasons, falling back to the arm's unfiltered frame if that would leave
    fewer than `MIN_TRAIN_SEASONS` seasons or `MIN_TRAIN_ROWS` rows."""
    if arm not in Y_ARMS:
        raise ValueError(f"unknown arm {arm!r}")

    last_train_season = target_season - 1 if arm in ("Y1", "Y3") else target_season - 2
    rows = all_data[all_data["target_season"] <= last_train_season]

    if arm in ("Y2", "Y3"):
        keep = eligible_ecr_seasons(rows, floor)
        filtered = rows[rows["target_season"].isin(keep)]
        if len(keep) >= MIN_TRAIN_SEASONS and len(filtered) >= MIN_TRAIN_ROWS:
            rows = filtered

    _assert_no_leakage(rows, target_season)
    return rows


def _fit_predict(train: pd.DataFrame, target: pd.DataFrame) -> np.ndarray:
    """M6's exact estimator, unchanged. Only the training rows vary between arms."""
    model = CatBoostRegressor(
        iterations=150,
        depth=3,
        learning_rate=0.08,
        loss_function="MAE",
        verbose=False,
        random_seed=42,
    )
    model.fit(train[FEATURES].to_numpy(), train[TARGET_COLUMN].to_numpy())
    return np.asarray(model.predict(target[FEATURES].to_numpy()), dtype=float)


@dataclass(frozen=True)
class ArmMeasurement:
    arm: Arm
    season: int
    position: str
    n: int
    n_train: int
    n_train_seasons: int
    mae: float
    rmse: float
    spearman: float
    bias: float
    top_decile_bias: float
    max_projection: float
    fell_back: bool


def measure_arm(
    con: duckdb.DuckDBPyConnection,
    arm: Arm,
    season: int,
    position: str,
    min_train_season: int = 2015,
) -> ArmMeasurement | None:
    """One (arm, season, position) walk-forward measurement, or None if M6 itself would skip."""
    all_data = load_season_level_data(con, position, min_train_season, season)
    target = all_data[all_data["target_season"] == season]
    control_rows = select_training_rows(PREREGISTERED_CONTROL, all_data, season)
    if target.empty or len(control_rows) < MIN_TRAIN_ROWS:
        return None

    train = select_training_rows(arm, all_data, season)
    fell_back = arm in ("Y2", "Y3") and set(train["target_season"]) == set(
        all_data[all_data["target_season"] <= train["target_season"].max()]["target_season"]
    )
    predicted = _fit_predict(train, target)
    actual = target[TARGET_COLUMN].to_numpy()

    order = np.argsort(-predicted)
    k = max(1, int(round(0.10 * len(predicted))))
    top = order[:k]
    return ArmMeasurement(
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
        fell_back=fell_back,
    )


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


def _paired(frame: pd.DataFrame, arm: Arm, metric: str) -> pd.Series:
    """Per (season, position) delta of `arm` minus control on `metric`."""
    wide = frame.pivot_table(index=["season", "position"], columns="arm", values=metric)
    return (wide[arm] - wide[PREREGISTERED_CONTROL]).dropna()


def _t_test_p(deltas: pd.Series) -> float:
    """Two-sided paired t-test p-value, computed without adding a scipy dependency to the
    production import path (scipy is already a transitive dep, but this keeps the module
    importable with numpy alone)."""
    n = len(deltas)
    if n < 2:
        return 1.0
    sd = float(deltas.std(ddof=1))
    if sd == 0.0:
        return 0.0 if float(deltas.mean()) != 0.0 else 1.0
    t = float(deltas.mean()) / (sd / np.sqrt(n))
    from scipy import stats  # local import: evaluation-only path

    return float(2.0 * stats.t.sf(abs(t), df=n - 1))


def evaluate_gates(frame: pd.DataFrame, arm: Arm) -> ArmVerdict:
    """Apply G1-G7 to an arm, given the full measurement frame."""
    verdict = ArmVerdict(arm=arm)
    if arm == PREREGISTERED_CONTROL:
        return verdict

    d_mae = _paired(frame, arm, "mae")
    d_rmse = _paired(frame, arm, "rmse")
    d_sp = _paired(frame, arm, "spearman")

    verdict.gates.append(
        GateResult(
            "G1 accuracy improves",
            bool(d_mae.mean() < 0 and d_rmse.mean() < 0),
            f"dMAE {d_mae.mean():+.3f}, dRMSE {d_rmse.mean():+.3f}",
        )
    )

    per_season = d_mae.groupby("season").mean()
    better = int((per_season < 0).sum())
    verdict.gates.append(
        GateResult(
            "G2 not one season",
            better >= PREREGISTERED_MIN_BETTER_SEASONS,
            f"{better}/{len(per_season)} seasons better: "
            + ", ".join(f"{s}:{v:+.2f}" for s, v in per_season.items()),
        )
    )

    mae_by_pos = frame.pivot_table(index="position", columns="arm", values="mae")
    worse_pos = [
        p
        for p in mae_by_pos.index
        if mae_by_pos.loc[p, arm] > mae_by_pos.loc[p, PREREGISTERED_CONTROL]
    ]
    verdict.gates.append(
        GateResult(
            "G3 no position sacrificed",
            not worse_pos,
            "all positions improve" if not worse_pos else f"worse at {worse_pos}",
        )
    )

    sp_by_pos = frame.pivot_table(index="position", columns="arm", values="spearman")
    drops = {
        p: float(sp_by_pos.loc[p, PREREGISTERED_CONTROL] - sp_by_pos.loc[p, arm])
        for p in sp_by_pos.index
    }
    worst_drop = max(drops.values())
    verdict.gates.append(
        GateResult(
            "G4 ordering intact",
            bool(d_sp.mean() >= 0 and worst_drop <= PREREGISTERED_MAX_SPEARMAN_DROP),
            f"dSpearman {d_sp.mean():+.4f}, worst per-position drop {worst_drop:+.4f}",
        )
    )

    p_value = _t_test_p(d_mae)
    verdict.gates.append(
        GateResult(
            "G5 not noise",
            p_value < PREREGISTERED_ALPHA,
            f"paired t-test p={p_value:.4f} over n={len(d_mae)}",
        )
    )

    tdb = frame.pivot_table(index="position", columns="arm", values="top_decile_bias").abs()
    worse_top = [p for p in tdb.index if tdb.loc[p, arm] > tdb.loc[p, PREREGISTERED_CONTROL] + 1e-9]
    verdict.gates.append(
        GateResult(
            "G6 top-of-board not worse",
            not worse_top,
            "|top-decile bias| not increased anywhere"
            if not worse_top
            else f"worse at {worse_top}",
        )
    )

    folds = {}
    for held_out in sorted({s for s, _ in d_mae.index}):
        fold = d_mae[[s != held_out for s, _ in d_mae.index]]
        folds[held_out] = float(fold.mean())
    verdict.gates.append(
        GateResult(
            "G7 leave-one-season-out",
            all(v < 0 for v in folds.values()),
            ", ".join(f"drop {s}:{v:+.3f}" for s, v in folds.items()),
        )
    )
    return verdict


@dataclass
class SpecificationReport:
    measurements: list[ArmMeasurement] = field(default_factory=list)
    verdicts: list[ArmVerdict] = field(default_factory=list)
    selected: Arm | None = None

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([m.__dict__ for m in self.measurements])


def run_specification_experiment(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...] = PREREGISTERED_TARGET_SEASONS,
    positions: tuple[str, ...] = POSITIONS,
    min_train_season: int = 2015,
) -> SpecificationReport:
    """Run every arm over every (season, position), apply the gates, apply the selection rule."""
    report = SpecificationReport()
    for season in seasons:
        for position in positions:
            for arm in Y_ARMS:
                m = measure_arm(con, arm, season, position, min_train_season)
                if m is not None:
                    report.measurements.append(m)

    frame = report.frame()
    if frame.empty:
        return report

    for arm in Y_ARMS:
        if arm == PREREGISTERED_CONTROL:
            continue
        report.verdicts.append(evaluate_gates(frame, arm))

    for verdict in report.verdicts:  # Y_ARMS order == lowest-numbered first
        if verdict.passed:
            report.selected = verdict.arm
            break
    return report


ARM_DESCRIPTIONS: dict[Arm, str] = {
    "Y0": "control -- production: train on every season <= S-2, ECR sentinel 999 kept",
    "Y1": "train through S-1 (the most recent completed season reaches the point model)",
    "Y2": "drop training seasons whose preseason board does not exist (ECR coverage < floor)",
    "Y3": "both Y1 and Y2",
}


def render_specification_report(report: SpecificationReport) -> str:
    """Markdown for `reports/projection_specification.md`."""
    frame = report.frame()
    lines = [
        "# M6 Training-Specification Experiment (D78)",
        "",
        "Walk-forward test of **which rows M6 may train on**. No arm changes the estimator, the",
        "features, the loss, or the model's output, and no arm contains a position-specific",
        "term -- see `evaluation/projection_specification.py` for the pre-registration.",
        "",
        "## Arms",
        "",
        "| arm | definition |",
        "|---|---|",
    ]
    lines += [f"| {a} | {ARM_DESCRIPTIONS[a]} |" for a in Y_ARMS]

    if frame.empty:
        lines += ["", "No measurements -- run `train uncertainty` first."]
        return "\n".join(lines) + "\n"

    lines += [
        "",
        "## Pooled results (mean over target seasons x positions)",
        "",
        "| arm | MAE | RMSE | Spearman | mean bias | top-decile bias | max projection |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm in Y_ARMS:
        s = frame[frame.arm == arm]
        if s.empty:
            continue
        lines.append(
            f"| {arm} | {s.mae.mean():.3f} | {s.rmse.mean():.3f} | {s.spearman.mean():.4f} | "
            f"{s.bias.mean():+.2f} | {s.top_decile_bias.mean():+.2f} | "
            f"{s.max_projection.mean():.1f} |"
        )

    lines += [
        "",
        "## MAE by position",
        "",
        "| position | " + " | ".join(Y_ARMS) + " |",
        "|---" * (len(Y_ARMS) + 1) + "|",
    ]
    by_pos = frame.pivot_table(index="position", columns="arm", values="mae")
    for pos in by_pos.index:
        lines.append(f"| {pos} | " + " | ".join(f"{by_pos.loc[pos, a]:.2f}" for a in Y_ARMS) + " |")

    lines += [
        "",
        "## Top-decile signed bias by position (realized minus projected)",
        "",
        "| position | " + " | ".join(Y_ARMS) + " |",
        "|---" * (len(Y_ARMS) + 1) + "|",
    ]
    tdb = frame.pivot_table(index="position", columns="arm", values="top_decile_bias")
    for pos in tdb.index:
        lines.append(f"| {pos} | " + " | ".join(f"{tdb.loc[pos, a]:+.1f}" for a in Y_ARMS) + " |")

    lines += ["", "## Pre-registered gates", ""]
    for verdict in report.verdicts:
        lines += [
            f"### {verdict.arm} -- {ARM_DESCRIPTIONS[verdict.arm]}",
            "",
            "| gate | result | detail |",
            "|---|---|---|",
        ]
        for gate in verdict.gates:
            lines.append(f"| {gate.name} | {'PASS' if gate.passed else 'FAIL'} | {gate.detail} |")
        lines += ["", f"**{verdict.arm}: {'PASSES' if verdict.passed else 'rejected'}**", ""]

    lines += [
        "## Selection",
        "",
        f"**{report.selected or 'no arm cleared every gate -- nothing ships'}**",
        "",
    ]
    return "\n".join(lines) + "\n"
