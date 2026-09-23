"""Where ECR's top-of-board advantage comes from (W8). Pure functions, no I/O.

The decomposition
-----------------
For every evaluated player-week, realized points split exactly into W5's usage and conversion
parts, and usage splits exactly into W7's Class A forecast and the surprise it did not see:

    pts = x + c = f + s + c        x = usage-expected points   c = pts - x   s = x - f

Top-k points capture is `sum(pts over the top-k) / D_k`, and `D_k` (the best possible top-k
total) is the same for every board in a week. The ECR-minus-Alpha capture gap is therefore
**exactly** additive:

    G = G_F + G_S + G_C

Each piece is a sum over the players in one board's top-k and not the other's -- W5's exact
per-player regret, split by component. Nothing is estimated and there is no residual, so each
piece is a fact about the week and only its stability across weeks needs inference.

**ECR is an instrument here, never a feature.** Nothing in this module trains, calibrates or
selects anything; every input is a finished board and a set of realized quantities.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: Components of a player-week's realized points, in decomposition order.
COMPONENTS: tuple[str, ...] = ("F", "S", "C")

#: Opportunity-surprise buckets (on |s|), efficiency buckets (on c), fixed in the pre-registration.
OPP_BUCKETS: tuple[str, ...] = ("CLOSE", "MODERATE", "LARGE")
SIGNED_BUCKETS: tuple[str, ...] = ("CLOSE", "MODERATE", "LARGE_UP", "LARGE_DOWN")
EFF_BUCKETS: tuple[str, ...] = ("LOW", "MID", "HIGH")

#: Pair types for the top-region pairwise test.
PAIR_TYPES: tuple[str, ...] = ("ALL", "CLOSE", "SURPRISE", "MATCHED")


@dataclass(frozen=True)
class PlayerWeek:
    """One evaluated player-week's realized decomposition. `f` is Class A; the rest are outcomes."""

    player_id: str
    pts: float
    x: float
    f: float

    @property
    def s(self) -> float:
        return self.x - self.f

    @property
    def c(self) -> float:
        return self.pts - self.x

    def component(self, name: str) -> float:
        return {"F": self.f, "S": self.s, "C": self.c}[name]


def top_k(order: list[str], k: int) -> list[str]:
    """The first `k` ids of a board's order (best first)."""
    return order[:k]


def best_total(pts: Iterable[float], k: int) -> float:
    """`D_k`: the best possible top-k points total -- the capture denominator."""
    return sum(sorted(pts, reverse=True)[:k])


def decompose_gap(
    order_a: list[str],
    order_b: list[str],
    rows: dict[str, PlayerWeek],
    k: int,
) -> dict[str, float] | None:
    """Board A's top-k capture minus board B's, and its exact split into G_F + G_S + G_C.

    `order_*` are the boards' orders over the same universe (`rows`). Returns `None` when the
    board is shorter than `k` or nobody scored (the capture metric is undefined there too).
    `capture_a` and `capture_b` are returned alongside so a caller can check them against
    `metrics.topk_points_capture` -- the decomposition is only meaningful if it is decomposing
    the program's own metric."""
    if len(order_a) < k or len(order_b) < k or set(order_a) != set(order_b):
        return None
    denom = best_total((r.pts for r in rows.values()), k)
    if denom <= 0:
        return None
    ta, tb = top_k(order_a, k), top_k(order_b, k)
    out = {
        "capture_a": sum(rows[p].pts for p in ta) / denom,
        "capture_b": sum(rows[p].pts for p in tb) / denom,
    }
    out["G"] = out["capture_a"] - out["capture_b"]
    for comp in COMPONENTS:
        out[f"G_{comp}"] = (
            sum(rows[p].component(comp) for p in ta) - sum(rows[p].component(comp) for p in tb)
        ) / denom
    return out


def attribute_gap(
    order_a: list[str],
    order_b: list[str],
    rows: dict[str, PlayerWeek],
    k: int,
    bucket_of: dict[str, str],
) -> dict[str, float] | None:
    """The capture gap carried by each bucket's players: `pts_i * (1[A top-k] - 1[B top-k])`
    summed within bucket, over `D_k`. The buckets sum exactly to `G`.

    Every player in either top-k must have a bucket; a missing one raises rather than being
    silently dropped (which would break the identity the gate checks)."""
    if len(order_a) < k or len(order_b) < k:
        return None
    denom = best_total((r.pts for r in rows.values()), k)
    if denom <= 0:
        return None
    ta, tb = set(top_k(order_a, k)), set(top_k(order_b, k))
    out: dict[str, float] = {}
    for pid in sorted(ta ^ tb):
        sign = 1.0 if pid in ta else -1.0
        bucket = bucket_of[pid]
        out[bucket] = out.get(bucket, 0.0) + sign * rows[pid].pts / denom
    return out


def swap_counts(order_a: list[str], order_b: list[str], k: int, bucket_of: dict[str, str]):
    """How many swapped players (in exactly one top-k) fall in each bucket."""
    ta, tb = set(top_k(order_a, k)), set(top_k(order_b, k))
    out: dict[str, int] = {}
    for pid in sorted(ta ^ tb):
        out[bucket_of[pid]] = out.get(bucket_of[pid], 0) + 1
    return out


# ---------------------------------------------------------------------------------------
# Thresholds and buckets
# ---------------------------------------------------------------------------------------


def quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted list (the same rule as `noise`)."""
    if not sorted_values:
        return math.nan
    idx = q * (len(sorted_values) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def thresholds(values: Iterable[float], qs: tuple[float, ...]) -> tuple[float, ...]:
    """Cut points of `values` at quantiles `qs`, computed once from the pooled distribution."""
    s = sorted(values)
    return tuple(quantile(s, q) for q in qs)


def tercile_bucket(value: float, cuts: tuple[float, float], labels: tuple[str, str, str]) -> str:
    """Bottom (`<= cuts[0]`), middle, top (`> cuts[1]`)."""
    lo, hi = cuts
    if value <= lo:
        return labels[0]
    if value > hi:
        return labels[2]
    return labels[1]


def opportunity_bucket(s: float, cuts: tuple[float, float]) -> str:
    return tercile_bucket(abs(s), cuts, ("CLOSE", "MODERATE", "LARGE"))


def signed_bucket(s: float, cuts: tuple[float, float]) -> str:
    b = opportunity_bucket(s, cuts)
    if b != "LARGE":
        return b
    return "LARGE_UP" if s > 0 else "LARGE_DOWN"


def efficiency_bucket(c: float, cuts: tuple[float, float]) -> str:
    return tercile_bucket(c, cuts, ("LOW", "MID", "HIGH"))


# ---------------------------------------------------------------------------------------
# Top-region pairwise accuracy by pair type
# ---------------------------------------------------------------------------------------


def pair_accuracy_by_type(
    region: list[str],
    rank_a: dict[str, float],
    rank_b: dict[str, float],
    pts: dict[str, float],
    pair_types: Callable[[str, str], Iterable[str]],
) -> dict[str, dict[str, float | int | None]]:
    """For each pair type: each board's share of correctly ordered pairs, and the pair count.

    A pair counts only when the realized points differ -- `metrics.pairwise_accuracy`'s rule,
    so a coin-flip pair never dilutes the comparison. `pair_types(i, j)` names every type the
    pair belongs to ("ALL" is added here)."""
    tally: dict[str, list[int]] = {}
    ids = sorted(region)
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            if pts[i] == pts[j]:
                continue
            better, worse = (i, j) if pts[i] > pts[j] else (j, i)
            ok_a = int(rank_a[better] < rank_a[worse])
            ok_b = int(rank_b[better] < rank_b[worse])
            for t in ("ALL", *pair_types(i, j)):
                row = tally.setdefault(t, [0, 0, 0])
                row[0] += ok_a
                row[1] += ok_b
                row[2] += 1
    return {
        t: {"acc_a": ca / n if n else None, "acc_b": cb / n if n else None, "n": n}
        for t, (ca, cb, n) in tally.items()
    }


def concordance(
    region: list[str], rank: dict[str, float], pts: dict[str, float]
) -> dict[str, float | None]:
    """Per player: the share of that player's region pairs the board orders correctly."""
    out: dict[str, float | None] = {}
    for i in region:
        ok = n = 0
        for j in region:
            if i == j or pts[i] == pts[j]:
                continue
            better, worse = (i, j) if pts[i] > pts[j] else (j, i)
            ok += int(rank[better] < rank[worse])
            n += 1
        out[i] = ok / n if n else None
    return out


def spearman_values(xs: list[float], ys: list[float]) -> float | None:
    """Spearman correlation with average ranks for ties. `None` when undefined."""
    n = len(xs)
    if n < 3:
        return None

    def avg_ranks(v: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for t in range(i, j + 1):
                r[order[t]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return r

    rx, ry = avg_ranks(xs), avg_ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


# ---------------------------------------------------------------------------------------
# The pre-registered interpretation (W8 pre-registration §7), evaluated mechanically
# ---------------------------------------------------------------------------------------

#: The primary capture depth the verdict reads.
PRIMARY_DEPTH = 10


def _row(summary: dict, section: str, metric: str) -> dict | None:
    return summary.get(section, {}).get(metric)


def _sig_pos(row: dict | None) -> bool:
    return bool(row) and row["ci_low"] > 0.0


def verdict(summary: dict, depth: int = PRIMARY_DEPTH, prefix: str = "") -> dict:
    """The pre-registered §7 rule, evaluated mechanically. `prefix` selects a sensitivity
    variant's CLOSE / SURPRISE split (e.g. "MED_") for the robustness count."""
    G = _row(summary, "decomp", f"G@{depth}")
    GS = _row(summary, "decomp", f"G_S@{depth}")
    GC = _row(summary, "decomp", f"G_C@{depth}")
    GF = _row(summary, "decomp", f"G_F@{depth}")
    omega = _row(summary, "pairs", "pair_ALL")
    w_close = _row(summary, "pairs", f"pair_{prefix}CLOSE")
    w_match = _row(summary, "pairs", "pair_MATCHED")
    w_diff = _row(summary, "omega", f"{prefix}surp_minus_close")

    pair_route = _sig_pos(omega)
    capture_route = _sig_pos(G)
    out = {"pair_precondition": pair_route, "capture_precondition": capture_route}
    if not (pair_route or capture_route):
        out.update(verdict="NO GAP TO EXPLAIN", information=False, efficiency=False, w_flag=False)
        return out

    def mean(r):
        return r["mean_diff"] if r else float("nan")

    i1 = pair_route and _sig_pos(w_diff) and mean(w_close) <= 0.5 * mean(omega)
    i2 = capture_route and _sig_pos(GS) and mean(GS) >= mean(G) / 3.0
    e1 = pair_route and _sig_pos(w_close) and mean(w_close) >= 0.5 * mean(omega)
    e2a = capture_route and _sig_pos(GC) and mean(GC) >= 0.5 * mean(G)
    e2b = pair_route and _sig_pos(w_match) and mean(w_match) >= 0.5 * mean(omega)
    info = bool(i1 or i2)
    eff = bool(e1 and (e2a or e2b))
    w_flag = bool(capture_route and _sig_pos(GF) and mean(GF) >= mean(G) / 3.0)
    label = (
        "MIXED"
        if info and eff
        else "INFORMATION"
        if info
        else "EFFICIENCY"
        if eff
        else "INCONCLUSIVE"
    )
    out.update(
        routes={
            "I-1": bool(i1),
            "I-2": bool(i2),
            "E-1": bool(e1),
            "E-2a": bool(e2a),
            "E-2b": bool(e2b),
        },
        information=info,
        efficiency=eff,
        w_flag=w_flag,
        verdict=label,
    )
    return out


def overall(v_rb: str, v_wr: str) -> str:
    """The pre-registered combination of the RB and WR verdicts."""
    weak = ("INCONCLUSIVE", "NO GAP TO EXPLAIN")
    if v_rb == v_wr:
        return v_rb
    if "MIXED" in (v_rb, v_wr):
        return "MIXED"
    if v_rb in weak and v_wr in weak:
        return "INCONCLUSIVE"
    if v_rb in weak:
        return f"{v_wr} (WR only)"
    if v_wr in weak:
        return f"{v_rb} (RB only)"
    return "MIXED"


def recommendation(overall_verdict: str, w_flags: list[bool]) -> str:
    base = overall_verdict.split(" (")[0]
    if base == "INCONCLUSIVE" and any(w_flags):
        return "NEITHER A NOR B: the gap lies in how Alpha uses information it already has"
    return {
        "INFORMATION": "A: acquire timestamped external information",
        "EFFICIENCY": "B: investigate efficiency/performance prediction",
        "MIXED": "C: investigate both",
        "INCONCLUSIVE": "D: stop this line of research",
        "NO GAP TO EXPLAIN": "D: stop this line of research",
    }[base]
