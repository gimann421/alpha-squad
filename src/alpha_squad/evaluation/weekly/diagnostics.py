"""W3's declared reporting additions: paired win/loss counts, a paired test, point-error
diagnostics and FLEX cross-position composition.

Everything here was declared in `docs/weekly/W3_PREREGISTRATION.md` §5, §6 and §8 **before any
Alpha result existed**. None of it is a new ranking metric — the metric suite is W2's, reused
verbatim. These are the *reporting* additions the W3 brief asked for.

Two deliberate restraints:

* **Point-error diagnostics are computed for Alpha only.** ECR publishes no point projection.
  Manufacturing one (by mapping rank to points) and then scoring it would invent the quantity
  under test. `point_diagnostics` therefore takes predictions, and no ECR board can supply any.
* **Composition is measured, never corrected.** `flex_composition` reports which positions fill
  a FLEX top-k against which positions actually should have. If the pooled ordering is
  miscalibrated across positions, that is a W3 finding and a W4 candidate — W3 applies no
  reweighting.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class PairedOutcome:
    """Week-by-week win/loss record and a paired significance test."""

    metric: str
    system_a: str
    system_b: str
    n_weeks: int
    a_wins: int
    b_wins: int
    ties: int
    mean_diff: float
    median_diff: float
    #: Wilcoxon signed-rank statistic and its normal-approximation two-sided p-value.
    wilcoxon_w: float
    wilcoxon_p: float
    #: Matched-pairs rank-biserial correlation: a scale-free paired effect size in [-1, 1].
    effect_size_rb: float

    def as_row(self) -> dict:
        return self.__dict__.copy()


def _normal_sf(z: float) -> float:
    """Upper-tail probability of the standard normal, via erfc."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def wilcoxon_signed_rank(diffs: list[float]) -> tuple[float, float, float]:
    """Two-sided Wilcoxon signed-rank test on paired differences.

    Returns `(W, p, rank_biserial)`. Zero differences are dropped (Wilcoxon's standard
    treatment), ties share average ranks, and the p-value uses the normal approximation with a
    tie correction — appropriate at n ≈ 79 weeks, which is well inside the regime where the
    approximation is accurate.

    Implemented here rather than pulled from scipy because the whole weekly package is
    dependency-light and hand-checkable, and because a test whose exact convention matters to a
    reported result should be readable in the repository that reports it."""
    nonzero = [d for d in diffs if d != 0.0]
    n = len(nonzero)
    if n < 6:  # normal approximation is not trustworthy below this
        return (math.nan, math.nan, math.nan)

    order = sorted(range(n), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * n
    i = 0
    tie_groups: list[int] = []
    while i < n:
        j = i
        while j + 1 < n and abs(nonzero[order[j + 1]]) == abs(nonzero[order[i]]):
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        tie_groups.append(j - i + 1)
        i = j + 1

    w_plus = sum(r for r, d in zip(ranks, nonzero, strict=True) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, nonzero, strict=True) if d < 0)
    w = min(w_plus, w_minus)

    mean_w = n * (n + 1) / 4.0
    tie_term = sum(t**3 - t for t in tie_groups)
    var_w = (n * (n + 1) * (2 * n + 1) - tie_term / 2.0) / 24.0
    if var_w <= 0:
        return (w, math.nan, math.nan)
    z = (w - mean_w) / math.sqrt(var_w)
    p = 2.0 * _normal_sf(abs(z))

    total = w_plus + w_minus
    rb = (w_plus - w_minus) / total if total else math.nan
    return (w, min(p, 1.0), rb)


def paired_outcome(
    metric: str,
    system_a: str,
    system_b: str,
    a_per_week: dict[str, float],
    b_per_week: dict[str, float],
) -> PairedOutcome | None:
    """Win/loss counts and the paired test over the weeks both systems cover."""
    weeks = sorted(set(a_per_week) & set(b_per_week))
    pairs = [
        (a_per_week[w], b_per_week[w])
        for w in weeks
        if a_per_week[w] is not None
        and b_per_week[w] is not None
        and not math.isnan(a_per_week[w])
        and not math.isnan(b_per_week[w])
    ]
    if len(pairs) < 3:
        return None
    diffs = [a - b for a, b in pairs]
    w, p, rb = wilcoxon_signed_rank(diffs)
    return PairedOutcome(
        metric=metric,
        system_a=system_a,
        system_b=system_b,
        n_weeks=len(diffs),
        a_wins=sum(1 for d in diffs if d > 0),
        b_wins=sum(1 for d in diffs if d < 0),
        ties=sum(1 for d in diffs if d == 0),
        mean_diff=statistics.fmean(diffs),
        median_diff=statistics.median(diffs),
        wilcoxon_w=w,
        wilcoxon_p=p,
        effect_size_rb=rb,
    )


@dataclass
class PointDiagnostics:
    """SECONDARY. Point-prediction error for a system that produces point predictions.

    Never a success criterion (W3 §5). Reported so the phase can answer the separate,
    genuinely useful question of whether point accuracy and ranking quality move together."""

    n: int
    mae: float
    rmse: float
    mean_signed_bias: float
    #: (predicted decile → mean predicted, mean realized), lowest decile first.
    calibration: list[tuple[float, float]] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "n": self.n,
            "mae": self.mae,
            "rmse": self.rmse,
            "mean_signed_bias": self.mean_signed_bias,
            "calibration": self.calibration,
        }


def point_diagnostics(predicted: list[float], realized: list[float]) -> PointDiagnostics | None:
    """MAE / RMSE / signed bias / decile calibration. Alpha only; ECR has no point projection."""
    n = len(predicted)
    if n < 10:
        return None
    errs = [p - r for p, r in zip(predicted, realized, strict=True)]
    order = sorted(range(n), key=lambda i: predicted[i])
    calib: list[tuple[float, float]] = []
    for d in range(10):
        lo, hi = d * n // 10, (d + 1) * n // 10
        idx = order[lo:hi]
        if idx:
            calib.append(
                (
                    statistics.fmean(predicted[i] for i in idx),
                    statistics.fmean(realized[i] for i in idx),
                )
            )
    return PointDiagnostics(
        n=n,
        mae=statistics.fmean(abs(e) for e in errs),
        rmse=math.sqrt(statistics.fmean(e * e for e in errs)),
        mean_signed_bias=statistics.fmean(errs),
        calibration=calib,
    )


def flex_composition(
    positions: list[str], pred_rank: list[float], realized: list[float], k: int
) -> dict[str, dict[str, float]] | None:
    """Which positions fill a FLEX top-k, against which positions *should* have filled it.

    The concrete test of cross-position calibration: three per-position models pooled without
    normalisation will, if their scales differ, systematically over- or under-represent a
    position at the top of the FLEX board. Comparing predicted composition to realized
    composition makes that visible without correcting it."""
    n = len(pred_rank)
    if n < k:
        return None
    pred_top = sorted(range(n), key=lambda i: pred_rank[i])[:k]
    true_top = sorted(range(n), key=lambda i: -realized[i])[:k]
    out: dict[str, dict[str, float]] = {}
    for pos in ("RB", "WR", "TE"):
        out[pos] = {
            "predicted_share": sum(1 for i in pred_top if positions[i] == pos) / k,
            "realized_share": sum(1 for i in true_top if positions[i] == pos) / k,
            "pool_share": sum(1 for p in positions if p == pos) / n,
        }
        out[pos]["over_representation"] = out[pos]["predicted_share"] - out[pos]["realized_share"]
    return out
