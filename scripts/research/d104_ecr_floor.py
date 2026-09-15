"""D104 -- how much of the measured oracle gap does a REAL preseason ranking recover?

Read-only research runner. Reuses D103's instruments verbatim (`draft_oracle.audit_draft` for
pick-level regret, and D103's own `_play_draft`/`oracle_static` for whole-draft value) rather than
reimplementing either. Opens the database read-only; writes nothing but JSON artifacts. No
production module is touched: `models/` and `league/` are byte-identical and no `src/` file changes
in D104 at all.

    uv run python scripts/research/d104_ecr_floor.py --mode decomposition --out <dir>
    uv run python scripts/research/d104_ecr_floor.py --mode divergence    --out <dir>
    uv run python scripts/research/d104_ecr_floor.py --mode regret        --out <dir>

PRE-REGISTRATION (written before ANY D104 comparison was run)
==========================================================================================

THE QUESTION.  Holding the Y1 DECISION RULE FIXED, how much of the Y1 -> ORACLE_Y1 information gap
does the strongest legitimate preseason ranking in this repository recover?

    Y1  ->  FP_ECR_Y1  ->  ORACLE_Y1

ORACLE_Y1 is the information CEILING and is never described as achievable.

WHY `ecr_implied_baseline` IS NOT USED, decided in Phase 0 BEFORE any result was seen
-------------------------------------------------------------------------------------
`models/baselines/market_implied.py::ecr_implied_baseline` is the repository's existing ECR->value
transformation (walk-forward isotonic rank->points). It was inspected and REJECTED for this job on
three independent grounds, each measured:

  1. **It destroys the ordering under test.** The isotonic step function collapses the top of the
     board: in 2023 the top 24 by value hold 4 distinct values at RB (largest tie group 12), 6 at
     WR, 9 at QB, 12 at TE. The draft engine breaks exact ties on `player_id`, so an arm built on
     it would choose among 4-12 tied players ALPHABETICALLY, precisely in rounds 1-5 where D103
     measured regret to be concentrated. That measures the isotonic map plus alphabetical
     tie-breaking, not ECR's information.
  2. **It is hardcoded to `ecr_type='ro'`** and ignores the league's resolved series, so for
     `dynasty_1qb` (series `do`/`dynasty-overall`) it would feed the REDRAFT board -- a D56
     violation. Half the registered population could not be measured at all.
  3. **Coverage is 66-75% of the board** and it covers only QB/RB/WR/TE (`_POSITIONS`), so
     substituting it changes the candidate universe and breaks the pool parity this comparison
     depends on.

THE SUBSTITUTION ACTUALLY USED -- a rank permutation of Y1's own values
------------------------------------------------------------------------
`ecr_ordered_static` replaces, within each position, the ASSIGNMENT of Y1's projected values to
players, ordering players by their preseason ECR rank instead of by Y1's projection:

    C        = board players at this position that carry an ECR rank
    values   = sorted({Y1 projection of x : x in C}, descending)
    players  = C sorted by (ecr_rank ascending, player_id)
    assign     values[i] -> players[i]
    players not in C keep their Y1 projection, untouched

Why this is an INFORMATION substitution and not a new valuation function:

  * the MULTISET of projected values at every position is exactly Y1's, so replacement levels,
    scarcity, consumption demand and the positional value scale are all unchanged;
  * only WHICH player holds which value changes -- that is the ordering information D100 measured
    ECR to be better at;
  * the candidate universe is identical, so pool parity holds by construction;
  * it introduces no ties beyond Y1's own.

The board it reads is `SeasonStatic.market_rank` -- already loaded by the instrument through the
league's RESOLVED series with the correct `page_type`, restricted to July/August scrapes of the
target season. It is the same board the opponent model and the survival term already consume.

METRICS.  Primary: realized roster value per draft (whole-draft arms) and D103's pick-level regret.
Secondary: picks changed, first divergence round, per-position and per-phase breakdowns. Phases are
D103's registered convention -- EARLY 1-5, MIDDLE 6-10, LATE 11-16.

STOPPING RULE, fixed in advance.  Seasons are the independent clusters (k=5). D97's measurement
floor for a draft-level contrast is ~172-250 points. If the Y1 -> FP_ECR_Y1 effect is below that
floor it is classified UNRESOLVED even if the point estimate is positive, and no downstream
production run, 2026 check, retraining or tuning follows. No gate is invented after the fact, and
ECR is not tuned -- there is no weight to tune, by construction.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb

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
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.replacement import marginal_value_over_replacement
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
DEFAULT_SLOTS = (1, 4, 7, 10)
ARMS = ("Y1", "FP_ECR_Y1", "ORACLE_Y1")
SKILL = ("QB", "RB", "WR", "TE")
#: D97's measured floor for a draft-level contrast, quoted not re-derived.
DETECTION_FLOOR = (172.0, 250.0)


def _load_d103():
    """D103's runner, reused rather than reimplemented (the brief forbids a parallel regret
    implementation). `_play_draft` and `oracle_static` are its already-reviewed machinery."""
    path = Path(__file__).resolve().parent / "d103_pick_regret.py"
    spec = importlib.util.spec_from_file_location("d103_pick_regret", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D103 = _load_d103()


class SubstitutionError(RuntimeError):
    """Raised when the ECR substitution would not be a clean information isolation."""


def ecr_ordered_static(league, static, positions=SKILL):
    """`static` with Y1's projected values re-assigned within position by preseason ECR order.

    See the module pre-registration for why this, and not `ecr_implied_baseline`, is the
    substitution. Positions outside `positions` (K/DST, which no ECR board ranks and which come
    from the D57 baselines) are left entirely alone, which is also what isolates the contrast to
    exactly the positions M6 models."""
    projections = dict(static.projections)
    by_position: dict[str, list[str]] = defaultdict(list)
    for player_id in static.projections:
        by_position[static.positions.get(player_id, "UNKNOWN")].append(player_id)

    moved = 0
    for position in positions:
        covered = [p for p in by_position.get(position, []) if p in static.market_rank]
        if len(covered) < 2:
            continue
        values = sorted((static.projections[p] for p in covered), reverse=True)
        ordered = sorted(covered, key=lambda p: (static.market_rank[p][1], p))
        for player_id, value in zip(ordered, values, strict=True):
            if projections[player_id] != value:
                moved += 1
            projections[player_id] = value

    if sorted(projections.values()) != sorted(static.projections.values()):
        raise SubstitutionError(
            "the ECR substitution changed the multiset of projected values; it must be a "
            "permutation within position, or it is a new valuation function rather than an "
            "information change"
        )
    vorp = marginal_value_over_replacement(league, projections, static.positions)
    return dataclasses.replace(static, projections=projections, vorp=vorp), moved


def _arm_static(con, league, season, static, arm):
    if arm == "Y1":
        return static
    if arm == "FP_ECR_Y1":
        return ecr_ordered_static(league, static)[0]
    if arm == "ORACLE_Y1":
        return D103.oracle_static(con, league, season, static)
    raise ValueError(f"unknown arm {arm!r}")


def _static_for(con, league, season):
    series = resolve_market_series(league)
    return load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )


# --------------------------------------------------------------------------------------------
# MODE: decomposition -- Y1 -> FP_ECR_Y1 -> ORACLE_Y1 on realized roster value
# --------------------------------------------------------------------------------------------
def run_decomposition(con, slots, objective):
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            arm_statics = {a: _arm_static(con, league, season, static, a) for a in ARMS}
            for slot in slots:
                row = {"league": league_name, "season": season, "slot": slot,
                       "objective": objective}
                for arm in ARMS:
                    row[arm] = D103._play_draft(
                        con, league, season, arm_statics[arm], slot, SHIPPED_TIER,
                        static, weekly, objective,
                    )
                rows.append(row)
            print(f"  decomposition {league_name} {season} done", flush=True)
    return rows


def _paired(rows, league_name, a, b):
    """Season-clustered paired difference a - b, the independent-unit contrast."""
    by_season = defaultdict(list)
    for r in rows:
        if r["league"] == league_name:
            by_season[r["season"]].append(r[a] - r[b])
    return [mean(v) for _, v in sorted(by_season.items())]


def _ci(values, t_crit=2.776):
    k = len(values)
    md = mean(values)
    if k < 2 or stdev(values) == 0:
        return md, float("nan"), "n/a"
    se = stdev(values) / k**0.5
    return md, md / se, f"[{md - t_crit * se:+.1f}, {md + t_crit * se:+.1f}]"


def report_decomposition(rows):
    print(f"\n{'=' * 98}\nY1 -> FP_ECR_Y1 -> ORACLE_Y1  (realized roster value, Y1 rule held fixed)"
          f"\n{'=' * 98}")
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}   (n = {len(sub)} drafts)")
        for arm in ARMS:
            print(f"    {arm:<12} mean realized value {mean(r[arm] for r in sub):>9.1f}")
        print()
        contrasts = [
            ("1. Y1 -> FP_ECR_Y1  (what a real preseason ranking recovers)", "FP_ECR_Y1", "Y1"),
            ("2. FP_ECR_Y1 -> ORACLE_Y1  (what remains under perfect info)", "ORACLE_Y1",
             "FP_ECR_Y1"),
            ("3. Y1 -> ORACLE_Y1  (the measured ceiling)", "ORACLE_Y1", "Y1"),
        ]
        results = {}
        for label, a, b in contrasts:
            per_season = _paired(sub, league_name, a, b)
            md, t, ci = _ci(per_season)
            wins = sum(1 for v in per_season if v > 0)
            losses = sum(1 for v in per_season if v < 0)
            results[(a, b)] = md
            print(f"    {label}")
            print(f"       {md:>+9.1f}   95% CI {ci}   t={t:>6.2f}   "
                  f"seasons {wins}W/{len(per_season) - wins - losses}T/{losses}L")
            print("       by season: " + "  ".join(
                f"{s}:{v:+.0f}" for s, v in zip(sorted({r['season'] for r in sub}), per_season,
                                                strict=True)))
        num = results[("FP_ECR_Y1", "Y1")]
        den = results[("ORACLE_Y1", "Y1")]
        print(f"\n    fraction of THIS MEASURED oracle gap recovered by the tested preseason ECR "
              f"benchmark: {num:+.1f} / {den:+.1f} = {num / den:+.1%}" if den else "")
        print("    (not a causal estimate; not a generalization beyond this experiment)")
        lo, hi = DETECTION_FLOOR
        verdict = ("BELOW the floor -> UNRESOLVED" if abs(num) < lo
                   else "inside the floor band -> UNRESOLVED" if abs(num) < hi
                   else "ABOVE the floor")
        print(f"    against D97's measurement floor ({lo:.0f}-{hi:.0f} pts): {verdict}")


# --------------------------------------------------------------------------------------------
# MODE: divergence -- which picks actually change, without any rollout
# --------------------------------------------------------------------------------------------
def run_divergence(con, slots):
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            ecr_static, moved = ecr_ordered_static(league, static)
            for slot in slots:
                # Replay ONE draft state sequence, asking both arms at each of our turns from the
                # identical pool and roster. The state advances on Y1's pick, so every comparison
                # is made at a state production actually reaches.
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
                            opps[seat], remaining,
                        )
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                    y1, _ = _pick_by_tier(static, con, league, season, set(avail), list(my_pos),
                                          SHIPPED_TIER, current, nxt, **kw)
                    ecr, _ = _pick_by_tier(ecr_static, con, league, season, set(avail),
                                           list(my_pos), SHIPPED_TIER, current, nxt, **kw)
                    rows.append({
                        "league": league_name, "season": season, "slot": slot,
                        "round": round_no, "phase": D103.phase_of(round_no),
                        "y1_pick": y1, "ecr_pick": ecr, "same": y1 == ecr,
                        "y1_pos": static.positions.get(y1, "UNKNOWN"),
                        "ecr_pos": static.positions.get(ecr, "UNKNOWN"),
                        "values_moved": moved,
                    })
                    mine.append(y1)
                    avail.discard(y1)
            print(f"  divergence {league_name} {season} done", flush=True)
    return rows


def report_divergence(rows):
    print(f"\n{'=' * 98}\nPICK DIVERGENCE -- where does ECR ordering change the engine's choice?"
          f"\n{'=' * 98}")
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        changed = [r for r in sub if not r["same"]]
        print(f"\n  {league_name}: {len(changed)} of {len(sub)} picks changed "
              f"({len(changed) / len(sub):.1%})")
        print(f"    {'phase':<16}{'picks':>7}{'changed':>9}{'%':>8}")
        for phase in D103.PHASES:
            ph = [r for r in sub if r["phase"] == phase]
            ch = [r for r in ph if not r["same"]]
            print(f"    {phase:<16}{len(ph):>7}{len(ch):>9}{len(ch) / len(ph):>7.1%}")
        print(f"    {'round':<16}{'changed %':>10}")
        for rnd in sorted({r["round"] for r in sub}):
            rr = [r for r in sub if r["round"] == rnd]
            print(f"    {rnd:<16}{sum(1 for r in rr if not r['same']) / len(rr):>9.0%}")
        first = []
        for key in {(r["season"], r["slot"]) for r in sub}:
            ch = sorted(r["round"] for r in changed
                        if (r["season"], r["slot"]) == key)
            first.append(ch[0] if ch else None)
        present = [f for f in first if f is not None]
        print(f"    first divergence round: median "
              f"{sorted(present)[len(present) // 2] if present else 'n/a'}, "
              f"drafts with no divergence {sum(1 for f in first if f is None)}/{len(first)}")
        print(f"    position swaps (Y1 pos -> ECR pos), top 8: "
              f"{Counter((r['y1_pos'], r['ecr_pos']) for r in changed).most_common(8)}")


# --------------------------------------------------------------------------------------------
# MODE: regret -- D103's pick-level instrument, unchanged, on the ECR-informed board
# --------------------------------------------------------------------------------------------
def run_regret(con, slots, objective, league_names):
    rows = []
    for league_name in league_names:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            for arm in ("Y1", "FP_ECR_Y1"):
                arm_static = _arm_static(con, league, season, static, arm)
                for slot in slots:
                    picks = audit_draft(
                        con, league, season, slot, arm_static,
                        objective=objective,
                        weekly=weekly if objective != SEASON_LONG else None,
                    )
                    for p in picks:
                        alpha, oracle = p.alpha, p.oracle
                        rows.append({
                            "league": league_name, "season": season, "slot": slot, "arm": arm,
                            "round": p.round_no, "phase": D103.phase_of(p.round_no),
                            "regret": p.regret,
                            "alpha_value": alpha.rollout_starter_points if alpha else 0.0,
                            "best_value": oracle.rollout_starter_points if oracle else 0.0,
                            "alpha_is_oracle": p.alpha_is_oracle,
                            "alpha_pos": alpha.position if alpha else None,
                        })
                    print(f"  regret {league_name} {season} slot {slot} {arm} done", flush=True)
    return rows


def report_regret(rows):
    print(f"\n{'=' * 98}\nPICK-LEVEL REGRET -- D103's instrument, unchanged\n{'=' * 98}")
    for league_name in sorted({r["league"] for r in rows}):
        print(f"\n  {league_name}")
        print(f"    {'arm':<12}{'all':>9}{'EARLY':>9}{'MIDDLE':>9}{'LATE':>9}{'alpha=oracle':>14}")
        for arm in ("Y1", "FP_ECR_Y1"):
            sub = [r for r in rows if r["league"] == league_name and r["arm"] == arm]
            if not sub:
                continue
            cells = []
            for phase in D103.PHASES:
                vals = [r["regret"] for r in sub if r["phase"] == phase]
                cells.append(f"{mean(vals):>9.1f}" if vals else f"{'-':>9}")
            hit = sum(1 for r in sub if r["alpha_is_oracle"]) / len(sub)
            print(f"    {arm:<12}{mean(r['regret'] for r in sub):>9.1f}"
                  + "".join(cells) + f"{hit:>13.1%}")
        by_season = defaultdict(dict)
        for arm in ("Y1", "FP_ECR_Y1"):
            for season in BACKTEST_SEASONS:
                vals = [r["regret"] for r in rows
                        if r["league"] == league_name and r["arm"] == arm and r["season"] == season]
                if vals:
                    by_season[season][arm] = mean(vals)
        diffs = [v["FP_ECR_Y1"] - v["Y1"] for v in by_season.values() if len(v) == 2]
        if diffs:
            md, t, ci = _ci(diffs)
            print(f"    FP_ECR_Y1 - Y1 mean regret: {md:+.1f}  95% CI {ci}  t={t:.2f}  "
                  f"seasons better {sum(1 for d in diffs if d < 0)}/{len(diffs)}")
        print("    by position (mean regret at picks where that position was taken)")
        for arm in ("Y1", "FP_ECR_Y1"):
            cells = []
            for pos in (*SKILL, "K", "DST"):
                vals = [r["regret"] for r in rows if r["league"] == league_name
                        and r["arm"] == arm and r["alpha_pos"] == pos]
                cells.append(f"{pos} {mean(vals):.0f}" if vals else f"{pos} -")
            print(f"      {arm:<12}" + "  ".join(cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True,
                    choices=("decomposition", "divergence", "regret"))
    ap.add_argument("--slots", default=",".join(str(s) for s in DEFAULT_SLOTS))
    ap.add_argument("--objective", default=SEASON_LONG)
    ap.add_argument("--leagues", default=",".join(FORMATS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = tuple(int(s) for s in args.slots.split(","))

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise SubstitutionError(f"{season} must never enter the historical evaluation")

    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}")
    print(f"seasons {BACKTEST_SEASONS}  slots {slots}  arms {ARMS}  mode {args.mode}\n")

    if args.mode == "decomposition":
        rows = run_decomposition(con, slots, args.objective)
        (out / f"d104_decomposition_{args.objective}.json").write_text(json.dumps(rows))
        report_decomposition(rows)
    elif args.mode == "divergence":
        rows = run_divergence(con, slots)
        (out / "d104_divergence.json").write_text(json.dumps(rows))
        report_divergence(rows)
    else:
        leagues = tuple(args.leagues.split(","))
        rows = run_regret(con, slots, args.objective, leagues)
        (out / f"d104_regret_{args.objective}.json").write_text(json.dumps(rows))
        report_regret(rows)


if __name__ == "__main__":
    main()
