"""Week-to-week variation, and the minimum detectable difference it implies (W2).

The question this exists to answer
----------------------------------
> How large would an improvement over ECR have to be before we should regard it as
> distinguishable from normal weekly noise?

**The unit of replication is the week, not the player-week.** Player-weeks inside one week
share the slate, the injury news, the weather and the same ECR vintage. Treating ~30,000
player-weeks as independent would overstate precision by roughly an order of magnitude and is
the single most likely way to manufacture a false result in this program. Every interval here
resamples **weeks**.

Paired, not unpaired
--------------------
Two systems are always compared on the *same* week and the *same* player universe, so the
quantity of interest is the per-week **paired difference**. Its SD is far smaller than either
system's own week-to-week SD, because the shared weekly difficulty cancels — a week where
everyone's ranking looks bad (a high-variance slate) is not evidence about either system. The
difference between the raw SD and the paired SD is itself reported, because quoting the raw
one would overstate the detection floor by a wide margin.

The draft program's 172–250 point detection floor does not transfer and is never quoted here:
that was a different instrument, a different unit and 5 season-clusters (D108, W1 §10.3).
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

#: Fixed in the pre-registration. Resampling WEEKS, not player-weeks.
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEEDS: tuple[int, ...] = tuple(range(10))
CONFIDENCE = 0.95


@dataclass
class Distribution:
    """The per-week distribution of one metric for one system."""

    metric: str
    n_weeks: int
    mean: float
    median: float
    sd: float
    p10: float
    p90: float
    ci_low: float
    ci_high: float

    def as_row(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PairedDifference:
    """The per-week paired difference between two systems, and the MDE it implies."""

    metric: str
    system_a: str
    system_b: str
    n_weeks: int
    mean_diff: float
    sd_diff: float
    ci_low: float
    ci_high: float
    #: The smallest true per-week mean difference this instrument could resolve at `n_weeks`,
    #: i.e. the half-width of the interval. An observed effect below it is not distinguishable
    #: from weekly noise no matter which direction it points.
    mde: float
    excludes_zero: bool

    def as_row(self) -> dict:
        return self.__dict__.copy()


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return math.nan
    idx = q * (len(sorted_values) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def _bootstrap_mean_ci(values: list[float]) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean, resampling weeks.

    Averaged over the pre-registered seeds so the reported interval does not depend on which
    single seed happened to be used — a reproducibility property the draft program had to
    learn the hard way (D92)."""
    if len(values) < 3:
        return (math.nan, math.nan)
    alpha = (1.0 - CONFIDENCE) / 2.0
    per_seed_lo: list[float] = []
    per_seed_hi: list[float] = []
    per_seed = max(1, BOOTSTRAP_RESAMPLES // len(BOOTSTRAP_SEEDS))
    n = len(values)
    for seed in BOOTSTRAP_SEEDS:
        rng = random.Random(seed)
        means = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(per_seed)]
        means.sort()
        per_seed_lo.append(_percentile(means, alpha))
        per_seed_hi.append(_percentile(means, 1 - alpha))
    return (statistics.fmean(per_seed_lo), statistics.fmean(per_seed_hi))


def describe(metric: str, per_week: list[float]) -> Distribution | None:
    """The per-week distribution of one metric. `None` when too few weeks are valid."""
    vals = [v for v in per_week if v is not None and not math.isnan(v)]
    if len(vals) < 3:
        return None
    s = sorted(vals)
    lo, hi = _bootstrap_mean_ci(vals)
    return Distribution(
        metric=metric,
        n_weeks=len(vals),
        mean=statistics.fmean(vals),
        median=statistics.median(vals),
        sd=statistics.stdev(vals) if len(vals) > 1 else 0.0,
        p10=_percentile(s, 0.10),
        p90=_percentile(s, 0.90),
        ci_low=lo,
        ci_high=hi,
    )


def paired_difference(
    metric: str,
    system_a: str,
    system_b: str,
    a_per_week: dict[tuple[int, int], float],
    b_per_week: dict[tuple[int, int], float],
) -> PairedDifference | None:
    """Per-week paired difference (a − b) over the weeks where BOTH systems are valid.

    Restricting to the intersection is what makes the comparison paired; averaging each
    system over its own set of weeks and subtracting would confound the difference with which
    weeks each happened to cover."""
    weeks = sorted(set(a_per_week) & set(b_per_week))
    diffs = [
        a_per_week[w] - b_per_week[w]
        for w in weeks
        if a_per_week[w] is not None
        and b_per_week[w] is not None
        and not math.isnan(a_per_week[w])
        and not math.isnan(b_per_week[w])
    ]
    if len(diffs) < 3:
        return None
    lo, hi = _bootstrap_mean_ci(diffs)
    return PairedDifference(
        metric=metric,
        system_a=system_a,
        system_b=system_b,
        n_weeks=len(diffs),
        mean_diff=statistics.fmean(diffs),
        sd_diff=statistics.stdev(diffs) if len(diffs) > 1 else 0.0,
        ci_low=lo,
        ci_high=hi,
        mde=(hi - lo) / 2.0,
        excludes_zero=(lo > 0.0 or hi < 0.0),
    )
