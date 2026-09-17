"""D110 secondary diagnostic -- what is the `risk` multiplier, and does it penalise RB?

READ-ONLY. Nothing is ablated, modified, or fed back into the main experiment; D110's arms hold
`confidence` frozen precisely so that risk stays a control there.

`league/draft.py` multiplies every candidate's value base by `risk = confidence`, and
`models/uncertainty/conformal.py::confidence_from_interval_width` defines

    confidence = clip(1 - (p90 - p10) / (2 * |point_prediction|), 0, 1)

so it is a RELATIVE interval width -- the point prediction is in the denominator. Two things
follow that are worth measuring rather than asserting:

  (a) a position whose projections are systematically SMALLER earns lower confidence for the
      same absolute uncertainty, which would make the D109 RB under-projection partly
      self-reinforcing; and
  (b) the quantity is documented as "a simple heuristic (not a probability) ... deliberately
      not claimed as calibrated on its own", yet it is used as a direct multiplicative factor
      on value.

This script asks whether confidence tracks anything real: do high-confidence players actually
turn out to be more accurately projected?
"""

from __future__ import annotations

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


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/alpha_squad.duckdb"
    con = duckdb.connect(db, read_only=True)
    league = load_league_context()
    ecr_type = resolve_market_series(league).ecr_type

    rows = []
    for season in SEASONS:
        market = load_market_ranks(con, ecr_type, season)
        realized = dict(
            con.execute(
                "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
                "WHERE season = ?",
                [season],
            ).fetchall()
        )
        for pid, pos, point, p10, p90, conf in con.execute(
            "SELECT player_id, position, point_prediction, p10, p90, confidence "
            "FROM uncertainty_predictions WHERE season = ? AND model_version = ?",
            [season, MODEL_VERSION],
        ).fetchall():
            if pos not in POS or conf is None or point is None:
                continue
            rows.append({
                "season": season, "pid": pid, "pos": pos, "proj": point,
                "width": (p90 - p10) if (p90 is not None and p10 is not None) else None,
                "conf": conf,
                "real": realized.get(pid, 0.0),
                "ecr": market[pid][1] if pid in market else None,
            })

    print(f"n = {len(rows)} uncertainty predictions, {MODEL_VERSION}, 2021-2025\n")

    # ---- 1. is confidence lower at RB, and is it the numerator or the denominator? --------
    print("=== 1. CONFIDENCE BY POSITION -- numerator (absolute width) vs denominator (proj) ===")
    print(f"{'pos':<5}{'n':>6}{'meanConf':>10}{'meanWidth':>11}{'meanProj':>10}{'width/proj':>12}")
    for pos in POS:
        sub = [r for r in rows if r["pos"] == pos and r["width"] is not None]
        if not sub:
            continue
        w = statistics.mean(r["width"] for r in sub)
        p = statistics.mean(r["proj"] for r in sub)
        print(
            f"{pos:<5}{len(sub):>6}{statistics.mean(r['conf'] for r in sub):>10.3f}"
            f"{w:>11.1f}{p:>10.1f}{w / max(p, 1.0):>12.2f}"
        )
    print("\n  If absolute widths are SIMILAR across positions but mean projections differ,")
    print("  the confidence gap is produced by the denominator, not by real uncertainty.")

    # ---- 2. confidence among the players actually in early contention --------------------
    print("\n=== 2. CONFIDENCE INSIDE THE ROUNDS 1-3 CONTENTION SET (ECR <= 36) ===")
    print(f"{'pos':<5}{'n':>5}{'meanConf':>10}{'meanWidth':>11}{'meanProj':>10}")
    for pos in POS:
        sub = [r for r in rows if r["pos"] == pos and r["ecr"] is not None and r["ecr"] <= 36
               and r["width"] is not None]
        if len(sub) < 3:
            continue
        print(
            f"{pos:<5}{len(sub):>5}{statistics.mean(r['conf'] for r in sub):>10.3f}"
            f"{statistics.mean(r['width'] for r in sub):>11.1f}"
            f"{statistics.mean(r['proj'] for r in sub):>10.1f}"
        )

    # ---- 3. does confidence predict accuracy at all? -------------------------------------
    print("\n=== 3. DOES CONFIDENCE TRACK REALIZED ACCURACY? (ECR<=100, the draftable pool) ===")
    pool = [r for r in rows if r["ecr"] is not None and r["ecr"] <= 100]
    pool.sort(key=lambda r: r["conf"])
    n = len(pool)
    print(f"{'conf quintile':<16}{'n':>5}{'meanConf':>10}{'MAE':>9}{'relErr':>9}{'bias':>9}")
    for i in range(5):
        q = pool[i * n // 5 : (i + 1) * n // 5]
        mae = statistics.mean(abs(r["proj"] - r["real"]) for r in q)
        rel = statistics.mean(abs(r["proj"] - r["real"]) / max(r["proj"], 1.0) for r in q)
        bias = statistics.mean(r["proj"] - r["real"] for r in q)
        print(
            f"{f'Q{i + 1}':<16}{len(q):>5}{statistics.mean(r['conf'] for r in q):>10.3f}"
            f"{mae:>9.1f}{rel:>9.2f}{bias:>+9.1f}"
        )
    print("\n  A risk multiplier is only defensible if higher confidence means lower RELATIVE")
    print("  error. Absolute MAE rising with confidence is expected (bigger players, bigger")
    print("  errors) and is NOT evidence the heuristic works.")

    # ---- 4. within-position, does it separate hits from misses? --------------------------
    print("\n=== 4. WITHIN POSITION (ECR<=100): confidence vs relative error ===")
    print(f"{'pos':<5}{'loConf relErr':>15}{'hiConf relErr':>15}{'loConf bias':>13}{'hiConf bias':>13}")
    for pos in POS:
        sub = sorted((r for r in pool if r["pos"] == pos), key=lambda r: r["conf"])
        if len(sub) < 20:
            continue
        half = len(sub) // 2
        lo, hi = sub[:half], sub[half:]
        f = lambda g: statistics.mean(abs(r["proj"] - r["real"]) / max(r["proj"], 1.0) for r in g)  # noqa: E731
        b = lambda g: statistics.mean(r["proj"] - r["real"] for r in g)  # noqa: E731
        print(f"{pos:<5}{f(lo):>15.2f}{f(hi):>15.2f}{b(lo):>+13.1f}{b(hi):>+13.1f}")

    # ---- 5. the circularity, quantified --------------------------------------------------
    print("\n=== 5. THE CIRCULARITY, QUANTIFIED ===")
    print("If a position's projections were scaled by m with its ABSOLUTE interval unchanged,")
    print("confidence would move as conf' = 1 - (1 - conf)/m -- so correcting an")
    print("under-projection ALSO raises that position's risk multiplier.")
    print(f"{'pos':<5}{'conf @m=1.00':>14}{'@m=1.10':>10}{'@m=1.20':>10}{'@m=1.40':>10}{'score x @1.20':>15}")
    for pos in POS:
        sub = [r for r in rows if r["pos"] == pos and r["ecr"] is not None and r["ecr"] <= 36]
        if len(sub) < 3:
            continue
        c = statistics.mean(r["conf"] for r in sub)
        vals = [1.0 - (1.0 - c) / m for m in (1.0, 1.1, 1.2, 1.4)]
        print(
            f"{pos:<5}{vals[0]:>14.3f}{vals[1]:>10.3f}{vals[2]:>10.3f}{vals[3]:>10.3f}"
            f"{vals[2] / vals[0]:>15.3f}"
        )
    print("\n  D110's arms hold confidence FROZEN, which isolates the magnitude channel but")
    print("  therefore UNDERSTATES what a real recalibration would do, by the last column.")

    # ---- 6. how often is risk the deciding term? ----------------------------------------
    print("\n=== 6. SPREAD OF THE RISK MULTIPLIER WITHIN A POSITION (ECR<=36) ===")
    print(f"{'pos':<5}{'min':>8}{'p25':>8}{'median':>8}{'p75':>8}{'max':>8}{'max/min':>9}")
    for pos in POS:
        c = sorted(r["conf"] for r in rows
                   if r["pos"] == pos and r["ecr"] is not None and r["ecr"] <= 36)
        if len(c) < 4:
            continue
        print(
            f"{pos:<5}{c[0]:>8.3f}{c[len(c) // 4]:>8.3f}{statistics.median(c):>8.3f}"
            f"{c[3 * len(c) // 4]:>8.3f}{c[-1]:>8.3f}{c[-1] / max(c[0], 1e-9):>9.2f}"
        )

    _ = defaultdict, os


if __name__ == "__main__":
    main()
