"""D110 -- analysis of the pre-registered magnitude grid. Pure post-processing.

Every arm is compared with `control` on the SAME (season, slot), so the trials are paired and
the opponent field and board are identical by construction.

Inference unit is the SEASON, not the draft. D88 established that the detection floor is bound
by the number of independent season clusters and that slots provably cannot lower it, so a
50-draft interval would be anticonservative. Both are printed; the season-cluster one decides.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import Counter

SP = os.environ.get("D110_OUT", "reports/d110")
SEASONS = (2021, 2022, 2023, 2024, 2025)
VALUE_ARMS = (
    "control", "rb_080", "rb_090", "rb_110", "rb_120", "rb_140",
    "qb_090", "qb_110", "wr_090", "gap_rb120_wr090",
)
DECISION_ONLY = ("rb_095", "rb_105", "rb_115", "rb_130")
#: t(4), two-sided 95%, for 5 independent season clusters.
T4 = 2.776


def load(arm: str) -> dict[tuple[int, int], dict] | None:
    path = f"{SP}/d110_{arm}.json"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return {(r["season"], r["slot"]): r for r in json.load(f)}


def paired(arm_rows: dict, ctrl_rows: dict) -> list[tuple[int, int, float]]:
    """(season, slot, arm_starters - control_starters) over cells present in BOTH."""
    return [
        (s, sl, arm_rows[(s, sl)]["starter_points"] - ctrl_rows[(s, sl)]["starter_points"])
        for (s, sl) in sorted(arm_rows)
        if (s, sl) in ctrl_rows
    ]


def season_ci(diffs: list[tuple[int, int, float]]) -> tuple[float, float, float, str]:
    """Mean, and a t interval over SEASON means (the independent cluster)."""
    by_season: dict[int, list[float]] = {}
    for s, _sl, d in diffs:
        by_season.setdefault(s, []).append(d)
    means = [statistics.mean(v) for _s, v in sorted(by_season.items())]
    overall = statistics.mean([d for _s, _sl, d in diffs])
    if len(means) < 2:
        return overall, float("nan"), float("nan"), ""
    half = T4 * statistics.stdev(means) / math.sqrt(len(means))
    wins = sum(1 for m in means if m > 0)
    return overall, overall - half, overall + half, f"{wins}W/{len(means) - wins}L"


def first_round_of(positions: list[str], pos: str) -> int | None:
    return positions.index(pos) + 1 if pos in positions else None


def main() -> None:
    ctrl = load("control")
    if ctrl is None:
        sys.exit("control arm missing")

    arms = [a for a in (*VALUE_ARMS, *DECISION_ONLY) if load(a) is not None]
    print(f"arms present: {', '.join(arms)}")
    vint = {r["board_vintage"] for r in ctrl.values()}
    print(f"board vintage: {vint.pop()[:16]}...  control cells: {len(ctrl)}\n")

    # ================= PART 1 -- DECISION SENSITIVITY =================
    print("=" * 100)
    print("PART 1 -- DECISION SENSITIVITY (paired vs control on the same season+slot)")
    print("=" * 100)
    print(f"{'arm':<18}{'cells':>6}{'%picks chg':>12}{'%R1-3 chg':>11}"
          f"{'R1-3 QB/RB/WR/TE':>20}{'1stRB':>8}{'modal open':>14}")
    for arm in arms:
        rows = load(arm)
        cells = [(s, sl) for (s, sl) in sorted(rows) if (s, sl) in ctrl]
        chg = chg13 = tot = tot13 = 0
        comp: Counter = Counter()
        first_rb: list[int] = []
        opens: Counter = Counter()
        for key in cells:
            a, c = rows[key], ctrl[key]
            for i, (pa, pc) in enumerate(zip(a["picks"], c["picks"], strict=False)):
                tot += 1
                chg += pa != pc
                if i < 3:
                    tot13 += 1
                    chg13 += pa != pc
            comp.update(a["pick_positions"][:3])
            opens["-".join(a["pick_positions"][:3])] += 1
            r = first_round_of(a["pick_positions"], "RB")
            if r:
                first_rb.append(r)
        mix = f"{comp['QB']}/{comp['RB']}/{comp['WR']}/{comp['TE']}"
        print(
            f"{arm:<18}{len(cells):>6}{100 * chg / max(tot, 1):>11.0f}%"
            f"{100 * chg13 / max(tot13, 1):>10.0f}%{mix:>20}"
            f"{statistics.mean(first_rb) if first_rb else float('nan'):>8.2f}"
            f"{opens.most_common(1)[0][0]:>14}"
        )

    # The picks the brief names explicitly are exactly draft slot 1's rounds 1-7.
    print("\n  SLOT 1 -- overall picks #1, #20, #21, #40, #41, #60, #61 (position taken,")
    print("  pooled over the 5 seasons; 'WR4 RB1' means 4 seasons WR, 1 RB)")
    labels = [1, 20, 21, 40, 41, 60, 61]
    print(f"  {'arm':<18}" + "".join(f"{'#' + str(p):>14}" for p in labels))
    for arm in arms:
        rows = load(arm)
        cols = []
        for rnd in range(1, 8):
            c = Counter(
                rows[(s, 1)]["pick_positions"][rnd - 1] for s in SEASONS if (s, 1) in rows
            )
            cols.append(" ".join(f"{p}{n}" for p, n in c.most_common()))
        print(f"  {arm:<18}" + "".join(f"{x:>14}" for x in cols))

    # ================= PART 2 -- THRESHOLDS =================
    print("\n" + "=" * 100)
    print("PART 2 -- THRESHOLDS (RB family; where does each behaviour move?)")
    print("=" * 100)
    rb_ladder = [
        ("rb_080", 0.80), ("rb_090", 0.90), ("rb_095", 0.95), ("control", 1.00),
        ("rb_105", 1.05), ("rb_110", 1.10), ("rb_115", 1.15), ("rb_120", 1.20),
        ("rb_130", 1.30), ("rb_140", 1.40),
    ]
    print(f"{'m_RB':>6}{'cells':>7}{'R1 RB%':>9}{'R1-3 RB%':>11}{'1st RB rnd':>12}"
          f"{'%R1-3 chg':>11}{'modal opening':>16}")
    for arm, m in rb_ladder:
        rows = load(arm)
        if rows is None:
            continue
        cells = [k for k in sorted(rows) if k in ctrl]
        r1 = sum(1 for k in cells if rows[k]["pick_positions"][0] == "RB")
        r13 = sum(rows[k]["pick_positions"][:3].count("RB") for k in cells)
        fr = [first_round_of(rows[k]["pick_positions"], "RB") for k in cells]
        fr = [x for x in fr if x]
        chg = sum(
            1 for k in cells for i in range(3) if rows[k]["picks"][i] != ctrl[k]["picks"][i]
        )
        opens = Counter("-".join(rows[k]["pick_positions"][:3]) for k in cells)
        print(
            f"{m:>6.2f}{len(cells):>7}{100 * r1 / len(cells):>8.0f}%"
            f"{100 * r13 / (3 * len(cells)):>10.0f}%"
            f"{statistics.mean(fr) if fr else float('nan'):>12.2f}"
            f"{100 * chg / (3 * len(cells)):>10.0f}%{opens.most_common(1)[0][0]:>16}"
        )

    # ================= PART 3 -- REALIZED VALUE =================
    print("\n" + "=" * 100)
    print("PART 3 -- REALIZED DRAFT VALUE vs CONTROL (primary: absolute starter points)")
    print("=" * 100)
    print("Inference unit is the SEASON cluster (n=5); the per-draft sd is shown only to make")
    print("the anticonservatism of a 50-draft interval visible, and decides nothing.")
    print(f"{'arm':<18}{'n':>4}{'mean d':>9}{'95% CI (season)':>22}{'seasons':>9}"
          f"{'sd(draft)':>11}{'sd(season)':>12}")
    value_rows: dict[str, tuple[float, float, float, float]] = {}
    for arm in arms:
        if arm == "control" or arm in DECISION_ONLY:
            continue
        rows = load(arm)
        d = paired(rows, ctrl)
        if not d:
            continue
        mean, lo, hi, rec = season_ci(d)
        by_season: dict[int, list[float]] = {}
        for s, _sl, x in d:
            by_season.setdefault(s, []).append(x)
        sd_season = statistics.stdev([statistics.mean(v) for v in by_season.values()])
        value_rows[arm] = (mean, lo, hi, sd_season)
        print(
            f"{arm:<18}{len(d):>4}{mean:>+9.1f}{f'[{lo:+.1f}, {hi:+.1f}]':>22}{rec:>9}"
            f"{statistics.stdev([x for _s, _sl, x in d]):>11.1f}{sd_season:>12.1f}"
        )

    print("\n  SEASON-BY-SEASON mean paired difference vs control")
    print(f"  {'arm':<18}" + "".join(f"{s:>10}" for s in SEASONS))
    for arm in value_rows:
        rows = load(arm)
        d = paired(rows, ctrl)
        by_season = {}
        for s, _sl, x in d:
            by_season.setdefault(s, []).append(x)
        print(f"  {arm:<18}" + "".join(
            f"{statistics.mean(by_season[s]):>+10.1f}" if s in by_season else f"{'-':>10}"
            for s in SEASONS
        ))

    # ================= PART 4 -- EARLY vs LATE =================
    print("\n" + "=" * 100)
    print("PART 4 -- WHERE THE POINTS COME FROM (diagnostic only; starter points stay primary)")
    print("=" * 100)
    print("Realized points of the players DRAFTED in each round block, differenced vs control.")
    print(f"{'arm':<18}{'R1-3':>10}{'R4-6':>10}{'R7-16':>10}{'all picks':>12}{'starters':>11}")
    for arm in value_rows:
        rows = load(arm)
        cells = [k for k in sorted(rows) if k in ctrl]

        def blk(src: dict, lo: int, hi: int, _cells: list = cells) -> float:
            return statistics.mean(sum(src[k]["pick_realized"][lo:hi]) for k in _cells)

        print(
            f"{arm:<18}{blk(rows, 0, 3) - blk(ctrl, 0, 3):>+10.1f}"
            f"{blk(rows, 3, 6) - blk(ctrl, 3, 6):>+10.1f}"
            f"{blk(rows, 6, 16) - blk(ctrl, 6, 16):>+10.1f}"
            f"{blk(rows, 0, 16) - blk(ctrl, 0, 16):>+12.1f}"
            f"{value_rows[arm][0]:>+11.1f}"
        )

    # ================= PART 5 -- ATTRIBUTION =================
    print("\n" + "=" * 100)
    print("PART 5 -- ATTRIBUTION: is a changed pick a different POSITION or a different PLAYER?")
    print("=" * 100)
    print(f"{'arm':<18}{'changed':>9}{'diff pos':>10}{'same pos':>10}"
          f"{'d real|diffpos':>16}{'d real|samepos':>16}")
    for arm in value_rows:
        rows = load(arm)
        cells = [k for k in sorted(rows) if k in ctrl]
        dp = sp = 0
        dp_val: list[float] = []
        sp_val: list[float] = []
        for k in cells:
            a, c = rows[k], ctrl[k]
            for i in range(min(len(a["picks"]), len(c["picks"]))):
                if a["picks"][i] == c["picks"][i]:
                    continue
                delta = a["pick_realized"][i] - c["pick_realized"][i]
                if a["pick_positions"][i] != c["pick_positions"][i]:
                    dp += 1
                    dp_val.append(delta)
                else:
                    sp += 1
                    sp_val.append(delta)
        print(
            f"{arm:<18}{dp + sp:>9}{dp:>10}{sp:>10}"
            f"{statistics.mean(dp_val) if dp_val else float('nan'):>+16.1f}"
            f"{statistics.mean(sp_val) if sp_val else float('nan'):>+16.1f}"
        )
    print("\n  'd real' is the realized-point difference of the swapped player at that pick.")
    print("  A large per-pick delta that does NOT reach starter points means the change landed")
    print("  on a player who never entered the starting lineup.")

    # ================= PART 6 -- POWER =================
    print("\n" + "=" * 100)
    print("PART 6 -- POWER / DETECTION CHECK")
    print("=" * 100)
    sds = [v[3] for v in value_rows.values()]
    if sds:
        med_sd = statistics.median(sds)
        mde = T4 * med_sd / math.sqrt(len(SEASONS))
        print(f"  median sd of the SEASON-level paired difference: {med_sd:.1f}")
        print(f"  minimum detectable effect, t(4) 95%, n=5 seasons:  {mde:.1f} points/draft")
        print("  D109's expected wrong-position component:          ~177 points/draft")
        print(f"  season clusters needed to detect ~177:             "
              f"{math.ceil((T4 * med_sd / 177) ** 2)}")
        print()
        if mde > 177:
            print("  -> CANNOT reliably distinguish 'no effect' from an effect the size D109")
            print("     suggested. Any null here is UNDERPOWERED, not evidence that magnitude")
            print("     does not matter.")
        else:
            print("  -> CAN detect an effect of roughly the expected size, so a null is")
            print("     informative about effects at or above that magnitude.")

    print("\n  Unfilled mandatory starting slots (a forfeited slot must never be silent):")
    any_unfilled = False
    for arm in arms:
        rows = load(arm)
        n = sum(r["n_unfilled_mandatory_slots"] for r in rows.values())
        if n:
            any_unfilled = True
            print(f"    {arm}: {n}")
    if not any_unfilled:
        print("    none -- every arm filled every mandatory starting slot in every draft")


if __name__ == "__main__":
    main()
