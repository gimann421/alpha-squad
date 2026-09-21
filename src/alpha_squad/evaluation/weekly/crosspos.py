"""The additive within-vs-cross-position decomposition of FLEX ordering quality (W4).

This is W4's primary decomposition because it is **exact**, not modelled. Pairwise ordering
accuracy on a FLEX board is by definition a weighted average over position-pair buckets:

    pairwise_total = SUM_b (n_b / N) * accuracy_b

with `b` ranging over the three **within-position** buckets (RB-RB, WR-WR, TE-TE) and the three
**cross-position** buckets (RB-WR, RB-TE, WR-TE). No assumption is needed for that identity to
hold, and it partitions the metric cleanly into the part a per-position monotone transform
**cannot** touch and the part it can.

That is the whole question of the phase, made arithmetic: if the cross-position buckets are
already near the within-position buckets in accuracy, there is little for calibration to win,
regardless of what the composition table looks like.

Directional bias
----------------
`pair_bias` additionally records, for each ordered position pair, how often the ranking put the
first position above the second when the second actually scored more. A system that
systematically over-rates RBs against TEs shows up here as an asymmetry, which a symmetric
accuracy number would hide.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The three FLEX positions, in a fixed order so bucket keys are deterministic.
FLEX_POSITIONS: tuple[str, ...] = ("RB", "WR", "TE")

WITHIN_BUCKETS: tuple[str, ...] = ("RB-RB", "WR-WR", "TE-TE")
CROSS_BUCKETS: tuple[str, ...] = ("RB-WR", "RB-TE", "WR-TE")


def _bucket(a: str, b: str) -> str:
    """Canonical bucket name for an unordered pair of positions."""
    i, j = FLEX_POSITIONS.index(a), FLEX_POSITIONS.index(b)
    return f"{FLEX_POSITIONS[min(i, j)]}-{FLEX_POSITIONS[max(i, j)]}"


@dataclass
class PairDecomposition:
    """Pairwise accuracy split by position-pair bucket, plus the within/cross rollups."""

    n_pairs: dict[str, int]
    accuracy: dict[str, float]
    within_pairs: int
    cross_pairs: int
    within_accuracy: float | None
    cross_accuracy: float | None
    total_accuracy: float | None

    def as_row(self) -> dict:
        row: dict = {
            "within_pairs": self.within_pairs,
            "cross_pairs": self.cross_pairs,
            "within_accuracy": self.within_accuracy,
            "cross_accuracy": self.cross_accuracy,
            "total_accuracy": self.total_accuracy,
        }
        for b in (*WITHIN_BUCKETS, *CROSS_BUCKETS):
            row[f"n_{b}"] = self.n_pairs.get(b, 0)
            row[f"acc_{b}"] = self.accuracy.get(b)
        return row


def decompose_pairs(
    positions: list[str],
    pred_rank: list[float],
    realized: list[float],
    *,
    min_gap: float = 0.0,
) -> PairDecomposition:
    """Split pairwise ordering accuracy into position-pair buckets.

    Tied outcomes (or gaps below `min_gap`) are excluded from every denominator, matching
    `metrics.pairwise_accuracy`'s convention exactly so the buckets sum back to the headline
    metric rather than to a slightly different quantity."""
    n = len(pred_rank)
    correct: dict[str, int] = {}
    total: dict[str, int] = {}
    for i in range(n):
        for j in range(i + 1, n):
            gap = abs(realized[i] - realized[j])
            if gap <= 0.0 or gap < min_gap:
                continue
            b = _bucket(positions[i], positions[j])
            total[b] = total.get(b, 0) + 1
            better = i if realized[i] > realized[j] else j
            worse = j if better == i else i
            if pred_rank[better] < pred_rank[worse]:
                correct[b] = correct.get(b, 0) + 1

    accuracy = {b: correct.get(b, 0) / t for b, t in total.items() if t}
    wp = sum(total.get(b, 0) for b in WITHIN_BUCKETS)
    cp = sum(total.get(b, 0) for b in CROSS_BUCKETS)
    wc = sum(correct.get(b, 0) for b in WITHIN_BUCKETS)
    cc = sum(correct.get(b, 0) for b in CROSS_BUCKETS)
    return PairDecomposition(
        n_pairs=total,
        accuracy=accuracy,
        within_pairs=wp,
        cross_pairs=cp,
        within_accuracy=(wc / wp) if wp else None,
        cross_accuracy=(cc / cp) if cp else None,
        total_accuracy=((wc + cc) / (wp + cp)) if (wp + cp) else None,
    )


def pair_bias(
    positions: list[str],
    pred_rank: list[float],
    realized: list[float],
) -> dict[str, dict[str, float]]:
    """Directional error rate for each ordered cross-position pair.

    For pair (A, B): among decidable pairs where an A and a B disagree, how often did the
    ranking put A above B when B actually scored more (`a_over_b_wrong`), versus B above A when
    A actually scored more (`b_over_a_wrong`)? A symmetric accuracy figure cannot distinguish
    "both directions equally wrong" from "systematically over-rates A", and only the second is
    something a cross-position transform could fix."""
    n = len(pred_rank)
    out: dict[str, dict[str, float]] = {}
    tallies: dict[str, list[int]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            pa, pb = positions[i], positions[j]
            if pa == pb or abs(realized[i] - realized[j]) <= 0.0:
                continue
            ia, ib = (i, j) if FLEX_POSITIONS.index(pa) < FLEX_POSITIONS.index(pb) else (j, i)
            key = _bucket(pa, pb)
            t = tallies.setdefault(key, [0, 0, 0])  # [a_over_b_wrong, b_over_a_wrong, total]
            t[2] += 1
            first_ranked_higher = pred_rank[ia] < pred_rank[ib]
            first_scored_more = realized[ia] > realized[ib]
            if first_ranked_higher and not first_scored_more:
                t[0] += 1
            elif (not first_ranked_higher) and first_scored_more:
                t[1] += 1
    for key, (aw, bw, tot) in tallies.items():
        if not tot:
            continue
        out[key] = {
            "n": float(tot),
            "a_over_b_wrong": aw / tot,
            "b_over_a_wrong": bw / tot,
            #: Positive means the FIRST position in the bucket name is systematically
            #: over-ranked against the second.
            "net_bias": (aw - bw) / tot,
        }
    return out
