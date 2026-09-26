"""Does historical player knowledge improve Alpha? (W10). Pure functions, no I/O.

W9 found ECR's top-of-board usage edge is largely durable knowledge of who a player is. W10
tests the practical consequence (`docs/weekly/W10_PREREGISTRATION.md`): Alpha plus the seven
prior-season features W9 defined (arm B, frozen -- never re-specified), against current Alpha
(arm A), a historical-only baseline (C), a permuted-feature null (N) and attribution-only
ablations. This module holds the instrument's pure parts: the baseline ordering, the W5 miss
counts, the movement categories and the pre-registered §5 verdict order.
"""

from __future__ import annotations

import math

from alpha_squad.evaluation.weekly.regret import (
    FN_PRED_DEPTH,
    FN_REAL_DEPTH,
    FP_PRED_DEPTH,
    FP_REAL_DEPTH,
)

#: The historical categories of W9's seven features (pre-registration §2). Efficiency: none.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "production": ("prior_ppg", "prior_rank"),
    "opportunity": ("prior_opp_pg", "prior_tsh"),
    "role": ("prior_snap", "prior_games", "has_prior"),
}

#: Movement categories, first match wins (§6.5).
MOVEMENT_CATEGORIES: tuple[str, ...] = (
    "QUIET_STAR",
    "SMALL_SAMPLE",
    "ROLE_STRONGER_BEFORE",
    "ROLE_STRONGER_NOW",
    "OTHER",
)
SMALL_SAMPLE_GAMES = 3
ROLE_GAP = 3.0
ELITE_MAX_RANK = 12

#: §5 thresholds.
SUCCESS_BAR = 0.02
BREACH_FLOOR = 0.005
MIN_SEASONS_POSITIVE = 4
MIN_LOSO_SIGNIFICANT = 4
ECR_GAP_SHARE = 1.0 / 3.0


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def historical_only_order(ids: list[str], prior_ppg: dict[str, float | None]) -> list[str]:
    """Arm C: prior-season PPG descending; players with no prior season last, by `player_id`.
    No model and no Alpha tiebreak -- the point is what history alone knows."""
    have = [p for p in ids if not _missing(prior_ppg.get(p))]
    none = sorted(p for p in ids if _missing(prior_ppg.get(p)))
    return sorted(have, key=lambda p: (-float(prior_ppg[p]), p)) + none


def realized_ranks(pts: dict[str, float]) -> dict[str, int]:
    order = sorted(pts, key=lambda p: (-pts[p], p))
    return {p: n for n, p in enumerate(order, start=1)}


def miss_counts(order: list[str], pts: dict[str, float]) -> dict[str, int]:
    """W5's pre-registered misses for one board-week: FALSE POSITIVE (predicted top-10, finished
    outside the realized top-24) and FALSE NEGATIVE (realized top-5, predicted outside top-24)."""
    real = realized_ranks(pts)
    pred = {p: n for n, p in enumerate(order, start=1)}
    fp = sum(1 for p in order if pred[p] <= FP_PRED_DEPTH and real[p] > FP_REAL_DEPTH)
    fn = sum(1 for p in order if real[p] <= FN_REAL_DEPTH and pred[p] > FN_PRED_DEPTH)
    return {"false_positive": fp, "false_negative": fn}


def quiet_star(prior_rank, last_pts, prior_ppg) -> bool:
    """A prior-season ELITE player whose most recent game was below their prior-season PPG."""
    if _missing(prior_rank) or _missing(last_pts) or _missing(prior_ppg):
        return False
    return float(prior_rank) <= ELITE_MAX_RANK and float(last_pts) < float(prior_ppg)


def movement_category(
    prior_rank, last_pts, prior_ppg, games_this_season, prior_opp_pg, recent_opp
) -> str:
    if quiet_star(prior_rank, last_pts, prior_ppg):
        return "QUIET_STAR"
    if not _missing(games_this_season) and float(games_this_season) < SMALL_SAMPLE_GAMES:
        return "SMALL_SAMPLE"
    if not _missing(prior_opp_pg) and not _missing(recent_opp):
        gap = float(prior_opp_pg) - float(recent_opp)
        if gap >= ROLE_GAP:
            return "ROLE_STRONGER_BEFORE"
        if -gap >= ROLE_GAP:
            return "ROLE_STRONGER_NOW"
    return "OTHER"


# ---------------------------------------------------------------------------------------
# The pre-registered §5 verdict
# ---------------------------------------------------------------------------------------


def _sig_pos(r: dict | None) -> bool:
    return bool(r) and r["ci_low"] > 0.0


def meets_s1(r: dict | None) -> bool:
    return _sig_pos(r) and r["mean_diff"] >= SUCCESS_BAR


def is_breach(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0 and abs(r["mean_diff"]) >= BREACH_FLOOR


def success_conditions(cell: dict) -> dict[str, bool]:
    """S1-S4 for one success cell. `cell` carries: full, seasons (list of point estimates),
    loso (list of rows), early, late (rows) and ecr_minus_a (the ECR - A mean difference)."""
    full = cell.get("full")
    s1 = meets_s1(full)
    s2 = (
        sum(1 for v in cell.get("seasons", []) if v > 0) >= MIN_SEASONS_POSITIVE
        and sum(1 for r in cell.get("loso", []) if _sig_pos(r)) >= MIN_LOSO_SIGNIFICANT
    )
    ecr = cell.get("ecr_minus_a")
    s3 = bool(full) and ecr is not None and ecr > 0 and full["mean_diff"] / ecr >= ECR_GAP_SHARE
    early, late = cell.get("early"), cell.get("late")
    s4 = bool(early and late) and early["mean_diff"] > 0 and early["mean_diff"] >= late["mean_diff"]
    return {"S1": bool(s1), "S2": bool(s2), "S3": bool(s3), "S4": bool(s4)}


def verdict(success_cells: dict[str, dict], all_cells: dict[str, dict], guardrails: dict) -> dict:
    """`success_cells`: {"RB|capture@10": cell, ...} for RB/WR capture@5/@10.
    `all_cells`: the same shape for every position's capture@5/@10 (for HARM / PARTIAL).
    `guardrails`: {name: row} for every breach-eligible metric."""
    breaches = sorted(n for n, r in guardrails.items() if is_breach(r))
    conds = {n: success_conditions(c) for n, c in success_cells.items()}
    winners = sorted(n for n, c in conds.items() if all(c.values()) and not breaches)
    full_s1 = sorted(n for n, c in all_cells.items() if meets_s1(c.get("full")))
    early_s1 = sorted(n for n, c in all_cells.items() if meets_s1(c.get("early")))
    if winners:
        label = "SUCCESS"
    elif breaches and not full_s1 and not early_s1:
        label = "HARM"
    elif full_s1 or early_s1:
        label = "PARTIAL"
    else:
        label = "NO EFFECT"
    return {
        "verdict": label,
        "success_cells": winners,
        "conditions": conds,
        "breaches": breaches,
        "full_season_s1_cells": full_s1,
        "early_s1_cells": early_s1,
        "tradeoff": bool(breaches) and label in ("PARTIAL",),
    }
