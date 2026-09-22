"""Exact, additive player-level regret, and the cohorts it is attributed to (W5).

The decomposition
-----------------
For depth *K*, a week's top-K points-capture shortfall is **exactly** additive over players:

    shortfall_K = sum_{i in realized top-K} pts_i  -  sum_{i in predicted top-K} pts_i
                = sum_i pts_i * ( 1[i in realized top-K] - 1[i in predicted top-K] )

so each player carries `regret_i = pts_i * (1[real top-K] - 1[pred top-K])`: **positive** for a
player the board missed, **negative** for one it wrongly promoted, and zero for everyone the
board got right or correctly ignored. Summing over any subset gives that subset's exact
contribution, with no modelling assumption and no residual term.

That exactness is why this is the attribution instrument rather than, say, a regression of error
on cohort dummies: a cohort's share of the shortfall is a fact about the week, not an estimate,
and the only inferential step left is whether that share is stable across weeks.

Cohorts
-------
Defined in `docs/weekly/W5_PREREGISTRATION.md` §8 with thresholds fixed before any result. They
are **not** mutually exclusive -- a rookie can also be LOW_SAMPLE -- so each is always reported
against its own complement, never against the other cohorts.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_squad.evaluation.weekly.context import (
    ELITE_DEPTH,
    HIGH_SNAP_PCT,
    LOW_SAMPLE_GAMES,
    RETURNING_GAP_WEEKS,
    PlayerContext,
)

COHORTS: tuple[str, ...] = (
    "ELITE_PRIOR_SEASON",
    "HOT_L3",
    "HIGH_SNAP",
    "LOW_SAMPLE",
    "ROOKIE",
    "TEAM_CHANGE",
    "RETURNING",
    "VOLATILE_ROLE",
    "OPPORTUNITY_UP",
    "OPPORTUNITY_DOWN",
)

#: Depths the regret decomposition is reported at. A subset of the pre-registered metric depths:
#: regret at depth 50 on a 55-player board is nearly the whole board and carries no information
#: about the TOP of it.
REGRET_DEPTHS: tuple[int, ...] = (5, 10, 20, 25)

#: FALSE POSITIVE / FALSE NEGATIVE definitions, frozen in the pre-registration §7.
FP_PRED_DEPTH, FP_REAL_DEPTH = 10, 24
FN_PRED_DEPTH, FN_REAL_DEPTH = 24, 5


def _quintile_flags(values: dict[str, float | None]) -> tuple[set[str], set[str]]:
    """Top and bottom quintile of a within-cell measure, ties resolved by `player_id`.

    Quintiles are computed **within (position, season, week)**, so a cohort is always about a
    fifth of that cell and cannot be inflated by a league-wide seasonal trend."""
    present = sorted(
        ((pid, v) for pid, v in values.items() if v is not None), key=lambda t: (-t[1], t[0])
    )
    if len(present) < 5:
        return set(), set()
    k = max(1, len(present) // 5)
    return {p for p, _ in present[:k]}, {p for p, _ in present[-k:]}


def assign_cohorts(
    season: int, contexts: dict[str, PlayerContext], universe: list[str]
) -> dict[str, set[str]]:
    """Cohort -> player ids, for one (position, season, week) cell."""
    hot_top, _ = _quintile_flags(
        {p: contexts[p].fp_ppr_avg_last3 for p in universe if p in contexts}
    )
    opp_up, opp_down = _quintile_flags(
        {p: contexts[p].opportunity_delta for p in universe if p in contexts}
    )
    sds = [
        contexts[p].snap_sd_prior3
        for p in universe
        if p in contexts and contexts[p].snap_sd_prior3 is not None
    ]
    median_sd = sorted(sds)[len(sds) // 2] if sds else None

    out: dict[str, set[str]] = {c: set() for c in COHORTS}
    for pid in universe:
        c = contexts.get(pid)
        if c is None:
            continue
        if c.prior_season_rank is not None and c.prior_season_rank <= ELITE_DEPTH:
            out["ELITE_PRIOR_SEASON"].add(pid)
        if pid in hot_top:
            out["HOT_L3"].add(pid)
        if c.snap_pct_avg_last3 is not None and c.snap_pct_avg_last3 >= HIGH_SNAP_PCT:
            out["HIGH_SNAP"].add(pid)
        if c.games_played_prior <= LOW_SAMPLE_GAMES:
            out["LOW_SAMPLE"].add(pid)
        if c.rookie_season == season:
            out["ROOKIE"].add(pid)
        if c.prior_team and c.team and c.prior_team != c.team:
            out["TEAM_CHANGE"].add(pid)
        if c.weeks_since_last_game is not None and c.weeks_since_last_game >= RETURNING_GAP_WEEKS:
            out["RETURNING"].add(pid)
        if median_sd is not None and c.snap_sd_prior3 is not None and c.snap_sd_prior3 > median_sd:
            out["VOLATILE_ROLE"].add(pid)
        if pid in opp_up:
            out["OPPORTUNITY_UP"].add(pid)
        if pid in opp_down:
            out["OPPORTUNITY_DOWN"].add(pid)
    return out


@dataclass
class PlayerRegret:
    player_id: str
    position: str
    season: int
    week: int
    predicted_rank: int
    realized_rank: int
    realized_points: float
    predicted_points: float
    regret: dict[int, float]
    false_positive: bool
    false_negative: bool


def player_regret(
    season: int,
    week: int,
    position: str,
    predictions: dict[str, float],
    realized: dict[str, float],
    depths: tuple[int, ...] = REGRET_DEPTHS,
) -> list[PlayerRegret]:
    """One row per evaluated player, carrying its exact contribution to each depth's shortfall.

    Ties are broken by `player_id` on both sides, the same deterministic backstop every other
    board in this package uses, so a rerun attributes regret to the same players."""
    universe = sorted(set(predictions) & set(realized))
    pred_order = sorted(universe, key=lambda p: (-predictions[p], p))
    real_order = sorted(universe, key=lambda p: (-realized[p], p))
    pred_rank = {p: i for i, p in enumerate(pred_order, start=1)}
    real_rank = {p: i for i, p in enumerate(real_order, start=1)}

    rows: list[PlayerRegret] = []
    for pid in universe:
        pr, rr = pred_rank[pid], real_rank[pid]
        pts = realized[pid]
        rows.append(
            PlayerRegret(
                player_id=pid,
                position=position,
                season=season,
                week=week,
                predicted_rank=pr,
                realized_rank=rr,
                realized_points=pts,
                predicted_points=predictions[pid],
                regret={k: pts * ((1 if rr <= k else 0) - (1 if pr <= k else 0)) for k in depths},
                false_positive=pr <= FP_PRED_DEPTH and rr > FP_REAL_DEPTH,
                false_negative=pr > FN_PRED_DEPTH and rr <= FN_REAL_DEPTH,
            )
        )
    return rows


def cohort_shares(
    rows: list[PlayerRegret], cohorts: dict[str, set[str]], depth: int
) -> dict[str, dict[str, float]]:
    """Each cohort's share of the week's **missed** points, against its share of the players.

    The two halves of the decomposition mean different things and are never summed:

    * **`missed_regret`** (positive terms) -- points from players who genuinely finished in the
      top-K and whom the board left out. This is the quantity a cohort is *blamed* for, and the
      one §9's materiality bar is written against.
    * **`slot_credit`** (the magnitude of the negative terms) -- points delivered by players the
      board *did* rank in the top-K who turned out not to belong there. Despite the intuition,
      this is **not** a measure of damage: those points were genuinely captured, and a bust who
      scores 0.0 contributes exactly 0.0 here, not a penalty. The cost of promoting a bust shows
      up as the *missed* regret of whoever he displaced, which is where it belongs -- counting it
      twice would double-charge the same shortfall.

    `false_positives` is the categorical companion that does measure bust promotion directly."""
    total_missed = sum(max(0.0, r.regret[depth]) for r in rows)
    total_credit = sum(-min(0.0, r.regret[depth]) for r in rows)
    n = len(rows)
    out: dict[str, dict[str, float]] = {}
    for name, members in cohorts.items():
        inside = [r for r in rows if r.player_id in members]
        missed = sum(max(0.0, r.regret[depth]) for r in inside)
        credit = sum(-min(0.0, r.regret[depth]) for r in inside)
        out[name] = {
            "n": float(len(inside)),
            "population_share": len(inside) / n if n else 0.0,
            "missed_regret": missed,
            "missed_share": missed / total_missed if total_missed > 0 else None,
            "slot_credit": credit,
            "slot_credit_share": credit / total_credit if total_credit > 0 else None,
            "false_positives": float(sum(1 for r in inside if r.false_positive)),
            "false_negatives": float(sum(1 for r in inside if r.false_negative)),
        }
    return out
