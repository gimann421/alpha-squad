"""Weekly ranking-quality metrics (W2).

**Frozen before any comparative result was computed.** The definitions here, including tie
handling, missing-player handling and depth handling, were committed in
`docs/weekly/W2_PREREGISTRATION.md` before the benchmark was run. Changing one after seeing a
result requires a dated amendment in that file (the rule D70 set and honoured when its own
gates failed).

Why these, and what each is for
-------------------------------
The product question is *"help the user identify the players they should value most for the
upcoming week"*. Ranking quality is therefore primary and point accuracy is a supporting
diagnostic -- so this module computes **no point-error metric for ECR at all**. ECR is a
ranking; it publishes no point projection, and inventing one (by mapping rank to points) would
manufacture a quantity the source does not contain and then evaluate it as though it were real.

    M1  spearman              overall rank-order quality        "is this list ordered sensibly"
    M2  kendall_tau_b         ordering, tie-aware               same, robust to the many ties
    M3  pairwise_accuracy     P(correctly ordered pair)         the raw ordering act
    M4  decisive_pair_accuracy  M3 on pairs >= 3.0 pts apart    "which of these two do I start"
    M5  topk_precision        |pred top-k & true top-k| / k     "did it find the right players"
    M6  topk_points_capture   pts(pred top-k) / pts(true top-k) what the ranking actually WON
    M7  mean_rank_error       mean |pred rank - true rank|      interpretable miss size

M6 is the one that most directly measures product value: a top-10 that misses the true #1 but
catches nine good players costs the user far less than one that misses five. Precision alone
cannot see that; points captured can.

Conventions, fixed
------------------
* **Universe.** Metrics are computed over the *evaluable set*: ranked players who were not
  already playing at the cutoff AND who have a realized outcome. Ranked players with no
  realized row did not play; they are excluded from the production-forecast metrics and
  counted separately as the availability quantity. Nothing is imputed to 0.0.
* **Ties.** Realized fantasy points tie constantly (every 0.0). Spearman and Kendall use
  average ranks. `pairwise_accuracy` **excludes tied-outcome pairs from the denominator**
  rather than scoring them as half-right, so the metric answers "when there was a real
  difference, did the ranking get it right".
* **Depth.** A top-k metric is computed only when the evaluable set has at least `k` players;
  otherwise it is `None` and the cell is reported as invalid rather than silently computed on
  a shorter list. This is what keeps top-25 off a 32-team DST board from being meaningless.
* **Direction.** Predicted rank 1 = best. Realized rank 1 = most fantasy points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: A pair of players is "decisive" when their realized points differ by at least this much --
#: roughly the scale at which a start/sit choice stops being a coin flip. Fixed in the
#: pre-registration, not chosen after seeing which threshold flattered anything.
DECISIVE_POINT_GAP = 3.0

#: Depths the product cares about. A depth is skipped for a cell too small to support it.
DEPTHS: tuple[int, ...] = (10, 25, 50)


def _average_ranks(values: list[float], *, descending: bool) -> list[float]:
    """Competition-free average ranks, ties sharing the mean of their positions.

    Average ranks are what make Spearman well-defined under the heavy tying that realized
    weekly points produce (every player who scored 0.0 is tied)."""
    order = sorted(range(len(values)), key=lambda i: -values[i] if descending else values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(pred_rank: list[float], realized: list[float]) -> float | None:
    """M1. Pearson correlation of average ranks -- the standard tie-corrected Spearman."""
    n = len(pred_rank)
    if n < 3:
        return None
    x = _average_ranks(pred_rank, descending=False)
    y = _average_ranks(realized, descending=True)
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def kendall_tau_b(pred_rank: list[float], realized: list[float]) -> float | None:
    """M2. Tie-aware Kendall's tau-b.

    Reported alongside Spearman because the two disagree in exactly the situation this data
    produces: a few enormous outliers (a 40-point game) move Spearman through the rank
    distance, while tau-b only counts orderings. If they disagree, the disagreement is the
    finding."""
    n = len(pred_rank)
    if n < 3:
        return None
    conc = disc = tx = ty = 0
    for i in range(n):
        for j in range(i + 1, n):
            a = pred_rank[i] - pred_rank[j]
            # realized is "higher is better", predicted rank is "lower is better", so a
            # correctly-ordered pair has opposite signs.
            b = realized[j] - realized[i]
            if a == 0 and b == 0:
                tx += 1
                ty += 1
            elif a == 0:
                tx += 1
            elif b == 0:
                ty += 1
            elif (a > 0) == (b > 0):
                conc += 1
            else:
                disc += 1
    n0 = n * (n - 1) / 2
    denom = math.sqrt((n0 - tx) * (n0 - ty))
    return None if denom == 0 else (conc - disc) / denom


def pairwise_accuracy(
    pred_rank: list[float], realized: list[float], *, min_gap: float = 0.0
) -> tuple[float | None, int]:
    """M3/M4. Share of player pairs the ranking ordered correctly, and the pair count.

    Pairs whose realized points are tied (or differ by less than `min_gap`) are **excluded
    from the denominator**: the question is "when there was a real difference, did the
    ranking get it right", and scoring a coin-flip pair as half-right dilutes that."""
    n = len(pred_rank)
    correct = total = 0
    for i in range(n):
        for j in range(i + 1, n):
            gap = abs(realized[i] - realized[j])
            if gap <= 0.0 or gap < min_gap:
                continue
            total += 1
            better = i if realized[i] > realized[j] else j
            worse = j if better == i else i
            if pred_rank[better] < pred_rank[worse]:
                correct += 1
    return (correct / total if total else None), total


def topk_precision(pred_rank: list[float], realized: list[float], k: int) -> float | None:
    """M5. Overlap between the predicted top-k and the realized top-k.

    Symmetric in k, so precision and recall coincide; reported once."""
    n = len(pred_rank)
    if n < k:
        return None
    pred_top = {i for i in sorted(range(n), key=lambda i: pred_rank[i])[:k]}
    true_top = {i for i in sorted(range(n), key=lambda i: -realized[i])[:k]}
    return len(pred_top & true_top) / k


def topk_points_capture(pred_rank: list[float], realized: list[float], k: int) -> float | None:
    """M6. Points scored by the predicted top-k, as a share of the best possible top-k.

    The most product-relevant metric here: it prices a miss by what the miss *cost*, not by
    whether a name matched. A denominator of 0 (nobody scored) returns None rather than a
    fabricated 1.0."""
    n = len(pred_rank)
    if n < k:
        return None
    pred_top = sorted(range(n), key=lambda i: pred_rank[i])[:k]
    best = sorted(realized, reverse=True)[:k]
    denom = sum(best)
    if denom <= 0:
        return None
    return sum(realized[i] for i in pred_top) / denom


def mean_rank_error(pred_rank: list[float], realized: list[float]) -> float | None:
    """M7. Mean absolute difference between predicted rank and realized rank.

    In the same units a user reads ("it had him 8th, he finished 31st"), which neither
    correlation reports."""
    n = len(pred_rank)
    if n < 2:
        return None
    pr = _average_ranks(pred_rank, descending=False)
    tr = _average_ranks(realized, descending=True)
    return sum(abs(a - b) for a, b in zip(pr, tr, strict=True)) / n


@dataclass
class CellMetrics:
    """Every frozen metric for one (season, week, board) cell."""

    n: int
    spearman: float | None
    kendall: float | None
    pairwise: float | None
    pairwise_pairs: int
    decisive: float | None
    decisive_pairs: int
    mean_rank_error: float | None
    precision: dict[int, float | None]
    capture: dict[int, float | None]

    def as_row(self) -> dict:
        row = {
            "n": self.n,
            "spearman": self.spearman,
            "kendall": self.kendall,
            "pairwise": self.pairwise,
            "pairwise_pairs": self.pairwise_pairs,
            "decisive": self.decisive,
            "decisive_pairs": self.decisive_pairs,
            "mean_rank_error": self.mean_rank_error,
        }
        for k in DEPTHS:
            row[f"precision@{k}"] = self.precision.get(k)
            row[f"capture@{k}"] = self.capture.get(k)
        return row


def evaluate_cell(
    pred_rank: list[float], realized: list[float], *, depths: tuple[int, ...] = DEPTHS
) -> CellMetrics:
    """Compute the whole frozen suite for one board-week. Inputs are already restricted to the
    evaluable set (see the module docstring); this function does no filtering of its own, so
    the universe rule lives in exactly one place (`snapshots.py`) rather than two."""
    pw, pw_n = pairwise_accuracy(pred_rank, realized)
    dec, dec_n = pairwise_accuracy(pred_rank, realized, min_gap=DECISIVE_POINT_GAP)
    return CellMetrics(
        n=len(pred_rank),
        spearman=spearman(pred_rank, realized),
        kendall=kendall_tau_b(pred_rank, realized),
        pairwise=pw,
        pairwise_pairs=pw_n,
        decisive=dec,
        decisive_pairs=dec_n,
        mean_rank_error=mean_rank_error(pred_rank, realized),
        precision={k: topk_precision(pred_rank, realized, k) for k in depths},
        capture={k: topk_points_capture(pred_rank, realized, k) for k in depths},
    )
