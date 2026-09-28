"""Quiet week or real role change? (W11). Pure functions, no I/O.

W10 found that last season's role and production lift Alpha's WR top 10, and that the same memory
costs at RB: it rescues established players through quiet weeks (+0.041 capture@10) but holds back
players whose role has genuinely grown (-0.055). W11 (`docs/weekly/W11_PREREGISTRATION.md`) asks
whether a pre-registered, pre-Friday comparison of the **current season's role** with **last
season's role** can tell the two apart, and whether giving it to W10's model lets current role
override stale history.

A player's *current role* is read only from this season's games **before** the predicted week
(Class A for a Friday cutoff): opportunity per game (targets + carries, the scale of W10's
`prior_opp_pg`) and offensive snap share (the scale of `prior_snap`). Persistence separates a
one-game fluctuation from a sustained change.
"""

from __future__ import annotations

import math
import random

from alpha_squad.evaluation.weekly import noise
from alpha_squad.evaluation.weekly.advantage import quantile

#: Pre-registered thresholds (touches per game, snap-share points). PRIMARY drives the verdict and
#: arm C; LOOSE and STRICT are reported for the mechanism test only and never select anything.
THRESHOLDS: dict[str, tuple[float, float]] = {
    "PRIMARY": (3.0, 0.15),
    "LOOSE": (2.0, 0.10),
    "STRICT": (4.0, 0.20),
}
#: The current-role window (last N current-season appearances) and the persistence rule (the
#: deviation must hold, in the same direction, in each of the last K current-season games).
WINDOW = 3
PERSISTENCE = 2

ROLE_FEATURES: tuple[str, ...] = ("role_d_opp", "role_d_snap", "role_shift")

#: First match wins.
CLASSES: tuple[str, ...] = (
    "NO_PRIOR",
    "TOO_EARLY",
    "ROLE_UP",
    "ROLE_DOWN",
    "ROLE_MIXED",
    "TRANSIENT",
    "QUIET",
    "STABLE",
)
CHANGE_CLASSES: tuple[str, ...] = ("ROLE_UP", "ROLE_DOWN", "ROLE_MIXED")
STABLE_CLASSES: tuple[str, ...] = ("QUIET", "STABLE")

#: Movers for the "is history stale?" test: in either board's top REGION, moved >= MOVE_MIN ranks.
REGION = 24
MOVE_MIN = 3

#: Model-verdict thresholds (pre-registration §8).
SUCCESS_BAR = 0.02
BREACH_FLOOR = 0.005
WR_MATERIAL = 0.01
MIN_SEASONS_POSITIVE = 4
MIN_LOSO_SIGNIFICANT = 4


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _mean(vals: list[float]) -> float | None:
    return math.fsum(vals) / len(vals) if vals else None


def _dev(game: dict, prior: dict, key: str, prior_key: str) -> float | None:
    if _missing(game.get(key)) or _missing(prior.get(prior_key)):
        return None
    return float(game[key]) - float(prior[prior_key])


def _direction(game: dict, prior: dict, tau_opp: float, tau_snap: float) -> set[str]:
    """{"UP"}, {"DOWN"}, {"UP","DOWN"} (conflicting measures) or empty, for one game."""
    out: set[str] = set()
    for key, prior_key, tau in (("opp", "prior_opp_pg", tau_opp), ("snap", "prior_snap", tau_snap)):
        d = _dev(game, prior, key, prior_key)
        if d is None:
            continue
        if d >= tau:
            out.add("UP")
        elif d <= -tau:
            out.add("DOWN")
    return out


def role_state(prior: dict, games: list[dict], tau_opp: float, tau_snap: float) -> dict:
    """The current-vs-history role state for one player-week.

    `prior`: the W9/W10 durable row (`has_prior`, `prior_opp_pg`, `prior_snap`, `prior_ppg`).
    `games`: this season's appearances **before** the predicted week, each with `week`, `opp`
    (targets + carries), `snap` and `ppr`. Returns the three model features and the class."""
    rows = sorted(games, key=lambda g: g["week"])
    recent = rows[-WINDOW:]
    has_prior = not _missing(prior.get("has_prior")) and float(prior["has_prior"]) == 1.0

    def delta(key: str, prior_key: str) -> float | None:
        vals = [float(g[key]) for g in recent if not _missing(g.get(key))]
        m = _mean(vals)
        if not has_prior or m is None or _missing(prior.get(prior_key)):
            return None
        return m - float(prior[prior_key])

    d_opp, d_snap = delta("opp", "prior_opp_pg"), delta("snap", "prior_snap")
    out = {"role_d_opp": d_opp, "role_d_snap": d_snap, "role_shift": None, "transient_dir": None}
    if not has_prior:
        return out | {"cls": "NO_PRIOR"}
    if len(rows) < PERSISTENCE:
        return out | {"cls": "TOO_EARLY"}
    dirs = [_direction(g, prior, tau_opp, tau_snap) for g in rows[-PERSISTENCE:]]
    up = all("UP" in d for d in dirs)
    down = all("DOWN" in d for d in dirs)
    if up and down:
        return out | {"role_shift": 0.0, "cls": "ROLE_MIXED"}
    if up:
        return out | {"role_shift": 1.0, "cls": "ROLE_UP"}
    if down:
        return out | {"role_shift": -1.0, "cls": "ROLE_DOWN"}
    last = dirs[-1]
    if last:
        tdir = "UP" if last == {"UP"} else "DOWN" if last == {"DOWN"} else "MIXED"
        return out | {"role_shift": 0.0, "cls": "TRANSIENT", "transient_dir": tdir}
    ppg = _mean([float(g["ppr"] or 0.0) for g in recent])
    quiet = (
        not _missing(prior.get("prior_ppg")) and ppg is not None and ppg < float(prior["prior_ppg"])
    )
    return out | {"role_shift": 0.0, "cls": "QUIET" if quiet else "STABLE"}


def group_of(cls: str) -> str | None:
    if cls in CHANGE_CLASSES:
        return "CHANGE"
    if cls in STABLE_CLASSES:
        return "STABLE"
    return None


def move_outcome(rank_a: int, rank_b: int, rank_real: int) -> str | None:
    """For a substantial mover: did B's move bring the player closer to where they finished?
    "RIGHT", "WRONG", or None (equal distance)."""
    ea, eb = abs(rank_a - rank_real), abs(rank_b - rank_real)
    if eb < ea:
        return "RIGHT"
    if eb > ea:
        return "WRONG"
    return None


def is_mover(rank_a: int, rank_b: int) -> bool:
    return min(rank_a, rank_b) <= REGION and abs(rank_a - rank_b) >= MOVE_MIN


# ---------------------------------------------------------------------------------------
# Statistics: a difference of two pooled ratios, bootstrapped over weeks
# ---------------------------------------------------------------------------------------


def ratio_diff_ci(
    num1: dict[str, float], den1: dict[str, float], num2: dict[str, float], den2: dict[str, float]
) -> dict | None:
    """(Σnum1/Σden1) − (Σnum2/Σden2) over weeks, with a week-cluster bootstrap using `noise`'s
    seeds and resample count. A week missing from a series contributes 0 to it."""
    weeks = sorted(set(num1) | set(den1) | set(num2) | set(den2))
    if len(weeks) < 3:
        return None
    cols = [[float(s.get(w, 0.0)) for w in weeks] for s in (num1, den1, num2, den2)]

    def stat(ix) -> float | None:
        n1, d1, n2, d2 = (math.fsum(c[i] for i in ix) for c in cols)
        if d1 == 0 or d2 == 0:
            return None
        return n1 / d1 - n2 / d2

    point = stat(range(len(weeks)))
    if point is None:
        return None
    lows, highs = [], []
    per_seed = max(1, noise.BOOTSTRAP_RESAMPLES // len(noise.BOOTSTRAP_SEEDS))
    n = len(weeks)
    for seed in noise.BOOTSTRAP_SEEDS:
        rng = random.Random(seed)
        vals = []
        for _ in range(per_seed):
            v = stat([rng.randrange(n) for _ in range(n)])
            if v is not None:
                vals.append(v)
        vals.sort()
        lows.append(quantile(vals, 0.025))
        highs.append(quantile(vals, 0.975))
    lo, hi = math.fsum(lows) / len(lows), math.fsum(highs) / len(highs)
    return {
        "diff": point,
        "ci_low": lo,
        "ci_high": hi,
        "excludes_zero": lo > 0.0 or hi < 0.0,
        "n_weeks": n,
        "rate_1": math.fsum(cols[0]) / math.fsum(cols[1]),
        "rate_2": math.fsum(cols[2]) / math.fsum(cols[3]),
        "n_1": math.fsum(cols[1]),
        "n_2": math.fsum(cols[3]),
    }


# ---------------------------------------------------------------------------------------
# Pre-registered decisions
# ---------------------------------------------------------------------------------------


def _pos(r: dict | None) -> bool:
    return bool(r) and r["ci_low"] > 0.0


def _neg(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0


def mechanism(m1: dict | None, m2: dict | None, m3: dict | None, rel: dict | None) -> dict:
    """§5: M1 (history helps QUIET: attribution > 0) and M2 (history hurts ROLE_UP: < 0) both
    with CIs excluding 0 establish the mechanism at a position. M3 (history's moves are wrong
    more often for role changers) and R (sustained changes persist more than one-game ones)
    answer "can it be seen before the game" and are reported, not required."""
    c = {
        "M1": _pos(m1),
        "M2": _neg(m2),
        "M3": bool(m3) and m3["ci_low"] > 0.0,
        "R": bool(rel) and rel["ci_low"] > 0.0,
    }
    return {"conditions": c, "established": c["M1"] and c["M2"]}


def is_breach(r: dict | None) -> bool:
    return bool(r) and r["ci_high"] < 0.0 and abs(r["mean_diff"]) >= BREACH_FLOOR


def model_verdict(inputs: dict) -> dict:
    """§8, evaluated in order. `inputs`:

    - mechanism_established: bool (from the mechanism stage, RB or WR)
    - rb: C − B RB capture@10 row;  rb_role_up: C − B attribution to ROLE_UP (row)
    - rb_null: C − N RB capture@10 row
    - rb_seasons: per-season C − B RB capture@10 point estimates; rb_loso: LOSO rows
    - wr: C − B WR capture@10 row;  wr_vs_a: C − A WR capture@10 row
    - guard: {name: C − B row} for every breach-eligible metric
    - any_gain: {name: C − B row} capture@10 at RB/WR/TE (for PARTIAL route d)
    """
    if not inputs.get("mechanism_established"):
        return {"verdict": "MECHANISM NOT ESTABLISHED", "conditions": {}, "breaches": []}
    rb, up = inputs.get("rb"), inputs.get("rb_role_up")
    breaches = sorted(n for n, r in inputs.get("guard", {}).items() if is_breach(r))
    wr = inputs.get("wr")
    wr_ok = bool(wr) and not is_breach(wr) and wr["mean_diff"] > -WR_MATERIAL
    s1 = _pos(rb) and (
        rb["mean_diff"] >= SUCCESS_BAR or (_pos(up) and up["mean_diff"] >= SUCCESS_BAR)
    )
    c = {
        "S1_rb_improves": s1,
        "S2_wr_preserved": wr_ok and _pos(inputs.get("wr_vs_a")),
        "S3_no_breach": not breaches,
        "S4_beats_null": _pos(inputs.get("rb_null")),
        "S5_consistent": (
            sum(1 for v in inputs.get("rb_seasons", []) if v > 0) >= MIN_SEASONS_POSITIVE
            and sum(1 for r in inputs.get("rb_loso", []) if _pos(r)) >= MIN_LOSO_SIGNIFICANT
        ),
    }
    wr_harm = not wr_ok
    if all(c.values()):
        label = "SUCCESS"
    elif s1 and (breaches or wr_harm):
        label = "TRADEOFF"
    elif breaches or wr_harm:
        label = "HARM"
    elif (
        s1
        or (rb and rb["mean_diff"] >= SUCCESS_BAR)
        or _pos(up)
        or any(
            _pos(r) and r["mean_diff"] >= SUCCESS_BAR for r in inputs.get("any_gain", {}).values()
        )
    ):
        label = "PARTIAL"
    else:
        label = "NO EFFECT"
    return {"verdict": label, "conditions": c, "breaches": breaches, "wr_harm": wr_harm}
