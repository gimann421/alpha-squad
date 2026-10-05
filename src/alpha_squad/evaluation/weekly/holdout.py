"""The untouched-2026 out-of-sample validation of W10 (W14). Pure functions, no I/O.

W10 found that giving Alpha last season's role and production lifts its WR top 10 (2021-2025,
retrospective). Its pre-registration §9 froze a 2026 test before any 2026 data existed. W14
(`docs/weekly/W14_PREREGISTRATION.md`) runs that test on the 2026 weeks that are complete, and adds
what §9 left open: which weeks are eligible, how an interim look is read, and how a 2026 result is
compared with W10's own history. This module holds those rules.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import random

#: Fewer eligible weeks than this and no test is attempted (§7: INCONCLUSIVE, invalid).
MIN_WEEKS_VALID = 3
#: Before this many eligible weeks an interim look reads no direction (§7).
MIN_WEEKS_DIRECTION = 8
#: W10's guardrail breach: a CI excluding 0, negative, of magnitude at least this.
BREACH_FLOOR = 0.005
#: Exact sign-flip enumeration up to this many weeks (2**20 patterns); Monte Carlo above.
EXACT_MAX_N = 20
MC_DRAWS = 100_000
MC_SEED = 14
#: The historical predictive band: n-week means resampled from W10's weekly differences.
BAND_DRAWS = 100_000
BAND_SEED = 14
BAND_LOW = 0.025
#: A week's last game must have kicked off this long before the data was captured.
COMPLETE_BUFFER = dt.timedelta(hours=6)

REPLICATED = "REPLICATED"
PARTIAL = "PARTIAL REPLICATION"
NOT_REPLICATED = "NOT REPLICATED"
INCONCLUSIVE = "INCONCLUSIVE"
INCONCLUSIVE_CONTINUE = "INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT"


# ---------------------------------------------------------------------------------------
# Week eligibility
# ---------------------------------------------------------------------------------------


def week_eligibility(
    scheduled: set[tuple[str, str]],
    played: set[tuple[str, str]],
    teams_with_stats: set[str],
    last_kickoff: dt.datetime | None,
    captured: dt.datetime,
) -> tuple[bool, str]:
    """Is a week complete in the data? `scheduled`: (home, away) of every REG game on the nflverse
    schedule. `played`: those present in the pbp-derived `games` table. `teams_with_stats`: teams
    with at least one player-week stats row. `last_kickoff` / `captured`: aware datetimes."""
    if not scheduled:
        return False, "no scheduled games"
    missing = sorted(scheduled - played)
    if missing:
        return False, f"{len(missing)} scheduled game(s) not in the data: {missing}"
    teams = {t for g in scheduled for t in g}
    no_stats = sorted(teams - teams_with_stats)
    if no_stats:
        return False, f"teams without stats: {no_stats}"
    if last_kickoff is None or last_kickoff + COMPLETE_BUFFER > captured:
        return False, f"last kickoff {last_kickoff} not {COMPLETE_BUFFER} before capture {captured}"
    return True, "complete"


# ---------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------


def sign_flip_p(diffs: list[float]) -> dict:
    """Two-sided sign-flip permutation p for a mean paired difference.

    Under H0 each week's difference is equally likely to carry either sign. Statistic: |mean|.
    Exact over all 2**n sign patterns for n <= EXACT_MAX_N, else seeded Monte Carlo. Also returns
    the smallest p the sample could have produced (2 / 2**n when exact)."""
    xs = [float(d) for d in diffs]
    n = len(xs)
    if not n:
        return {"p": math.nan, "method": "none", "n": 0, "min_attainable": math.nan}
    obs = abs(math.fsum(xs)) / n
    tol = 1e-12
    if n <= EXACT_MAX_N:
        hits = 0
        for signs in itertools.product((1.0, -1.0), repeat=n):
            s = math.fsum(sg * x for sg, x in zip(signs, xs, strict=True))
            hits += int(abs(s) / n >= obs - tol)
        total = 2**n
        nonzero = any(abs(x) > 0 for x in xs)
        return {
            "p": hits / total,
            "method": "exact",
            "n": n,
            "patterns": total,
            "min_attainable": (2 / total) if nonzero else 1.0,
        }
    rng = random.Random(MC_SEED)
    hits = 0
    for _ in range(MC_DRAWS):
        s = math.fsum(x if rng.random() < 0.5 else -x for x in xs)
        hits += int(abs(s) / n >= obs - tol)
    return {
        "p": (1 + hits) / (1 + MC_DRAWS),
        "method": "monte_carlo",
        "n": n,
        "draws": MC_DRAWS,
        "min_attainable": 1 / (1 + MC_DRAWS),
    }


def predictive_band(history: list[float], n: int, value: float | None = None) -> dict:
    """Where an n-week mean would fall if 2026 were drawn like W10's history.

    Resamples n weekly differences with replacement from `history` (W10's committed per-week
    B - A values), BAND_DRAWS times, seeded. Returns the 2.5/50/97.5 percentiles and, for
    `value`, the share of resampled means at or below it."""
    hs = [float(h) for h in history]
    if not hs or n < 1:
        return {}
    rng = random.Random(BAND_SEED)
    means = sorted(
        math.fsum(hs[rng.randrange(len(hs))] for _ in range(n)) / n for _ in range(BAND_DRAWS)
    )

    def q(p: float) -> float:
        return means[min(len(means) - 1, max(0, int(round(p * (len(means) - 1)))))]

    out = {
        "n_weeks": n,
        "draws": BAND_DRAWS,
        "p025": q(BAND_LOW),
        "p50": q(0.5),
        "p975": q(1 - BAND_LOW),
    }
    if value is not None:
        lo, hi = 0, len(means)
        while lo < hi:  # number of resampled means <= value
            mid = (lo + hi) // 2
            if means[mid] <= value:
                lo = mid + 1
            else:
                hi = mid
        out["value"] = value
        out["percentile"] = lo / len(means)
    return out


# ---------------------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------------------


def is_breach(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0 and abs(r["mean_diff"]) >= BREACH_FLOOR


def section9(wr10: dict | None, wr5: dict | None) -> bool:
    """W10 pre-registration §9, verbatim: WR capture@10 and capture@5 B - A point estimates both
    positive, and the WR capture@10 CI excludes 0."""
    return (
        bool(wr10)
        and bool(wr5)
        and wr10["mean_diff"] > 0
        and wr5["mean_diff"] > 0
        and wr10["ci_low"] > 0
    )


def classify(inputs: dict) -> dict:
    """The §7 rule. `inputs`:

    - `valid`: every validity gate passed and W10 ran unmodified;
    - `final`: every week 1-17 is evaluated or permanently unavailable;
    - `n_weeks`; `wr10`, `wr5` (B - A rows); `band` (`predictive_band` for wr10's mean);
    - `guard` ({name: B - A row}, W10's guardrail set)."""
    n = int(inputs.get("n_weeks", 0))
    wr10, wr5 = inputs.get("wr10"), inputs.get("wr5")
    band = inputs.get("band") or {}
    final = bool(inputs.get("final"))
    breaches = sorted(k for k, r in (inputs.get("guard") or {}).items() if is_breach(r))
    s9 = section9(wr10, wr5)
    reasons: list[str] = []

    def out(label: str) -> dict:
        return {
            "verdict": label,
            "look": "FINAL" if final else "INTERIM",
            "n_weeks": n,
            "section9_holds": s9 if final else None,
            "section9_point_estimates": s9,
            "breaches": breaches,
            "reasons": reasons,
        }

    if not inputs.get("valid") or n < MIN_WEEKS_VALID or not wr10:
        reasons.append("invalid test: a gate failed, W10 could not run, or too few weeks")
        return out(INCONCLUSIVE)
    if wr10["ci_high"] < 0:
        reasons.append("WR capture@10 CI entirely below 0")
    if band and "p025" in band and wr10["mean_diff"] < band["p025"]:
        reasons.append("WR capture@10 below the 2.5th percentile of W10's predictive band")
    if final and wr10["mean_diff"] <= 0:
        reasons.append("WR capture@10 not positive over the full season")
    if reasons:
        return out(NOT_REPLICATED)
    if final:
        if s9 and not breaches:
            reasons.append("§9 holds and no guardrail breach")
            return out(REPLICATED)
        reasons.append("WR capture@10 positive" + ("; §9 holds with a breach" if s9 else ""))
        return out(PARTIAL)
    if n >= MIN_WEEKS_DIRECTION and wr10["mean_diff"] > 0 and wr5 and wr5["mean_diff"] > 0:
        reasons.append(f"interim, n >= {MIN_WEEKS_DIRECTION}: both WR point estimates positive")
        return out(PARTIAL)
    reasons.append(
        f"interim with n = {n}: too few weeks to read a direction"
        if n < MIN_WEEKS_DIRECTION
        else "interim: direction not established"
    )
    return out(INCONCLUSIVE_CONTINUE)
