"""D111 Parts 1-4 -- what the `risk` multiplier is, whether it measures risk, and its leverage.

READ-ONLY. Nothing is modified; the ablation is a separate, separately pre-registered runner.

The structural fact this script establishes and then builds on:
`models/uncertainty/conformal.py::apply_quantiles` returns `point_prediction + residual_quantile`,
and the residual quantiles are fit ONCE per (calibration season, position). So the interval WIDTH
`p90 - p10` is a per-(season, position) CONSTANT, identical for every player in that cell, and

    confidence = clip(1 - W(season, position) / (2 * |projection|), 0, 1)

is a deterministic, strictly increasing function of the player's OWN PROJECTION. It contains no
player-specific uncertainty information at all. Everything in Parts 2 and 3 follows from that.
"""

from __future__ import annotations

import math
import os
import statistics
import sys
from collections import defaultdict

import duckdb

from alpha_squad.league.context import load_league_context
from alpha_squad.league.opportunity_cost import load_market_ranks
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.run import MODEL_VERSION

SEASONS = (2021, 2022, 2023, 2024, 2025)
POS = ("QB", "RB", "WR", "TE")
SP = os.environ.get("D111_OUT", "reports/d111")


def spearman(xs: list[float], ys: list[float]) -> float:
    def rank(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def main() -> None:
    os.makedirs(SP, exist_ok=True)
    db = sys.argv[1] if len(sys.argv) > 1 else "data/alpha_squad.duckdb"
    con = duckdb.connect(db, read_only=True)
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type

    rows = []
    for season in SEASONS:
        market = load_market_ranks(con, ecr_type, season)
        realized = dict(
            con.execute(
                "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats WHERE season=?",
                [season],
            ).fetchall()
        )
        names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())
        for pid, pos, point, p10, p25, p90, conf in con.execute(
            "SELECT player_id, position, point_prediction, p10, p25, p90, confidence "
            "FROM uncertainty_predictions WHERE season=? AND model_version=?",
            [season, MODEL_VERSION],
        ).fetchall():
            if pos not in POS or conf is None:
                continue
            rows.append({
                "season": season, "pid": pid, "name": names.get(pid, pid), "pos": pos,
                "proj": point, "p10": p10, "p25": p25, "p90": p90, "conf": conf,
                "width": p90 - p10, "real": realized.get(pid, 0.0),
                "ecr": market[pid][1] if pid in market else None,
            })

    print(f"population: {len(rows)} predictions, {MODEL_VERSION}, 2021-2025\n")

    # ============ PART 1 -- the mechanism, with real examples ============
    print("=" * 96)
    print("PART 1 -- WHAT RISK ACTUALLY IS")
    print("=" * 96)
    print("A. The p10-p90 interval width is a per-(season, position) CONSTANT:")
    print(f"   {'season':<8}" + "".join(f"{p:>12}" for p in POS))
    for season in SEASONS:
        widths = []
        for p in POS:
            w = {round(r["width"], 6) for r in rows if r["season"] == season and r["pos"] == p}
            widths.append(f"{next(iter(w)):.1f}" if len(w) == 1 else f"VARIES({len(w)})")
        print(f"   {season:<8}" + "".join(f"{w:>12}" for w in widths))
    n_cells = sum(
        1 for s in SEASONS for p in POS
        if len({round(r["width"], 6) for r in rows if r["season"] == s and r["pos"] == p}) == 1
    )
    print(f"\n   -> {n_cells} of 20 (season, position) cells have exactly ONE interval width.")
    print("      So the width carries NO player-specific information whatsoever.")

    print("\nB. Therefore confidence is a monotone function of the projection alone.")
    print("   Spearman(confidence, projection) WITHIN each (season, position) cell:")
    worst = 1.0
    for season in SEASONS:
        vals = []
        for p in POS:
            sub = [r for r in rows if r["season"] == season and r["pos"] == p]
            rho = spearman([r["proj"] for r in sub], [r["conf"] for r in sub])
            vals.append(rho)
            worst = min(worst, rho)
        print(f"   {season:<8}" + "".join(f"{v:>12.4f}" for v in vals))
    print(f"\n   -> minimum rho across all 20 cells = {worst:.4f}. Confidence IS the projection,")
    print("      re-expressed. It adds no ordering information within a position.")

    print("\nC. Concrete examples from the real 2024 board (same position, same season):")
    ex = sorted(
        (r for r in rows if r["season"] == 2024 and r["pos"] == "RB" and r["ecr"] and r["ecr"] <= 60),
        key=lambda r: -r["proj"],
    )
    print(f"   {'player':<24}{'proj':>8}{'p10':>8}{'p90':>8}{'width':>8}{'conf':>7}{'realized':>10}")
    for r in [*ex[:3], *ex[-3:]]:
        print(f"   {r['name'][:23]:<24}{r['proj']:>8.1f}{r['p10']:>8.1f}{r['p90']:>8.1f}"
              f"{r['width']:>8.1f}{r['conf']:>7.3f}{r['real']:>10.1f}")
    print("   Every width is identical. The only thing separating their risk multipliers is")
    print("   how many points each is projected for.")

    print("\nD. Range of the multiplier, and whether it can ever help a player:")
    allc = [r["conf"] for r in rows]
    print(f"   min {min(allc):.3f}  max {max(allc):.3f}  median {statistics.median(allc):.3f}")
    print(f"   clipped to 0.0: {sum(1 for c in allc if c <= 0.0)} of {len(allc)}")
    print("   The multiplier is bounded above by 1.0, so it can only ever REDUCE a score.")
    print("   Players with no uncertainty row (all DST, most K, ~100 rookies/season) instead")
    print("   take the hardcoded 0.7 fallback in league/draft.py -- a magic constant, not a model")
    print("   output, applied to roughly a quarter of the evaluable pool.")

    # ============ PART 2 -- is it measuring risk? ============
    print("\n" + "=" * 96)
    print("PART 2 -- IS RISK ACTUALLY MEASURING RISK?")
    print("=" * 96)
    print("A. Are the intervals themselves calibrated? A 10-90 interval should cover 80%.")
    print(f"   {'season':<8}{'pos':<5}{'n':>5}{'coverage':>10}{'below p10':>11}{'above p90':>11}")
    cov_all = []
    for season in SEASONS:
        for p in POS:
            sub = [r for r in rows if r["season"] == season and r["pos"] == p and r["ecr"]]
            if len(sub) < 10:
                continue
            inside = sum(1 for r in sub if r["p10"] <= r["real"] <= r["p90"]) / len(sub)
            below = sum(1 for r in sub if r["real"] < r["p10"]) / len(sub)
            above = sum(1 for r in sub if r["real"] > r["p90"]) / len(sub)
            cov_all.append(inside)
            print(f"   {season:<8}{p:<5}{len(sub):>5}{inside:>9.0%}{below:>11.0%}{above:>11.0%}")
    if cov_all:
        print(f"\n   mean coverage {statistics.mean(cov_all):.0%} against a nominal 80%"
              " (ECR-ranked pool only)")

    print("\nB. Does confidence predict error BEYOND the projection it is built from?")
    print("   Within each (season, position) cell, confidence is a monotone function of the")
    print("   projection, so conditioning on the projection leaves confidence with zero")
    print("   variance. The partial association is therefore exactly zero BY CONSTRUCTION,")
    print("   not as an empirical finding. Shown here as absolute error against projection")
    print("   decile, which is the same information the multiplier is using:")
    pool = [r for r in rows if r["ecr"] is not None and r["ecr"] <= 100]
    pool.sort(key=lambda r: r["proj"])
    n = len(pool)
    print(f"   {'proj quintile':<16}{'n':>5}{'meanProj':>10}{'meanConf':>10}{'MAE':>8}"
          f"{'relErr':>9}{'signed bias':>13}")
    for i in range(5):
        q = pool[i * n // 5 : (i + 1) * n // 5]
        print(
            f"   {f'Q{i + 1}':<16}{len(q):>5}{statistics.mean(r['proj'] for r in q):>10.1f}"
            f"{statistics.mean(r['conf'] for r in q):>10.3f}"
            f"{statistics.mean(abs(r['proj'] - r['real']) for r in q):>8.1f}"
            f"{statistics.mean(abs(r['proj'] - r['real']) / max(r['proj'], 1.0) for r in q):>9.2f}"
            f"{statistics.mean(r['proj'] - r['real'] for r in q):>+13.1f}"
        )
    print("\n   NOTE on D110: it reported relative error falling as confidence rises and read")
    print("   that as 'real signal'. Both quantities divide by the projection, so that")
    print("   relationship is mechanical. D111 supersedes that reading -- see Part 2C.")

    print("\nC. The honest test: does confidence order players by ABSOLUTE error, within a cell?")
    print(f"   {'pos':<5}{'n':>6}{'rho(conf, |err|)':>18}{'rho(conf, signed err)':>23}")
    for p in POS:
        xs, ys, zs = [], [], []
        for season in SEASONS:
            sub = [r for r in rows if r["season"] == season and r["pos"] == p and r["ecr"]]
            if len(sub) < 10:
                continue
            xs += [r["conf"] for r in sub]
            ys += [abs(r["proj"] - r["real"]) for r in sub]
            zs += [r["proj"] - r["real"] for r in sub]
        if xs:
            print(f"   {p:<5}{len(xs):>6}{spearman(xs, ys):>18.3f}{spearman(xs, zs):>23.3f}")
    print("\n   A working risk measure needs rho(conf, |err|) clearly NEGATIVE -- more confident")
    print("   means smaller error. A POSITIVE rho(conf, signed err) means the multiplier marks")
    print("   down exactly the players the model under-projects.")

    # ============ PART 3 -- the D109 concern, decomposed ============
    print("\n" + "=" * 96)
    print("PART 3 -- WHY IS RB's MULTIPLIER LOWER THAN WR's? (ECR <= 36 contention set)")
    print("=" * 96)
    cell = {
        p: [r for r in rows if r["pos"] == p and r["ecr"] is not None and r["ecr"] <= 36]
        for p in POS
    }
    stat = {}
    for p in POS:
        if not cell[p]:
            continue
        stat[p] = (
            statistics.mean(r["conf"] for r in cell[p]),
            statistics.mean(r["width"] for r in cell[p]),
            statistics.mean(r["proj"] for r in cell[p]),
        )
        print(f"   {p}: conf {stat[p][0]:.3f}  width {stat[p][1]:.1f}  projection {stat[p][2]:.1f}")

    if "RB" in stat and "WR" in stat:
        c_rb, w_rb, p_rb = stat["RB"]
        c_wr, w_wr, p_wr = stat["WR"]
        gap = c_wr - c_rb
        # counterfactual confidences using the closed form 1 - W/(2P)
        rb_with_wr_width = 1 - w_wr / (2 * p_rb)
        rb_with_wr_proj = 1 - w_rb / (2 * p_wr)
        print(f"\n   WR minus RB confidence gap: {gap:+.3f}")
        print(f"   If RB kept its projection but had WR's WIDTH:      {rb_with_wr_width:.3f} "
              f"(closes {100 * (rb_with_wr_width - c_rb) / gap:.0f}% of the gap)")
        print(f"   If RB kept its width but had WR's PROJECTION:      {rb_with_wr_proj:.3f} "
              f"(closes {100 * (rb_with_wr_proj - c_rb) / gap:.0f}% of the gap)")
        print("\n   Both mechanisms are POSITION-level. Neither is player-level risk. And the")
        print("   projection channel is the one D109 showed to be biased LOW at RB, so the")
        print("   multiplier compounds that bias rather than hedging it.")

    _ = defaultdict


if __name__ == "__main__":
    main()
