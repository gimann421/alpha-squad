"""D116 -- did Alpha's survival / opportunity-cost system know which player would disappear first?

Read-only research runner. Opens the database read-only, reuses D115's COMMITTED regret and
timing artifacts (`d115_regret.json`, `d115_timing.json`, produced by
`scripts/research/d115_regret_attribution.py` on the same database), re-walks the same drafts
with D115's own `replay_states`, and re-asks the SHIPPED scoring path (`_pick_by_tier` at
`SHIPPED_TIER`) for the full candidate score list at each state. It writes nothing but JSON under
`--out`. **No file under `src/alpha_squad/` is touched and this script is imported by no
production path.**

    uv run python scripts/research/d115_regret_attribution.py --mode regret --out <dir>
    uv run python scripts/research/d115_regret_attribution.py --mode timing --out <dir>
    uv run python scripts/research/d116_survival_attribution.py --mode measure \
        --in <dir> [--in <dir2>] --out <out>
    uv run python scripts/research/d116_survival_attribution.py --mode report --out <out>

==========================================================================================
PRE-REGISTRATION -- written before any D116 number existed
==========================================================================================

THE QUESTION.  D115 found that 47.3% of per-pick oracle regret sits on "pure sequencing" picks
(C1 AND C2): the oracle's player O survived to Alpha's next pick under the real opponent
sequence, and -- counterfactually -- had Alpha taken O, Alpha's own player A would also have
survived. D116 asks whether Alpha's EXISTING survival / opportunity-cost system knew, ex ante,
which of the two would disappear first. **Attribution only. No weight is tuned, no survival
model is built, no realized outcome becomes a feature, and nothing ships.**

POPULATION.  D115's exact definition, read off D115's own artifacts: C1 is
`C1_oracle_survives_to_next_pick`, C2 is `C2_alpha_survives_if_oracle_taken`, both computed by
D115's committed code. Pairs with O == A carry C2 = None and are excluded, exactly as D115 does.
Seasons 2021-2025, slots (1, 4, 7, 10), 16 rounds, `target_league` (PRIMARY) and `dynasty_1qb`
(replication). Formats are never pooled. Independent unit = SEASON (k = 5), t_crit = 2.776.

EX-ANTE SIGNALS (all read from the shipped engine's own `CandidateScore` at the state BEFORE the
pick; nothing is recomputed from outcomes):

  S   survival probability     `CandidateScore.survival_probability` (Uniform(ecr_best,
                               ecr_worst) at the next pick; None when no dispersion is on file)
  SM  survival multiplier      exactly what the score multiplies by: 1 + 0.3 * (1 - S), and 1.0
                               when S is None. Monotone in S, so it can differ from S only on
                               the None cases -- measured, not assumed.
  OC  opportunity cost         `CandidateScore.opportunity_cost_pts` -- a per-POSITION figure, so
                               it is necessarily TIED for a same-position pair
  R   replay-implied survival  whether the player is still in production's OWN opponent replay
                               (`replay_opponent_picks`, the input `positional_opportunity_cost`
                               computes OC from). Production computes it and reduces it to a
                               positional max; D116 reads the per-player membership it discards.
  SC  combined score           `CandidateScore.score`. Alpha took A, so SC prefers A unless the
                               legality restriction overrode the score (flagged per pick).
  MR  market rank (REFERENCE)  the preseason ECR rank the opponent field itself drafts by. Not an
                               Alpha signal; reported so the survival model's ranking can be read
                               against the ordering the backtest's opponents actually follow.

Each signal makes a pairwise prediction about which of A and O disappears FIRST: the lower
survival (S), the higher multiplier (SM), the higher positional cost (OC), the one missing from
the replay (R), the higher score (SC -- "take this one now"), the better market rank (MR).
Equal values are a TIE and are reported separately, never counted as right or wrong.

GROUND TRUTH -- two horizons, because on C1 AND C2 the first one is constant by construction
------------------------------------------------------------------------------------------------
  H1  NEXT-PICK survival: S_O = C1, S_A = C2. On C1 AND C2 BOTH are True for every pick, so the
      next-pick truth is a tie on every pick in the population, the correct ex-ante statement
      is "both survive", and pairwise ranking accuracy at H1 is UNDEFINED there. D116 reports
      H1 calibration on that population and H1 ranking accuracy on the complementary picks
      where exactly one of the two survived (C1 XOR C2) -- the picks where availability
      prediction at the decision horizon actually bites.
  H2  OPPONENT-EXPOSURE removal order: from the pre-pick state, Alpha passes on every remaining
      turn and the real opponent field (`roster_aware_market_pick`, the same rosters) drafts
      on; the pick at which each of A and O is removed is recorded. "Which disappeared first"
      and "how many opponent picks separated them" are read from this. Symmetric in A and O
      (neither is removed by Alpha), ex post, and never an input to any prediction. Players
      never removed are censored at the end of the draft; both censored is a TIE.

FOLLOW-THROUGH -- the mechanism test.  Taking A first is harmless on a C1 AND C2 pick if Alpha
then takes O at its next pick. D116 records, from the real replay: did Alpha take O at its next
pick; if not, O's rank in Alpha's own score list there; and, by one counterfactual step from the
pre-pick state, what Alpha's shipped engine would have taken at the next pick had it taken O
now (is it A?). This separates "wrong order" from "never gets around to O".

MAGNITUDE.  Predicted survival gap S_O - S_A; the H1 availability difference; the H2 removal gap
in opponent picks; OC_O - OC_A against the ACTUAL positional drop by the next pick in the same
static-VORP units production prices it in (D97's convention; the real next-pick pool with A put
back, so the drop is the opponents' alone), plus a realized-points version labelled HINDSIGHT;
and D115's regret_roster.

WHERE INFORMATION IS LOST.  The shipped score factors exactly as
  score = (value_base + OC) * fit * risk * SM * feasibility
so log(score_A / score_O) splits into additive, fit, risk, SM and feasibility terms that sum to
the whole. The factorisation is CHECKED per candidate against the value_base the engine itself
logs in `CandidateScore.reasons`; a mismatch raises. Reported: how often each term pointed at O, and by how much the
other terms outweighed it. "Would neutralising the term change the choice between these two" is
an attribution of the term's leverage on this pair, not a proposal to change it.

BREAKDOWNS.  Position (O's position, and same- vs cross-position pairs), round, phase
(R1-6 / R7-11 / R12-16), season, and regret tercile within the population.

ADDRESSABLE SHARE.  Potentially addressable = C1 AND C2 regret / total regret (D115's 47.3% on
its vintage). SUPPORTED by the existing survival signal = the part of that regret on picks where
S pointed at O (S_O < S_A); STRICTLY supported = additionally, O really was removed first under
H2. The rest is reported as unexplained. None of these is called "recoverable": "both survived"
is hindsight, and the H1 truth on this population says the order did not matter for availability.

STATISTICS.  Accuracy = correct / (non-tied prediction AND non-tied truth). 95% interval by
season-clustered t (k = 5) and pooled Wilson; MDE against 50% = t_crit * SE. Calibration: Brier
and 10-bin ECE of S against H1 survival, on the population and on a CONTEXT population (every
player in Alpha's top-30 at every non-final state, Alpha's own pick excluded because its H1 truth
is counterfactual).

WHAT D116 MAY NOT DO.  No weight, coefficient or threshold is tuned; no survival model is fitted;
no realized outcome enters a prediction; no production file changes; no arm is recreated.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.draft_forensics import _pick_by_tier
from alpha_squad.evaluation.draft_oracle import (
    SHIPPED_TIER,
    assert_no_realized_inputs_in_policy,
    draft_order,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import (
    picks_until_next_turn,
    replay_opponent_picks,
    roster_aware_market_pick,
)

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
PRIMARY_FORMAT = "target_league"
T_CRIT = 2.776  # k = 5 seasons, df = 4
CONTEXT_TOP_K = 30
#: The shipped survival bonus in `score_candidate` for SHIPPED_TIER (L0). Quoted to reconstruct
#: the multiplier the score actually applied; asserted against the score itself on every pair.
SHIPPED_SURVIVAL_BONUS = 0.3
#: D115's published figures, on ITS vintage -- quoted, never re-derived.
D115_VINTAGE = "0d52543044fe99d6d03a7592190c070bde36a6f465041e2304acdab5b35891e0"
D115_C1C2_SHARE = {"target_league": 47.3, "dynasty_1qb": 52.2}

A_FIRST, O_FIRST, TIE, UNDEFINED = "A_first", "O_first", "tie", "undefined"
SIGNALS = ("S", "SM", "OC", "R", "SC", "MR")
SIGNAL_LABELS = {
    "S": "survival probability",
    "SM": "survival multiplier",
    "OC": "opportunity cost",
    "R": "replay-implied survival (production's own replay, per player)",
    "SC": "combined decision score",
    "MR": "market rank (REFERENCE: the opponent field's own ordering)",
}


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D115 = _load("d115_regret_attribution")


class UnreconstructibleError(RuntimeError):
    """Raised when an input cannot be joined or reproduced without inventing it. D116 stops
    rather than substituting."""


# --------------------------------------------------------------------------------------------
# Pairwise predictions -- pure functions, so each rule can be tested rather than trusted
# --------------------------------------------------------------------------------------------
def lower_goes_first(a: float | None, o: float | None) -> str:
    """For survival-like quantities: the LOWER value is predicted to disappear first."""
    if a is None or o is None:
        return UNDEFINED
    if a == o:
        return TIE
    return A_FIRST if a < o else O_FIRST


def higher_goes_first(a: float | None, o: float | None) -> str:
    """For urgency-like quantities (multiplier, cost, score): the HIGHER is predicted first."""
    if a is None or o is None:
        return UNDEFINED
    if a == o:
        return TIE
    return A_FIRST if a > o else O_FIRST


def survival_multiplier(survival: float | None) -> float:
    """What the shipped L0 score multiplies by -- None is 1.0, exactly as `score_candidate`."""
    return 1.0 if survival is None else 1.0 + SHIPPED_SURVIVAL_BONUS * (1.0 - survival)


def truth_first(removed_a: int | None, removed_o: int | None) -> str:
    """H2 truth from removal indices. None = never removed (censored at the end of the draft)."""
    if removed_a is None and removed_o is None:
        return TIE
    if removed_a is None:
        return O_FIRST
    if removed_o is None:
        return A_FIRST
    if removed_a == removed_o:  # impossible for two distinct players; kept total
        return TIE
    return A_FIRST if removed_a < removed_o else O_FIRST


def truth_next_pick(a_survives: bool | None, o_survives: bool | None) -> str:
    """H1 truth: the one that did NOT survive to the next pick disappeared first."""
    if a_survives is None or o_survives is None:
        return UNDEFINED
    if a_survives == o_survives:
        return TIE
    return O_FIRST if a_survives else A_FIRST


def score_pairs(predictions: list[str], truths: list[str]) -> dict:
    """Accuracy over pairs where BOTH the prediction and the truth are decisive; everything else
    is counted, never dropped silently."""
    if len(predictions) != len(truths):
        raise ValueError("predictions and truths must align")
    n = len(predictions)
    decisive = [
        (p, t)
        for p, t in zip(predictions, truths, strict=True)
        if p in (A_FIRST, O_FIRST) and t in (A_FIRST, O_FIRST)
    ]
    correct = sum(1 for p, t in decisive if p == t)
    return {
        "n": n,
        "n_decisive": len(decisive),
        "n_correct": correct,
        "accuracy": correct / len(decisive) if decisive else None,
        "pred_tie": sum(1 for p in predictions if p == TIE),
        "pred_undefined": sum(1 for p in predictions if p == UNDEFINED),
        "truth_tie": sum(1 for t in truths if t == TIE),
        "pred_tie_rate": (sum(1 for p in predictions if p in (TIE, UNDEFINED)) / n) if n else None,
        "points_at_O": sum(1 for p in predictions if p == O_FIRST),
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def season_clustered(values_by_season: dict[int, float]) -> dict:
    """Mean over seasons, t-interval over k seasons, MDE vs a null of 0 on the same scale."""
    vals = [v for v in values_by_season.values() if v is not None]
    k = len(vals)
    if k == 0:
        return {"k": 0, "mean": None, "ci": None, "mde": None}
    md = mean(vals)
    if k < 2 or stdev(vals) == 0:
        return {"k": k, "mean": md, "ci": None, "mde": None}
    se = stdev(vals) / math.sqrt(k)
    return {"k": k, "mean": md, "ci": (md - T_CRIT * se, md + T_CRIT * se), "mde": T_CRIT * se}


def brier(probs: list[float], outcomes: list[bool]) -> float | None:
    if not probs:
        return None
    return mean((p - float(o)) ** 2 for p, o in zip(probs, outcomes, strict=True))


def ece(probs: list[float], outcomes: list[bool], bins: int = 10) -> tuple[float | None, list]:
    """Expected calibration error with equal-width bins, plus the reliability table."""
    if not probs:
        return None, []
    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for p, o in zip(probs, outcomes, strict=True):
        buckets[min(bins - 1, int(p * bins))].append((p, o))
    total = len(probs)
    err = 0.0
    table = []
    for b in range(bins):
        rows = buckets.get(b, [])
        if not rows:
            continue
        mp = mean(p for p, _ in rows)
        mo = mean(float(o) for _, o in rows)
        err += len(rows) / total * abs(mp - mo)
        table.append({"bin": b, "n": len(rows), "mean_pred": mp, "mean_obs": mo})
    return err, table


def score_parts(c: dict) -> dict:
    """Factor the shipped L0 score into its multiplicative terms, and assert the factorisation
    reproduces the score. `c` is a serialised `CandidateScore`."""
    fit = c["fit_multiplier"]
    risk = c["confidence"] if c["confidence"] is not None else 0.7
    sm = survival_multiplier(c["survival_probability"])
    feas = c["feasibility_multiplier"] if c["feasibility_multiplier"] is not None else 1.0
    product = fit * risk * sm * feas
    oc = c["opportunity_cost_pts"] or 0.0
    if product < 0:
        raise UnreconstructibleError(f"negative multiplier product for {c['player_id']}")
    if product == 0:
        # A zero model confidence zeroes the whole score; the additive term is then not
        # identifiable from the score, so it is reported as unknown rather than guessed.
        return {
            "fit": fit,
            "risk": risk,
            "sm": sm,
            "feas": feas,
            "additive": None,
            "value_base": None,
            "oc": oc,
        }
    additive = c["score"] / product
    # Independent check: the engine logs its own value_base (to 0.1) in `reasons`. If the
    # multiplicative terms above are not the ones the score applied, the implied value_base
    # disagrees with the logged one -- so this is a real test of the factorisation, not a
    # restatement of it.
    logged = logged_value_base(c.get("reasons") or [])
    if logged is not None and abs((additive - oc) - logged) > 0.051 + 1e-9 * abs(logged):
        raise UnreconstructibleError(
            f"score factorisation implies value_base {additive - oc:.3f} but the engine logged "
            f"{logged:.1f} for {c['player_id']}"
        )
    return {
        "fit": fit,
        "risk": risk,
        "sm": sm,
        "feas": feas,
        "additive": additive,
        "value_base": additive - oc,
        "oc": oc,
    }


_VALUE_BASE_RE = re.compile(r"^value_base=\S+ ([+-]\d+(?:\.\d+)?) pts$")


def logged_value_base(reasons: list[str]) -> float | None:
    """The value_base the shipped engine itself wrote into `CandidateScore.reasons`."""
    for reason in reasons:
        m = _VALUE_BASE_RE.match(reason)
        if m:
            return float(m.group(1))
    return None


def log_decomposition(pa: dict, po: dict) -> dict | None:
    """log(score_A / score_O) as a sum of per-term log ratios. None when either additive term is
    non-positive (the multiplicative reading is then undefined)."""
    if pa["additive"] is None or po["additive"] is None:
        return None
    if pa["additive"] <= 0 or po["additive"] <= 0 or pa["risk"] <= 0 or po["risk"] <= 0:
        return None
    return {
        "additive": math.log(pa["additive"] / po["additive"]),
        "fit": math.log(pa["fit"] / po["fit"]),
        "risk": math.log(pa["risk"] / po["risk"]),
        "survival": math.log(pa["sm"] / po["sm"]),
        "feasibility": math.log(pa["feas"] / po["feas"]),
    }


def positional_drop(pool_now: set[str], pool_next: set[str], positions, value, position) -> float:
    """`max(0, best now) - max(0, best at next turn)` at one position -- the same clamped form
    `positional_opportunity_cost` prices, applied to the pool that actually existed."""
    best_now = max(
        (value[p] for p in pool_now if positions.get(p) == position and p in value), default=0.0
    )
    best_next = max(
        (value[p] for p in pool_next if positions.get(p) == position and p in value), default=0.0
    )
    return max(0.0, best_now) - max(0.0, best_next)


def regret_tercile(value: float, cuts: tuple[float, float]) -> str:
    if value <= cuts[0]:
        return "T1 low"
    if value <= cuts[1]:
        return "T2 mid"
    return "T3 high"


# --------------------------------------------------------------------------------------------
# Draft mechanics -- opponent exposure and the one-step counterfactual
# --------------------------------------------------------------------------------------------
def opponent_exposure(state: dict, static, league, slot: int, players: tuple[str, ...]) -> dict:
    """H2: from the PRE-pick state, Alpha passes on every remaining turn and the real opponent
    field drafts on. Returns {player: (overall pick removed, opponent-pick index)} with None for
    a player never removed. Neither player is removed by Alpha, so the comparison is symmetric."""
    total_rounds = int(league.roster.get("roster_size", 0))
    avail = set(state["available"])
    opps = {s: list(v) for s, v in state["opponents"].items()}
    removed: dict[str, tuple[int, int] | None] = dict.fromkeys(players)
    index = 0
    for current, round_no, seat in draft_order(league):
        if current <= state["overall_pick"] or seat == slot:
            continue
        if not avail:
            break
        pick = roster_aware_market_pick(
            avail,
            static.market_rank,
            static.positions,
            league,
            opps[seat],
            total_rounds - round_no + 1,
        )
        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
        avail.discard(pick)
        index += 1
        if pick in removed and removed[pick] is None:
            removed[pick] = (current, index)
        if all(v is not None for v in removed.values()):
            break
    return removed


def opponent_picks_remaining(state: dict, league, slot: int) -> int:
    """Opponent picks left in the draft after this state -- the censoring horizon for H2."""
    return sum(
        1
        for current, _, seat in draft_order(league)
        if current > state["overall_pick"] and seat != slot
    )


def counterfactual_next_pick(con, league, season, static, slot: int, state: dict, taken: str):
    """Had Alpha taken `taken` now, what does the SHIPPED engine take at Alpha's next pick?
    Opponents are stepped exactly as D115's `survives_counterfactual` steps them."""
    next_pick = state["next_pick"]
    if next_pick is None:
        return None, None
    total_rounds = int(league.roster.get("roster_size", 0))
    my_picks = [snake_overall_pick(r, slot, league.teams) for r in range(1, total_rounds + 1)]
    avail = set(state["available"]) - {taken}
    opps = {s: list(v) for s, v in state["opponents"].items()}
    next_round = None
    for current, round_no, seat in draft_order(league):
        if current == next_pick:
            next_round = round_no
        if current <= state["overall_pick"] or current >= next_pick or seat == slot:
            continue
        if not avail:
            break
        pick = roster_aware_market_pick(
            avail,
            static.market_rank,
            static.positions,
            league,
            opps[seat],
            total_rounds - round_no + 1,
        )
        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
        avail.discard(pick)
    drafted = [*state["drafted"], taken]
    following = next((p for p in my_picks if p > next_pick), None)
    pick, _ = _pick_by_tier(
        static,
        con,
        league,
        season,
        set(avail),
        [static.positions.get(p, "UNKNOWN") for p in drafted],
        SHIPPED_TIER,
        next_pick,
        following,
        roster_player_ids=list(drafted),
        picks_remaining=total_rounds - next_round + 1,
    )
    return pick, avail


def _candidate_dict(c) -> dict:
    return {
        "player_id": c.player_id,
        "position": c.position,
        "projection": c.projection,
        "vorp": c.vorp,
        "fit_multiplier": c.fit_multiplier,
        "confidence": c.confidence,
        "survival_probability": c.survival_probability,
        "feasibility_multiplier": c.feasibility_multiplier,
        "opportunity_cost_pts": c.opportunity_cost_pts,
        "marginal_starter_value": c.marginal_starter_value,
        "score": c.score,
        "reasons": list(c.reasons),
    }


def scored_states(con, league, season, static, slot) -> list[dict]:
    """D115's own `replay_states`, plus the FULL shipped score list at each state.

    `replay_states` keeps only the chosen player's components; D116 needs the oracle player's
    too. `_pick_by_tier` is re-asked at the identical state -- the engine is deterministic -- and
    the runner raises if it does not return the same pick the replay recorded."""
    states = D115.replay_states(con, league, season, static, slot)
    for state in states:
        pick, scored = _pick_by_tier(
            static,
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
        if pick != state["alpha_pick"]:
            raise UnreconstructibleError(
                f"re-scoring chose {pick!r} but the replay chose {state['alpha_pick']!r} at "
                f"{season} slot {slot} pick {state['overall_pick']}"
            )
        state["scored"] = {c.player_id: _candidate_dict(c) for c in scored}
        state["ranked"] = [c.player_id for c in scored]
    return states


def o_fate(states: list[dict], index: int, oracle: str) -> str:
    """What happened to the oracle's player in the REAL draft after Alpha took its own man."""
    for j in range(index + 1, len(states)):
        if oracle not in states[j]["available"]:
            return "opponent_took_O"
        if states[j]["alpha_pick"] == oracle:
            return "alpha_took_O_next" if j == index + 1 else "alpha_took_O_later"
    return "O_still_available_at_alpha_last_pick"


# --------------------------------------------------------------------------------------------
# MODE: measure
# --------------------------------------------------------------------------------------------
def _load_d115(dirs: list[Path]) -> tuple[list[dict], list[dict], list[dict]]:
    regret, timing, prov = [], [], []
    for d in dirs:
        r = json.loads((d / "d115_regret.json").read_text())
        t = json.loads((d / "d115_timing.json").read_text())
        regret.extend(r["rows"])
        timing.extend(t["rows"])
        prov.append(
            {
                "dir": str(d),
                "regret_sha256": hashlib.sha256((d / "d115_regret.json").read_bytes()).hexdigest(),
                "timing_sha256": hashlib.sha256((d / "d115_timing.json").read_bytes()).hexdigest(),
                "regret_vintage": r["provenance"]["board_vintage_combined"],
                "timing_vintage": t["provenance"]["board_vintage_combined"],
                "regret_git_head": r["provenance"]["git_head"],
            }
        )
    vintages = {p["regret_vintage"] for p in prov} | {p["timing_vintage"] for p in prov}
    if len(vintages) != 1:
        raise UnreconstructibleError(f"D115 artifacts span more than one vintage: {vintages}")
    return regret, timing, prov


def run_measure(con, dirs: list[Path], slots) -> tuple[list[dict], list[dict], dict]:
    regret_rows, timing_rows, prov = _load_d115(dirs)
    by_key = {(r["league"], r["season"], r["slot"], r["overall_pick"]): r for r in regret_rows}
    tim_key = {(r["league"], r["season"], r["slot"], r["overall_pick"]): r for r in timing_rows}
    formats = [f for f in FORMATS if any(r["league"] == f for r in regret_rows)]
    pairs: list[dict] = []
    context: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            realized = _actual_points_for(con, season, sorted(static.projections))
            realized_vorp = {
                p: realized.get(p, 0.0) - static.replacement_levels.get(static.positions[p], 0.0)
                for p in static.projections
                if p in static.positions
            }
            for slot in slots:
                states = scored_states(con, league, season, static, slot)
                for i, state in enumerate(states):
                    key = (league_name, season, slot, state["overall_pick"])
                    row, tim = by_key.get(key), tim_key.get(key)
                    if row is None or tim is None:
                        raise UnreconstructibleError(f"no D115 row for {key}")
                    if row["alpha_player"] != state["alpha_pick"]:
                        raise UnreconstructibleError(
                            f"D115 has {row['alpha_player']!r} at {key}, replay "
                            f"{state['alpha_pick']!r} -- not the same draft"
                        )
                    if i + 1 >= len(states):
                        continue  # last pick: no next pick, excluded exactly as D115 does
                    nxt = states[i + 1]
                    a, o = state["alpha_pick"], row["oracle_player"]
                    n_opp = picks_until_next_turn(state["overall_pick"], state["next_pick"])
                    replay_left = replay_opponent_picks(
                        state["available"], static.market_rank, n_opp
                    )

                    # ---- context calibration population: Alpha's top-K, own pick excluded
                    for pid in state["ranked"][:CONTEXT_TOP_K]:
                        if pid == a:
                            continue
                        surv = state["scored"][pid]["survival_probability"]
                        context.append(
                            {
                                "league": league_name,
                                "season": season,
                                "round": state["round"],
                                "n_opp": n_opp,
                                "survival": surv,
                                "replay_survives": pid in replay_left,
                                "survived": pid in nxt["available"],
                            }
                        )

                    if o == a:
                        continue
                    ca, co = state["scored"].get(a), state["scored"].get(o)
                    if ca is None or co is None:
                        raise UnreconstructibleError(f"no shipped score for the pair at {key}")
                    pa, po = score_parts(ca), score_parts(co)
                    exposure = opponent_exposure(state, static, league, slot, (a, o))
                    rem_a, rem_o = exposure[a], exposure[o]
                    cf_pick, cf_avail = counterfactual_next_pick(
                        con, league, season, static, slot, state, o
                    )
                    c2 = tim["C2_alpha_survives_if_oracle_taken"]
                    if cf_avail is not None and c2 is not None and (a in cf_avail) != c2:
                        raise UnreconstructibleError(
                            f"counterfactual step disagrees with D115's C2 at {key}"
                        )
                    pool_next_opp = set(nxt["available"]) | {a}
                    pos_a, pos_o = ca["position"], co["position"]
                    mr = static.market_rank
                    o_next = nxt["scored"].get(o)
                    pairs.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "round": state["round"],
                            "phase": D115._phase_of(state["round"]),
                            "overall_pick": state["overall_pick"],
                            "next_pick": state["next_pick"],
                            "n_opp_picks_to_next": n_opp,
                            "alpha": a,
                            "oracle": o,
                            "alpha_position": pos_a,
                            "oracle_position": pos_o,
                            "same_position": pos_a == pos_o,
                            "category": row["category"],
                            "regret_roster": row["regret_roster"],
                            "alpha_projection": row["alpha_projection"],
                            "alpha_realized": row["alpha_realized"],
                            "oracle_projection": row["oracle_projection"],
                            "oracle_realized": row["oracle_realized"],
                            "regret_raw": row["regret_raw"],
                            "C1": tim["C1_oracle_survives_to_next_pick"],
                            "C2": c2,
                            # ---- ex ante (shipped engine, pre-pick state)
                            "S_A": ca["survival_probability"],
                            "S_O": co["survival_probability"],
                            "SM_A": pa["sm"],
                            "SM_O": po["sm"],
                            "OC_A": pa["oc"],
                            "OC_O": po["oc"],
                            "R_A": a in replay_left,
                            "R_O": o in replay_left,
                            "SC_A": ca["score"],
                            "SC_O": co["score"],
                            "MR_A": mr[a][1] if a in mr else None,
                            "MR_O": mr[o][1] if o in mr else None,
                            "ecr_range_A": static.ecr_dispersion.get(a),
                            "ecr_range_O": static.ecr_dispersion.get(o),
                            "parts_A": pa,
                            "parts_O": po,
                            "alpha_rank_of_O": state["ranked"].index(o) + 1,
                            "legality_override": state["ranked"][0] != a,
                            # ---- ex post
                            "n_opp_remaining": opponent_picks_remaining(state, league, slot),
                            "removed_A": rem_a,
                            "removed_O": rem_o,
                            "o_fate": o_fate(states, i, o),
                            "alpha_next_pick": nxt["alpha_pick"],
                            "alpha_took_O_next": nxt["alpha_pick"] == o,
                            "O_rank_at_next": (
                                nxt["ranked"].index(o) + 1 if o in nxt["ranked"] else None
                            ),
                            "O_score_at_next": None if o_next is None else o_next["score"],
                            "next_pick_score": nxt["scored"][nxt["alpha_pick"]]["score"],
                            "cf_next_pick": cf_pick,
                            "cf_takes_A_next": cf_pick == a,
                            "drop_vorp_A_pos": positional_drop(
                                state["available"],
                                pool_next_opp,
                                static.positions,
                                static.vorp,
                                pos_a,
                            ),
                            "drop_vorp_O_pos": positional_drop(
                                state["available"],
                                pool_next_opp,
                                static.positions,
                                static.vorp,
                                pos_o,
                            ),
                            "drop_realized_A_pos": positional_drop(
                                state["available"],
                                pool_next_opp,
                                static.positions,
                                realized_vorp,
                                pos_a,
                            ),
                            "drop_realized_O_pos": positional_drop(
                                state["available"],
                                pool_next_opp,
                                static.positions,
                                realized_vorp,
                                pos_o,
                            ),
                        }
                    )
                print(
                    f"  measure {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return pairs, context, {"d115_inputs": prov}


# --------------------------------------------------------------------------------------------
# Derived columns and reporting
# --------------------------------------------------------------------------------------------
def predictions(p: dict) -> dict[str, str]:
    return {
        "S": lower_goes_first(p["S_A"], p["S_O"]),
        "SM": higher_goes_first(p["SM_A"], p["SM_O"]),
        "OC": higher_goes_first(p["OC_A"], p["OC_O"]),
        "R": lower_goes_first(float(p["R_A"]), float(p["R_O"])),
        "SC": higher_goes_first(p["SC_A"], p["SC_O"]),
        "MR": lower_goes_first(p["MR_A"], p["MR_O"]),
    }


def h2_truth(p: dict) -> str:
    return truth_first(
        None if p["removed_A"] is None else p["removed_A"][1],
        None if p["removed_O"] is None else p["removed_O"][1],
    )


def h2_separation(p: dict) -> int:
    """Opponent picks between the two removals (O minus A); a player never removed is placed one
    past the last opponent pick of the draft."""
    end = p["n_opp_remaining"] + 1
    ia = p["removed_A"][1] if p["removed_A"] is not None else end
    io = p["removed_O"][1] if p["removed_O"] is not None else end
    return io - ia


def is_c1c2(p: dict) -> bool:
    return bool(p["C1"]) and bool(p["C2"])


def signal_table(rows: list[dict], truth_fn) -> dict:
    out = {}
    for sig in SIGNALS:
        preds = [predictions(r)[sig] for r in rows]
        truths = [truth_fn(r) for r in rows]
        res = score_pairs(preds, truths)
        per_season: dict[int, float] = {}
        for season in BACKTEST_SEASONS:
            sub = [r for r in rows if r["season"] == season]
            s = score_pairs([predictions(r)[sig] for r in sub], [truth_fn(r) for r in sub])
            if s["accuracy"] is not None:
                per_season[season] = s["accuracy"]
        res["per_season"] = per_season
        res["season_clustered"] = season_clustered(per_season)
        res["wilson"] = wilson(res["n_correct"], res["n_decisive"])
        out[sig] = res
    return out


def _fmt_acc(res: dict) -> str:
    if res["accuracy"] is None:
        return "undefined (no decisive pairs)"
    w = res["wilson"]
    sc = res["season_clustered"]
    ci = "" if sc["ci"] is None else f" season-CI [{sc['ci'][0]:.0%}, {sc['ci'][1]:.0%}]"
    return (
        f"{res['accuracy']:.1%} ({res['n_correct']}/{res['n_decisive']}) "
        f"Wilson [{w[0]:.0%}, {w[1]:.0%}]{ci}"
    )


def summarise_population(rows: list[dict], total_regret: float) -> dict:
    """The primary deliverable table for one population."""
    s_members = [(r["S_A"], r["C2"]) for r in rows] + [(r["S_O"], r["C1"]) for r in rows]
    probs = [s for s, _ in s_members if s is not None]
    outs = [bool(o) for s, o in s_members if s is not None]
    cal_ece, _ = ece(probs, outs)
    gaps = [r["S_O"] - r["S_A"] for r in rows if r["S_O"] is not None and r["S_A"] is not None]
    oc_gap = [r["OC_O"] - r["OC_A"] for r in rows]
    drop_gap = [r["drop_vorp_O_pos"] - r["drop_vorp_A_pos"] for r in rows]
    drop_gap_real = [r["drop_realized_O_pos"] - r["drop_realized_A_pos"] for r in rows]
    h1_diff = [float(bool(r["C1"])) - float(bool(r["C2"])) for r in rows]
    h2_sep = [h2_separation(r) for r in rows]
    regret = [r["regret_roster"] for r in rows]
    per_season_regret = defaultdict(list)
    for r in rows:
        per_season_regret[r["season"]].append(r["regret_roster"])
    return {
        "n": len(rows),
        "share_of_total_regret": sum(regret) / total_regret if total_regret else None,
        "mean_regret": mean(regret) if regret else None,
        "regret_season_ci": season_clustered({s: mean(v) for s, v in per_season_regret.items()}),
        "S_undefined_members": sum(1 for s, _ in s_members if s is None),
        "calibration_brier_H1": brier(probs, outs),
        "calibration_ece_H1": cal_ece,
        "mean_S": mean(probs) if probs else None,
        "mean_observed_H1": mean(float(o) for o in outs) if outs else None,
        "mean_pred_survival_gap_O_minus_A": mean(gaps) if gaps else None,
        "mean_abs_pred_survival_gap": mean(abs(g) for g in gaps) if gaps else None,
        "mean_H1_availability_diff_O_minus_A": mean(h1_diff) if h1_diff else None,
        "mean_H2_removal_gap_opp_picks_O_minus_A": mean(h2_sep) if h2_sep else None,
        "median_abs_H2_gap": sorted(abs(x) for x in h2_sep)[len(h2_sep) // 2] if h2_sep else None,
        "mean_OC_gap_O_minus_A": mean(oc_gap) if oc_gap else None,
        "mean_actual_drop_gap_vorp_O_minus_A": mean(drop_gap) if drop_gap else None,
        "mean_actual_drop_gap_realized_O_minus_A_HINDSIGHT": mean(drop_gap_real)
        if drop_gap_real
        else None,
        "H2": signal_table(rows, h2_truth),
        "S_agrees_with_MR": _agreement(rows, "S", "MR"),
        "R_agrees_with_MR": _agreement(rows, "R", "MR"),
    }


def _agreement(rows: list[dict], x: str, y: str) -> dict:
    """How often two signals make the same decisive call, over pairs where both are decisive."""
    both = [
        (predictions(r)[x], predictions(r)[y])
        for r in rows
        if predictions(r)[x] in (A_FIRST, O_FIRST) and predictions(r)[y] in (A_FIRST, O_FIRST)
    ]
    return {
        "n_both_decisive": len(both),
        "agree": sum(1 for a, b in both if a == b),
        "rate": sum(1 for a, b in both if a == b) / len(both) if both else None,
    }


def follow_through(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    fates = defaultdict(int)
    for r in rows:
        fates[r["o_fate"]] += 1
    not_taken = [r for r in rows if not r["alpha_took_O_next"]]
    ranks = sorted(r["O_rank_at_next"] for r in not_taken if r["O_rank_at_next"] is not None)
    return {
        "n": n,
        "alpha_took_O_next": sum(1 for r in rows if r["alpha_took_O_next"]),
        "o_fate": dict(fates),
        "cf_takes_A_next": sum(1 for r in rows if r["cf_takes_A_next"]),
        "passed_on_O_next_and_cf_takes_A": sum(
            1 for r in rows if not r["alpha_took_O_next"] and r["cf_takes_A_next"]
        ),
        "median_O_rank_at_next_when_passed": ranks[len(ranks) // 2] if ranks else None,
        "O_rank_at_next_distribution": {
            "1": sum(1 for x in ranks if x == 1),
            "2-3": sum(1 for x in ranks if 2 <= x <= 3),
            "4-10": sum(1 for x in ranks if 4 <= x <= 10),
            ">10": sum(1 for x in ranks if x > 10),
        },
        "regret_when_took_O_next": mean(r["regret_roster"] for r in rows if r["alpha_took_O_next"])
        if any(r["alpha_took_O_next"] for r in rows)
        else None,
        "regret_when_passed_on_O_next": mean(r["regret_roster"] for r in not_taken)
        if not_taken
        else None,
    }


def information_loss(rows: list[dict]) -> dict:
    """Which terms pointed at O, how often they were outweighed, and by what."""
    out: dict = {"n": len(rows)}
    decomp = [(r, log_decomposition(r["parts_A"], r["parts_O"])) for r in rows]
    valid = [(r, d) for r, d in decomp if d is not None]
    out["n_decomposable"] = len(valid)
    out["legality_override"] = sum(1 for r in rows if r["legality_override"])
    for term in ("additive", "fit", "risk", "survival", "feasibility"):
        toward_o = [d[term] for _, d in valid if d[term] < 0]
        toward_a = [d[term] for _, d in valid if d[term] > 0]
        out[term] = {
            "points_at_O": len(toward_o),
            "points_at_A": len(toward_a),
            "neutral": len(valid) - len(toward_o) - len(toward_a),
            "mean_log_ratio_A_over_O": mean(d[term] for _, d in valid) if valid else None,
            "mean_log_when_at_O": mean(toward_o) if toward_o else None,
        }
    # Survival's leverage on THIS pair: neutralise SM for both; does O then outscore A?
    flips_s = sum(1 for _, d in valid if sum(d.values()) - d["survival"] < 0)
    flips_oc = 0
    for r in rows:
        pa, po = r["parts_A"], r["parts_O"]
        if pa["value_base"] is None or po["value_base"] is None:
            continue
        sa = pa["value_base"] * pa["fit"] * pa["risk"] * pa["sm"] * pa["feas"]
        so = po["value_base"] * po["fit"] * po["risk"] * po["sm"] * po["feas"]
        if so > sa:
            flips_oc += 1
    out["survival_neutralised_O_wins"] = flips_s
    out["opp_cost_neutralised_O_wins"] = flips_oc
    at_o = [(r, d) for r, d in valid if d["survival"] < 0]
    out["survival_points_at_O_but_outweighed"] = {
        "n": len(at_o),
        "mean_survival_log": mean(d["survival"] for _, d in at_o) if at_o else None,
        "mean_total_log": mean(sum(d.values()) for _, d in at_o) if at_o else None,
        "mean_additive_log": mean(d["additive"] for _, d in at_o) if at_o else None,
    }
    vb_gap = [
        r["parts_A"]["value_base"] - r["parts_O"]["value_base"]
        for r in rows
        if r["parts_A"]["value_base"] is not None and r["parts_O"]["value_base"] is not None
    ]
    oc_gap = [r["parts_A"]["oc"] - r["parts_O"]["oc"] for r in rows]
    out["mean_value_base_gap_A_minus_O_pts"] = mean(vb_gap) if vb_gap else None
    out["mean_opp_cost_gap_A_minus_O_pts"] = mean(oc_gap) if oc_gap else None
    out["max_survival_log_leverage"] = math.log(1 + SHIPPED_SURVIVAL_BONUS)
    out["share_with_total_gap_within_survival_range"] = (
        sum(1 for _, d in valid if sum(d.values()) < math.log(1 + SHIPPED_SURVIVAL_BONUS))
        / len(valid)
        if valid
        else None
    )
    return out


def _median(xs: list[float]) -> float | None:
    xs = sorted(xs)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def who_is_o(rows: list[dict]) -> dict:
    """Who the oracle's player is on these picks, in the engine's own (ex-ante) terms, beside
    what happened (ex post, labelled). Answers whether "wrong order" is really about order."""
    ranks = [r["alpha_rank_of_O"] for r in rows]
    mr_lag = [r["MR_O"] - r["overall_pick"] for r in rows if r["MR_O"] is not None]
    mr_lag_a = [r["MR_A"] - r["overall_pick"] for r in rows if r["MR_A"] is not None]
    return {
        "n": len(rows),
        "median_alpha_rank_of_O_at_pick": _median(ranks),
        "alpha_rank_of_O_at_pick": {
            "2": sum(1 for x in ranks if x == 2),
            "3-5": sum(1 for x in ranks if 3 <= x <= 5),
            "6-10": sum(1 for x in ranks if 6 <= x <= 10),
            ">10": sum(1 for x in ranks if x > 10),
        },
        "O_value_base_nonpositive": sum(
            1 for r in rows if r["parts_O"]["additive"] is None or r["parts_O"]["additive"] <= 0
        ),
        "O_no_market_rank": sum(1 for r in rows if r["MR_O"] is None),
        "median_O_market_rank_minus_pick": _median(mr_lag),
        "median_A_market_rank_minus_pick": _median(mr_lag_a),
        "O_market_rank_beyond_next_pick": sum(
            1 for r in rows if r["MR_O"] is None or r["MR_O"] > r["next_pick"]
        ),
        "mean_O_projection": mean(r["oracle_projection"] for r in rows) if rows else None,
        "mean_A_projection": mean(r["alpha_projection"] for r in rows) if rows else None,
        "mean_O_realized_HINDSIGHT": mean(r["oracle_realized"] for r in rows) if rows else None,
        "mean_A_realized_HINDSIGHT": mean(r["alpha_realized"] for r in rows) if rows else None,
        "O_outperformed_projection_by_HINDSIGHT": mean(
            r["oracle_realized"] - r["oracle_projection"] for r in rows
        )
        if rows
        else None,
        "A_outperformed_projection_by_HINDSIGHT": mean(
            r["alpha_realized"] - r["alpha_projection"] for r in rows
        )
        if rows
        else None,
    }


def breakdown(rows: list[dict], field_fn, order=None) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(field_fn(r))].append(r)
    keys = order or sorted(groups)
    out = {}
    for k in keys:
        sub = groups.get(k, [])
        if not sub:
            continue
        s = score_pairs([predictions(r)["S"] for r in sub], [h2_truth(r) for r in sub])
        oc = score_pairs([predictions(r)["OC"] for r in sub], [h2_truth(r) for r in sub])
        sc = score_pairs([predictions(r)["SC"] for r in sub], [h2_truth(r) for r in sub])
        rr = score_pairs([predictions(r)["R"] for r in sub], [h2_truth(r) for r in sub])
        out[k] = {
            "n": len(sub),
            "regret": sum(r["regret_roster"] for r in sub),
            "mean_regret": mean(r["regret_roster"] for r in sub),
            "S_acc": s["accuracy"],
            "S_decisive": s["n_decisive"],
            "S_points_at_O": s["points_at_O"],
            "S_tie_rate": s["pred_tie_rate"],
            "OC_acc": oc["accuracy"],
            "OC_decisive": oc["n_decisive"],
            "SC_acc": sc["accuracy"],
            "R_acc": rr["accuracy"],
            "R_decisive": rr["n_decisive"],
            "O_first_H2": sum(1 for r in sub if h2_truth(r) == O_FIRST),
            "took_O_next": sum(1 for r in sub if r["alpha_took_O_next"]),
            "mean_S_gap_O_minus_A": mean(
                r["S_O"] - r["S_A"] for r in sub if r["S_O"] is not None and r["S_A"] is not None
            )
            if any(r["S_O"] is not None and r["S_A"] is not None for r in sub)
            else None,
        }
    return out


def addressable(pop: list[dict], total_regret: float) -> dict:
    tot = sum(r["regret_roster"] for r in pop)
    s_at_o = [r for r in pop if predictions(r)["S"] == O_FIRST]
    strict = [r for r in s_at_o if h2_truth(r) == O_FIRST]
    r_at_o = [r for r in pop if predictions(r)["R"] == O_FIRST]
    oc_at_o = [r for r in pop if predictions(r)["OC"] == O_FIRST]
    any_at_o = [
        r
        for r in pop
        if O_FIRST in (predictions(r)["S"], predictions(r)["R"], predictions(r)["OC"])
    ]

    def pct(rows):
        return 100 * sum(r["regret_roster"] for r in rows) / total_regret if total_regret else None

    return {
        "potentially_addressable_pct_of_total": pct(pop),
        "survival_points_at_O_pct_of_total": pct(s_at_o),
        "survival_points_at_O_and_O_first_H2_pct_of_total": pct(strict),
        "replay_points_at_O_pct_of_total": pct(r_at_o),
        "opp_cost_points_at_O_pct_of_total": pct(oc_at_o),
        "any_signal_points_at_O_pct_of_total": pct(any_at_o),
        "unexplained_pct_of_total": pct(pop) - pct(any_at_o) if total_regret else None,
        "population_regret": tot,
        "n": len(pop),
        "n_survival_points_at_O": len(s_at_o),
        "n_strict": len(strict),
    }


def context_calibration(ctx: list[dict]) -> dict:
    with_s = [c for c in ctx if c["survival"] is not None]
    probs = [c["survival"] for c in with_s]
    outs = [c["survived"] for c in with_s]
    e, table = ece(probs, outs)
    replay_acc = mean(float(c["replay_survives"] == c["survived"]) for c in ctx) if ctx else None
    zero_but_survived = sum(1 for c in with_s if c["survival"] == 0.0 and c["survived"])
    zero = sum(1 for c in with_s if c["survival"] == 0.0)
    one_but_gone = sum(1 for c in with_s if c["survival"] == 1.0 and not c["survived"])
    one = sum(1 for c in with_s if c["survival"] == 1.0)
    return {
        "n": len(ctx),
        "n_with_S": len(with_s),
        "brier": brier(probs, outs),
        "ece": e,
        "reliability": table,
        "mean_S": mean(probs) if probs else None,
        "observed_survival_rate": mean(float(o) for o in outs) if outs else None,
        "replay_membership_accuracy": replay_acc,
        "S_eq_0_count": zero,
        "S_eq_0_but_survived": zero_but_survived,
        "S_eq_1_count": one,
        "S_eq_1_but_gone": one_but_gone,
    }


def _pct_or_dash(x: float | None) -> str:
    return "   --" if x is None else f"{x:>6.0%}"


def _src_tree() -> dict:
    """Proof that production is untouched: the committed tree hash of `src/alpha_squad` and
    whether the working copy differs from it."""

    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()

    return {
        "src_tree_hash_at_head": run(["git", "rev-parse", "HEAD:src/alpha_squad"]),
        "src_dirty": bool(run(["git", "status", "--porcelain", "--", "src/alpha_squad"])),
    }


def report(pairs: list[dict], context: list[dict], regret_rows: list[dict]) -> dict:
    bar = "=" * 100
    summary: dict = {"formats": {}}
    for league_name in FORMATS:
        sub = [p for p in pairs if p["league"] == league_name]
        if not sub:
            continue
        total = sum(r["regret_roster"] for r in regret_rows if r["league"] == league_name)
        pop = [p for p in sub if is_c1c2(p)]
        xor = [p for p in sub if bool(p["C1"]) != bool(p["C2"]) and p["C2"] is not None]
        entry = summary["formats"].setdefault(league_name, {})
        print(f"\n{bar}\nD116 -- {league_name}  ({len(sub)} non-final pairs with O != A)\n{bar}")

        prim = summarise_population(pop, total)
        entry["c1c2"] = prim
        print(
            f"  C1 AND C2 population: {prim['n']} picks, "
            f"{100 * prim['share_of_total_regret']:.1f}% of total regret "
            f"(D115 on {D115_VINTAGE[:8]}: {D115_C1C2_SHARE[league_name]}%)"
        )
        print(f"  mean regret/pick {prim['mean_regret']:.1f}  season CI {prim['regret_season_ci']}")
        print(
            f"  H1 calibration on the population (truth = 1 for every member): Brier "
            f"{prim['calibration_brier_H1']:.3f}  ECE {prim['calibration_ece_H1']:.3f}  mean S "
            f"{prim['mean_S']:.3f} vs observed {prim['mean_observed_H1']:.3f}"
        )
        print(
            f"  predicted survival gap S_O - S_A: mean {prim['mean_pred_survival_gap_O_minus_A']:+.3f}"
            f"  |gap| {prim['mean_abs_pred_survival_gap']:.3f}   H1 actual diff "
            f"{prim['mean_H1_availability_diff_O_minus_A']:+.3f}   H2 removal gap "
            f"{prim['mean_H2_removal_gap_opp_picks_O_minus_A']:+.1f} opp picks "
            f"(median |gap| {prim['median_abs_H2_gap']})"
        )
        print(
            f"  opp-cost gap OC_O - OC_A {prim['mean_OC_gap_O_minus_A']:+.2f}  vs actual drop "
            f"gap (VORP) {prim['mean_actual_drop_gap_vorp_O_minus_A']:+.2f}  (realized, "
            f"HINDSIGHT) {prim['mean_actual_drop_gap_realized_O_minus_A_HINDSIGHT']:+.2f}"
        )
        print("  H2 pairwise ranking (which disappears first under the opponent field):")
        for sig in SIGNALS:
            res = prim["H2"][sig]
            print(
                f"    {sig:<3}{SIGNAL_LABELS[sig]:<62}{_fmt_acc(res)}  ties/undef "
                f"{res['pred_tie'] + res['pred_undefined']}/{res['n']}  "
                f"points at O {res['points_at_O']}"
            )
        h2_counts = defaultdict(int)
        for p in pop:
            h2_counts[h2_truth(p)] += 1
        entry["c1c2_H2_truth_counts"] = dict(h2_counts)
        print(f"  H2 truth counts: {dict(h2_counts)}")

        # H1 ranking where it is defined: exactly one of the two survived.
        h1 = {}
        for sig in SIGNALS:
            preds = [predictions(r)[sig] for r in xor]
            truths = [truth_next_pick(r["C2"], r["C1"]) for r in xor]
            res = score_pairs(preds, truths)
            per_season = {}
            for season in BACKTEST_SEASONS:
                ss = [r for r in xor if r["season"] == season]
                sres = score_pairs(
                    [predictions(r)[sig] for r in ss],
                    [truth_next_pick(r["C2"], r["C1"]) for r in ss],
                )
                if sres["accuracy"] is not None:
                    per_season[season] = sres["accuracy"]
            res["season_clustered"] = season_clustered(per_season)
            res["wilson"] = wilson(res["n_correct"], res["n_decisive"])
            h1[sig] = res
        entry["xor_H1"] = h1
        entry["xor_n"] = len(xor)
        entry["xor_regret_pct"] = (
            100 * sum(r["regret_roster"] for r in xor) / total if total else None
        )
        print(
            f"\n  CONTRAST: C1 XOR C2 ({len(xor)} picks, {entry['xor_regret_pct']:.1f}% of regret)"
            " -- H1 ranking where exactly one survived:"
        )
        for sig in SIGNALS:
            print(f"    {sig:<3}{SIGNAL_LABELS[sig]:<62}{_fmt_acc(h1[sig])}")
        entry["xor_H2"] = signal_table(xor, h2_truth)

        entry["follow_through"] = follow_through(pop)
        ft = entry["follow_through"]
        print(
            f"\n  FOLLOW-THROUGH on C1 AND C2: Alpha took O at its next pick "
            f"{ft['alpha_took_O_next']}/{ft['n']}; O's fate {ft['o_fate']}; "
            f"counterfactual engine takes A next {ft['cf_takes_A_next']}/{ft['n']}; "
            f"median O rank at next pick when passed {ft['median_O_rank_at_next_when_passed']} "
            f"{ft['O_rank_at_next_distribution']}"
        )
        print(
            f"    regret when O taken next {ft['regret_when_took_O_next']}  when passed "
            f"{ft['regret_when_passed_on_O_next']}"
        )

        entry["who_is_O"] = who_is_o(pop)
        w = entry["who_is_O"]
        print(
            f"\n  WHO IS O on C1 AND C2: Alpha's rank of O at the pick median "
            f"{w['median_alpha_rank_of_O_at_pick']} {w['alpha_rank_of_O_at_pick']}; O value base "
            f"<= 0 {w['O_value_base_nonpositive']}/{w['n']}; O has no market rank "
            f"{w['O_no_market_rank']}; O market rank beyond Alpha's next pick "
            f"{w['O_market_rank_beyond_next_pick']}/{w['n']}; median market-rank lag O "
            f"{w['median_O_market_rank_minus_pick']} vs A {w['median_A_market_rank_minus_pick']}"
        )
        print(
            f"    projection O {w['mean_O_projection']:.1f} vs A {w['mean_A_projection']:.1f}; "
            f"realized (HINDSIGHT) O {w['mean_O_realized_HINDSIGHT']:.1f} vs A "
            f"{w['mean_A_realized_HINDSIGHT']:.1f}; realized - projection O "
            f"{w['O_outperformed_projection_by_HINDSIGHT']:+.1f} vs A "
            f"{w['A_outperformed_projection_by_HINDSIGHT']:+.1f}"
        )
        for k in ("S_agrees_with_MR", "R_agrees_with_MR"):
            print(f"    {k}: {prim[k]}")

        entry["information_loss"] = information_loss(pop)
        il = entry["information_loss"]
        print(f"\n  INFORMATION LOSS on C1 AND C2 ({il['n_decomposable']}/{il['n']} decomposable):")
        for term in ("additive", "fit", "risk", "survival", "feasibility"):
            t = il[term]
            print(
                f"    {term:<12} points at O {t['points_at_O']:>4}  at A {t['points_at_A']:>4}  "
                f"neutral {t['neutral']:>4}  mean log(A/O) {t['mean_log_ratio_A_over_O']:+.3f}"
            )
        print(
            f"    neutralise survival -> O wins {il['survival_neutralised_O_wins']}; neutralise "
            f"opp cost -> O wins {il['opp_cost_neutralised_O_wins']}; legality overrides "
            f"{il['legality_override']}; value-base gap A-O {il['mean_value_base_gap_A_minus_O_pts']:+.1f}"
            f" pts, opp-cost gap A-O {il['mean_opp_cost_gap_A_minus_O_pts']:+.2f} pts"
        )

        tot_c = sorted(r["regret_roster"] for r in pop)
        cuts = (tot_c[len(tot_c) // 3], tot_c[2 * len(tot_c) // 3]) if tot_c else (0.0, 0.0)
        entry["by_oracle_position"] = breakdown(pop, lambda r: r["oracle_position"])
        entry["by_pair_type"] = breakdown(
            pop, lambda r: "same-position" if r["same_position"] else "cross-position"
        )
        entry["by_pair"] = breakdown(
            pop, lambda r: f"{r['alpha_position']}->{r['oracle_position']}"
        )
        entry["by_round"] = breakdown(
            pop, lambda r: r["round"], order=[str(x) for x in range(1, 17)]
        )
        entry["by_phase"] = breakdown(pop, lambda r: r["phase"], order=[p[0] for p in D115.PHASES])
        entry["by_season"] = breakdown(
            pop, lambda r: r["season"], order=[str(s) for s in BACKTEST_SEASONS]
        )
        entry["by_regret_tercile"] = breakdown(
            pop,
            lambda r, cuts=cuts: regret_tercile(r["regret_roster"], cuts),
            order=["T1 low", "T2 mid", "T3 high"],
        )
        entry["regret_tercile_cuts"] = cuts
        for name in (
            "by_oracle_position",
            "by_pair_type",
            "by_phase",
            "by_round",
            "by_season",
            "by_regret_tercile",
        ):
            print(f"\n  {name.upper()}  (H2 accuracy; S = survival, OC, SC, R = replay)")
            print(
                f"    {'group':<16}{'n':>4}{'regret%':>9}{'S acc':>8}{'S dec':>6}{'S->O':>6}"
                f"{'OC acc':>8}{'OC dec':>7}{'R acc':>8}{'SC acc':>8}{'O 1st':>7}{'O next':>7}"
            )
            for k, g in entry[name].items():
                f = _pct_or_dash
                print(
                    f"    {k:<16}{g['n']:>4}{100 * g['regret'] / total:>8.1f}%"
                    f"{f(g['S_acc']):>8}{g['S_decisive']:>6}{g['S_points_at_O']:>6}"
                    f"{f(g['OC_acc']):>8}{g['OC_decisive']:>7}{f(g['R_acc']):>8}"
                    f"{f(g['SC_acc']):>8}{g['O_first_H2']:>7}{g['took_O_next']:>7}"
                )

        entry["addressable"] = addressable(pop, total)
        ad = entry["addressable"]
        print(
            f"\n  ADDRESSABLE: potentially {ad['potentially_addressable_pct_of_total']:.1f}% of "
            f"total regret; survival points at O {ad['survival_points_at_O_pct_of_total']:.1f}%; "
            f"survival at O AND O first (H2) "
            f"{ad['survival_points_at_O_and_O_first_H2_pct_of_total']:.1f}%; replay at O "
            f"{ad['replay_points_at_O_pct_of_total']:.1f}%; opp cost at O "
            f"{ad['opp_cost_points_at_O_pct_of_total']:.1f}%; any signal at O "
            f"{ad['any_signal_points_at_O_pct_of_total']:.1f}%; unexplained "
            f"{ad['unexplained_pct_of_total']:.1f}%"
        )

        ctx = [c for c in context if c["league"] == league_name]
        entry["context_calibration"] = context_calibration(ctx)
        cc = entry["context_calibration"]
        print(
            f"\n  CONTEXT calibration (Alpha top-{CONTEXT_TOP_K}, {cc['n']} player-states): "
            f"Brier {cc['brier']:.3f}  ECE {cc['ece']:.3f}  mean S {cc['mean_S']:.3f} vs "
            f"observed {cc['observed_survival_rate']:.3f}; replay membership accuracy "
            f"{cc['replay_membership_accuracy']:.3f}; S=0 but survived "
            f"{cc['S_eq_0_but_survived']}/{cc['S_eq_0_count']}; S=1 but gone "
            f"{cc['S_eq_1_but_gone']}/{cc['S_eq_1_count']}"
        )
        for b in cc["reliability"]:
            print(
                f"    bin {b['bin']}  n {b['n']:>5}  pred {b['mean_pred']:.2f}  obs "
                f"{b['mean_obs']:.2f}"
            )
    return summary


def _write(out: Path, name: str, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=list))
    print(f"wrote {out / name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("measure", "report"))
    ap.add_argument("--in", dest="inputs", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default="1,4,7,10")
    a = ap.parse_args()
    out = Path(a.out)
    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise UnreconstructibleError(f"{season} must never enter the historical evaluation")

    if a.mode == "measure":
        if not a.inputs:
            raise UnreconstructibleError("--in <dir with d115_regret.json and d115_timing.json>")
        con = duckdb.connect(a.db, read_only=True)
        slots = tuple(int(s) for s in a.slots.split(","))
        pairs, context, prov = run_measure(con, [Path(d) for d in a.inputs], slots)
        regret_rows, _, _ = _load_d115([Path(d) for d in a.inputs])
        prov.update(D115._provenance(con, {"mode": "d116_measure", "argv": sys.argv}))
        prov.update(_src_tree())
        _write(
            out,
            "d116_pairs.json",
            {"provenance": prov, "pairs": pairs, "context": context, "regret_rows": regret_rows},
        )
        return

    payload = json.loads((out / "d116_pairs.json").read_text())
    summary = report(payload["pairs"], payload["context"], payload["regret_rows"])
    summary["provenance"] = payload["provenance"]
    _write(out, "d116_summary.json", summary)


if __name__ == "__main__":
    main()
