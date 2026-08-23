"""Correlated team-season Monte Carlo simulation (PRODUCT_SPEC.md's Simulation section,
deferred to M13 per docs/DECISIONS.md D8: "eventually"/"later-stage" in the source docs,
built once the validated core existed).

Every distributional parameter is estimated from real historical data
(team_week_stats/team_week_points/player_week_stats) -- never fabricated or hand-picked. The
generative structure is what actually produces correlation, rather than it being assumed or
hardcoded: every simulated trial draws ONE joint (plays, pass_rate, team_points) sample from
the team's own real historical covariance, and every rostered player's simulated output is
computed from that SAME trial's draw (their real historical opportunity share × that trial's
simulated volume × their real historical efficiency). Players who share a team environment
are therefore driven by the same underlying randomness -- this is what makes a QB and his
WR1 genuinely correlated in the output, and it is measured empirically from the simulation's
own results as a validation check (`qb_wr1_correlation`), never assumed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import duckdb
import numpy as np

from alpha_squad.sources.base import utcnow

MIN_TEAM_WEEKS = 8
MIN_PLAYER_WEEKS = 4
_PASS_CATCHER_POSITIONS = ("WR", "TE")


@dataclass
class PlayerSimResult:
    player_id: str
    position: str
    mean_points: float
    std_points: float
    p10: float
    p50: float
    p90: float


@dataclass
class TeamSimulationResult:
    team: str
    season: int
    n_simulations: int
    n_weeks: int
    mean_team_points: float
    std_team_points: float
    players: list[PlayerSimResult] = field(default_factory=list)
    qb_wr1_correlation: float | None = None
    same_position_correlation: float | None = None


def _team_environment_history(
    con: duckdb.DuckDBPyConnection, team: str, before_season: int
) -> np.ndarray:
    rows = con.execute(
        """
        SELECT s.plays, s.pass_rate, p.points
        FROM team_week_stats s
        JOIN team_week_points p ON p.team = s.team AND p.season = s.season AND p.week = s.week
        WHERE s.team = ? AND s.season < ? AND s.plays IS NOT NULL AND s.pass_rate IS NOT NULL
        """,
        [team, before_season],
    ).fetchall()
    return np.array(rows, dtype=float)


def _sample_team_environment(history: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Real historical mean + covariance -> n joint (plays, pass_rate, points) draws. A small
    ridge keeps the covariance well-conditioned for sampling without materially altering the
    real correlation structure a limited real sample can produce."""
    mean = history.mean(axis=0)
    cov = np.cov(history, rowvar=False) + np.eye(3) * 1e-6
    samples = rng.multivariate_normal(mean, cov, size=n)
    samples[:, 0] = np.clip(samples[:, 0], 40, 90)
    samples[:, 1] = np.clip(samples[:, 1], 0.15, 0.85)
    samples[:, 2] = np.clip(samples[:, 2], 0, 60)
    return samples


def _pass_catcher_shares(
    con: duckdb.DuckDBPyConnection, team: str, season: int
) -> dict[str, tuple[str, float, float]]:
    """{player_id: (position, real target share, real points per target)} for real
    pass-catchers (WR/TE) on this team/season.

    Share's denominator is the team's TOTAL targets that season -- every position, not just
    qualifying WR/TEs -- because it is later multiplied against `pass_attempts`, the team's
    full simulated passing volume. Using the smaller sum-of-qualifying-WR/TEs denominator
    instead would inflate every qualifying pass-catcher's simulated volume by however much
    real target volume went to RBs or to receivers below MIN_PLAYER_WEEKS
    (docs/DECISIONS.md D-simulation-1)."""
    team_total_targets = con.execute(
        "SELECT sum(targets) FROM player_week_stats WHERE team = ? AND season = ? AND targets IS NOT NULL",
        [team, season],
    ).fetchone()[0]
    if not team_total_targets:
        return {}
    # ORDER BY matters beyond readability: simulate_team_season iterates this dict in
    # insertion order, drawing each player's noise sequentially from one shared
    # np.random.Generator, so an unordered GROUP BY would make the seeded RNG stream
    # non-reproducible (which named player gets which draw becomes query-plan-dependent).
    rows = con.execute(
        """
        SELECT player_id, position, sum(targets) AS total_targets, sum(fantasy_points_ppr) AS total_points
        FROM player_week_stats
        WHERE team = ? AND season = ? AND position IN ('WR', 'TE') AND targets IS NOT NULL
        GROUP BY player_id, position
        HAVING count(*) >= ? AND sum(targets) > 0
        ORDER BY player_id
        """,
        [team, season, MIN_PLAYER_WEEKS],
    ).fetchall()
    return {r[0]: (r[1], r[2] / team_total_targets, r[3] / r[2]) for r in rows}


def _rb_shares(
    con: duckdb.DuckDBPyConnection, team: str, season: int
) -> dict[str, tuple[str, float, float]]:
    """Same team-total-denominator reasoning as `_pass_catcher_shares`, using carries: the
    team total includes QB scrambles/kneels and below-threshold backs, which real
    rush_attempts in a simulated trial also implicitly includes."""
    team_total_carries = con.execute(
        "SELECT sum(carries) FROM player_week_stats WHERE team = ? AND season = ? AND carries IS NOT NULL",
        [team, season],
    ).fetchone()[0]
    if not team_total_carries:
        return {}
    # See the ORDER BY note in _pass_catcher_shares -- same reproducibility requirement.
    rows = con.execute(
        """
        SELECT player_id, position, sum(carries) AS total_carries, sum(fantasy_points_ppr) AS total_points
        FROM player_week_stats
        WHERE team = ? AND season = ? AND position = 'RB' AND carries IS NOT NULL
        GROUP BY player_id, position
        HAVING count(*) >= ? AND sum(carries) > 0
        ORDER BY player_id
        """,
        [team, season, MIN_PLAYER_WEEKS],
    ).fetchall()
    return {r[0]: (r[1], r[2] / team_total_carries, r[3] / r[2]) for r in rows}


def _starting_qb(
    con: duckdb.DuckDBPyConnection, team: str, season: int
) -> tuple[str, float] | None:
    """The real player with the most starts (offense_snap_pct > 0.5) at QB for this
    team/season, plus his real historical (fantasy points per pass attempt) ratio.

    Anchored to pass_attempts rather than team_points: real historical team-environment data
    (docs/DECISIONS.md D-simulation-1) shows pass_attempts and team_points are only weakly
    correlated per team (game-script effects -- teams both run more *and* pass less when
    already ahead), so a team_points-anchored QB would rarely land in the same simulated
    trial as a big pass-volume trial for his own WR1, even though real QB/WR1 fantasy
    correlation comes specifically from sharing the same passing plays. pass_attempts is the
    same shared draw every pass-catcher already uses, so anchoring the QB to it too is what
    makes the stack correlation real rather than incidental."""
    row = con.execute(
        """
        SELECT s.player_id,
               avg(s.fantasy_points_ppr / NULLIF(t.plays * t.pass_rate, 0)) AS pts_per_pass_attempt
        FROM player_week_stats s
        JOIN team_week_stats t ON t.team = s.team AND t.season = s.season AND t.week = s.week
        WHERE s.team = ? AND s.season = ? AND s.position = 'QB' AND s.offense_snap_pct > 0.5
        GROUP BY s.player_id
        ORDER BY count(*) DESC, s.player_id
        LIMIT 1
        """,
        [team, season],
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return row[0], float(row[1])


def simulate_team_season(
    con: duckdb.DuckDBPyConnection,
    team: str,
    season: int,
    n_weeks: int = 17,
    n_simulations: int = 1000,
    seed: int = 42,
) -> TeamSimulationResult | None:
    history = _team_environment_history(con, team, season)
    if len(history) < MIN_TEAM_WEEKS:
        return None

    rng = np.random.default_rng(seed)
    n_trials = n_simulations * n_weeks
    env = _sample_team_environment(history, n_trials, rng)
    plays, pass_rate, team_points = env[:, 0], env[:, 1], env[:, 2]
    pass_attempts = plays * pass_rate
    rush_attempts = plays * (1 - pass_rate)

    weekly_points: dict[str, np.ndarray] = {}
    positions: dict[str, str] = {}

    for player_id, (position, share, efficiency) in _pass_catcher_shares(con, team, season).items():
        noise = rng.lognormal(mean=0.0, sigma=0.35, size=n_trials)
        weekly_points[player_id] = pass_attempts * share * efficiency * noise
        positions[player_id] = position

    for player_id, (position, share, efficiency) in _rb_shares(con, team, season).items():
        noise = rng.lognormal(mean=0.0, sigma=0.35, size=n_trials)
        weekly_points[player_id] = rush_attempts * share * efficiency * noise
        positions[player_id] = position

    qb = _starting_qb(con, team, season)
    if qb is not None:
        qb_id, pts_per_pass_attempt = qb
        noise = rng.lognormal(mean=0.0, sigma=0.25, size=n_trials)
        weekly_points[qb_id] = pass_attempts * pts_per_pass_attempt * noise
        positions[qb_id] = "QB"

    players: list[PlayerSimResult] = []
    for player_id, pts in weekly_points.items():
        season_totals = pts.reshape(n_simulations, n_weeks).sum(axis=1)
        players.append(
            PlayerSimResult(
                player_id=player_id,
                position=positions[player_id],
                mean_points=float(season_totals.mean()),
                std_points=float(season_totals.std()),
                p10=float(np.percentile(season_totals, 10)),
                p50=float(np.percentile(season_totals, 50)),
                p90=float(np.percentile(season_totals, 90)),
            )
        )
    players.sort(key=lambda p: -p.mean_points)

    qb_wr1_corr = None
    if qb is not None:
        qb_id = qb[0]
        wr1 = next(
            (p for p in players if p.position in _PASS_CATCHER_POSITIONS and p.player_id != qb_id),
            None,
        )
        if wr1 is not None:
            qb_wr1_corr = float(
                np.corrcoef(weekly_points[qb_id], weekly_points[wr1.player_id])[0, 1]
            )

    same_position_corr = None
    pass_catchers = [p for p in players if p.position in _PASS_CATCHER_POSITIONS]
    if len(pass_catchers) >= 2:
        same_position_corr = float(
            np.corrcoef(
                weekly_points[pass_catchers[0].player_id], weekly_points[pass_catchers[1].player_id]
            )[0, 1]
        )

    season_team_totals = team_points.reshape(n_simulations, n_weeks).sum(axis=1)
    return TeamSimulationResult(
        team=team,
        season=season,
        n_simulations=n_simulations,
        n_weeks=n_weeks,
        mean_team_points=float(season_team_totals.mean()),
        std_team_points=float(season_team_totals.std()),
        players=players,
        qb_wr1_correlation=qb_wr1_corr,
        same_position_correlation=same_position_corr,
    )


def record_simulation_run(
    con: duckdb.DuckDBPyConnection, result: TeamSimulationResult, seed: int
) -> str:
    """Persists the team-level summary to `team_simulation_runs` (M13_SIMULATION_DDL);
    player-level detail lives only in the returned `TeamSimulationResult` -- run this
    immediately after `simulate_team_season` if the per-player breakdown doesn't need to
    outlive the process, or have the caller print/export it first."""
    built_at = utcnow()
    digest = hashlib.md5(f"{result.team}:{result.season}:{seed}:{built_at}".encode()).hexdigest()[
        :16
    ]
    run_id = f"sim_{digest}"
    con.execute(
        """
        INSERT INTO team_simulation_runs
            (run_id, team, season, n_simulations, seed, mean_team_points, std_team_points,
             qb_wr1_correlation, same_position_correlation, built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            result.team,
            result.season,
            result.n_simulations,
            seed,
            result.mean_team_points,
            result.std_team_points,
            result.qb_wr1_correlation,
            result.same_position_correlation,
            built_at,
        ],
    )
    return run_id
