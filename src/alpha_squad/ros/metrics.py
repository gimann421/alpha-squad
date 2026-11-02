"""Evaluation metrics for ROS QB forecasts (D116).

Unit of analysis. Rows inside one snapshot share a schedule, a market and most of their remaining
games; snapshots inside one season share most of their remaining games with each other; so the
independent unit is the SEASON, not the player row or the pair. Every metric here is first
computed per (season, snapshot), then averaged within season, then across seasons, and
``block_bootstrap`` resamples whole seasons and, inside each, whole snapshots.

Prespecified constants (fixed before any result was seen; see docs/ROS_QB_TRADE_MODEL.md):

* ``TIE_PTS_PER_GAME`` -- two QBs are "tied" in hindsight if their realized ROS totals differ by
  less than 0.5 points per remaining game.
* decision windows ``(1, 6)``, ``(4, 15)``, ``(8, 20)`` -- the ECR-rank bands named in the brief.
* ``LARGE_REGRET_PTS`` -- a "large mistake" is ROS regret of 40+ points (~4 points/game).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats as sps

TIE_PTS_PER_GAME = 0.5
LARGE_REGRET_PTS = 40.0
WINDOWS: dict[str, tuple[int, int]] = {"top6": (1, 6), "qb4_15": (4, 15), "qb8_20": (8, 20)}
PAIR_BANDS: dict[str, tuple[int, int]] = {**WINDOWS}
SIMILAR_ECR_GAP = 2.0  # |delta ECR| <= 2 ranks, both inside the top 24
TIER_EDGES = [(1, 6, "QB1-6"), (7, 12, "QB7-12"), (13, 24, "QB13-24"), (25, 36, "QB25-36")]
RUSHER_ATT_PG = 5.0  # season-to-date QB carries per game; fixed threshold


# ----------------------------------------------------------------------------------------
# point accuracy
# ----------------------------------------------------------------------------------------
def point_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    e = p - y
    out = {
        "n": float(len(y)),
        "mae": float(np.mean(np.abs(e))),
        "rmse": float(np.sqrt(np.mean(e**2))),
        "mean_error": float(np.mean(e)),
    }
    if len(y) > 2 and np.std(p) > 1e-12:
        slope, intercept, *_ = sps.linregress(p, y)
        out.update(calib_slope=float(slope), calib_intercept=float(intercept))
    else:
        out.update(calib_slope=np.nan, calib_intercept=np.nan)
    return out


# ----------------------------------------------------------------------------------------
# rank accuracy (per snapshot)
# ----------------------------------------------------------------------------------------
def rank_metrics_snapshot(g: pd.DataFrame, pred_col: str = "pred_total") -> dict[str, float]:
    y = g["y_total"].to_numpy()
    p = g[pred_col].to_numpy()
    if len(g) < 5 or np.std(p) < 1e-12:
        sp = kt = np.nan
    else:
        sp = float(sps.spearmanr(p, y).correlation)
        kt = float(sps.kendalltau(p, y).correlation)
    pr = sps.rankdata(-p, method="min")
    ar = sps.rankdata(-y, method="min")
    out = {"spearman": sp, "kendall": kt, "mean_abs_rank_err": float(np.mean(np.abs(pr - ar)))}
    for k in (6, 12, 24):
        kk = min(k, len(g))
        top_p = set(np.argsort(-p, kind="stable")[:kk])
        top_a = set(np.argsort(-y, kind="stable")[:kk])
        out[f"top{k}_hit"] = len(top_p & top_a) / kk
    return out


# ----------------------------------------------------------------------------------------
# pairs
# ----------------------------------------------------------------------------------------
def band_pairs(g: pd.DataFrame, lo: int, hi: int) -> list[tuple[int, int]]:
    idx = g.index[(g["ecr_rank"] >= lo) & (g["ecr_rank"] <= hi)].tolist()
    return list(combinations(idx, 2))


def similar_pairs(g: pd.DataFrame) -> list[tuple[int, int]]:
    top = g[g["ecr_rank"] <= 24]
    out = []
    for i, j in combinations(top.index.tolist(), 2):
        if abs(top.at[i, "ecr"] - top.at[j, "ecr"]) <= SIMILAR_ECR_GAP:
            out.append((i, j))
    return out


def pair_frame(
    g: pd.DataFrame, pairs: list[tuple[int, int]], pred_col: str = "pred_total"
) -> pd.DataFrame:
    """One row per pair with signed prediction gap, realized gap, outcome and tie flag."""
    if not pairs:
        return pd.DataFrame(columns=["dpred", "dact", "tie", "win", "score", "nbar", "pred_tie"])
    i, j = zip(*pairs, strict=True)
    gi, gj = g.loc[list(i)], g.loc[list(j)]
    dpred = gi[pred_col].to_numpy() - gj[pred_col].to_numpy()
    dact = gi["y_total"].to_numpy() - gj["y_total"].to_numpy()
    nbar = (gi["n_remaining"].to_numpy() + gj["n_remaining"].to_numpy()) / 2.0
    tie = np.abs(dact) < TIE_PTS_PER_GAME * nbar
    pred_tie = np.abs(dpred) < 1e-9
    win = (np.sign(dpred) == np.sign(dact)).astype(float)
    score = np.where(tie | pred_tie, 0.5, win)
    return pd.DataFrame(
        {
            "dpred": dpred,
            "dact": dact,
            "tie": tie,
            "win": win,
            "score": score,
            "nbar": nbar,
            "pred_tie": pred_tie,
        }
    )


def pairwise_snapshot(g: pd.DataFrame, pred_col: str = "pred_total") -> dict[str, float]:
    out: dict[str, float] = {}
    sets = {name: band_pairs(g, lo, hi) for name, (lo, hi) in PAIR_BANDS.items()}
    sets["similar"] = similar_pairs(g)
    for name, pairs in sets.items():
        pf = pair_frame(g, pairs, pred_col)
        out[f"pw_{name}"] = float(pf["score"].mean()) if len(pf) else np.nan
        dec = pf[~pf["tie"] & ~pf["pred_tie"]]
        out[f"pw_{name}_decisive"] = float(dec["win"].mean()) if len(dec) else np.nan
        out[f"pw_{name}_tie_share"] = float(pf["tie"].mean()) if len(pf) else np.nan
        out[f"n_pairs_{name}"] = float(len(pf))
    return out


GAP_BINS = [(0, 5, "<5"), (5, 15, "5-15"), (15, 30, "15-30"), (30, 1e9, "30+")]


def pairwise_by_gap(df: pd.DataFrame, pred_col: str = "pred_total") -> pd.DataFrame:
    """Accuracy of decisive pairs by the MODEL's own predicted gap (total points). Pooled over
    snapshots, so use for shape only; inference goes through the per-snapshot metrics."""
    rows = []
    for (_, _), g in df.groupby(["season", "snapshot_week"]):
        g = g.reset_index(drop=True)
        pf = pair_frame(g, band_pairs(g, 1, 24), pred_col)
        rows.append(pf)
    pf = pd.concat(rows, ignore_index=True)
    pf = pf[~pf["tie"] & ~pf["pred_tie"]]
    out = []
    for lo, hi, lab in GAP_BINS:
        sub = pf[(pf["dpred"].abs() >= lo) & (pf["dpred"].abs() < hi)]
        out.append(
            {
                "pred_gap_pts": lab,
                "n_pairs": len(sub),
                "accuracy": float(sub["win"].mean()) if len(sub) else np.nan,
            }
        )
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------------------
# decision regret
# ----------------------------------------------------------------------------------------
def regret_snapshot(g: pd.DataFrame, pred_col: str = "pred_total") -> dict[str, float]:
    """For each window: choose the QB with the highest predicted ROS total; regret = realized best
    in the window minus realized pick. ``vs_ecr`` = realized pick minus realized ECR-top pick."""
    out: dict[str, float] = {}
    for name, (lo, hi) in WINDOWS.items():
        w = g[(g["ecr_rank"] >= lo) & (g["ecr_rank"] <= hi)]
        if len(w) < 2:
            continue
        pick = w.loc[w[pred_col].idxmax()]
        ecr_pick = w.loc[w["ecr_rank"].idxmin()]
        out[f"regret_{name}"] = float(w["y_total"].max() - pick["y_total"])
        out[f"realized_{name}"] = float(pick["y_total"])
        out[f"vs_ecr_{name}"] = float(pick["y_total"] - ecr_pick["y_total"])
        out[f"pick_is_best_{name}"] = float(pick["y_total"] >= w["y_total"].max() - 1e-9)
        out[f"pick_ecr_rank_{name}"] = float(pick["ecr_rank"])
    return out


def regret_summary(per_snap: pd.DataFrame, window: str) -> dict[str, float]:
    r = per_snap[f"regret_{window}"].dropna().to_numpy()
    if len(r) == 0:
        return {}
    wrong = r[r > 1e-9]
    return {
        "n_decisions": float(len(r)),
        "mean_regret": float(r.mean()),
        "median_regret": float(np.median(r)),
        "p90_regret": float(np.quantile(r, 0.9)),
        "mean_regret_when_wrong": float(wrong.mean()) if len(wrong) else 0.0,
        "share_wrong": float(len(wrong) / len(r)),
        "share_large": float(np.mean(r >= LARGE_REGRET_PTS)),
    }


# ----------------------------------------------------------------------------------------
# probability calibration
# ----------------------------------------------------------------------------------------
class PairProb:
    """P(i outscores j) = sigmoid(b * dpred); no intercept (antisymmetry: swapping i and j must
    give 1-p). ``b`` is fitted by 1-D logistic regression on training pairs only."""

    def __init__(self) -> None:
        self.b_: float = 0.0

    def fit(self, dpred: np.ndarray, win: np.ndarray) -> PairProb:
        x = np.concatenate([dpred, -dpred])
        y = np.concatenate([win, 1 - win])
        b = 0.0
        for _ in range(60):  # Newton on the log-likelihood (concave); ridge 1e-6 for stability
            p = 1 / (1 + np.exp(-b * x))
            grad = np.sum((y - p) * x) - 1e-6 * b
            hess = -np.sum(p * (1 - p) * x**2) - 1e-6
            step = grad / hess
            b -= step
            if abs(step) < 1e-10:
                break
        self.b_ = float(b)
        return self

    def prob(self, dpred: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-self.b_ * dpred))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(p: np.ndarray, y: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(
    p: np.ndarray, y: np.ndarray, edges=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)
) -> pd.DataFrame:
    """Reliability on the folded probability max(p, 1-p) so each pair is counted once."""
    pf = np.where(p >= 0.5, p, 1 - p)
    yf = np.where(p >= 0.5, y, 1 - y)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (pf >= lo) & (pf < hi)
        rows.append(
            {
                "bin": f"{lo:.1f}-{min(hi, 1):.1f}",
                "n": int(m.sum()),
                "mean_pred": float(pf[m].mean()) if m.any() else np.nan,
                "observed": float(yf[m].mean()) if m.any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------
# season / snapshot block bootstrap
# ----------------------------------------------------------------------------------------
def _season_means(df: pd.DataFrame, cols: list[str]) -> dict[int, dict[int, np.ndarray]]:
    out: dict[int, dict[int, np.ndarray]] = {}
    for (s, w), g in df.groupby(["season", "snapshot_week"]):
        out.setdefault(int(s), {})[int(w)] = g[cols].to_numpy(dtype=float)[0]
    return out


def block_bootstrap(
    per_snap: pd.DataFrame, cols: list[str], n_boot: int = 4000, seed: int = 20260102
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Season-and-snapshot block bootstrap of the equal-weighted mean of per-snapshot values.

    Returns (point estimates, {col: bootstrap draws}). Draw: sample S seasons with replacement;
    within each sampled season sample its snapshots with replacement; average snapshots within
    season, then seasons. All columns share one resample, so differences between columns are
    properly paired. NaNs (e.g. an undefined metric in one snapshot) are ignored per column."""
    data = _season_means(per_snap, cols)
    seasons = sorted(data)
    rng = np.random.default_rng(seed)

    def one(sample_seasons, rng_inner):
        vals = []
        for s in sample_seasons:
            weeks = sorted(data[s])
            pick = rng_inner.choice(weeks, size=len(weeks), replace=True)
            arr = np.vstack([data[s][w] for w in pick])
            vals.append(np.nanmean(arr, axis=0))
        return np.nanmean(np.vstack(vals), axis=0)

    point = np.nanmean(
        np.vstack([np.nanmean(np.vstack(list(data[s].values())), axis=0) for s in seasons]), axis=0
    )
    draws = np.empty((n_boot, len(cols)))
    for b in range(n_boot):
        samp = rng.choice(seasons, size=len(seasons), replace=True)
        draws[b] = one(samp, rng)
    return point, {c: draws[:, k] for k, c in enumerate(cols)}


def ci(draws: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    a = (1 - level) / 2
    return float(np.nanquantile(draws, a)), float(np.nanquantile(draws, 1 - a))


def design_effect(per_snap: pd.DataFrame, col: str) -> dict[str, float]:
    """One-way ANOVA intraclass correlation of a per-snapshot metric across seasons, and the
    implied effective number of independent snapshots n_eff = n / (1 + (m-1) rho)."""
    g = per_snap.dropna(subset=[col]).groupby("season")[col]
    k, n = g.ngroups, int(g.size().sum())
    if k < 2 or n <= k:
        return {"n_snapshots": float(n), "n_seasons": float(k), "icc": np.nan, "n_eff": np.nan}
    m = n / k
    grand = per_snap[col].mean()
    msb = sum(len(v) * (v.mean() - grand) ** 2 for _, v in g) / (k - 1)
    msw = sum(((v - v.mean()) ** 2).sum() for _, v in g) / (n - k)
    rho = max((msb - msw) / (msb + (m - 1) * msw), 0.0) if (msb + (m - 1) * msw) > 0 else 0.0
    return {
        "n_snapshots": float(n),
        "n_seasons": float(k),
        "icc": float(rho),
        "n_eff": float(n / (1 + (m - 1) * rho)),
    }
