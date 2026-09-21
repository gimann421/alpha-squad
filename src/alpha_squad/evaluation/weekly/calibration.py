"""Causal, per-position, monotone cross-position calibration (W4).

Four transforms, fixed in `docs/weekly/W4_PREREGISTRATION.md` §6 before any result existed.
Each one is:

* **per position** — the whole point is that RB, WR and TE may need different maps;
* **monotone non-decreasing within a position** — so within-position ordering is provably
  unchanged and any measured effect is *purely* cross-position (asserted by test);
* **causal** — fitted only on player-weeks strictly before the week being ranked.

Why monotonicity is the load-bearing property
---------------------------------------------
A FLEX board is the pooled sort of three positional prediction vectors. If the same monotone
map were applied to all three, the pooled order would not change at all. So the *entire* effect
of calibration is the **difference** between the three positional maps — which is exactly the
quantity W4 is trying to size. Allowing a transform to reorder players within a position would
confound that with a change to the positional rankings themselves, and the phase could no
longer answer its own question.

What the audit says to expect (recorded in the pre-registration, not here)
-------------------------------------------------------------------------
The three positional OLS fits are nearly identical (slopes within 0.012, intercepts within
0.153), so `CAL_AFFINE` should be close to a no-op. The marginal-matching maps
(`CAL_QUANTILE`, `CAL_RANKPCT`) expand a conditionally-calibrated prediction to match a
realized *marginal* distribution, which adds spread without adding information — CLAUDE.md
records the same manoeuvre failing in the draft program. Both predictions are pre-registered so
they can be scored against the outcome.
"""

from __future__ import annotations

import bisect
import statistics
from dataclasses import dataclass, field

import duckdb

#: A position needs at least this many prior (predicted, realized) pairs before any transform
#: is fitted; below it the transform is the identity. Fixed in the pre-registration.
MIN_FIT_SAMPLE = 200

CALIBRATION_METHODS: tuple[str, ...] = (
    "CAL_MEANVAR",
    "CAL_AFFINE",
    "CAL_QUANTILE",
    "CAL_RANKPCT",
)


@dataclass(frozen=True)
class FitWindow:
    """The strictly-prior window a calibration may see for one evaluated week.

    Materialised as an object rather than inlined into SQL so the causality rule is stated in
    exactly one place and can be asserted by a test."""

    season: int
    week: int

    def sql(self, alias: str = "w") -> str:
        """`(season < S) OR (season = S AND week < w)` — never the week being ranked."""
        return f"({alias}.season < {self.season} OR ({alias}.season = {self.season} AND {alias}.week < {self.week}))"


@dataclass
class PositionSample:
    """Prior (predicted, realized) pairs for one position, and the summaries fitted from them."""

    position: str
    predicted: list[float] = field(default_factory=list)
    realized: list[float] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.predicted)

    @property
    def usable(self) -> bool:
        return self.n >= MIN_FIT_SAMPLE


def load_prior_sample(
    con: duckdb.DuckDBPyConnection,
    window: FitWindow,
    positions: tuple[str, ...],
    model_name: str,
) -> dict[str, PositionSample]:
    """Every completed (predicted, realized) pair strictly before `window`, per position.

    This is the only place calibration touches data, and the window predicate is the only
    thing standing between W4 and a leak. It is deliberately not parameterised by anything a
    caller could widen."""
    rows = con.execute(
        f"""
        SELECT w.position, w.predicted_points, s.fantasy_points_ppr
        FROM weekly_projection_snapshot w
        JOIN player_week_stats s
          ON s.player_id = w.player_id AND s.season = w.season AND s.week = w.week
        WHERE w.model_name = ? AND w.position = ANY(?) AND {window.sql("w")}
        """,
        [model_name, list(positions)],
    ).fetchall()
    out = {p: PositionSample(p) for p in positions}
    for position, pred, real in rows:
        out[position].predicted.append(float(pred))
        out[position].realized.append(float(real or 0.0))
    return out


# ---------------------------------------------------------------------------------------
# The four transforms. Each returns a callable float -> float, monotone non-decreasing.
# ---------------------------------------------------------------------------------------


def _identity(x: float) -> float:
    return x


def fit_meanvar(sample: PositionSample):
    """Match the prior *marginal* mean and sd of realized points.

    `g(x) = mu_real + (x - mu_pred) * (sd_real / sd_pred)`. Strictly increasing whenever
    `sd_real > 0`, which it always is. This is the transform that most directly undoes the
    measured compression (sd ratios 0.54-0.62)."""
    if not sample.usable:
        return _identity
    mp, mr = statistics.fmean(sample.predicted), statistics.fmean(sample.realized)
    sp = statistics.stdev(sample.predicted)
    sr = statistics.stdev(sample.realized)
    if sp <= 0:
        return _identity
    scale = sr / sp
    return lambda x: mr + (x - mp) * scale


def fit_affine(sample: PositionSample):
    """OLS of realized on predicted: `g(x) = a + b*x`.

    Applied only when `b > 0`; a non-positive slope would invert the position's ordering, which
    would violate the monotonicity contract and confound the experiment, so it falls back to
    the identity rather than being silently applied."""
    if not sample.usable:
        return _identity
    xs, ys = sample.predicted, sample.realized
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return _identity
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    if b <= 0:
        return _identity
    a = my - b * mx
    return lambda x: a + b * x


def _ecdf_quantile(sorted_values: list[float], q: float) -> float:
    """Empirical quantile with linear interpolation; clamped at both ends."""
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]
    idx = q * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def fit_quantile(sample: PositionSample):
    """Quantile mapping: `g(x) = Q_real( F_pred(x) )`.

    Monotone because both the empirical CDF and the empirical quantile function are
    non-decreasing. Extrapolation is clamped to the fitted range (a prediction above anything
    seen before maps to the largest realized value seen before) rather than extended, because
    an empirical quantile function carries no information outside its support."""
    if not sample.usable:
        return _identity
    preds = sorted(sample.predicted)
    reals = sorted(sample.realized)
    n = len(preds)

    def g(x: float) -> float:
        # Fraction of prior predictions at or below x -- the empirical CDF.
        q = bisect.bisect_right(preds, x) / n
        return _ecdf_quantile(reals, q)

    return g


def fit_rankpct(sample: PositionSample):
    """Rank-only mapping. Returns the *quantile function* of prior realized values; the caller
    supplies a within-position percentile instead of a predicted value.

    This is the method that discards prediction magnitudes entirely and trusts only Alpha's
    within-position ordering. It is handled separately in `apply_to_week` because its input is
    a rank, not a point value."""
    if not sample.usable:
        return None
    reals = sorted(sample.realized)
    return lambda pct: _ecdf_quantile(reals, pct)


_FITTERS = {
    "CAL_MEANVAR": fit_meanvar,
    "CAL_AFFINE": fit_affine,
    "CAL_QUANTILE": fit_quantile,
}


def calibrated_scores(
    method: str,
    sample_by_position: dict[str, PositionSample],
    predictions: dict[str, float],
    position_of: dict[str, str],
) -> dict[str, float]:
    """Apply one calibration to a week's predictions, returning new scores.

    Within-position ordering is preserved by construction for every method: the value-based
    maps are monotone, and `CAL_RANKPCT` is a strictly decreasing function of within-position
    rank. `tests/unit/test_weekly_calibration.py` asserts this on real-shaped data rather than
    trusting the reasoning."""
    if method not in CALIBRATION_METHODS:
        known = ", ".join(CALIBRATION_METHODS)
        raise ValueError(f"unknown calibration method {method!r}; known: {known}")

    if method == "CAL_RANKPCT":
        out: dict[str, float] = {}
        by_pos: dict[str, list[str]] = {}
        for pid in predictions:
            by_pos.setdefault(position_of[pid], []).append(pid)
        for position, pids in by_pos.items():
            qf = fit_rankpct(sample_by_position.get(position, PositionSample(position)))
            ordered = sorted(pids, key=lambda p: (-predictions[p], p))
            n = len(ordered)
            for i, pid in enumerate(ordered):
                if qf is None:
                    out[pid] = predictions[pid]
                else:
                    # Rank 1 -> highest percentile. The 0.5 offset is the standard
                    # mid-rank plotting position, avoiding the degenerate 0 and 1 ends.
                    out[pid] = qf(1.0 - (i + 0.5) / n)
        return out

    fitter = _FITTERS[method]
    fitted = {position: fitter(sample) for position, sample in sample_by_position.items()}
    return {
        pid: fitted.get(position_of[pid], _identity)(value) for pid, value in predictions.items()
    }
