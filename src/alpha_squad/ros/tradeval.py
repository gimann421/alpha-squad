"""Does the Monte Carlo trade engine's P(trade improves the lineup) mean what it says? (D116)

For every trade the D_usage model would have EXECUTED in the roster-level backtest, rebuild the
decision with the production Monte Carlo engine (``ros.trade.evaluate_trade``) using only
information available at the snapshot -- forecasts from models fitted on earlier seasons, a noise
model fitted on earlier seasons, interval width from the backtest's own coverage calibration --
then compare its stated distribution of the lineup gain with what the lineup actually gained.

Reported: calibration of P(gain > 0), coverage of the central 50/80% intervals of the gain,
and the mean stated gain vs mean realized gain. Nothing here is tuned on these outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from alpha_squad.league.context import LeagueContext
from alpha_squad.ros import metrics as M
from alpha_squad.ros import noise as NZ
from alpha_squad.ros import rosterbench as RB
from alpha_squad.ros import trade as T
from alpha_squad.ros.models import add_derived, make_model


def _qb_parts(panel: pd.DataFrame, season: int, week: int):
    df = add_derived(panel[panel["target_complete"]].reset_index(drop=True))
    train = df[df["season"] < season].reset_index(drop=True)
    test = df[(df["season"] == season) & (df["snapshot_week"] == week)].reset_index(drop=True)
    m = make_model("D_usage").fit(train)
    rate, avail = m.predict_parts(test)
    res = []
    for s in sorted(train["season"].unique()):
        tr, te = train[train["season"] != s], train[(train["season"] == s) & (train["y_apps"] > 0)]
        if tr.empty or te.empty:
            continue
        mi = make_model("D_usage").fit(tr.reset_index(drop=True))
        res.append(
            (te["y_total"] / te["y_apps"]).to_numpy()
            - mi.predict_parts(te.reset_index(drop=True))[0]
        )
    tau = float(np.std(np.concatenate(res)))
    return dict(zip(test["gsis_id"], zip(rate, avail, strict=True), strict=True)), tau


def validate_trade_simulation(
    panel: pd.DataFrame,
    skill_players: pd.DataFrame,
    skill_weekly: pd.DataFrame,
    qb_preds: pd.DataFrame,
    decisions: pd.DataFrame,
    stats: pd.DataFrame,
    league: LeagueContext,
    models: list[str],
    kappa: float = 1.0,
    n_sims: int = 1000,
    model: str = "D_usage",
) -> pd.DataFrame:
    """One row per executed trade: simulated P(gain>0), mean/p10/p90 of gain, realized gain."""
    ex = decisions[(decisions["model"] == model) & (decisions["pred_delta"] > 0)]
    rows = []
    noise_cache: dict[int, dict] = {}
    for snap in RB.iter_snapshots(skill_players, skill_weekly, qb_preds, league, models):
        T_, wk, world = snap["season"], snap["week"], snap["world"]
        sel = ex[(ex["season"] == T_) & (ex["snapshot_week"] == wk)]
        if sel.empty:
            continue
        if T_ not in noise_cache:
            noise_cache[T_] = NZ.fit_noise_model(
                stats[stats["season"] < T_], skill_players[skill_players["season"] < T_]
            )
        noise = noise_cache[T_]
        parts, tau = _qb_parts(panel, T_, wk)
        av = {p: v["mean"] for p, v in noise["availability"].items()}
        train_sp = skill_players[skill_players["season"] < T_]
        resid = {}
        for pos in RB.SKILL:
            d = RB._skill_frame(train_sp[train_sp["position"] == pos]).reset_index(drop=True)
            resid[pos] = float(
                np.sqrt(np.mean((d["y_rate"].to_numpy() - snap["maps"][pos].predict_rate(d)) ** 2))
            )
        weeks_of = {
            g: tuple(world.weeks[i] for i in np.where(world.sched[g])[0]) for g in world.sched
        }

        def asset(
            g, _w=world, _parts=parts, _tau=tau, _av=av, _resid=resid, _weeks=weeks_of, _k=kappa
        ):
            pos = _w.positions[g]
            if pos == "QB":
                rate, avail = _parts[g]
                return T.Asset(
                    g,
                    _w.names[g],
                    "QB",
                    _w.team[g],
                    float(rate),
                    _tau * _k,
                    float(avail),
                    _weeks[g],
                )
            a = _av.get(pos, 0.85)
            return T.Asset(
                g,
                _w.names[g],
                pos,
                _w.team[g],
                float(_w.skill_rate[g]) / a,
                _resid[pos] * _k / a,
                a,
                _weeks[g],
            )

        rates = dict(world.skill_rate)
        rates.update({g: v for g, v in snap["qb_rates"][model].items() if g in world.positions})
        drafted = {p for r in snap["rosters"].values() for p in r}
        undrafted = [g for g in world.positions if g not in drafted]
        wv_ids = RB._waiver_ids(world, rates, undrafted, snap["league"])
        waiver = [asset(g) for g in wv_ids if g in parts or world.positions[g] != "QB"]
        for r in sel.itertuples():
            roster = [
                asset(g)
                for g in snap["rosters"][r.team]
                if world.positions[g] != "QB" or g in parts
            ]
            if r.give not in {a.pid for a in roster} or r.get not in parts:
                continue
            sim = T.evaluate_trade(
                snap["league"],
                roster,
                [r.give],
                [asset(r.get)],
                waiver,
                noise,
                n_sims=n_sims,
                seed=7,
                plan=snap["plan"],
            )
            d = sim.delta
            rows.append(
                dict(
                    season=T_,
                    snapshot_week=wk,
                    team=r.team,
                    p_improve=float(np.mean(d > 0)),
                    mean=float(d.mean()),
                    p10=float(np.quantile(d, 0.1)),
                    p90=float(np.quantile(d, 0.9)),
                    p25=float(np.quantile(d, 0.25)),
                    p75=float(np.quantile(d, 0.75)),
                    realized=float(r.real_if_exec),
                    det_pred=float(r.pred_delta),
                )
            )
    return pd.DataFrame(rows)


def summarize_trade_validation(v: pd.DataFrame) -> dict:
    if v.empty:
        return {}
    y = (v["realized"] > 0).astype(float).to_numpy()
    p = v["p_improve"].to_numpy()
    edges = (0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001)
    rel = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi)
        rel.append(
            {
                "P(improves) bin": f"{lo:.1f}-{min(hi, 1):.1f}",
                "n": int(m.sum()),
                "mean stated": float(p[m].mean()) if m.any() else np.nan,
                "observed share improved": float(y[m].mean()) if m.any() else np.nan,
            }
        )
    return {
        "n_trades": int(len(v)),
        "brier": M.brier(p, y),
        "brier_always_base_rate": M.brier(np.full_like(p, y.mean()), y),
        "mean_stated_gain": float(v["mean"].mean()),
        "mean_realized_gain": float(v["realized"].mean()),
        "cov50": float(((v.realized >= v.p25) & (v.realized <= v.p75)).mean()),
        "cov80": float(((v.realized >= v.p10) & (v.realized <= v.p90)).mean()),
        "observed_improved": float(y.mean()),
        "mean_stated_p_improve": float(p.mean()),
        "reliability": pd.DataFrame(rel),
        "by_season": v.groupby("season")
        .agg(n=("realized", "size"), stated=("mean", "mean"), realized=("realized", "mean"))
        .reset_index(),
    }
