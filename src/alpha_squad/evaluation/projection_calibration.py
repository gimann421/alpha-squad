"""Pre-registered walk-forward projection calibration experiment (docs/DECISIONS.md D68).

**Everything in this module was committed to git BEFORE any arm was fitted against real data**
-- the arms, the estimators, the eligibility prior, the eight gates and the selection rule --
following the D39/D54/D63/D66/D67 discipline of fixing the decision rule before seeing the
outcome, so a result cannot be rationalised after the fact.

Why this phase exists
---------------------
D67's official benchmark left Alpha ahead of the fair consensus opponent on the point estimate
(+26.5) but inside the noise (95% CI [-38.0, +91.0]), with a 144-point loss in 2024. The
slot-by-slot decomposition put the residual gap **upstream of the draft engine**: Alpha loses RB
in all five seasons (mean -247.7) and wins WR in all five (+183.2) while drafting fewer of both,
and M6 under-projects RB in 4 of 5 seasons. The obvious next move was a positional bias
correction -- and the read-only diagnostics that preceded this module argue against it:

    RB residual, all M6-projected RBs      mean +10.3 but MEDIAN -0.7
    RB residual by projection-rank band    top 24 median ~ +26; below that ~ 0 to -2.8
    top-24 RB residual by season           2021 -8.8, 2022 +8.5, 2023 +19.0, 2024 +64.8, 2025 +39.5
    walk-forward prediction of 2024        +6.3 against an actual +64.8
    empirical-Bayes lambda, walk-forward   RB 0.00 in 2022/2023/2024; WR 0.00 every year
    the one stable finding                 QB OLS slope ~ 0.444, below 1 in all five seasons

So "RBs are systematically under-projected" is false as a statement about RBs -- the typical RB
is projected essentially correctly and the effect lives in the top of the board, where it is not
sign-stable and where a leakage-safe estimator declines to correct it at all. This module is
therefore built to be *capable of concluding that nothing should ship*, which on the evidence
above is its most likely outcome. That is a result, not a failure.

What varies, and what does not
------------------------------
The draft engine is a constant. This phase adds no scoring term, no positional scarcity, no
replacement or depth multiplier, no positional cap, no round-specific rule and no RB bonus. The
**only** treatment is the projection input, applied at a single point -- immediately after
`load_season_projections` and before `marginal_value_over_replacement` -- so that MSV, static
VORP, replacement levels, scarcity and the D67 demand boundary all see one consistent set of
numbers. Applying it any later would produce an internally inconsistent engine.

Leakage
-------
`fit_arm` raises if any training row belongs to the target season; that is a structural guard,
not a convention. It is safe to fit on a residual from season T in the first place only because
M6's own split already made T's prediction out-of-sample (`models/uncertainty/run.py`: train on
target seasons < S-1, calibrate on S-1, predict S).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import duckdb
import numpy as np

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.opportunity_cost import load_market_ranks
from alpha_squad.league.replacement import load_season_projections, market_draft_demand
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

Arm = str

#: The five pre-registered calibration forms. There is no sixth, and adding one after seeing
#: results is a protocol violation to be reported as a failed phase rather than patched around.
#:
#:   X0  control, no calibration                        p' = p
#:   X1  position-specific additive                     p' = p + b_pos
#:   X2  position-specific affine (multiplicative)      p' = a_pos + b_pos * p
#:   X3  rank/percentile-aware additive                 p' = p + b_{pos,band}
#:   X4  additive shrunk toward zero (empirical Bayes)  p' = p + lambda_pos * b_pos
#:
#: X2 is stated as an affine fit rather than a bare scale factor because that is the form the
#: strongest diagnostic actually speaks to (the QB slope of ~0.444), and because it nests both
#: the pure level shift (b = 1) and the pure multiplicative rescale (a = 0). It is one form, not
#: two -- the OLS calibration regression of realized on projected.
X_ARMS: tuple[Arm, ...] = ("X0", "X1", "X2", "X3", "X4")

PREREGISTERED_X_CONTROL: Arm = "X0"

#: K and DST are excluded from every arm. D57 measured year-over-year K r=0.41 and DST r=0.29
#: and deliberately ships baselines rather than models for them; a bias correction on a signal
#: that weak fits noise. They also carry no `confidence`, so the draft engine already applies a
#: hardcoded risk multiplier to them regardless of what any calibration would say.
CALIBRATED_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: PRE-REGISTERED PRIOR for insufficient evidence. An arm emits **zero adjustment** for a
#: position with fewer than this many distinct training seasons. Two is the minimum at which a
#: between-season variance -- and therefore any honest standard error on the estimate -- exists
#: at all. With one season an estimator cannot distinguish a stable bias from that season.
MIN_TRAINING_SEASONS = 2

#: Matches `models/uncertainty/run.py::MIN_TRAIN_ROWS`. M6 declines to fit a thin position
#: rather than fitting noise; a calibration on top of it adopts the same posture.
MIN_TRAINING_ROWS = 30

#: Consequence of the two rules above, given that M6 predictions exist only for 2021-2025 and
#: cannot be extended backwards (the `ro` board begins in 2020 and `preseason_ecr_rank` is one
#: of M6's four features, so no earlier target season has trainable rows):
#:
#:     target 2021  0 training seasons  -> control by construction
#:     target 2022  1 training season   -> control by construction
#:     target 2023  2 training seasons  -> treated
#:     target 2024  3 training seasons  -> treated
#:     target 2025  4 training seasons  -> treated
#:
#: 20 of the 50 benchmark drafts are therefore IDENTICAL to control by construction, with a
#: paired delta of exactly zero. The primary draft-layer comparison is pre-registered on the
#: treated subset; the full 50 is reported as a secondary figure. Declared here, before
#: measurement, precisely so it cannot look like a subset chosen after the fact.
PREREGISTERED_TREATED_SEASONS: tuple[int, ...] = (2023, 2024, 2025)

#: The earliest season with M6 predictions, and a hard limit rather than a choice. The residual
#: history cannot be extended backwards: `preseason_ecr_rank` is one of M6's four features and
#: the `ro` board only begins in 2020, so no earlier target season has trainable rows. Five
#: residual seasons is the entire universe available to this experiment.
FIRST_RESIDUAL_SEASON = 2021

#: The whole experiment rests on 30 drafts across 3 seasons. That is a mechanism/diagnostic
#: sample, NOT evidence sufficient on its own to declare Alpha superior or inferior to
#: consensus, and no report generated from this module may claim otherwise.
PREREGISTERED_TREATED_DRAFTS = 30


# --------------------------------------------------------------------------------------------
# PRE-REGISTERED GATES -- eight, evaluated in two ordered layers.
#
# Projection layer (G1-G4) is evaluated FIRST, on held-out target seasons. An arm that fails it
# is dropped before any of its draft numbers are looked at, so no calibration parameter can be
# chosen by draft outcome.
#
#   G1  accuracy does not regress. Pooled MAE and RMSE <= control, and MAE worse than control in
#       at most one season.
#   G2  ordering not damaged. Within-position Spearman not decreased in any season, and
#       cross-position Spearman not decreased. X1/X2/X4 are monotone per position and preserve
#       within-position rank identically -- this gate exists to catch X3, whose band edges can
#       invert ranks across a boundary.
#   G3  the bias it targets actually falls. |mean signed residual| reduced at every position the
#       arm adjusts, and not increased at any position it leaves alone.
#   G4  the estimator is stable, not lucky. For every position receiving a non-zero adjustment:
#       the training-fold estimate has the SAME SIGN in every available fold, and the
#       out-of-fold predicted bias correlates positively with the realized bias across treated
#       seasons. This is the gate aimed at the sign-instability in the header table and at the
#       winner's-curse confound in G2's rank conditioning; on the measured evidence RB is
#       expected to FAIL it, and that expectation is recorded here before the run.
#
# Draft layer (G5-G8), only for arms that passed G1-G4.
#
#   G5  primary. Mean realized starter points over the treated subset exceeds X0, with the
#       paired 95% CI vs X0 excluding zero. Significance versus CONSENSUS is reported but is
#       explicitly NOT a gate.
#   G6  robustness. At most one treated season worse than control; leave-one-season-out pooled
#       delta positive in every fold; the out-of-format rerun on `legacy_2qb_dynasty`, rule
#       unchanged, is not negative.
#   G7  structural validity preserved. Zero drafts with no player at a mandatory position; zero
#       unfilled mandatory starting slots; every roster exactly `roster_size`; feasibility-cap
#       breaches not increased above the control's.
#   G8  no disguised positional bonus. No position's mean roster count moves by more than
#       PREREGISTERED_MAX_ROSTER_COUNT_SHIFT players, and no position's first-pick round moves
#       by more than PREREGISTERED_MAX_ROUNDS_SHIFT rounds, versus control. An arm that "works"
#       by simply buying RBs two rounds earlier is an unprincipled positional bonus wearing a
#       calibration's clothes, and this gate rejects it on structure regardless of its score.
#
# SELECTION RULE: ship the LOWEST-NUMBERED arm clearing all eight gates; ties break to the lower
# number (Occam, the project's standing rule since D63). If no arm clears them, NOTHING ships,
# production stays on the D67 W1 engine unchanged, and the phase reports that the positional
# bias is not reliably calibratable -- which the diagnostics say is the expected outcome.
# --------------------------------------------------------------------------------------------

#: G1: seasons in which an arm's MAE may be worse than control's.
PREREGISTERED_MAX_WORSE_MAE_SEASONS = 1
#: G6: treated seasons in which an arm's starter points may be worse than control's.
PREREGISTERED_MAX_WORSE_SEASONS = 1
#: G8: reused verbatim from the N-/W-tier rules so the timing gate means the same thing here.
PREREGISTERED_MAX_ROUNDS_SHIFT = 2.0
#: G8: mean players drafted at a position may not move by more than this versus control.
PREREGISTERED_MAX_ROSTER_COUNT_SHIFT = 1.0


# --------------------------------------------------------------------------------------------
# Estimation universe and rank bands -- both DERIVED FROM THE LEAGUE, never chosen.
# --------------------------------------------------------------------------------------------


def season_demand(
    con: duckdb.DuckDBPyConnection, league: LeagueContext, season: int
) -> dict[str, float]:
    """{position: players a full draft of this league consumes at it, per team} for `season`.

    Delegates to the shipped D67 production function `league/replacement.py::
    market_draft_demand`, which runs one mock draft of this league on the season's preseason
    consensus board and counts positions. It sums to `roster_size` by construction and has no
    free parameter, and `load_market_ranks` is already restricted to the season's own Jul/Aug
    snapshots (D54), so this is leakage-safe."""
    ecr_type = resolve_market_series(league).ecr_type
    projections, positions = load_season_projections(con, season)
    market_rank = load_market_ranks(con, ecr_type, season)
    return market_draft_demand(league, market_rank, projections, positions)


def draftable_depth(league: LeagueContext, demand: dict[str, float], position: str) -> int:
    """How many players at `position` a full draft consumes, league-wide.

    **This is the estimation universe for every arm.** Adjusting players nobody drafts cannot
    change a draft, and including them would drown the estimate in hundreds of near-zero
    residuals from deep-bench players -- which is exactly how the unconditional RB mean (+10.3)
    and median (-0.7) came to disagree. Using the count a draft actually consumes keeps the
    estimate on the population the draft engine is choosing between, and reuses D67's
    parameter-free quantity rather than inventing a cut."""
    return max(1, int(round(league.teams * demand.get(position, 0.0))))


def band_edges(league: LeagueContext, demand: dict[str, float]) -> dict[str, tuple[int, int]]:
    """{position: (end of band 1, end of band 2)} in 1-based within-position projection rank.

    **Derived from the league config, never hardcoded.** Band 1 is the league's dedicated
    starting slots at the position (`teams x dedicated_slots`); band 2 runs to the full draft
    consumption (`teams x demand`); band 3 is everything beyond, which no arm adjusts because
    no draft reaches it. Hardcoding these edges would reintroduce exactly the format-bound
    constant D58 removed and the tuned constant D66/D67 removed, so a test asserts they move
    when the league config does."""
    dedicated = league.dedicated_slots()
    edges: dict[str, tuple[int, int]] = {}
    for position in CALIBRATED_POSITIONS:
        full = draftable_depth(league, demand, position)
        top = league.teams * dedicated.get(position, 0)
        top = max(1, min(top, full)) if top > 0 else max(1, full // 2)
        edges[position] = (top, full)
    return edges


def band_of(rank: int, edges: tuple[int, int]) -> int:
    """1, 2 or 3 for a 1-based within-position projection rank."""
    top, full = edges
    if rank <= top:
        return 1
    if rank <= full:
        return 2
    return 3


# --------------------------------------------------------------------------------------------
# Residual dataset
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidualRow:
    """One (player, season) M6 prediction against its realized outcome.

    Restricted to the M6 path (`uncertainty_predictions` at the production model version)
    because that is the estimand: the rookie model and the K/DST baselines are different
    estimators with different biases, and pooling them would blend three populations into one
    parameter. The adjustment is nevertheless *applied* to every player at the position, so the
    board stays internally coherent -- a known and recorded asymmetry."""

    season: int
    player_id: str
    position: str
    projected: float
    realized: float
    pos_rank: int  # 1-based, within position, by projection descending
    band: int  # 1, 2 or 3 per `band_of`

    @property
    def residual(self) -> float:
        """Realized minus projected. Positive = the model under-projected this player."""
        return self.realized - self.projected


def load_residual_rows(
    con: duckdb.DuckDBPyConnection, league: LeagueContext, seasons: list[int]
) -> list[ResidualRow]:
    """Every M6 prediction in `seasons` paired with its realized PPR total, ranked and banded.

    Ordered deterministically by (season, position, rank, player_id) so two processes build
    identical parameters from identical inputs."""
    rows: list[ResidualRow] = []
    for season in sorted(seasons):
        _, positions = load_season_projections(con, season)
        edges = band_edges(league, season_demand(con, league, season))
        records = con.execute(
            """
            SELECT u.player_id, u.point_prediction, s.total_fantasy_points_ppr, s.position
            FROM uncertainty_predictions u
            JOIN player_season_stats s
              ON u.player_id = s.player_id AND u.season = s.season
            WHERE u.season = ?
              AND u.model_version = ?
              AND u.point_prediction IS NOT NULL
              AND s.total_fantasy_points_ppr IS NOT NULL
            ORDER BY u.player_id
            """,
            [season, UNCERTAINTY_MODEL_VERSION],
        ).fetchall()

        by_position: dict[str, list[tuple[str, float, float]]] = {}
        for player_id, projected, realized, stats_position in records:
            position = positions.get(player_id, stats_position)
            if position not in CALIBRATED_POSITIONS:
                continue
            by_position.setdefault(position, []).append(
                (player_id, float(projected), float(realized))
            )

        for position, entries in sorted(by_position.items()):
            entries.sort(key=lambda e: (-e[1], e[0]))
            for index, (player_id, projected, realized) in enumerate(entries, start=1):
                rows.append(
                    ResidualRow(
                        season=season,
                        player_id=player_id,
                        position=position,
                        projected=projected,
                        realized=realized,
                        pos_rank=index,
                        band=band_of(index, edges[position]),
                    )
                )
    return rows


# --------------------------------------------------------------------------------------------
# Fitted parameters
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionFit:
    """What one arm estimated for one position, plus everything needed to audit it.

    `is_identity` is the honest headline: an arm that declined to adjust a position -- because
    the evidence was too thin (the eligibility prior), because shrinkage zeroed it, or because
    the fit was degenerate -- reports that here rather than emitting a silent zero that reads
    like a measured absence of bias."""

    position: str
    intercept: float = 0.0  # `a` in p' = a + b*p ; 0.0 for the additive arms
    slope: float = 1.0  # `b` in p' = a + b*p ; 1.0 for the additive arms
    offsets: dict[int, float] = field(default_factory=dict)  # band -> additive offset
    lam: float | None = None  # empirical-Bayes shrinkage weight, X4 only
    n_rows: int = 0
    n_seasons: int = 0
    season_means: dict[int, float] = field(default_factory=dict)
    reason: str = ""  # why it is identity, when it is

    @property
    def is_identity(self) -> bool:
        return (
            self.intercept == 0.0
            and self.slope == 1.0
            and all(value == 0.0 for value in self.offsets.values())
        )

    def adjust(self, projection: float, band: int) -> float:
        return self.intercept + self.slope * projection + self.offsets.get(band, 0.0)


@dataclass(frozen=True)
class CalibrationParameters:
    """One arm, fitted for one target season. Immutable and fully auditable."""

    arm: Arm
    target_season: int
    training_seasons: tuple[int, ...]
    fits: dict[str, PositionFit]

    @property
    def is_identity(self) -> bool:
        return all(fit.is_identity for fit in self.fits.values())


def _identity(position: str, reason: str, n_rows: int, n_seasons: int) -> PositionFit:
    return PositionFit(position=position, reason=reason, n_rows=n_rows, n_seasons=n_seasons)


def _eligible(rows: list[ResidualRow]) -> tuple[bool, str]:
    """The pre-registered evidence prior, applied identically by every arm."""
    seasons = {row.season for row in rows}
    if len(seasons) < MIN_TRAINING_SEASONS:
        return False, f"only {len(seasons)} training season(s), need {MIN_TRAINING_SEASONS}"
    if len(rows) < MIN_TRAINING_ROWS:
        return False, f"only {len(rows)} training rows, need {MIN_TRAINING_ROWS}"
    return True, ""


def _season_means(rows: list[ResidualRow]) -> dict[int, float]:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(row.season, []).append(row.residual)
    return {season: float(np.mean(values)) for season, values in sorted(grouped.items())}


def _shrinkage_weight(rows: list[ResidualRow]) -> tuple[float, float, float, float]:
    """Empirical-Bayes weight toward a prior of ZERO: `lambda = tau^2 / (tau^2 + se^2)`.

    The quantity being predicted is next season's positional bias, from `k` past seasons whose
    means are `m_1..m_k` with within-season sampling variances `s_1^2..s_k^2`:

        estimate  b_hat = mean(m_i)
        prior     the true bias is drawn around zero with variance
                  tau^2 = max(0, mean(m_i^2) - mean(s_i^2))          (method of moments)
        noise     predicting a NEW season's draw carries
                  se^2  = var(m_i) * (1 + 1/k)                       (predictive variance)
        weight    lambda = tau^2 / (tau^2 + se^2)

    Read plainly: lambda is the share of the observed positional effect that survives once the
    effect's own instability between seasons is charged against it. Seasons that agree push
    lambda toward 1; seasons that disagree push it toward 0 and the arm declines to correct.

    **Why `mean(m_i^2)` and not the variance of the means.** A prior centred on zero asks how
    big the true bias is in absolute terms, which is a second moment about zero. Using the
    variance about the observed mean instead produces a perverse estimator: five seasons that
    all agree on +20 have zero between-season variance and would shrink to zero -- the
    strongest possible evidence of a stable bias, discarded. That defect was caught by
    `TestShrinkageArm::test_no_between_season_variation_keeps_the_estimate` while writing the
    pre-registration, before any arm had been fitted against real data, and the form above is
    what was committed. The exploratory diagnostic that motivated this phase used the defective
    form, so its reported lambdas are superseded by whatever this one measures.

    Returns `(lambda, estimate, tau_squared, se_squared)`."""
    means = _season_means(rows)
    k = len(means)
    estimate = float(np.mean(list(means.values()))) if means else 0.0
    if k < MIN_TRAINING_SEASONS:
        return 0.0, estimate, 0.0, float("inf")

    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(row.season, []).append(row.residual)
    within = [
        float(np.var(values, ddof=1)) / len(values)
        for values in grouped.values()
        if len(values) > 1
    ]
    mean_within = float(np.mean(within)) if within else 0.0

    observed = list(means.values())
    tau_squared = max(0.0, float(np.mean(np.square(observed))) - mean_within)
    se_squared = float(np.var(observed, ddof=1)) * (1.0 + 1.0 / k)
    if tau_squared <= 0.0:
        return 0.0, estimate, tau_squared, se_squared
    if se_squared <= 0.0:
        return 1.0, estimate, tau_squared, se_squared
    return float(tau_squared / (tau_squared + se_squared)), estimate, tau_squared, se_squared


def fit_arm(
    arm: Arm,
    rows: list[ResidualRow],
    target_season: int,
) -> CalibrationParameters:
    """Fit `arm` for `target_season` using ONLY residuals from strictly earlier seasons.

    Raises if `rows` contains the target season or anything later. This is the leakage guard,
    and it is structural rather than a convention someone has to remember: the function cannot
    see the target season's outcomes because it refuses to run when handed them."""
    if arm not in X_ARMS:
        raise ValueError(f"unknown calibration arm {arm!r}; expected one of {X_ARMS}")
    leaked = sorted({row.season for row in rows if row.season >= target_season})
    if leaked:
        raise ValueError(
            f"leakage: fitting {arm} for target season {target_season} was handed training "
            f"rows from season(s) {leaked}. A calibration may only ever see strictly earlier "
            f"seasons."
        )

    training_seasons = tuple(sorted({row.season for row in rows}))
    fits: dict[str, PositionFit] = {}
    for position in CALIBRATED_POSITIONS:
        # Sorted so the arithmetic below runs over an identical sequence regardless of the
        # order the caller assembled `rows` in -- floating-point summation is not commutative,
        # and two processes must produce byte-identical parameters.
        pool = sorted(
            (row for row in rows if row.position == position and row.band in (1, 2)),
            key=lambda row: (row.season, row.pos_rank, row.player_id),
        )
        n_rows, n_seasons = len(pool), len({row.season for row in pool})
        if arm == "X0":
            fits[position] = _identity(position, "control arm", n_rows, n_seasons)
            continue
        ok, why = _eligible(pool)
        if not ok:
            fits[position] = _identity(position, why, n_rows, n_seasons)
            continue
        fits[position] = _FITTERS[arm](position, pool, n_rows, n_seasons)

    return CalibrationParameters(
        arm=arm,
        target_season=target_season,
        training_seasons=training_seasons,
        fits=fits,
    )


def _fit_additive(
    position: str, pool: list[ResidualRow], n_rows: int, n_seasons: int
) -> PositionFit:
    """X1: `p' = p + b_pos`, `b_pos` the mean residual over the draftable universe.

    The mean is taken over per-season means rather than pooled rows so a season with more
    qualifying players does not outweigh a season with fewer -- the variation being corrected is
    between seasons, so that is the level the estimate belongs at."""
    means = _season_means(pool)
    estimate = float(np.mean(list(means.values())))
    return PositionFit(
        position=position,
        offsets={1: estimate, 2: estimate},
        n_rows=n_rows,
        n_seasons=n_seasons,
        season_means=means,
    )


def _fit_affine(position: str, pool: list[ResidualRow], n_rows: int, n_seasons: int) -> PositionFit:
    """X2: `p' = a_pos + b_pos * p`, the OLS calibration regression of realized on projected.

    A slope below 1 means the projections are too spread out (elite over-projected, low
    under-projected); above 1, too compressed. This is a DISPERSION correction and is a
    different mathematical object from a level shift, which is why it gets its own arm rather
    than being folded into X1.

    A non-positive slope would invert the position's board -- pathological rather than
    calibrated -- so the arm declines instead."""
    projected = np.array([row.projected for row in pool], dtype=float)
    realized = np.array([row.realized for row in pool], dtype=float)
    centred = projected - projected.mean()
    denominator = float(np.dot(centred, centred))
    if denominator <= 0.0:
        return _identity(position, "no variance in projections", n_rows, n_seasons)
    # Closed form rather than `np.polyfit`: least-squares solvers are free to reorder work and
    # were measured to disagree in the last two decimal places on identically-valued inputs
    # supplied in different orders, which would break the determinism gate.
    slope = float(np.dot(centred, realized - realized.mean()) / denominator)
    intercept = float(realized.mean() - slope * projected.mean())
    if not math.isfinite(slope) or not math.isfinite(intercept) or slope <= 0.0:
        return _identity(position, f"degenerate slope {slope:.4f}", n_rows, n_seasons)
    return PositionFit(
        position=position,
        intercept=float(intercept),
        slope=float(slope),
        n_rows=n_rows,
        n_seasons=n_seasons,
        season_means=_season_means(pool),
    )


def _fit_rank_aware(
    position: str, pool: list[ResidualRow], n_rows: int, n_seasons: int
) -> PositionFit:
    """X3: `p' = p + b_{pos,band}`, one additive offset per league-derived rank band.

    This is the form that matches the measured shape of the RB effect (top of the board biased,
    middle and bottom not). It is also the form most exposed to the winner's-curse confound:
    conditioning on projection RANK guarantees a positive expected residual at the top of any
    noisy ranking, bias or no bias. G4 exists to test that, and an X3 that passes only in band 1
    is a pre-registered abandonment condition rather than a finding.

    A band with too little evidence gets zero, independently of the other bands."""
    offsets: dict[int, float] = {}
    for band in (1, 2):
        band_rows = [row for row in pool if row.band == band]
        ok, _ = _eligible(band_rows)
        offsets[band] = float(np.mean(list(_season_means(band_rows).values()))) if ok else 0.0
    return PositionFit(
        position=position,
        offsets=offsets,
        n_rows=n_rows,
        n_seasons=n_seasons,
        season_means=_season_means(pool),
    )


def _fit_shrunk(position: str, pool: list[ResidualRow], n_rows: int, n_seasons: int) -> PositionFit:
    """X4: `p' = p + lambda_pos * b_pos`, X1's estimate shrunk toward zero by empirical Bayes.

    Expected, before running, to collapse to the control on RB and WR -- the walk-forward
    diagnostics put lambda at 0.00 for RB in 2022/2023/2024 and for WR in every year. If X4
    clears the gates and X1 does not, the honest reading is that the only defensible correction
    is the one that mostly declines to correct, and that is a legitimate result rather than a
    reason to prefer the unshrunk arm."""
    lam, estimate, _tau, _se = _shrinkage_weight(pool)
    shrunk = lam * estimate
    return PositionFit(
        position=position,
        offsets={1: shrunk, 2: shrunk},
        lam=lam,
        n_rows=n_rows,
        n_seasons=n_seasons,
        season_means=_season_means(pool),
        reason="" if shrunk != 0.0 else f"shrunk to zero (lambda={lam:.4f})",
    )


_FITTERS = {
    "X1": _fit_additive,
    "X2": _fit_affine,
    "X3": _fit_rank_aware,
    "X4": _fit_shrunk,
}


# --------------------------------------------------------------------------------------------
# Application -- the single insertion point
# --------------------------------------------------------------------------------------------


def apply_calibration(
    params: CalibrationParameters,
    projections: dict[str, float],
    positions: dict[str, str],
    edges: dict[str, tuple[int, int]],
) -> dict[str, float]:
    """Return a new projections dict with `params` applied. Never mutates its input.

    Applied to every player at a calibrated position, not only to those in the estimation
    universe: a level or affine statement about a position that held only for its top 46 players
    would put a discontinuity in the middle of the board. Players at K, DST or any position no
    arm calibrates pass through untouched, as do players with no position."""
    if params.is_identity:
        return dict(projections)

    ranked: dict[str, list[str]] = {}
    for player_id, position in positions.items():
        if position in CALIBRATED_POSITIONS and player_id in projections:
            ranked.setdefault(position, []).append(player_id)

    calibrated = dict(projections)
    for position, player_ids in ranked.items():
        fit = params.fits.get(position)
        if fit is None or fit.is_identity:
            continue
        player_ids.sort(key=lambda pid: (-projections[pid], pid))
        position_edges = edges.get(position, (len(player_ids), len(player_ids)))
        for index, player_id in enumerate(player_ids, start=1):
            calibrated[player_id] = fit.adjust(
                projections[player_id], band_of(index, position_edges)
            )
    return calibrated


def calibrated_season_projections(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    arm: Arm,
    *,
    residual_rows: list[ResidualRow] | None = None,
) -> tuple[dict[str, float], dict[str, str], CalibrationParameters]:
    """`load_season_projections`, with `arm` fitted walk-forward and applied.

    The single insertion point for the whole experiment. `residual_rows` may be supplied to
    avoid reloading the residual history per call; it is filtered to strictly earlier seasons
    here regardless of what the caller passes, and `fit_arm` raises if that filter ever fails."""
    projections, positions = load_season_projections(con, season)
    if residual_rows is None:
        history = list(range(FIRST_RESIDUAL_SEASON, season))
        residual_rows = load_residual_rows(con, league, history) if history else []
    training = [row for row in residual_rows if row.season < season]
    params = fit_arm(arm, training, season)
    edges = band_edges(league, season_demand(con, league, season))
    return apply_calibration(params, projections, positions, edges), positions, params


# --------------------------------------------------------------------------------------------
# Projection-layer measurement (gates G1-G4)
# --------------------------------------------------------------------------------------------


def _universe(rows: list[ResidualRow]) -> list[ResidualRow]:
    """The evaluated population: bands 1 and 2, i.e. the players a draft actually consumes.

    Membership is fixed by the UNCALIBRATED rank (`ResidualRow.band` is computed from M6's own
    output), so every arm is scored on exactly the same set of players and an arm cannot improve
    its own metrics by reshuffling who counts as draftable."""
    return [row for row in rows if row.band in (1, 2)]


def _spearman(xs: list[float], ys: list[float]) -> float:
    from scipy import stats

    if len(xs) < 3:
        return float("nan")
    value = stats.spearmanr(xs, ys).statistic
    return float(value) if value == value else float("nan")


def measure_arm_season(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    arm: Arm,
    residual_rows: list[ResidualRow],
) -> dict:
    """Projection-layer metrics for one arm on one held-out target season.

    Everything here is measured against realized outcomes for `season`, which the arm's
    parameters were forbidden to see -- `fit_arm` raises if they did."""
    season_rows = _universe([row for row in residual_rows if row.season == season])
    training = [row for row in residual_rows if row.season < season]
    params = fit_arm(arm, training, season)

    all_season = [row for row in residual_rows if row.season == season]
    full_projections = {row.player_id: row.projected for row in all_season}
    full_positions = {row.player_id: row.position for row in all_season}
    edges = band_edges(league, season_demand(con, league, season))
    calibrated = apply_calibration(params, full_projections, full_positions, edges)

    errors, signed, by_position = [], [], {}
    for row in season_rows:
        value = calibrated[row.player_id]
        error = row.realized - value
        errors.append(abs(error))
        signed.append(error)
        by_position.setdefault(row.position, []).append((value, row.realized, error))

    stability = sign_stability(residual_rows, season)
    rows_by_position: dict[str, list[ResidualRow]] = {}
    for row in season_rows:
        rows_by_position.setdefault(row.position, []).append(row)

    positional = {}
    for position, entries in sorted(by_position.items()):
        values = [e[0] for e in entries]
        realized = [e[1] for e in entries]
        residuals = [e[2] for e in entries]
        fit = params.fits.get(position)
        adjustments = [
            calibrated[row.player_id] - row.projected for row in rows_by_position[position]
        ]
        positional[position] = {
            "n": len(entries),
            "mean_signed_residual": float(np.mean(residuals)),
            "median_signed_residual": float(np.median(residuals)),
            "mae": float(np.mean(np.abs(residuals))),
            "spearman_within_position": _spearman(values, realized),
            "implied_mean_adjustment": float(np.mean(adjustments)) if adjustments else 0.0,
            "fit_is_identity": fit.is_identity if fit is not None else True,
            "fit_reason": fit.reason if fit is not None else "",
            "fit_sign_stable": bool(stability[position]["sign_stable"]),
            "training_season_means": dict(stability[position]["season_means"]),
            "lambda": fit.lam if fit is not None else None,
            "slope": fit.slope if fit is not None else 1.0,
        }

    return {
        "arm": arm,
        "season": season,
        "training_seasons": list(params.training_seasons),
        "is_identity": params.is_identity,
        "n": len(season_rows),
        "mae": float(np.mean(errors)) if errors else float("nan"),
        "rmse": float(np.sqrt(np.mean(np.square(signed)))) if signed else float("nan"),
        "mean_signed_residual": float(np.mean(signed)) if signed else float("nan"),
        "spearman_cross_position": _spearman(
            [calibrated[row.player_id] for row in season_rows],
            [row.realized for row in season_rows],
        ),
        "by_position": positional,
    }


def evaluate_projection_layer(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    seasons: list[int],
    arms: tuple[Arm, ...] = X_ARMS,
) -> dict:
    """Run every arm over every target season and apply gates G1-G4.

    Gates are evaluated on the TREATED seasons only -- on 2021 and 2022 every arm is the control
    by construction (the eligibility prior), so including them would dilute every comparison
    with pairs whose difference is identically zero."""
    residual_rows = load_residual_rows(con, league, seasons)
    measurements = {
        arm: [measure_arm_season(con, league, season, arm, residual_rows) for season in seasons]
        for arm in arms
    }
    treated = [s for s in seasons if s in PREREGISTERED_TREATED_SEASONS]
    control = {m["season"]: m for m in measurements[PREREGISTERED_X_CONTROL]}

    verdicts = {}
    for arm in arms:
        rows = {m["season"]: m for m in measurements[arm]}
        treated_rows = [rows[s] for s in treated]
        control_rows = [control[s] for s in treated]
        verdicts[arm] = _gate_projection_layer(arm, treated_rows, control_rows)

    return {
        "seasons": list(seasons),
        "treated_seasons": treated,
        "measurements": measurements,
        "gates": verdicts,
        "survivors": [a for a in arms if a != PREREGISTERED_X_CONTROL and verdicts[a]["passes"]],
    }


def _gate_projection_layer(arm: Arm, treated: list[dict], control: list[dict]) -> dict:
    """G1-G4 for one arm, each reported with the number that decided it."""
    if arm == PREREGISTERED_X_CONTROL:
        return {"arm": arm, "passes": False, "detail": "control arm, not a candidate", "gates": {}}
    if all(row["is_identity"] for row in treated):
        return {
            "arm": arm,
            "passes": False,
            "detail": "identity on every treated season -- the evidence prior or shrinkage "
            "zeroed it, so there is nothing to ship",
            "gates": {},
        }

    mae = float(np.mean([r["mae"] for r in treated]))
    control_mae = float(np.mean([r["mae"] for r in control]))
    rmse = float(np.mean([r["rmse"] for r in treated]))
    control_rmse = float(np.mean([r["rmse"] for r in control]))
    worse_mae = sum(1 for a, b in zip(treated, control, strict=True) if a["mae"] > b["mae"])
    g1 = (
        mae <= control_mae
        and rmse <= control_rmse
        and worse_mae <= PREREGISTERED_MAX_WORSE_MAE_SEASONS
    )

    g2 = True
    for arm_row, ctl_row in zip(treated, control, strict=True):
        if arm_row["spearman_cross_position"] < ctl_row["spearman_cross_position"] - 1e-12:
            g2 = False
        for position, stats_ in arm_row["by_position"].items():
            ctl = ctl_row["by_position"].get(position)
            if ctl is None:
                continue
            if stats_["spearman_within_position"] < ctl["spearman_within_position"] - 1e-12:
                g2 = False

    g3 = True
    for arm_row, ctl_row in zip(treated, control, strict=True):
        for position, stats_ in arm_row["by_position"].items():
            ctl = ctl_row["by_position"].get(position)
            if ctl is None:
                continue
            adjusted = not stats_["fit_is_identity"]
            arm_bias, ctl_bias = (
                abs(stats_["mean_signed_residual"]),
                abs(ctl["mean_signed_residual"]),
            )
            if adjusted and arm_bias > ctl_bias + 1e-9:
                g3 = False
            if not adjusted and arm_bias > ctl_bias + 1e-9:
                g3 = False

    # G4 has two independent halves and BOTH must hold: every adjusted position's walk-forward
    # estimate must carry the same sign in every training fold, and the out-of-fold predicted
    # bias must correlate positively with the bias that actually materialised.
    g4 = True
    unstable: list[str] = []
    predicted, realized = [], []
    for arm_row, ctl_row in zip(treated, control, strict=True):
        for position, stats_ in arm_row["by_position"].items():
            if stats_["fit_is_identity"]:
                continue
            if not stats_["fit_sign_stable"]:
                g4 = False
                label = f"{position}@{arm_row['season']}"
                if label not in unstable:
                    unstable.append(label)
            predicted.append(stats_["implied_mean_adjustment"])
            realized.append(ctl_row["by_position"][position]["mean_signed_residual"])
    if len(predicted) >= 3 and float(np.var(predicted)) > 0.0:
        correlation = float(np.corrcoef(predicted, realized)[0, 1])
    else:
        correlation = float("nan")
    if not (correlation > 0.0):
        g4 = False

    return {
        "arm": arm,
        "passes": bool(g1 and g2 and g3 and g4),
        "gates": {
            "G1_accuracy": {
                "passes": bool(g1),
                "mae": mae,
                "control_mae": control_mae,
                "rmse": rmse,
                "control_rmse": control_rmse,
                "seasons_worse_mae": worse_mae,
            },
            "G2_ordering": {"passes": bool(g2)},
            "G3_bias_falls": {"passes": bool(g3)},
            "G4_estimator_stable": {
                "passes": bool(g4),
                "out_of_fold_correlation": correlation,
                "n_points": len(predicted),
                "sign_unstable_positions": unstable,
            },
        },
    }


def sign_stability(rows: list[ResidualRow], target_season: int) -> dict[str, dict]:
    """Per-position sign stability of the walk-forward estimate, the core of G4.

    Reported separately from the gate so a reader can see WHY an arm failed rather than only
    that it did: an estimate whose per-season means flip sign is not a bias being measured with
    noise, it is a phenomenon that is not stationary, and no amount of shrinkage rescues it --
    shrinkage only decides how loudly to say nothing."""
    training = [row for row in rows if row.season < target_season]
    out: dict[str, dict] = {}
    for position in CALIBRATED_POSITIONS:
        pool = [r for r in training if r.position == position and r.band in (1, 2)]
        means = _season_means(pool)
        signs = {1 if v > 0 else (-1 if v < 0 else 0) for v in means.values()}
        lam, estimate, tau_squared, se_squared = _shrinkage_weight(pool)
        out[position] = {
            "season_means": means,
            "sign_stable": len(signs) <= 1 and len(means) > 0,
            "estimate": estimate,
            "lambda": lam,
            "tau_squared": tau_squared,
            "se_squared": se_squared,
        }
    return out


def render_report(result: dict, stability: dict[int, dict[str, dict]]) -> str:
    """Markdown for `reports/projection_calibration.md`.

    Written so a reader can REJECT an arm without re-running anything: every gate prints the
    number that decided it, and every position prints the per-season estimates the walk-forward
    fit was built from."""
    lines: list[str] = [
        "# D68 -- walk-forward projection calibration: projection layer",
        "",
        "Pre-registered arms, estimators, evidence prior and gates: "
        "`src/alpha_squad/evaluation/projection_calibration.py`, committed before any arm was "
        "fitted against real data.",
        "",
        f"Seasons measured: {result['seasons']}. "
        f"**Treated seasons: {result['treated_seasons']}** -- earlier seasons have too few "
        "training folds to clear the evidence prior, so every arm is the control there by "
        "construction.",
        "",
        "> This is a mechanism/diagnostic experiment. The treated sample is "
        f"{len(result['treated_seasons'])} seasons; nothing here is sufficient on its own to "
        "declare Alpha superior or inferior to consensus.",
        "",
        "## Gates G1-G4",
        "",
        "| arm | G1 accuracy | G2 ordering | G3 bias falls | G4 estimator stable | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for arm, verdict in result["gates"].items():
        if not verdict["gates"]:
            lines.append(f"| {arm} | -- | -- | -- | -- | {verdict['detail']} |")
            continue
        marks = {
            key: ("PASS" if entry["passes"] else "**FAIL**")
            for key, entry in verdict["gates"].items()
        }
        lines.append(
            f"| {arm} | {marks['G1_accuracy']} | {marks['G2_ordering']} | "
            f"{marks['G3_bias_falls']} | {marks['G4_estimator_stable']} | "
            f"{'**PASSES**' if verdict['passes'] else 'rejected'} |"
        )

    lines += [
        "",
        "### G1 detail (mean over treated seasons)",
        "",
        "| arm | MAE | control MAE | RMSE | control RMSE | seasons worse |",
        "|---|---|---|---|---|---|",
    ]
    for arm, verdict in result["gates"].items():
        if not verdict["gates"]:
            continue
        g1 = verdict["gates"]["G1_accuracy"]
        lines.append(
            f"| {arm} | {g1['mae']:.2f} | {g1['control_mae']:.2f} | {g1['rmse']:.2f} | "
            f"{g1['control_rmse']:.2f} | {g1['seasons_worse_mae']} |"
        )

    lines += [
        "",
        "### G4 detail -- out-of-fold correlation and sign stability",
        "",
        "| arm | out-of-fold corr | n points | sign-unstable |",
        "|---|---|---|---|",
    ]
    for arm, verdict in result["gates"].items():
        if not verdict["gates"]:
            continue
        g4 = verdict["gates"]["G4_estimator_stable"]
        unstable = ", ".join(g4["sign_unstable_positions"]) or "none"
        lines.append(
            f"| {arm} | {g4['out_of_fold_correlation']:.3f} | {g4['n_points']} | {unstable} |"
        )

    lines += [
        "",
        "## Walk-forward estimate, by target season and position",
        "",
        "`sign stable` is half of G4: an estimate whose per-season means flip sign is not a "
        "bias measured with noise, it is a phenomenon that is not stationary.",
        "",
        "| target | pos | per-season training means | estimate | lambda | sign stable |",
        "|---|---|---|---|---|---|",
    ]
    for season in sorted(stability):
        for position, entry in stability[season].items():
            means = ", ".join(f"{s}:{v:+.1f}" for s, v in sorted(entry["season_means"].items()))
            lines.append(
                f"| {season} | {position} | {means or '(none)'} | {entry['estimate']:+.1f} | "
                f"{entry['lambda']:.3f} | {'yes' if entry['sign_stable'] else '**NO**'} |"
            )

    lines += ["", "## Per-arm, per-season, per-position measurement", ""]
    for arm, measurements in result["measurements"].items():
        lines += [
            f"### {arm}",
            "",
            "| season | identity | MAE | RMSE | cross-pos rho | "
            "QB bias | RB bias | WR bias | TE bias |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for row in measurements:
            biases = [
                f"{row['by_position'][p]['mean_signed_residual']:+.1f}"
                if p in row["by_position"]
                else "--"
                for p in CALIBRATED_POSITIONS
            ]
            lines.append(
                f"| {row['season']} | {'yes' if row['is_identity'] else 'no'} | "
                f"{row['mae']:.2f} | {row['rmse']:.2f} | "
                f"{row['spearman_cross_position']:.3f} | " + " | ".join(biases) + " |"
            )
        lines.append("")

    lines += [
        "## Selection",
        "",
        f"Arms clearing G1-G4: **{result['survivors'] or 'none'}**.",
        "",
        "Pre-registered rule: only these proceed to the draft layer (G5-G8), and the "
        "lowest-numbered arm clearing all eight ships. If none clears them, nothing ships and "
        "production stays on the D67 W1 engine unchanged.",
        "",
    ]
    return "\n".join(lines)
