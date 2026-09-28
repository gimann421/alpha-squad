"""D122 -- does the shipped MSV over-credit filling an EMPTY starting slot, because it ignores the
player the fixed continuation would have started in that slot anyway?

Read-only research runner. Starts from D120's corrected perfect-projection arm (ARM 4) exactly as
D121 did: the same 640 production pick states (D115's replay), the shipped `_pick_by_tier` re-asked
on the ARM 4 board, and D115's common one-step continuation (`roll_from_state`, the shipped L0
policy on the Y1 board against the fixed market opponents). It writes nothing but JSON under
`--out`. **No file under `src/alpha_squad/` is touched and this script is imported by no
production path.**

    uv run python scripts/research/d122_continuation_aware_msv.py --mode measure \
        --leagues <f> --d115 <dir> --d120 <dir> --d121 <dir> --out <o>
    uv run python scripts/research/d122_continuation_aware_msv.py --mode report --out <o>

==========================================================================================
PRE-REGISTRATION -- written before any D122 number existed
==========================================================================================

REPRODUCTION (stop conditions; any mismatch raises, nothing is substituted)
  1. ARM 4's pick recomputed at all 640 states (320 per format) equals D120's stored pick.
  2. The D121 primary population (rounds 1-6, RB->WR and RB->QB) is recovered state-for-state,
     and at every one of its states P, O, the six score factors, MSV, DA-VORP and the season-long
     and weekly one-step values equal D121's stored numbers to 1e-6.
  3. At every state the ARM 4 pick's one-step value equals D120's stored ARM 4 rollout, and the
     oracle's equals D115's stored oracle rollout, to 1e-6.
  4. The engine's MSV for P and O is recomputed with `league.replacement.marginal_starter_value`
     on the ARM 4 board and must match to 1e-6.
  5. The best-lineup value of every captured final roster, computed with the ARM 4 projections
     (which ARE realized points -- asserted), equals the season-long scorer's value to 1e-6. This
     is what ties the continuation-aware quantity to D115's one-step value without a second
     scoring implementation.

CAPTURING THE CONTINUATION, WITHOUT A SECOND IMPLEMENTATION
  `draft_oracle.rollout` returns only a score. The final roster is captured by wrapping the
  shipped season-long scorer (`make_roster_scorer(SEASON_LONG, ...)`) in a function that records
  the roster it is asked to score and then delegates. The draft itself is the unmodified
  production rollout; the policy never sees the wrapper (it is called after the last pick).

DEFINITIONS, fixed now
  * P = ARM 4's pick; O = the D115/D120 per-pick oracle (slate maximiser of one-step value).
  * F_c = the final 16-man roster the fixed continuation produces after taking candidate c here.
  * BL(R) = `best_lineup_points(league, R, ARM4 projections)` (production; teams=1 allocator).
  * MSV(c) = the shipped value: BL(roster_now + c) - BL(roster_now).
  * CONTINUATION-AWARE MSV (the brief's diagnostic, leave-one-out on the continuation's roster):
        CA(c) = BL(F_c) - BL(F_c minus c)
    i.e. the lineup value WITH c minus the lineup value when the continuation's eventual
    replacement for c's slot (the one bench player who enters, possibly through a FLEX reshuffle)
    plays instead. Exactly one player can enter (one slot frees); he is recorded with his id,
    position, projection, realized points, the slot he takes, and his ORIGIN: already rostered at
    this state (redundancy with a rostered player) or drafted later by the continuation.
    The same leave-one-out is computed on the weekly no-foresight scorer (CA_weekly).
  * EXACT IDENTITY (asserted per state): V(F_P) - V(F_O) = [CA(P) - CA(O)] + [BL(F_P - P) -
    BL(F_O - O)]. The CA gap is therefore PART of the one-step gap by construction; its agreement
    with one-step value is not independent evidence and is never presented as such. What is
    informative is (a) how far current MSV sits from CA and (b) whether a rule ranking on CA
    realizes more value.
  * PAIRWISE "OTHERWISE" DECOMPOSITION: the starters of F_P and F_O grouped by player position
    and, separately, by lineup slot (QB/RB/WR/TE/FLEX/K/DST). Their per-group differences sum
    exactly to V(F_P) - V(F_O) (asserted). The P-position group difference is P's increment over
    the starters the continuation would otherwise have fielded at that position had O been taken;
    the players who start at P's position in F_O but not in F_P are "the continuation's player
    for P's slot". Positions are never assumed to be slots: every player's slot is read from the
    allocator.
  * Gaps (P minus O): current_msv_gap, ca_msv_gap, value_base gap (MSV + DA-VORP),
    ca_value gap (CA + DA-VORP), one-step gap (season-long; weekly separately).
    Error of a gap g against the one-step gap y is g - y; reported as mean, median, mean |g - y|,
    Pearson and Spearman correlation with y, and sign agreement.
  * OVERSTATEMENT: G = current_msv_gap - ca_msv_gap (how much MORE current MSV favours P than CA
    does). Per candidate, MSV(c) - CA(c) as a continuous quantity; no materiality threshold.

POPULATIONS (never pooled across the first two)
  A  D121 PRIMARY RB->QB      B  D121 PRIMARY RB->WR
  S  SECONDARY: every rounds 1-6 state where ARM 4's pick and the oracle differ in position.
  R  RE-RANK GRID: every rounds 1-6 state (120 per format: 6 rounds x 4 slots x 5 seasons), so a
     re-ranking that moves correct picks the wrong way is counted, not hidden.

COUNTERFACTUAL RE-RANK (diagnostic only, not a production experiment): replace each candidate's
value_base by CA(c) + DA-VORP(c), leave OC / fit / risk / survival / capacity untouched, take
argmax(score) with the `player_id` tie key (L0 has no legality rule -- asserted, as in D121).
Exact over the whole board with a proven bound: every multiplier is >= 0 (asserted), so the score
is non-decreasing in value; and CA(c) <= points(c) + s, s = max(0, -min points on the board),
because removing c from F_c and filling its slot is a feasible forced-fill lineup. Candidates are
evaluated in decreasing order of their upper-bound score and the search stops when the next
bound is strictly below the best exact score. The bound is asserted on every evaluated candidate.
Reported: picks changed, new pick == O, flips by flow, ORACLE-DIRECTION flips (new pick has O's
position, P did not), REVERSE-DIRECTION flips (P had O's position, the new pick does not),
season-long and weekly realized one-step value vs P, regret, per format.

STATISTICS: season-clustered t intervals (k seasons, t_{0.975,k-1}); MDE is reported two ways --
the CI half-width (D114's convention) and the 80%-power paired MDE (t_{0.975,k-1} + t_{0.80,k-1})
* SE. The old 172-250 detection floor is not reused.

STRUCTURAL CLASSIFICATION (first that holds, in this order; the others' conditions are reported)
  "overcredit supported" for (flow, format) iff BOTH
      (i)  the season-clustered CI of G excludes 0 on the positive side, and
      (ii) the critical cell "term prefers P but one-step prefers O" is strictly smaller for CA
           than for current MSV.
  "decision-relevant" for a format iff the re-rank's per-state season-long delta on the PRIMARY
      states has a season-clustered CI excluding 0 on the positive side AND its weekly mean > 0.
  A  overcredit supported for both flows in both formats AND decision-relevant in both formats.
  D  not A; overcredit supported in both formats for one flow and in neither format for the other.
  B  not A or D; overcredit supported for at least one (flow, format).
  C  overcredit supported nowhere.
  E  reserved for a failed exact computation -- the runner raises instead of producing numbers.
Whatever the letter, the only production conclusion D122 can draw is "No production change
recommended"; if A holds, the next step is a separately pre-registered controlled experiment.

------------------------------------------------------------------------------------------
AMENDMENT -- after a one-draft smoke run (target 2022, slot 1), BEFORE the full run
------------------------------------------------------------------------------------------
The smoke run showed the two pre-registered continuation quantities can diverge sharply, and why:
the leave-one-out CA(c) is computed on F_c, a roster the continuation built KNOWING it had c. In
both RB->QB states of that draft the continuation, holding the RB, drafted no third RB, so
removing him leaves the RB slot empty and CA(RB) = his full projection = MSV. But when the QB is
taken instead, the same continuation drafts a 202-point RB -- so the RB's increment over what the
continuation would OTHERWISE have fielded is 126, not 328. Leave-one-out cannot see a replacement
the continuation only drafts when the candidate is absent; the pairwise decomposition can.
Therefore, added now, before any full-run number:
  * pw_msv(P) = P_increment_over_otherwise, pw_msv(O) = O_increment_over_otherwise, and
    pw_value = pw_msv + DA-VORP, carried through EVERY table as two more terms beside msv /
    ca_msv / value_base / ca_value. (pw is defined only for the pair, so it has no whole-board
    re-rank; instead the pairwise check "with pw_value, does O outscore P" is reported.)
  * The pre-registered overcredit criterion and A-D rule are evaluated SEPARATELY on ca_msv (the
    pre-registered letter) and on pw_msv (the amended letter). Both letters are reported; neither
    replaces the other. For the pw letter "decision-relevant" is the same whole-board re-rank
    criterion (the only realized-value test that exists), so A under pw cannot be reached without
    the re-rank also passing.
  * As with CA, pw_gap = one-step gap - spillover (other positions) exactly, so its agreement with
    one-step value is partly by construction and is never presented as independent evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
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
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.replacement import (
    best_lineup_points,
    compute_league_starters,
    marginal_starter_value,
)

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
EARLY_ROUNDS = (1, 2, 3, 4, 5, 6)
PRIMARY = ("PRIMARY RB->QB", "PRIMARY RB->WR")
REPRO_TOLERANCE = 1e-6
BENCH = "BENCH"


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D121 = _load("d121_value_vs_survival")
D120, D117, D116, D115 = D121.D120, D121.D117, D121.D116, D121.D115


class UnreconstructibleError(RuntimeError):
    """D122 stops rather than substituting."""


# --------------------------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------------------------
def sign(x: float, tol: float = 1e-9) -> int:
    return 0 if abs(x) <= tol else (1 if x > 0 else -1)


def lineup(league, roster: list[str], proj: dict, pos: dict) -> tuple[float, dict[str, str]]:
    """(best-lineup value, {starter: slot}) with the production allocator. The value is
    `best_lineup_points` itself; the slots come from the same `compute_league_starters` call
    shape it uses, and the two are asserted to agree."""
    rp = {p: proj.get(p, 0.0) for p in roster}
    rpos = {p: pos.get(p, "UNKNOWN") for p in roster}
    res = compute_league_starters(league, rp, rpos, teams=1)
    slots: dict[str, str] = {}
    for position, players in res["dedicated_starters"].items():
        for p in players:
            slots[p] = position
    flex_names = sorted(league.flex_slots())
    flex_label = flex_names[0] if len(flex_names) == 1 else "FLEX*"
    for p in res["flex_starters"]:
        slots[p] = flex_label
    value = best_lineup_points(league, roster, proj, pos)
    if abs(value - sum(rp[p] for p in slots)) > REPRO_TOLERANCE:
        raise UnreconstructibleError("slot map disagrees with best_lineup_points")
    return value, slots


def leave_one_out(league, final: list[str], c: str, proj: dict, pos: dict) -> dict:
    """CA(c) = BL(final) - BL(final - c), plus who enters the lineup when c leaves it."""
    v_with, s_with = lineup(league, final, proj, pos)
    rest = [p for p in final if p != c]
    v_without, s_without = lineup(league, rest, proj, pos)
    entrants = sorted(set(s_without) - set(s_with))
    if len(entrants) > 1:
        raise UnreconstructibleError(f"{len(entrants)} entrants after removing one player")
    return {
        "ca_msv": v_with - v_without,
        "bl_final": v_with,
        "bl_without": v_without,
        "slot_in_final": s_with.get(c, BENCH),
        "entrant": entrants[0] if entrants else None,
        "entrant_slot": s_without[entrants[0]] if entrants else None,
        "reshuffled": sorted(
            p for p in s_without if p in s_with and s_with[p] != s_without[p] and p != c
        ),
    }


def entrant_origin(entrant: str | None, drafted_now: list[str], slot_in_final: str) -> str:
    """Where the continuation's replacement for c comes from. Descriptive, no threshold."""
    if slot_in_final == BENCH:
        return "not_a_starter_in_final"
    if entrant is None:
        return "no_entrant_slot_left_empty"
    if entrant in drafted_now:
        return "rostered_at_state"
    return "drafted_by_continuation"


def group_points(slots: dict[str, str], proj: dict, pos: dict, by: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for p, slot in slots.items():
        out[pos.get(p, "UNKNOWN") if by == "position" else slot] += proj.get(p, 0.0)
    return dict(out)


def pairwise_otherwise(league, f_p, f_o, p, o, proj, pos) -> dict:
    """Group the starters of F_P and F_O by position and by slot; the differences sum to the
    one-step gap exactly (asserted)."""
    v_p, s_p = lineup(league, f_p, proj, pos)
    v_o, s_o = lineup(league, f_o, proj, pos)
    out = {}
    for by in ("position", "slot"):
        gp, go = group_points(s_p, proj, pos, by), group_points(s_o, proj, pos, by)
        delta = {k: gp.get(k, 0.0) - go.get(k, 0.0) for k in sorted(set(gp) | set(go))}
        if abs(sum(delta.values()) - (v_p - v_o)) > REPRO_TOLERANCE:
            raise UnreconstructibleError(f"{by} groups do not sum to the one-step gap")
        out[f"delta_by_{by}"] = delta
    pp, po = pos.get(p), pos.get(o)
    d = out["delta_by_position"]
    out["P_increment_over_otherwise"] = d.get(pp, 0.0)
    out["O_increment_over_otherwise"] = -d.get(po, 0.0)
    out["spillover_other_positions"] = (v_p - v_o) - d.get(pp, 0.0) - d.get(po, 0.0)

    def starters_at(slots, position):
        return {x: slots[x] for x in slots if pos.get(x) == position}

    out["otherwise_for_P_position"] = [
        {"player_id": x, "slot": s, "points": proj.get(x, 0.0)}
        for x, s in sorted(starters_at(s_o, pp).items())
        if x not in s_p
    ]
    out["otherwise_for_O_position"] = [
        {"player_id": x, "slot": s, "points": proj.get(x, 0.0)}
        for x, s in sorted(starters_at(s_p, po).items())
        if x not in s_o
    ]
    out["P_slot_in_F_P"] = s_p.get(p, BENCH)
    out["O_slot_in_F_O"] = s_o.get(o, BENCH)
    # Does the continuation that takes the OTHER player now draft this very player later?
    out["P_in_F_O"] = s_o.get(p, BENCH) if p in f_o else None
    out["O_in_F_P"] = s_p.get(o, BENCH) if o in f_p else None
    out["P_otherwise_kind"] = otherwise_kind(
        out["P_in_F_O"], out["otherwise_for_P_position"], out["P_increment_over_otherwise"]
    )
    out["O_otherwise_kind"] = otherwise_kind(
        out["O_in_F_P"], out["otherwise_for_O_position"], out["O_increment_over_otherwise"]
    )
    return out


def otherwise_kind(same_player_slot: str | None, otherwise: list, increment: float) -> str:
    """What the continuation does at this player's position when the OTHER player is taken now.
    Descriptive and mutually exclusive; no threshold on the increment is used."""
    if same_player_slot is not None:
        return "same_player_drafted_later"
    if otherwise:
        return "position_refilled_by_another_player"
    if increment > 1e-9:
        return "position_not_refilled"
    return "no_starter_change_at_position"


def attach_pairwise_terms(rec_p: dict, rec_o: dict, pw: dict) -> None:
    """The amendment's pw terms: each side's increment over what the continuation fields at its
    position when the OTHER side is taken, plus unchanged DA-VORP, and the pair's L0 scores."""
    rec_p["pw_msv"] = pw["P_increment_over_otherwise"]
    rec_o["pw_msv"] = pw["O_increment_over_otherwise"]
    for rec in (rec_p, rec_o):
        rec["pw_value"] = rec["pw_msv"] + rec["da_vorp"]
        rec["pw_score"] = D117.l0_score({**rec["factors"], "value": rec["pw_value"]})


def ca_upper_bound(points: float, slack: float) -> float:
    return points + slack


def rerank(factors: dict, da_vorp: dict, points: dict, slack: float, ca_of) -> tuple[str, int]:
    """Exact argmax of l0_score with value = CA + DA-VORP over the whole board, evaluating CA
    (one rollout each) lazily in decreasing order of the upper-bound score."""

    def score(pid, value):
        return D117.l0_score({**factors[pid], "value": value})

    ub = {pid: score(pid, ca_upper_bound(points[pid], slack) + da_vorp[pid]) for pid in factors}
    best: tuple[float, str] | None = None
    n = 0
    for pid in sorted(factors, key=lambda x: (-ub[x], x)):
        if best is not None and ub[pid] < best[0] - 1e-9:
            break
        ca = ca_of(pid)
        n += 1
        if ca > ca_upper_bound(points[pid], slack) + 1e-6:
            raise UnreconstructibleError(f"CA bound violated for {pid}")
        s = score(pid, ca + da_vorp[pid])
        if best is None or s > best[0] + 1e-12 or (abs(s - best[0]) <= 1e-12 and pid < best[1]):
            best = (s, pid)
    return best[1], n


def season_ci(values: dict) -> dict:
    """Season-clustered t interval; MDE as CI half-width and as the 80%-power paired MDE."""
    from scipy.stats import t as student_t

    vals = [v for v in values.values() if v is not None]
    k = len(vals)
    if k < 2:
        return {"k": k, "mean": vals[0] if vals else None, "ci": None, "mde_half": None}
    md, se = mean(vals), stdev(vals) / math.sqrt(k)
    t975 = float(student_t.ppf(0.975, k - 1))
    t80 = float(student_t.ppf(0.80, k - 1))
    return {
        "k": k,
        "mean": md,
        "se": se,
        "ci": (md - t975 * se, md + t975 * se),
        "mde_half": t975 * se,
        "mde_80": (t975 + t80) * se,
    }


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for m in range(i, j + 1):
            ranks[order[m]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (sx * sy)


def spearman(x: list[float], y: list[float]) -> float | None:
    return pearson(_rank(x), _rank(y)) if len(x) >= 3 else None


def gap_error(g: list[float], y: list[float]) -> dict:
    e = [a - b for a, b in zip(g, y, strict=True)]
    return {
        "n": len(g),
        "mean_error": mean(e) if e else None,
        "median_error": median(e) if e else None,
        "mean_abs_error": mean(abs(x) for x in e) if e else None,
        "pearson": pearson(g, y),
        "spearman": spearman(g, y),
        "sign_agreement": sum(1 for a, b in zip(g, y, strict=True) if sign(a) == sign(b)),
    }


def overcredit_supported(entry: dict | None, term: str) -> bool:
    """Pre-registered: G's season CI excludes 0 on the positive side AND the critical cell is
    strictly smaller for the continuation-aware term than for current MSV."""
    if entry is None:
        return False
    ci = entry["overstatement_G"][term]["season"]["ci"]
    return bool(
        ci is not None
        and ci[0] > 0
        and entry["critical_cell"][term]["n"] < entry["critical_cell"]["msv"]["n"]
    )


def classify_structure(overcredit: dict, relevant: dict) -> dict:
    """The pre-registered A-D rule. `overcredit[(flow, fmt)]` and `relevant[fmt]` are bools."""
    flows = sorted({f for f, _ in overcredit})
    fmts = sorted({m for _, m in overcredit})
    held = {
        "A": all(overcredit[(f, m)] for f in flows for m in fmts)
        and all(relevant.get(m, False) for m in fmts),
        "D": any(
            all(overcredit[(f, m)] for m in fmts)
            and all(not overcredit[(g, m)] for g in flows if g != f for m in fmts)
            for f in flows
        ),
        "B": any(overcredit.values()),
    }
    held["C"] = not held["B"]
    letter = next(x for x in ("A", "D", "B", "C") if held[x])
    return {"letter": letter, "conditions": held}


# --------------------------------------------------------------------------------------------
# MODE: measure
# --------------------------------------------------------------------------------------------
def _key(r) -> tuple:
    return (r["league"], r["season"], r["slot"], r["overall_pick"])


class Continuation:
    """Per-state memo of the fixed continuation after each candidate: final roster and the
    season-long and weekly one-step values. The production rollout runs unmodified; the final
    roster is captured by the scorer wrapper it calls after the last pick."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cache: dict[str, dict] = {}

    def __call__(self, pick: str) -> dict:
        if pick not in self.cache:
            con, league, season, static, slot, state, realized, sl, wk = self.ctx
            captured: list[tuple[list[str], dict]] = []

            def capturing(drafted, actual):
                captured.append((list(drafted), dict(actual)))
                return sl(drafted, actual)

            v_sl = D115.roll_from_state(
                con, league, season, static, slot, state, pick, realized, capturing
            )
            if len(captured) != 1:
                raise UnreconstructibleError("the rollout did not score exactly one roster")
            final, actual = captured[0]
            self.cache[pick] = {
                "final": final,
                "actual": actual,
                "v_sl": v_sl,
                "v_wk": wk(final, actual)[0],
            }
        return self.cache[pick]


def candidate_record(league, c, cands, factors, state, arm4, static, cont, ca) -> dict:
    proj, pos = arm4.projections, arm4.positions
    drafted = list(state["drafted"])
    msv_engine = cands[c]["marginal_starter_value"]
    msv_re = marginal_starter_value(league, drafted, c, proj, pos)
    if abs(msv_re - msv_engine) > REPRO_TOLERANCE * max(1.0, abs(msv_engine)):
        raise UnreconstructibleError(f"MSV recomputation {msv_re} != engine {msv_engine} for {c}")
    _, slots_now = lineup(league, [*drafted, c], proj, pos)
    _, slots_before = lineup(league, drafted, proj, pos)
    run = cont(c)
    loo = ca(c)
    wk_scorer = cont.ctx[8]
    rest = [p for p in run["final"] if p != c]
    ca_wk = run["v_wk"] - wk_scorer(rest, run["actual"])[0]
    ent = loo["entrant"]
    f = factors[c]
    return {
        "player_id": c,
        "position": pos.get(c),
        "projection": proj.get(c, 0.0),
        "projection_y1": static.projections.get(c),
        "msv": msv_engine,
        "da_vorp": f["value"] - msv_engine,
        "value_base": f["value"],
        "ca_msv": loo["ca_msv"],
        "ca_msv_weekly": ca_wk,
        "ca_value": loo["ca_msv"] + f["value"] - msv_engine,
        "msv_equals_projection": abs(msv_engine - proj.get(c, 0.0)) < 1e-6,
        "slot_now": slots_now.get(c, BENCH),
        "roster_now_slots": dict(sorted(slots_before.items())),
        "roster_now_positions": [pos.get(p) for p in drafted],
        "slot_in_final": loo["slot_in_final"],
        "entrant": None
        if ent is None
        else {
            "player_id": ent,
            "position": pos.get(ent),
            "projection_y1": static.projections.get(ent),
            "realized": proj.get(ent, 0.0),
            "slot": loo["entrant_slot"],
        },
        "entrant_origin": entrant_origin(ent, drafted, loo["slot_in_final"]),
        "reshuffled": loo["reshuffled"],
        "score": D117.l0_score(f),
        "ca_score": D117.l0_score({**f, "value": loo["ca_msv"] + f["value"] - msv_engine}),
        "factors": f,
        "onestep": run["v_sl"],
        "onestep_weekly": run["v_wk"],
        "final_positions": sorted(pos.get(p, "UNKNOWN") for p in run["final"]),
    }


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= REPRO_TOLERANCE * max(1.0, abs(b))


def check_d121(pair: tuple[str, str, str | None], recs: dict, ref: dict, key) -> None:
    """Reproduction item 2: the state-level numbers D121 stored. `pair` = (P, O, flow)."""
    if pair != (ref["P"], ref["O"], ref["flow"]):
        raise UnreconstructibleError(f"D121 population differs at {key} -- STOP")
    for side in ("P", "O"):
        mine, theirs = recs[side], ref[f"value_split_{side}"]
        for k in D117.FACTORS:
            if not _near(mine["factors"][k], ref[f"factors_{side}"][k]):
                raise UnreconstructibleError(f"D121 factor {k} for {side} differs at {key}")
        if not (_near(mine["msv"], theirs["msv"]) and _near(mine["da_vorp"], theirs["da_vorp"])):
            raise UnreconstructibleError(f"D121 MSV/DA-VORP for {side} differs at {key}")
        if not _near(mine["onestep"], ref[f"onestep_{side}"]):
            raise UnreconstructibleError(f"D121 one-step for {side} differs at {key}")
        if not _near(mine["onestep_weekly"], ref[f"onestep_weekly_{side}"]):
            raise UnreconstructibleError(f"D121 weekly one-step for {side} differs at {key}")


def run_measure(con, leagues, d120_rows: dict, d121_rows: dict) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    repro = defaultdict(int)
    t0 = time.time()
    for league_name in leagues:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            arm4 = D120.arm_statics(con, league, season, static)["ARM4"]
            realized = _actual_points_for(con, season, sorted(static.projections))
            if any(abs(arm4.projections[p] - realized.get(p, 0.0)) > 0 for p in arm4.projections):
                raise UnreconstructibleError("ARM 4 projections are not realized points")
            slack = max(0.0, -min(arm4.projections.values()))
            sl = make_roster_scorer(SEASON_LONG, league, static)
            wk = make_roster_scorer(
                WEEKLY_NO_FORESIGHT, league, static, load_weekly_points(con, season)
            )
            for slot in sorted({k[2] for k in d120_rows if k[0] == league_name and k[1] == season}):
                for state in D115.replay_states(con, league, season, static, slot):
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
                    repro["arm4_states_checked"] += 1
                    if pick != ref["arms"]["ARM4"]["pick"]:
                        raise UnreconstructibleError(
                            f"ARM 4 pick {pick} != D120's {ref['arms']['ARM4']['pick']} at {key}"
                            " -- STOP"
                        )
                    repro["arm4_pick_matches"] += 1
                    if state["round"] not in EARLY_ROUNDS:
                        continue
                    o = ref["oracle_player"]
                    p_pos, o_pos = static.positions.get(pick, "UNKNOWN"), ref["oracle_position"]
                    wrong_position = pick != o and p_pos != o_pos
                    flow = D121.flow_of(p_pos, o_pos, state["round"]) if wrong_position else None
                    cands = {c.player_id: D116._candidate_dict(c) for c in scored}
                    if o not in cands:
                        raise UnreconstructibleError(f"oracle not on the ARM 4 board at {key}")
                    factors = {pid: D117.factors_from(c) for pid, c in cands.items()}
                    D121.exact_value_bases(factors, cands, arm4, league, state)
                    if D121.argmax_pick(factors) != pick:
                        raise UnreconstructibleError(f"re-ranking does not reproduce at {key}")
                    for f in factors.values():
                        if min(f["fit"], f["risk"], f["survival"], f["capacity"]) < 0:
                            raise UnreconstructibleError("negative multiplier breaks the bound")
                    ctx = (con, league, season, static, slot, state, realized, sl, wk)
                    cont = Continuation(ctx)
                    loo_cache: dict[str, dict] = {}

                    def ca(pid, _cont=cont, _cache=loo_cache, _lg=league, _a4=arm4):
                        if pid not in _cache:
                            run = _cont(pid)
                            loo = leave_one_out(
                                _lg, run["final"], pid, _a4.projections, _a4.positions
                            )
                            if abs(loo["bl_final"] - run["v_sl"]) > REPRO_TOLERANCE:
                                raise UnreconstructibleError(
                                    "BL(final) on ARM 4 projections != season-long scorer"
                                )
                            _cache[pid] = loo
                        return _cache[pid]

                    rec_p = candidate_record(
                        league, pick, cands, factors, state, arm4, static, cont, ca
                    )
                    rec_o = candidate_record(
                        league, o, cands, factors, state, arm4, static, cont, ca
                    )
                    if not _near(rec_p["onestep"], ref["arms"]["ARM4"]["rollout"]):
                        raise UnreconstructibleError(f"ARM 4 rollout != D120's at {key}")
                    if not _near(rec_p["onestep_weekly"], ref["arms"]["ARM4"]["rollout_weekly"]):
                        raise UnreconstructibleError(f"ARM 4 weekly rollout != D120's at {key}")
                    if not _near(rec_o["onestep"], ref["oracle_rollout"]):
                        raise UnreconstructibleError(f"oracle rollout != D115's at {key}")
                    repro["rollout_matches"] += 1
                    # The exact identity: one-step gap = CA gap + rest-of-roster gap.
                    rest_gap = ca(pick)["bl_without"] - ca(o)["bl_without"]
                    y = rec_p["onestep"] - rec_o["onestep"]
                    if abs(y - (rec_p["ca_msv"] - rec_o["ca_msv"]) - rest_gap) > REPRO_TOLERANCE:
                        raise UnreconstructibleError(f"CA identity fails at {key}")
                    da = {
                        pid: factors[pid]["value"] - cands[pid]["marginal_starter_value"]
                        for pid in factors
                    }
                    new, n_eval = rerank(
                        factors,
                        da,
                        {pid: arm4.projections.get(pid, 0.0) for pid in factors},
                        slack,
                        lambda pid, _ca=ca: _ca(pid)["ca_msv"],
                    )
                    run_new = cont(new)
                    row = {
                        "league": league_name,
                        "season": season,
                        "slot": slot,
                        "round": state["round"],
                        "overall_pick": state["overall_pick"],
                        "P": pick,
                        "O": o,
                        "P_position": p_pos,
                        "O_position": o_pos,
                        "wrong_position": wrong_position,
                        "flow": flow
                        if flow
                        else (f"OTHER {p_pos}->{o_pos}" if wrong_position else "SAME_POSITION"),
                        "rest_of_roster_gap": rest_gap,
                        "regret": rec_o["onestep"] - rec_p["onestep"],
                        "rerank": {
                            "pick": new,
                            "position": static.positions.get(new),
                            "changed": new != pick,
                            "is_oracle": new == o,
                            "n_rollouts": n_eval,
                            "onestep": run_new["v_sl"],
                            "onestep_weekly": run_new["v_wk"],
                            "delta": run_new["v_sl"] - rec_p["onestep"],
                            "delta_weekly": run_new["v_wk"] - rec_p["onestep_weekly"],
                        },
                    }
                    if wrong_position:
                        row["P"] = rec_p
                        row["O"] = rec_o
                        row["pairwise"] = pairwise_otherwise(
                            league,
                            cont(pick)["final"],
                            cont(o)["final"],
                            pick,
                            o,
                            arm4.projections,
                            arm4.positions,
                        )
                        attach_pairwise_terms(rec_p, rec_o, row["pairwise"])
                    else:
                        row["P"] = {k: rec_p[k] for k in ("player_id", "onestep", "onestep_weekly")}
                        row["O"] = {k: rec_o[k] for k in ("player_id", "onestep", "onestep_weekly")}
                    ref121 = d121_rows.get(key)
                    if ref121 is not None and ref121["flow"].startswith("PRIMARY"):
                        check_d121((pick, o, flow), {"P": rec_p, "O": rec_o}, ref121, key)
                        repro["d121_primary_matches"] += 1
                    elif flow in PRIMARY:
                        raise UnreconstructibleError(f"{key} is primary here but not in D121")
                    rows.append(row)
                print(
                    f"  measure {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows, dict(repro)


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
TERMS = ("msv", "ca_msv", "pw_msv", "value_base", "ca_value", "pw_value")
CONTINUATION_TERMS = ("ca_msv", "pw_msv")


def _stats(xs: list[float]) -> dict:
    xs = sorted(xs)
    if not xs:
        return {"n": 0}
    q = lambda f: xs[min(len(xs) - 1, int(f * (len(xs) - 1) + 0.5))]  # noqa: E731
    return {
        "n": len(xs),
        "mean": mean(xs),
        "median": median(xs),
        "min": xs[0],
        "q25": q(0.25),
        "q75": q(0.75),
        "max": xs[-1],
    }


def gap(r: dict, term: str) -> float:
    return r["P"][term] - r["O"][term]


def onestep_gap(r: dict, weekly: bool = False) -> float:
    k = "onestep_weekly" if weekly else "onestep"
    return r["P"][k] - r["O"][k]


def two_by_two(rows: list[dict], term: str, weekly: bool = False) -> dict:
    cells: dict = defaultdict(list)
    for r in rows:
        t, y = sign(gap(r, term)), sign(onestep_gap(r, weekly))
        name = lambda s: "Alpha" if s > 0 else ("Oracle" if s < 0 else "tie")  # noqa: E731
        cells[f"{term}_prefers_{name(t)}|onestep_prefers_{name(y)}"].append(r)
    return {
        cell: {
            "n": len(rs),
            "pct": 100 * len(rs) / len(rows),
            "regret": sum(r["regret"] for r in rs),
            "term_gap": _stats([gap(r, term) for r in rs]),
            "onestep_gap": _stats([onestep_gap(r, weekly) for r in rs]),
        }
        for cell, rs in sorted(cells.items())
    }


def critical(rows: list[dict], term: str, weekly: bool = False) -> dict:
    rs = [r for r in rows if gap(r, term) > 1e-9 and onestep_gap(r, weekly) < -1e-9]
    return {"n": len(rs), "regret": sum(r["regret"] for r in rs)}


def by_season(rows: list[dict], fn) -> dict:
    g: dict = defaultdict(list)
    for r in rows:
        g[r["season"]].append(fn(r))
    return {s: mean(v) for s, v in g.items()}


def side_profile(rows: list[dict], side: str) -> dict:
    recs = [r[side] for r in rows]
    empty = [c for c in recs if c["msv_equals_projection"]]

    def count(key):
        out: dict = defaultdict(int)
        for c in recs:
            out[str(key(c))] += 1
        return dict(sorted(out.items()))

    return {
        "msv_minus_ca": _stats([c["msv"] - c["ca_msv"] for c in recs]),
        "ca_over_msv": _stats([c["ca_msv"] / c["msv"] for c in recs if abs(c["msv"]) > 1e-9]),
        "msv_equals_projection": len(empty),
        "empty_slot_projection_minus_ca": _stats([c["projection"] - c["ca_msv"] for c in empty]),
        "empty_slot_ca_below_projection": sum(
            1 for c in empty if c["ca_msv"] < c["projection"] - 1e-6
        ),
        "empty_slot_projection_minus_pw": _stats([c["projection"] - c["pw_msv"] for c in empty]),
        "empty_slot_pw_below_projection": sum(
            1 for c in empty if c["pw_msv"] < c["projection"] - 1e-6
        ),
        "msv_minus_pw": _stats([c["msv"] - c["pw_msv"] for c in recs]),
        "slot_now": count(lambda c: c["slot_now"]),
        "slot_in_final": count(lambda c: c["slot_in_final"]),
        "entrant_origin": count(lambda c: c["entrant_origin"]),
        "entrant_slot": count(lambda c: (c["entrant"] or {}).get("slot")),
        "entrant_position": count(lambda c: (c["entrant"] or {}).get("position")),
        "entrant_realized": _stats([c["entrant"]["realized"] for c in recs if c["entrant"]]),
    }


def pair_analysis(rows: list[dict]) -> dict:
    y = [onestep_gap(r) for r in rows]
    yw = [onestep_gap(r, True) for r in rows]
    out: dict = {"n": len(rows), "regret": sum(r["regret"] for r in rows)}
    out["distinct_decisions"] = len({(r["P"]["player_id"], r["O"]["player_id"]) for r in rows})
    out["seasons"] = _count(r["season"] for r in rows)
    out["prefers_alpha"] = {t: sum(1 for r in rows if gap(r, t) > 1e-9) for t in TERMS}
    out["agrees_with_onestep"] = {
        t: sum(1 for r, v in zip(rows, y, strict=True) if sign(gap(r, t)) == sign(v)) for t in TERMS
    }
    out["agrees_with_onestep_weekly"] = {
        t: sum(1 for r, v in zip(rows, yw, strict=True) if sign(gap(r, t)) == sign(v))
        for t in TERMS
    }
    out["ca_weekly_agrees_with_weekly"] = sum(
        1
        for r, v in zip(rows, yw, strict=True)
        if sign(r["P"]["ca_msv_weekly"] - r["O"]["ca_msv_weekly"]) == sign(v)
    )
    out["two_by_two"] = {t: two_by_two(rows, t) for t in TERMS}
    out["two_by_two_weekly"] = {t: two_by_two(rows, t, weekly=True) for t in TERMS}
    out["critical_cell"] = {t: critical(rows, t) for t in TERMS}
    out["critical_cell_weekly"] = {t: critical(rows, t, weekly=True) for t in TERMS}
    out["gap_error"] = {t: gap_error([gap(r, t) for r in rows], y) for t in TERMS}
    out["gap_error_weekly"] = {t: gap_error([gap(r, t) for r in rows], yw) for t in TERMS}
    out["gap_error_weekly"]["ca_msv_weekly"] = gap_error(
        [r["P"]["ca_msv_weekly"] - r["O"]["ca_msv_weekly"] for r in rows], yw
    )
    out["overstatement_G"] = {}
    for term in CONTINUATION_TERMS:
        over = lambda r, term=term: gap(r, "msv") - gap(r, term)  # noqa: E731
        out["overstatement_G"][term] = {
            **_stats([over(r) for r in rows]),
            "season": season_ci(by_season(rows, over)),
        }
    out["abs_error_reduction"] = {}
    for a, b in (
        ("msv", "ca_msv"),
        ("msv", "pw_msv"),
        ("value_base", "ca_value"),
        ("value_base", "pw_value"),
    ):
        red = lambda r, a=a, b=b: abs(gap(r, a) - onestep_gap(r)) - abs(gap(r, b) - onestep_gap(r))  # noqa: E731
        out["abs_error_reduction"][f"{a}->{b}"] = {
            **_stats([red(r) for r in rows]),
            "season": season_ci(by_season(rows, red)),
        }
    out["rest_of_roster_gap"] = _stats([r["rest_of_roster_gap"] for r in rows])
    out["pw_spillover"] = _stats([r["pairwise"]["spillover_other_positions"] for r in rows])
    out["pw_pair_flips_to_oracle"] = {
        "n": sum(1 for r in rows if r["O"]["pw_score"] > r["P"]["pw_score"]),
        "regret_on_flipped": sum(
            r["regret"] for r in rows if r["O"]["pw_score"] > r["P"]["pw_score"]
        ),
        "ca_pair_flips_to_oracle": sum(1 for r in rows if r["O"]["ca_score"] > r["P"]["ca_score"]),
    }
    out["side_P"] = side_profile(rows, "P")
    out["side_O"] = side_profile(rows, "O")
    # MSV vs DA-VORP, for each continuation-aware term
    da = lambda r: gap(r, "da_vorp")  # noqa: E731
    out["msv_vs_davorp"] = {
        "davorp_alone_sign_agrees": sum(
            1 for r, v in zip(rows, y, strict=True) if sign(da(r)) == sign(v)
        ),
        "msv_alone_sign_agrees": out["agrees_with_onestep"]["msv"],
        "msv_disagrees_with_davorp": sum(1 for r in rows if sign(gap(r, "msv")) != sign(da(r))),
        "davorp_gap_all": _stats([da(r) for r in rows]),
    }
    for term, value in (("ca_msv", "ca_value"), ("pw_msv", "pw_value")):
        wrong = [r for r in rows if gap(r, value) > 1e-9 and onestep_gap(r) < -1e-9]
        out["msv_vs_davorp"][term] = {
            "1_alone_sign_agrees": out["agrees_with_onestep"][term],
            "2_disagrees_with_davorp": sum(1 for r in rows if sign(gap(r, term)) != sign(da(r))),
            "3_value_still_prefers_alpha_wrongly": len(wrong),
            "3_regret_on_those": sum(r["regret"] for r in wrong),
            "3_davorp_alone_carries_it": sum(
                1 for r in wrong if da(r) > 1e-9 and gap(r, term) <= 1e-9
            ),
            "3_term_alone_carries_it": sum(
                1 for r in wrong if gap(r, term) > 1e-9 and da(r) <= 1e-9
            ),
            "3_both_favour_alpha": sum(1 for r in wrong if gap(r, term) > 1e-9 and da(r) > 1e-9),
            "3_davorp_gap": _stats([da(r) for r in wrong]),
            "3_term_gap": _stats([gap(r, term) for r in wrong]),
        }
    # Pairwise "otherwise" decomposition
    pw = [r["pairwise"] for r in rows]
    keys_pos = sorted({k for p in pw for k in p["delta_by_position"]})
    keys_slot = sorted({k for p in pw for k in p["delta_by_slot"]})
    out["pairwise"] = {
        "delta_by_position_mean": {
            k: mean(p["delta_by_position"].get(k, 0.0) for p in pw) for k in keys_pos
        },
        "delta_by_slot_mean": {
            k: mean(p["delta_by_slot"].get(k, 0.0) for p in pw) for k in keys_slot
        },
        "P_increment_over_otherwise": _stats([p["P_increment_over_otherwise"] for p in pw]),
        "O_increment_over_otherwise": _stats([p["O_increment_over_otherwise"] for p in pw]),
        "spillover_other_positions": _stats([p["spillover_other_positions"] for p in pw]),
        "pairwise_gap_error": gap_error(
            [p["P_increment_over_otherwise"] - p["O_increment_over_otherwise"] for p in pw], y
        ),
        "msv_P_minus_P_increment": _stats(
            [r["P"]["msv"] - r["pairwise"]["P_increment_over_otherwise"] for r in rows]
        ),
        "msv_O_minus_O_increment": _stats(
            [r["O"]["msv"] - r["pairwise"]["O_increment_over_otherwise"] for r in rows]
        ),
        "P_otherwise_kind": _count(p["P_otherwise_kind"] for p in pw),
        "O_otherwise_kind": _count(p["O_otherwise_kind"] for p in pw),
        "P_otherwise_kind_regret": {
            k: sum(r["regret"] for r in rows if r["pairwise"]["P_otherwise_kind"] == k)
            for k in sorted({p["P_otherwise_kind"] for p in pw})
        },
        "P_slot_in_F_P": _count(p["P_slot_in_F_P"] for p in pw),
        "O_slot_in_F_O": _count(p["O_slot_in_F_O"] for p in pw),
        "otherwise_for_P_position_slots": _count(
            x["slot"] for p in pw for x in p["otherwise_for_P_position"]
        ),
        "otherwise_for_O_position_slots": _count(
            x["slot"] for p in pw for x in p["otherwise_for_O_position"]
        ),
    }
    for name, fn in (("by_season", lambda r: r["season"]), ("by_round", lambda r: r["round"])):
        g: dict = defaultdict(list)
        for r in rows:
            g[str(fn(r))].append(r)
        out[name] = {
            k: {
                "n": len(v),
                "regret": sum(r["regret"] for r in v),
                "msv_prefers_alpha": sum(1 for r in v if gap(r, "msv") > 1e-9),
                "ca_prefers_alpha": sum(1 for r in v if gap(r, "ca_msv") > 1e-9),
                "value_prefers_alpha": sum(1 for r in v if gap(r, "value_base") > 1e-9),
                "ca_value_prefers_alpha": sum(1 for r in v if gap(r, "ca_value") > 1e-9),
                "onestep_prefers_alpha": sum(1 for r in v if onestep_gap(r) > 1e-9),
                "mean_G": mean(gap(r, "msv") - gap(r, "ca_msv") for r in v),
                "mean_G_pw": mean(gap(r, "msv") - gap(r, "pw_msv") for r in v),
                "pw_prefers_alpha": sum(1 for r in v if gap(r, "pw_msv") > 1e-9),
                "rerank_delta": sum(r["rerank"]["delta"] for r in v),
            }
            for k, v in sorted(g.items())
        }
    return out


def _count(xs) -> dict:
    out: dict = defaultdict(int)
    for x in xs:
        out[str(x)] += 1
    return dict(sorted(out.items()))


def deep_dive(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        p, o, pw = r["P"], r["O"], r["pairwise"]
        out.append(
            {
                "state": f"{r['season']} s{r['slot']} R{r['round']} #{r['overall_pick']}",
                "alpha": f"{p['position']} {p['player_id'][-6:]}",
                "oracle": f"{o['position']} {o['player_id'][-6:]}",
                "proj_A": p["projection"],
                "proj_O": o["projection"],
                "msv_A": p["msv"],
                "msv_O": o["msv"],
                "davorp_A": p["da_vorp"],
                "davorp_O": o["da_vorp"],
                "slot_now_A": p["slot_now"],
                "slot_now_O": o["slot_now"],
                "roster_now": "".join(x[0] for x in p["roster_now_positions"]) or "-",
                "ca_A": p["ca_msv"],
                "ca_O": o["ca_msv"],
                "pw_A": p["pw_msv"],
                "pw_O": o["pw_msv"],
                "pw_score_A": p["pw_score"],
                "pw_score_O": o["pw_score"],
                "entrant_A": _ent(p),
                "entrant_O": _ent(o),
                "otherwise_A_pos": [
                    f"{x['player_id'][-6:]}@{x['slot']}:{x['points']:.0f}"
                    for x in pw["otherwise_for_P_position"]
                ],
                "otherwise_O_pos": [
                    f"{x['player_id'][-6:]}@{x['slot']}:{x['points']:.0f}"
                    for x in pw["otherwise_for_O_position"]
                ],
                "onestep_A": p["onestep"],
                "onestep_O": o["onestep"],
                "onestep_wk_A": p["onestep_weekly"],
                "onestep_wk_O": o["onestep_weekly"],
                "score_A": p["score"],
                "score_O": o["score"],
                "ca_score_A": p["ca_score"],
                "ca_score_O": o["ca_score"],
                "rerank": f"{r['rerank']['position']} {r['rerank']['pick'][-6:]} "
                f"d{r['rerank']['delta']:+.0f}",
            }
        )
    return out


def _ent(c: dict) -> str:
    e = c["entrant"]
    if e is None:
        return c["entrant_origin"]
    return f"{e['position']} {e['player_id'][-6:]}@{e['slot']}:{e['realized']:.0f} ({c['entrant_origin']})"


def rerank_analysis(rows: list[dict], total_arm4_regret: float) -> dict:
    groups = {
        "PRIMARY": [r for r in rows if r["flow"] in PRIMARY],
        "PRIMARY RB->QB": [r for r in rows if r["flow"] == PRIMARY[0]],
        "PRIMARY RB->WR": [r for r in rows if r["flow"] == PRIMARY[1]],
        "ALL_WRONG_POSITION": [r for r in rows if r["wrong_position"]],
        "SAME_POSITION_OR_AGREES": [r for r in rows if not r["wrong_position"]],
        "ALL_R1_6": rows,
    }
    out = {}
    for name, rs in groups.items():
        if not rs:
            continue
        rr = [r["rerank"] for r in rs]
        out[name] = {
            "n": len(rs),
            "picks_changed": sum(1 for x in rr if x["changed"]),
            "new_pick_is_oracle": sum(1 for x in rr if x["is_oracle"]),
            "oracle_direction_flips": sum(
                1
                for r in rs
                if r["rerank"]["changed"]
                and r["rerank"]["position"] == r["O_position"]
                and r["P_position"] != r["O_position"]
            ),
            "reverse_direction_flips": sum(
                1
                for r in rs
                if r["rerank"]["changed"]
                and r["P_position"] == r["O_position"]
                and r["rerank"]["position"] != r["O_position"]
            ),
            "flips_by_new_position": _count(
                f"{r['P_position']}->{r['rerank']['position']}"
                for r in rs
                if r["rerank"]["changed"]
            ),
            "improved": sum(1 for x in rr if x["delta"] > 1e-9),
            "worsened": sum(1 for x in rr if x["delta"] < -1e-9),
            "delta_sum": sum(x["delta"] for x in rr),
            "delta_weekly_sum": sum(x["delta_weekly"] for x in rr),
            "delta_per_state": mean(x["delta"] for x in rr),
            "delta_season": season_ci(by_season(rs, lambda r: r["rerank"]["delta"])),
            "delta_weekly_season": season_ci(by_season(rs, lambda r: r["rerank"]["delta_weekly"])),
            "regret_before": sum(r["regret"] for r in rs),
            "regret_after": sum(r["regret"] - r["rerank"]["delta"] for r in rs),
            "share_of_total_arm4_regret_recovered": 100
            * sum(x["delta"] for x in rr)
            / total_arm4_regret,
            "rollouts_per_state": _stats([x["n_rollouts"] for x in rr]),
        }
    return out


def report(rows_all: list[dict], totals: dict, repro: dict) -> dict:
    bar = "=" * 100
    summary: dict = {"reproduction": repro, "formats": {}}
    print(f"{bar}\nREPRODUCTION: {repro}\n{bar}")
    overcredit: dict = {t: {} for t in CONTINUATION_TERMS}
    relevant: dict = {}
    for league in FORMATS:
        rows = [r for r in rows_all if r["league"] == league]
        if not rows:
            continue
        entry = summary["formats"].setdefault(league, {"total_arm4_regret": totals[league]})
        groups = {
            "A_RB->QB": [r for r in rows if r["flow"] == PRIMARY[0]],
            "B_RB->WR": [r for r in rows if r["flow"] == PRIMARY[1]],
            "PRIMARY_POOLED": [r for r in rows if r["flow"] in PRIMARY],
            "S_ALL_R1_6_WRONG_POSITION": [r for r in rows if r["wrong_position"]],
        }
        for name, rs in groups.items():
            if not rs:
                continue
            entry[name] = pair_analysis(rs)
            entry[name]["deep_dive"] = deep_dive(rs) if name[0] in "AB" else None
            _print_group(f"{league} {name}", entry[name])
        entry["rerank"] = rerank_analysis(rows, totals[league])
        print(f"\n{bar}\n{league} RE-RANK (CA-MSV + unchanged DA-VORP)\n{bar}")
        for g, v in entry["rerank"].items():
            print(f"  {g:<26} {json.dumps(v, default=str)}")
        for term in CONTINUATION_TERMS:
            for flow, name in ((PRIMARY[0], "A_RB->QB"), (PRIMARY[1], "B_RB->WR")):
                overcredit[term][(flow, league)] = overcredit_supported(entry.get(name), term)
        pr = entry["rerank"].get("PRIMARY")
        ci = pr["delta_season"]["ci"] if pr else None
        relevant[league] = bool(
            ci is not None and ci[0] > 0 and pr["delta_weekly_season"]["mean"] > 0
        )
    summary["classification"] = {
        "decision_relevant": relevant,
        **{
            f"{'preregistered' if term == 'ca_msv' else 'amended'}_{term}": {
                "overcredit_supported": {f"{f} | {m}": v for (f, m), v in oc.items()},
                **classify_structure(oc, relevant),
            }
            for term, oc in overcredit.items()
        },
    }
    print(f"\n{bar}\nSTRUCTURAL CLASSIFICATION: {json.dumps(summary['classification'])}\n{bar}")
    return summary


def _print_group(title: str, e: dict) -> None:
    print(f"\n{'=' * 100}\n{title}: n {e['n']} regret {e['regret']:.0f}\n{'=' * 100}")
    print(f"  prefers Alpha: {e['prefers_alpha']}")
    print(f"  agrees with one-step (season): {e['agrees_with_onestep']}")
    print(
        f"  agrees with one-step (weekly): {e['agrees_with_onestep_weekly']} "
        f"| CA-weekly vs weekly: {e['ca_weekly_agrees_with_weekly']}"
    )
    print(f"  critical cell (term prefers Alpha, one-step prefers Oracle): {e['critical_cell']}")
    print(f"  critical cell weekly: {e['critical_cell_weekly']}")
    for t in TERMS:
        print(f"  2x2 {t}:")
        for cell, v in e["two_by_two"][t].items():
            print(
                f"    {cell:<50} n {v['n']:>3} ({v['pct']:.0f}%) regret {v['regret']:7.1f} "
                f"term gap mean {v['term_gap']['mean']:+.1f} med {v['term_gap']['median']:+.1f} "
                f"one-step gap mean {v['onestep_gap']['mean']:+.1f} "
                f"med {v['onestep_gap']['median']:+.1f}"
            )
    print(f"  gap error vs one-step: {json.dumps(e['gap_error'])}")
    print(f"  gap error vs weekly:   {json.dumps(e['gap_error_weekly'])}")
    print(f"  overstatement G: {json.dumps(e['overstatement_G'], default=str)}")
    print(f"  |err| reduction: {json.dumps(e['abs_error_reduction'], default=str)}")
    print(f"  rest-of-roster gap (CA): {json.dumps(e['rest_of_roster_gap'])}")
    print(f"  spillover (pw): {json.dumps(e['pw_spillover'])}")
    print(f"  pairwise flips to oracle: {json.dumps(e['pw_pair_flips_to_oracle'])}")
    print(f"  side P: {json.dumps(e['side_P'])}")
    print(f"  side O: {json.dumps(e['side_O'])}")
    print(f"  MSV vs DA-VORP: {json.dumps(e['msv_vs_davorp'])}")
    print(f"  pairwise: {json.dumps(e['pairwise'])}")
    for name in ("by_season", "by_round"):
        for k, v in e[name].items():
            print(f"  {name} {k:<6} {json.dumps(v)}")


def _src_tree() -> dict:
    return D121._src_tree()


def _write(out: Path, name: str, payload) -> None:
    D121._write(out, name, payload)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("measure", "report"))
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument("--d115", action="append", default=[])
    ap.add_argument("--d120", help="dir with d120_arms_*.json")
    ap.add_argument("--d121", help="dir with d121_measured_*.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    assert_no_realized_inputs_in_policy()
    if DECISION_ARM_VORP_WEIGHT != 1.0:
        raise UnreconstructibleError("DA-VORP = value_base - MSV needs the shipped weight of 1.0")
    if SHIPPED_TIER in TIERS_ENFORCING_LEGALITY or L_TIER_SPEC[SHIPPED_TIER][1]:
        raise UnreconstructibleError("the argmax re-ranking assumes no legality rule")
    if a.mode == "report":
        rows, totals, repro, prov = [], {}, defaultdict(int), {}
        for path in sorted(out.glob("d122_measured_*.json")):
            payload = json.loads(path.read_text())
            rows.extend(payload["rows"])
            totals.update(payload["arm4_total_regret"])
            for k, v in payload["reproduction"].items():
                repro[k] += v
            prov[path.name] = payload["provenance"]
        summary = report(rows, totals, dict(repro))
        summary["provenance"] = prov
        _write(out, "d122_summary.json", summary)
        return
    con = duckdb.connect(a.db, read_only=True)
    vintage = compute_board_vintage(con)
    leagues = tuple(x for x in a.leagues.split(",") if x)
    d115 = D120.load_d115([Path(d) for d in a.d115], vintage.combined_hash)
    d120_rows, input_hashes = {}, {}
    for path in sorted(Path(a.d120).glob("d120_arms_*.json")):
        payload = json.loads(path.read_text())
        if payload["provenance"]["board_vintage_combined"] != vintage.combined_hash:
            raise UnreconstructibleError(f"{path} is a different vintage")
        input_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        d120_rows.update({_key(r): r for r in payload["rows"]})
    d121_rows = {}
    for path in sorted(Path(a.d121).glob("d121_measured_*.json")):
        payload = json.loads(path.read_text())
        if payload["provenance"]["board_vintage_combined"] != vintage.combined_hash:
            raise UnreconstructibleError(f"{path} is a different vintage")
        input_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        d121_rows.update({_key(r): r for r in payload["rows"]})
    for lg in leagues:
        n = sum(1 for k in d120_rows if k[0] == lg)
        if n != 320:
            raise UnreconstructibleError(f"D120 has {n} states for {lg}, expected 320")
    rows, repro = run_measure(con, leagues, d120_rows, d121_rows)
    for lg in leagues:
        want = sum(1 for k, r in d121_rows.items() if k[0] == lg and r["flow"] in PRIMARY)
        got = sum(1 for r in rows if r["league"] == lg and r["flow"] in PRIMARY)
        if want != got:
            raise UnreconstructibleError(f"D121 primary {want} states, D122 found {got} -- STOP")
    if repro.get("d121_primary_matches", 0) != sum(
        1 for k, r in d121_rows.items() if k[0] in leagues and r["flow"] in PRIMARY
    ):
        raise UnreconstructibleError("not every D121 primary state was reproduced -- STOP")
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
        f"d122_measured_{'_'.join(leagues)}.json",
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
                "d120_d121_inputs": input_hashes,
                "argv": sys.argv,
                **_src_tree(),
            },
        },
    )


if __name__ == "__main__":
    main()
