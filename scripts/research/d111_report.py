"""D111 Parts 6-8 -- did removing the risk multiplier change realized draft value?

Pure post-processing of the pre-registered ablation. Arms are paired by (season, slot) against
control, so board, opponent field and every other score term are identical by construction.

Inference unit is the SEASON cluster (n=5, t(4)=2.776), per D88: the detection floor is bound by
independent season clusters and slots provably cannot lower it.
"""

from __future__ import annotations

import glob
import json
import math
import os
import statistics
from collections import Counter

SEASONS = (2021, 2022, 2023, 2024, 2025)
POS = ("QB", "RB", "WR", "TE", "K", "DST")
SP = os.environ.get("D111_OUT", "reports/d111")
T4 = 2.776


def load(league: str, arm: str) -> dict[tuple[int, int], dict]:
    rows: list[dict] = []
    for path in sorted(glob.glob(f"{SP}/d111_{league}_{arm}*.json")):
        with open(path) as f:
            rows.extend(json.load(f))
    return {(r["season"], r["slot"]): r for r in rows}


def season_ci(diffs: list[tuple[int, float]]) -> tuple[float, float, float, str, float]:
    by: dict[int, list[float]] = {}
    for s, d in diffs:
        by.setdefault(s, []).append(d)
    means = [statistics.mean(v) for _s, v in sorted(by.items())]
    overall = statistics.mean([d for _s, d in diffs])
    if len(means) < 2:
        return overall, float("nan"), float("nan"), "", float("nan")
    sd = statistics.stdev(means)
    half = T4 * sd / math.sqrt(len(means))
    wins = sum(1 for m in means if m > 0)
    return overall, overall - half, overall + half, f"{wins}W/{len(means) - wins}L", sd


def report_league(league: str, label: str) -> None:
    ctrl, arm = load(league, "control"), load(league, "risk_off")
    cells = sorted(set(ctrl) & set(arm))
    if not cells:
        print(f"\n[{label}] no paired cells yet")
        return
    print("\n" + "=" * 96)
    print(f"{label}  --  {len(cells)} paired drafts")
    print("=" * 96)

    diffs = [(s, arm[(s, sl)]["starter_points"] - ctrl[(s, sl)]["starter_points"])
             for (s, sl) in cells]
    mean, lo, hi, rec, sd = season_ci(diffs)
    mde = T4 * sd / math.sqrt(len(SEASONS))
    ctrl_mean = statistics.mean(ctrl[c]["starter_points"] for c in cells)
    print("PRIMARY -- whole-draft realized starter points, risk_off minus control")
    print(f"  control mean {ctrl_mean:.1f}   arm mean "
          f"{statistics.mean(arm[c]['starter_points'] for c in cells):.1f}")
    print(f"  mean delta {mean:+.1f}   95% CI over season clusters [{lo:+.1f}, {hi:+.1f}]   {rec}")
    print(f"  sd(season) {sd:.1f}   MDE at 95% {mde:.1f} pts/draft   "
          f"{'POWERED' if mde <= 177 else 'UNDERPOWERED'} for D109's ~177 reference")
    verdict = (
        "IMPROVES (CI excludes zero)" if lo > 0
        else "WORSENS (CI excludes zero)" if hi < 0
        else "NO DETECTABLE EFFECT (CI spans zero)"
    )
    print(f"  -> {verdict}")

    print("\n  season by season")
    by: dict[int, list[float]] = {}
    for s, d in diffs:
        by.setdefault(s, []).append(d)
    print("  " + "".join(f"{s:>10}" for s in SEASONS))
    print("  " + "".join(
        f"{statistics.mean(by[s]):>+10.1f}" if s in by else f"{'-':>10}" for s in SEASONS
    ))

    # ---- Part 7: what changed in the draft ----
    print("\nPART 7 -- what changed")
    tot = chg = tot13 = chg13 = 0
    for c in cells:
        for i, (a, b) in enumerate(zip(arm[c]["picks"], ctrl[c]["picks"], strict=False)):
            tot += 1
            chg += a != b
            if i < 3:
                tot13 += 1
                chg13 += a != b
    print(f"  picks changed: {chg}/{tot} ({chg / tot:.0%})   rounds 1-3: "
          f"{chg13}/{tot13} ({chg13 / tot13:.0%})")
    print(f"  {'arm':<10}" + "".join(f"{p:>7}" for p in POS) + f"{'1stRB':>8}{'modal open':>16}")
    for name, src in (("control", ctrl), ("risk_off", arm)):
        c13: Counter = Counter()
        first_rb, opens = [], Counter()
        for k in cells:
            c13.update(src[k]["pick_positions"][:3])
            opens["-".join(src[k]["pick_positions"][:3])] += 1
            if "RB" in src[k]["pick_positions"]:
                first_rb.append(src[k]["pick_positions"].index("RB") + 1)
        print(f"  {name:<10}" + "".join(f"{c13[p]:>7}" for p in POS)
              + f"{statistics.mean(first_rb) if first_rb else float('nan'):>8.2f}"
              + f"{opens.most_common(1)[0][0]:>16}")

    print("\n  full 16-round roster shape (mean count per position)")
    for name, src in (("control", ctrl), ("risk_off", arm)):
        cnt: Counter = Counter()
        for k in cells:
            cnt.update(src[k]["pick_positions"])
        print(f"  {name:<10}" + "  ".join(f"{p} {cnt[p] / len(cells):.2f}" for p in POS))

    # ---- Part 8: attribution ----
    print("\nPART 8 -- where the value difference comes from")
    print(f"  {'block':<10}{'control':>10}{'risk_off':>10}{'delta':>9}")
    for lbl, lo_i, hi_i in (("R1-3", 0, 3), ("R4-6", 3, 6), ("R7-10", 6, 10), ("R11-16", 10, 16)):
        c = statistics.mean(sum(ctrl[k]["pick_realized"][lo_i:hi_i]) for k in cells)
        a = statistics.mean(sum(arm[k]["pick_realized"][lo_i:hi_i]) for k in cells)
        print(f"  {lbl:<10}{c:>10.1f}{a:>10.1f}{a - c:>+9.1f}")
    print(f"  {'STARTERS':<10}{ctrl_mean:>10.1f}"
          f"{statistics.mean(arm[c]['starter_points'] for c in cells):>10.1f}{mean:>+9.1f}")

    print("\n  first divergence per draft (the one clean like-for-like comparison)")
    rnds, deltas, swaps = [], [], Counter()
    for k in cells:
        a, c = arm[k], ctrl[k]
        for i in range(min(len(a["picks"]), len(c["picks"]))):
            if a["picks"][i] == c["picks"][i]:
                continue
            rnds.append(i + 1)
            deltas.append(a["pick_realized"][i] - c["pick_realized"][i])
            if a["pick_positions"][i] != c["pick_positions"][i]:
                swaps[f"{a['pick_positions'][i]}<-{c['pick_positions'][i]}"] += 1
            break
    if rnds:
        print(f"  {len(rnds)}/{len(cells)} drafts diverge, mean round {statistics.mean(rnds):.2f}, "
              f"delta realized {statistics.mean(deltas):+.1f}")
        print("  " + "  ".join(f"{k}:{v}" for k, v in swaps.most_common(5)))

    print("\n  concentration: is the effect a few drafts?")
    ranked = sorted(((arm[k]["starter_points"] - ctrl[k]["starter_points"], k) for k in cells),
                    key=lambda t: -abs(t[0]))
    top5 = sum(d for d, _ in ranked[:5])
    print(f"  total delta across {len(cells)} drafts: {sum(d for d, _ in ranked):+.0f}")
    print(f"  the 5 largest-magnitude drafts contribute {top5:+.0f} "
          f"({100 * abs(top5) / max(abs(sum(d for d, _ in ranked)), 1e-9):.0f}% of the net)")
    for d, k in ranked[:5]:
        print(f"    {k[0]} slot {k[1]:>2}: {d:+8.0f}   ctrl {ctrl[k]['pick_positions'][:3]} "
              f"-> arm {arm[k]['pick_positions'][:3]}")

    unf = sum(r["n_unfilled_mandatory_slots"] for r in arm.values())
    unf_c = sum(r["n_unfilled_mandatory_slots"] for r in ctrl.values())
    print(f"\n  unfilled mandatory starting slots -- control {unf_c}, risk_off {unf}")


def main() -> None:
    report_league("target_league", "TARGET FORMAT (10-team 1-QB PPR redraft) -- PRIMARY")
    report_league("legacy_2qb_dynasty", "CROSS-FORMAT (10-team 2-QB dynasty, no K/DEF)")


if __name__ == "__main__":
    main()
