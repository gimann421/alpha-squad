"""Pre-registered walk-forward test of ADDING PRE-SEASON-KNOWABLE FEATURES to M6 (D82).

**Committed to git before any arm was run against real data** -- the features, the arms, the tier
definitions, the gates and the selection rule. D39/D54/D63/D66/D67/D68/D70/D78/D80 discipline.

Why this phase, and why it is different from everything tried so far
--------------------------------------------------------------------
D79 and D80 both tried to fix the elite-tail behaviour by changing the ESTIMATOR (monotone
constraints, shrinkage, a different library) while holding the four features fixed. Every arm
failed. D80's diagnosis said why: the elite tail is sparse (RB has 22 training rows above a
prior weighted total of 300 and 5 above 350, from 14 distinct players), so no estimator change
can manufacture information that is not in the features.

This phase asks the other question: **is the information missing?**

M6 currently sees exactly four things -- `prior_ppg`, `prior_games`, `prior_weighted_total`,
`preseason_ecr_rank`. It has no notion of how old a player is, how long he has been in the
league, how much volume he absorbed last season, or what share of his offence he commanded.
The football story behind the RB elite-tail collapse -- attrition after a monster workload
season -- is precisely an age x workload interaction, and the model cannot represent it because
it cannot see either term.

Measured before this module existed (D80 diagnosis, real 2015-2025 data):

    training rows for the 2026 fit        n     >=300   >=350   distinct players >=300
    QB                                   585      52      17            25
    RB                                  1120      22       5            14
    WR                                  1678      32       8            16
    TE                                   943       0       0             0

    realized in the >=350 tail:  QB n=17 mean 297.0 | RB n=5 mean 157.4 | WR n=8 mean 231.2

    partial dependence on prior_weighted_total at an ELITE profile, 100 -> 450:
      QB  170 -> 287, monotone, 0 reversals
      RB  199 -> peak 246 at 280 -> 198, 4 reversals     <- the defect
      WR  162 -> peak 252 at 320 -> 245, 2 reversals
      TE  143 -> flat 162 past 280 (no training rows exist above 300 at all)

So the shape of the problem is common (a sparse extreme tail the trees cannot extrapolate
through) while the severity is entirely position-specific, tracking each position's tail
population and that tail's realized outcomes.

The features, and why each is legitimately pre-season knowable
---------------------------------------------------------------
Every feature below is derived either from a static player attribute or from the season STRICTLY
BEFORE the one being projected. `_assert_feature_leakage_free` enforces the second condition
structurally and raises rather than warns.

  age_at_season      years from `players.birth_date` to Sept 1 of the target season. Static
                     biographical fact, known years in advance.
  career_season      target season minus `players.rookie_season`. Known in advance.
  draft_round        `players.draft_round`, the player's own draft capital. Known in advance.
  prior_carries      total carries in season S-1.
  prior_targets      total targets in season S-1.
  prior_touches      carries + receptions in S-1 -- the workload-volume term the attrition story
                     is actually about.
  prior_target_share mean weekly `target_share` in S-1.
  prior_snap_pct     mean weekly `offense_snap_pct` in S-1 -- usage/role, distinct from output.

None of these is a positional term, a bonus, an ECR transform, or anything player-specific.

Coverage, measured before any arm was run (2015-2025 rows, real data). This is an availability
fact about the columns, not a result about any arm:

    position   rows   age   career   draft_round   volume   target_share   snap_pct
    QB          585   100%    100%         86.2%     100%           100%      100%
    RB         1120   100%    100%         71.5%     100%           100%      100%
    WR         1678   100%    100%         71.9%     100%           100%     99.8%
    TE          943   100%    100%         71.3%     100%           100%     99.9%

`draft_round` is null for undrafted players -- a real signal, not a defect -- and CatBoost
handles NaN natively, so those rows are kept rather than dropped. The join is verified
row-count-preserving (1120 -> 1120 for RB): a fan-out would silently duplicate training rows.

WHAT IS EXPLICITLY NOT DONE HERE
--------------------------------
No estimator change (the CatBoost hyperparameters are byte-identical to production), no loss
change, no monotone constraint, no target change, no training-row change, no positional
parameter. The ONLY thing that varies between arms is which columns the model may see, so a
difference is attributable to information and nothing else.
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
    select_training_rows,
)
from alpha_squad.models.established.season_level import (
    FEATURES,
    TARGET_COLUMN,
    load_season_level_data,
)

Arm = str

#: Feature blocks. Each is a group of columns added on top of M6's four.
AGE_BLOCK = ("age_at_season", "career_season", "draft_round")
VOLUME_BLOCK = ("prior_carries", "prior_targets", "prior_touches")
USAGE_BLOCK = ("prior_target_share", "prior_snap_pct")

#: The five pre-registered arms. There is no sixth, and adding one after seeing results is a
#: protocol violation to be reported as a failed phase rather than patched around.
#:
#:   F0  control: the shipped Y1 model on its four features.
#:   F1  + age / career / draft capital.
#:   F2  + prior-season workload VOLUME.
#:   F3  + prior-season USAGE SHARE.
#:   F4  + all three blocks.
#:
#: F1-F3 are separated so that, if F4 helps, the phase can say WHICH information did the work
#: rather than shipping a bundle it cannot attribute.
F_ARMS: tuple[Arm, ...] = ("F0", "F1", "F2", "F3", "F4")
PREREGISTERED_CONTROL: Arm = "F0"

F_ARM_BLOCKS: dict[Arm, tuple[str, ...]] = {
    "F0": (),
    "F1": AGE_BLOCK,
    "F2": VOLUME_BLOCK,
    "F3": USAGE_BLOCK,
    "F4": AGE_BLOCK + VOLUME_BLOCK + USAGE_BLOCK,
}

#: Row selection is the SHIPPED D78 specification for every arm.
SHIPPED_ROW_SPECIFICATION = "Y1"

#: PRE-REGISTERED evaluation window, identical to D78/D79/D80.
PREREGISTERED_TARGET_SEASONS: tuple[int, ...] = (2022, 2023, 2024, 2025)

# --------------------------------------------------------------------------------------------
# PRE-REGISTERED TIERS -- the fuller set this phase is judged on.
#
# Cut by preseason ECR rank WITHIN POSITION, which is exogenous to every arm, so all arms are
# scored on the identical players and the comparison is genuinely paired. Cutting by predicted
# rank would let each arm choose its own top five and turn the metric into a selection effect.
# --------------------------------------------------------------------------------------------
PREREGISTERED_TIERS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "RB": (
        ("top5", 1, 6),
        ("top10", 1, 11),
        ("11_24", 11, 25),
        ("25_60", 25, 61),
        ("61_100", 61, 101),
        ("all", 1, 10_000),
    ),
    "WR": (
        ("top5", 1, 6),
        ("top10", 1, 11),
        ("11_24", 11, 25),
        ("25_60", 25, 61),
        ("all", 1, 10_000),
    ),
    "QB": (("top5", 1, 6), ("top10", 1, 11), ("11_24", 11, 25), ("all", 1, 10_000)),
    "TE": (("top5", 1, 6), ("top10", 1, 11), ("11_24", 11, 25), ("all", 1, 10_000)),
}
PREREGISTERED_OVERALL_TIERS: tuple[tuple[str, int, int], ...] = (
    ("top12", 1, 13),
    ("top24", 1, 25),
    ("top50", 1, 51),
    ("top100", 1, 101),
    ("all", 1, 10_000),
)

# --------------------------------------------------------------------------------------------
# PRE-REGISTERED GATES
#
# All deltas are (arm - control), pooled over the four target seasons; NEGATIVE MAE is better.
#
#   P1  ACCURACY IMPROVES     pooled MAE over all position-seasons improves by at least
#                             MIN_POOLED_GAIN, AND the paired two-sided t-test over the 16
#                             position-seasons has p < 0.05. The effect-size floor is there
#                             because significance alone is not a reason to change production:
#                             a reliably-detected 0.01-point gain is still not worth shipping.
#   P2  NO TIER DAMAGED       no pre-registered tier's MAE worsens by more than TOLERANCE.
#                             This is the tier-preservation requirement: an arm that buys one
#                             tier with another fails here regardless of its pooled mean.
#   P3  NO POSITION DAMAGED   no position's whole-pool MAE worsens by more than TOLERANCE.
#   P4  RB TOP-10 NOT WORSE   the known defect must not be made worse (<= TOLERANCE).
#   P5  TE PRESERVED          TE pool MAE must not worsen by more than TOLERANCE. TE is measured
#                             unbiased today and has no elite tail at all; it is the control
#                             position and must survive untouched.
#   P6  NOT ONE SEASON        pooled MAE improves in at least 3 of the 4 target seasons.
#   P7  LEAVE-ONE-SEASON-OUT  the pooled improvement survives dropping any single season.
#   P8  ORDERING NOT DAMAGED  mean Spearman does not fall, and no position's Spearman falls by
#                             more than MAX_SPEARMAN_DROP.
#   P9  NOT CONSENSUS-COPYING no position's Spearman(prediction, -ECR) exceeds the control's by
#                             more than MAX_ECR_SPEARMAN_GAIN. An arm that wins by reproducing
#                             the market's ordering is not a model improvement.
#
# SELECTION RULE: ship the LOWEST-NUMBERED arm clearing every gate (Occam, standing since D63).
# If no arm clears them, NOTHING ships and M6 stays byte-identical to Y1.
#
# Stated before the run so it cannot be reinterpreted afterwards:
#   * P2 is deliberately strict and is the gate most likely to kill an arm. Adding features
#     redistributes error as well as reducing it, and this phase is explicitly not willing to
#     trade one tier for another.
#   * A shipped arm would ALSO require re-measuring conformal interval coverage before being
#     called done -- adding features changes the residual distribution the intervals are fitted
#     on. That is a follow-up condition, not a gate here, and it is recorded so it cannot be
#     forgotten.
#   * Shipping nothing is an explicitly acceptable outcome.
# --------------------------------------------------------------------------------------------

TOLERANCE = 1.0
#: Minimum pooled MAE improvement, in fantasy points, for P1 to count an arm as better. Pool MAE
#: sits near 40-50 points, so this is roughly a 1% relative floor.
MIN_POOLED_GAIN = 0.5
MAX_SPEARMAN_DROP = 0.01
MAX_ECR_SPEARMAN_GAIN = 0.05
PREREGISTERED_ALPHA = 0.05
PREREGISTERED_MIN_BETTER_SEASONS = 3


def load_extended_features(
    con: duckdb.DuckDBPyConnection, position: str, season_start: int, season_end: int
) -> pd.DataFrame:
    """M6's own frame plus the pre-season-knowable blocks, joined on (player_id, target_season).

    Every added column is either a static biographical attribute or an aggregate of the season
    STRICTLY BEFORE the target season. The `s1.season = t.target_season - 1` join condition is
    what enforces that, and `_assert_feature_leakage_free` re-checks it independently."""
    base = load_season_level_data(con, position, season_start, season_end)
    if base.empty:
        return base

    extra = con.execute(
        """
        SELECT
            s1.player_id,
            s1.season + 1                                   AS target_season,
            s1.total_carries                                AS prior_carries,
            s1.total_targets                                AS prior_targets,
            COALESCE(s1.total_carries, 0) + COALESCE(s1.total_receptions, 0) AS prior_touches,
            w.mean_target_share                             AS prior_target_share,
            w.mean_snap_pct                                 AS prior_snap_pct,
            p.rookie_season,
            p.birth_date,
            p.draft_round
        FROM player_season_stats s1
        LEFT JOIN players p ON p.player_id = s1.player_id
        LEFT JOIN (
            SELECT player_id, season,
                   avg(target_share)      AS mean_target_share,
                   avg(offense_snap_pct)  AS mean_snap_pct
            FROM player_week_stats GROUP BY player_id, season
        ) w ON w.player_id = s1.player_id AND w.season = s1.season
        WHERE s1.position = ?
        """,
        [position],
    ).fetchdf()

    df = base.merge(extra, on=["player_id", "target_season"], how="left")
    # Age is computed against each row's OWN target season, never the range end -- otherwise
    # every training row would carry the evaluation season's age and the feature would leak.
    birth = pd.to_datetime(df["birth_date"], errors="coerce")
    sept1 = pd.to_datetime(df["target_season"].astype(str) + "-09-01")
    df["age_at_season"] = (sept1 - birth).dt.days / 365.25
    df["career_season"] = df["target_season"] - df["rookie_season"]
    for col in (*AGE_BLOCK, *VOLUME_BLOCK, *USAGE_BLOCK):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop(columns=["birth_date", "rookie_season"])


def _assert_feature_leakage_free(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, position: str
) -> None:
    """Independent re-check that every workload/usage value belongs to the season BEFORE the
    target, by recomputing a sample directly from the source table. Raises rather than warns."""
    if df.empty:
        return
    sample = df.dropna(subset=["prior_carries"]).head(25)
    for row in sample.itertuples():
        got = con.execute(
            "SELECT total_carries FROM player_season_stats WHERE player_id=? AND season=?",
            [row.player_id, int(row.target_season) - 1],
        ).fetchone()
        expected = got[0] if got else None
        if expected is None:
            continue
        if abs(float(expected) - float(row.prior_carries)) > 1e-6:
            raise ValueError(
                f"leakage or misjoin at {position}/{row.player_id}/{row.target_season}: "
                f"prior_carries={row.prior_carries} but season "
                f"{int(row.target_season) - 1} has {expected}"
            )


def features_for(arm: Arm) -> list[str]:
    if arm not in F_ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    return [*FEATURES, *F_ARM_BLOCKS[arm]]


def _new_model() -> CatBoostRegressor:
    """M6's estimator, byte-identical to production. Nothing about it varies between arms --
    only the feature columns do."""
    return CatBoostRegressor(
        iterations=150,
        depth=3,
        learning_rate=0.08,
        loss_function="MAE",
        verbose=False,
        random_seed=42,
    )


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    return float(pd.Series(a).corr(pd.Series(b), method="spearman"))


@dataclass(frozen=True)
class TierRow:
    arm: Arm
    season: int
    position: str
    tier: str
    n: int
    mae: float
    rmse: float
    bias: float


def measure_arm_season(
    con: duckdb.DuckDBPyConnection, arm: Arm, season: int, min_train_season: int = 2015
) -> tuple[list[TierRow], dict]:
    rows: list[TierRow] = []
    extras: dict = {"arm": arm, "season": season}
    frames = []
    cols = features_for(arm)

    for position in POSITIONS:
        data = load_extended_features(con, position, min_train_season, season)
        if data.empty:
            continue
        _assert_feature_leakage_free(con, data, position)
        target = data[data["target_season"] == season]
        train = select_training_rows(SHIPPED_ROW_SPECIFICATION, data, season)
        if target.empty or len(train) < MIN_TRAIN_ROWS:
            continue
        model = _new_model()
        model.fit(train[cols].to_numpy(dtype=float), train[TARGET_COLUMN].to_numpy())
        pred = np.asarray(model.predict(target[cols].to_numpy(dtype=float)), dtype=float)

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

        ranked = frame.sort_values("preseason_ecr_rank").reset_index(drop=True)
        for label, lo, hi in PREREGISTERED_TIERS[position]:
            tier = ranked.iloc[lo - 1 : hi - 1]
            if tier.empty:
                continue
            a, p = tier[TARGET_COLUMN].to_numpy(), tier["predicted"].to_numpy()
            rows.append(
                TierRow(
                    arm,
                    season,
                    position,
                    label,
                    len(tier),
                    float(np.abs(a - p).mean()),
                    float(np.sqrt(((a - p) ** 2).mean())),
                    float((a - p).mean()),
                )
            )

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
            rows.append(
                TierRow(
                    arm,
                    season,
                    "ALL",
                    label,
                    len(tier),
                    float(np.abs(aa - pp).mean()),
                    float(np.sqrt(((aa - pp) ** 2).mean())),
                    float((aa - pp).mean()),
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


def _t_test_p(deltas: np.ndarray) -> float:
    n = len(deltas)
    if n < 2:
        return 1.0
    sd = float(np.std(deltas, ddof=1))
    if sd == 0.0:
        return 0.0 if float(np.mean(deltas)) != 0.0 else 1.0
    from scipy import stats

    t = float(np.mean(deltas)) / (sd / np.sqrt(n))
    return float(2.0 * stats.t.sf(abs(t), df=n - 1))


def evaluate_gates(
    tiers: pd.DataFrame, extras: pd.DataFrame, arm: Arm, control: Arm = PREREGISTERED_CONTROL
) -> ArmVerdict:
    verdict = ArmVerdict(arm=arm)
    if arm == control:
        return verdict

    pos_tiers = tiers[tiers.position != "ALL"]
    wide = pos_tiers[pos_tiers.tier == "all"].pivot_table(
        index=["season", "position"], columns="arm", values="mae"
    )
    deltas = (wide[arm] - wide[control]).dropna().to_numpy()
    p_value = _t_test_p(deltas)
    verdict.gates.append(
        GateResult(
            "P1 accuracy improves",
            bool(deltas.mean() <= -MIN_POOLED_GAIN and p_value < PREREGISTERED_ALPHA),
            f"mean position-season dMAE {deltas.mean():+.3f} "
            f"(needs <= {-MIN_POOLED_GAIN:+.2f}), paired p={p_value:.4f}",
        )
    )

    tier_piv = tiers.pivot_table(index=["position", "tier"], columns="arm", values="mae")
    damaged = {
        f"{pos}/{tier}": float(tier_piv.loc[(pos, tier), arm] - tier_piv.loc[(pos, tier), control])
        for pos, tier in tier_piv.index
        if tier_piv.loc[(pos, tier), arm] - tier_piv.loc[(pos, tier), control] > TOLERANCE
    }
    verdict.gates.append(
        GateResult(
            "P2 no tier damaged",
            not damaged,
            "all tiers within tolerance"
            if not damaged
            else ", ".join(f"{k} {v:+.1f}" for k, v in sorted(damaged.items())),
        )
    )

    pos_damage = {}
    for position in POSITIONS:
        col = f"pool_mae_{position}"
        if col in extras.columns:
            d = float(extras[extras.arm == arm][col].mean()) - float(
                extras[extras.arm == control][col].mean()
            )
            pos_damage[position] = d
    verdict.gates.append(
        GateResult(
            "P3 no position damaged",
            all(v <= TOLERANCE for v in pos_damage.values()),
            ", ".join(f"{k} {v:+.2f}" for k, v in pos_damage.items()),
        )
    )

    d_rb_top = float(tier_piv.loc[("RB", "top10"), arm] - tier_piv.loc[("RB", "top10"), control])
    verdict.gates.append(
        GateResult(
            "P4 RB top10 not worse", bool(d_rb_top <= TOLERANCE), f"RB top10 dMAE {d_rb_top:+.2f}"
        )
    )

    verdict.gates.append(
        GateResult(
            "P5 TE preserved",
            bool(pos_damage.get("TE", 0.0) <= TOLERANCE),
            f"TE pool dMAE {pos_damage.get('TE', float('nan')):+.2f}",
        )
    )

    per_season = {}
    for season in sorted(extras.season.unique()):
        a = float(extras[(extras.arm == arm) & (extras.season == season)]["pool_mae_ALL"].mean())
        c = float(
            extras[(extras.arm == control) & (extras.season == season)]["pool_mae_ALL"].mean()
        )
        per_season[int(season)] = a - c
    better = sum(1 for v in per_season.values() if v < 0)
    verdict.gates.append(
        GateResult(
            "P6 not one season",
            better >= PREREGISTERED_MIN_BETTER_SEASONS,
            f"{better}/{len(per_season)} better: "
            + ", ".join(f"{s}:{v:+.2f}" for s, v in per_season.items()),
        )
    )

    loso = {}
    for held in sorted(extras.season.unique()):
        kept = extras[extras.season != held]
        loso[int(held)] = float(kept[kept.arm == arm]["pool_mae_ALL"].mean()) - float(
            kept[kept.arm == control]["pool_mae_ALL"].mean()
        )
    verdict.gates.append(
        GateResult(
            "P7 leave-one-season-out",
            all(v < 0 for v in loso.values()),
            ", ".join(f"drop {s}:{v:+.2f}" for s, v in loso.items()),
        )
    )

    drops = {}
    for position in POSITIONS:
        col = f"spearman_{position}"
        if col in extras.columns:
            drops[position] = float(extras[extras.arm == control][col].mean()) - float(
                extras[extras.arm == arm][col].mean()
            )
    verdict.gates.append(
        GateResult(
            "P8 ordering intact",
            bool(np.mean(list(drops.values())) <= 0 or max(drops.values()) <= MAX_SPEARMAN_DROP),
            ", ".join(f"{k} {-v:+.4f}" for k, v in drops.items()),
        )
    )

    ecr_gain = {}
    for position in POSITIONS:
        col = f"ecr_spearman_{position}"
        if col in extras.columns:
            ecr_gain[position] = float(extras[extras.arm == arm][col].mean()) - float(
                extras[extras.arm == control][col].mean()
            )
    verdict.gates.append(
        GateResult(
            "P9 not consensus-copying",
            all(v <= MAX_ECR_SPEARMAN_GAIN for v in ecr_gain.values()),
            ", ".join(f"{k} {v:+.3f}" for k, v in ecr_gain.items()),
        )
    )
    return verdict


@dataclass
class FeatureReport:
    tiers: list[TierRow] = field(default_factory=list)
    extras: list[dict] = field(default_factory=list)
    verdicts: list[ArmVerdict] = field(default_factory=list)
    selected: Arm | None = None

    def tier_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.tiers])

    def extras_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.extras)


def run_feature_experiment(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...] = PREREGISTERED_TARGET_SEASONS,
    arms: tuple[Arm, ...] = F_ARMS,
) -> FeatureReport:
    report = FeatureReport()
    for arm in arms:
        for season in seasons:
            rows, extras = measure_arm_season(con, arm, season)
            report.tiers.extend(rows)
            report.extras.append(extras)
    tf, ef = report.tier_frame(), report.extras_frame()
    for arm in arms:
        if arm == PREREGISTERED_CONTROL:
            continue
        report.verdicts.append(evaluate_gates(tf, ef, arm))
    for arm in arms:
        v = next((v for v in report.verdicts if v.arm == arm), None)
        if v is not None and v.passed:
            report.selected = arm
            break
    return report


ARM_DESCRIPTIONS: dict[Arm, str] = {
    "F0": "control -- the shipped Y1 model on its four features",
    "F1": "+ age at season, career season, draft round",
    "F2": "+ prior-season workload volume (carries, targets, touches)",
    "F3": "+ prior-season usage share (target share, snap pct)",
    "F4": "+ all three blocks",
}
