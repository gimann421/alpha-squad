"""Positional top-of-board instruments: the quality curve and the two reachable ceilings (W5).

Two ceilings, not one
---------------------
W4's `ORACLE_WITHIN` assumed **perfect outcome knowledge** and reported a gain of +0.3613 on
FLEX capture@10. `docs/weekly/W5_PREREGISTRATION.md` §2.7 measured why that number cannot be a
target: knowing a player's *realized* usage for the week -- every target and carry he would
actually get -- still leaves 29-37% of weekly point variance unexplained, and 63-86% unexplained
among the players who finished at the top. Most of a weekly fantasy score is conversion, and
conversion is close to a coin flip.

So this module builds two:

* ``ORACLE_USAGE``   -- rank by the week's realized usage-expected points.
  **Perfect opportunity foresight, zero conversion foresight.** The bound on what any better
  usage model could ever reach.
* ``ORACLE_OUTCOME`` -- rank by realized points. Perfect foresight; the unattainable ceiling.

`U = ORACLE_USAGE - CF_A` is the reachable headroom; `O - U` is touchdown variance and is
unreachable from any pre-game information whatsoever. Splitting the ceiling this way is the
difference between "there is a lot of headroom" and "there is a lot of headroom *worth chasing*".

Both use realized outcomes **by design** and neither is a production candidate.

Tie handling
------------
W4 lost a reportable number to this exact hazard: 42.5% of realized values tie inside a
position-week, so an oracle that scores players by realized values hands equal scores to players
the source ordering had strictly separated, and a `player_id` fallback then scrambles the
ordering the oracle exists to preserve. Every board here therefore resolves ties in **Alpha's**
favour first, with `player_id` as the deterministic backstop, and the invariants that must
follow are asserted by test rather than reasoned about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from alpha_squad.evaluation.weekly.benchmark import Board, BoardRow

#: The pre-registered depths. 20 is added for W5; it is a depth of the existing metrics.
W5_DEPTHS: tuple[int, ...] = (5, 10, 20, 25, 50)

#: Boards W5 scores on each positional cell.
TOPBOARD_SYSTEMS: tuple[str, ...] = ("CF_A", "ECR", "ORACLE_USAGE", "ORACLE_OUTCOME")

#: `conditional_correlation` is reported at this predicted depth. 24 is two fantasy starters per
#: team at RB/WR in a 12-team league -- the depth at which "top of the board" stops being a
#: product question. Fixed in the pre-registration, not chosen from a result.
CONDITIONAL_DEPTH = 24


def scored_board(
    board: Board, scores: dict[str, float], tiebreak: dict[str, float] | None = None
) -> Board:
    """Re-rank `board` densely by `scores`, resolving ties toward `tiebreak` then `player_id`."""
    tb = tiebreak or {}
    ordered = sorted(
        board.rows, key=lambda r: (-scores[r.player_id], tb.get(r.player_id, 0.0), r.player_id)
    )
    return Board(
        board.season,
        board.week,
        board.label,
        [BoardRow(r.player_id, r.position, float(i), r.realized) for i, r in enumerate(ordered, 1)],
    )


def alpha_rank_map(board: Board, predictions: dict[str, float]) -> dict[str, float]:
    """Alpha's 1..N ordering of `board`, for use as the tiebreak every oracle resolves toward."""
    ordered = sorted(board.rows, key=lambda r: (-predictions[r.player_id], r.player_id))
    return {r.player_id: float(i) for i, r in enumerate(ordered, start=1)}


def oracle_outcome(board: Board, predictions: dict[str, float]) -> Board:
    """Perfect foresight. Must score pairwise accuracy exactly 1.0 (asserted by test)."""
    return scored_board(
        board,
        {r.player_id: float(r.realized) for r in board.rows},
        alpha_rank_map(board, predictions),
    )


def oracle_usage(
    board: Board, predictions: dict[str, float], usage: dict[str, float]
) -> tuple[Board, int]:
    """Perfect opportunity foresight. Returns the board and the number of players it covered.

    A player with no usage row keeps **Alpha's own predicted score**, so he is neither dropped
    (which would change the universe and break the pairing) nor imputed a fabricated usage value.
    The count is returned so the coverage can be reported rather than assumed, and a cell whose
    coverage is poor is visible instead of quietly diluted toward Alpha."""
    covered = sum(1 for r in board.rows if r.player_id in usage)
    scores = {
        r.player_id: float(usage.get(r.player_id, predictions[r.player_id])) for r in board.rows
    }
    return scored_board(board, scores, alpha_rank_map(board, predictions)), covered


# ---------------------------------------------------------------------------------------
# The quality curve
# ---------------------------------------------------------------------------------------


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def conditional_correlation(
    predictions: dict[str, float], realized: dict[str, float], depth: int = CONDITIONAL_DEPTH
) -> float | None:
    """Pearson `corr(predicted, realized)` among the **predicted top `depth`** players.

    This is the statistic W4 reported collapsing to 0.251 / 0.222 / 0.141, reproduced exactly.

    **It is not comparable across systems whose scores live on different scales.** Pearson reads
    the spacing of the scores, and Alpha's predicted points are compressed and right-skewed while
    a synthetic ranker's latent score is standard normal and a rank is uniform; correlating each
    against the same outcomes answers three different questions. Use `conditional_spearman` for
    any cross-system claim, or transplant one system's value curve onto the other's ordering
    (`transplant_values`) so that Pearson is measuring the same thing on both sides."""
    universe = sorted(set(predictions) & set(realized))
    if len(universe) < depth:
        return None
    top = sorted(universe, key=lambda p: (-predictions[p], p))[:depth]
    return _pearson([predictions[p] for p in top], [realized[p] for p in top])


def conditional_spearman(
    predictions: dict[str, float], realized: dict[str, float], depth: int = CONDITIONAL_DEPTH
) -> float | None:
    """Rank correlation among the predicted top `depth`. **Invariant to the score's scale.**

    This is the version that may be compared between Alpha and the copula null, because any
    strictly monotone transform of either score leaves it unchanged. The gap between it and the
    full-board Spearman is the range-restriction effect, and `nulls.py` measures how much of that
    gap a ranker with no top-specific defect produces anyway."""
    universe = sorted(set(predictions) & set(realized))
    if len(universe) < depth:
        return None
    from alpha_squad.evaluation.weekly.metrics import spearman

    top = sorted(universe, key=lambda p: (-predictions[p], p))[:depth]
    return spearman([float(i) for i in range(1, depth + 1)], [realized[p] for p in top])


def transplant_values(order: list[str], values: list[float]) -> dict[str, float]:
    """Give the players in `order` the value curve `values`, largest first.

    Lets a synthetic ranking be scored on **Alpha's own predicted value distribution**, so a
    Pearson statistic computed on both is measuring the same quantity. The same device W4 used to
    build `ORACLE_XPOS`: hold one side's ordering, replace the other side's scale."""
    curve = sorted(values, reverse=True)
    return {pid: curve[i] for i, pid in enumerate(order) if i < len(curve)}


@dataclass
class DepthWindow:
    """Pairwise ordering accuracy among players whose predicted rank falls in `[lo, hi]`."""

    lo: int
    hi: int
    accuracy: float | None
    pairs: int


#: Windows the curve is reported over. Contiguous and non-overlapping, so the sequence reads as
#: "how well is this band of the board ordered" rather than as nested prefixes whose later
#: entries are dominated by the earlier ones.
CURVE_WINDOWS: tuple[tuple[int, int], ...] = ((1, 10), (11, 25), (26, 50), (51, 200))


def depth_windows(
    predictions: dict[str, float],
    realized: dict[str, float],
    windows: tuple[tuple[int, int], ...] = CURVE_WINDOWS,
) -> list[DepthWindow]:
    """Ordering accuracy band by band down the predicted board.

    Tied realized outcomes are excluded from the denominator, exactly as `metrics.pairwise_accuracy`
    does, so a band full of players who all scored 0.0 reports `None` rather than a flattering
    50%."""
    universe = sorted(set(predictions) & set(realized))
    order = sorted(universe, key=lambda p: (-predictions[p], p))
    out: list[DepthWindow] = []
    for lo, hi in windows:
        band = order[lo - 1 : hi]
        correct = total = 0
        for i in range(len(band)):
            for j in range(i + 1, len(band)):
                a, b = band[i], band[j]
                if realized[a] == realized[b]:
                    continue
                total += 1
                # `a` is ranked ahead of `b` by construction of `order`.
                if realized[a] > realized[b]:
                    correct += 1
        out.append(DepthWindow(lo, hi, (correct / total if total else None), total))
    return out
