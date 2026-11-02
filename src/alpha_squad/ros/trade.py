"""Monte Carlo trade evaluation on top of weekly optimal-lineup value (Model F).

The quantity every output is built from:

    net trade value = E[ best-lineup points after trade ] - E[ best-lineup points before trade ]

computed week by week over the remaining schedule, with the SAME simulated season used for the
"before" and "after" rosters (common random numbers), so the difference isolates the trade.

What is simulated, per season-draw and per player
-------------------------------------------------
* a persistent skill level ``mu ~ N(mu_game, mu_sd)`` -- *model uncertainty*: the forecast is not
  the truth, and ``mu_sd`` is the out-of-sample forecast error measured in the backtest;
* weekly scores: gamma-distributed with mean ``mu`` and sd from ``noise.weekly_sd`` (estimated
  from data), driven through a Gaussian copula whose team factor makes teammates co-move
  (loadings from ``noise.team_loadings``);
* availability: byes are exact (from the schedule); an injury happens with the probability implied
  by the player's expected availability and removes a contiguous block of games whose size is
  drawn from the empirical missed-fraction distribution (``noise.missed_fraction_sample``).

Replacement. Every roster is given the league's waiver wire as extra bench players, so a slot
vacated by the trade is refilled at waiver level rather than at zero, and a QB hole is priced at
the best free QB.

What it does NOT validate. The simulated distributions are checked against history by the
backtest (``rosterbench``: coverage and calibration of P(trade helps)), but the playoff and
championship probabilities additionally need standings, the matchup schedule and opponents'
strength, which a caller must supply; without them they are scenario numbers resting on stated
assumptions and are flagged ``assumption_based``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
from scipy import stats as sps

from alpha_squad.league.context import LeagueContext
from alpha_squad.ros import noise as N
from alpha_squad.ros.lineup import UNAVAILABLE, SlotPlan, best_lineup_value, slot_plan


@dataclass
class Asset:
    pid: str
    name: str
    position: str
    team: str
    mu_game: float  # expected points per game when playing
    mu_sd: float  # model uncertainty about mu_game (points/game)
    avail: float  # expected fraction of remaining team games played
    weeks: tuple[int, ...]  # NFL weeks in which the team still plays (byes absent)
    notes: dict = field(default_factory=dict)

    @property
    def expected_total(self) -> float:
        return self.mu_game * self.avail * len(self.weeks)


def _seed_for(seed: int, key: str) -> np.random.Generator:
    h = int.from_bytes(hashlib.sha256(f"{seed}|{key}".encode()).digest()[:8], "little")
    return np.random.default_rng(h)


def simulate_assets(
    assets: list[Asset],
    all_weeks: list[int],
    noise: dict,
    n_sims: int,
    seed: int = 7,
    *,
    injury_multiplier: float = 1.0,
) -> dict[str, np.ndarray]:
    """{pid: (n_weeks, n_sims) weekly points; UNAVAILABLE where bye/injured}.

    Each asset's randomness is derived from ``(seed, pid)`` and each team factor from
    ``(seed, team)``, so adding or removing OTHER assets never changes an asset's draws."""
    W = len(all_weeks)
    widx = {w: i for i, w in enumerate(all_weeks)}
    loadings = N.team_loadings(noise)
    missed = np.asarray(noise.get("missed_fraction_sample") or [0.5])
    team_z: dict[str, np.ndarray] = {}
    out: dict[str, np.ndarray] = {}
    for a in assets:
        if a.team not in team_z:
            team_z[a.team] = _seed_for(seed, f"team:{a.team}").standard_normal((W, n_sims))
        r = _seed_for(seed, f"asset:{a.pid}")
        mu = np.clip(a.mu_game + a.mu_sd * r.standard_normal(n_sims), 0.5, None)
        sp = noise["weekly_sd"][a.position]
        sd = np.maximum(sp["a"] + sp["b"] * mu, 1.0)
        lam = loadings.get(a.position, 0.0)
        x = lam * team_z[a.team] + np.sqrt(max(1 - lam**2, 0.0)) * r.standard_normal((W, n_sims))
        u = np.clip(sps.norm.cdf(x), 1e-9, 1 - 1e-9)
        k = (mu / sd) ** 2
        pts = sps.gamma.ppf(u, a=k[None, :], scale=(sd**2 / mu)[None, :])

        n_g = len(a.weeks)
        arr = np.full((W, n_sims), UNAVAILABLE)
        game_pts = np.empty((n_g, n_sims))
        for j, wk in enumerate(a.weeks):
            game_pts[j] = pts[widx[wk]]
        # injuries: contiguous missed block over the player's own remaining games
        if n_g > 0:
            exp_missed = float(np.mean(missed))
            p_ev = min(max((1.0 - a.avail) * injury_multiplier / max(exp_missed, 1e-6), 0.0), 1.0)
            event = r.random(n_sims) < p_ev
            frac = r.choice(missed, size=n_sims)
            length = np.clip(np.rint(frac * n_g).astype(int), 1, n_g)
            start = np.floor(r.random(n_sims) * (n_g - length + 1)).astype(int)
            j = np.arange(n_g)[:, None]
            is_missed = event[None, :] & (j >= start[None, :]) & (j < (start + length)[None, :])
            game_pts = np.where(is_missed, UNAVAILABLE, game_pts)
        for j, wk in enumerate(a.weeks):
            arr[widx[wk]] = game_pts[j]
        out[a.pid] = arr
    return out


def season_value(
    plan: SlotPlan,
    weekly: dict[str, np.ndarray],
    positions: dict[str, str],
    rank_by: dict[str, np.ndarray] | None = None,
) -> np.ndarray:
    """(n_weeks, n_sims) lineup points, in one vectorized call (weeks x sims flattened).

    ``rank_by`` (same shape as ``weekly``) is what the lineup is chosen by; ``weekly`` is what it
    scores. Omitting it picks the lineup with hindsight."""
    if not weekly:
        return np.zeros((1, 1))
    W, S = next(iter(weekly.values())).shape
    flat = {p: a.reshape(-1) for p, a in weekly.items()}
    if rank_by is None:
        return best_lineup_value(plan, flat, positions).reshape(W, S)
    keys = {p: rank_by[p].reshape(-1) for p in weekly}
    return best_lineup_value(plan, keys, positions, scores=flat).reshape(W, S)


def forecast_keys(assets: dict[str, Asset], sims: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """What a manager knows when setting a lineup: the forecast mean of each player who is
    scheduled and not out (UNAVAILABLE otherwise) -- NOT the week's realized score."""
    return {p: np.where(sims[p] > UNAVAILABLE / 2, assets[p].mu_game, UNAVAILABLE) for p in sims}


def waiver_assets(
    league: LeagueContext,
    levels: dict[str, tuple[float, float, float]],
    weeks: tuple[int, ...],
    team: str = "FA",
    depth: int | None = None,
) -> list[Asset]:
    """Free-agent bodies. ``levels[pos] = (mu_game, mu_sd, avail)``. One body per lineup slot the
    position could fill (+1), so a vacated slot is refilled at waiver level, never at zero.
    Each waiver body gets its own team factor ``FA:<pos>:<i>`` (they are different real players)."""
    from alpha_squad.league.roster import startable_slots

    out = []
    for pos, (mu, sd, av) in levels.items():
        n = depth if depth is not None else startable_slots(league).get(pos, 0) + 1
        for i in range(n):
            out.append(
                Asset(
                    f"FA_{pos}_{i}",
                    f"waiver {pos}{i + 1}",
                    pos,
                    f"{team}:{pos}:{i}",
                    mu,
                    sd,
                    av,
                    weeks,
                    {"waiver": True},
                )
            )
    return out


@dataclass
class TradeSim:
    before: np.ndarray  # (n_weeks, n_sims) lineup points
    after: np.ndarray
    weeks: list[int]

    @property
    def delta(self) -> np.ndarray:
        return (self.after - self.before).sum(axis=0)

    def summary(self) -> dict[str, float]:
        d = self.delta
        return {
            "mean": float(d.mean()),
            "median": float(np.median(d)),
            "sd": float(d.std()),
            "p05": float(np.quantile(d, 0.05)),
            "p25": float(np.quantile(d, 0.25)),
            "p75": float(np.quantile(d, 0.75)),
            "p95": float(np.quantile(d, 0.95)),
            "prob_improves": float(np.mean(d > 0)),
            "mean_before": float(self.before.sum(axis=0).mean()),
            "mean_after": float(self.after.sum(axis=0).mean()),
        }


def evaluate_trade(
    league: LeagueContext,
    roster: list[Asset],
    give: list[str],
    get: list[Asset],
    waiver: list[Asset],
    noise: dict,
    *,
    n_sims: int = 4000,
    seed: int = 7,
    injury_multiplier: float = 1.0,
    plan: SlotPlan | None = None,
    sim_cache: dict | None = None,
    hindsight_lineups: bool = False,
) -> TradeSim:
    """Paired before/after lineup distributions for one candidate trade.

    ``give`` are pids on ``roster``; ``get`` are incoming assets. The pool simulated once covers
    roster + incoming + waiver, so every comparison inside a call shares its randomness.

    Lineups are chosen by FORECAST (each week's starters are picked from the forecast means of the
    players who are scheduled and healthy, then scored with what the simulation drew) -- the
    decision a manager can actually make. ``hindsight_lineups=True`` picks them with knowledge of
    the week's scores instead; that overstates the value of depth and waiver bodies and is exposed
    only as an upper-bound sensitivity."""
    plan = plan or slot_plan(league)
    have = {a.pid for a in roster}
    missing = [g for g in give if g not in have]
    if missing:
        raise ValueError(f"cannot give players not on the roster: {missing}")
    pool = {a.pid: a for a in [*roster, *get, *waiver]}
    weeks = sorted({w for a in pool.values() for w in a.weeks})
    key = (n_sims, seed, injury_multiplier, tuple(sorted(pool)))
    if sim_cache is not None and key in sim_cache:
        sims = sim_cache[key]
    else:
        sims = simulate_assets(
            list(pool.values()), weeks, noise, n_sims, seed, injury_multiplier=injury_multiplier
        )
        if sim_cache is not None:
            sim_cache[key] = sims
    pos = {p: a.position for p, a in pool.items()}
    before_ids = [a.pid for a in [*roster, *waiver]]
    after_ids = (
        [a.pid for a in roster if a.pid not in set(give)]
        + [a.pid for a in get]
        + [a.pid for a in waiver]
    )
    keys = None if hindsight_lineups else forecast_keys(pool, sims)
    before = season_value(
        plan,
        {p: sims[p] for p in before_ids},
        pos,
        None if keys is None else {p: keys[p] for p in before_ids},
    )
    after = season_value(
        plan,
        {p: sims[p] for p in after_ids},
        pos,
        None if keys is None else {p: keys[p] for p in after_ids},
    )
    return TradeSim(before, after, weeks)


# --------------------------------------------------------------------------------------------
# season outcome model: playoff and championship probability
# --------------------------------------------------------------------------------------------
@dataclass
class LeagueScenario:
    """Everything the playoff/championship probabilities need and the repo cannot know."""

    teams: int = 10
    playoff_teams: int = 6
    regular_season_last_week: int = 14
    playoff_weeks: tuple[int, ...] = (15, 16, 17)
    my_wins: int | None = None  # current wins (None -> unknown)
    games_played: int | None = None
    other_wins: tuple[int, ...] | None = None  # current wins of the other teams
    opp_weekly_mean: float | None = None  # a typical rival's weekly score; default = league mean
    opp_weekly_sd: float = 22.0
    strength_sd: float = 7.0

    @property
    def assumption_based(self) -> bool:
        return self.my_wins is None or self.other_wins is None or self.opp_weekly_mean is None


def _bracket(scores: np.ndarray, seeds: np.ndarray, byes: int) -> np.ndarray:
    """Single-elimination champion index per sim. ``scores`` (S, rounds, K) indexed by SEED
    position; ``seeds`` unused placeholder. Standard bracket: with 2 byes (K=6) seeds 1-2 skip
    round 1; with 0 byes (K=4/8) seed i plays seed K+1-i."""
    S, R, K = scores.shape
    if byes == 2 and K == 6:
        pairs1 = [(2, 5), (3, 4)]
        w1 = np.stack(
            [np.where(scores[:, 0, a] >= scores[:, 0, b], a, b) for a, b in pairs1], axis=1
        )
        # reseed: seed 0 faces the lowest remaining seed
        lo = w1.max(axis=1)
        hi = w1.min(axis=1)
        sc = lambda r, idx: scores[np.arange(S), r, idx]  # noqa: E731
        s0_win = sc(1, np.zeros(S, int)) >= sc(1, lo)
        s1_win = sc(1, np.ones(S, int)) >= sc(1, hi)
        f0 = np.where(s0_win, 0, lo)
        f1 = np.where(s1_win, 1, hi)
        champ = np.where(sc(2, f0) >= sc(2, f1), f0, f1)
        return champ
    # generic: pair best vs worst each round
    cur = np.tile(np.arange(K), (S, 1))
    for r in range(R):
        n = cur.shape[1]
        if n == 1:
            break
        nxt = []
        for i in range(n // 2):
            a, b = cur[:, i], cur[:, n - 1 - i]
            sa = scores[np.arange(S), r, a]
            sb = scores[np.arange(S), r, b]
            nxt.append(np.where(sa >= sb, a, b))
        cur = np.stack(nxt, axis=1)
        cur = np.sort(cur, axis=1)
    return cur[:, 0]


def simulate_outcomes(
    my_weekly: np.ndarray,
    weeks: list[int],
    scen: LeagueScenario,
    opp_mean: float,
    seed: int = 11,
) -> dict[str, np.ndarray]:
    """P(make playoffs) and P(champion) for a weekly-score path ``my_weekly`` (n_weeks, n_sims).

    Opponents: ``teams-1`` rivals with persistent strength ``N(0, strength_sd)`` and weekly score
    ``N(opp_mean + strength, opp_weekly_sd)``; random weekly pairings. The opponent draws depend
    only on ``seed`` (not on ``my_weekly``), so calling this for the before- and after-trade
    rosters uses identical rivals and the difference is the trade."""
    W, S = my_weekly.shape
    T = scen.teams
    rng = np.random.default_rng(seed)
    strength = rng.normal(0, scen.strength_sd, size=(S, T))
    strength[:, 0] = 0.0  # team 0 is the manager; its score comes from `my_weekly`
    reg_idx = [i for i, w in enumerate(weeks) if w <= scen.regular_season_last_week]
    po_idx = [i for i, w in enumerate(weeks) if w in scen.playoff_weeks]
    wins = np.zeros((S, T))
    pf = np.zeros((S, T))
    if scen.my_wins is not None and scen.other_wins is not None:
        wins[:, 0] = scen.my_wins
        wins[:, 1:] = np.asarray(scen.other_wins)[None, :]
    elif scen.my_wins is not None:
        wins[:, :] = scen.my_wins
    rng_w = np.random.default_rng(seed + 1)
    for i in reg_idx:
        score = opp_mean + strength + rng_w.normal(0, scen.opp_weekly_sd, size=(S, T))
        score[:, 0] = my_weekly[i]
        perm = np.argsort(rng_w.random((S, T)), axis=1)
        for k in range(0, T - 1, 2):
            a, b = perm[:, k], perm[:, k + 1]
            sa, sb = score[np.arange(S), a], score[np.arange(S), b]
            wins[np.arange(S), a] += sa > sb
            wins[np.arange(S), b] += sb > sa
        pf += score
    order = np.argsort(-(wins * 1e4 + pf), axis=1)
    seed_of_me = np.argmax(order == 0, axis=1)  # position of team 0 in the ranking
    made = seed_of_me < scen.playoff_teams
    champ = np.zeros(S, dtype=bool)
    if po_idx and scen.playoff_teams >= 4:
        K = scen.playoff_teams
        R = len(po_idx)
        sc = np.empty((S, R, K))
        rng_p = np.random.default_rng(seed + 2)
        for r, i in enumerate(po_idx[:R]):
            for k in range(K):
                team = order[:, k]
                s_opp = (
                    opp_mean
                    + strength[np.arange(S), team]
                    + rng_p.normal(0, scen.opp_weekly_sd, size=S)
                )
                sc[:, r, k] = np.where(team == 0, my_weekly[i], s_opp)
        byes = 2 if K == 6 else 0
        winner_seed = _bracket(sc, np.arange(K), byes)
        champ = made & (order[np.arange(S), winner_seed] == 0)
    return {"made_playoffs": made, "champion": champ}


def playoff_deltas(
    sim: TradeSim, scen: LeagueScenario, opp_mean: float, seed: int = 11
) -> dict[str, float]:
    b = simulate_outcomes(sim.before, sim.weeks, scen, opp_mean, seed)
    a = simulate_outcomes(sim.after, sim.weeks, scen, opp_mean, seed)
    return {
        "p_playoffs_before": float(b["made_playoffs"].mean()),
        "p_playoffs_after": float(a["made_playoffs"].mean()),
        "d_playoffs_pp": 100 * float(a["made_playoffs"].mean() - b["made_playoffs"].mean()),
        "p_champion_before": float(b["champion"].mean()),
        "p_champion_after": float(a["champion"].mean()),
        "d_champion_pp": 100 * float(a["champion"].mean() - b["champion"].mean()),
        "assumption_based": scen.assumption_based,
    }


# --------------------------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------------------------
LABELS = (
    "Strongly favorable",
    "Favorable",
    "Approximately neutral",
    "Unfavorable",
    "Strongly unfavorable",
    "Insufficient evidence",
)

#: Classification thresholds, fixed before any live recommendation was produced. Points are ROS
#: lineup points for a ~9-game remainder (about 1 point per game); probabilities are
#: P(trade improves the lineup) under the base simulation.
STRONG_MEAN, STRONG_PROB = 20.0, 0.85
FAV_MEAN, FAV_PROB = 8.0, 0.65


def classify(
    base: dict[str, float],
    sensitivities: dict[str, dict[str, float]],
    *,
    evidence_ok: bool = True,
) -> tuple[str, list[str]]:
    """Label a trade from its base simulation and its sensitivity scenarios.

    A positive label requires the base case AND the worst sensitivity scenario to agree on sign;
    a base-case 'strong' that flips sign in a sensitivity run is downgraded one step, never
    promoted. ``evidence_ok=False`` (missing/stale inputs) returns 'Insufficient evidence'."""
    notes: list[str] = []
    if not evidence_ok:
        return "Insufficient evidence", ["required inputs missing or stale"]
    m, p = base["mean"], base["prob_improves"]
    worst = min((s["mean"] for s in sensitivities.values()), default=m)
    best = max((s["mean"] for s in sensitivities.values()), default=m)
    if m >= STRONG_MEAN and p >= STRONG_PROB:
        label = "Strongly favorable"
    elif m >= FAV_MEAN and p >= FAV_PROB:
        label = "Favorable"
    elif m <= -STRONG_MEAN and p <= 1 - STRONG_PROB:
        label = "Strongly unfavorable"
    elif m <= -FAV_MEAN and p <= 1 - FAV_PROB:
        label = "Unfavorable"
    else:
        label = "Approximately neutral"
    if label in ("Strongly favorable", "Favorable") and worst <= 0:
        label = "Favorable" if label == "Strongly favorable" else "Approximately neutral"
        notes.append("a sensitivity scenario flips the sign -> downgraded one level")
    if label in ("Strongly unfavorable", "Unfavorable") and best >= 0:
        label = "Unfavorable" if label == "Strongly unfavorable" else "Approximately neutral"
        notes.append("a sensitivity scenario flips the sign -> downgraded one level")
    return label, notes
