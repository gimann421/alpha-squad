"""D118 -- is player-specific upside predictable before the season from information Alpha
already has?

Read-only research runner. Builds a (player, season) panel of PRESEASON information already stored
in the database, measures the board projection's out-of-sample error, and asks -- strictly
walk-forward -- whether any existing information predicts that error well enough to change a
same-position draft decision. Writes nothing but JSON under `--out`. **No file under
`src/alpha_squad/` is touched and this script is imported by no production path.**

    uv run python scripts/research/d118_upside_predictability.py --mode measure \
        --d117 <dir with d117_measured.json> --out <out>
    uv run python scripts/research/d118_upside_predictability.py --mode report --out <out>

==========================================================================================
PRE-REGISTRATION -- written before any D118 number existed
==========================================================================================

THE QUESTION.  D117 showed Alpha's uncertainty model carries no player-specific upside (its
intervals are the projection plus a per-position constant). D118 asks whether the preseason
information Alpha ALREADY STORES could have predicted which players beat their own projection.
**Diagnostic only: nothing here is a production model, no draft-engine term changes, no external
data is added, and no hyperparameter is searched.**

INVENTORY (every source was checked for pre-season availability before use):
  used      board projection (`load_season_projections`: M6 point for established players, M7 for
            rookies); preseason ECR rank and ecr_best/ecr_worst on the `ro` / `redraft-overall`
            page, latest Jul/Aug scrape of season S; `players` (birth_date -> age at Sep 1 of S,
            rookie_season -> experience, draft_pick); `player_season_stats` for S-1 (games,
            PPG, targets + carries); `player_week_stats` REG weeks of S-1 (mean
            offense_snap_pct, mean target_share); `rookie_predictions.breakout_probability`.
  EXCLUDED  `dynasty_values` -- its only snapshot is 2026-09-18, i.e. AFTER every evaluated
            season; using it would be future leakage. `edge_snapshot` -- empty. Anything from
            season S itself (realized points, games, usage, in-season ECR).

FEATURES (pre-registered; 12 established, 7 rookie; no others will be tried):
  proj, ecr_rank, ecr_range (= worst - best), mkt_vs_model (within-position projection rank
  minus within-position ECR rank: > 0 means the market likes him more than the model), age,
  experience, draft_pick (undrafted = 300), prior_games, prior_ppg, prior_opp_pg ((targets +
  carries) / games), prior_snap_pct, prior_target_share. Rookies have no S-1 season, so the
  rookie cohort uses proj, ecr_rank, ecr_range, mkt_vs_model, age, draft_pick, breakout.
  Missing values are imputed with the (season, position) median of the same cohort, and every
  feature is z-scored within (season, position) -- so a feature can only ever order players
  WITHIN a position, which is where D117 showed cross-position comparisons create artifacts.

POPULATION.  Every QB/RB/WR/TE on the board with a preseason ECR rank in season S; ECR <= 200 is
the decision-relevant slice and is reported beside the whole. Two cohorts: established (M6) and
rookie (M7), never pooled.

TARGETS (all from season S outcomes; never features):
  A  e = realized_S - proj         (signed projection error)
  B  |e|                            (error size)
  C  max(e, 0)                      (positive upside)
  D  e >= +50                       ("substantially beats projection")
  E  e >= +100                      (extreme tail; D116's oracle players averaged ~+160)

WALK-FORWARD.  The brief restricts data to 2021-2025. Evaluation season S uses training rows
from 2021..S-1 only, so the out-of-sample seasons are **2022-2025 (k = 4, t_crit = 3.182)**;
2021 has no prior season in the window and appears only in descriptive, clearly labelled
in-season correlations. Each signal is one ridge regression (alpha = 1.0, FIXED -- not tuned) of
the target on z-scored features with per-position intercepts:
  * one per SINGLE feature (its univariate walk-forward predictor), and
  * one COMBINED model on all pre-registered features of the cohort.
Baselines: chance; `proj` itself; `ecr_rank` itself (both also appear as single features).

METRICS (per signal, out of sample):
  * Spearman of the prediction with e, |e| (B-model), max(e,0), within (season, position),
    averaged; per season; per position; season-clustered CI.
  * AUC of the A-model prediction for D and E events, within (season, position).
  * same-position pairwise concordance with e (chance = 0.5).
  * DECISION LEVEL -- the test that matters: within (season, position), among ECR <= 200 pairs,
    does ordering by proj + e_hat get the REALIZED order right more often than ordering by proj?
    Reported: pairs flipped, share of flips that are correct, net correct flips, and the same for
    CLOSE pairs (|proj gap| <= 30). A relationship too small to flip orderings is not a draft
    signal.
  * OOS R^2 of the A-model against the training-mean (per-position intercept) baseline.

SEQUENCING POPULATION.  D117's measured pairs (D116's C1 AND C2, same vintage, checked). For each
signal: on SAME-POSITION pairs does e_hat favour the oracle player O over Alpha's player A, and
does proj + e_hat actually flip the pair? Cross-position pairs are reported on the engine's
replacement-level scale (proj_vorp + e_hat) and labelled secondary. The oracle's identity is never
a feature. Pairs in 2021, and K/DST players (no features), are counted as undefined.

PERFECT-SIGNAL BOUND.  D115's own `ORACLE_Y1` arm (the shipped rule reading realized points as
its projections) on this vintage, read from D115's `arms` artifact: the share of per-pick regret
a PERFECT upside signal recovers, and what remains even then.

VERDICT RULE (fixed now).  "Predictable" requires ALL THREE, in the established cohort:
  1. out-of-sample Spearman with e whose season-clustered CI excludes 0 AND the same sign in all
     4 OOS seasons;
  2. same-position pairwise decision accuracy (proj + e_hat vs proj) with MORE correct flips than
     incorrect ones, CI on net-correct excluding 0;
  3. flips at least 5% of close ECR <= 200 same-position pairs.
Otherwise: "player-specific upside is not demonstrated as predictable from Alpha's current
information set" -- a statement about this information set, not about all information.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, stdev

import duckdb
import numpy as np
from scipy import stats as scipy_stats

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.league.replacement import load_season_projections

DB = "data/alpha_squad.duckdb"
POSITIONS = ("QB", "RB", "WR", "TE")
ECR_TYPE, ECR_PAGE = "ro", "redraft-overall"
DECISION_ECR_CAP = 200.0
CLOSE_PAIR_GAP = 30.0
RIDGE_ALPHA = 1.0  # fixed, declared; never searched
UNDRAFTED_PICK = 300.0
BEAT_THRESHOLD, EXTREME_THRESHOLD = 50.0, 100.0
FIRST_SEASON = min(BACKTEST_SEASONS)
OOS_SEASONS = tuple(s for s in BACKTEST_SEASONS if s > FIRST_SEASON)
T_CRIT = {4: 3.182, 5: 2.776, 3: 4.303}
MIN_FLIP_SHARE = 0.05

ESTABLISHED_FEATURES = (
    "proj",
    "ecr_rank",
    "ecr_range",
    "mkt_vs_model",
    "age",
    "experience",
    "draft_pick",
    "prior_games",
    "prior_ppg",
    "prior_opp_pg",
    "prior_snap_pct",
    "prior_target_share",
)
ROOKIE_FEATURES = ("proj", "ecr_rank", "ecr_range", "mkt_vs_model", "age", "draft_pick", "breakout")
COHORT_FEATURES = {"established": ESTABLISHED_FEATURES, "rookie": ROOKIE_FEATURES}
COMBINED = "COMBINED"


class UnreconstructibleError(RuntimeError):
    """D118 stops rather than substituting."""


# --------------------------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------------------------
def zscore_within(rows: list[dict], feature: str, group_key) -> None:
    """z-score `feature` within each group, writing `z_<feature>`. Missing values are imputed to
    the group median first (a constant group scores 0)."""
    groups: dict = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)
    for g in groups.values():
        present = [r[feature] for r in g if r[feature] is not None]
        med = float(np.median(present)) if present else 0.0
        vals = [r[feature] if r[feature] is not None else med for r in g]
        mu = mean(vals)
        sd = stdev(vals) if len(vals) > 1 else 0.0
        for r, v in zip(g, vals, strict=True):
            r[f"z_{feature}"] = 0.0 if sd == 0 else (v - mu) / sd


def fit_ridge(x: np.ndarray, y: np.ndarray, groups: list[str], alpha: float = RIDGE_ALPHA):
    """Ridge with an UNPENALISED intercept per group (position). Returns (coef, {group: b0})."""
    levels = sorted(set(groups))
    d = np.array([[1.0 if g == lv else 0.0 for lv in levels] for g in groups])
    design = np.hstack([d, x]) if x.size else d
    penalty = np.diag([0.0] * len(levels) + [alpha] * (x.shape[1] if x.size else 0))
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return beta[len(levels) :], dict(zip(levels, beta[: len(levels)], strict=True))


def predict_ridge(coef, intercepts, x: np.ndarray, groups: list[str]) -> np.ndarray:
    fallback = float(np.mean(list(intercepts.values())))
    b0 = np.array([intercepts.get(g, fallback) for g in groups])
    return b0 + (x @ coef if x.size else 0.0)


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """Mann-Whitney AUC; None when a class is empty."""
    pos = [s for s, lab in zip(scores, labels, strict=True) if lab]
    neg = [s for s, lab in zip(scores, labels, strict=True) if not lab]
    if not pos or not neg:
        return None
    ranks = scipy_stats.rankdata(scores)
    r_pos = sum(r for r, lab in zip(ranks, labels, strict=True) if lab)
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return float(scipy_stats.spearmanr(xs, ys).correlation)


def pairwise_concordance(pred: list[float], target: list[float]) -> tuple[int, int]:
    """(concordant, decisive) over all pairs where both the prediction and the target differ."""
    conc = dec = 0
    n = len(pred)
    for i in range(n):
        for j in range(i + 1, n):
            dp, dt = pred[i] - pred[j], target[i] - target[j]
            if dp == 0 or dt == 0:
                continue
            dec += 1
            conc += (dp > 0) == (dt > 0)
    return conc, dec


def decision_flips(proj, adj, realized, close_gap: float | None = None) -> dict:
    """Among pairs, how often does ordering by `adj` (proj + e_hat) differ from ordering by
    `proj`, and when it does, is the new order the realized one?"""
    flipped = correct = pairs = base_correct = 0
    gain = 0.0
    n = len(proj)
    for i in range(n):
        for j in range(i + 1, n):
            if realized[i] == realized[j] or proj[i] == proj[j]:
                continue
            if close_gap is not None and abs(proj[i] - proj[j]) > close_gap:
                continue
            pairs += 1
            base_correct += (proj[i] > proj[j]) == (realized[i] > realized[j])
            if (proj[i] > proj[j]) != (adj[i] > adj[j]):
                flipped += 1
                correct += (adj[i] > adj[j]) == (realized[i] > realized[j])
                # realized points of the adjusted choice minus the projection's choice
                pick_adj, pick_proj = (i, j) if adj[i] > adj[j] else (j, i)
                gain += realized[pick_adj] - realized[pick_proj]
    return {
        "pairs": pairs,
        "flipped": flipped,
        "flips_correct": correct,
        "base_correct": base_correct,
        "gain": gain,
    }


def season_ci(values: dict) -> dict:
    vals = [v for v in values.values() if v is not None]
    k = len(vals)
    if k < 2:
        return {"k": k, "mean": vals[0] if vals else None, "ci": None, "mde": None}
    md, se = mean(vals), stdev(vals) / math.sqrt(k)
    t = T_CRIT.get(k, 2.0)
    return {"k": k, "mean": md, "ci": (md - t * se, md + t * se), "mde": t * se}


def age_on(birth: date | None, season: int) -> float | None:
    if birth is None:
        return None
    return (date(season, 9, 1) - birth).days / 365.25


# --------------------------------------------------------------------------------------------
# MODE: measure -- the panel
# --------------------------------------------------------------------------------------------
def _market(con, season: int) -> dict[str, tuple[float, float | None, float | None]]:
    rows = con.execute(
        """
        SELECT player_id, ecr_rank, ecr_best, ecr_worst FROM (
            SELECT player_id, ecr_rank, ecr_best, ecr_worst,
                   row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND page_type = ? AND year(scrape_date) = ?
              AND month(scrape_date) IN (7, 8)
        ) WHERE rn = 1
        """,
        [ECR_TYPE, ECR_PAGE, season],
    ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def build_panel(con) -> list[dict]:
    players = {
        r[0]: {"birth": r[1], "rookie_season": r[2], "draft_pick": r[3]}
        for r in con.execute(
            "SELECT player_id, birth_date, rookie_season, draft_pick FROM players"
        ).fetchall()
    }
    rows: list[dict] = []
    for season in BACKTEST_SEASONS:
        projections, positions = load_season_projections(con, season)
        m6 = {
            r[0]
            for r in con.execute(
                "SELECT player_id FROM uncertainty_predictions WHERE season = ? "
                "AND model_version = 'uncertainty_catboost_v2'",
                [season],
            ).fetchall()
        }
        rookie = dict(
            con.execute(
                "SELECT player_id, breakout_probability FROM rookie_predictions "
                "WHERE draft_class = ?",
                [season],
            ).fetchall()
        )
        prior = {
            r[0]: r[1:]
            for r in con.execute(
                "SELECT player_id, games_played, ppr_points_per_game, total_targets, "
                "total_carries FROM player_season_stats WHERE season = ?",
                [season - 1],
            ).fetchall()
        }
        weekly = {
            r[0]: r[1:]
            for r in con.execute(
                """
                SELECT w.player_id, avg(w.offense_snap_pct), avg(w.target_share)
                FROM player_week_stats w JOIN games g ON g.game_id = w.game_id
                WHERE w.season = ? AND g.game_type = 'REG' GROUP BY 1
                """,
                [season - 1],
            ).fetchall()
        }
        market = _market(con, season)
        ids = [
            p
            for p in projections
            if positions.get(p) in POSITIONS and p in market and (p in m6 or p in rookie)
        ]
        realized = _actual_points_for(con, season, ids)
        for pid in ids:
            info = players.get(pid, {})
            ecr, best, worst = market[pid]
            pr = prior.get(pid)
            wk = weekly.get(pid)
            games = pr[0] if pr else None
            cohort = "established" if pid in m6 else "rookie"
            e = realized[pid] - projections[pid]
            rows.append(
                {
                    "player_id": pid,
                    "season": season,
                    "position": positions[pid],
                    "cohort": cohort,
                    "proj": projections[pid],
                    "realized": realized[pid],
                    "ecr_rank": ecr,
                    "ecr_range": None if best is None or worst is None else worst - best,
                    "age": age_on(info.get("birth"), season),
                    "experience": None
                    if info.get("rookie_season") is None
                    else season - info["rookie_season"],
                    "draft_pick": UNDRAFTED_PICK
                    if info.get("draft_pick") is None
                    else float(info["draft_pick"]),
                    "prior_games": games,
                    "prior_ppg": pr[1] if pr else None,
                    "prior_opp_pg": ((pr[2] or 0) + (pr[3] or 0)) / games if pr and games else None,
                    "prior_snap_pct": wk[0] if wk else None,
                    "prior_target_share": wk[1] if wk else None,
                    "breakout": rookie.get(pid),
                    "e": e,
                    "abs_e": abs(e),
                    "e_pos": max(e, 0.0),
                    "beat50": e >= BEAT_THRESHOLD,
                    "beat100": e >= EXTREME_THRESHOLD,
                }
            )
    # Market-vs-model disagreement: within-(season, position, cohort-agnostic) ranks.
    groups: dict = defaultdict(list)
    for r in rows:
        groups[(r["season"], r["position"])].append(r)
    for g in groups.values():
        by_proj = {r["player_id"]: i + 1 for i, r in enumerate(sorted(g, key=lambda r: -r["proj"]))}
        by_ecr = {
            r["player_id"]: i + 1 for i, r in enumerate(sorted(g, key=lambda r: r["ecr_rank"]))
        }
        for r in g:
            r["mkt_vs_model"] = by_proj[r["player_id"]] - by_ecr[r["player_id"]]
    return rows


def walk_forward(rows: list[dict], cohort: str, target: str) -> dict[str, dict[tuple, float]]:
    """{signal: {(player_id, season): prediction}} for every OOS season, per cohort."""
    feats = COHORT_FEATURES[cohort]
    sub = [r for r in rows if r["cohort"] == cohort]
    for f in feats:
        zscore_within(sub, f, lambda r: (r["season"], r["position"]))
    signals = {f: (f,) for f in feats}
    signals[COMBINED] = feats
    out: dict[str, dict[tuple, float]] = {s: {} for s in signals}
    for season in OOS_SEASONS:
        train = [r for r in sub if r["season"] < season]
        test = [r for r in sub if r["season"] == season]
        if not train or not test:
            continue
        for name, fs in signals.items():
            xtr = np.array([[r[f"z_{f}"] for f in fs] for r in train])
            ytr = np.array([r[target] for r in train], dtype=float)
            coef, b0 = fit_ridge(xtr, ytr, [r["position"] for r in train])
            xte = np.array([[r[f"z_{f}"] for f in fs] for r in test])
            pred = predict_ridge(coef, b0, xte, [r["position"] for r in test])
            for r, p in zip(test, pred, strict=True):
                out[name][(r["player_id"], r["season"])] = float(p)
    return out


# --------------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------------
def _groups(rows, cap=None):
    g: dict = defaultdict(list)
    for r in rows:
        if cap is None or r["ecr_rank"] <= cap:
            g[(r["season"], r["position"])].append(r)
    return g


def evaluate_signal(rows: list[dict], pred_a: dict, pred_b: dict, cap=None) -> dict:
    """All OOS metrics for one signal on one cohort."""
    rows = [r for r in rows if (r["player_id"], r["season"]) in pred_a]
    groups = _groups(rows, cap)
    per_season: dict = defaultdict(lambda: defaultdict(list))
    per_pos: dict = defaultdict(lambda: defaultdict(list))
    conc_tot = dec_tot = 0
    keys = ("pairs", "flipped", "flips_correct", "base_correct", "gain")
    flips = dict.fromkeys(keys, 0)
    close = dict.fromkeys(keys, 0)
    net_by_season: dict = defaultdict(int)
    gain_by_season: dict = defaultdict(float)
    flipped_by_season: dict = defaultdict(int)
    sse = sse0 = 0.0
    for (season, pos), g in groups.items():
        p = [pred_a[(r["player_id"], r["season"])] for r in g]
        pb = [pred_b[(r["player_id"], r["season"])] for r in g]
        e = [r["e"] for r in g]
        metrics = {
            "signed": spearman(p, e),
            "abs": spearman(pb, [r["abs_e"] for r in g]),
            "upside": spearman(p, [r["e_pos"] for r in g]),
            "auc50": auc(p, [r["beat50"] for r in g]),
            "auc100": auc(p, [r["beat100"] for r in g]),
        }
        for k, v in metrics.items():
            if v is not None:
                per_season[season][k].append(v)
                per_pos[pos][k].append(v)
        c, d = pairwise_concordance(p, e)
        conc_tot += c
        dec_tot += d
        proj = [r["proj"] for r in g]
        adj = [a + b for a, b in zip(proj, p, strict=True)]
        real = [r["realized"] for r in g]
        f_all = decision_flips(proj, adj, real)
        f_close = decision_flips(proj, adj, real, CLOSE_PAIR_GAP)
        for k in flips:
            flips[k] += f_all[k]
            close[k] += f_close[k]
        net_by_season[season] += 2 * f_all["flips_correct"] - f_all["flipped"]
        gain_by_season[season] += f_all["gain"]
        flipped_by_season[season] += f_all["flipped"]
        mu = mean(e)
        sse += sum((ei - pi) ** 2 for ei, pi in zip(e, p, strict=True))
        sse0 += sum((ei - mu) ** 2 for ei in e)
    season_mean = {s: {k: mean(v) for k, v in d.items()} for s, d in per_season.items()}
    pos_mean = {s: {k: mean(v) for k, v in d.items()} for s, d in per_pos.items()}
    signed_by_season = {s: v.get("signed") for s, v in season_mean.items()}
    return {
        "n": sum(len(g) for g in groups.values()),
        "signed": season_ci(signed_by_season),
        "abs": season_ci({s: v.get("abs") for s, v in season_mean.items()}),
        "upside": season_ci({s: v.get("upside") for s, v in season_mean.items()}),
        "auc50": season_ci({s: v.get("auc50") for s, v in season_mean.items()}),
        "auc100": season_ci({s: v.get("auc100") for s, v in season_mean.items()}),
        "signed_by_season": signed_by_season,
        "signed_same_sign_all_seasons": len({(v > 0) for v in signed_by_season.values() if v}) == 1
        and len([v for v in signed_by_season.values() if v is not None]) == len(OOS_SEASONS),
        "by_position": pos_mean,
        "pairwise_concordance": conc_tot / dec_tot if dec_tot else None,
        "pairwise_decisive": dec_tot,
        "decision_all": flips,
        "decision_close": close,
        "net_correct_flips_by_season": dict(net_by_season),
        "net_correct_flips_ci": season_ci({s: float(v) for s, v in net_by_season.items()}),
        "ordering_accuracy_proj": flips["base_correct"] / flips["pairs"]
        if flips["pairs"]
        else None,
        "ordering_accuracy_adjusted": (
            (flips["base_correct"] + 2 * flips["flips_correct"] - flips["flipped"]) / flips["pairs"]
            if flips["pairs"]
            else None
        ),
        "gain_per_flip": flips["gain"] / flips["flipped"] if flips["flipped"] else None,
        "gain_per_flip_ci": season_ci(
            {
                s: gain_by_season[s] / flipped_by_season[s]
                for s in gain_by_season
                if flipped_by_season[s]
            }
        ),
        "oos_r2_vs_position_mean": 1 - sse / sse0 if sse0 else None,
    }


def descriptive_in_season(rows: list[dict], cohort: str) -> dict:
    """NOT out of sample: per-season within-(season, position) Spearman of each raw feature with
    e, all five seasons, for sign-stability reading only."""
    out = {}
    for f in COHORT_FEATURES[cohort]:
        per_season = {}
        for season in BACKTEST_SEASONS:
            vals = []
            for (s, _pos), g in _groups([r for r in rows if r["cohort"] == cohort]).items():
                if s != season:
                    continue
                xs = [r[f] for r in g if r[f] is not None]
                ys = [r["e"] for r in g if r[f] is not None]
                rho = spearman(xs, ys)
                if rho is not None:
                    vals.append(rho)
            per_season[season] = mean(vals) if vals else None
        out[f] = per_season
    return out


def sequencing_pairs(pairs: list[dict], preds: dict, panel_index: dict) -> dict:
    """D117's pairs: does each signal favour O, and does proj + e_hat flip the pair?"""
    out = {}
    for sig in preds:
        res = {
            "same": {
                "n": 0,
                "defined": 0,
                "favors_O": 0,
                "flips_to_O": 0,
                "regret_flipped": 0.0,
                "ehat_gap_O_minus_A": [],
                "base_gap_A_minus_O": [],
            },
            "cross": {
                "n": 0,
                "defined": 0,
                "favors_O": 0,
                "flips_to_O": 0,
                "regret_flipped": 0.0,
                "ehat_gap_O_minus_A": [],
                "base_gap_A_minus_O": [],
            },
        }
        for p in pairs:
            bucket = res["same" if p["same_position"] else "cross"]
            bucket["n"] += 1
            ka, ko = (p["alpha"], p["season"]), (p["oracle"], p["season"])
            ea, eo = preds[sig].get(ka), preds[sig].get(ko)
            if ea is None or eo is None:
                continue
            bucket["defined"] += 1
            bucket["favors_O"] += eo > ea
            if p["same_position"]:
                base_a, base_o = panel_index[ka]["proj"], panel_index[ko]["proj"]
            else:
                base_a, base_o = p["A"]["proj_vorp"], p["O"]["proj_vorp"]
            bucket["ehat_gap_O_minus_A"].append(eo - ea)
            bucket["base_gap_A_minus_O"].append(base_a - base_o)
            if base_o + eo > base_a + ea:
                bucket["flips_to_O"] += 1
                bucket["regret_flipped"] += p["regret_roster"]
        for b in res.values():
            for k in ("ehat_gap_O_minus_A", "base_gap_A_minus_O"):
                b[f"mean_{k}"] = mean(b[k]) if b[k] else None
                del b[k]
        out[sig] = res
    return out


def _src_tree() -> dict:
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()

    return {
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "src_tree_hash_at_head": run(["git", "rev-parse", "HEAD:src/alpha_squad"]),
        "src_dirty": bool(run(["git", "status", "--porcelain", "--", "src/alpha_squad"])),
    }


def run_measure(con, d117_dir: Path) -> dict:
    t0 = time.time()
    vintage = compute_board_vintage(con)
    d117 = json.loads((d117_dir / "d117_measured.json").read_text())
    if d117["provenance"]["board_vintage_combined"] != vintage.combined_hash:
        raise UnreconstructibleError("D117 artifact and database are different vintages")
    panel = build_panel(con)
    preds: dict = {}
    for cohort in COHORT_FEATURES:
        preds[cohort] = {
            "A": walk_forward(panel, cohort, "e"),
            "B": walk_forward(panel, cohort, "abs_e"),
        }
    print(f"  panel {len(panel)} rows, walk-forward done ({time.time() - t0:.0f}s)", flush=True)
    return {
        "panel": panel,
        "preds": {
            c: {
                t: {s: {f"{k[0]}|{k[1]}": v for k, v in d.items()} for s, d in m.items()}
                for t, m in v.items()
            }
            for c, v in preds.items()
        },
        "d117_pairs": d117["pairs"],
        "regret_totals": d117["regret_totals"],
        "provenance": {
            "board_vintage_combined": vintage.combined_hash,
            "board_vintage_per_season": {str(s): h for s, h in vintage.season_hashes.items()},
            "upstream_board_sha256": vintage.board_sha256,
            "upstream_idmap_sha256": vintage.idmap_sha256,
            "d117_measured_sha256": hashlib.sha256(
                (d117_dir / "d117_measured.json").read_bytes()
            ).hexdigest(),
            "argv": sys.argv,
            **_src_tree(),
        },
    }


def _unkey(d: dict) -> dict:
    return {(k.split("|")[0], int(k.split("|")[1])): v for k, v in d.items()}


def perfect_signal_bound(arm_files: list[Path], regret_totals: dict) -> dict:
    """D115's ORACLE_Y1 arm (perfect projections into the shipped rule), one-step recovery."""
    out = {}
    for path in arm_files:
        if not path.exists():
            continue
        rows = json.loads(path.read_text())["rows"]
        for league in {r["league"] for r in rows}:
            orc = [r for r in rows if r["league"] == league and r["arm"] == "ORACLE_Y1"]
            per_season = defaultdict(list)
            for r in orc:
                per_season[r["season"]].append(r["delta"])
            total = regret_totals.get(league)
            out[league] = {
                "n": len(orc),
                "mean_delta": mean(r["delta"] for r in orc) if orc else None,
                "recovery_of_total_regret": sum(r["delta"] for r in orc) / total if total else None,
                "per_season_mean_delta": {s: mean(v) for s, v in per_season.items()},
            }
    return out


def report(measured: dict, arm_files: list[Path]) -> dict:
    bar = "=" * 100
    panel = measured["panel"]
    idx = {(r["player_id"], r["season"]): r for r in panel}
    summary: dict = {"cohorts": {}}
    for cohort in COHORT_FEATURES:
        pa = {s: _unkey(d) for s, d in measured["preds"][cohort]["A"].items()}
        pb = {s: _unkey(d) for s, d in measured["preds"][cohort]["B"].items()}
        rows = [r for r in panel if r["cohort"] == cohort]
        entry = summary["cohorts"].setdefault(cohort, {})
        entry["n_rows"] = len(rows)
        entry["n_by_season"] = {
            s: sum(1 for r in rows if r["season"] == s) for s in BACKTEST_SEASONS
        }
        entry["event_rates"] = {
            "beat50": mean(float(r["beat50"]) for r in rows) if rows else None,
            "beat100": mean(float(r["beat100"]) for r in rows) if rows else None,
            "mean_e": mean(r["e"] for r in rows) if rows else None,
            "sd_e": stdev(r["e"] for r in rows) if len(rows) > 1 else None,
        }
        print(
            f"\n{bar}\nD118 -- {cohort.upper()} cohort: {len(rows)} player-seasons "
            f"{entry['n_by_season']}; e mean {entry['event_rates']['mean_e']:+.1f} sd "
            f"{entry['event_rates']['sd_e']:.1f}; beat+50 {entry['event_rates']['beat50']:.1%}; "
            f"beat+100 {entry['event_rates']['beat100']:.1%}\n{bar}"
        )
        for label, cap in (("ALL", None), ("ECR<=200", DECISION_ECR_CAP)):
            tab = {s: evaluate_signal(rows, pa[s], pb[s], cap) for s in pa}
            entry[f"oos_{label}"] = tab
            print(f"\n  OUT-OF-SAMPLE ({', '.join(map(str, OOS_SEASONS))}) -- {label}")
            print(
                f"    {'signal':<19}{'n':>6}{'rho(e)':>8}{'CI':>17}{'all4':>6}{'rho|e|':>8}"
                f"{'rho e+':>8}{'AUC50':>7}{'AUC100':>8}{'pair':>7}{'R2':>7}"
                f"{'flip%':>7}{'flipOK':>8}{'close flip%':>12}{'closeOK':>8}"
            )
            for sig, m in tab.items():
                s = m["signed"]
                ci = "--" if s["ci"] is None else f"[{s['ci'][0]:+.2f},{s['ci'][1]:+.2f}]"
                da, dc = m["decision_all"], m["decision_close"]

                def f(x, spec="+.3f"):
                    return "--" if x is None else format(x, spec)

                print(
                    f"    {sig:<19}{m['n']:>6}{f(s['mean']):>8}{ci:>17}"
                    f"{'Y' if m['signed_same_sign_all_seasons'] else 'n':>6}"
                    f"{f(m['abs']['mean']):>8}{f(m['upside']['mean']):>8}"
                    f"{f(m['auc50']['mean'], '.3f'):>7}{f(m['auc100']['mean'], '.3f'):>8}"
                    f"{f(m['pairwise_concordance'], '.3f'):>7}"
                    f"{f(m['oos_r2_vs_position_mean'], '+.3f'):>7}"
                    f"{(da['flipped'] / da['pairs'] if da['pairs'] else 0):>7.1%}"
                    f"{(da['flips_correct'] / da['flipped'] if da['flipped'] else 0):>8.1%}"
                    f"{(dc['flipped'] / dc['pairs'] if dc['pairs'] else 0):>12.1%}"
                    f"{(dc['flips_correct'] / dc['flipped'] if dc['flipped'] else 0):>8.1%}"
                )
            print("    decision magnitude (ALL pairs in slice):")
            for sig, m in tab.items():
                g = m["gain_per_flip_ci"]
                gci = "--" if g["ci"] is None else f"[{g['ci'][0]:+.1f},{g['ci'][1]:+.1f}]"
                acc_p, acc_a = m["ordering_accuracy_proj"], m["ordering_accuracy_adjusted"]
                print(
                    f"      {sig:<19} order acc proj {acc_p:.3f} -> adj {acc_a:.3f}  "
                    f"net correct flips/season {m['net_correct_flips_ci']['mean']:+.1f} "
                    f"CI {m['net_correct_flips_ci']['ci']}  realized gain per flip "
                    f"{'--' if m['gain_per_flip'] is None else format(m['gain_per_flip'], '+.1f')}"
                    f" season CI {gci}"
                )
        entry["descriptive_in_season_NOT_OOS"] = descriptive_in_season(panel, cohort)
        print("\n  DESCRIPTIVE, in-season (NOT out of sample): rho(raw feature, e) by season")
        for feat, ps in entry["descriptive_in_season_NOT_OOS"].items():
            cells = "  ".join(f"{s}:{'--' if v is None else f'{v:+.2f}'}" for s, v in ps.items())
            print(f"    {feat:<19}{cells}")

    # Combined-model per-position and per-season detail (established, ECR<=200)
    est = summary["cohorts"]["established"]["oos_ECR<=200"][COMBINED]
    print(
        f"\n  COMBINED established ECR<=200 by position: {json.dumps(est['by_position'], default=str)}"
    )
    print(f"  COMBINED signed rho by season: {est['signed_by_season']}")
    print(
        f"  COMBINED net correct flips by season: {est['net_correct_flips_by_season']} CI {est['net_correct_flips_ci']}"
    )

    # Sequencing pairs
    merged: dict = {}
    for cohort in COHORT_FEATURES:
        for s, d in measured["preds"][cohort]["A"].items():
            merged.setdefault(s, {}).update(_unkey(d))
    summary["sequencing"] = {}
    for league, total in measured["regret_totals"].items():
        pairs = [p for p in measured["d117_pairs"] if p["league"] == league]
        res = sequencing_pairs(pairs, merged, idx)
        summary["sequencing"][league] = res
        same_n = sum(1 for p in pairs if p["same_position"])
        print(
            f"\n{bar}\nSEQUENCING PAIRS -- {league}: {len(pairs)} pairs ({same_n} same-position); "
            f"trained signals exist for {', '.join(map(str, OOS_SEASONS))} only\n{bar}"
        )
        print(
            f"    {'signal':<19}{'same def':>9}{'fav O':>7}{'flip->O':>8}{'regret%':>9}"
            f"{'cross def':>10}{'fav O':>7}{'flip->O':>8}{'regret%':>9}"
        )
        for sig, r in res.items():
            s, c = r["same"], r["cross"]
            if sig in (COMBINED, "mkt_vs_model", "proj", "age"):
                print(
                    f"      [{sig}] same-position mean e_hat gap O-A "
                    f"{s['mean_ehat_gap_O_minus_A']} vs projection gap A-O "
                    f"{s['mean_base_gap_A_minus_O']}"
                )
            print(
                f"    {sig:<19}{s['defined']:>9}{s['favors_O']:>7}{s['flips_to_O']:>8}"
                f"{100 * s['regret_flipped'] / total:>8.1f}%{c['defined']:>10}{c['favors_O']:>7}"
                f"{c['flips_to_O']:>8}{100 * c['regret_flipped'] / total:>8.1f}%"
            )
    summary["perfect_signal_bound"] = perfect_signal_bound(arm_files, measured["regret_totals"])
    print(
        f"\n  PERFECT-SIGNAL BOUND (D115 ORACLE_Y1, this vintage): {summary['perfect_signal_bound']}"
    )
    return summary


def _write(out: Path, name: str, payload: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    print(f"wrote {out / name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("measure", "report"))
    ap.add_argument("--d117", help="directory holding d117_measured.json")
    ap.add_argument(
        "--arms", action="append", default=[], help="D115 d115_arms.json files (perfect bound)"
    )
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if a.mode == "measure":
        if not a.d117:
            raise UnreconstructibleError("--d117 <dir with d117_measured.json> is required")
        con = duckdb.connect(a.db, read_only=True)
        _write(out, "d118_measured.json", run_measure(con, Path(a.d117)))
        return
    measured = json.loads((out / "d118_measured.json").read_text())
    summary = report(measured, [Path(p) for p in a.arms])
    summary["provenance"] = measured["provenance"]
    _write(out, "d118_summary.json", summary)


if __name__ == "__main__":
    main()
