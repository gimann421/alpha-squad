"""D109 Part 6 -- connect the rounds 1-3 decisions to realized outcomes.

Instrument: `evaluation/draft_oracle.py::audit_draft`, D103's validated pick-level regret,
called with the `rounds` argument it already exposes. No new oracle, no new objective, no new
scoring path. `assert_no_realized_inputs_in_policy()` is called first, exactly as D103's own
runner does, so the rollout policy provably cannot see realized points.

D106's warning does NOT bite here: it applies to comparing arms that draft from DIFFERENT
boards. This measures a single arm (Y1) against the oracle on its own board.
"""

from __future__ import annotations

import json
import os
from statistics import mean, median

import duckdb

from alpha_squad.evaluation.board_vintage import compute_board_vintage
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    assert_no_realized_inputs_in_policy,
    audit_draft,
)
from alpha_squad.league.context import load_league_context

#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SP = SP
SEASONS = (2021, 2022, 2023, 2024, 2025)
SLOTS = tuple(range(1, 11))


def main() -> None:
    assert_no_realized_inputs_in_policy()
    con = duckdb.connect(
        f"{SP}/p6_ro.duckdb", read_only=True
    )  # verified-identical copy; the live DB holds a writer lock
    league = load_league_context()
    print(f"board vintage {compute_board_vintage(con).combined_hash}")

    # `_static_for` is D103's own season-static builder; reuse it rather than rebuilding.
    import sys

    sys.path.insert(0, "scripts/research")
    from d103_pick_regret import _static_for  # noqa: E402

    rows = []
    for season in SEASONS:
        static = _static_for(con, league, season)
        for slot in SLOTS:
            picks = audit_draft(
                con, league, season, slot, static, rounds=(1, 2, 3), objective=SEASON_LONG
            )
            for p in picks:
                a, o = p.alpha, p.oracle
                rows.append(
                    {
                        "season": season,
                        "slot": slot,
                        "round": p.round_no,
                        "regret": p.regret,
                        "alpha_is_oracle": p.alpha_is_oracle,
                        "alpha_pos": a.position if a else None,
                        "oracle_pos": o.position if o else None,
                        "alpha_realized": a.realized_points if a else 0.0,
                        "oracle_realized": o.realized_points if o else 0.0,
                        "alpha_rank_of_oracle": o.alpha_rank if o else None,
                        "slate": len(p.candidates),
                    }
                )
            print(f"  {season} slot {slot} done", flush=True)

    with open(f"{SP}/p6_regret.json", "w") as f:
        json.dump(rows, f, default=str)

    print("\n" + "=" * 90)
    print(f"PICK-LEVEL REGRET, ROUNDS 1-3, target format, season_long  (n={len(rows)})")
    print("=" * 90)
    for rnd in (1, 2, 3):
        sub = [r for r in rows if r["round"] == rnd]
        reg = [r["regret"] for r in sub]
        hit = sum(1 for r in sub if r["alpha_is_oracle"]) / len(sub)
        print(
            f"  round {rnd}: n={len(sub):>3}  mean regret {mean(reg):>7.1f}  "
            f"median {median(reg):>7.1f}  alpha==oracle {hit:>5.1%}"
        )

    print("\n  REGRET BY THE POSITION ALPHA TOOK")
    print(f"  {'pos':<5}{'n':>5}{'meanRegret':>12}{'medRegret':>11}{'==oracle':>10}")
    for pos in ("QB", "RB", "WR", "TE"):
        sub = [r for r in rows if r["alpha_pos"] == pos]
        if not sub:
            continue
        reg = [r["regret"] for r in sub]
        hit = sum(1 for r in sub if r["alpha_is_oracle"]) / len(sub)
        print(f"  {pos:<5}{len(sub):>5}{mean(reg):>12.1f}{median(reg):>11.1f}{hit:>9.1%}")

    print("\n  WHAT POSITION WAS THE ORACLE'S PICK, when Alpha was NOT the oracle?")
    miss = [r for r in rows if not r["alpha_is_oracle"]]
    tally: dict[str, int] = {}
    for r in miss:
        k = f"{r['alpha_pos']}->{r['oracle_pos']}"
        tally[k] = tally.get(k, 0) + 1
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1])[:12]:
        sub = [r for r in miss if f"{r['alpha_pos']}->{r['oracle_pos']}" == k]
        print(f"    {k:<12} n={v:>3}  mean regret {mean(r['regret'] for r in sub):>7.1f}")

    # Did Alpha's own board even RANK the oracle's player near the top?
    ranks = [r["alpha_rank_of_oracle"] for r in miss if r["alpha_rank_of_oracle"] is not None]
    if ranks:
        print(
            f"\n  Alpha's rank of the oracle's player (when it missed): median {median(ranks):.0f}, "
            f"mean {mean(ranks):.1f}, within top 5: {sum(1 for x in ranks if x <= 5) / len(ranks):.0%}"
        )


if __name__ == "__main__":
    main()
