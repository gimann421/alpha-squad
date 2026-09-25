"""D120 -- why does Alpha leave ~27% of the per-pick oracle value on the table even when it is
handed perfect projections?

Read-only research runner. Reuses D115's committed replay, rollout and regret artifacts, D103's
committed `oracle_static` (the ORACLE_Y1 arm), and D116/D117's committed score factorisation. It
writes nothing but JSON under `--out`. **No file under `src/alpha_squad/` is touched and this
script is imported by no production path.**

    uv run python scripts/research/d120_perfect_projection_gap.py --mode audit   --d115 <dir> --out <o>
    uv run python scripts/research/d120_perfect_projection_gap.py --mode weekly  --leagues <f> --d115 <dir> --out <o>
    uv run python scripts/research/d120_perfect_projection_gap.py --mode arms    --leagues <f> --d115 <dir> --out <o>
    uv run python scripts/research/d120_perfect_projection_gap.py --mode report  --out <o>

==========================================================================================
PRE-REGISTRATION -- written before any D120 number existed
==========================================================================================

THE QUESTION.  D115's ORACLE_Y1 (the shipped rule reading realized points as its projections)
recovers ~73% of per-pick oracle regret on this vintage (D118 re-run: 72.7% target / 74.4%
dynasty). If Alpha knew exactly how good every player would be, does its decision ARCHITECTURE
still choose worse, and why? **Diagnostic only. No weight tuned, no formula changed beyond the
mechanically necessary recomputation, no new information. Nothing ships.**

STEP 0 -- REPRODUCE BEFORE ANYTHING ELSE.  The existing ORACLE_Y1 arm is re-run at every one of
the 640 audited states through D103's unmodified `oracle_static` and D115's unmodified harness.
Its pick AND its one-step delta must equal D115's stored `d115_arms.json` rows exactly (delta to
1e-6). Any mismatch raises and no new arm runs.

STEP 1 -- THE INSTRUMENT AUDIT.  Every input the shipped L0 score reads, and whether ORACLE_Y1
updates it from the perfect projections:
  per-season (`SeasonStatic`)   projections, vorp, replacement_levels, scarcity_raw/norm,
                                confidence, consumption_demand, market_rank, ecr_dispersion,
                                availability_rates
  per-pick (inside `_pick_by_tier` / `score_candidate`)
                                draft-aware replacement levels, marginal starter value, starting-
                                lineup baseline, opportunity cost, roster fit, survival, risk,
                                feasibility cap
Measured, per season and format, by comparing ORACLE_Y1's static with a FULL rebuild
(`load_season_static(projections_override=realized)`): which fields differ, and by how much.
Confidence is recomputed with M6's own formula (below), because no static rebuild touches the
`uncertainty_predictions` table.

STEP 2 -- THE ARMS (diagnostic, not candidates):
  CONTROL  production Alpha (SHIPPED_TIER on the Y1 board)
  ARM 1    ORACLE_Y1 exactly as committed (D103 `oracle_static`)
  ARM 2    ARM 1 + `replacement_levels` recomputed from the perfect projections
           (`league/replacement.py::replacement_level`, the function `load_season_static` uses)
  ARM 3    ARM 1 + confidence recomputed from the perfect projections with M6's OWN construction:
           the player's interval offsets (p10 - point, p90 - point) are kept -- they are M6's
           calibrated per-(season, position) constants -- and `confidence_from_interval_width`
           is re-evaluated at the new point. Players with no M6 row keep the shipped 0.7
           fallback. (Setting confidence to 1.0 "because information is perfect" would be a RULE
           change; it is not done.)
  ARM 4    ARM 1 + both recomputations
  ARM 4F   AUDIT CHECK, not an arm: a FULL static rebuild from the perfect projections plus ARM
           3's confidence. If ARM 4F picks exactly what ARM 4 picks at every state, no other
           stale projection-dependent input matters to the decision.
Each arm's board is used only to CHOOSE the pick at each audited production state; the pick is
scored by D115's common continuation (the shipped policy on the Y1 board), exactly as D115's
arms were, so ARM 1's numbers reproduce D115's.

MEASURES, per arm and format (target PRIMARY, dynasty replication, never pooled):
  one-step delta vs control, season-long (D115's scorer) and WEEKLY (`WEEKLY_NO_FORESIGHT`, the
  lineup set weekly by Y1's projections among actual participants -- the D106 objective);
  oracle gap recovered = mean delta / mean per-pick regret (weekly uses a weekly per-pick oracle,
  produced here by `audit_draft(objective=WEEKLY_NO_FORESIGHT)` on the identical grid);
  per-pick regret of the arm = oracle rollout - arm rollout; changed-pick rate vs control and vs
  ARM 1; by round, by position, by season; season-clustered 95% CI with k = 5 and its own MDE
  (the CI half-width, D114's convention). Every season has perfect information, so k = 5.

DECOMPOSITION (not assumed additive).  With R(x) = recovery of arm x:
  stale replacement effect  R(2) - R(1)
  stale risk effect         R(3) - R(1)
  interaction               R(4) - R(2) - R(3) + R(1)
  other decision residual   1 - R(4)
Each difference is also measured PAIRED per pick (delta_x - delta_1) with a season-clustered CI.

RESIDUAL ATTRIBUTION under the internally consistent arm (ARM 4), existing categories only:
  wrong position vs right position (D115's A/B on the arm's pick vs the per-pick oracle's);
  sequencing (D115/D116's C1 and C2, recomputed for the arm's pick with D115's own
  `survives_counterfactual`); and the score factors -- value, opportunity cost, roster fit, risk,
  survival, capacity -- via D117's exact Shapley split of the arm's score gap between its pick
  and the oracle's player, on the ARM 4 board.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
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
    WEEKLY_NO_FORESIGHT,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    make_roster_scorer,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.replacement import replacement_level
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.conformal import confidence_from_interval_width
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
DEFAULT_SLOTS = (1, 4, 7, 10)
ARMS = ("ARM1", "ARM2", "ARM3", "ARM4")
AUDIT_ARM = "ARM4F"
T_CRIT_K5 = 2.776
REPRO_TOLERANCE = 1e-6


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D117 = _load("d117_upside_audit")
D116 = D117.D116
D115 = D116.D115
D103 = D115.D103


class UnreconstructibleError(RuntimeError):
    """D120 stops rather than substituting."""


# --------------------------------------------------------------------------------------------
# The arms' boards
# --------------------------------------------------------------------------------------------
def load_m6_intervals(con, season: int) -> dict[str, tuple[float, float, float]]:
    rows = con.execute(
        "SELECT player_id, point_prediction, p10, p90 FROM uncertainty_predictions "
        "WHERE season = ? AND model_version = ? AND confidence IS NOT NULL",
        [season, UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def recomputed_confidence(
    projections: dict[str, float], intervals: dict[str, tuple[float, float, float]]
) -> dict[str, float]:
    """M6's own confidence, re-evaluated at the new point with M6's own interval offsets. Only
    players M6 covers get a value -- exactly the set the shipped `static.confidence` covers --
    so everyone else keeps the shipped 0.7 fallback."""
    out = {}
    for pid, (point, p10, p90) in intervals.items():
        if pid not in projections:
            continue
        new = projections[pid]
        out[pid] = confidence_from_interval_width(new, new + (p10 - point), new + (p90 - point))
    return out


def arm_statics(con, league, season, static) -> dict:
    """{arm: SeasonStatic}. ARM 1 is D103's committed construction, untouched."""
    arm1 = D103.oracle_static(con, league, season, static)
    levels = replacement_level(league, arm1.projections, arm1.positions)
    conf = recomputed_confidence(arm1.projections, load_m6_intervals(con, season))
    series = resolve_market_series(league)
    full = load_season_static(
        con,
        league,
        season,
        page_type=preseason_page_type(con, series.ecr_type, season),
        projections_override=dict(arm1.projections),
    )
    return {
        "ARM1": arm1,
        "ARM2": dataclasses.replace(arm1, replacement_levels=levels),
        "ARM3": dataclasses.replace(arm1, confidence=conf),
        "ARM4": dataclasses.replace(arm1, replacement_levels=levels, confidence=conf),
        AUDIT_ARM: dataclasses.replace(full, confidence=conf),
    }


def _diff_map(a: dict, b: dict, tol: float = 1e-9) -> dict:
    keys = set(a) | set(b)
    diffs = [
        abs((a.get(k) or 0.0) - (b.get(k) or 0.0))
        for k in keys
        if not isinstance(a.get(k), tuple) and not isinstance(b.get(k), tuple)
    ]
    changed = [d for d in diffs if d > tol]
    return {
        "n": len(keys),
        "n_changed": len(changed),
        "max_abs_change": max(changed) if changed else 0.0,
        "mean_abs_change_when_changed": mean(changed) if changed else 0.0,
    }


def audit_fields(control, arms: dict) -> dict:
    """Which static fields ARM 1 leaves at their Y1 values, measured against the full rebuild."""
    a1, full = arms["ARM1"], arms[AUDIT_ARM]
    fields = {}
    for name in (
        "projections",
        "vorp",
        "replacement_levels",
        "scarcity_raw",
        "scarcity_norm",
        "confidence",
        "consumption_demand",
        "availability_rates",
    ):
        fields[name] = {
            "arm1_vs_control": _diff_map(getattr(a1, name), getattr(control, name)),
            "full_rebuild_vs_arm1": _diff_map(getattr(full, name), getattr(a1, name)),
        }
    fields["market_rank"] = {
        "identical_all_three": control.market_rank == a1.market_rank == full.market_rank
    }
    fields["ecr_dispersion"] = {
        "identical_all_three": control.ecr_dispersion == a1.ecr_dispersion == full.ecr_dispersion
    }
    fields["replacement_levels_values"] = {
        "control": control.replacement_levels,
        "arm1_stale": a1.replacement_levels,
        "recomputed": arms["ARM2"].replacement_levels,
    }
    conf_old, conf_new = a1.confidence, arms["ARM3"].confidence
    common = [p for p in conf_old if p in conf_new]
    fields["confidence_detail"] = {
        "n_players": len(common),
        "n_zero_stale": sum(1 for p in common if conf_old[p] == 0.0),
        "n_zero_recomputed": sum(1 for p in common if conf_new[p] == 0.0),
        "mean_stale": mean(conf_old[p] for p in common) if common else None,
        "mean_recomputed": mean(conf_new[p] for p in common) if common else None,
    }
    return fields


# --------------------------------------------------------------------------------------------
# Loading D115's artifacts
# --------------------------------------------------------------------------------------------
def _key(r) -> tuple:
    return (r["league"], r["season"], r["slot"], r["overall_pick"])


def load_d115(d115_dirs: list[Path], vintage: str) -> dict:
    regret, timing, arms, hashes = {}, {}, [], {}
    for d in d115_dirs:
        for name in ("d115_regret.json", "d115_timing.json", "d115_arms.json"):
            path = d / name
            payload = json.loads(path.read_text())
            if payload["provenance"]["board_vintage_combined"] != vintage:
                raise UnreconstructibleError(f"{path} is a different vintage from the database")
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            if name == "d115_regret.json":
                regret.update({_key(r): r for r in payload["rows"]})
            elif name == "d115_timing.json":
                timing.update({_key(r): r for r in payload["rows"]})
            else:
                arms.extend(payload["rows"])
    return {"regret": regret, "timing": timing, "arms": arms, "hashes": hashes}


# --------------------------------------------------------------------------------------------
# MODE: weekly -- the per-pick oracle under the weekly objective, on the identical grid
# --------------------------------------------------------------------------------------------
def run_weekly(con, leagues, slots, regret: dict) -> list[dict]:
    rows = []
    t0 = time.time()
    for league_name in leagues:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            for slot in slots:
                audited = audit_draft(
                    con, league, season, slot, static, objective=WEEKLY_NO_FORESIGHT, weekly=weekly
                )
                for rec in audited:
                    key = (league_name, season, slot, rec.pick_overall)
                    base = regret.get(key)
                    if base is None or base["alpha_player"] != rec.alpha.player_id:
                        raise UnreconstructibleError(
                            f"weekly audit walked a different draft at {key}"
                        )
                    rows.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "overall_pick": rec.pick_overall,
                            "alpha_player": rec.alpha.player_id,
                            "alpha_rollout_weekly": rec.alpha.rollout_starter_points,
                            "oracle_player_weekly": rec.oracle.player_id,
                            "oracle_rollout_weekly": rec.oracle.rollout_starter_points,
                            "regret_weekly": rec.regret,
                        }
                    )
                print(
                    f"  weekly {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows


# --------------------------------------------------------------------------------------------
# MODE: arms
# --------------------------------------------------------------------------------------------
def _candidate(c) -> dict:
    return D116._candidate_dict(c)


def rollout_pair(ctx: tuple, pick: str, cache: dict) -> tuple[float, float]:
    """(season-long, weekly) one-step rollout value of taking `pick` at this state, memoised per
    state. Module level and fully parameterised -- a closure over loop variables is the classic
    late-binding bug this repository has recorded before."""
    if pick not in cache:
        con, league, season, static, slot, state, realized, sl_scorer, wk_scorer = ctx
        cache[pick] = tuple(
            D115.roll_from_state(con, league, season, static, slot, state, pick, realized, scorer)
            for scorer in (sl_scorer, wk_scorer)
        )
    return cache[pick]


def run_arms(con, leagues, slots, d115: dict) -> list[dict]:
    # D115's arms rows carry no overall_pick; they are stored in replay order per draft, so they
    # are indexed by order and the round is asserted per state.
    by_draft: dict = defaultdict(list)
    for r in d115["arms"]:
        if r["arm"] == "ORACLE_Y1":
            by_draft[(r["league"], r["season"], r["slot"])].append(r)
    out = []
    t0 = time.time()
    for league_name in leagues:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            arms = arm_statics(con, league, season, static)
            realized = _actual_points_for(con, season, sorted(static.projections))
            sl_scorer = make_roster_scorer(SEASON_LONG, league, static)
            wk_scorer = make_roster_scorer(
                WEEKLY_NO_FORESIGHT, league, static, load_weekly_points(con, season)
            )
            for slot in slots:
                states = D115.replay_states(con, league, season, static, slot)
                stored = by_draft[(league_name, season, slot)]
                if len(stored) != len(states):
                    raise UnreconstructibleError(
                        f"D115 ORACLE_Y1 has {len(stored)} rows, replay {len(states)} states"
                    )
                for i, state in enumerate(states):
                    key = (league_name, season, slot, state["overall_pick"])
                    reg = d115["regret"][key]
                    tim = d115["timing"][key]
                    if reg["alpha_player"] != state["alpha_pick"]:
                        raise UnreconstructibleError(f"replay diverges from D115 at {key}")
                    cache: dict[str, tuple[float, float]] = {}
                    ctx = (con, league, season, static, slot, state, realized, sl_scorer, wk_scorer)
                    base_sl, base_wk = rollout_pair(ctx, state["alpha_pick"], cache)
                    if abs(base_sl - reg["alpha_rollout"]) > REPRO_TOLERANCE:
                        raise UnreconstructibleError(f"control rollout != D115's at {key}")
                    row = {
                        "league": league_name,
                        "season": season,
                        "slot": slot,
                        "round": state["round"],
                        "phase": D115._phase_of(state["round"]),
                        "overall_pick": state["overall_pick"],
                        "is_last_pick": i + 1 >= len(states),
                        "alpha_pick": state["alpha_pick"],
                        "alpha_position": static.positions.get(state["alpha_pick"], "UNKNOWN"),
                        "oracle_player": reg["oracle_player"],
                        "oracle_position": reg["oracle_position"],
                        "oracle_rollout": reg["oracle_rollout"],
                        "regret_roster": reg["regret_roster"],
                        "alpha_rollout": base_sl,
                        "alpha_rollout_weekly": base_wk,
                        "oracle_rollout_weekly": None,  # joined from the weekly audit in report
                        "regret_weekly": None,
                        "C1_alpha": tim["C1_oracle_survives_to_next_pick"],
                        "C2_alpha": tim["C2_alpha_survives_if_oracle_taken"],
                        "arms": {},
                    }
                    scored_by_arm = {}
                    for arm in (*ARMS, AUDIT_ARM):
                        pick, scored = _pick_by_tier(
                            arms[arm],
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
                        scored_by_arm[arm] = scored
                        sl, wkv = rollout_pair(ctx, pick, cache)
                        row["arms"][arm] = {
                            "pick": pick,
                            "position": static.positions.get(pick, "UNKNOWN"),
                            "changed": pick != state["alpha_pick"],
                            "delta": sl - base_sl,
                            "delta_weekly": wkv - base_wk,
                            "rollout": sl,
                            "rollout_weekly": wkv,
                        }
                    # STEP 0: ARM 1 must reproduce D115's stored ORACLE_Y1 exactly.
                    s = stored[i]
                    if s["round"] != state["round"]:
                        raise UnreconstructibleError(f"D115 arms rows out of order at {key}")
                    a1 = row["arms"]["ARM1"]
                    if (
                        s["arm_pick"] != a1["pick"]
                        or abs(s["delta"] - a1["delta"]) > REPRO_TOLERANCE
                    ):
                        raise UnreconstructibleError(
                            f"ARM 1 does not reproduce D115's ORACLE_Y1 at {key}: stored "
                            f"{s['arm_pick']} {s['delta']:+.6f}, re-run {a1['pick']} "
                            f"{a1['delta']:+.6f} -- STOP, no new arm is interpretable"
                        )
                    # Score-level effect of each stale input, on ARM 1's top-10.
                    top = [c.player_id for c in scored_by_arm["ARM1"][:10]]
                    for arm in ("ARM2", "ARM3", "ARM4"):
                        s1 = {c.player_id: c.score for c in scored_by_arm["ARM1"]}
                        sx = {c.player_id: c.score for c in scored_by_arm[arm]}
                        rel = [
                            abs(sx[p] - s1[p]) / abs(s1[p])
                            for p in top
                            if p in sx and s1.get(p) not in (None, 0.0)
                        ]
                        row["arms"][arm]["mean_rel_score_change_top10"] = mean(rel) if rel else 0.0
                    # Residual attribution under ARM 4 (internally consistent).
                    p4, o = row["arms"]["ARM4"]["pick"], reg["oracle_player"]
                    attr = {"arm4_pick_is_oracle": p4 == o}
                    if p4 != o:
                        cands = {c.player_id: _candidate(c) for c in scored_by_arm["ARM4"]}
                        if p4 in cands and o in cands:
                            fp = D117.factors_from(cands[p4])
                            fo = D117.factors_from(cands[o])
                            attr["shapley_P_minus_O"] = D117.shapley(fp, fo)
                            attr["score_gap"] = D117.l0_score(fp) - D117.l0_score(fo)
                            attr["legality_override"] = scored_by_arm["ARM4"][0].player_id != p4
                        if state["next_pick"] is not None:
                            attr["C1"] = D115.survives_counterfactual(
                                con, league, season, static, slot, state, p4, o
                            )
                            attr["C2"] = D115.survives_counterfactual(
                                con, league, season, static, slot, state, o, p4
                            )
                    row["arm4_attribution"] = attr
                    out.append(row)
                print(
                    f"  arms {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return out


# --------------------------------------------------------------------------------------------
# MODE: audit -- fields and structure, no rollouts
# --------------------------------------------------------------------------------------------
def run_audit(con) -> dict:
    out = {}
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            arms = arm_statics(con, league, season, static)
            out[f"{league_name}|{season}"] = audit_fields(static, arms)
    return out


# --------------------------------------------------------------------------------------------
# Statistics and report
# --------------------------------------------------------------------------------------------
def season_ci(values: dict) -> dict:
    vals = [v for v in values.values() if v is not None]
    k = len(vals)
    if k < 2:
        return {"k": k, "mean": vals[0] if vals else None, "ci": None, "mde": None}
    md, se = mean(vals), stdev(vals) / math.sqrt(k)
    t = T_CRIT_K5 if k == 5 else {4: 3.182, 3: 4.303}.get(k, 2.0)
    return {"k": k, "mean": md, "ci": (md - t * se, md + t * se), "mde": t * se}


def _per_season(rows, fn) -> dict:
    g: dict = defaultdict(list)
    for r in rows:
        v = fn(r)
        if v is not None:
            g[r["season"]].append(v)
    return {s: mean(v) for s, v in sorted(g.items())}


def arm_summary(rows: list[dict], arm: str) -> dict:
    def d(r):
        return r["arms"][arm]["delta"]

    def dw(r):
        return r["arms"][arm]["delta_weekly"]

    regret = sum(r["regret_roster"] for r in rows)
    wk_rows = [r for r in rows if r["regret_weekly"] is not None]
    regret_wk = sum(r["regret_weekly"] for r in wk_rows)
    return {
        "n": len(rows),
        "delta": season_ci(_per_season(rows, d)),
        "delta_weekly": season_ci(_per_season(rows, dw)),
        "recovery": sum(d(r) for r in rows) / regret if regret else None,
        "recovery_by_season": {
            s: sum(d(r) for r in rows if r["season"] == s)
            / sum(r["regret_roster"] for r in rows if r["season"] == s)
            for s in BACKTEST_SEASONS
            if any(r["season"] == s for r in rows)
        },
        "recovery_weekly": sum(dw(r) for r in wk_rows) / regret_wk if regret_wk else None,
        "per_pick_regret": season_ci(
            _per_season(rows, lambda r: r["oracle_rollout"] - r["arms"][arm]["rollout"])
        ),
        "per_pick_regret_weekly": season_ci(
            _per_season(
                wk_rows, lambda r: r["oracle_rollout_weekly"] - r["arms"][arm]["rollout_weekly"]
            )
        ),
        "negative_regret_picks": sum(
            1 for r in rows if r["oracle_rollout"] - r["arms"][arm]["rollout"] < -1e-9
        ),
        "changed_vs_control": mean(float(r["arms"][arm]["changed"]) for r in rows),
        "changed_vs_arm1": mean(
            float(r["arms"][arm]["pick"] != r["arms"]["ARM1"]["pick"]) for r in rows
        ),
        "picks_equal_oracle": mean(
            float(r["arms"][arm]["pick"] == r["oracle_player"]) for r in rows
        ),
        "mean_rel_score_change_top10": mean(
            r["arms"][arm].get("mean_rel_score_change_top10", 0.0) for r in rows
        ),
    }


def paired_difference(rows, arm_x: str, arm_y: str, weekly: bool = False) -> dict:
    field = "delta_weekly" if weekly else "delta"
    return season_ci(_per_season(rows, lambda r: r["arms"][arm_x][field] - r["arms"][arm_y][field]))


def decompose(summ: dict) -> dict:
    r1, r2, r3, r4 = (summ[a]["recovery"] for a in ARMS)
    return {
        "residual_arm1": 1 - r1,
        "stale_replacement_effect": r2 - r1,
        "stale_risk_effect": r3 - r1,
        "interaction": r4 - r2 - r3 + r1,
        "other_decision_residual": 1 - r4,
    }


def breakdown(rows, key_fn, arm: str) -> dict:
    groups: dict = defaultdict(list)
    for r in rows:
        groups[str(key_fn(r))].append(r)
    out = {}
    for k in sorted(groups, key=lambda x: (len(x), x)):
        g = groups[k]
        reg = sum(r["regret_roster"] for r in g)
        out[k] = {
            "n": len(g),
            "regret": reg,
            "arm_delta_mean": mean(r["arms"][arm]["delta"] for r in g),
            "recovery": sum(r["arms"][arm]["delta"] for r in g) / reg if reg else None,
            "arm_regret_mean": mean(r["oracle_rollout"] - r["arms"][arm]["rollout"] for r in g),
            "changed": mean(float(r["arms"][arm]["changed"]) for r in g),
        }
    return out


def residual_attribution(rows: list[dict]) -> dict:
    """Where ARM 4 (internally consistent perfect projections) still loses to the per-pick
    oracle -- existing categories only."""

    def arm_regret(r):
        return r["oracle_rollout"] - r["arms"]["ARM4"]["rollout"]

    total = sum(arm_regret(r) for r in rows)
    miss = [r for r in rows if not r["arm4_attribution"]["arm4_pick_is_oracle"]]
    same = [r for r in miss if r["arms"]["ARM4"]["position"] == r["oracle_position"]]
    diff = [r for r in miss if r["arms"]["ARM4"]["position"] != r["oracle_position"]]
    seq = [r for r in miss if r["arm4_attribution"].get("C1") and r["arm4_attribution"].get("C2")]
    shap = [r for r in miss if "shapley_P_minus_O" in r["arm4_attribution"]]
    factors = {}
    for f in D117.FACTORS:
        vals = [r["arm4_attribution"]["shapley_P_minus_O"][f] for r in shap]
        gap = sum(r["arm4_attribution"]["score_gap"] for r in shap)
        factors[f] = {
            "mean_contribution": mean(vals) if vals else None,
            "share_of_score_gap": sum(vals) / gap if gap else None,
            "favors_arm_pick": sum(1 for v in vals if v > 1e-12),
            "favors_oracle": sum(1 for v in vals if v < -1e-12),
        }

    def pct(rs):
        return 100 * sum(arm_regret(r) for r in rs) / total if total else None

    flows: dict = defaultdict(lambda: {"n": 0, "regret": 0.0})
    for r in miss:
        f = flows[f"{r['arms']['ARM4']['position']}->{r['oracle_position']}"]
        f["n"] += 1
        f["regret"] += arm_regret(r)
    by_phase = {
        ph: {
            "n": sum(1 for r in rows if r["phase"] == ph),
            "pct_regret": pct([r for r in rows if r["phase"] == ph]),
        }
        for ph in sorted({r["phase"] for r in rows})
    }
    return {
        "flows_arm_pick_to_oracle": {
            k: {**v, "pct_regret": 100 * v["regret"] / total if total else None}
            for k, v in sorted(flows.items(), key=lambda kv: -kv[1]["regret"])
        },
        "by_phase": by_phase,
        "n": len(rows),
        "total_arm_regret": total,
        "arm_equals_oracle": len(rows) - len(miss),
        "A_right_position_wrong_player": {"n": len(same), "pct_regret": pct(same)},
        "B_wrong_position": {"n": len(diff), "pct_regret": pct(diff)},
        "C1_and_C2_sequencing_overlay": {"n": len(seq), "pct_regret": pct(seq)},
        "shapley_factors": factors,
        "n_decomposed": len(shap),
        "legality_override": sum(1 for r in shap if r["arm4_attribution"].get("legality_override")),
    }


def join_weekly(rows: list[dict], weekly: dict) -> None:
    """Attach the weekly per-pick oracle, and CHECK that the arms run and the weekly audit scored
    the control pick identically (they are two independent walks of the same draft)."""
    for r in rows:
        wk = weekly.get(_key(r))
        if wk is None:
            continue
        if abs(wk["alpha_rollout_weekly"] - r["alpha_rollout_weekly"]) > REPRO_TOLERANCE:
            raise UnreconstructibleError(f"weekly control rollout disagrees at {_key(r)}")
        r["oracle_rollout_weekly"] = wk["oracle_rollout_weekly"]
        r["regret_weekly"] = wk["regret_weekly"]


def report(rows_all: list[dict], audit: dict) -> dict:
    bar = "=" * 100
    summary: dict = {"formats": {}, "audit": audit}
    print(f"{bar}\nINSTRUMENT AUDIT (ARM 1 static vs control, and full rebuild vs ARM 1)\n{bar}")
    for k, fields in audit.items():
        line = []
        for name in (
            "vorp",
            "replacement_levels",
            "scarcity_raw",
            "confidence",
            "consumption_demand",
        ):
            f = fields[name]
            line.append(
                f"{name}: A1-ctl {f['arm1_vs_control']['n_changed']}/{f['arm1_vs_control']['n']} "
                f"full-A1 {f['full_rebuild_vs_arm1']['n_changed']}"
            )
        print(f"  {k:<22} " + " | ".join(line))
        cd = fields["confidence_detail"]
        print(
            f"      confidence zeros stale {cd['n_zero_stale']} -> recomputed "
            f"{cd['n_zero_recomputed']} of {cd['n_players']}; mean {cd['mean_stale']:.3f} -> "
            f"{cd['mean_recomputed']:.3f}; market_rank identical "
            f"{fields['market_rank']['identical_all_three']}"
        )
    for league in FORMATS:
        rows = [r for r in rows_all if r["league"] == league]
        if not rows:
            continue
        entry = summary["formats"].setdefault(league, {})
        print(f"\n{bar}\n{league}: {len(rows)} audited picks\n{bar}")
        summ = {a: arm_summary(rows, a) for a in (*ARMS, AUDIT_ARM)}
        entry["arms"] = summ
        for a, s in summ.items():
            d, dw, rg = s["delta"], s["delta_weekly"], s["per_pick_regret"]
            print(
                f"  {a:<6} delta/pick {d['mean']:+7.2f} CI {tuple(round(x, 1) for x in d['ci'])} "
                f"MDE {d['mde']:.1f} | recovery {s['recovery']:.1%} | weekly delta "
                f"{dw['mean']:+.2f} rec {s['recovery_weekly'] if s['recovery_weekly'] is None else format(s['recovery_weekly'], '.1%')}"
                f" | regret/pick {rg['mean']:.1f} | changed vs ctl {s['changed_vs_control']:.1%} "
                f"vs A1 {s['changed_vs_arm1']:.1%} | =oracle {s['picks_equal_oracle']:.1%} | "
                f"rel score chg {s['mean_rel_score_change_top10']:.4f} | neg regret "
                f"{s['negative_regret_picks']}"
            )
        entry["arm4_vs_arm4full_pick_mismatches"] = sum(
            1 for r in rows if r["arms"]["ARM4"]["pick"] != r["arms"][AUDIT_ARM]["pick"]
        )
        print(
            f"  ARM4 vs ARM4F (full rebuild) pick mismatches: {entry['arm4_vs_arm4full_pick_mismatches']}"
        )
        entry["decomposition"] = decompose(summ)
        entry["paired"] = {
            f"{x}-{y}": paired_difference(rows, x, y)
            for x, y in (("ARM2", "ARM1"), ("ARM3", "ARM1"), ("ARM4", "ARM1"), ("ARM4", "ARM3"))
        }
        entry["paired_weekly"] = {
            f"{x}-{y}": paired_difference(rows, x, y, weekly=True)
            for x, y in (("ARM2", "ARM1"), ("ARM3", "ARM1"), ("ARM4", "ARM1"))
        }
        print(f"  DECOMPOSITION: {json.dumps(entry['decomposition'], default=str)}")
        for k, v in entry["paired"].items():
            print(f"    paired {k}: mean {v['mean']:+.2f} CI {v['ci']} MDE {v['mde']}")
        for k, v in entry["paired_weekly"].items():
            print(f"    paired WEEKLY {k}: mean {v['mean']:+.2f} CI {v['ci']}")
        for name, fn in (
            ("by_round", lambda r: r["round"]),
            ("by_phase", lambda r: r["phase"]),
            ("by_season", lambda r: r["season"]),
            ("by_arm4_pick_position", lambda r: r["arms"]["ARM4"]["position"]),
            ("by_oracle_position", lambda r: r["oracle_position"]),
        ):
            entry[name] = {a: breakdown(rows, fn, a) for a in ("ARM1", "ARM4")}
            print(f"\n  {name.upper()} (ARM1 | ARM4): n, recovery, arm regret/pick")
            for k in entry[name]["ARM1"]:
                b1, b4 = entry[name]["ARM1"][k], entry[name]["ARM4"][k]

                def f(x):
                    return "  --" if x is None else f"{x:6.1%}"

                print(
                    f"    {k:<8}{b1['n']:>4}  A1 {f(b1['recovery'])} {b1['arm_regret_mean']:7.1f} | "
                    f"A4 {f(b4['recovery'])} {b4['arm_regret_mean']:7.1f}"
                )
        entry["residual_attribution_arm4"] = residual_attribution(rows)
        ra = entry["residual_attribution_arm4"]
        print(
            f"\n  RESIDUAL ATTRIBUTION (ARM 4): {json.dumps({k: v for k, v in ra.items() if k != 'shapley_factors'}, default=str)}"
        )
        for f, v in ra["shapley_factors"].items():
            print(f"    {f:<10} {json.dumps(v, default=str)}")
    return summary


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
    ap.add_argument("--mode", required=True, choices=("audit", "weekly", "arms", "report"))
    ap.add_argument("--d115", action="append", default=[], help="dirs with D115 artifacts")
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument("--slots", default=",".join(map(str, DEFAULT_SLOTS)))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    leagues = tuple(x for x in a.leagues.split(",") if x)
    slots = tuple(int(s) for s in a.slots.split(","))
    assert_no_realized_inputs_in_policy()
    if a.mode == "report":
        rows = []
        for path in sorted(out.glob("d120_arms_*.json")):
            rows.extend(json.loads(path.read_text())["rows"])
        weekly: dict = {}
        for path in sorted(out.glob("d120_weekly_*.json")):
            weekly.update({_key(r): r for r in json.loads(path.read_text())["rows"]})
        join_weekly(rows, weekly)
        audit = json.loads((out / "d120_audit.json").read_text())
        summary = report(rows, audit["fields"])
        summary["provenance"] = {
            p.name: json.loads(p.read_text())["provenance"] for p in sorted(out.glob("d120_*.json"))
        }
        _write(out, "d120_summary.json", summary)
        return
    con = duckdb.connect(a.db, read_only=True)
    vintage = compute_board_vintage(con)
    prov = {
        "board_vintage_combined": vintage.combined_hash,
        "board_vintage_per_season": {str(s): h for s, h in vintage.season_hashes.items()},
        "upstream_board_sha256": vintage.board_sha256,
        "upstream_idmap_sha256": vintage.idmap_sha256,
        "argv": sys.argv,
        **_src_tree(),
    }
    if a.mode == "audit":
        _write(out, "d120_audit.json", {"fields": run_audit(con), "provenance": prov})
        return
    d115 = load_d115([Path(d) for d in a.d115], vintage.combined_hash)
    prov["d115_inputs"] = d115["hashes"]
    tag = "_".join(leagues)
    if a.mode == "weekly":
        rows = run_weekly(con, leagues, slots, d115["regret"])
        _write(out, f"d120_weekly_{tag}.json", {"rows": rows, "provenance": prov})
        return
    rows = run_arms(con, leagues, slots, d115)
    _write(out, f"d120_arms_{tag}.json", {"rows": rows, "provenance": prov})


if __name__ == "__main__":
    main()
