"""D105 -- is the draft objective actually sensitive to within-position ranking information?

Read-only research runner. Reuses D103's `_play_draft`/`oracle_static` and D104's
`ecr_ordered_static` verbatim rather than reimplementing anything, and reuses D103's
`audit_draft` for the regret ladder. Opens the database read-only; writes nothing but JSON.
No production module is touched -- `models/` and `league/` are byte-identical and D105 changes
no `src/` file at all.

    uv run python scripts/research/d105_objective_sensitivity.py --mode validity   --out <dir>
    uv run python scripts/research/d105_objective_sensitivity.py --mode value      --out <dir>
    uv run python scripts/research/d105_objective_sensitivity.py --mode divergence --out <dir>
    uv run python scripts/research/d105_objective_sensitivity.py --mode regret     --out <dir>

PRE-REGISTRATION (written before ANY D105 result was inspected)
==========================================================================================

HYPOTHESIS UNDER TEST.

    H_FLAT   Within the Y1 operating region, deliberately degrading within-position ranking
             information produces little or no meaningful degradation in realized pick quality.
    H_ALT    Controlled degradation produces a systematic, measurable decline.

The question is NOT "does random drafting do worse" -- that is trivial and answers nothing. It is
"HOW MUCH does pick quality change as ranking quality is degraded", i.e. the SHAPE of the curve.

THE PERTURBATION -- rank interpolation, the same mechanism D104 used for ECR
-----------------------------------------------------------------------------
Within each position, players are re-ordered by a convex blend of their true Y1 rank and a random
rank, then Y1's OWN values are re-assigned down that order:

    key(p)   = (1 - alpha) * rank_Y1(p) + alpha * rank_random(p)
    players  = covered players sorted by (key, player_id)          <- D54 tie-break
    values   = sorted({Y1 projection of x : x in covered}, desc)
    assign     values[i] -> players[i]

`alpha = 0` reproduces Y1 EXACTLY; `alpha = 1` is a uniform random within-position permutation
independent of Y1. The ladder is L0..L4 at alpha = 0.00, 0.25, 0.50, 0.75, 1.00.

This is deliberately the SAME machinery as D104's `ecr_ordered_static` -- only the ordering key
differs (random blend instead of ECR rank). That is what makes the ECR arm and the scramble ladder
directly comparable rather than two unrelated experiments.

WHAT IS PRESERVED, by construction and asserted at runtime:
  * the MULTISET of projected values at every position is exactly Y1's, so replacement levels,
    scarcity, consumption demand and the positional value scale are unchanged;
  * the candidate universe is identical (pool parity);
  * the decision rule, survival, opportunity cost, capacity, roster logic and continuation
    mechanics are untouched -- only `projections` and its derived `vorp` change;
  * no realized outcome reaches any policy.

WHAT IS *NOT* PURELY WITHIN-POSITION, stated in advance because it matters.  Re-ordering skill
values while holding K/DST fixed changes which individual skill player a given kicker is being
compared against at a particular pick. D104 measured this as RB->K / WR->K drift. It is reported
as a secondary outcome. It is NOT treated as a defect: a drafter with degraded skill rankings
genuinely should sometimes prefer a kicker, so the drift is part of the effect under test, and it
is identical in kind for the ECR arm, which is what keeps the two comparable.

RANDOMIZATION.  Seeds are pre-registered as (0, 1, 2, 3, 4), used identically at every level.
`alpha = 0` is seed-independent and is run once. Randomness is drawn from
`random.Random((seed, season, position, level))` so a re-run reproduces exactly.

**SEEDS ARE NOT INDEPENDENT CLUSTERS.** The independent experimental unit remains the SEASON
(k = 5), as in D97/D103/D104. Seeds are averaged within a season to form that season's value, and
every confidence interval is computed across the five season means. Seeds characterise
sensitivity/noise and are never used to manufacture power.

PRIMARY OUTCOME.  Realized roster value per draft, which D104 established is the cleaner primary
whenever the BOARD changes: running `audit_draft` on a perturbed board changes both the audited
policy and the rollout continuation, so regret becomes arm-relative -- each level would be scored
against its own scrambled oracle. The regret ladder is therefore reported as SECONDARY, at reduced
scope, with that limitation restated.

X-AXIS.  Ranking quality is reported as the measured within-position Spearman correlation between
each arm's ordering and Y1's, averaged over positions and seasons. This is a MEASURED quantity,
not an invented score, and ECR has one too -- which is how FP_ECR_Y1 is placed on the same axis
without forcing a metric. Realized-outcome Spearman is reported alongside, so the ladder is shown
to degrade PREDICTIVE quality and not merely agreement with Y1.

INTERPRETATION, fixed in advance.  No new threshold is invented. Effects are read against three
existing quantities: D103's decision-shaped residual (~86-113 pts/draft), D104's ECR effect
(+77.3 target / -132.1 dynasty), and D97's detection floor (~172-250 pts for a draft-level
contrast).

    SENSITIVE (A)   controlled degradation produces decline exceeding the floor at moderate alpha.
    ROBUST (B)      decline is clear only at severe alpha (0.75-1.00); moderate alpha is inside
                    the floor.
    FLAT (C)        even alpha = 1.00 produces decline below the floor.
    UNRESOLVED (D)  the ladder is non-monotone or the instrument cannot resolve it.

A CI spanning zero is NOT on its own grounds for B or C; magnitude against the floor is.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb
import pandas as pd

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.draft_forensics import (
    _pick_by_tier,
    load_season_static,
    preseason_page_type,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    draft_order,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.replacement import marginal_value_over_replacement
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
DEFAULT_SLOTS = (1, 4, 7, 10)
SKILL = ("QB", "RB", "WR", "TE")
#: The pre-registered perturbation ladder. L0 reproduces Y1 exactly; L4 is a uniform permutation.
LEVELS: dict[str, float] = {"L0": 0.00, "L1": 0.25, "L2": 0.50, "L3": 0.75, "L4": 1.00}
#: Pre-registered seeds, identical at every level. NOT independent clusters -- seasons are.
SEEDS = (0, 1, 2, 3, 4)
#: Quoted from D97/D103/D104, never re-derived here.
DETECTION_FLOOR = (172.0, 250.0)
D103_DECISION_RESIDUAL = (86.0, 113.0)


def _load(name):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D103 = _load("d103_pick_regret")
D104 = _load("d104_ecr_floor")


class PerturbationError(RuntimeError):
    """Raised when a perturbation would change more than the within-position ordering."""


def perturbed_static(league, static, alpha: float, seed: int, positions=SKILL):
    """`static` with Y1's values re-assigned within position by a rank-interpolated ordering.

    See the module pre-registration. `alpha=0` must reproduce `static` exactly; that is asserted
    by test, not assumed."""
    if not 0.0 <= alpha <= 1.0:
        raise PerturbationError(f"alpha must be in [0, 1], got {alpha}")
    projections = dict(static.projections)
    by_position: dict[str, list[str]] = defaultdict(list)
    for player_id in static.projections:
        by_position[static.positions.get(player_id, "UNKNOWN")].append(player_id)

    for position in positions:
        covered = sorted(by_position.get(position, []))
        if len(covered) < 2:
            continue
        # True Y1 rank within position, 1 = best. Deterministic under ties via player_id.
        by_value = sorted(covered, key=lambda p: (-static.projections[p], p))
        true_rank = {p: i + 1 for i, p in enumerate(by_value)}
        # A STRING seed, not a tuple: `random.Random` rejects tuples, and a string is hashed from
        # its bytes so the stream is reproducible across processes (unlike `hash()` on a str,
        # which is salted per interpreter run).
        rng = random.Random(f"{seed}|{static.season}|{position}|{alpha}")
        shuffled = list(covered)
        rng.shuffle(shuffled)
        random_rank = {p: i + 1 for i, p in enumerate(shuffled)}

        key = {p: (1.0 - alpha) * true_rank[p] + alpha * random_rank[p] for p in covered}
        ordered = sorted(covered, key=lambda p: (key[p], p))
        values = sorted((static.projections[p] for p in covered), reverse=True)
        for player_id, value in zip(ordered, values, strict=True):
            projections[player_id] = value

    if sorted(projections.values()) != sorted(static.projections.values()):
        raise PerturbationError(
            "the perturbation changed the multiset of projected values; it must be a permutation "
            "within position, or the arm is a new valuation function rather than a ranking change"
        )
    vorp = marginal_value_over_replacement(league, projections, static.positions)
    return dataclasses.replace(static, projections=projections, vorp=vorp)


def _static_for(con, league, season):
    series = resolve_market_series(league)
    return load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )


def _spearman(a: list[float], b: list[float]) -> float:
    if len(a) < 3:
        return float("nan")
    ra, rb = pd.Series(a).rank(), pd.Series(b).rank()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(ra.corr(rb))


# --------------------------------------------------------------------------------------------
# MODE: validity -- does the ladder actually degrade ranking information, monotonically?
# --------------------------------------------------------------------------------------------
def run_validity(con):
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            realized = _actual_points_for(con, season, sorted(static.projections))
            arms = {name: perturbed_static(league, static, a, SEEDS[0])
                    for name, a in LEVELS.items()}
            arms["FP_ECR_Y1"] = D104.ecr_ordered_static(league, static)[0]
            for name, arm in arms.items():
                for position in SKILL:
                    ids = sorted(p for p in static.projections
                                 if static.positions.get(p) == position)
                    if len(ids) < 3:
                        continue
                    rows.append({
                        "league": league_name, "season": season, "arm": name,
                        "position": position,
                        # agreement with Y1's ordering -- the registered x-axis
                        "spearman_vs_y1": _spearman([arm.projections[p] for p in ids],
                                                    [static.projections[p] for p in ids]),
                        # agreement with what actually happened -- predictive quality
                        "spearman_vs_realized": _spearman([arm.projections[p] for p in ids],
                                                          [realized.get(p, 0.0) for p in ids]),
                    })
            print(f"  validity {league_name} {season} done", flush=True)
    return rows


def report_validity(rows):
    print(f"\n{'=' * 98}\nVALIDITY -- does the ladder degrade ranking information monotonically?"
          f"\n{'=' * 98}")
    order = [*LEVELS, "FP_ECR_Y1"]
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}")
        print(f"    {'arm':<12}{'alpha':>7}{'Spearman vs Y1':>17}{'Spearman vs REALIZED':>22}")
        for arm in order:
            vals = [r for r in sub if r["arm"] == arm]
            if not vals:
                continue
            a = f"{LEVELS[arm]:.2f}" if arm in LEVELS else "-"
            print(f"    {arm:<12}{a:>7}{mean(r['spearman_vs_y1'] for r in vals):>17.3f}"
                  f"{mean(r['spearman_vs_realized'] for r in vals):>22.3f}")
        print("    by position, Spearman vs REALIZED")
        print(f"      {'arm':<12}" + "".join(f"{p:>9}" for p in SKILL))
        for arm in order:
            cells = []
            for position in SKILL:
                vals = [r["spearman_vs_realized"] for r in sub
                        if r["arm"] == arm and r["position"] == position]
                cells.append(f"{mean(vals):>9.3f}" if vals else f"{'-':>9}")
            print(f"      {arm:<12}" + "".join(cells))


# --------------------------------------------------------------------------------------------
# MODE: value -- the primary outcome, realized roster value along the ladder
# --------------------------------------------------------------------------------------------
def run_value(con, slots, objective, seeds):
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            arms: list[tuple[str, int, object]] = []
            for name, alpha in LEVELS.items():
                # alpha = 0 is seed-independent: run it once rather than five identical times.
                for seed in ((seeds[0],) if alpha == 0.0 else seeds):
                    arms.append((name, seed, perturbed_static(league, static, alpha, seed)))
            arms.append(("FP_ECR_Y1", -1, D104.ecr_ordered_static(league, static)[0]))
            arms.append(("ORACLE_Y1", -2, D103.oracle_static(con, league, season, static)))
            for slot in slots:
                for name, seed, arm in arms:
                    value = D103._play_draft(
                        con, league, season, arm, slot, SHIPPED_TIER, static, weekly, objective
                    )
                    rows.append({"league": league_name, "season": season, "slot": slot,
                                 "arm": name, "seed": seed, "value": value})
            print(f"  value {league_name} {season} done", flush=True)
    return rows


def _season_means(rows, league_name, arm):
    """Average over seeds and slots WITHIN a season -- seasons are the independent clusters."""
    by_season = defaultdict(list)
    for r in rows:
        if r["league"] == league_name and r["arm"] == arm:
            by_season[r["season"]].append(r["value"])
    return [mean(v) for _, v in sorted(by_season.items())]


def _ci(values, t_crit=2.776):
    k = len(values)
    md = mean(values)
    if k < 2 or stdev(values) == 0:
        return md, float("nan"), "n/a"
    se = stdev(values) / k**0.5
    return md, md / se, f"[{md - t_crit * se:+.1f}, {md + t_crit * se:+.1f}]"


def report_value(rows):
    print(f"\n{'=' * 98}\nSENSITIVITY CURVE -- realized roster value along the ranking ladder"
          f"\n{'=' * 98}")
    lo, hi = DETECTION_FLOOR
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        base = _season_means(sub, league_name, "L0")
        print(f"\n  {league_name}   (L0 = Y1 baseline, {mean(base):.1f})")
        print(f"    {'arm':<12}{'alpha':>7}{'value':>10}{'vs L0':>10}{'95% CI':>20}"
              f"{'seasons worse':>15}{'vs floor':>12}")
        for arm in [*LEVELS, "FP_ECR_Y1", "ORACLE_Y1"]:
            means = _season_means(sub, league_name, arm)
            if not means:
                continue
            diffs = [m - b for m, b in zip(means, base, strict=True)]
            md, _, ci = _ci(diffs)
            worse = sum(1 for d in diffs if d < 0)
            a = f"{LEVELS[arm]:.2f}" if arm in LEVELS else "-"
            flag = ("--" if arm == "L0" else
                    "ABOVE" if abs(md) >= hi else
                    "in band" if abs(md) >= lo else "below")
            print(f"    {arm:<12}{a:>7}{mean(means):>10.1f}{md:>+10.1f}{ci:>20}"
                  f"{f'{worse}/{len(diffs)}':>15}{flag:>12}")
        print("\n    per season, value vs L0")
        print(f"      {'arm':<12}" + "".join(f"{s:>9}" for s in BACKTEST_SEASONS))
        for arm in [*LEVELS, "FP_ECR_Y1", "ORACLE_Y1"]:
            means = _season_means(sub, league_name, arm)
            if not means:
                continue
            diffs = [m - b for m, b in zip(means, base, strict=True)]
            print(f"      {arm:<12}" + "".join(f"{d:>+9.0f}" for d in diffs))
        print("\n    seed dispersion within the ladder (SD across seeds of the draft value)")
        for arm in LEVELS:
            per = defaultdict(list)
            for r in sub:
                if r["arm"] == arm:
                    per[(r["season"], r["slot"])].append(r["value"])
            sds = [stdev(v) for v in per.values() if len(v) > 1]
            print(f"      {arm:<12}mean within-cell SD across seeds "
                  f"{mean(sds):>8.1f}" if sds else f"      {arm:<12}seed-independent")


# --------------------------------------------------------------------------------------------
# MODE: divergence -- decision sensitivity, separate from value sensitivity
# --------------------------------------------------------------------------------------------
def run_divergence(con, slots, seeds):
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            arms = {f"{n}|{s}": perturbed_static(league, static, a, s)
                    for n, a in LEVELS.items() for s in ((seeds[0],) if a == 0.0 else seeds)}
            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, static.positions, league,
                            opps[seat], remaining)
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                    baseline, _ = _pick_by_tier(static, con, league, season, set(avail),
                                                list(my_pos), SHIPPED_TIER, current, nxt, **kw)
                    for key, arm in arms.items():
                        pick, _ = _pick_by_tier(arm, con, league, season, set(avail),
                                                list(my_pos), SHIPPED_TIER, current, nxt, **kw)
                        name, seed = key.split("|")
                        rows.append({
                            "league": league_name, "season": season, "slot": slot,
                            "arm": name, "seed": int(seed), "round": round_no,
                            "phase": D103.phase_of(round_no), "same": pick == baseline,
                            "base_pos": static.positions.get(baseline, "UNKNOWN"),
                            "arm_pos": static.positions.get(pick, "UNKNOWN"),
                        })
                    mine.append(baseline)
                    avail.discard(baseline)
            print(f"  divergence {league_name} {season} done", flush=True)
    return rows


def report_divergence(rows, value_rows=None):
    print(f"\n{'=' * 98}\nDECISION SENSITIVITY -- how many picks change, vs how much value moves"
          f"\n{'=' * 98}")
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}")
        print(f"    {'arm':<8}{'alpha':>7}{'picks changed':>15}{'EARLY':>9}{'MIDDLE':>9}"
              f"{'LATE':>9}{'first div (median rd)':>23}")
        for arm in LEVELS:
            a = [r for r in sub if r["arm"] == arm]
            if not a:
                continue
            changed = [r for r in a if not r["same"]]
            cells = []
            for phase in D103.PHASES:
                ph = [r for r in a if r["phase"] == phase]
                cells.append(f"{sum(1 for r in ph if not r['same']) / len(ph):>8.1%}" if ph
                             else f"{'-':>8}")
            firsts = []
            for key in {(r["season"], r["slot"], r["seed"]) for r in a}:
                ch = sorted(r["round"] for r in changed
                            if (r["season"], r["slot"], r["seed"]) == key)
                firsts.append(ch[0] if ch else 99)
            med = sorted(firsts)[len(firsts) // 2] if firsts else 0
            print(f"    {arm:<8}{LEVELS[arm]:>7.2f}{len(changed) / len(a):>14.1%}"
                  + "".join(f"{c:>9}" for c in cells)
                  + f"{(med if med < 99 else 'none'):>23}")
        print("\n    positional MIX of the arm's pick when it diverges (top 5)")
        for arm in LEVELS:
            changed = [r for r in sub if r["arm"] == arm and not r["same"]]
            if not changed:
                continue
            print(f"      {arm:<8}{Counter(r['arm_pos'] for r in changed).most_common(5)}")


# --------------------------------------------------------------------------------------------
# MODE: regret -- SECONDARY. See the pre-registration for why.
# --------------------------------------------------------------------------------------------
def run_regret(con, slots, objective, league_names, levels, seed):
    rows = []
    for league_name in league_names:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            for name in levels:
                arm = perturbed_static(league, static, LEVELS[name], seed)
                for slot in slots:
                    for p in audit_draft(
                        con, league, season, slot, arm, objective=objective,
                        weekly=weekly if objective != SEASON_LONG else None,
                    ):
                        rows.append({
                            "league": league_name, "season": season, "slot": slot, "arm": name,
                            "round": p.round_no, "phase": D103.phase_of(p.round_no),
                            "regret": p.regret, "alpha_is_oracle": p.alpha_is_oracle,
                            "alpha_pos": p.alpha.position if p.alpha else None,
                        })
                    print(f"  regret {league_name} {season} slot {slot} {name} done", flush=True)
    return rows


def report_regret(rows):
    print(f"\n{'=' * 98}\nREGRET LADDER (SECONDARY -- each level is scored against its OWN oracle)"
          f"\n{'=' * 98}")
    for league_name in sorted({r["league"] for r in rows}):
        print(f"\n  {league_name}")
        print(f"    {'arm':<8}{'alpha':>7}{'all':>9}{'EARLY':>9}{'MIDDLE':>9}{'LATE':>9}"
              f"{'alpha=oracle':>14}")
        for arm in LEVELS:
            sub = [r for r in rows if r["league"] == league_name and r["arm"] == arm]
            if not sub:
                continue
            cells = []
            for phase in D103.PHASES:
                vals = [r["regret"] for r in sub if r["phase"] == phase]
                cells.append(f"{mean(vals):>9.1f}" if vals else f"{'-':>9}")
            print(f"    {arm:<8}{LEVELS[arm]:>7.2f}{mean(r['regret'] for r in sub):>9.1f}"
                  + "".join(cells)
                  + f"{sum(1 for r in sub if r['alpha_is_oracle']) / len(sub):>13.1%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True,
                    choices=("validity", "value", "divergence", "regret"))
    ap.add_argument("--slots", default=",".join(str(s) for s in DEFAULT_SLOTS))
    ap.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    ap.add_argument("--objective", default=SEASON_LONG)
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument("--levels", default=",".join(LEVELS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = tuple(int(s) for s in args.slots.split(","))
    seeds = tuple(int(s) for s in args.seeds.split(","))

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise PerturbationError(f"{season} must never enter the historical evaluation")

    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}")
    print(f"seasons {BACKTEST_SEASONS}  slots {slots}  seeds {seeds}  levels {LEVELS}\n")

    if args.mode == "validity":
        rows = run_validity(con)
        (out / "d105_validity.json").write_text(json.dumps(rows))
        report_validity(rows)
    elif args.mode == "value":
        rows = run_value(con, slots, args.objective, seeds)
        (out / f"d105_value_{args.objective}.json").write_text(json.dumps(rows))
        report_value(rows)
    elif args.mode == "divergence":
        rows = run_divergence(con, slots, seeds)
        (out / "d105_divergence.json").write_text(json.dumps(rows))
        report_divergence(rows)
    else:
        rows = run_regret(con, slots, args.objective, tuple(args.leagues.split(",")),
                          tuple(args.levels.split(",")), seeds[0])
        (out / f"d105_regret_{args.objective}.json").write_text(json.dumps(rows))
        report_regret(rows)


if __name__ == "__main__":
    main()
