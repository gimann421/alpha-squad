"""Durable knowledge, weekly information or efficiency? (W9). Pure functions, no I/O.

W8 showed ECR's top-of-board lead over Alpha is mostly *usage that no provably-pre-Friday
information forecast* (`G_S`), and that ECR's disagreements with Alpha anticipate it
(rho(d, s) ~ +0.20). W9 asks where that anticipation comes from, measuring three sources
independently (`docs/weekly/W9_PREREGISTRATION.md`):

  DURABLE     knowable before the season -- prior-season box scores (D_PUBLIC) and the frozen
              preseason expert ranking (D_EXPERT)
  WEEKLY      documented during the week by a strictly pre-Friday-timestamped source (class A),
              undocumented (B), or documented only where timing is uncertain (C)
  EFFICIENCY  W8's conversion rules, re-applied (not blind -- W8's answer was already known)

The instruments here are exact where they can be: an additive attribution of any decomposition
piece to player groups, and a *decomposable* form of the anticipation correlation whose mean over
a region reproduces rho(d, s) exactly. **ECR is an instrument only; nothing here fits a model.**
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable

import numpy as np

from alpha_squad.evaluation.weekly.advantage import PlayerWeek, best_total, top_k

#: Durable public features (pre-registration §4.1), all from season S-1.
DURABLE_FEATURES: tuple[str, ...] = (
    "prior_ppg",
    "prior_games",
    "prior_opp_pg",
    "prior_tsh",
    "prior_snap",
    "prior_rank",
    "has_prior",
)

#: Prior-season tiers by W5's positional rank (`ELITE_DEPTH` = 12).
TIERS: tuple[str, ...] = ("ELITE", "STARTER", "OTHER")
ELITE_MAX_RANK = 12
STARTER_MAX_RANK = 36

#: Weekly-information classes, in precedence order.
WEEKLY_CLASSES: tuple[str, ...] = ("A", "C", "B")

#: Season periods, fixed from week numbers alone (pre-registration §3).
PERIODS: tuple[tuple[str, int, int], ...] = (("EARLY", 1, 6), ("MID", 7, 12), ("LATE", 13, 17))

#: Measurability bar for the weekly test (§6.3).
MIN_CLASS_A_PLAYER_WEEKS = 100
MIN_CLASS_A_WEEKS = 20


def period_of(week: int) -> str:
    for name, lo, hi in PERIODS:
        if lo <= week <= hi:
            return name
    raise ValueError(f"week {week} is outside every pre-registered period")


# ---------------------------------------------------------------------------------------
# Durable public features
# ---------------------------------------------------------------------------------------


def durable_features(weeks: list[dict], position_rank: int | None) -> dict[str, float | None]:
    """The seven §4.1 features from one player's prior-season weekly rows.

    `weeks` rows carry `week`, `ppr`, `targets`, `carries`, `target_share`, `snap`. Sums use
    `math.fsum` over rows sorted by week, so the result is independent of arrival order (the
    D116 lesson). A player with no prior season returns `has_prior = 0` and `None` elsewhere."""
    rows = sorted(weeks, key=lambda r: r["week"])
    n = len(rows)
    if n == 0:
        return {f: None for f in DURABLE_FEATURES} | {"has_prior": 0.0}

    def mean(key: str) -> float | None:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        return math.fsum(vals) / len(vals) if vals else None

    return {
        "prior_ppg": math.fsum(float(r["ppr"] or 0.0) for r in rows) / n,
        "prior_games": float(n),
        "prior_opp_pg": math.fsum(float(r["targets"] or 0) + float(r["carries"] or 0) for r in rows)
        / n,
        "prior_tsh": mean("target_share"),
        "prior_snap": mean("snap"),
        "prior_rank": None if position_rank is None else float(position_rank),
        "has_prior": 1.0,
    }


def tier_of(prior_rank: float | None) -> str:
    if prior_rank is None or (isinstance(prior_rank, float) and math.isnan(prior_rank)):
        return "OTHER"
    if prior_rank <= ELITE_MAX_RANK:
        return "ELITE"
    if prior_rank <= STARTER_MAX_RANK:
        return "STARTER"
    return "OTHER"


# ---------------------------------------------------------------------------------------
# Decomposable anticipation
# ---------------------------------------------------------------------------------------


def _average_ranks(values: list[float]) -> list[float]:
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def standardized_ranks(values: list[float]) -> list[float] | None:
    """Average ranks, centred and scaled to unit (population) variance. `None` if constant."""
    n = len(values)
    if n < 3:
        return None
    r = _average_ranks(values)
    m = math.fsum(r) / n
    sd = math.sqrt(math.fsum((x - m) ** 2 for x in r) / n)
    if sd == 0:
        return None
    return [(x - m) / sd for x in r]


def anticipation_terms(d: list[float], s: list[float]) -> list[float] | None:
    """`a_i = rd_i * rs_i`. Their mean over the list equals Spearman rho(d, s) exactly, and the
    mean over any subset is that subset's contribution -- the decomposable form of W8's P3."""
    rd, rs = standardized_ranks(d), standardized_ranks(s)
    if rd is None or rs is None:
        return None
    return [a * b for a, b in zip(rd, rs, strict=True)]


def residualize(y: list[float], x_rows: list[list[float]]) -> list[float]:
    """OLS residuals of `y` on the columns of `x_rows` plus an intercept.

    Solved by `numpy.linalg.lstsq` (deterministic for a given input); constant or collinear
    columns are handled by the minimum-norm solution rather than failing."""
    y_arr = np.asarray(y, dtype=float)
    if not x_rows or not x_rows[0]:
        return list(y_arr - y_arr.mean())
    x = np.column_stack([np.ones(len(y)), np.asarray(x_rows, dtype=float)])
    beta, *_ = np.linalg.lstsq(x, y_arr, rcond=None)
    return list(y_arr - x @ beta)


#: Permutations for the chance-absorption correction (pre-registration amendment A2).
N_PERMUTATIONS = 20


def adjusted_reduction(
    d: list[float],
    s: list[float],
    x_rows: list[list[float]],
    n_perm: int = N_PERMUTATIONS,
) -> dict[str, float] | None:
    """How much of rho(d, s) the controls in `x_rows` explain, net of chance absorption.

    Residualizing on k columns within a small region shrinks rho even when the columns are noise
    (amendment A2: 0.058 with 7 noise columns and 25 players). So the reduction from the REAL
    rows is measured against the same residualization on the rows permuted across players, with
    fixed seeds 0..n_perm-1:

        adjusted = mean_p rho(d_perm_resid, s) - rho(d_real_resid, s)

    Returns rho, the real and null residual rhos, and the adjusted reduction."""
    rho = _spearman(d, s)
    if rho is None or not x_rows:
        return None
    rho_real = _spearman(residualize(d, x_rows), s)
    nulls = []
    for seed in range(n_perm):
        perm = list(range(len(x_rows)))
        random.Random(seed).shuffle(perm)
        r = _spearman(residualize(d, [x_rows[i] for i in perm]), s)
        if r is not None:
            nulls.append(r)
    if rho_real is None or not nulls:
        return None
    rho_null = math.fsum(nulls) / len(nulls)
    return {
        "rho": rho,
        "rho_resid_real": rho_real,
        "rho_resid_null": rho_null,
        "raw_reduction": rho - rho_real,
        "adjusted_reduction": rho_null - rho_real,
    }


def _spearman(x: list[float], y: list[float]) -> float | None:
    terms = anticipation_terms(x, y)
    return None if terms is None else math.fsum(terms) / len(terms)


# ---------------------------------------------------------------------------------------
# Exact attribution of any decomposition piece to groups of players
# ---------------------------------------------------------------------------------------


def attribute_piece(
    order_a: list[str],
    order_b: list[str],
    rows: dict[str, PlayerWeek],
    k: int,
    group_of: dict[str, str],
    piece: str,
) -> dict[str, float] | None:
    """`piece` in {"G", "F", "S", "C"}: board A's top-k minus board B's top-k of that component,
    split by the swapped players' group, over `D_k`. Groups sum exactly to the piece."""
    if len(order_a) < k or len(order_b) < k:
        return None
    denom = best_total((r.pts for r in rows.values()), k)
    if denom <= 0:
        return None
    ta, tb = set(top_k(order_a, k)), set(top_k(order_b, k))
    out: dict[str, float] = {}
    for pid in sorted(ta ^ tb):
        sign = 1.0 if pid in ta else -1.0
        value = rows[pid].pts if piece == "G" else rows[pid].component(piece)
        g = group_of[pid]
        out[g] = out.get(g, 0.0) + sign * value / denom
    return out


def classify_weekly(strict_event: bool, uncertain_event: bool) -> str:
    """A (documented pre-Friday) > C (timing uncertain) > B (undocumented)."""
    if strict_event:
        return "A"
    if uncertain_event:
        return "C"
    return "B"


# ---------------------------------------------------------------------------------------
# The pre-registered §9 verdict rules
# ---------------------------------------------------------------------------------------


def _pos_sig(row: dict | None) -> bool:
    return bool(row) and row.get("ci_low") is not None and row["ci_low"] > 0.0


def durable_route(
    reduction: dict | None,
    share: float | None,
    early: dict | None,
    per_season: Iterable[float],
) -> dict[str, bool]:
    """D-1 (share >= 1/3 and the reduction's CI excludes zero), D-2 (EARLY reduction CI > 0),
    D-3 (point estimate > 0 in >= 4 of 5 seasons) -- for ONE instrument."""
    seasons = list(per_season)
    d1 = _pos_sig(reduction) and share is not None and share >= 1.0 / 3.0
    d2 = _pos_sig(early)
    d3 = sum(1 for v in seasons if v > 0) >= 4
    return {"D-1": bool(d1), "D-2": bool(d2), "D-3": bool(d3), "all": bool(d1 and d2 and d3)}


def weekly_rule(
    large_share_of_g: float | None,
    measurable: bool,
    class_a_share_of_gs: float | None,
    class_a_attr: dict | None,
    class_a_swap_share: float | None,
    a_minus_b: dict | None,
    loso_a_minus_b: Iterable[float],
) -> dict:
    """W-1, W-2, W-3. Returns `status` in {"SUPPORTED", "NOT SUPPORTED", "NOT MEASURABLE"}."""
    w1 = large_share_of_g is not None and large_share_of_g >= 0.5
    if not measurable:
        return {"W-1": bool(w1), "W-2": None, "W-3": None, "status": "NOT MEASURABLE"}
    concentrated = (
        class_a_share_of_gs is not None
        and class_a_share_of_gs >= 1.0 / 3.0
        and _pos_sig(class_a_attr)
        and class_a_swap_share is not None
        and class_a_share_of_gs >= 1.5 * class_a_swap_share
    )
    w2 = bool(concentrated and _pos_sig(a_minus_b))
    w3 = sum(1 for v in loso_a_minus_b if v > 0) >= 4
    ok = bool(w1 and w2 and w3)
    return {
        "W-1": bool(w1),
        "W-2": w2,
        "W-3": bool(w3),
        "status": "SUPPORTED" if ok else "NOT SUPPORTED",
    }


def position_verdict(durable: bool, weekly_status: str, efficiency: bool) -> dict:
    supported = [
        name
        for name, ok in (
            ("DURABLE", durable),
            ("WEEKLY", weekly_status == "SUPPORTED"),
            ("EFFICIENCY", efficiency),
        )
        if ok
    ]
    label = supported[0] if len(supported) == 1 else ("MIXED" if supported else "INCONCLUSIVE")
    return {
        "supported": supported,
        "verdict": label,
        "weekly_not_measurable": weekly_status == "NOT MEASURABLE",
    }


def overall(v_rb: str, v_wr: str) -> str:
    """RB and WR combined, exactly as W8's rule (INCONCLUSIVE is the weak outcome)."""
    if v_rb == v_wr:
        return v_rb
    if "MIXED" in (v_rb, v_wr):
        return "MIXED"
    if v_rb == "INCONCLUSIVE":
        return f"{v_wr} (WR only)"
    if v_wr == "INCONCLUSIVE":
        return f"{v_rb} (RB only)"
    return "MIXED"


def recommendation(
    overall_verdict: str,
    weekly_not_measurable: bool,
    anticipated_share: float | None,
    largest_component: str | None = None,
    durable_kind: str | None = None,
) -> str:
    base = overall_verdict.split(" (")[0]
    if base == "DURABLE":
        return (
            f"A: improve Alpha's understanding of established player/role quality ({durable_kind})"
        )
    if base == "WEEKLY":
        return "B: investigate acquiring timestamped injury/news/role/game information"
    if base == "EFFICIENCY":
        return "C: investigate player-performance/efficiency modeling"
    if base == "MIXED":
        return f"D: research the largest measured component separately ({largest_component})"
    if anticipated_share is not None and anticipated_share < 1.0 / 3.0:
        return "E: most of the usage surprise is unanticipated even by experts; stop chasing it"
    if weekly_not_measurable:
        return (
            "B as a measurement: the only untested explanation needs timestamped weekly data the "
            "repository lacks (not a news pipeline)"
        )
    # Not covered by the pre-registration's mapping -- say so rather than invent a direction.
    return "UNMAPPED: INCONCLUSIVE with weekly measurable and anticipated share >= 1/3"
