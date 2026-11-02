"""Roster-level swap backtest: draft legality, decision mechanics, threshold handling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.league.context import load_league_context
from alpha_squad.ros import rosterbench as RB
from alpha_squad.ros.lineup import UNAVAILABLE, slot_plan

pytestmark = pytest.mark.unit


def board(n_qb=20, n_rb=50, n_wr=60, n_te=40) -> pd.DataFrame:
    rows = []
    spec = [("QB", n_qb, 20), ("RB", n_rb, 1), ("WR", n_wr, 1), ("TE", n_te, 8)]
    items = []
    for pos, n, off in spec:
        for i in range(n):
            items.append((pos, i, off + i * 2.2 + (0.1 if pos == "QB" else 0.0)))
    items.sort(key=lambda t: t[2])
    for rank, (pos, i, ecr) in enumerate(items, start=1):
        rows.append(
            dict(
                gsis_id=f"{pos}{i}",
                position=pos,
                overall_ecr=ecr,
                overall_rank=rank,
                player=f"{pos}{i}",
                team=f"T{i % 12}",
            )
        )
    return pd.DataFrame(rows)


def test_lineup_league_roster_arithmetic_and_exclusions():
    lg = RB.lineup_league(load_league_context())
    assert "K" not in lg.lineup and "DEF" not in lg.lineup
    assert sum(lg.lineup.values()) + lg.roster["bench"] == lg.roster["roster_size"] == RB.N_ROUNDS


def test_snake_draft_is_deterministic_legal_and_has_no_duplicates():
    lg = RB.lineup_league(load_league_context())
    b = board()
    r1, r2 = RB.snake_draft(lg, b), RB.snake_draft(lg, b)
    assert r1 == r2
    allp = [p for r in r1.values() for p in r]
    assert len(allp) == len(set(allp)) == 10 * RB.N_ROUNDS
    pos = dict(zip(b.gsis_id, b.position, strict=True))
    for roster in r1.values():
        counts = pd.Series([pos[p] for p in roster]).value_counts()
        assert (
            counts.get("QB", 0) >= 1
            and counts.get("TE", 0) >= 1
            and counts.get("RB", 0) >= 2
            and counts.get("WR", 0) >= 2
        )
        assert (
            counts.get("QB", 0) <= 2
        )  # positional ceiling from the lineup, not a hoard of quarterbacks


def test_draft_refuses_to_produce_an_illegal_roster():
    lg = RB.lineup_league(load_league_context())
    with pytest.raises(ValueError, match="too shallow"):
        RB.snake_draft(lg, board(n_qb=20, n_rb=50, n_wr=60, n_te=12))


def world_for(qb_real: dict[str, float], weeks=6) -> RB.SnapshotWorld:
    b = board(n_qb=6, n_rb=8, n_wr=8, n_te=4)
    ids = list(b.gsis_id)
    pos = dict(zip(b.gsis_id, b.position, strict=True))
    real = {g: np.full(weeks, qb_real.get(g, 8.0)) for g in ids}
    return RB.SnapshotWorld(
        2024,
        8,
        list(range(weeks)),
        pos,
        dict(zip(b.gsis_id, b.overall_rank.astype(float), strict=True)),
        {g: "T" for g in ids},
        real,
        {g: np.ones(weeks, bool) for g in ids},
        {g: 8.0 for g in ids if pos[g] != "QB"},
        {g: g for g in ids},
    )


def test_a_model_that_sees_a_better_qb_trades_and_realized_value_uses_actual_points():
    lg = RB.lineup_league(load_league_context())
    plan = slot_plan(lg)
    w = world_for({"QB0": 25.0, "QB5": 5.0})
    qbs = [g for g in w.positions if w.positions[g] == "QB"]
    nonqb = [g for g in w.positions if w.positions[g] != "QB"]
    # team 0 owns the weak QB5 (plus fillers); team 1 owns QB0
    rosters = {0: ["QB5", *nonqb[:6]], 1: ["QB0", *nonqb[6:12]]}
    rates_good = {q: (25.0 if q == "QB0" else 5.0) for q in qbs}
    rates_blind = dict.fromkeys(qbs, 10.0)
    rows = RB.run_snapshot(
        w, rosters, {"good": rates_good, "blind": rates_blind}, lg, plan, baseline_model="good"
    )
    df = pd.DataFrame(rows)
    good = df[(df.model == "good") & (df.team == 0)].iloc[0]
    assert good.executed and good["get"] == "QB0" and good.pred_delta > 50
    assert good.real_delta == pytest.approx(good.real_if_exec) and good.real_delta > 50
    blind = df[(df.model == "blind") & (df.team == 0)].iloc[0]
    assert (
        (not blind.executed)
        or blind.pred_delta <= 1e-6
        or blind.real_delta == pytest.approx(blind.real_if_exec)
    )


def test_with_threshold_rederives_execution_without_changing_the_candidate():
    res = pd.DataFrame(
        {
            "model": ["m"] * 3,
            "season": 2024,
            "snapshot_week": 6,
            "team": [0, 1, 2],
            "pred_delta": [5.0, 15.0, -2.0],
            "real_if_exec": [3.0, -4.0, 9.0],
            "real_if_exec_hs": [4.0, -3.0, 9.0],
            "oracle_delta": [20.0, 20.0, 20.0],
        }
    )
    r0, r10 = RB.with_threshold(res, 0.0), RB.with_threshold(res, 10.0)
    assert r0["executed"].tolist() == [True, True, False] and r0["real_delta"].tolist() == [
        3.0,
        -4.0,
        0.0,
    ]
    assert r10["executed"].tolist() == [False, True, False] and r10["real_delta"].tolist() == [
        0.0,
        -4.0,
        0.0,
    ]
    m = RB.snapshot_roster_metrics(res, 10.0).iloc[0]
    assert m["trade_rate"] == pytest.approx(1 / 3) and m["hit_rate"] == 0.0


def test_unavailable_sentinel_never_leaks_into_realized_totals():
    lg = RB.lineup_league(load_league_context())
    plan = slot_plan(lg)
    w = world_for({})
    for g in w.real:
        w.real[g][2] = UNAVAILABLE  # everyone idle in one week
    ids = [g for g in w.positions][:14]
    total = RB._total(plan, {g: w.real[g] for g in ids}, w.positions)
    assert 0 <= total < 1e4
