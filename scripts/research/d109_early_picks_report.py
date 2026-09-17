"""D109 Parts 2, 3, 5 -- what Alpha does in rounds 1-3, why, and what it builds.

Pure post-processing of `p2_picks.json`, which was produced by the production path with a
verified score decomposition. Nothing here recomputes a score.
"""

from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict


def _load(path: str):
    with open(path) as f:
        return json.load(f)


def _dump(obj, path: str) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, default=str)


#: Where this phase's intermediate artifacts live. Override with D109_OUT.
SP = os.environ.get("D109_OUT", "reports/d109")
os.makedirs(SP, exist_ok=True)


SP = SP
POS = ("QB", "RB", "WR", "TE", "K", "DST")


def bar(n: int, total: int, width: int = 24) -> str:
    return "#" * round(width * n / total) if total else ""


def main() -> None:
    data = _load(f"{SP}/p2_picks.json")
    picks, rosters = data["picks"], data["rosters"]

    # ============================ PART 2 ============================
    print("=" * 94)
    print("PART 2 -- WHAT ALPHA DOES AT PICKS 1-30   (5 seasons x 10 slots = 50 drafts)")
    print("=" * 94)

    for rnd in (1, 2, 3):
        sub = [r for r in picks if r["round"] == rnd]
        c = Counter(r["pick_position"] for r in sub)
        print(f"\nROUND {rnd}  (n={len(sub)})")
        for p in POS:
            if c[p]:
                print(f"  {p:<4}{c[p]:>4} ({c[p] / len(sub):>5.0%})  {bar(c[p], len(sub))}")

    print("\nBY SEASON -- round 1 / round 2 / round 3 position mix")
    for season in sorted({r["season"] for r in picks}):
        line = []
        for rnd in (1, 2, 3):
            c = Counter(r["pick_position"] for r in picks if r["season"] == season and r["round"] == rnd)
            line.append("+".join(f"{p}{c[p]}" for p in POS if c[p]))
        print(f"  {season}: R1 {line[0]:<16} R2 {line[1]:<16} R3 {line[2]}")

    print("\nOPENING SEQUENCES (first three picks)")
    seqs = Counter("-".join(r["opening3"]) for r in rosters)
    for s, n in seqs.most_common():
        print(f"  {s:<14}{n:>4} ({n / len(rosters):>5.0%})  {bar(n, len(rosters))}")

    print("\nPOSITION BY OVERALL PICK NUMBER (pooled over 5 seasons; 5 observations each)")
    print(f"  {'pick':<6}{'positions taken':<28}{'modal'}")
    for op in range(1, 31):
        sub = [r for r in picks if r["overall_pick"] == op]
        if not sub:
            continue
        c = Counter(r["pick_position"] for r in sub)
        print(f"  {op:<6}{'+'.join(f'{p}{c[p]}' for p in POS if c[p]):<28}{c.most_common(1)[0][0]}")

    # ============================ PART 3 ============================
    print("\n" + "=" * 94)
    print("PART 3 -- WHY. Mean score components of the CHOSEN player, by round and position")
    print("=" * 94)
    print("score = (msv + daVORP + oppCost) x fit x risk x survivalMult x cap")
    for rnd in (1, 2, 3):
        print(f"\nROUND {rnd}")
        print(f"  {'pos':<5}{'n':>4}{'proj':>8}{'msv':>8}{'daVORP':>9}{'repl':>8}"
              f"{'oppCost':>9}{'fit':>6}{'risk':>6}{'surv':>6}{'score':>9}")
        for p in POS:
            sub = [r for r in picks if r["round"] == rnd and r["pick_position"] == p]
            if not sub:
                continue

            def g(k: str, _sub=sub) -> float:
                return statistics.mean(r["chosen"][k] for r in _sub)

            print(
                f"  {p:<5}{len(sub):>4}{g('projection'):>8.1f}{g('msv'):>8.1f}{g('da_vorp'):>9.1f}"
                f"{g('replacement_level'):>8.1f}{g('opportunity_cost'):>9.1f}"
                f"{g('fit_multiplier'):>6.2f}{g('risk_multiplier'):>6.2f}"
                f"{g('survival_multiplier'):>6.2f}{g('score'):>9.1f}"
            )

    print("\nTHE DOUBLE COUNT: is msv == the player's own projection? (empty-slot regime)")
    for rnd in (1, 2, 3):
        sub = [r for r in picks if r["round"] == rnd]
        eq = sum(1 for r in sub if abs(r["chosen"]["msv"] - r["chosen"]["projection"]) < 1e-6)
        print(f"  round {rnd}: msv == projection in {eq}/{len(sub)} chosen picks "
              f"({eq / len(sub):.0%}) -> value base = 2*proj - replacement")

    print("\nWHAT SEPARATES THE CHOSEN PLAYER FROM THE BEST ALTERNATIVE AT EACH OTHER POSITION")
    print("Mean term-by-term difference (chosen minus that position's best), round 1 only:")
    r1 = [r for r in picks if r["round"] == 1]
    print(f"  {'vs':<5}{'n':>4}{'dProj':>9}{'dMSV':>9}{'dVORP':>9}{'dOppCost':>10}"
          f"{'dFit':>7}{'dRisk':>7}{'dSurv':>7}{'dScore':>10}")
    for p in POS:
        rows = [r for r in r1 if p in r["best_by_position"] and r["pick_position"] != p]
        if not rows:
            continue

        def d(k: str, _rows=rows, _p=p) -> float:
            return statistics.mean(r["chosen"][k] - r["best_by_position"][_p][k] for r in _rows)

        print(
            f"  {p:<5}{len(rows):>4}{d('projection'):>+9.1f}{d('msv'):>+9.1f}{d('da_vorp'):>+9.1f}"
            f"{d('opportunity_cost'):>+10.1f}{d('fit_multiplier'):>+7.2f}"
            f"{d('risk_multiplier'):>+7.2f}{d('survival_multiplier'):>+7.2f}{d('score'):>+10.1f}"
        )

    print("\nOPPORTUNITY COST BY POSITION AND ROUND (the term D81 found dominant at pick 1)")
    print(f"  {'round':<7}" + "".join(f"{p:>9}" for p in POS))
    for rnd in (1, 2, 3):
        vals = []
        for p in POS:
            xs = [r["best_by_position"][p]["opportunity_cost"]
                  for r in picks if r["round"] == rnd and p in r["best_by_position"]]
            vals.append(statistics.mean(xs) if xs else float("nan"))
        print(f"  {rnd:<7}" + "".join(f"{v:>9.1f}" for v in vals))

    print("\n  ... and at the SNAKE TURN (picks_until_next_turn == 0), where oc is 0 by construction")
    turn = [r for r in picks if r["picks_until_next_turn"] == 0]
    notturn = [r for r in picks if r["picks_until_next_turn"] > 0]
    for label, grp in (("at the turn", turn), ("not at turn", notturn)):
        if not grp:
            continue
        c = Counter(r["pick_position"] for r in grp)
        print(f"  {label:<13} n={len(grp):>3}  " + "  ".join(f"{p} {c[p]}" for p in POS if c[p]))

    # survival multiplier -- does it favour the about-to-be-gone?
    print("\nSURVIVAL MULTIPLIER of the chosen player (1.0 = certain to last; 1.3 = certain to go)")
    for rnd in (1, 2, 3):
        sub = [r for r in picks if r["round"] == rnd]
        sm = [r["chosen"]["survival_multiplier"] for r in sub]
        print(f"  round {rnd}: mean {statistics.mean(sm):.3f}  "
              f"at 1.30: {sum(1 for x in sm if x > 1.299) / len(sm):.0%}")

    # ============================ PART 5 ============================
    print("\n" + "=" * 94)
    print("PART 5 -- WHAT THE FIRST THREE ROUNDS BUILD")
    print("=" * 94)

    print("\nPOSITIONAL CONCENTRATION in the opening three")
    conc = Counter()
    for r in rosters:
        c = Counter(r["opening3"])
        conc[max(c.values())] += 1
    for k in sorted(conc):
        print(f"  {k} of 3 at one position: {conc[k]:>3} drafts ({conc[k] / len(rosters):>4.0%})")

    print("\nFIRST ROUND AT WHICH EACH POSITION IS TAKEN (mean over 50 drafts)")
    for key, label in (("first_rb_round", "RB"), ("first_wr_round", "WR"), ("first_qb_round", "QB")):
        vals = [r[key] for r in rosters if r[key]]
        print(f"  first {label}: mean round {statistics.mean(vals):.2f}  "
              f"median {statistics.median(vals):.1f}  max {max(vals)}")

    print("\nDOES THE ENGINE RESPOND TO WHAT IT ALREADY HOLDS?")
    print("  Position taken in round 2 and 3, conditioned on what was taken before:")
    cond = defaultdict(Counter)
    for r in picks:
        if r["round"] > 1:
            cond["-".join(r["roster_positions_before"])][r["pick_position"]] += 1
    for prior in sorted(cond, key=lambda k: -sum(cond[k].values()))[:10]:
        c = cond[prior]
        tot = sum(c.values())
        print(f"    held {prior:<12} (n={tot:>3}) -> " + "  ".join(f"{p} {c[p]}" for p in POS if c[p]))

    print("\nFULL 16-ROUND ROSTER SHAPE (mean count per position)")
    shape = defaultdict(list)
    for r in rosters:
        c = Counter(r["positions"])
        for p in POS:
            shape[p].append(c[p])
    print("  " + "  ".join(f"{p} {statistics.mean(shape[p]):.2f}" for p in POS))

    print("\nREALIZED STARTER POINTS BY OPENING SEQUENCE  (observational -- see caveat)")
    print(f"  {'opening':<14}{'n':>4}{'meanRealized':>14}{'median':>10}")
    byseq = defaultdict(list)
    for r in rosters:
        byseq["-".join(r["opening3"])].append(r["realized_starter_points"])
    for s, v in sorted(byseq.items(), key=lambda kv: -statistics.mean(kv[1])):
        if len(v) >= 2:
            print(f"  {s:<14}{len(v):>4}{statistics.mean(v):>14.0f}{statistics.median(v):>10.0f}")
    allv = [r["realized_starter_points"] for r in rosters]
    print(f"  {'ALL':<14}{len(allv):>4}{statistics.mean(allv):>14.0f}{statistics.median(allv):>10.0f}")
    print(f"  spread across drafts: sd {statistics.stdev(allv):.0f}")

    print("\n  Grouped by whether the opening three contained >=2 WR vs >=2 RB:")
    for label, pred in (
        (">=2 WR", lambda o: o.count("WR") >= 2),
        (">=2 RB", lambda o: o.count("RB") >= 2),
        ("mixed", lambda o: o.count("WR") < 2 and o.count("RB") < 2),
    ):
        v = [r["realized_starter_points"] for r in rosters if pred(r["opening3"])]
        if v:
            print(f"    {label:<8} n={len(v):>3}  mean {statistics.mean(v):>7.0f}  "
                  f"median {statistics.median(v):>7.0f}")


if __name__ == "__main__":
    main()
