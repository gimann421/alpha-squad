"""The two pre-registered W2 decision rules, applied as code (`docs/weekly/W2_PREREGISTRATION.md` §2).

Both criteria and both thresholds were fixed before any metric was computed. They live here,
under test, rather than being applied by hand in a report, because a rule evaluated by hand is
a rule that can be nudged.

    R1  Is the instrument usable at all?     MDE vs the ECR-over-trivial-baseline gap
    R2  Is ECR's strength depth-uniform?     spread of that gap, in MDE units, across depths

**Effect sizes are expressed in MDE units** — `gap / MDE` — because the raw units differ by
metric and depth and are not comparable. A ratio of 1.0 means the effect is exactly at the
edge of what 79 weeks can resolve; below 1.0 it is indistinguishable from weekly noise
whichever direction it points.
"""

from __future__ import annotations

from dataclasses import dataclass

#: R2's threshold, fixed in the pre-registration: the point at which one pooled number stops
#: describing both ends of the board.
DEPTH_UNIFORMITY_THRESHOLD = 2.0

#: The depths R2 compares. Same metric family (`capture@k`) at every depth -- comparing
#: capture@10 against a full-board Spearman would be comparing two different quantities and
#: calling the difference "depth dependence".
R2_DEPTHS: tuple[int, ...] = (10, 25, 50)


@dataclass
class Effect:
    """One pre-registered effect: how far ECR sits above a reference, in MDE units."""

    metric: str
    gap: float
    mde: float

    @property
    def in_mde_units(self) -> float:
        return self.gap / self.mde if self.mde else float("nan")

    @property
    def resolvable(self) -> bool:
        return abs(self.in_mde_units) >= 1.0


@dataclass
class R1Verdict:
    usable: bool
    effects: list[Effect]
    min_ratio: float
    max_ratio: float


@dataclass
class R2Verdict:
    depth_uniform: bool
    ratios: dict[int, float]
    spread: float


def evaluate_r1(paired: dict, *, reference: str, metrics: tuple[str, ...]) -> R1Verdict:
    """R1 --- usable when the ECR-over-trivial-baseline gap exceeds the instrument's MDE.

    `paired` is the runner's `summary["paired"][board][reference]` mapping. The rule is
    "usable if the instrument can resolve the gap", so a single metric failing does not fail
    R1; **every** metric failing does. That asymmetry is deliberate and pre-registered: R1
    asks whether the instrument works at all, not whether it works for every metric."""
    effects = [Effect(m, paired[m]["mean_diff"], paired[m]["mde"]) for m in metrics if m in paired]
    ratios = [abs(e.in_mde_units) for e in effects]
    return R1Verdict(
        usable=any(e.resolvable for e in effects),
        effects=effects,
        min_ratio=min(ratios) if ratios else float("nan"),
        max_ratio=max(ratios) if ratios else float("nan"),
    )


def evaluate_r2(paired: dict, *, depths: tuple[int, ...] = R2_DEPTHS) -> R2Verdict:
    """R2 --- depth-uniform when the effect, in MDE units, varies by less than 2x across
    depths.

    A `capture@k` missing for a depth (a board too short to support it) is skipped rather
    than imputed: a position with only two valid depths is compared on those two."""
    ratios: dict[int, float] = {}
    for k in depths:
        row = paired.get(f"capture@{k}")
        if row and row.get("mde"):
            ratios[k] = abs(row["mean_diff"] / row["mde"])
    if len(ratios) < 2:
        return R2Verdict(depth_uniform=True, ratios=ratios, spread=float("nan"))
    lo, hi = min(ratios.values()), max(ratios.values())
    spread = hi / lo if lo else float("inf")
    return R2Verdict(
        depth_uniform=spread < DEPTH_UNIFORMITY_THRESHOLD, ratios=ratios, spread=spread
    )
