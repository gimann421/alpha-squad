"""Roster-level decision backtest -- the "market-priced QB swap" experiment (Model F).

Question answered: *if a manager used forecasting model M to decide whether to swap one of his
players for another team's quarterback, at ordinary market prices, did his realized lineup get
better?* This is the closest thing to "expected roster-level decision utility" the available
data supports, and it is the primary model-selection criterion.

Design (fixed before results were inspected)
--------------------------------------------
* Leagues are SYNTHETIC but reproducible: for every evaluation snapshot, ten teams snake-draft the
  archived ``ros-ppr-overall`` consensus board (QB/RB/WR/TE only, 14 rounds, roster-aware via the
  repo's own ``league.opportunity_cost.roster_aware_market_pick``). No real league's rosters or
  trade logs exist in this environment (``evaluation/trade_evaluation.py``), so none are claimed.
* The lineup is the target league's with K and DEF removed (no scored K/DST history here; a QB
  trade does not touch them).
* A candidate trade is one-for-one: the manager gives any player ``A`` and receives any quarterback
  ``T`` rostered by another team, provided the market would accept: ``overall_rank(A) <=
  overall_rank(T)`` (the manager gives up at least as much consensus value as he gets). Under the
  consensus' own valuation such a trade is never an upgrade; any positive predicted value must
  come from the model knowing something the board does not -- or from roster construction
  (a bench asset costs nothing in lineup points; a starter does).
* Model ``M`` values the incoming QB, the manager's own QBs and every free-agent QB with its own
  ROS forecasts; every other player (and every free agent at other positions) is valued with the
  same position-specific consensus-rank curve for all models, fitted on earlier seasons only. So
  the QB model is the only thing that varies. (Known limitation: the outgoing asset is valued at
  market, which is how most managers value what they give up.)
* Predicted value = expected best-lineup points over the remaining schedule (byes respected, free
  agents available to fill any hole, weekly re-optimized) after minus before. ``M`` executes the
  single best candidate if its predicted value exceeds ``threshold`` and otherwise holds.
* Realized value = the same quantity on the weekly points that actually happened (a player who
  did not play cannot start). Holds score 0. The headline ("forecast lineups") picks each week's
  starters by the model's own forecasts among players who played, then scores what they scored --
  the decision a manager can make. The hindsight-lineup variant (starters picked knowing the
  week's scores) is also stored; it flatters depth and is reported as a sensitivity only.
* ``oracle`` = best candidate in hindsight (diagnostic, not attainable).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.roster import positional_capacity, startable_slots, unfilled_dedicated_slots
from alpha_squad.ros.lineup import UNAVAILABLE, SlotPlan, best_lineup_value, slot_plan
from alpha_squad.ros.models import RidgeModel

SKILL = ("RB", "WR", "TE")
N_ROUNDS = 14


def lineup_league(league: LeagueContext) -> LeagueContext:
    """The target league minus K/DEF slots, with a consistent roster size."""
    lineup = {k: v for k, v in league.lineup.items() if k not in ("K", "DEF", "DST", "PK")}
    starters = sum(lineup.values())
    roster = dict(league.roster)
    roster["bench"] = N_ROUNDS - starters
    roster["roster_size"] = N_ROUNDS
    return league.model_copy(update={"lineup": lineup, "roster": roster})


def _skill_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["ecr"] = d["overall_ecr"]
    d["log_ecr"] = np.log(d["ecr"])
    return d


def fit_skill_maps(train: pd.DataFrame) -> dict[str, RidgeModel]:
    maps = {}
    for pos in SKILL:
        d = _skill_frame(train[train["position"] == pos]).reset_index(drop=True)
        maps[pos] = RidgeModel(f"skill_{pos}", ["log_ecr", "ecr"], two_part=False).fit(d)
    return maps


def snake_draft(
    league: LeagueContext, board: pd.DataFrame, n_teams: int = 10, rounds: int = N_ROUNDS
) -> dict[int, list[str]]:
    """Roster-aware snake draft of ``board`` (ranked by ``overall_rank``) using the repo's
    consensus drafter. Deterministic."""
    market = {r.gsis_id: (r.position, float(r.overall_rank)) for r in board.itertuples()}
    positions = {r.gsis_id: r.position for r in board.itertuples()}
    available = set(board["gsis_id"])
    rosters: dict[int, list[str]] = {t: [] for t in range(n_teams)}
    league_one = league.model_copy(update={"teams": n_teams})
    # positional ceilings derived from the lineup (league/roster.py), so no roster hoards a
    # position it could never start -- a 1-QB roster carries at most two QBs
    caps = {pos: positional_capacity(league, pos) for pos in ("QB", "RB", "WR", "TE")}
    for rd in range(rounds):
        order = range(n_teams) if rd % 2 == 0 else range(n_teams - 1, -1, -1)
        for t in order:
            have = [positions[p] for p in rosters[t]]
            allowed = {
                p for p in available if have.count(positions[p]) < caps[positions[p]]
            } or available
            pick = roster_aware_market_pick(
                allowed,
                market,
                positions,
                league_one,
                have,
                rounds - rd,
            )
            rosters[t].append(pick)
            available.discard(pick)
    for t, roster in rosters.items():  # never evaluate an illegal roster silently
        short = unfilled_dedicated_slots(league, [positions[p] for p in roster])
        if short:
            raise ValueError(
                f"draft left team {t} unable to fill {short}; the board is too shallow"
            )
    return rosters


@dataclass
class SnapshotWorld:
    season: int
    week: int
    weeks: list[int]
    positions: dict[str, str]
    overall_rank: dict[str, float]
    team: dict[str, str]
    real: dict[str, np.ndarray]  # realized weekly points, UNAVAILABLE if did not play / bye
    sched: dict[str, np.ndarray]  # bool mask: scheduled this week (bye-aware)
    skill_rate: dict[str, float]  # consensus-curve rate for RB/WR/TE (same for every model)
    names: dict[str, str]


def build_world(
    players: pd.DataFrame, weekly: pd.DataFrame, maps: dict[str, RidgeModel], season: int, week: int
) -> SnapshotWorld:
    p = players[(players["season"] == season) & (players["snapshot_week"] == week)].reset_index(
        drop=True
    )
    w = weekly[(weekly["season"] == season) & (weekly["snapshot_week"] == week)]
    weeks = sorted(w["nfl_week"].unique().tolist())
    widx = {x: i for i, x in enumerate(weeks)}
    real = {g: np.full(len(weeks), UNAVAILABLE) for g in p["gsis_id"]}
    sched = {g: np.zeros(len(weeks), dtype=bool) for g in p["gsis_id"]}
    for r in w.itertuples(index=False):
        sched[r.gsis_id][widx[r.nfl_week]] = True
        if r.played:
            real[r.gsis_id][widx[r.nfl_week]] = r.pts
    skill_rate: dict[str, float] = {}
    for pos in SKILL:
        d = _skill_frame(p[p["position"] == pos]).reset_index(drop=True)
        if len(d):
            for g, v in zip(d["gsis_id"], maps[pos].predict_rate(d), strict=True):
                skill_rate[g] = float(v)
    return SnapshotWorld(
        season,
        week,
        weeks,
        dict(zip(p["gsis_id"], p["position"], strict=True)),
        dict(zip(p["gsis_id"], p["overall_rank"].astype(float), strict=True)),
        dict(zip(p["gsis_id"], p["team"], strict=True)),
        real,
        sched,
        skill_rate,
        dict(zip(p["gsis_id"], p["player"], strict=True)),
    )


def _expected_arrays(world: SnapshotWorld, rates: dict[str, float], ids) -> dict[str, np.ndarray]:
    out = {}
    for g in ids:
        a = np.where(world.sched[g], rates[g], UNAVAILABLE)
        out[g] = a
    return out


def _total(
    plan: SlotPlan,
    arrays: dict[str, np.ndarray],
    positions: dict[str, str],
    scores: dict[str, np.ndarray] | None = None,
) -> float:
    return float(best_lineup_value(plan, arrays, positions, scores=scores).sum())


def _waiver_ids(
    world: SnapshotWorld, rates: dict[str, float], undrafted: list[str], league: LeagueContext
) -> list[str]:
    """Best undrafted players per position BY THIS MODEL'S forecasts: what a manager using the
    model would actually pick up, never the hindsight-best free agent."""
    startable = startable_slots(league)
    out = []
    for pos, n in startable.items():
        cands = [g for g in undrafted if world.positions[g] == pos and g in rates]
        cands.sort(key=lambda g: -rates[g])
        out.extend(cands[: n + 1])
    return out


def run_snapshot(
    world: SnapshotWorld,
    rosters: dict[int, list[str]],
    qb_rates: dict[str, dict[str, float]],  # model -> gsis -> pred_rate (QBs only)
    league: LeagueContext,
    plan: SlotPlan,
    threshold: float = 0.0,
    baseline_model: str = "A_ecr",
) -> list[dict]:
    drafted = {p for r in rosters.values() for p in r}
    undrafted = [g for g in world.positions if g not in drafted]
    pos = world.positions
    rows: list[dict] = []

    def rates_for(model: str) -> dict[str, float]:
        r = dict(world.skill_rate)
        r.update({g: v for g, v in qb_rates[model].items() if g in world.positions})
        return r

    models = list(qb_rates)
    rate_cache = {m: rates_for(m) for m in models}
    waiver_cache = {m: _waiver_ids(world, rate_cache[m], undrafted, league) for m in models}
    realized_cache: dict[tuple, float] = {}
    forecast_cache: dict[tuple, float] = {}

    def realized(ids: list[str]) -> float:
        """HINDSIGHT lineups: starters picked knowing each week's actual scores (optimistic)."""
        key = tuple(sorted(ids))
        if key not in realized_cache:
            realized_cache[key] = _total(plan, {g: world.real[g] for g in ids}, pos)
        return realized_cache[key]

    def realized_forecast(ids: list[str], model: str) -> float:
        """FORECAST lineups: starters picked by the model's own forecasts among players who
        actually played that week, then scored with what they actually scored."""
        key = (model, tuple(sorted(ids)))
        if key not in forecast_cache:
            r = rate_cache[model]
            keys = {
                g: np.where(world.real[g] > UNAVAILABLE / 2, r.get(g, 0.0), UNAVAILABLE)
                for g in ids
            }
            forecast_cache[key] = _total(plan, keys, pos, scores={g: world.real[g] for g in ids})
        return forecast_cache[key]

    for team, roster in rosters.items():
        my_qbs = [g for g in roster if pos[g] == "QB"]
        targets = [g for t2, r2 in rosters.items() if t2 != team for g in r2 if pos[g] == "QB"]
        cands = [
            (a, t)
            for a in roster
            for t in targets
            if world.overall_rank[a] <= world.overall_rank[t]
        ]
        if not cands:
            continue
        # hindsight-best candidate (diagnostic), with the baseline model's waiver set
        wb = waiver_cache[baseline_model]
        base_real = realized([*roster, *wb])
        deltas = {
            c: realized([g for g in roster if g != c[0]] + [c[1]] + wb) - base_real for c in cands
        }
        oracle = max(deltas.values())
        for m in models:
            r = rate_cache[m]
            wv = waiver_cache[m]
            base_pred = _total(plan, _expected_arrays(world, r, [*roster, *wv]), pos)
            best, best_pred = None, -1e18
            for a, t in cands:
                ids = [g for g in roster if g != a] + [t] + wv
                v = _total(plan, _expected_arrays(world, r, ids), pos) - base_pred
                if v > best_pred + 1e-9:
                    best, best_pred = (a, t), v
            execute = best is not None and best_pred > threshold
            real_if_exec = real_if_exec_hs = np.nan
            if best is not None:
                a, t = best
                after_ids = [g for g in roster if g != a] + [t] + wv
                real_if_exec = realized_forecast(after_ids, m) - realized_forecast(
                    [*roster, *wv], m
                )
                real_if_exec_hs = realized(after_ids) - realized([*roster, *wv])
            real_delta = real_if_exec if execute else 0.0
            rows.append(
                dict(
                    model=m,
                    season=world.season,
                    snapshot_week=world.week,
                    team=team,
                    executed=bool(execute),
                    pred_delta=best_pred if best else np.nan,
                    real_delta=real_delta,
                    real_if_exec=real_if_exec,
                    real_if_exec_hs=real_if_exec_hs,
                    give=best[0] if best else None,
                    get=best[1] if best else None,
                    oracle_delta=max(oracle, 0.0),
                    n_candidates=len(cands),
                    n_my_qbs=len(my_qbs),
                    get_qb_ecr_rank=world.overall_rank[best[1]] if execute else np.nan,
                )
            )
    return rows


def iter_snapshots(
    skill_players: pd.DataFrame,
    skill_weekly: pd.DataFrame,
    qb_preds: pd.DataFrame,
    league: LeagueContext,
    models: list[str],
    test_seasons=(2022, 2023, 2024, 2025),
    eval_weeks=(6, 7, 8, 9, 10),
):
    """Yield one prepared synthetic league per (test season, snapshot week).

    The QB universe is the board QBs that EVERY model in ``models`` forecast, so the leagues are
    identical across models -- callers that want the same leagues must pass the same ``models``."""
    lg = lineup_league(league)
    plan = slot_plan(lg)
    for T in test_seasons:
        maps = fit_skill_maps(skill_players[skill_players["season"] < T])
        for wk in eval_weeks:
            world = build_world(skill_players, skill_weekly, maps, T, wk)
            if not world.positions:
                continue
            board = skill_players[
                (skill_players["season"] == T) & (skill_players["snapshot_week"] == wk)
            ]
            qp = qb_preds[
                (qb_preds["season"] == T)
                & (qb_preds["snapshot_week"] == wk)
                & qb_preds["model"].isin(models)
            ]
            common = set.intersection(*[set(qp[qp["model"] == m]["gsis_id"]) for m in models])
            board = board[(board["position"] != "QB") | board["gsis_id"].isin(common)].sort_values(
                "overall_rank"
            )
            board = board.reset_index(drop=True)
            board["overall_rank"] = np.arange(1, len(board) + 1)
            world.overall_rank = dict(
                zip(board["gsis_id"], board["overall_rank"].astype(float), strict=True)
            )
            world.positions = {g: world.positions[g] for g in board["gsis_id"]}
            rosters = snake_draft(lg, board)
            qb_rates = {
                m: dict(
                    zip(
                        qp[qp["model"] == m]["gsis_id"],
                        qp[qp["model"] == m]["pred_rate"],
                        strict=True,
                    )
                )
                for m in models
            }
            yield {
                "season": T,
                "week": wk,
                "world": world,
                "rosters": rosters,
                "qb_rates": qb_rates,
                "maps": maps,
                "league": lg,
                "plan": plan,
            }


def run_roster_backtest(
    skill_players: pd.DataFrame,
    skill_weekly: pd.DataFrame,
    qb_preds: pd.DataFrame,
    league: LeagueContext,
    models: list[str],
    test_seasons=(2022, 2023, 2024, 2025),
    eval_weeks=(6, 7, 8, 9, 10),
    threshold: float = 0.0,
) -> pd.DataFrame:
    out: list[dict] = []
    for snap in iter_snapshots(
        skill_players, skill_weekly, qb_preds, league, models, test_seasons, eval_weeks
    ):
        out.extend(
            run_snapshot(
                snap["world"],
                snap["rosters"],
                snap["qb_rates"],
                snap["league"],
                snap["plan"],
                threshold,
            )
        )
    return pd.DataFrame(out)


def with_threshold(res: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Re-derive the decision at a different execution threshold from the stored best candidate
    (the candidate and its predicted/realized value do not depend on the threshold)."""
    d = res.copy()
    d["executed"] = d["pred_delta"] > threshold
    d["real_delta"] = np.where(d["executed"], d["real_if_exec"], 0.0)
    d["real_delta_hs"] = np.where(d["executed"], d["real_if_exec_hs"], 0.0)
    return d


def snapshot_roster_metrics(res: pd.DataFrame, threshold: float = 0.0) -> pd.DataFrame:
    res = with_threshold(res, threshold)
    g = res.groupby(["model", "season", "snapshot_week"])
    agg = g.apply(
        lambda d: pd.Series(
            {
                "mean_real_delta": d["real_delta"].mean(),
                "mean_real_delta_hindsight_lineups": d["real_delta_hs"].mean(),
                "trade_rate": d["executed"].mean(),
                "hit_rate": (d.loc[d["executed"], "real_delta"] > 0).mean()
                if d["executed"].any()
                else np.nan,
                "mean_pred_delta_exec": d.loc[d["executed"], "pred_delta"].mean()
                if d["executed"].any()
                else np.nan,
                "mean_real_delta_exec": d.loc[d["executed"], "real_delta"].mean()
                if d["executed"].any()
                else np.nan,
                "oracle_gap": (d["oracle_delta"] - d["real_delta"]).mean(),
                "n_teams": len(d),
            }
        ),
        include_groups=False,
    )
    return agg.reset_index()
