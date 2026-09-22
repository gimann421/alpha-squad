"""The copula null: what SHOULD a board's top-10 look like, given only its overall order? (W5)

Why this module is the centre of W5
-----------------------------------
"Correlation among the predicted top-K" is computed on a subgroup **selected by the predictor**,
so it is attenuated by range restriction whether or not the model has any top-specific defect.
Comparing it against the full-board correlation therefore cannot show that ranking quality
"collapses at the top" -- a perfectly uniform ranker shows the same drop.

This module builds the missing comparison. For a cell it draws synthetic rankings that have
**exactly the board's own overall Spearman** and *no* top-specific structure, then scores them
with the same frozen metric suite. The difference between what Alpha actually did at depth K and
what those draws did at depth K is the part of the top-of-board result that is **not** already
implied by how well Alpha orders the whole board.

Construction
------------
Given realized values `y` (n players) and a target rank correlation `rho`:

1. `z = Phi^-1( (rank(y) - 0.5) / n )` -- the realized values on a normal scale, ties averaged.
2. `s = rho_p * z + sqrt(1 - rho_p^2) * e`, `e ~ N(0,1)` independent.
3. Rank by `s`.

`rho_p` is the *Pearson* correlation of the latent pair. For a bivariate normal the induced
Spearman is `(6/pi) * arcsin(rho_p/2)`, and `pearson_for_spearman` inverts that -- setting
`rho_p = rho` instead lands ~0.025 low at rho = 0.65, larger than several of W4's reported
effects.

That inversion is necessary but **not sufficient**, because realized weekly points are heavily
tied and a tie-corrected Spearman against a tied vector is attenuated further (another ~0.007 to
~0.015, increasing as rho falls). That residual runs in the most dangerous possible direction: it
would hand the null a *worse* board than Alpha's and make Alpha look better at the top than it
is, which is precisely the pre-registered answer this phase predicts. `calibrate_latent`
therefore bisects the latent correlation per cell, against that cell's own tie structure, until
the achieved Spearman matches the target. The calibration is asserted by test, not assumed.

Determinism
-----------
Seeded from `(season, week, position, draw)` with a stable hash, never from `random` state, so a
rerun is byte-identical and two cells cannot accidentally share a draw.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Draws per cell. Fixed in `docs/weekly/W5_PREREGISTRATION.md` §5 before any result existed.
N_SIM = 200


def _norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.15e-9).

    Hand-implemented for the same reason `diagnostics.wilcoxon_signed_rank` is: the value enters
    a reported number, so it should be inspectable here rather than depend on which SciPy version
    a future environment resolves."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


def pearson_for_spearman(rho_s: float) -> float:
    """Latent Pearson correlation giving Spearman `rho_s` under a bivariate normal.

    Inverts `rho_s = (6/pi) * arcsin(rho_p / 2)`. Clamped to [-1, 1] because a cell's measured
    Spearman can sit a hair outside the representable range after tie correction."""
    x = max(-1.0, min(1.0, rho_s)) * math.pi / 6.0
    return max(-1.0, min(1.0, 2.0 * math.sin(x)))


def normal_scores(values: list[float]) -> list[float]:
    """Van der Waerden scores: the values mapped to a normal scale through their average ranks.

    Average ranks matter here for the same reason they matter in `metrics.spearman` -- realized
    weekly points tie constantly, and a competition rank would give tied players different latent
    positions and quietly inflate the achievable correlation."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [_norm_ppf((r - 0.5) / n) for r in ranks]


class _Rng:
    """A tiny, explicit PRNG (splitmix64 + Box-Muller).

    `random.Random` would do, but its stream is a Python implementation detail; this one is
    written out so a byte-identical rerun does not depend on the interpreter version, which is
    what the determinism gate actually promises."""

    def __init__(self, seed: int) -> None:
        self._s = seed & 0xFFFFFFFFFFFFFFFF
        self._spare: float | None = None

    def _next_u64(self) -> int:
        self._s = (self._s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def uniform(self) -> float:
        # 53 significant bits, strictly inside (0, 1) so the normal transform never blows up.
        u = (self._next_u64() >> 11) / float(1 << 53)
        return min(max(u, 1e-12), 1 - 1e-12)

    def normal(self) -> float:
        if self._spare is not None:
            v, self._spare = self._spare, None
            return v
        u1, u2 = self.uniform(), self.uniform()
        r = math.sqrt(-2.0 * math.log(u1))
        self._spare = r * math.sin(2 * math.pi * u2)
        return r * math.cos(2 * math.pi * u2)


def cell_seed(season: int, week: int, position: str, draw: int) -> int:
    """Stable per-draw seed. Not `hash()`, which is salted per process."""
    h = 1469598103934665603
    for token in (str(season), str(week), position, str(draw)):
        for ch in token:
            h = ((h ^ ord(ch)) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        h = ((h ^ 0x2545F4914F6CDD1D) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


#: The calibration bisects against **the very draws that get reported**, so the reported null
#: distribution's mean Spearman equals the target by construction. Calibrating on a separate,
#: smaller sample was tried first and failed: with 64 draws the Monte Carlo standard error of
#: the mean (~0.013 Spearman) dwarfs any sensible tolerance, so the bisection chases noise and
#: stops wherever the noise happens to land -- which left a systematic -0.017 bias, running in
#: the exact direction that would have flattered this phase's pre-registered answer.
_CALIB_STEPS = 18
#: The tolerance gate G9 holds the calibration to, on real cells.
CALIB_TOL = 1e-3
#: The closed-form inversion is already within ~0.03 of the root; the bracket only has to cover
#: the tie attenuation, which is one-sided (ties can only attenuate).
_BRACKET_LO, _BRACKET_HI = 0.05, 0.30


def _rank_from_scores(score: list[float]) -> list[float]:
    order = sorted(range(len(score)), key=lambda i: -score[i])
    rank = [0.0] * len(score)
    for i, idx in enumerate(order, start=1):
        rank[idx] = float(i)
    return rank


def _mean_spearman(
    realized: list[float], z: list[float], rho_p: float, season: int, week: int, position: str
) -> float:
    """Mean tie-corrected Spearman over the `N_SIM` reported draws at latent correlation `rho_p`.

    **Common random numbers**: draw `k` always uses seed `cell_seed(..., k)`, so this is a
    deterministic, monotone function of `rho_p` and bisection on it is well-posed."""
    from alpha_squad.evaluation.weekly.metrics import spearman

    w = math.sqrt(max(0.0, 1.0 - rho_p * rho_p))
    total, n = 0.0, 0
    for k in range(N_SIM):
        rng = _Rng(cell_seed(season, week, position, k))
        got = spearman(_rank_from_scores([rho_p * zi + w * rng.normal() for zi in z]), realized)
        if got is not None:
            total += got
            n += 1
    return total / n if n else 0.0


def calibrate_latent(
    realized: list[float], rho_spearman: float, season: int, week: int, position: str
) -> float:
    """Latent correlation whose `N_SIM` draws achieve `rho_spearman` **against this cell's ties**.

    A pure function of its inputs: same cell, same answer, every run."""
    target = max(-1.0, min(1.0, rho_spearman))
    closed = pearson_for_spearman(target)
    if target <= 0.0:
        # The phase only ever passes a board's own measured Spearman; a board ordered worse than
        # chance is reported, not simulated, so this branch exists to be explicit, not to be hit.
        return closed
    z = normal_scores(realized)
    lo = max(0.0, closed - _BRACKET_LO)
    hi = min(1.0, closed + _BRACKET_HI)
    for _ in range(_CALIB_STEPS):
        mid = (lo + hi) / 2.0
        if _mean_spearman(realized, z, mid, season, week, position) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass(frozen=True)
class NullDraw:
    """One synthetic ranking: dense predicted ranks, aligned to the input order."""

    pred_rank: list[float]


def draw_null_ranking(
    realized: list[float],
    rho_spearman: float,
    season: int,
    week: int,
    position: str,
    draw: int,
    latent: float | None = None,
) -> NullDraw:
    """One draw of a ranker with overall Spearman `rho_spearman` and no top-specific structure.

    `latent` is the calibrated correlation from `calibrate_latent`; callers producing a whole
    null distribution calibrate **once per cell** and pass it in, because bisecting per draw
    would cost 24x for an identical answer."""
    z = normal_scores(realized)
    rho_p = (
        latent
        if latent is not None
        else calibrate_latent(realized, rho_spearman, season, week, position)
    )
    rng = _Rng(cell_seed(season, week, position, draw))
    w = math.sqrt(max(0.0, 1.0 - rho_p * rho_p))
    score = [rho_p * zi + w * rng.normal() for zi in z]
    order = sorted(range(len(score)), key=lambda i: -score[i])
    rank = [0.0] * len(score)
    for i, idx in enumerate(order, start=1):
        rank[idx] = float(i)
    return NullDraw(rank)
