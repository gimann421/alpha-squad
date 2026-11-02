"""Live QB board and trade decision for the CURRENT week (D116).

Everything here is computed from data fetched at run time and stamped with its own timestamp; a
failed fetch raises (via the source adapters) instead of falling back to older numbers silently.
The models are the ones validated by ``ros.report`` and are fitted on every complete historical
season (2020-2025) -- never on the in-progress season.

What this module will and will not say
--------------------------------------
* ROS rank: the latest archived FantasyPros ``ros-qb`` consensus, with its scrape date and age.
* ROS point projection: FantasyPros' free API tier serves point projections for individual weeks
  to the top 10 players only (no pagination). Where a QB appears in every remaining week's list the
  weekly numbers are summed; otherwise the field is reported ``unavailable``. These projections
  have NO historical archive, so they are shown for reference and are not in any backtest.
* Playoff / championship probability: needs standings and the schedule. Without them the numbers
  are scenario values (``assumption_based=True``) and are labelled so.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import yaml

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.roster import positional_capacity
from alpha_squad.ros import noise as NZ
from alpha_squad.ros import rosterbench as RB
from alpha_squad.ros import skill
from alpha_squad.ros import snapshots as sn
from alpha_squad.ros import trade as T
from alpha_squad.ros.lineup import UNAVAILABLE, slot_plan
from alpha_squad.ros.models import add_derived, make_model
from alpha_squad.ros.scoring import ScoringRules

#: The model used for the live recommendation. Set from the walk-forward + roster-level results in
#: docs/ROS_QB_TRADE_MODEL.md; changing it requires a new evaluation, not a preference.
LIVE_MODEL = "D_usage"
MAX_ECR_AGE_DAYS = 8
FP_BASE = "https://api.fantasypros.com/public/v2/json/nfl"


@dataclass
class LiveData:
    today: date
    spec: sn.SnapshotSpec
    qb: pd.DataFrame  # live QB rows (features as of today, ECR as of spec.scrape_date)
    skill_players: pd.DataFrame
    skill_weekly: pd.DataFrame
    fut_weeks: dict[str, list[int]]
    train_panel: pd.DataFrame
    train_skill: pd.DataFrame
    train_stats: pd.DataFrame
    inputs: dict
    ids: pd.DataFrame


def _read_ids(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, na_values=["NA"])


def load_live(
    today: date | None = None,
    panel_dir: Path = Path("data/ros"),
    refresh: bool = True,
    settings=None,
) -> LiveData:
    from alpha_squad.config.settings import get_settings
    from alpha_squad.ros.ingest import ensure_inputs

    settings = settings or get_settings()
    today = today or datetime.now(UTC).date()
    season = today.year if today.month >= 3 else today.year - 1
    seasons = [season - 1, season]
    files = ensure_inputs(seasons, settings, refresh_season=season if refresh else None)
    paths = lambda ds: {s: f.path for s, f in files[ds].items()}  # noqa: E731
    ecr = sn.load_ecr_qb(files["ecr"].path)
    cand = sorted(
        d for d in set(ecr["scrape_date"]) if d <= today and d.year in (season, season + 1)
    )
    if not cand:
        raise RuntimeError("no archived ROS-QB scrape for the current season on or before today")
    sched = sn.load_schedule(files["schedule"].path)
    cur = sched[(sched.season == season)]
    played = cur[cur.pts_for.notna()]
    week = int(played["week"].max()) + 1 if len(played) else 1
    spec = sn.SnapshotSpec(season, week, cand[-1])
    pbp_player, pbp_team = sn.load_pbp_tables({season: paths("pbp")[season]})
    inp = sn.prepare_inputs(
        ecr=ecr,
        id_map=sn.load_id_map(files["player_ids"].path),
        schedule=sched,
        stats=sn.load_weekly_stats(paths("stats_player_week")),
        pbp_player=pbp_player,
        pbp_team=pbp_team,
        injuries=sn.load_injuries({season: paths("injuries")[season]}),
        rules=ScoringRules.nflverse_ppr(),
    )
    qb = sn.build_snapshot_rows(inp, spec, live_today=today)
    overall = skill.load_ecr_overall(files["ecr"].path)
    sp, sw = skill.build_skill_snapshot(inp, overall, spec, live_today=today)
    fut = cur[cur.pts_for.isna() & (cur.week <= sn.DEFAULT_HORIZON_WEEK)]
    fut_weeks = {t: sorted(g["week"].tolist()) for t, g in fut.groupby("team")}
    train = pd.read_parquet(panel_dir / "qb_ros_panel.parquet")
    train = train[train["target_complete"]]
    tsp = pd.read_parquet(panel_dir / "skill_players.parquet")
    # historical stats for the noise model (completed seasons only)
    from alpha_squad.ros.report import _load_stats_for_noise

    manifest = json.loads((panel_dir / "inputs_manifest.json").read_text())
    tst = _load_stats_for_noise(manifest)
    tst = tst[tst["season"] < season]
    return LiveData(
        today,
        spec,
        qb,
        sp,
        sw,
        fut_weeks,
        train,
        tsp,
        tst,
        {
            k: ({str(s): vars(f) for s, f in v.items()} if isinstance(v, dict) else vars(v))
            for k, v in files.items()
        },
        _read_ids(files["player_ids"].path),
    )


# ----------------------------------------------------------------------------------------
# forecasts
# ----------------------------------------------------------------------------------------
def load_kappa(panel_dir: Path = Path("data/ros")) -> tuple[float, str]:
    """Interval-widening factor from the backtest's Monte Carlo coverage check (see
    ``report.mc_validation``). Missing file -> 1.0 AND a visible warning string, never silence."""
    f = panel_dir / "mc_calibration.json"
    if not f.exists():
        return 1.0, "mc_calibration.json missing: simulation intervals are NOT coverage-calibrated"
    d = json.loads(f.read_text())
    return float(d["kappa"]), f"kappa={d['kappa']} ({d['rule']})"


def loso_tau(train: pd.DataFrame, model_name: str) -> float:
    """SD of out-of-sample points-per-game-played errors (leave-one-season-out)."""
    train = add_derived(train)
    res = []
    for s in sorted(train["season"].unique()):
        tr, te = train[train["season"] != s], train[(train["season"] == s) & (train["y_apps"] > 0)]
        if tr.empty or te.empty:
            continue
        m = make_model(model_name).fit(tr.reset_index(drop=True))
        te = te.reset_index(drop=True)
        rate = (
            m.predict_parts(te)[0]
            if hasattr(m, "predict_parts") and m.two_part
            else m.predict_rate(te)
        )
        res.append((te["y_total"] / te["y_apps"]).to_numpy() - rate)
    return float(np.std(np.concatenate(res)))


def forecast_qbs(
    data: LiveData, model_name: str = LIVE_MODEL, n_sims: int = 4000
) -> tuple[pd.DataFrame, dict]:
    train = add_derived(data.train_panel.reset_index(drop=True))
    live = add_derived(data.qb.copy()).reset_index(drop=True)
    names = ["A_ecr", "S2D", "C_recent", "D_usage", "E_full", model_name]
    preds = {}
    for n in dict.fromkeys(names):
        preds[n] = make_model(n).fit(train).predict_total(live)
    out = live[
        [
            "gsis_id",
            "fp_id",
            "player",
            "team",
            "ecr",
            "ecr_rank",
            "ecr_sd",
            "ecr_best",
            "ecr_worst",
            "ecr_age_days",
            "n_remaining",
            "apps",
            "games_missed",
            "ppg_app",
            "ppg_tg",
            "last3",
            "ppg_prev",
        ]
    ].copy()
    for n, p in preds.items():
        out[f"ros_{n}"] = p
    sel = make_model(model_name).fit(train)
    if getattr(sel, "two_part", False):
        rate, avail = sel.predict_parts(live)
    else:  # single-part model: split with the two-part availability model
        base = make_model("D_usage").fit(train)
        avail = base.predict_parts(live)[1]
        rate = sel.predict_rate(live) / np.clip(avail, 0.3, 1.0)
    kappa, kappa_note = load_kappa()
    tau = kappa * loso_tau(
        data.train_panel.reset_index(drop=True),
        "D_usage" if not getattr(sel, "two_part", False) else model_name,
    )
    out["pred_play"], out["pred_avail"] = rate, avail
    out["ros_selected"] = preds[model_name]
    noise = NZ.fit_noise_model(data.train_stats, data.train_skill)
    weeks = sorted({w for ws in data.fut_weeks.values() for w in ws})
    p10, p50, p90 = [], [], []
    for r in out.itertuples():
        ws = tuple(data.fut_weeks.get(r.team, []))
        a = T.Asset(
            r.gsis_id,
            r.player,
            "QB",
            f"t{r.gsis_id}",
            float(r.pred_play),
            tau,
            float(r.pred_avail),
            ws,
        )
        sim = T.simulate_assets([a], weeks, noise, n_sims, seed=5)[r.gsis_id]
        tot = np.where(sim > UNAVAILABLE / 2, sim, 0.0).sum(axis=0)
        (
            p10.append(np.quantile(tot, 0.1)),
            p50.append(np.quantile(tot, 0.5)),
            p90.append(np.quantile(tot, 0.9)),
        )
    out["ros_p10"], out["ros_p50"], out["ros_p90"] = p10, p50, p90
    return out, {
        "tau_play": tau,
        "noise": noise,
        "model": model_name,
        "weeks": weeks,
        "kappa_note": kappa_note,
    }


def fp_live_projections(weeks: list[int], settings=None) -> dict:
    """FantasyPros free-tier weekly QB projections and ROS consensus (top 10 only), timestamped."""
    from alpha_squad.config.settings import get_settings

    settings = settings or get_settings()
    key = settings.fantasypros_api_key or os.environ.get("FANTASYPROS_API_KEY")
    if not key:
        return {"available": False, "reason": "FANTASYPROS_API_KEY not configured"}
    H = {"x-api-key": key}
    season = date.today().year
    out: dict = {
        "available": True,
        "fetched_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "weekly": {},
        "tier_note": "free tier returns the top 10 players per request; no pagination",
    }
    import time

    def get(path: str, params: dict):
        for attempt in range(
            4
        ):  # the free tier rate-limits bursts (HTTP 429): back off, then give up
            r = httpx.get(f"{FP_BASE}/{season}/{path}", params=params, headers=H, timeout=30)
            if r.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"rate-limited (429) after retries: {path} {params}")

    failed: list[int] = []
    try:
        for w in weeks:
            try:
                out["weekly"][w] = {
                    p["fpid"]: float(p["stats"]["points"])
                    for p in get("projections", {"position": "QB", "week": w}).get("players", [])
                }
            except Exception:  # noqa: BLE001 - recorded in `failed_weeks`, never papered over
                failed.append(w)
            time.sleep(0.4)
        b = get("consensus-rankings", {"position": "QB", "type": "ROS"})
        out["ros_top10"] = {p["player_id"]: p["rank_ecr"] for p in b.get("players", [])}
        out["ros_last_updated_ts"] = b.get("last_updated_ts")
    except Exception as e:  # noqa: BLE001 - reported, never silently substituted
        return {"available": False, "reason": f"live fetch failed: {e!r}"}
    out["failed_weeks"] = failed
    return out


def attach_fp(board: pd.DataFrame, fp: dict, fut_weeks: dict[str, list[int]]) -> pd.DataFrame:
    b = board.copy()
    if not fp.get("available"):
        b["fp_ros_proj"] = np.nan
        b["fp_ros_note"] = fp.get("reason", "unavailable")
        return b
    proj, note = [], []
    for r in b.itertuples():
        ws = fut_weeks.get(r.team, [])
        vals = [fp["weekly"].get(w, {}).get(int(r.fp_id)) for w in ws]
        if ws and all(v is not None for v in vals):
            proj.append(float(sum(vals)))
            note.append("sum of FP weekly projections")
        else:
            proj.append(np.nan)
            note.append("unavailable: outside FP's free-tier top-10 for some remaining week")
    b["fp_ros_proj"], b["fp_ros_note"] = proj, note
    return b


# ----------------------------------------------------------------------------------------
# trade evaluation for a concrete roster
# ----------------------------------------------------------------------------------------
def skill_assets(data: LiveData, noise: dict) -> dict[str, T.Asset]:
    """RB/WR/TE (and board QB) assets valued by the consensus-rank curve fitted on past seasons."""
    maps = RB.fit_skill_maps(data.train_skill)
    sp = data.skill_players.copy()
    avail = {p: v["mean"] for p, v in noise["availability"].items()}
    out: dict[str, T.Asset] = {}
    for pos in RB.SKILL:
        d = RB._skill_frame(sp[sp["position"] == pos]).reset_index(drop=True)
        if d.empty:
            continue
        rate = maps[pos].predict_rate(d)
        resid_sd = float(
            np.sqrt(
                np.mean(
                    (
                        data.train_skill.loc[
                            data.train_skill["position"] == pos, "y_rate"
                        ].to_numpy()
                        - maps[pos].predict_rate(
                            RB._skill_frame(
                                data.train_skill[data.train_skill["position"] == pos]
                            ).reset_index(drop=True)
                        )
                    )
                    ** 2
                )
            )
        )
        for r, v in zip(d.itertuples(), rate, strict=True):
            av = float(avail.get(pos, 0.85))
            out[r.gsis_id] = T.Asset(
                r.gsis_id,
                r.player,
                pos,
                r.team,
                float(v) / av,
                resid_sd / av,
                av,
                tuple(data.fut_weeks.get(r.team, [])),
                {"overall_ecr": r.overall_ecr, "pos_rank": r.pos_rank},
            )
    return out


def qb_assets(board: pd.DataFrame, data: LiveData, tau: float) -> dict[str, T.Asset]:
    return {
        r.gsis_id: T.Asset(
            r.gsis_id,
            r.player,
            "QB",
            r.team,
            float(r.pred_play),
            tau,
            float(r.pred_avail),
            tuple(data.fut_weeks.get(r.team, [])),
            {"ecr_rank": r.ecr_rank, "ecr_age_days": r.ecr_age_days},
        )
        for r in board.itertuples()
    }


def waiver_levels(
    league: LeagueContext, board: pd.DataFrame, skill_a: dict[str, T.Asset], tau: float
) -> dict[str, tuple]:
    """Waiver-wire level per position: the first player beyond what a full league rosters
    (``teams * positional_capacity``), valued by the same forecasts."""
    levels = {}
    qb_rank = min(league.teams * positional_capacity(league, "QB") + 1, len(board))
    q = board.sort_values("ecr_rank").iloc[qb_rank - 1]
    levels["QB"] = (float(q.pred_play), tau, float(q.pred_avail))
    for pos in ("RB", "WR", "TE"):
        cands = sorted(
            (a for a in skill_a.values() if a.position == pos), key=lambda a: a.notes["pos_rank"]
        )
        if not cands:
            continue
        k = min(league.teams * positional_capacity(league, pos), len(cands)) - 1
        a = cands[k]
        levels[pos] = (a.mu_game, a.mu_sd, a.avail)
    return levels


@dataclass
class TradeInput:
    roster: list[str]
    targets: list[str]
    give_packages: list[list[str]]
    waiver_qbs: list[str] | None = None
    scenario: T.LeagueScenario | None = None


def load_trade_yaml(path: Path) -> tuple[LeagueContext, TradeInput]:
    cfg = yaml.safe_load(Path(path).read_text())
    league = (
        load_league_context(cfg["league"])
        if cfg.get("league") and Path(cfg["league"]).exists()
        else load_league_context()
    )
    if isinstance(cfg.get("league"), dict):
        league = LeagueContext.model_validate(cfg["league"])
    scen = None
    if cfg.get("standings") or cfg.get("playoffs"):
        s = {**(cfg.get("standings") or {}), **(cfg.get("playoffs") or {})}
        scen = T.LeagueScenario(
            teams=league.teams,
            **{k: (tuple(v) if isinstance(v, list) else v) for k, v in s.items()},
        )
    return league, TradeInput(
        roster=[str(x) for x in cfg["roster"]],
        targets=[str(x) for x in cfg.get("targets", [])],
        give_packages=[[str(g) for g in pkg] for pkg in cfg.get("give", [])],
        waiver_qbs=[str(x) for x in cfg["waiver_qbs"]] if cfg.get("waiver_qbs") else None,
        scenario=scen,
    )


def evaluate_candidates(
    league: LeagueContext,
    data: LiveData,
    board: pd.DataFrame,
    cal: dict,
    ti: TradeInput,
    n_sims: int = 4000,
    seed: int = 7,
) -> tuple[pd.DataFrame, dict]:
    noise, tau = cal["noise"], cal["tau_play"]
    plan = slot_plan(RB.lineup_league(league))
    sk = skill_assets(data, noise)
    qa = qb_assets(board, data, tau)
    pool = {**sk, **qa}
    unknown = [p for p in ti.roster if p not in pool]
    roster = [pool[p] for p in ti.roster if p in pool]
    wl = waiver_levels(league, board, sk, tau)
    all_weeks = cal["weeks"]
    waiver = T.waiver_assets(league, wl, tuple(all_weeks))
    if ti.waiver_qbs:  # explicit actual free-agent QBs replace the generic QB waiver body
        waiver = [w for w in waiver if w.position != "QB"] + [
            qa[p] for p in ti.waiver_qbs if p in qa
        ]
    opp_mean = None
    rows = []
    cache: dict = {}
    for tgt in ti.targets:
        if tgt not in qa:
            rows.append(
                {
                    "target": tgt,
                    "label": "Insufficient evidence",
                    "note": "target QB not on the current ROS-QB board",
                }
            )
            continue
        packages = ti.give_packages or [[]]
        for pkg in packages:
            if any(g not in {a.pid for a in roster} for g in pkg):
                rows.append(
                    {
                        "target": qa[tgt].name,
                        "give": pkg,
                        "label": "Insufficient evidence",
                        "note": "a proposed outgoing player is not on the supplied roster or is unprojectable",
                    }
                )
                continue
            get = [qa[tgt]]
            base = T.evaluate_trade(
                league,
                roster,
                pkg,
                get,
                waiver,
                noise,
                n_sims=n_sims,
                seed=seed,
                plan=plan,
                sim_cache=cache,
            )
            s = base.summary()
            sens = {
                "injury risk x1.5": T.evaluate_trade(
                    league,
                    roster,
                    pkg,
                    get,
                    waiver,
                    noise,
                    n_sims=n_sims,
                    seed=seed,
                    plan=plan,
                    injury_multiplier=1.5,
                    sim_cache=cache,
                ).summary(),
                "target forecast -1 tau": T.evaluate_trade(
                    league,
                    roster,
                    pkg,
                    [_shift(qa[tgt], -tau)],
                    waiver,
                    noise,
                    n_sims=n_sims,
                    seed=seed,
                    plan=plan,
                    sim_cache=cache,
                ).summary(),
                "target forecast +1 tau (optimistic)": T.evaluate_trade(
                    league,
                    roster,
                    pkg,
                    [_shift(qa[tgt], tau)],
                    waiver,
                    noise,
                    n_sims=n_sims,
                    seed=seed,
                    plan=plan,
                    sim_cache=cache,
                ).summary(),
            }
            r_ = board[board.gsis_id == tgt].iloc[0]
            ok = (r_.ecr_age_days <= MAX_ECR_AGE_DAYS) and r_.n_remaining > 0
            label, notes = T.classify(
                s, {k: v for k, v in sens.items() if "optimistic" not in k}, evidence_ok=bool(ok)
            )
            # max acceptable cost: lineup points the manager can afford to give up
            acq = T.evaluate_trade(
                league,
                roster,
                [],
                get,
                waiver,
                noise,
                n_sims=n_sims,
                seed=seed,
                plan=plan,
                sim_cache=cache,
            )
            sa = acq.summary()
            rec = {
                "target": qa[tgt].name,
                "target_id": tgt,
                "give": [pool[g].name for g in pkg],
                "ecr_rank": int(r_.ecr_rank),
                "ecr_scrape": str(data.spec.scrape_date),
                "ecr_age_days": int(r_.ecr_age_days),
                "model_ros_points": float(r_.ros_selected),
                "model_p10": float(r_.ros_p10),
                "model_p90": float(r_.ros_p90),
                "fp_ros_proj": r_.get("fp_ros_proj", np.nan),
                "net_value_mean": s["mean"],
                "net_value_median": s["median"],
                "net_p05": s["p05"],
                "net_p95": s["p95"],
                "prob_improves": s["prob_improves"],
                "acquire_only_mean": sa["mean"],
                "max_cost_breakeven": max(sa["mean"], 0.0),
                "max_cost_conservative": max(sa["p25"], 0.0),
                "sens": {k: round(v["mean"], 1) for k, v in sens.items()},
                "label": label,
                "notes": notes,
            }
            if ti.scenario is not None:
                if opp_mean is None:
                    opp_mean = ti.scenario.opp_weekly_mean or float(
                        base.before.sum(axis=0).mean() / max(len(base.weeks), 1)
                    )
                rec.update(T.playoff_deltas(base, ti.scenario, opp_mean))
            rows.append(rec)
    return pd.DataFrame(rows), {"unprojectable_roster_ids": unknown, "waiver_levels": wl}


def _shift(a: T.Asset, delta: float) -> T.Asset:
    from dataclasses import replace

    return replace(a, mu_game=max(a.mu_game + delta, 1.0))
