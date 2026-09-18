"""D111 Part 4 -- how much does the `risk` multiplier actually move draft decisions?

Instrument: `evaluation/opening_audit.py::audit_opening`, whose `decompose_candidate` ASSERTS that
the reassembled term-by-term score equals the production score to 1e-6. The counterfactual here is
arithmetic on that verified decomposition -- score with `risk_mult` replaced by 1.0, holding the
pick STATE fixed -- so it isolates risk's leverage at a state production actually reached, which is
a different (and cleaner) question than the full ablation, where trajectories diverge.

    uv run python scripts/research/d111_risk_leverage.py <db> <season>
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter

import duckdb

from alpha_squad.evaluation.opening_audit import audit_opening
from alpha_squad.league.context import load_league_context
from alpha_squad.market.series import resolve_market_series

SP = os.environ.get("D111_OUT", "reports/d111")
AUDIT_ROUNDS = 7  # covers overall picks 1, 20, 21, 40, 41, 60, 61 at draft slot 1
TOP_N = 80


def no_risk_score(d: dict) -> float:
    """The production score with `risk_mult` set to 1.0 and nothing else changed."""
    return (d["value_base"] + d["opportunity_cost"]) * d["fit_multiplier"] * d[
        "survival_multiplier"
    ] * d["cap_multiplier"]


def main() -> None:
    os.makedirs(SP, exist_ok=True)
    db, season = sys.argv[1], int(sys.argv[2])
    con = duckdb.connect(db, read_only=True)
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type
    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())

    out = []
    for slot in range(1, league.teams + 1):
        res = audit_opening(
            con, league, season, slot, world="default",
            audit_rounds=AUDIT_ROUNDS, top_n=TOP_N, ecr_type=ecr_type,
        )
        for ap in res.audited_picks:
            cands = [
                {
                    "pid": c.player_id, "name": names.get(c.player_id, c.player_id),
                    "pos": c.position, "proj": c.projection, "risk": c.risk_multiplier,
                    "score": c.score, "no_risk": no_risk_score(c.__dict__),
                }
                for c in ap.candidates
            ]
            prod = min(cands, key=lambda c: (-c["score"], c["pid"]))
            abl = min(cands, key=lambda c: (-c["no_risk"], c["pid"]))
            out.append({
                "season": season, "slot": slot, "round": ap.round_no,
                "overall_pick": ap.overall_pick,
                "prod_pid": prod["pid"], "prod_name": prod["name"], "prod_pos": prod["pos"],
                "prod_risk": prod["risk"], "prod_proj": prod["proj"],
                "abl_pid": abl["pid"], "abl_name": abl["name"], "abl_pos": abl["pos"],
                "abl_risk": abl["risk"], "abl_proj": abl["proj"],
                "flipped": prod["pid"] != abl["pid"],
                "risk_by_pos": {
                    p: statistics.mean([c["risk"] for c in cands if c["pos"] == p])
                    for p in {c["pos"] for c in cands}
                },
                "n_zero_risk": sum(1 for c in cands if c["risk"] <= 1e-9),
                "n_cands": len(cands),
            })
        print(f"  {season} slot {slot} done", flush=True)

    with open(f"{SP}/d111_leverage_{season}.json", "w") as f:
        json.dump(out, f)
    flips = sum(1 for r in out if r["flipped"])
    print(f"{season}: {flips}/{len(out)} audited picks flip when risk is removed "
          f"({Counter((r['prod_pos'], r['abl_pos']) for r in out if r['flipped'])})",
          flush=True)


if __name__ == "__main__":
    main()
