"""A player's own Friday injury designation and the FLEX top 10 (W13). Pure functions, no I/O.

W12 found a suggestive FLEX capture@10 gain from a player's own injury-report entry that did not
clear a permuted-feature null. W13 (`docs/weekly/W13_PREREGISTRATION.md`) re-tests exactly that
signal on W10's model: W10 + `own_status` + `own_practice`, built by W12's timestamped pipeline.
This module holds the status groups, the sign-flip permutation p-value and the pre-registered
six-condition decision.
"""

from __future__ import annotations

import math
import random

from alpha_squad.evaluation.weekly import timestamped as ts

OWN_FEATURES: tuple[str, ...] = ts.CATEGORIES["own"]
STATUS_GROUPS: tuple[str, ...] = ("NONE", "Q", "D", "O", "NO_REPORT")

MDE_BAR = 0.011
BREACH_FLOOR = 0.005
WR_MATERIAL = 0.01
LOSO_SIGNIFICANT = 3
N_PERMUTATIONS = 100_000
PERMUTATION_SEED = 13


def status_group(own_status) -> str:
    if own_status is None or (isinstance(own_status, float) and math.isnan(own_status)):
        return "NO_REPORT"
    return {0.0: "NONE", 1.0: "Q", 2.0: "D", 3.0: "O"}[float(own_status)]


def sign_flip_p(diffs: list[float], n: int = N_PERMUTATIONS, seed: int = PERMUTATION_SEED) -> float:
    """Two-sided Monte Carlo sign-flip permutation p-value for a mean paired difference.

    Under H0 each week's difference is equally likely to have either sign. The statistic is
    |mean|; p = (1 + #{|mean of flipped| >= |observed|}) / (1 + n). Deterministic for a seed."""
    xs = [float(d) for d in diffs]
    if not xs:
        return math.nan
    obs = abs(math.fsum(xs)) / len(xs)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n):
        s = math.fsum(x if rng.random() < 0.5 else -x for x in xs)
        hits += int(abs(s) / len(xs) >= obs - 1e-15)
    return (1 + hits) / (1 + n)


def _pos(r: dict | None) -> bool:
    return bool(r) and r["ci_low"] > 0.0


def is_breach(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0 and abs(r["mean_diff"]) >= BREACH_FLOOR


def verdict(inputs: dict) -> dict:
    """The §7 rule. `inputs`: flex (B − A FLEX capture@10 row), loso (4 rows), null (B − N row),
    half (Half-PPR B − A row), wr (B − A WR capture@10), wr_vs_prod (B − CF_A WR capture@10),
    guard ({name: B − A row})."""
    flex = inputs.get("flex")
    loso = inputs.get("loso", [])
    breaches = sorted(n for n, r in inputs.get("guard", {}).items() if is_breach(r))
    wr = inputs.get("wr")
    wr_ok = bool(wr) and not is_breach(wr) and wr["mean_diff"] > -WR_MATERIAL
    c = {
        "C1_mde": bool(flex) and flex["mean_diff"] >= MDE_BAR,
        "C2_ci": _pos(flex),
        "C3_loso": (
            len(loso) == 4
            and all(r["mean_diff"] > 0 for r in loso)
            and sum(1 for r in loso if _pos(r)) >= LOSO_SIGNIFICANT
        ),
        "C4_beats_null": _pos(inputs.get("null")),
        "C5_half_ppr": bool(inputs.get("half")) and inputs["half"]["mean_diff"] > 0,
        "C6_wr_guardrail": wr_ok and _pos(inputs.get("wr_vs_prod")) and not breaches,
    }
    first_five = all(c[k] for k in ("C1_mde", "C2_ci", "C3_loso", "C4_beats_null", "C5_half_ppr"))
    if first_five and c["C6_wr_guardrail"]:
        label = "CONFIRMED INCREMENTAL SIGNAL"
    elif first_five:
        label = "TRADEOFF"
    else:
        label = "NO CONFIRMED INCREMENTAL SIGNAL"
    return {"verdict": label, "conditions": c, "breaches": breaches}
