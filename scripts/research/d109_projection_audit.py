"""D109 Part 1 -- forensic audit of Y1 preseason projections, 2021-2025.

Read-only. Uses the application's OWN loader (`load_season_projections`) rather than a
re-query, so what is audited is exactly the board the draft engine reads.
"""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict

from alpha_squad.league.context import load_league_context
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import resolve_market_series
from alpha_squad.storage.db import get_connection

#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SEASONS = [2021, 2022, 2023, 2024, 2025]
SKILL = ("QB", "RB", "WR", "TE")


def main() -> None:
    con = get_connection()
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type

    rows = []  # (season, pid, pos, proj, realized, ecr_rank, pos_ecr_rank, proj_pos_rank)
    for season in SEASONS:
        projections, positions = load_season_projections(con, season)
        market = _preseason_overall_market(con, ecr_type, season)
        realized = dict(
            con.execute(
                "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats WHERE season = ?",
                [season],
            ).fetchall()
        )
        names = dict(
            con.execute(
                "SELECT player_id, display_name FROM players",
            ).fetchall()
        )

        # within-position projection rank and within-position ECR rank
        by_pos = defaultdict(list)
        for pid, proj in projections.items():
            by_pos[positions[pid]].append((proj, pid))
        proj_rank = {}
        for _pos, lst in by_pos.items():
            for i, (_, pid) in enumerate(sorted(lst, key=lambda t: (-t[0], t[1])), start=1):
                proj_rank[pid] = i

        ecr_by_pos = defaultdict(list)
        for pid, (_p, rank) in market.items():
            if pid in positions:
                ecr_by_pos[positions[pid]].append((rank, pid))
        ecr_pos_rank = {}
        for _pos, lst in ecr_by_pos.items():
            for i, (_, pid) in enumerate(sorted(lst, key=lambda t: (t[0], t[1])), start=1):
                ecr_pos_rank[pid] = i

        for pid, proj in projections.items():
            pos = positions[pid]
            rows.append(
                {
                    "season": season,
                    "pid": pid,
                    "name": names.get(pid, pid),
                    "pos": pos,
                    "proj": proj,
                    "realized": realized.get(pid, 0.0),
                    "ecr": market[pid][1] if pid in market else None,
                    "ecr_pos": ecr_pos_rank.get(pid),
                    "proj_pos_rank": proj_rank[pid],
                }
            )

    # Restrict to the DRAFT-RELEVANT population: players with a real preseason ECR rank on the
    # 1-QB board. A projection for a player nobody would draft cannot change a draft decision,
    # and including the long tail of ~600 unranked bodies would dominate every aggregate.
    drafted_pool = [r for r in rows if r["ecr"] is not None and r["pos"] in SKILL]
    print(f"population: {len(rows)} projections, {len(drafted_pool)} with a real preseason ECR")

    out = {"n_all": len(rows), "n_pool": len(drafted_pool)}

    # ---- 1. bias by position -------------------------------------------------------------
    print("\n=== BIAS BY POSITION (ECR-ranked pool, 2021-2025) ===")
    print(f"{'pos':<5}{'n':>5}{'meanProj':>10}{'meanReal':>10}{'bias':>9}{'MAE':>8}{'medBias':>9}")
    pos_tbl = {}
    for pos in SKILL:
        sub = [r for r in drafted_pool if r["pos"] == pos]
        if not sub:
            continue
        errs = [r["proj"] - r["realized"] for r in sub]
        pos_tbl[pos] = {
            "n": len(sub),
            "mean_proj": statistics.mean(r["proj"] for r in sub),
            "mean_real": statistics.mean(r["realized"] for r in sub),
            "bias": statistics.mean(errs),
            "mae": statistics.mean(abs(e) for e in errs),
            "med_bias": statistics.median(errs),
        }
        t = pos_tbl[pos]
        print(
            f"{pos:<5}{t['n']:>5}{t['mean_proj']:>10.1f}{t['mean_real']:>10.1f}"
            f"{t['bias']:>+9.1f}{t['mae']:>8.1f}{t['med_bias']:>+9.1f}"
        )
    out["bias_by_position"] = pos_tbl

    # ---- 2. elite tail: by within-position PROJECTION rank -------------------------------
    print("\n=== ELITE TAIL: bias by within-position PROJECTION rank band ===")
    print("(positive bias = Y1 projected too HIGH; negative = too LOW)")
    bands = [(1, 3), (4, 6), (7, 12), (13, 24), (25, 48)]
    tail_tbl = {}
    for pos in SKILL:
        print(f"\n  {pos}")
        print(
            f"  {'band':<10}{'n':>4}{'meanProj':>10}{'meanReal':>10}{'bias':>9}{'MAE':>8}{'%over':>7}"
        )
        for lo, hi in bands:
            sub = [r for r in drafted_pool if r["pos"] == pos and lo <= r["proj_pos_rank"] <= hi]
            if not sub:
                continue
            errs = [r["proj"] - r["realized"] for r in sub]
            over = sum(1 for e in errs if e > 0) / len(errs) * 100
            tail_tbl[f"{pos}_{lo}-{hi}"] = {
                "n": len(sub),
                "mean_proj": statistics.mean(r["proj"] for r in sub),
                "mean_real": statistics.mean(r["realized"] for r in sub),
                "bias": statistics.mean(errs),
                "mae": statistics.mean(abs(e) for e in errs),
                "pct_over": over,
            }
            t = tail_tbl[f"{pos}_{lo}-{hi}"]
            print(
                f"  {f'{lo}-{hi}':<10}{t['n']:>4}{t['mean_proj']:>10.1f}{t['mean_real']:>10.1f}"
                f"{t['bias']:>+9.1f}{t['mae']:>8.1f}{over:>6.0f}%"
            )
    out["elite_tail_by_proj_rank"] = tail_tbl

    # ---- 3. TAIL COMPRESSION: does the top of the board spread enough? -------------------
    print("\n=== TAIL COMPRESSION: projected vs realized SPREAD at the top ===")
    print("For each (season, pos): spread of the top-5 PROJECTED, vs spread of the top-5 REALIZED")
    comp = {}
    print(f"{'pos':<5}{'projTop1':>10}{'realTop1':>10}{'projP1-P12':>12}{'realP1-P12':>12}{'ratio':>8}")
    for pos in SKILL:
        p_top1, r_top1, p_spread, r_spread = [], [], [], []
        for season in SEASONS:
            sub = sorted(
                (r for r in drafted_pool if r["pos"] == pos and r["season"] == season),
                key=lambda r: -r["proj"],
            )
            if len(sub) < 12:
                continue
            realz = sorted((r["realized"] for r in sub), reverse=True)
            p_top1.append(sub[0]["proj"])
            r_top1.append(realz[0])
            p_spread.append(sub[0]["proj"] - sub[11]["proj"])
            r_spread.append(realz[0] - realz[11])
        if not p_top1:
            continue
        comp[pos] = {
            "proj_top1": statistics.mean(p_top1),
            "real_top1": statistics.mean(r_top1),
            "proj_spread_1_12": statistics.mean(p_spread),
            "real_spread_1_12": statistics.mean(r_spread),
            "spread_ratio": statistics.mean(p_spread) / statistics.mean(r_spread),
        }
        c = comp[pos]
        print(
            f"{pos:<5}{c['proj_top1']:>10.1f}{c['real_top1']:>10.1f}"
            f"{c['proj_spread_1_12']:>12.1f}{c['real_spread_1_12']:>12.1f}{c['spread_ratio']:>8.2f}"
        )
    out["tail_compression"] = comp

    # ---- 4. error by preseason ECR band (what the drafter actually sees) -----------------
    print("\n=== ERROR BY PRESEASON OVERALL ECR BAND (all skill positions) ===")
    ecr_bands = [(1, 12), (13, 24), (25, 36), (37, 60), (61, 100), (101, 200)]
    eb = {}
    print(f"{'ecr':<10}{'n':>5}{'meanProj':>10}{'meanReal':>10}{'bias':>9}{'MAE':>8}")
    for lo, hi in ecr_bands:
        sub = [r for r in drafted_pool if lo <= r["ecr"] <= hi]
        if not sub:
            continue
        errs = [r["proj"] - r["realized"] for r in sub]
        eb[f"{lo}-{hi}"] = {
            "n": len(sub),
            "mean_proj": statistics.mean(r["proj"] for r in sub),
            "mean_real": statistics.mean(r["realized"] for r in sub),
            "bias": statistics.mean(errs),
            "mae": statistics.mean(abs(e) for e in errs),
        }
        t = eb[f"{lo}-{hi}"]
        print(
            f"{f'{lo}-{hi}':<10}{t['n']:>5}{t['mean_proj']:>10.1f}{t['mean_real']:>10.1f}"
            f"{t['bias']:>+9.1f}{t['mae']:>8.1f}"
        )
    out["error_by_ecr_band"] = eb

    # ---- 5. the cross-positional question: bias INSIDE the first three rounds ------------
    print("\n=== THE DECISION-RELEVANT CELL: ECR 1-30 only, by position ===")
    print("These are the players actually in contention in rounds 1-3.")
    print(f"{'pos':<5}{'n':>5}{'meanProj':>10}{'meanReal':>10}{'bias':>9}{'MAE':>8}{'sd(err)':>9}")
    early = {}
    for pos in SKILL:
        sub = [r for r in drafted_pool if r["pos"] == pos and r["ecr"] <= 30]
        if len(sub) < 2:
            continue
        errs = [r["proj"] - r["realized"] for r in sub]
        early[pos] = {
            "n": len(sub),
            "mean_proj": statistics.mean(r["proj"] for r in sub),
            "mean_real": statistics.mean(r["realized"] for r in sub),
            "bias": statistics.mean(errs),
            "mae": statistics.mean(abs(e) for e in errs),
            "sd": statistics.stdev(errs),
        }
        t = early[pos]
        print(
            f"{pos:<5}{t['n']:>5}{t['mean_proj']:>10.1f}{t['mean_real']:>10.1f}"
            f"{t['bias']:>+9.1f}{t['mae']:>8.1f}{t['sd']:>9.1f}"
        )
    out["ecr_top30_by_position"] = early

    # ---- 6. concrete player-level examples ----------------------------------------------
    print("\n=== LARGEST MISSES INSIDE ECR 1-30 (the round 1-3 contention set) ===")
    cands = [r for r in drafted_pool if r["ecr"] <= 30]
    cands.sort(key=lambda r: r["proj"] - r["realized"])
    print("\n  Y1 most UNDER-projected (realized >> projected):")
    print(f"  {'season':<8}{'pos':<5}{'name':<26}{'ecr':>6}{'proj':>8}{'real':>8}{'err':>9}")
    for r in cands[:12]:
        print(
            f"  {r['season']:<8}{r['pos']:<5}{r['name'][:25]:<26}{r['ecr']:>6.1f}"
            f"{r['proj']:>8.1f}{r['realized']:>8.1f}{r['proj'] - r['realized']:>+9.1f}"
        )
    print("\n  Y1 most OVER-projected (projected >> realized):")
    for r in cands[-12:][::-1]:
        print(
            f"  {r['season']:<8}{r['pos']:<5}{r['name'][:25]:<26}{r['ecr']:>6.1f}"
            f"{r['proj']:>8.1f}{r['realized']:>8.1f}{r['proj'] - r['realized']:>+9.1f}"
        )
    out["examples_under"] = [
        {k: r[k] for k in ("season", "pos", "name", "ecr", "proj", "realized")} for r in cands[:12]
    ]
    out["examples_over"] = [
        {k: r[k] for k in ("season", "pos", "name", "ecr", "proj", "realized")}
        for r in cands[-12:][::-1]
    ]

    # ---- 7. THE key cross-positional number for Part 4 ------------------------------------
    print("\n=== Y1 ERROR DISTRIBUTION inside ECR 1-30, pooled (for Part 4 thresholds) ===")
    errs = [r["proj"] - r["realized"] for r in cands]
    absr = sorted(abs(e) for e in errs)
    q = {
        "n": len(errs),
        "mean_abs": statistics.mean(absr),
        "median_abs": statistics.median(absr),
        "p75_abs": absr[int(0.75 * len(absr))],
        "p90_abs": absr[int(0.90 * len(absr))],
        "sd": statistics.stdev(errs),
    }
    print(json.dumps(q, indent=2))
    out["error_distribution_ecr_top30"] = q

    with open(
        f"{SP}/p1_results.json",
        "w",
    ) as f:
        json.dump(out, f, indent=2, default=str)
    print("\nwrote p1_results.json")


if __name__ == "__main__":
    main()
