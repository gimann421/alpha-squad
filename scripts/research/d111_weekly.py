"""D111 secondary metric -- re-score the already-drafted rosters under the WEEKLY objective.

Diagnostic only; `season_long` starter points remain the primary metric (pre-registered).
Reuses `draft_oracle.make_roster_scorer(WEEKLY_NO_FORESIGHT)` unchanged, so this is the same
weekly instrument D103/D106 used -- no new objective, no re-drafting. The rosters are the ones
the pre-registered ablation already produced, so nothing about the draft itself is recomputed.
"""

from __future__ import annotations

import glob
import json
import math
import os
import statistics
import sys

import duckdb

from alpha_squad.evaluation.draft_oracle import WEEKLY_NO_FORESIGHT, make_roster_scorer
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import load_league_context

SEASONS = (2021, 2022, 2023, 2024, 2025)
SP = os.environ.get("D111_OUT", "reports/d111")
T4 = 2.776


def load(league: str, arm: str) -> dict[tuple[int, int], dict]:
    rows: list[dict] = []
    for path in sorted(glob.glob(f"{SP}/d111_{league}_{arm}*.json")):
        with open(path) as f:
            rows.extend(json.load(f))
    return {(r["season"], r["slot"]): r for r in rows}


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/alpha_squad.duckdb"
    league_name = sys.argv[2] if len(sys.argv) > 2 else "target_league"
    con = duckdb.connect(db, read_only=True)
    league = load_league_context(f"src/alpha_squad/config/league_configs/{league_name}.yaml")

    sys.path.insert(0, "scripts/research")
    from d103_pick_regret import _static_for  # noqa: E402

    ctrl, arm = load(league_name, "control"), load(league_name, "risk_off")
    cells = sorted(set(ctrl) & set(arm))
    if not cells:
        sys.exit("no paired cells")

    diffs: list[tuple[int, float]] = []
    for season in SEASONS:
        season_cells = [c for c in cells if c[0] == season]
        if not season_cells:
            continue
        static = _static_for(con, league, season)
        weekly = load_weekly_points(con, season)
        scorer = make_roster_scorer(WEEKLY_NO_FORESIGHT, league, static, weekly)
        for c in season_cells:
            a, _t, _u = scorer(arm[c]["picks"], {})
            b, _t, _u = scorer(ctrl[c]["picks"], {})
            diffs.append((season, a - b))

    by: dict[int, list[float]] = {}
    for s, d in diffs:
        by.setdefault(s, []).append(d)
    means = [statistics.mean(v) for _s, v in sorted(by.items())]
    overall = statistics.mean([d for _s, d in diffs])
    sd = statistics.stdev(means)
    half = T4 * sd / math.sqrt(len(means))
    wins = sum(1 for m in means if m > 0)
    print(f"WEEKLY objective ({league_name}) -- risk_off minus control, {len(diffs)} paired drafts")
    print(f"  mean delta {overall:+.1f}   95% CI over season clusters "
          f"[{overall - half:+.1f}, {overall + half:+.1f}]   {wins}W/{len(means) - wins}L")
    print("  season by season: " + "  ".join(
        f"{s}:{statistics.mean(by[s]):+.0f}" for s in sorted(by)
    ))
    verdict = ("IMPROVES" if overall - half > 0 else
               "WORSENS" if overall + half < 0 else "NO DETECTABLE EFFECT")
    print(f"  -> {verdict}")


if __name__ == "__main__":
    main()
