"""Weekly optimal-lineup value, vectorized across simulations (Model F building block).

``compute_league_starters`` (``league/replacement.py``) is the repository's lineup allocator, but
it works one lineup at a time on scalar values and pools every flex-type slot together. A trade
evaluation needs the lineup re-optimized every week of every simulated season, so this module
re-implements the same allocation rule -- dedicated slots first, then flex slots from what is left
-- on arrays of shape ``(n_sims,)``, and treats each flex *type* in order of restrictiveness
(WRRB_FLEX, FLEX, SUPERFLEX) so a QB can never be used to fill a plain FLEX.

For nested eligibility sets (every league config this repo can express) this greedy order is
optimal; ``tests/unit/test_ros_lineup.py`` checks it against an exact assignment solver on random
rosters, and checks agreement with ``compute_league_starters`` where the two are comparable.

Lineup slot vocabulary is the repo's: ``league/context.py::FLEX_ELIGIBILITY`` for flex types and
``normalize_slot_position`` (``DEF`` -> ``DST``) for dedicated slots.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from alpha_squad.league.context import FLEX_ELIGIBILITY, LeagueContext

UNAVAILABLE = -1e9  # sentinel for "cannot be started this week" (bye, injured)


@dataclass(frozen=True)
class SlotPlan:
    dedicated: dict[str, int]  # player position -> slots
    flex: tuple[
        tuple[str, tuple[str, ...]], ...
    ]  # (slot name, eligible positions), restrictive first


def slot_plan(league: LeagueContext, exclude: tuple[str, ...] = ()) -> SlotPlan:
    """Lineup slots of ``league``. ``exclude`` drops player positions whose slots a particular
    analysis cannot score (e.g. K/DST in the roster-level backtest, which have no scored
    history here); they are unaffected by a QB trade."""
    dedicated = {p: n for p, n in league.dedicated_slots().items() if p not in exclude}
    flex: list[tuple[str, tuple[str, ...]]] = []
    for name, count in league.flex_slots().items():
        elig = tuple(FLEX_ELIGIBILITY.get(name, ()))
        flex.extend([(name, elig)] * int(count))
    flex.sort(key=lambda t: len(t[1]))
    return SlotPlan(dedicated, tuple(flex))


def best_lineup_value(
    plan: SlotPlan,
    values: dict[str, np.ndarray],
    positions: dict[str, str],
    *,
    scores: dict[str, np.ndarray] | None = None,
    return_starters: bool = False,
):
    """Best legal lineup total for each simulation.

    ``values[player]`` has shape ``(n_sims,)`` and is what the lineup is CHOSEN by; use
    ``UNAVAILABLE`` where the player cannot start. If ``scores`` is given the chosen players are
    SCORED with it instead: ``values`` = what the manager knew when setting the lineup (forecasts),
    ``scores`` = what actually happened. With ``scores=None`` the lineup is picked with hindsight
    (optimistic: it lets a bench player who happened to boom replace a starter every week).
    Unfillable slots score 0. Returns ``(n_sims,)`` totals (and, if requested, a dict
    ``player -> boolean array`` of sims in which that player starts)."""
    if not values:
        return (np.zeros(1), {}) if return_starters else np.zeros(1)
    n = len(next(iter(values.values())))
    by_pos: dict[str, list[str]] = {}
    for pid in values:
        by_pos.setdefault(positions[pid], []).append(pid)

    total = np.zeros(n)
    started = {pid: np.zeros(n, dtype=bool) for pid in values} if return_starters else {}
    # per position: players sorted by value per sim (descending), with ids carried along
    order: dict[str, np.ndarray] = {}
    sorted_vals: dict[str, np.ndarray] = {}
    sorted_scores: dict[str, np.ndarray] = {}
    ids: dict[str, list[str]] = {}
    for pos, plist in by_pos.items():
        mat = np.vstack([values[p] for p in plist])  # (k, n)
        idx = np.argsort(-mat, axis=0, kind="stable")
        order[pos] = idx
        sorted_vals[pos] = np.take_along_axis(mat, idx, axis=0)
        smat = mat if scores is None else np.vstack([scores[p] for p in plist])
        sorted_scores[pos] = np.take_along_axis(smat, idx, axis=0)
        ids[pos] = plist
    head = {pos: np.zeros(n, dtype=int) for pos in by_pos}

    def take(pos: str, mask: np.ndarray) -> None:
        h = head[pos]
        cols = np.where(mask)[0]
        if return_starters and len(cols):
            who = order[pos][h[cols], cols]
            for pi, c in zip(who, cols, strict=True):
                started[ids[pos][pi]][c] = True
        head[pos] = h + mask.astype(int)

    def head_val(pos: str) -> np.ndarray:
        k = sorted_vals[pos].shape[0]
        h = head[pos]
        v = np.full(n, UNAVAILABLE)
        ok = h < k
        v[ok] = sorted_vals[pos][h[ok], np.where(ok)[0]]
        return v

    def head_score(pos: str) -> np.ndarray:
        k = sorted_scores[pos].shape[0]
        h = head[pos]
        v = np.zeros(n)
        ok = h < k
        v[ok] = sorted_scores[pos][h[ok], np.where(ok)[0]]
        return v

    for pos, slots in plan.dedicated.items():
        if pos not in by_pos:
            continue
        for _ in range(slots):
            v = head_val(pos)
            ok = v > UNAVAILABLE / 2
            total += np.where(ok, head_score(pos), 0.0)
            take(pos, ok)

    for _, elig in plan.flex:
        cand = [p for p in elig if p in by_pos]
        if not cand:
            continue
        heads = np.vstack([head_val(p) for p in cand])  # (len(cand), n)
        best = np.argmax(heads, axis=0)
        bv = heads[best, np.arange(n)]
        ok = bv > UNAVAILABLE / 2
        hs = np.vstack([head_score(p) for p in cand])
        total += np.where(ok, hs[best, np.arange(n)], 0.0)
        for k, p in enumerate(cand):
            take(p, ok & (best == k))
    return (total, started) if return_starters else total


def season_lineup_value(
    plan: SlotPlan,
    weekly: dict[str, np.ndarray],
    positions: dict[str, str],
    weeks: list[int] | None = None,
    scores: dict[str, np.ndarray] | None = None,
) -> np.ndarray:
    """Sum over weeks of the best lineup. ``weekly[player]`` has shape ``(n_weeks, n_sims)``."""
    n_weeks = next(iter(weekly.values())).shape[0]
    wk = range(n_weeks) if weeks is None else weeks
    total = None
    for w in wk:
        v = best_lineup_value(
            plan,
            {p: a[w] for p, a in weekly.items()},
            positions,
            scores=None if scores is None else {p: a[w] for p, a in scores.items()},
        )
        total = v if total is None else total + v
    return total if total is not None else np.zeros(1)
