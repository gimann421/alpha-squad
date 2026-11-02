"""Vectorized weekly lineup optimizer (alpha_squad.ros.lineup)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.replacement import compute_league_starters
from alpha_squad.ros.lineup import UNAVAILABLE, best_lineup_value, slot_plan

pytestmark = pytest.mark.unit


def league(lineup: dict[str, int]) -> LeagueContext:
    return LeagueContext(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup=lineup,
        roster={"bench": 6, "roster_size": 16},
    )


def exact_best(plan, vals: dict[str, float], pos: dict[str, str]) -> float:
    """Exact assignment solver over expanded slots -- the oracle the greedy must match."""
    slots = [[p] for p, n in plan.dedicated.items() for _ in range(n)] + [
        list(e) for _, e in plan.flex
    ]
    ids = list(vals)
    cost = np.zeros((len(slots), len(ids)))
    for i, elig in enumerate(slots):
        for j, p in enumerate(ids):
            cost[i, j] = -vals[p] if pos[p] in elig else 1e6
    r, c = linear_sum_assignment(cost)
    return float(sum(-cost[i, j] for i, j in zip(r, c, strict=True) if cost[i, j] < 1e5))


def test_matches_exact_solver_on_random_rosters_including_superflex():
    rng = np.random.default_rng(1)
    for lineup in (
        {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
        {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 1},
        {"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
    ):
        plan = slot_plan(league(lineup))
        for _ in range(60):
            pos = {
                f"p{i}": rng.choice(["QB", "RB", "WR", "TE"], p=[0.15, 0.35, 0.35, 0.15])
                for i in range(16)
            }
            vals = {p: float(rng.uniform(0, 30)) for p in pos}
            got = best_lineup_value(plan, {p: np.array([v]) for p, v in vals.items()}, pos)[0]
            assert got == pytest.approx(exact_best(plan, vals, pos))


def test_agrees_with_the_repos_allocator_where_comparable():
    lg = load_league_context()
    from alpha_squad.ros.rosterbench import lineup_league

    lg = lineup_league(lg)
    rng = np.random.default_rng(2)
    plan = slot_plan(lg)
    for _ in range(40):
        pos = {f"p{i}": rng.choice(["QB", "RB", "WR", "TE"]) for i in range(14)}
        vals = {p: float(rng.uniform(1, 25)) for p in pos}
        ref = compute_league_starters(lg.model_copy(update={"teams": 1}), vals, pos)
        want = sum(vals[p] for p in ref["starters"])
        got = best_lineup_value(plan, {p: np.array([v]) for p, v in vals.items()}, pos)[0]
        assert got == pytest.approx(want)


def test_unavailable_players_are_skipped_and_empty_slots_score_zero():
    plan = slot_plan(league({"QB": 1, "RB": 1}))
    pos = {"q1": "QB", "q2": "QB", "r1": "RB"}
    vals = {
        "q1": np.array([UNAVAILABLE, 20.0]),
        "q2": np.array([10.0, 5.0]),
        "r1": np.array([UNAVAILABLE, UNAVAILABLE]),
    }
    out = best_lineup_value(plan, vals, pos)
    assert out.tolist() == [10.0, 20.0]  # week 1: backup QB starts, RB slot empty = 0


def test_flex_cannot_be_filled_by_a_qb_but_superflex_can():
    pos = {"q1": "QB", "q2": "QB", "r1": "RB"}
    vals = {p: np.array([v]) for p, v in {"q1": 20.0, "q2": 18.0, "r1": 5.0}.items()}
    assert best_lineup_value(slot_plan(league({"QB": 1, "FLEX": 1})), vals, pos)[
        0
    ] == pytest.approx(25.0)
    assert best_lineup_value(slot_plan(league({"QB": 1, "SUPERFLEX": 1})), vals, pos)[
        0
    ] == pytest.approx(38.0)


def test_exclude_drops_unscorable_slots():
    plan = slot_plan(load_league_context(), exclude=("K", "DST"))
    assert "K" not in plan.dedicated and "DST" not in plan.dedicated


def test_lineup_can_be_chosen_by_forecast_and_scored_by_outcome():
    plan = slot_plan(league({"QB": 1}))
    pos = {"a": "QB", "b": "QB"}
    forecast = {"a": np.array([20.0]), "b": np.array([10.0])}
    actual = {"a": np.array([5.0]), "b": np.array([30.0])}
    assert (
        best_lineup_value(plan, forecast, pos, scores=actual)[0] == 5.0
    )  # started 'a', 'a' flopped
    assert best_lineup_value(plan, actual, pos)[0] == 30.0  # hindsight picks the boomer
