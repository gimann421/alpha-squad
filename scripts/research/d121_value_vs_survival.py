"""D121 -- in the early-round wrong-position states D120 isolated, is it the VALUE TERM or the
SURVIVAL URGENCY term that makes the rule prefer its RB over the oracle's WR/QB?

Read-only research runner. Starts from D120's corrected perfect-projection arm (ARM 4:
realized-points projections + recomputed replacement levels + confidence recomputed with M6's
own formula), re-walks the same 640 production pick states through D115's replay, re-asks the
shipped `_pick_by_tier` on the ARM 4 board, and scores every counterfactual pick with D115's
common one-step continuation. It writes nothing but JSON under `--out`. **No file under
`src/alpha_squad/` is touched and this script is imported by no production path.**

    uv run python scripts/research/d121_value_vs_survival.py --mode measure \
        --leagues <f> --d115 <dir> --d120 <dir> --out <o>
    uv run python scripts/research/d121_value_vs_survival.py --mode report --out <o>

==========================================================================================
PRE-REGISTRATION -- written before any D121 number existed
==========================================================================================

DEFINITIONS, fixed now and not changed later
  * "The oracle" is D115/D120's per-pick oracle O: the slate maximiser of one-step roster value
    under the common continuation, whose regret D120 decomposed. (D120's ~13% residual is
    ARM 4's regret against O.) It is NOT the ORACLE_Y1 arm.
  * P = ARM 4's pick (the corrected perfect-projection rule).
  * One-step roster value of a candidate = D115's `roll_from_state` value (season-long scorer,
    D115's own), and the WEEKLY_NO_FORESIGHT scorer as the weekly objective. No new regret.
  * Shipped L0 score = (value_base + OC) * fit * risk * survival * capacity, with
    value_base = MSV + 1.0 * DA-VORP (`DECISION_ARM_VORP_WEIGHT` = 1.0, asserted), so
    DA-VORP = value_base - MSV exactly. L0 does not enforce the legality restriction (asserted),
    so the engine's pick is argmax(score) with `player_id` as the tie key -- which is what makes
    a re-ranking with one component neutralised an exact counterfactual of the engine.

REPRODUCTION (stop condition): ARM 4's pick is recomputed at all 640 states per format and must
equal D120's stored ARM 4 pick at every one; ARM 4's one-step value is recomputed at every
included state and must equal D120's stored value to 1e-6. Any mismatch raises.

POPULATION
  PRIMARY    rounds 1-6, P is an RB, O is a WR (A: RB->WR) or a QB (B: RB->QB).
  CONTEXT    rounds 1-6, P is a WR or QB and O is an RB (the reverse flows). Reported
             separately, never pooled with the primary.

PER STATE, for P and O on the ARM 4 board: MSV, DA-VORP, value_base, fit, risk, survival
multiplier, OC, capacity, final score, and the one-step roster value (season-long and weekly).

Q1  value_preference = sign(value_base_P - value_base_O) against one_step_preference =
    sign(value_P - value_O): the 2x2, with counts, regret, and mean/median score and value gaps.
    The one-step preference favours O BY CONSTRUCTION whenever P is inside O's slate (O is the
    slate maximiser); it can favour P only where P lies outside the slate. That is stated, not
    hidden, and the weekly one-step preference (where O is not the maximiser) is reported beside.
Q2  States where the value term prefers O but the final score picks P: neutralise ONLY survival
    (multiplier = 1 for every candidate) and re-rank the whole board. Report flips, the new
    pick's realized one-step value, and the regret recovered. And the reverse: where the value
    term prefers P, how often survival also favours P (reinforcement).

NEUTRALISATION ARMS (diagnostic, not interventions), one component at a time, value term never
touched: survival -> 1, OC -> 0, fit -> 1, risk -> 1, capacity -> 1, applied to EVERY candidate,
whole board re-ranked. Per arm: picks changed, pairwise P->O and O->P order changes, whole-board
new pick == O, realized season-long and weekly value vs ARM 4, regret, change in regret per pick,
season-clustered CI and the design's own MDE (CI half-width).

VALUE-TERM DECOMPOSITION: MSV alone, DA-VORP alone, MSV + DA-VORP -- which player each prefers,
by how much, how often it disagrees with one-step value, and the regret on those states. The
"MSV equals raw projection when the slot is empty" property is measured per player
(|MSV - projection| < 1e-6). It is called a defect ONLY if it is shown to produce a ranking that
disagrees with one-step value in a way the other terms do not.

SCORE-GAP CLASSES (mutually exclusive, fixed now), per primary state:
  1  large value disagreement      value_base prefers P, and value's Shapley share of the P-O
                                   score gap >= 50%
  2  small value disagreement,     value_base prefers P, value's share < 50%; labelled by the
     amplified                     component with the largest P-favouring Shapley contribution
                                   (survival, or other)
  3  correct value, overturned by  value_base prefers O, and neutralising survival alone flips
     survival                      the pair to O
  4  correct value, overturned by  value_base prefers O, survival alone does not flip it, some
     another single component     other single neutralisation does
  5  combination                   value_base prefers O and no single neutralisation flips it

ORACLE-ALIGNED VALUE (pairwise, mechanical, no new rollouts): set value_base_O' = value_base_P +
(one-step value_O - one-step value_P), keep every multiplier, and ask whether O now outscores P.
That answers "if the value term's gap equalled the one-step roster value gap, would the other
terms still pick P?" -- a pairwise statement only, not a whole-board policy.

FINAL CLASSIFICATION of the primary regret into D120/brief categories A-G by the classes above:
A value construction (1, 2-other), B survival (2-survival, 3), C OC, D fit, E risk, F capacity
(4, by the flipping component), G combination (5). A component is called a CANDIDATE for future
rule experimentation only if its disagreement is reproducible (same sign in both formats and in
a majority of seasons), associated with regret (paired CI on its neutralisation excludes 0 in
the helpful direction), and distinguishable (it accounts for the largest class).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.draft_forensics import (
    DECISION_ARM_VORP_WEIGHT,
    L_TIER_SPEC,
    TIERS_ENFORCING_LEGALITY,
    _pick_by_tier,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    WEEKLY_NO_FORESIGHT,
    assert_no_realized_inputs_in_policy,
    make_roster_scorer,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.replacement_diagnostics import consumption_replacement
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
EARLY_ROUNDS = (1, 2, 3, 4, 5, 6)
PRIMARY_FLOWS = (("RB", "WR"), ("RB", "QB"))
CONTEXT_FLOWS = (("WR", "RB"), ("QB", "RB"))
COMPONENTS = ("survival", "opp_cost", "fit", "risk", "capacity")
NEUTRAL = {"survival": 1.0, "opp_cost": 0.0, "fit": 1.0, "risk": 1.0, "capacity": 1.0}
REPRO_TOLERANCE = 1e-6
T_CRIT = {5: 2.776, 4: 3.182, 3: 4.303, 2: 12.706}


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D120 = _load("d120_perfect_projection_gap")
D117, D116, D115 = D120.D117, D120.D116, D120.D115


class UnreconstructibleError(RuntimeError):
    """D121 stops rather than substituting."""


# --------------------------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------------------------
def sign(x: float, tol: float = 1e-9) -> int:
    return 0 if abs(x) <= tol else (1 if x > 0 else -1)


def l0_score(f: dict) -> float:
    return D117.l0_score(f)


def neutralised(f: dict, component: str) -> dict:
    return {**f, component: NEUTRAL[component]}


def argmax_pick(factors: dict[str, dict], component: str | None = None) -> str:
    """The engine's pick over a whole board of factor dicts: max score, `player_id` tie key --
    `_pick_by_tier`'s own ordering for a tier that does not enforce legality."""

    def key(pid):
        f = factors[pid] if component is None else neutralised(factors[pid], component)
        return (-l0_score(f), pid)

    return min(factors, key=key)


def value_split(candidate: dict, factors: dict) -> dict:
    """MSV, DA-VORP and their sum for one candidate. DA-VORP = value_base - MSV exactly, because
    the shipped weight is 1.0 (asserted at import)."""
    msv = candidate["marginal_starter_value"]
    if msv is None:
        raise UnreconstructibleError(f"no MSV on {candidate['player_id']}")
    vb = factors["value"]
    return {
        "msv": msv,
        "da_vorp": vb - msv,
        "value_base": vb,
        "msv_equals_projection": abs(msv - candidate["projection"]) < 1e-6,
    }


def score_gap_class(value_pref: int, shapley: dict, flips: dict) -> str:
    """The pre-registered, mutually exclusive classes. `value_pref` = sign(vb_P - vb_O);
    `flips[c]` = does neutralising component c alone make O outscore P."""
    if value_pref > 0:
        gap = sum(shapley.values())
        share = shapley["value"] / gap if gap else 0.0
        if share >= 0.5:
            return "1_large_value_disagreement"
        others = {k: v for k, v in shapley.items() if k != "value"}
        top = max(others, key=lambda k: others[k])
        return (
            "2_small_value_amplified_by_survival"
            if top == "survival"
            else "2_small_value_amplified_by_other"
        )
    if flips.get("survival"):
        return "3_correct_value_overturned_by_survival"
    single = [c for c in COMPONENTS if c != "survival" and flips.get(c)]
    if single:
        return f"4_correct_value_overturned_by_{single[0]}"
    return "5_combination"


def season_ci(values: dict) -> dict:
    vals = [v for v in values.values() if v is not None]
    k = len(vals)
    if k < 2:
        return {"k": k, "mean": vals[0] if vals else None, "ci": None, "mde": None}
    md, se = mean(vals), stdev(vals) / math.sqrt(k)
    t = T_CRIT.get(k, 2.0)
    return {"k": k, "mean": md, "ci": (md - t * se, md + t * se), "mde": t * se}


# --------------------------------------------------------------------------------------------
# MODE: measure
# --------------------------------------------------------------------------------------------
def _key(r) -> tuple:
    return (r["league"], r["season"], r["slot"], r["overall_pick"])


def flow_of(p_pos: str, o_pos: str, round_no: int) -> str | None:
    if round_no not in EARLY_ROUNDS:
        return None
    if (p_pos, o_pos) in PRIMARY_FLOWS:
        return f"PRIMARY {p_pos}->{o_pos}"
    if (p_pos, o_pos) in CONTEXT_FLOWS:
        return f"CONTEXT {p_pos}->{o_pos}"
    return None


def exact_value_bases(factors: dict, cands: dict, board, league, state) -> None:
    """Replace each candidate's value_base with the engine's exact value: MSV + (projection -
    draft-aware level), the level falling back to the static one exactly as `score_candidate`
    does. Where the score identifies value_base (non-zero multiplier product) the two must agree
    to 1e-6; where confidence is 0 the score hides it and D116's logged 0.1-point value is the
    only other source, so they must agree to 0.051. Without this, neutralising risk would rank
    confidence-0 players on a rounded value."""
    dyn = consumption_replacement(board.consumption_demand)(
        league, set(state["available"]), board.projections, board.positions
    )
    for pid, c in cands.items():
        pos = c["position"]
        exact = c["marginal_starter_value"] + (
            c["projection"] - dyn.get(pos, board.replacement_levels.get(pos, 0.0))
        )
        f = factors[pid]
        identified = f["fit"] * f["risk"] * f["survival"] * f["capacity"] > 0
        tol = 1e-6 * max(1.0, abs(exact)) if identified else 0.051
        if abs(exact - f["value"]) > tol:
            raise UnreconstructibleError(
                f"exact value_base {exact:.4f} != engine-implied {f['value']:.4f} for {pid}"
            )
        f["value"] = exact


def rollout_pair(ctx: tuple, pick: str, cache: dict) -> tuple[float, float]:
    return D120.rollout_pair(ctx, pick, cache)


def run_measure(con, leagues, d115: dict, d120_rows: dict) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    repro = {"states_checked": 0, "arm4_pick_matches": 0}
    t0 = time.time()
    for league_name in leagues:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            arm4 = D120.arm_statics(con, league, season, static)["ARM4"]
            realized = _actual_points_for(con, season, sorted(static.projections))
            sl = make_roster_scorer(SEASON_LONG, league, static)
            wk = make_roster_scorer(
                WEEKLY_NO_FORESIGHT, league, static, load_weekly_points(con, season)
            )
            for slot in sorted({k[2] for k in d120_rows if k[0] == league_name and k[1] == season}):
                states = D115.replay_states(con, league, season, static, slot)
                for state in states:
                    key = (league_name, season, slot, state["overall_pick"])
                    ref = d120_rows.get(key)
                    if ref is None:
                        raise UnreconstructibleError(f"no D120 row for {key}")
                    pick, scored = _pick_by_tier(
                        arm4,
                        con,
                        league,
                        season,
                        set(state["available"]),
                        [static.positions.get(p, "UNKNOWN") for p in state["drafted"]],
                        SHIPPED_TIER,
                        state["overall_pick"],
                        state["next_pick"],
                        roster_player_ids=list(state["drafted"]),
                        picks_remaining=state["picks_remaining"],
                    )
                    repro["states_checked"] += 1
                    if pick != ref["arms"]["ARM4"]["pick"]:
                        raise UnreconstructibleError(
                            f"ARM 4 pick {pick} != D120's {ref['arms']['ARM4']['pick']} at {key}"
                            " -- STOP"
                        )
                    repro["arm4_pick_matches"] += 1
                    o = ref["oracle_player"]
                    flow = flow_of(
                        static.positions.get(pick, "UNKNOWN"),
                        ref["oracle_position"],
                        state["round"],
                    )
                    if flow is None or pick == o:
                        continue
                    cands = {c.player_id: D116._candidate_dict(c) for c in scored}
                    if o not in cands:
                        raise UnreconstructibleError(
                            f"oracle player not on the ARM 4 board at {key}"
                        )
                    factors = {pid: D117.factors_from(c) for pid, c in cands.items()}
                    exact_value_bases(factors, cands, arm4, league, state)
                    if argmax_pick(factors) != pick:
                        raise UnreconstructibleError(
                            f"re-ranking from factors does not reproduce the engine at {key}"
                        )
                    ctx = (con, league, season, static, slot, state, realized, sl, wk)
                    cache: dict = {}
                    v_p = rollout_pair(ctx, pick, cache)
                    if abs(v_p[0] - ref["arms"]["ARM4"]["rollout"]) > REPRO_TOLERANCE:
                        raise UnreconstructibleError(f"ARM 4 rollout != D120's at {key}")
                    v_o = rollout_pair(ctx, o, cache)
                    if abs(v_o[0] - ref["oracle_rollout"]) > REPRO_TOLERANCE:
                        raise UnreconstructibleError(f"oracle rollout != D115's at {key}")
                    fp, fo = factors[pick], factors[o]
                    arms = {}
                    for comp in COMPONENTS:
                        new = argmax_pick(factors, comp)
                        v_new = rollout_pair(ctx, new, cache)
                        arms[comp] = {
                            "pick": new,
                            "changed": new != pick,
                            "new_is_oracle": new == o,
                            "pair_flips_to_O": l0_score(neutralised(fo, comp))
                            > l0_score(neutralised(fp, comp)),
                            "value": v_new[0],
                            "value_weekly": v_new[1],
                            "delta": v_new[0] - v_p[0],
                            "delta_weekly": v_new[1] - v_p[1],
                        }
                    # Oracle-aligned value, pairwise and mechanical.
                    aligned_o = {**fo, "value": fp["value"] + (v_o[0] - v_p[0])}
                    rows.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "round": state["round"],
                            "overall_pick": state["overall_pick"],
                            "flow": flow,
                            "P": pick,
                            "O": o,
                            "P_position": static.positions.get(pick),
                            "O_position": ref["oracle_position"],
                            "factors_P": fp,
                            "factors_O": fo,
                            "value_split_P": value_split(cands[pick], fp),
                            "value_split_O": value_split(cands[o], fo),
                            "projection_P": cands[pick]["projection"],
                            "projection_O": cands[o]["projection"],
                            "score_P": l0_score(fp),
                            "score_O": l0_score(fo),
                            "shapley": D117.shapley(fp, fo),
                            "onestep_P": v_p[0],
                            "onestep_O": v_o[0],
                            "onestep_weekly_P": v_p[1],
                            "onestep_weekly_O": v_o[1],
                            "regret": v_o[0] - v_p[0],
                            "arms": arms,
                            "aligned_value_O_wins": l0_score(aligned_o) > l0_score(fp),
                        }
                    )
                print(
                    f"  measure {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows, repro


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
def _stats(xs: list[float]) -> dict:
    return {
        "n": len(xs),
        "mean": mean(xs) if xs else None,
        "median": median(xs) if xs else None,
    }


def two_by_two(rows: list[dict], weekly: bool = False) -> dict:
    out = {}
    for r in rows:
        vp = sign(r["value_split_P"]["value_base"] - r["value_split_O"]["value_base"])
        if weekly:
            op = sign(r["onestep_weekly_P"] - r["onestep_weekly_O"])
        else:
            op = sign(r["onestep_P"] - r["onestep_O"])
        cell = (
            f"value_prefers_{'P' if vp > 0 else ('O' if vp < 0 else 'tie')}|"
            f"onestep_prefers_{'P' if op > 0 else ('O' if op < 0 else 'tie')}"
        )
        out.setdefault(cell, []).append(r)
    return {
        cell: {
            "n": len(rs),
            "pct": 100 * len(rs) / len(rows) if rows else None,
            "regret": sum(r["regret"] for r in rs),
            "score_gap": _stats([r["score_P"] - r["score_O"] for r in rs]),
            "value_gap": _stats(
                [r["value_split_P"]["value_base"] - r["value_split_O"]["value_base"] for r in rs]
            ),
            "onestep_gap": _stats([r["onestep_P"] - r["onestep_O"] for r in rs]),
        }
        for cell, rs in sorted(out.items())
    }


def arm_table(rows: list[dict], total_arm4_regret: float) -> dict:
    out = {}
    for comp in COMPONENTS:
        per_season = defaultdict(list)
        per_season_wk = defaultdict(list)
        for r in rows:
            per_season[r["season"]].append(r["arms"][comp]["delta"])
            per_season_wk[r["season"]].append(r["arms"][comp]["delta_weekly"])
        d = [r["arms"][comp]["delta"] for r in rows]
        out[comp] = {
            "picks_changed": sum(1 for r in rows if r["arms"][comp]["changed"]),
            "pair_flips_P_to_O": sum(1 for r in rows if r["arms"][comp]["pair_flips_to_O"]),
            "new_pick_is_oracle": sum(1 for r in rows if r["arms"][comp]["new_is_oracle"]),
            "new_pick_other": sum(
                1
                for r in rows
                if r["arms"][comp]["changed"] and not r["arms"][comp]["new_is_oracle"]
            ),
            "delta_per_state": mean(d) if d else None,
            "delta_sum": sum(d),
            "delta_season": season_ci({s: mean(v) for s, v in per_season.items()}),
            "delta_weekly_season": season_ci({s: mean(v) for s, v in per_season_wk.items()}),
            "regret_before": sum(r["regret"] for r in rows),
            "regret_after": sum(r["regret"] - r["arms"][comp]["delta"] for r in rows),
            "share_of_total_arm4_regret_recovered": 100 * sum(d) / total_arm4_regret
            if total_arm4_regret
            else None,
            "improved": sum(1 for x in d if x > 1e-9),
            "worsened": sum(1 for x in d if x < -1e-9),
        }
    return out


def value_decomposition(rows: list[dict]) -> dict:
    out = {}
    for term in ("msv", "da_vorp", "value_base"):
        gaps = [r["value_split_P"][term] - r["value_split_O"][term] for r in rows]
        disagree = [
            r
            for r, g in zip(rows, gaps, strict=True)
            if sign(g) != sign(r["onestep_P"] - r["onestep_O"]) and sign(g) != 0
        ]
        out[term] = {
            "prefers_P": sum(1 for g in gaps if g > 1e-9),
            "prefers_O": sum(1 for g in gaps if g < -1e-9),
            "tie": sum(1 for g in gaps if abs(g) <= 1e-9),
            "gap_P_minus_O": _stats(gaps),
            "disagrees_with_onestep": len(disagree),
            "regret_on_disagreement": sum(r["regret"] for r in disagree),
        }
    out["msv_equals_projection"] = {
        "P": sum(1 for r in rows if r["value_split_P"]["msv_equals_projection"]),
        "O": sum(1 for r in rows if r["value_split_O"]["msv_equals_projection"]),
        "both": sum(
            1
            for r in rows
            if r["value_split_P"]["msv_equals_projection"]
            and r["value_split_O"]["msv_equals_projection"]
        ),
        "n": len(rows),
    }
    out["projection_gap_P_minus_O"] = _stats([r["projection_P"] - r["projection_O"] for r in rows])
    # DA-VORP = projection - draft-aware level, so the level each player is measured against is
    # projection - DA-VORP. The gap (level_O - level_P) is how much of DA-VORP's preference comes
    # from the replacement construction rather than from the players' projections.
    out["draft_aware_level_gap_O_minus_P"] = _stats(
        [
            (r["projection_O"] - r["value_split_O"]["da_vorp"])
            - (r["projection_P"] - r["value_split_P"]["da_vorp"])
            for r in rows
        ]
    )
    out["by_flow"] = {
        f: {
            "n": len(fr),
            "value_base_prefers_P": sum(
                1 for r in fr if r["value_split_P"]["value_base"] > r["value_split_O"]["value_base"]
            ),
            "msv_prefers_P": sum(
                1 for r in fr if r["value_split_P"]["msv"] > r["value_split_O"]["msv"]
            ),
            "da_vorp_prefers_P": sum(
                1 for r in fr if r["value_split_P"]["da_vorp"] > r["value_split_O"]["da_vorp"]
            ),
            "projection_gap_P_minus_O": _stats([r["projection_P"] - r["projection_O"] for r in fr]),
            "P_msv_equals_projection": sum(
                1 for r in fr if r["value_split_P"]["msv_equals_projection"]
            ),
            "O_msv_equals_projection": sum(
                1 for r in fr if r["value_split_O"]["msv_equals_projection"]
            ),
            "msv_gap_P_minus_O": _stats(
                [r["value_split_P"]["msv"] - r["value_split_O"]["msv"] for r in fr]
            ),
            "da_vorp_gap_P_minus_O": _stats(
                [r["value_split_P"]["da_vorp"] - r["value_split_O"]["da_vorp"] for r in fr]
            ),
            "regret": sum(r["regret"] for r in fr),
            "level_gap_O_minus_P": _stats(
                [
                    (r["projection_O"] - r["value_split_O"]["da_vorp"])
                    - (r["projection_P"] - r["value_split_P"]["da_vorp"])
                    for r in fr
                ]
            ),
        }
        for f in sorted({r["flow"] for r in rows})
        for fr in [[r for r in rows if r["flow"] == f]]
    }
    return out


def classify(rows: list[dict]) -> dict:
    counts: dict = defaultdict(lambda: {"n": 0, "regret": 0.0})
    for r in rows:
        vp = sign(r["value_split_P"]["value_base"] - r["value_split_O"]["value_base"])
        flips = {c: r["arms"][c]["pair_flips_to_O"] for c in COMPONENTS}
        cls = score_gap_class(vp, r["shapley"], flips)
        r["class"] = cls
        counts[cls]["n"] += 1
        counts[cls]["regret"] += r["regret"]
    return dict(counts)


CATEGORY_OF_CLASS = {
    "1_large_value_disagreement": "A_value_construction",
    "2_small_value_amplified_by_other": "A_value_construction",
    "2_small_value_amplified_by_survival": "B_survival",
    "3_correct_value_overturned_by_survival": "B_survival",
    "4_correct_value_overturned_by_opp_cost": "C_opportunity_cost",
    "4_correct_value_overturned_by_fit": "D_roster_fit",
    "4_correct_value_overturned_by_risk": "E_risk",
    "4_correct_value_overturned_by_capacity": "F_capacity",
    "5_combination": "G_combination",
}


def report(rows_all: list[dict], totals: dict, repro: dict) -> dict:
    bar = "=" * 100
    summary: dict = {"reproduction": repro, "formats": {}}
    print(f"{bar}\nREPRODUCTION: {repro}\n{bar}")
    for league in FORMATS:
        rows = [r for r in rows_all if r["league"] == league]
        if not rows:
            continue
        total = totals[league]
        entry = summary["formats"].setdefault(league, {"total_arm4_regret": total})
        for group in ("PRIMARY", "CONTEXT"):
            grp = [r for r in rows if r["flow"].startswith(group)]
            ge = entry.setdefault(group, {})
            ge["n"] = len(grp)
            ge["regret"] = sum(r["regret"] for r in grp)
            ge["pct_of_arm4_regret"] = 100 * ge["regret"] / total if total else None
            ge["by_flow"] = {
                f: {"n": len(fr), "regret": sum(r["regret"] for r in fr)}
                for f in sorted({r["flow"] for r in grp})
                for fr in [[r for r in grp if r["flow"] == f]]
            }
            print(
                f"\n{bar}\n{league} {group}: {ge['n']} states, regret {ge['regret']:.0f} = "
                f"{ge['pct_of_arm4_regret']:.1f}% of ARM 4's total regret ({total:.0f}); "
                f"{ge['by_flow']}\n{bar}"
            )
            if not grp:
                continue
            ge["classes"] = classify(grp)
            ge["categories"] = defaultdict(lambda: {"n": 0, "regret": 0.0})
            for cls, v in ge["classes"].items():
                cat = CATEGORY_OF_CLASS[cls]
                ge["categories"][cat]["n"] += v["n"]
                ge["categories"][cat]["regret"] += v["regret"]
            ge["categories"] = dict(ge["categories"])
            ge["two_by_two"] = two_by_two(grp)
            ge["two_by_two_weekly"] = two_by_two(grp, weekly=True)
            ge["value_decomposition"] = value_decomposition(grp)
            ge["arms"] = arm_table(grp, total)
            ge["aligned_value_flips"] = {
                "n": sum(1 for r in grp if r["aligned_value_O_wins"]),
                "regret_on_flipped": sum(r["regret"] for r in grp if r["aligned_value_O_wins"]),
            }
            vp_o = [
                r
                for r in grp
                if sign(r["value_split_P"]["value_base"] - r["value_split_O"]["value_base"]) < 0
            ]
            vp_p = [r for r in grp if r not in vp_o]
            ge["q2"] = {
                "value_prefers_O_but_P_chosen": len(vp_o),
                "survival_neutral_flips_pair": sum(
                    1 for r in vp_o if r["arms"]["survival"]["pair_flips_to_O"]
                ),
                "survival_neutral_new_pick_is_O": sum(
                    1 for r in vp_o if r["arms"]["survival"]["new_is_oracle"]
                ),
                "survival_neutral_delta_on_these": sum(
                    r["arms"]["survival"]["delta"] for r in vp_o
                ),
                "survival_neutral_delta_weekly_on_these": sum(
                    r["arms"]["survival"]["delta_weekly"] for r in vp_o
                ),
                "regret_on_these": sum(r["regret"] for r in vp_o),
                "mean_survival_shapley_on_these": mean(r["shapley"]["survival"] for r in vp_o)
                if vp_o
                else None,
                "value_prefers_P": len(vp_p),
                "survival_reinforces_P": sum(1 for r in vp_p if r["shapley"]["survival"] > 1e-9),
                "survival_opposes_P": sum(1 for r in vp_p if r["shapley"]["survival"] < -1e-9),
            }
            shap_tot = {k: sum(r["shapley"][k] for r in grp) for k in D117.FACTORS}
            gap_tot = sum(shap_tot.values())
            ge["shapley_share"] = {k: v / gap_tot for k, v in shap_tot.items()} if gap_tot else {}
            for name, fn in (
                ("by_round", lambda r: r["round"]),
                ("by_season", lambda r: r["season"]),
                ("by_flow", lambda r: r["flow"]),
            ):
                g: dict = defaultdict(list)
                for r in grp:
                    g[str(fn(r))].append(r)
                ge[f"table_{name}"] = {
                    k: {
                        "n": len(v),
                        "regret": sum(r["regret"] for r in v),
                        "value_prefers_P": sum(
                            1
                            for r in v
                            if r["value_split_P"]["value_base"] > r["value_split_O"]["value_base"]
                        ),
                        "surv_neutral_flips": sum(
                            1 for r in v if r["arms"]["survival"]["pair_flips_to_O"]
                        ),
                        "surv_neutral_delta": sum(r["arms"]["survival"]["delta"] for r in v),
                        "classes": dict(
                            sorted(
                                {
                                    c: sum(1 for r in v if r["class"] == c)
                                    for c in {r["class"] for r in v}
                                }.items()
                            )
                        ),
                    }
                    for k, v in sorted(g.items())
                }
            _print_group(ge)
    return summary


def _print_group(ge: dict) -> None:
    print(f"  SCORE-GAP CLASSES: {json.dumps(ge['classes'])}")
    print(f"  CATEGORIES A-G: {json.dumps(ge['categories'])}")
    print("  Q1 2x2 (season-long one-step):")
    for cell, v in ge["two_by_two"].items():
        print(
            f"    {cell:<40} n {v['n']:>3} ({v['pct']:.0f}%) regret {v['regret']:8.1f} "
            f"score gap mean {v['score_gap']['mean']:+.1f} med {v['score_gap']['median']:+.1f} "
            f"value gap mean {v['value_gap']['mean']:+.1f} one-step gap mean "
            f"{v['onestep_gap']['mean']:+.1f} med {v['onestep_gap']['median']:+.1f}"
        )
    print("  Q1 2x2 (WEEKLY one-step):")
    for cell, v in ge["two_by_two_weekly"].items():
        print(f"    {cell:<40} n {v['n']:>3} ({v['pct']:.0f}%) regret {v['regret']:8.1f}")
    print(f"  Q2: {json.dumps(ge['q2'], default=str)}")
    print(
        f"  SHAPLEY SHARE of P-O score gap: {json.dumps({k: round(v, 3) for k, v in ge['shapley_share'].items()})}"
    )
    print("  NEUTRALISATION ARMS:")
    for comp, a in ge["arms"].items():
        ds, dw = a["delta_season"], a["delta_weekly_season"]
        print(
            f"    {comp:<9} changed {a['picks_changed']:>3} pairP->O {a['pair_flips_P_to_O']:>3} "
            f"new=O {a['new_pick_is_oracle']:>3} new=other {a['new_pick_other']:>3} | "
            f"improved {a['improved']} worsened {a['worsened']} | delta/state "
            f"{a['delta_per_state']:+.1f} season CI {ds['ci']} MDE {ds['mde']} | weekly "
            f"{dw['mean']} CI {dw['ci']} | recovered {a['share_of_total_arm4_regret_recovered']:+.2f}% "
            f"of ARM4 regret"
        )
    print(f"  VALUE DECOMPOSITION: {json.dumps(ge['value_decomposition'], default=str)}")
    print(f"  ORACLE-ALIGNED VALUE (pairwise): {ge['aligned_value_flips']}")
    for name in ("table_by_round", "table_by_season", "table_by_flow"):
        print(f"  {name.upper()}:")
        for k, v in ge[name].items():
            print(f"    {k:<16} {json.dumps(v)}")


def _src_tree() -> dict:
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()

    return {
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "src_tree_hash_at_head": run(["git", "rev-parse", "HEAD:src/alpha_squad"]),
        "src_dirty": bool(run(["git", "status", "--porcelain", "--", "src/alpha_squad"])),
    }


def _write(out: Path, name: str, payload) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    print(f"wrote {out / name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("measure", "report"))
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument("--d115", action="append", default=[])
    ap.add_argument("--d120", help="dir with d120_arms_*.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    assert_no_realized_inputs_in_policy()
    if DECISION_ARM_VORP_WEIGHT != 1.0:
        raise UnreconstructibleError("DA-VORP = value_base - MSV needs the shipped weight of 1.0")
    if SHIPPED_TIER in TIERS_ENFORCING_LEGALITY or L_TIER_SPEC[SHIPPED_TIER][1]:
        raise UnreconstructibleError(
            "the argmax re-ranking assumes the shipped tier has no legality rule"
        )
    if a.mode == "report":
        rows, totals, repro = [], {}, {"states_checked": 0, "arm4_pick_matches": 0}
        prov = {}
        for path in sorted(out.glob("d121_measured_*.json")):
            payload = json.loads(path.read_text())
            rows.extend(payload["rows"])
            totals.update(payload["arm4_total_regret"])
            for k in repro:
                repro[k] += payload["reproduction"][k]
            prov[path.name] = payload["provenance"]
        summary = report(rows, totals, repro)
        summary["provenance"] = prov
        _write(out, "d121_summary.json", summary)
        return
    con = duckdb.connect(a.db, read_only=True)
    vintage = compute_board_vintage(con)
    leagues = tuple(x for x in a.leagues.split(",") if x)
    d115 = D120.load_d115([Path(d) for d in a.d115], vintage.combined_hash)
    d120_rows, d120_hashes = {}, {}
    for path in sorted(Path(a.d120).glob("d120_arms_*.json")):
        payload = json.loads(path.read_text())
        if payload["provenance"]["board_vintage_combined"] != vintage.combined_hash:
            raise UnreconstructibleError(f"{path} is a different vintage")
        d120_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        d120_rows.update({_key(r): r for r in payload["rows"]})
    for lg in leagues:
        n = sum(1 for k in d120_rows if k[0] == lg)
        if n != 320:
            raise UnreconstructibleError(f"D120 has {n} states for {lg}, expected 320")
    rows, repro = run_measure(con, leagues, d115, d120_rows)
    totals = {
        lg: sum(
            r["oracle_rollout"] - r["arms"]["ARM4"]["rollout"]
            for k, r in d120_rows.items()
            if k[0] == lg
        )
        for lg in leagues
    }
    _write(
        out,
        f"d121_measured_{'_'.join(leagues)}.json",
        {
            "rows": rows,
            "reproduction": repro,
            "arm4_total_regret": totals,
            "provenance": {
                "board_vintage_combined": vintage.combined_hash,
                "board_vintage_per_season": {str(s): h for s, h in vintage.season_hashes.items()},
                "upstream_board_sha256": vintage.board_sha256,
                "upstream_idmap_sha256": vintage.idmap_sha256,
                "d115_inputs": d115["hashes"],
                "d120_inputs": d120_hashes,
                "argv": sys.argv,
                **_src_tree(),
            },
        },
    )


if __name__ == "__main__":
    main()
