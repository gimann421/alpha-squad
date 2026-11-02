"""Empirical noise model for the Monte Carlo trade engine -- every number estimated from data.

Three ingredients, all estimated from nflverse weekly stat lines (2020 onward) and the ROS panels,
none hand-picked:

* weekly score dispersion: for each position, ``sd = a + b * mean`` fitted across player-seasons
  with at least 8 appearances.
* same-team correlation: the correlation of weekly residuals (points minus the player's own
  season mean) between a team's QB (the game's leading passer) and its RB/WR/TE. Used as a
  one-factor loading so players on the same team share the same game-environment shock.
* availability shocks: the empirical distribution of the *fraction of remaining scheduled games
  missed* among players who missed any, measured on the ROS panels. A simulated injury draws its
  missed fraction from this empirical distribution rather than from an assumed duration law.

``fit_noise_model`` is deterministic given its inputs and is written next to the panel with its
sample sizes so a reader can see how much data stands behind each number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

POSITIONS = ("QB", "RB", "WR", "TE")


def _played(stats: pd.DataFrame) -> pd.Series:
    """Took part in the offense: any pass attempt, carry or target. (`snapshots.prepare_inputs`'s
    `appeared` flag counts attempts + carries only, which is right for QBs and wrong for WR/TE.)"""
    cols = [c for c in ("attempts", "carries", "targets") if c in stats.columns]
    return stats[cols].fillna(0).sum(axis=1) > 0


def fit_weekly_sd(stats: pd.DataFrame, min_apps: int = 8) -> dict[str, dict[str, float]]:
    st = stats[_played(stats) & stats["position"].isin(POSITIONS)]
    g = (
        st.groupby(["player_id", "season", "position"])["pts"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    g = g[(g["count"] >= min_apps) & g["std"].notna()]
    out: dict[str, dict[str, float]] = {}
    for pos in POSITIONS:
        d = g[g["position"] == pos]
        if len(d) < 20:
            continue
        b, a = np.polyfit(d["mean"].to_numpy(), d["std"].to_numpy(), 1)
        resid = d["std"].to_numpy() - (a + b * d["mean"].to_numpy())
        out[pos] = {
            "a": float(a),
            "b": float(b),
            "n_player_seasons": float(len(d)),
            "resid_sd": float(resid.std()),
        }
    return out


def fit_team_correlation(stats: pd.DataFrame) -> dict[str, dict[str, float]]:
    """corr(QB residual, teammate residual) for teammates at RB/WR/TE, same game."""
    st = stats[_played(stats) & stats["position"].isin(POSITIONS)].copy()
    st["resid"] = st["pts"] - st.groupby(["player_id", "season"])["pts"].transform("mean")
    qb = st[st["position"] == "QB"].copy()
    # the game's QB = the leading passer of the team that week
    qb = qb.sort_values("attempts", ascending=False).drop_duplicates(["season", "week", "team"])
    qb = qb[["season", "week", "team", "resid"]].rename(columns={"resid": "qb_resid"})
    out: dict[str, dict[str, float]] = {}
    for pos in ("WR", "TE", "RB"):
        m = st[st["position"] == pos].merge(qb, on=["season", "week", "team"])
        m = m[(m["targets"].fillna(0) + m["carries"].fillna(0)) >= 3]
        if len(m) < 100:
            continue
        out[pos] = {
            "rho": float(np.corrcoef(m["qb_resid"], m["resid"])[0, 1]),
            "n_pairs": float(len(m)),
        }
    return out


def missed_fraction_sample(players: pd.DataFrame) -> np.ndarray:
    """Empirical (n_remaining - y_apps) / n_remaining among rows that missed >= 1 game."""
    d = players[(players["n_remaining"] > 0) & (players["y_apps"] < players["n_remaining"])]
    return ((d["n_remaining"] - d["y_apps"]) / d["n_remaining"]).to_numpy()


def availability_by_position(players: pd.DataFrame) -> dict[str, dict[str, float]]:
    out = {}
    for pos, g in players[players["n_remaining"] > 0].groupby("position"):
        frac = g["y_apps"] / g["n_remaining"]
        out[pos] = {
            "mean": float(frac.mean()),
            "p_any_miss": float((frac < 1).mean()),
            "n": float(len(g)),
        }
    return out


def fit_noise_model(stats: pd.DataFrame, skill_players: pd.DataFrame) -> dict:
    sd = fit_weekly_sd(stats)
    corr = fit_team_correlation(stats)
    missed = missed_fraction_sample(skill_players)
    return {
        "weekly_sd": sd,
        "team_corr": corr,
        "availability": availability_by_position(skill_players),
        "missed_fraction_quantiles": {
            str(q): float(np.quantile(missed, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        }
        if len(missed)
        else {},
        "missed_fraction_sample": [float(x) for x in np.round(missed, 4)],
        "n_missed_rows": int(len(missed)),
    }


def weekly_sd(model: dict, position: str, mean: float) -> float:
    p = model["weekly_sd"][position]
    return max(p["a"] + p["b"] * mean, 1.0)


def team_loadings(model: dict) -> dict[str, float]:
    """One-factor loadings reproducing the estimated QB-teammate correlations.

    corr(QB, X) = l_QB * l_X. The QB loading is set from the QB-WR correlation; the other
    positions' loadings follow. Negative estimated correlations are floored at 0 (no negative
    loadings), and the implied WR-WR correlation is reported by the caller as a known
    overstatement."""
    c = model["team_corr"]
    rho_wr = max(c.get("WR", {}).get("rho", 0.0), 0.0)
    l_qb = float(np.sqrt(rho_wr)) if rho_wr > 0 else 0.0
    out = {"QB": l_qb, "WR": l_qb}
    for pos in ("TE", "RB"):
        r = max(c.get(pos, {}).get("rho", 0.0), 0.0)
        out[pos] = float(min(r / l_qb, 0.95)) if l_qb > 0 else 0.0
    return out
