"""D117 -- does Alpha already hold upside / uncertainty information about the players behind the
D115/D116 sequencing regret, and does the projection/risk logic suppress it?

Read-only research runner. Reads D116's committed artifact (`d116_pairs.json`) for the EXACT
C1 AND C2 population, re-walks the same drafts through D116's `scored_states` (which re-walks
D115's `replay_states` and re-asks the shipped `_pick_by_tier`), and reads the shipped
uncertainty and rookie model outputs for the two players at each pick. Writes nothing but JSON
under `--out`. **No file under `src/alpha_squad/` is touched and this script is imported by no
production path.**

    uv run python scripts/research/d117_upside_audit.py --mode measure \
        --d116 <dir with d116_pairs.json> --out <out>
    uv run python scripts/research/d117_upside_audit.py --mode report --out <out>

==========================================================================================
PRE-REGISTRATION -- written before any D117 number existed
==========================================================================================

THE QUESTION.  On D116's C1 AND C2 picks the oracle's player O loses to Alpha's player A in the
value term (~2.2x) and in the risk (confidence) multiplier. Is O losing because Alpha's
available information says he is worse, or because Alpha holds useful upside information that
the scoring formula fails to use? **Diagnostic only. No weight, threshold, feature, model or
draft strategy is introduced; no realized outcome enters any signal.**

POPULATION.  D116's pairs with `C1 AND C2` (D115's definition, via D116's `is_c1c2`), read
from D116's artifact and never redefined. `target_league` PRIMARY, `dynasty_1qb` replication,
never pooled. Seasons 2021-2025; unit of independence = season (k = 5, t_crit = 2.776). The
artifact's board vintage must equal the database's, or the runner raises.

EX-ANTE SIGNALS, per player, all already produced by shipped code before the draft:
  proj          the board projection the engine reads (`load_season_projections`)
  p10..p90      `uncertainty_predictions` (M6, `uncertainty_catboost_v2`) quantiles
  width         p90 - p10
  upside        p90 - point
  top12, top24  M6's Monte Carlo top-N probabilities
  confidence    M6's `confidence` (None when the player has no M6 row)
  risk          the multiplier the L0 score ACTUALLY applied: confidence, or 0.7 when None
  breakout      `rookie_predictions.breakout_probability` (rookies only; the engine never
                reads it -- listed because the brief asks for every existing upside output)
  ecr           preseason market rank (CONTEXT ONLY; lower is better)
  ecr_range     ecr_worst - ecr_best (market disagreement; CONTEXT ONLY)
  proj_vorp, p90_vorp  proj / p90 minus the engine's own static replacement level at the
                position -- the SAME level the engine already uses, applied so a cross-position
                comparison is on the scale the decision is made on. A re-expression of existing
                outputs, not a new feature.

PAIRWISE CALL.  For every signal: does it rank O above A ("favors O"), A above O, tie, or is it
undefined (either player lacks the output)? Direction: higher is better for every signal except
ecr. Because O is the hindsight-better player on every pair in this population, "favors O" is
the only definition of "correct" available -- and it is a HINDSIGHT label. Rule 4 of the brief
is honoured by a SELECTION CONTROL (below): a signal that merely tracks variance will favour
O on a population selected for O's upside surprise, without carrying any usable information.

  A. p90 vs projection      paired discordance (p90 favors O where proj favors A, and the
                            reverse), exact two-sided sign test on the discordant pairs
  B. top24 vs projection    same
  C. every signal           favors-O rate, ties, undefined, season-clustered CI, Wilson, MDE,
                            mean gap A - O
  D. breakout identification the favors-O rate IS this; reported per signal, and for "ANY
                            uncertainty signal favors O while the projection favors A" -- the
                            information-beyond-projection test
  E. concentration          O position, pair type, phase, round, O projection tier (O's
                            within-position projection rank that season), O ECR tier, season
  F. realized outcome       mean realized gap per pair (HINDSIGHT, never an input), and the
                            SELECTION CONTROL: across every established player on the board, is
                            the signed projection residual predictable from any uncertainty
                            output GIVEN the projection? If not, upside info cannot improve a
                            decision, whatever it does on a hindsight-selected population.

STRUCTURAL CHECK, stated before measuring because it decides what the pairwise numbers can
mean: the M6 intervals are `point + residual quantile`, fitted once per (season, position), so
within a position-season `p90 - point` and `p10 - point` should be CONSTANTS, `confidence`
should be a deterministic function of the point projection, and `top24` should be monotone in
it up to Monte Carlo noise. The runner measures all three on the full table. If they hold,
within-position uncertainty outputs cannot disagree with the projection, by construction.

SCORE DECOMPOSITION.  The shipped L0 score is
    score = (value_base + OC) * fit * risk * survival_mult * capacity
(capacity = the positional feasibility multiplier). score_A - score_O is split by an EXACT
SHAPLEY decomposition over those six factors (all 64 subsets): each factor's contribution is its
average marginal effect of switching from O's value to A's; contributions sum to the gap exactly
(asserted). value_base is identified from the score where the multiplier product is non-zero and
read from the engine's own `reasons` log where it is zero (confidence = 0 zeroes the score). "Would
neutralising factor X let O win" is reported per factor as leverage, not as a proposal.

RISK: "risk is bad" vs "risk uses the wrong information".  Measured on the full board, by
within-position confidence bucket: the mean SIGNED residual (does low confidence predict
under-performance -- a justified penalty?) against the mean ABSOLUTE residual (does it only
predict noise?), and the realized/projection ratio.

ADDRESSABLE SHARE.  Of total regret per format: pairs where ANY existing uncertainty signal
favours O while the projection favours A (information inside Alpha that the projection lacks),
and pairs where neutralising the risk multiplier alone lets O outscore A (what the multiplier
suppresses -- whatever information it carries). Neither is called recoverable.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
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
from alpha_squad.evaluation.draft_oracle import assert_no_realized_inputs_in_policy
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.league.context import resolve_league
from alpha_squad.models.uncertainty.conformal import confidence_from_interval_width
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
T_CRIT = 2.776
#: The risk multiplier `score_candidate` applies when a player has no M6 confidence.
SHIPPED_RISK_FALLBACK = 0.7
FAVORS_O, FAVORS_A, TIE, UNDEFINED = "O", "A", "tie", "undefined"
FACTORS = ("value", "opp_cost", "fit", "risk", "survival", "capacity")

#: signal -> (higher is better?, family). "uncertainty" signals are the ones the brief asks
#: whether Alpha already holds; "projection" is the reference; "context" is never counted as
#: upside information.
SIGNALS: dict[str, tuple[bool, str]] = {
    "proj": (True, "projection"),
    "proj_vorp": (True, "projection"),
    "p10": (True, "uncertainty"),
    "median": (True, "uncertainty"),
    "p90": (True, "uncertainty"),
    "p90_vorp": (True, "uncertainty"),
    "width": (True, "uncertainty"),
    "upside": (True, "uncertainty"),
    "top12": (True, "uncertainty"),
    "top24": (True, "uncertainty"),
    "confidence": (True, "risk"),
    "risk": (True, "risk"),
    "breakout": (True, "uncertainty"),
    "ecr": (False, "context"),
    "ecr_range": (True, "context"),
}
UPSIDE_SIGNALS = tuple(k for k, (_, fam) in SIGNALS.items() if fam == "uncertainty")
#: Signals that are CONSTANT within a (season, position) by M6's construction -- they can only
#: ever separate two players by their positions, never as individuals.
POSITION_CONSTANT_SIGNALS = ("width", "upside")
PLAYER_LEVEL_UPSIDE_SIGNALS = tuple(s for s in UPSIDE_SIGNALS if s not in POSITION_CONSTANT_SIGNALS)


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D116 = _load("d116_survival_attribution")
D115 = D116.D115


class UnreconstructibleError(RuntimeError):
    """D117 stops rather than substituting."""


# --------------------------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------------------------
#: Two values closer than this are a TIE. M6's per-position interval offsets are identical up to
#: ~1e-14 of floating-point noise; without a tolerance that noise is scored as a preference (it
#: was, in D117's first report run, on 5 same-position pairs -- fixed before anything was read).
TIE_TOLERANCE = 1e-9


def favors(a: float | None, o: float | None, higher_is_better: bool = True) -> str:
    if a is None or o is None:
        return UNDEFINED
    if abs(a - o) <= TIE_TOLERANCE * max(1.0, abs(a), abs(o)):
        return TIE
    o_better = o > a if higher_is_better else o < a
    return FAVORS_O if o_better else FAVORS_A


def call_summary(calls: list[str]) -> dict:
    n = len(calls)
    o = sum(1 for c in calls if c == FAVORS_O)
    a = sum(1 for c in calls if c == FAVORS_A)
    decisive = o + a
    return {
        "n": n,
        "favors_O": o,
        "favors_A": a,
        "tie": sum(1 for c in calls if c == TIE),
        "undefined": sum(1 for c in calls if c == UNDEFINED),
        "decisive": decisive,
        "rate_O": o / decisive if decisive else None,
    }


def sign_test_p(k: int, n: int) -> float | None:
    """Exact two-sided binomial test of k successes in n at p = 0.5."""
    if n == 0:
        return None
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2**n
    return min(1.0, 2 * tail)


def discordance(calls_x: list[str], calls_ref: list[str]) -> dict:
    """Paired comparison of two signals' calls: where one favours O and the other A."""
    x_only = sum(
        1 for x, r in zip(calls_x, calls_ref, strict=True) if x == FAVORS_O and r == FAVORS_A
    )
    ref_only = sum(
        1 for x, r in zip(calls_x, calls_ref, strict=True) if x == FAVORS_A and r == FAVORS_O
    )
    return {
        "x_favors_O_ref_favors_A": x_only,
        "ref_favors_O_x_favors_A": ref_only,
        "sign_test_p": sign_test_p(x_only, x_only + ref_only),
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    return D116.wilson(k, n, z)


def season_clustered(values_by_season: dict) -> dict:
    return D116.season_clustered(values_by_season)


def l0_score(f: dict[str, float]) -> float:
    """The shipped L0 score from its six factors."""
    return (f["value"] + f["opp_cost"]) * f["fit"] * f["risk"] * f["survival"] * f["capacity"]


def shapley(fa: dict[str, float], fo: dict[str, float]) -> dict[str, float]:
    """Exact Shapley split of l0_score(fa) - l0_score(fo) over FACTORS. The 'players' are the
    factors; a coalition S takes A's value for factors in S and O's for the rest."""
    n = len(FACTORS)
    out = dict.fromkeys(FACTORS, 0.0)
    for i, name in enumerate(FACTORS):
        others = [f for j, f in enumerate(FACTORS) if j != i]
        for size in range(n):
            weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            for coalition in itertools.combinations(others, size):
                base = {f: (fa[f] if f in coalition else fo[f]) for f in FACTORS}
                with_i = {**base, name: fa[name]}
                out[name] += weight * (l0_score(with_i) - l0_score(base))
    total = l0_score(fa) - l0_score(fo)
    if abs(sum(out.values()) - total) > 1e-6 * max(1.0, abs(total)):
        raise UnreconstructibleError("Shapley contributions do not sum to the score gap")
    return out


def neutralised_winner(fa: dict[str, float], fo: dict[str, float], factor: str) -> str:
    """Who outscores whom if `factor` is set to the same neutral value for both players."""
    neutral = 0.0 if factor == "opp_cost" else 1.0
    if factor == "value":
        return "n/a"
    sa = l0_score({**fa, factor: neutral})
    so = l0_score({**fo, factor: neutral})
    return FAVORS_O if so > sa else (FAVORS_A if sa > so else TIE)


def factors_from(candidate: dict) -> dict[str, float]:
    """The six factors of one shipped CandidateScore. value_base is identified from the score
    when the multiplier product is non-zero (D116's checked factorisation) and read from the
    engine's own log when it is zero -- a zero confidence zeroes the score and hides it."""
    parts = D116.score_parts(candidate)
    value = parts["value_base"]
    if value is None:
        value = D116.logged_value_base(candidate.get("reasons") or [])
        if value is None:
            raise UnreconstructibleError(f"no identifiable value_base for {candidate['player_id']}")
    return {
        "value": value,
        "opp_cost": parts["oc"],
        "fit": parts["fit"],
        "risk": parts["risk"],
        "survival": parts["sm"],
        "capacity": parts["feas"],
    }


def within_position_rank(player: str, projections: dict, positions: dict) -> int | None:
    pos = positions.get(player)
    if pos is None or player not in projections:
        return None
    peers = sorted(
        (p for p in projections if positions.get(p) == pos), key=lambda p: (-projections[p], p)
    )
    return peers.index(player) + 1


def projection_tier(rank: int | None) -> str:
    if rank is None:
        return "unranked"
    if rank <= 12:
        return "pos 1-12"
    if rank <= 24:
        return "pos 13-24"
    if rank <= 48:
        return "pos 25-48"
    return "pos 49+"


def ecr_tier(rank: float | None) -> str:
    if rank is None:
        return "no ECR"
    if rank <= 50:
        return "ECR 1-50"
    if rank <= 100:
        return "ECR 51-100"
    if rank <= 150:
        return "ECR 101-150"
    return "ECR 151+"


def confidence_bucket(conf: float | None) -> str:
    if conf is None:
        return "none (0.7 fallback)"
    if conf == 0.0:
        return "0 (score zeroed)"
    if conf < 0.25:
        return "(0, .25)"
    if conf < 0.5:
        return "[.25, .5)"
    if conf < 0.75:
        return "[.5, .75)"
    return "[.75, 1]"


# --------------------------------------------------------------------------------------------
# MODE: measure
# --------------------------------------------------------------------------------------------
def load_uncertainty(con) -> dict[tuple[str, int], dict]:
    rows = con.execute(
        "SELECT player_id, season, position, point_prediction, p10, p25, median, p75, p90, "
        "top12_prob, top24_prob, confidence FROM uncertainty_predictions WHERE model_version = ?",
        [UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    keys = (
        "position",
        "point",
        "p10",
        "p25",
        "median",
        "p75",
        "p90",
        "top12",
        "top24",
        "confidence",
    )
    return {(r[0], r[1]): dict(zip(keys, r[2:], strict=True)) for r in rows}


def load_rookie(con) -> dict[tuple[str, int], dict]:
    rows = con.execute(
        "SELECT player_id, draft_class, predicted_rookie_points, breakout_probability, "
        "model_version FROM rookie_predictions"
    ).fetchall()
    return {
        (r[0], r[1]): {"rookie_points": r[2], "breakout": r[3], "model_version": r[4]} for r in rows
    }


def structural_check(unc: dict) -> dict:
    """Does M6 carry ANY player-specific uncertainty? Per (season, position) in the window."""
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for (_pid, season), row in unc.items():
        if season in BACKTEST_SEASONS:
            groups[(season, row["position"])].append(row)
    out = {}
    for (season, pos), rows in sorted(groups.items()):
        ups = [r["p90"] - r["point"] for r in rows]
        dns = [r["p10"] - r["point"] for r in rows]
        conf_err = max(
            abs(r["confidence"] - confidence_from_interval_width(r["point"], r["p10"], r["p90"]))
            for r in rows
        )
        ordered = sorted(rows, key=lambda r: r["point"])
        inversions = sum(
            1
            for x, y in itertools.combinations(ordered, 2)
            if x["point"] < y["point"] and x["top24"] > y["top24"]
        )
        pairs_n = len(rows) * (len(rows) - 1) // 2
        out[f"{season} {pos}"] = {
            "n": len(rows),
            "sd_p90_minus_point": stdev(ups) if len(ups) > 1 else 0.0,
            "sd_p10_minus_point": stdev(dns) if len(dns) > 1 else 0.0,
            "upside_constant": ups[0],
            "max_abs_confidence_minus_formula": conf_err,
            "top24_order_inversions": inversions,
            "top24_pairs": pairs_n,
            "confidence_zero": sum(1 for r in rows if r["confidence"] == 0.0),
        }
    return out


def player_signals(pid, season, static, unc, rookie) -> dict:
    u = unc.get((pid, season))
    rk = rookie.get((pid, season))
    pos = static.positions.get(pid)
    repl = static.replacement_levels.get(pos, 0.0)
    proj = static.projections.get(pid)
    mr = static.market_rank.get(pid)
    rng = static.ecr_dispersion.get(pid)
    conf = None if u is None else u["confidence"]
    return {
        "position": pos,
        "source": "m6" if u is not None else ("rookie" if rk is not None else "none"),
        "proj": proj,
        "proj_vorp": None if proj is None else proj - repl,
        "p10": None if u is None else u["p10"],
        "median": None if u is None else u["median"],
        "p90": None if u is None else u["p90"],
        "p90_vorp": None if u is None else u["p90"] - repl,
        "width": None if u is None else u["p90"] - u["p10"],
        "upside": None if u is None else u["p90"] - u["point"],
        "top12": None if u is None else u["top12"],
        "top24": None if u is None else u["top24"],
        "confidence": conf,
        "risk": SHIPPED_RISK_FALLBACK if conf is None else conf,
        "breakout": None if rk is None else rk["breakout"],
        "ecr": None if mr is None else mr[1],
        "ecr_range": None if rng is None else rng[1] - rng[0],
        "m6_point_matches_board": None
        if u is None or proj is None
        else abs(u["point"] - proj) < 1e-9,
    }


def run_measure(con, d116_dir: Path) -> dict:
    payload = json.loads((d116_dir / "d116_pairs.json").read_text())
    vintage = compute_board_vintage(con).combined_hash
    if payload["provenance"]["board_vintage_combined"] != vintage:
        raise UnreconstructibleError(
            f"D116 artifact is vintage {payload['provenance']['board_vintage_combined']}, the "
            f"database is {vintage} -- refusing to mix vintages"
        )
    pop = [p for p in payload["pairs"] if D116.is_c1c2(p)]
    unc = load_uncertainty(con)
    rookie = load_rookie(con)
    rows: list[dict] = []
    context: list[dict] = []
    t0 = time.time()
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = D115._static_for(con, league, season)
            want = [p for p in pop if p["league"] == league_name and p["season"] == season]
            for slot in sorted({p["slot"] for p in want}):
                states = {
                    s["overall_pick"]: s
                    for s in D116.scored_states(con, league, season, static, slot)
                }
                for p in (x for x in want if x["slot"] == slot):
                    state = states.get(p["overall_pick"])
                    if state is None or state["alpha_pick"] != p["alpha"]:
                        raise UnreconstructibleError(
                            f"re-walk does not reproduce D116's pick at {league_name} {season} "
                            f"slot {slot} pick {p['overall_pick']}"
                        )
                    ca, co = state["scored"][p["alpha"]], state["scored"][p["oracle"]]
                    fa, fo = factors_from(ca), factors_from(co)
                    if abs(l0_score(fa) - ca["score"]) > 1e-6 * max(1.0, abs(ca["score"])):
                        raise UnreconstructibleError(f"factors do not rebuild A's score at {p}")
                    if abs(l0_score(fo) - co["score"]) > 0.051 * fo["fit"] * fo["risk"] * fo[
                        "survival"
                    ] * fo["capacity"] + 1e-6 * max(1.0, abs(co["score"])):
                        raise UnreconstructibleError(f"factors do not rebuild O's score at {p}")
                    rows.append(
                        {
                            **{
                                k: p[k]
                                for k in (
                                    "league",
                                    "season",
                                    "slot",
                                    "round",
                                    "phase",
                                    "overall_pick",
                                    "alpha",
                                    "oracle",
                                    "alpha_position",
                                    "oracle_position",
                                    "same_position",
                                    "category",
                                    "regret_roster",
                                    "alpha_realized",
                                    "oracle_realized",
                                )
                            },
                            "A": player_signals(p["alpha"], season, static, unc, rookie),
                            "O": player_signals(p["oracle"], season, static, unc, rookie),
                            "O_proj_rank": within_position_rank(
                                p["oracle"], static.projections, static.positions
                            ),
                            "factors_A": fa,
                            "factors_O": fo,
                        }
                    )
            # ---- selection control: every established player with an M6 row this season
            if league_name == FORMATS[0]:
                ids = [pid for (pid, s) in unc if s == season]
                realized = _actual_points_for(con, season, ids)
                for pid in ids:
                    u = unc[(pid, season)]
                    if pid not in realized:
                        continue
                    context.append(
                        {
                            "season": season,
                            "position": u["position"],
                            "point": u["point"],
                            "p90": u["p90"],
                            "top24": u["top24"],
                            "confidence": u["confidence"],
                            "realized": realized[pid],
                            "ecr": None
                            if pid not in static.market_rank
                            else static.market_rank[pid][1],
                            "ecr_range": None
                            if pid not in static.ecr_dispersion
                            else static.ecr_dispersion[pid][1] - static.ecr_dispersion[pid][0],
                        }
                    )
            print(f"  measure {league_name} {season} ({time.time() - t0:.0f}s)", flush=True)
    return {
        "pairs": rows,
        "context": context,
        "structural": structural_check(unc),
        "d116_pairs_sha256": hashlib.sha256(
            (d116_dir / "d116_pairs.json").read_bytes()
        ).hexdigest(),
        "d116_vintage": payload["provenance"]["board_vintage_combined"],
    }


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
def calls_for(rows: list[dict], sig: str) -> list[str]:
    higher = SIGNALS[sig][0]
    return [favors(r["A"][sig], r["O"][sig], higher) for r in rows]


def any_upside_beyond_projection(r: dict, signals: tuple[str, ...] = UPSIDE_SIGNALS) -> bool:
    """Some existing uncertainty output favours O while the projection favours A."""
    if favors(r["A"]["proj"], r["O"]["proj"]) != FAVORS_A:
        return False
    return any(favors(r["A"][s], r["O"][s], SIGNALS[s][0]) == FAVORS_O for s in signals)


def player_level_beyond_projection(r: dict) -> bool:
    """As above, excluding the position-constant signals: the strict test of whether any output
    separates the two players AS INDIVIDUALS in O's favour against the projection."""
    return any_upside_beyond_projection(r, PLAYER_LEVEL_UPSIDE_SIGNALS)


def signal_table(rows: list[dict]) -> dict:
    out = {}
    for sig in SIGNALS:
        calls = calls_for(rows, sig)
        res = call_summary(calls)
        per_season = {}
        for season in BACKTEST_SEASONS:
            sub = [r for r in rows if r["season"] == season]
            s = call_summary(calls_for(sub, sig))
            if s["rate_O"] is not None:
                per_season[season] = s["rate_O"]
        res["season_clustered"] = season_clustered(per_season)
        res["wilson"] = wilson(res["favors_O"], res["decisive"])
        gaps = [
            r["A"][sig] - r["O"][sig]
            for r in rows
            if r["A"][sig] is not None and r["O"][sig] is not None
        ]
        res["mean_gap_A_minus_O"] = mean(gaps) if gaps else None
        out[sig] = res
    return out


def breakdown(rows: list[dict], key_fn, order=None) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(key_fn(r))].append(r)
    out = {}
    for k in order or sorted(groups):
        sub = groups.get(k)
        if not sub:
            continue
        entry = {"n": len(sub), "regret": sum(r["regret_roster"] for r in sub)}
        for sig in ("proj", "proj_vorp", "p90", "p90_vorp", "top24", "confidence", "risk", "ecr"):
            entry[sig] = call_summary(calls_for(sub, sig))["rate_O"]
        entry["beyond_proj"] = sum(1 for r in sub if any_upside_beyond_projection(r))
        out[k] = entry
    return out


def decomposition(rows: list[dict]) -> dict:
    contrib = {f: [] for f in FACTORS}
    gaps = []
    flips = dict.fromkeys(FACTORS, 0)
    for r in rows:
        sh = shapley(r["factors_A"], r["factors_O"])
        gaps.append(l0_score(r["factors_A"]) - l0_score(r["factors_O"]))
        for f in FACTORS:
            contrib[f].append(sh[f])
            if neutralised_winner(r["factors_A"], r["factors_O"], f) == FAVORS_O:
                flips[f] += 1
    total_gap = sum(gaps)
    return {
        "n": len(rows),
        "mean_score_gap_A_minus_O": mean(gaps) if gaps else None,
        "factors": {
            f: {
                "mean_contribution": mean(contrib[f]) if contrib[f] else None,
                "share_of_gap": sum(contrib[f]) / total_gap if total_gap else None,
                "favors_A": sum(1 for c in contrib[f] if c > 1e-12),
                "favors_O": sum(1 for c in contrib[f] if c < -1e-12),
                "neutralise_lets_O_win": flips[f],
            }
            for f in FACTORS
        },
        "O_zero_confidence": sum(1 for r in rows if r["O"]["confidence"] == 0.0),
        "O_risk_fallback_0_7": sum(1 for r in rows if r["O"]["confidence"] is None),
        "A_zero_confidence": sum(1 for r in rows if r["A"]["confidence"] == 0.0),
        "A_risk_fallback_0_7": sum(1 for r in rows if r["A"]["confidence"] is None),
    }


def _pearson(xs, ys):
    return D115._pearson(xs, ys)


def selection_control(ctx: list[dict], ecr_cap: float | None = None) -> dict:
    """Across the board: is the SIGNED residual predictable from any uncertainty output given
    the projection? Within a position-season the M6 outputs are functions of the point, so the
    only question left is whether the projection LEVEL (which is what confidence re-expresses)
    predicts residual sign or only its size."""
    rows = [c for c in ctx if ecr_cap is None or (c["ecr"] is not None and c["ecr"] <= ecr_cap)]
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for c in rows:
        by_bucket[confidence_bucket(c["confidence"])].append(c)
    buckets = {}
    for k in ("0 (score zeroed)", "(0, .25)", "[.25, .5)", "[.5, .75)", "[.75, 1]"):
        sub = by_bucket.get(k, [])
        if not sub:
            continue
        per_season = defaultdict(list)
        for c in sub:
            per_season[c["season"]].append(c["realized"] - c["point"])
        buckets[k] = {
            "n": len(sub),
            "mean_point": mean(c["point"] for c in sub),
            "mean_realized": mean(c["realized"] for c in sub),
            "mean_signed_residual": mean(c["realized"] - c["point"] for c in sub),
            "signed_residual_season_ci": season_clustered(
                {s: mean(v) for s, v in per_season.items()}
            ),
            "mean_abs_residual": mean(abs(c["realized"] - c["point"]) for c in sub),
            "share_beating_projection": mean(float(c["realized"] > c["point"]) for c in sub),
        }
    # Within position-season, correlation of signed residual with each output (all of which
    # are monotone in the point -- so these are the SAME question asked four ways).
    corr = {}
    for sig in ("point", "p90", "top24", "confidence"):
        per_group = []
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for c in rows:
            groups[(c["season"], c["position"])].append(c)
        for g in groups.values():
            if len(g) >= 10:
                r = _pearson([c[sig] for c in g], [c["realized"] - c["point"] for c in g])
                if r == r:  # not NaN
                    per_group.append(r)
        corr[sig] = mean(per_group) if per_group else None
    return {
        "n": len(rows),
        "by_confidence_bucket": buckets,
        "mean_within_group_corr": corr,
        "ecr_range_partial": ecr_range_partial(rows),
    }


def _residualise(xs: list[float], zs: list[float]) -> list[float]:
    """x minus its least-squares fit on z (with intercept)."""
    mz, mx = mean(zs), mean(xs)
    vz = sum((z - mz) ** 2 for z in zs)
    if vz == 0:
        return [x - mx for x in xs]
    b = sum((z - mz) * (x - mx) for z, x in zip(zs, xs, strict=True)) / vz
    return [x - mx - b * (z - mz) for x, z in zip(xs, zs, strict=True)]


def ecr_range_partial(rows: list[dict]) -> dict:
    """The market's per-player disagreement is the ONE player-specific dispersion signal already
    stored. Within each (season, position): partial correlation of ecr_range with the SIGNED and
    ABSOLUTE residual, holding the projection fixed. Per-season means give a k = 5 interval."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in rows:
        if c.get("ecr_range") is not None:
            groups[(c["season"], c["position"])].append(c)
    per_season_signed: dict[int, list[float]] = defaultdict(list)
    per_season_abs: dict[int, list[float]] = defaultdict(list)
    n = 0
    for (season, _pos), g in groups.items():
        if len(g) < 10:
            continue
        n += len(g)
        pts = [c["point"] for c in g]
        rng = _residualise([c["ecr_range"] for c in g], pts)
        signed = _residualise([c["realized"] - c["point"] for c in g], pts)
        absr = _residualise([abs(c["realized"] - c["point"]) for c in g], pts)
        for store, ys in ((per_season_signed, signed), (per_season_abs, absr)):
            r = _pearson(rng, ys)
            if r == r:
                store[season].append(r)
    return {
        "n": n,
        "signed": season_clustered({s: mean(v) for s, v in per_season_signed.items()}),
        "absolute": season_clustered({s: mean(v) for s, v in per_season_abs.items()}),
    }


def addressable(rows: list[dict], total_regret: float) -> dict:
    def pct(sub):
        return 100 * sum(r["regret_roster"] for r in sub) / total_regret if total_regret else None

    beyond = [r for r in rows if any_upside_beyond_projection(r)]
    strict = [r for r in rows if player_level_beyond_projection(r)]
    risk_flip = [
        r for r in rows if neutralised_winner(r["factors_A"], r["factors_O"], "risk") == FAVORS_O
    ]
    p90_o = [r for r in rows if favors(r["A"]["p90_vorp"], r["O"]["p90_vorp"]) == FAVORS_O]
    return {
        "population_pct": pct(rows),
        "any_upside_beyond_projection_pct": pct(beyond),
        "n_any_upside_beyond_projection": len(beyond),
        "player_level_beyond_projection_pct": pct(strict),
        "n_player_level_beyond_projection": len(strict),
        "risk_neutralised_O_wins_pct": pct(risk_flip),
        "n_risk_neutralised_O_wins": len(risk_flip),
        "p90_vorp_favors_O_pct": pct(p90_o),
        "same_position_beyond_projection": sum(1 for r in beyond if r["same_position"]),
    }


def _fmt(res: dict) -> str:
    if res["rate_O"] is None:
        return f"{'undefined':>9}"
    sc = res["season_clustered"]
    ci = "" if sc["ci"] is None else f" CI[{sc['ci'][0]:.0%},{sc['ci'][1]:.0%}]"
    return f"{res['rate_O']:>8.1%} ({res['favors_O']}/{res['decisive']}){ci}"


def report(measured: dict, regret_totals: dict) -> dict:
    bar = "=" * 100
    summary: dict = {"structural": measured["structural"], "formats": {}}
    st = measured["structural"]
    print(f"\n{bar}\nSTRUCTURAL CHECK -- does M6 carry player-specific uncertainty?\n{bar}")
    print(
        f"  position-seasons {len(st)}; max sd(p90 - point) "
        f"{max(v['sd_p90_minus_point'] for v in st.values()):.2e}; max sd(p10 - point) "
        f"{max(v['sd_p10_minus_point'] for v in st.values()):.2e}; max |confidence - "
        f"formula(point)| {max(v['max_abs_confidence_minus_formula'] for v in st.values()):.2e}; "
        f"top24 order inversions vs point "
        f"{sum(v['top24_order_inversions'] for v in st.values())}/"
        f"{sum(v['top24_pairs'] for v in st.values())}; confidence == 0 rows "
        f"{sum(v['confidence_zero'] for v in st.values())}/{sum(v['n'] for v in st.values())}"
    )
    for league_name in FORMATS:
        rows = [r for r in measured["pairs"] if r["league"] == league_name]
        if not rows:
            continue
        total = regret_totals[league_name]
        entry = summary["formats"].setdefault(league_name, {})
        print(f"\n{bar}\nD117 -- {league_name}: {len(rows)} C1 AND C2 pairs\n{bar}")
        sources = defaultdict(int)
        for r in rows:
            sources[f"A:{r['A']['source']} O:{r['O']['source']}"] += 1
        entry["sources"] = dict(sources)
        print(f"  output coverage {dict(sources)}")
        for label, sub in (
            ("ALL PAIRS", rows),
            ("SAME-POSITION", [r for r in rows if r["same_position"]]),
            ("CROSS-POSITION", [r for r in rows if not r["same_position"]]),
        ):
            tab = signal_table(sub)
            entry[f"signals_{label}"] = tab
            print(f"\n  {label} ({len(sub)}) -- favors-O rate among decisive; ties / undefined")
            for sig, res in tab.items():
                gap = res["mean_gap_A_minus_O"]
                print(
                    f"    {sig:<11}{SIGNALS[sig][1]:<12}{_fmt(res):<34} tie {res['tie']:>3} "
                    f"undef {res['undefined']:>3}  mean gap A-O "
                    f"{'--' if gap is None else f'{gap:+.3f}'}"
                )
            disc = {
                s: discordance(calls_for(sub, s), calls_for(sub, ref))
                for s, ref in (
                    ("p90", "proj"),
                    ("top24", "proj"),
                    ("p90_vorp", "proj_vorp"),
                    ("confidence", "proj"),
                )
            }
            entry[f"discordance_{label}"] = disc
            print(f"    discordance vs projection: {disc}")
            beyond = [r for r in sub if any_upside_beyond_projection(r)]
            strict = [r for r in sub if player_level_beyond_projection(r)]
            entry[f"beyond_projection_{label}"] = len(beyond)
            entry[f"player_level_beyond_projection_{label}"] = len(strict)
            print(
                f"    ANY uncertainty signal favors O while projection favors A: {len(beyond)}; "
                f"excluding the position-constant width/upside: {len(strict)}"
            )

        entry["by_oracle_position"] = breakdown(rows, lambda r: r["oracle_position"])
        entry["by_phase"] = breakdown(rows, lambda r: r["phase"], [p[0] for p in D115.PHASES])
        entry["by_round"] = breakdown(rows, lambda r: r["round"], [str(i) for i in range(1, 17)])
        entry["by_O_projection_tier"] = breakdown(
            rows,
            lambda r: projection_tier(r["O_proj_rank"]),
            ["pos 1-12", "pos 13-24", "pos 25-48", "pos 49+", "unranked"],
        )
        entry["by_O_ecr_tier"] = breakdown(
            rows,
            lambda r: ecr_tier(r["O"]["ecr"]),
            ["ECR 1-50", "ECR 51-100", "ECR 101-150", "ECR 151+", "no ECR"],
        )
        entry["by_season"] = breakdown(
            rows, lambda r: r["season"], [str(s) for s in BACKTEST_SEASONS]
        )
        for name in (
            "by_oracle_position",
            "by_phase",
            "by_O_projection_tier",
            "by_O_ecr_tier",
            "by_season",
            "by_round",
        ):
            print(f"\n  {name.upper()} -- favors-O rate")
            print(
                f"    {'group':<14}{'n':>4}{'regret%':>9}{'proj':>7}{'projV':>7}{'p90':>7}"
                f"{'p90V':>7}{'top24':>7}{'conf':>7}{'risk':>7}{'ecr':>7}{'beyond':>8}"
            )
            for k, g in entry[name].items():
                cells = "".join(
                    f"{'--':>7}" if g[s] is None else f"{g[s]:>7.0%}"
                    for s in (
                        "proj",
                        "proj_vorp",
                        "p90",
                        "p90_vorp",
                        "top24",
                        "confidence",
                        "risk",
                        "ecr",
                    )
                )
                print(
                    f"    {k:<14}{g['n']:>4}{100 * g['regret'] / total:>8.1f}%{cells}"
                    f"{g['beyond_proj']:>8}"
                )

        entry["decomposition"] = decomposition(rows)
        dc = entry["decomposition"]
        print(
            f"\n  SCORE DECOMPOSITION (exact Shapley, score points) -- mean gap A-O "
            f"{dc['mean_score_gap_A_minus_O']:+.1f}; O confidence==0 {dc['O_zero_confidence']}, "
            f"O on 0.7 fallback {dc['O_risk_fallback_0_7']}; A confidence==0 "
            f"{dc['A_zero_confidence']}, A on fallback {dc['A_risk_fallback_0_7']}"
        )
        for f in FACTORS:
            v = dc["factors"][f]
            print(
                f"    {f:<10} mean {v['mean_contribution']:+8.1f}  share {v['share_of_gap']:+7.1%}"
                f"  favors A {v['favors_A']:>4}  favors O {v['favors_O']:>4}  neutralise -> O "
                f"wins {v['neutralise_lets_O_win']:>4}"
            )

        entry["realized_HINDSIGHT"] = {
            "mean_realized_A": mean(r["alpha_realized"] for r in rows),
            "mean_realized_O": mean(r["oracle_realized"] for r in rows),
            "mean_proj_A": mean(r["A"]["proj"] for r in rows),
            "mean_proj_O": mean(r["O"]["proj"] for r in rows),
            "O_realized_above_own_p90": sum(
                1
                for r in rows
                if r["O"]["p90"] is not None and r["oracle_realized"] > r["O"]["p90"]
            ),
            "O_with_p90": sum(1 for r in rows if r["O"]["p90"] is not None),
        }
        rz = entry["realized_HINDSIGHT"]
        print(
            f"\n  REALIZED (HINDSIGHT, never an input): A {rz['mean_realized_A']:.1f} (proj "
            f"{rz['mean_proj_A']:.1f}) vs O {rz['mean_realized_O']:.1f} (proj "
            f"{rz['mean_proj_O']:.1f}); O beat his OWN p90 in {rz['O_realized_above_own_p90']}/"
            f"{rz['O_with_p90']}"
        )
        entry["addressable"] = addressable(rows, total)
        ad = entry["addressable"]
        print(
            f"  ADDRESSABLE (% of total regret): population {ad['population_pct']:.1f}%; any "
            f"upside signal beyond projection {ad['any_upside_beyond_projection_pct']:.1f}% "
            f"({ad['n_any_upside_beyond_projection']} pairs, same-position "
            f"{ad['same_position_beyond_projection']}); player-level only "
            f"{ad['player_level_beyond_projection_pct']:.1f}% "
            f"({ad['n_player_level_beyond_projection']}); risk-neutralised O wins "
            f"{ad['risk_neutralised_O_wins_pct']:.1f}% ({ad['n_risk_neutralised_O_wins']}); "
            f"p90-over-replacement favors O {ad['p90_vorp_favors_O_pct']:.1f}%"
        )

    for label, cap in (("ALL ESTABLISHED", None), ("ECR <= 200", 200.0)):
        sc = selection_control(measured["context"], cap)
        summary[f"selection_control_{label}"] = sc
        print(f"\n{bar}\nSELECTION CONTROL -- {label} ({sc['n']} player-seasons, 2021-2025)\n{bar}")
        print(
            f"  mean within-(season,position) corr with SIGNED residual: {sc['mean_within_group_corr']}"
        )
        er = sc["ecr_range_partial"]
        print(
            f"  ECR range | projection, partial corr (n {er['n']}): signed {er['signed']}  "
            f"absolute {er['absolute']}"
        )
        print(
            f"    {'confidence':<22}{'n':>6}{'point':>8}{'realized':>10}{'signed':>9}"
            f"{'abs':>8}{'beat%':>7}  season CI on signed"
        )
        for k, b in sc["by_confidence_bucket"].items():
            ci = b["signed_residual_season_ci"]["ci"]
            print(
                f"    {k:<22}{b['n']:>6}{b['mean_point']:>8.1f}{b['mean_realized']:>10.1f}"
                f"{b['mean_signed_residual']:>+9.1f}{b['mean_abs_residual']:>8.1f}"
                f"{b['share_beating_projection']:>7.0%}  "
                f"{'--' if ci is None else f'[{ci[0]:+.1f}, {ci[1]:+.1f}]'}"
            )
    return summary


def _src_tree() -> dict:
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()

    return {
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "src_tree_hash_at_head": run(["git", "rev-parse", "HEAD:src/alpha_squad"]),
        "src_dirty": bool(run(["git", "status", "--porcelain", "--", "src/alpha_squad"])),
    }


def _write(out: Path, name: str, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=list))
    print(f"wrote {out / name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("measure", "report"))
    ap.add_argument("--d116", help="directory holding D116's d116_pairs.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    assert_no_realized_inputs_in_policy()
    if a.mode == "measure":
        if not a.d116:
            raise UnreconstructibleError("--d116 <dir with d116_pairs.json> is required")
        con = duckdb.connect(a.db, read_only=True)
        measured = run_measure(con, Path(a.d116))
        d116 = json.loads((Path(a.d116) / "d116_pairs.json").read_text())
        measured["regret_totals"] = {
            f: sum(r["regret_roster"] for r in d116["regret_rows"] if r["league"] == f)
            for f in FORMATS
        }
        measured["provenance"] = {
            **D115._provenance(con, {"mode": "d117_measure", "argv": sys.argv}),
            **_src_tree(),
            "uncertainty_model_version": UNCERTAINTY_MODEL_VERSION,
        }
        _write(out, "d117_measured.json", measured)
        return
    measured = json.loads((out / "d117_measured.json").read_text())
    summary = report(measured, measured["regret_totals"])
    summary["provenance"] = measured["provenance"]
    summary["d116_pairs_sha256"] = measured["d116_pairs_sha256"]
    _write(out, "d117_summary.json", summary)


if __name__ == "__main__":
    main()
