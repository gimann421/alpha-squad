"""Pre-cutoff context for every evaluated player-week (W5).

**Every quantity here is computed from strictly-prior information**, and the one exception is
labelled at its definition. The module exists so the cohort and information-class analyses in
`docs/weekly/W5_PREREGISTRATION.md` §8-§9 rest on one auditable set of SQL predicates rather than
on ad-hoc joins scattered through a runner.

The causality rule, in one place
--------------------------------
For week *w* of season *S*, "prior" means `(season < S) OR (season = S AND week < w)`. It is
emitted by `PriorWindow.sql`, the same shape W4's `calibration.FitWindow` used, and a validity
gate runs that predicate against the real tables and asks for the latest row it admits.

What is deliberately NOT here
-----------------------------
* **No current-week usage.** Targets, carries and snaps for week *w* are the outcome's own
  cause; they are Class D and appear only inside the `ORACLE_USAGE` diagnostic, never here.
* **No ECR.** W5 may not read the benchmark into any explanatory variable.
* **No served evidence layer.** W3 found a live post-Friday injury leak in it; this module reads
  the immutable nflverse snapshot directly and applies its own cutoff.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import duckdb

#: A player counts as RETURNING if at least this many calendar weeks passed since his last
#: appearance. 2 (i.e. he missed at least one week) -- fixed in the pre-registration.
RETURNING_GAP_WEEKS = 2
#: HIGH_SNAP threshold on `snap_pct_avg_last3`. Fixed in the pre-registration.
HIGH_SNAP_PCT = 0.75
#: LOW_SAMPLE threshold on `games_played_prior`.
LOW_SAMPLE_GAMES = 2
#: ELITE_PRIOR_SEASON depth, by prior-season total PPR points.
ELITE_DEPTH = 12
#: An opponent's points-allowed measure needs at least this many prior weeks to be reported.
MIN_OPPONENT_WEEKS = 3

#: The two pre-registered injury-cutoff variants. `nflverse/injuries` stores one FINAL row per
#: player-week, so a `date_modified` filter DELETES a row rather than rewinding it; STRICT is the
#: conservative reading and FRIDAY matches ECR's own publication vintage.
INJURY_VARIANTS: tuple[str, ...] = ("STRICT", "FRIDAY")
#: Seasons whose injury file carries `date_modified`. 2025 does not, and is excluded outright
#: rather than imputed -- see `docs/weekly/W5_PREREGISTRATION.md` §2.5.
INJURY_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024)


@dataclass(frozen=True)
class PriorWindow:
    """The strictly-prior window any W5 explanatory variable may see."""

    season: int
    week: int

    def sql(self, alias: str) -> str:
        return (
            f"({alias}.season < {self.season} OR "
            f"({alias}.season = {self.season} AND {alias}.week < {self.week}))"
        )


@dataclass
class PlayerContext:
    """Everything W5 knows about one player-week **before** the Friday cutoff."""

    player_id: str
    position: str
    team: str | None = None
    opponent: str | None = None
    # --- role and opportunity, from prior appearances only ---
    games_played_prior: int = 0
    snap_pct_avg_last3: float | None = None
    opportunity_last1: float | None = None
    opportunity_avg_prior3: float | None = None
    opportunity_delta: float | None = None
    snap_delta: float | None = None
    snap_sd_prior3: float | None = None
    weeks_since_last_game: int | None = None
    prior_team: str | None = None
    fp_ppr_avg_last3: float | None = None
    fp_ppr_avg_season_to_date: float | None = None
    prior_season_rank: int | None = None
    rookie_season: int | None = None
    # --- context that Alpha does not use at all ---
    opponent_pa_prior: float | None = None
    opponent_pa_weeks: int = 0
    team_epa_avg_last3: float | None = None
    team_plays_avg_last3: float | None = None
    team_epa_delta: float | None = None
    depth_team_prior: int | None = None
    # --- injury, per cutoff variant; None means "no usable row", never "healthy" ---
    injury: dict[str, str | None] = field(default_factory=dict)
    practice: dict[str, str | None] = field(default_factory=dict)
    teammates_out: dict[str, int] = field(default_factory=dict)


def _fetch(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> list[tuple]:
    return con.execute(sql, params).fetchall()


def _sample_sd(values: list) -> float | None:
    """Sample standard deviation, summed in a fixed order so it is bit-for-bit reproducible."""
    xs = [float(v) for v in values]
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    return (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _exact_mean(values: list) -> float | None:
    """Mean of the non-null values with a correctly-rounded sum (`math.fsum`).

    Replaces SQL `avg()` over DOUBLE, whose parallel partial sums combine in a planner-chosen
    order: W8's pre-analysis reproduction of W5 caught `avg(fantasy_points_ppr)` moving in the
    last bit (max 3.6e-15) between runs. `fsum` is exact before its single final rounding, so
    the result is independent of the input order, not merely of one fixed order."""
    xs = [float(v) for v in values if v is not None]
    return math.fsum(xs) / len(xs) if xs else None


def load_role_context(
    con: duckdb.DuckDBPyConnection, season: int, week: int, positions: tuple[str, ...]
) -> dict[str, PlayerContext]:
    """Role, opportunity and recency, all from games the player already played.

    `opportunity` is `targets + carries` -- the two touch types a fantasy point can come from,
    added rather than modelled, because W5 is measuring whether role *change* matters, not
    building a usage model. `weeks_since_last_game` is the measure that actually captures
    "returning from an absence", and it is strictly pre-cutoff: it needs only the calendar."""
    win = PriorWindow(season, week)
    rows = _fetch(
        con,
        f"""
        WITH prior AS (
            SELECT s.player_id, s.position, s.season, s.week, s.team,
                   COALESCE(s.targets, 0) + COALESCE(s.carries, 0) AS opp,
                   s.offense_snap_pct AS snap,
                   row_number() OVER (
                       PARTITION BY s.player_id ORDER BY s.season DESC, s.week DESC
                   ) AS recency
            FROM player_week_stats s
            WHERE {win.sql("s")} AND s.position = ANY(?)
        )
        SELECT player_id,
               max(CASE WHEN recency = 1 THEN opp END)                       AS opp_last1,
               avg(CASE WHEN recency BETWEEN 2 AND 4 THEN opp END)           AS opp_prior3,
               max(CASE WHEN recency = 1 THEN snap END)                      AS snap_last1,
               list(CASE WHEN recency BETWEEN 2 AND 4 THEN snap END ORDER BY recency)
                                                                             AS snap_list_prior3,
               -- `list(... ORDER BY ...)` and a Python reduction, not `stddev_samp`: floating
               -- point addition is not associative, so an aggregate whose input order the
               -- planner may vary is not reproducible. G2 caught one such movement.
               list(CASE WHEN recency <= 3 THEN snap END ORDER BY recency) AS snap_list3,
               max(CASE WHEN recency = 1 THEN team END)                      AS prior_team,
               max(CASE WHEN recency = 1 AND season = ? THEN week END)       AS last_week_same_season
        FROM prior
        GROUP BY 1
        """,
        [list(positions), season],
    )
    out: dict[str, PlayerContext] = {}
    for pid, o1, o3, s1, s3, ssd, pteam, lastwk in rows:
        ctx = PlayerContext(player_id=pid, position="")
        ctx.opportunity_last1 = None if o1 is None else float(o1)
        ctx.opportunity_avg_prior3 = None if o3 is None else float(o3)
        if o1 is not None and o3 is not None:
            ctx.opportunity_delta = float(o1) - float(o3)
        s3 = _exact_mean(s3 or [])
        if s1 is not None and s3 is not None:
            ctx.snap_delta = float(s1) - float(s3)
        ctx.snap_sd_prior3 = _sample_sd([v for v in (ssd or []) if v is not None])
        ctx.prior_team = pteam
        # A player with no prior game THIS season has no measurable gap; leaving it None keeps
        # "never appeared" distinct from "played last week", which a 0 would silently merge.
        ctx.weeks_since_last_game = None if lastwk is None else int(week - int(lastwk))
        out[pid] = ctx
    return out


def attach_features(
    con: duckdb.DuckDBPyConnection, season: int, week: int, ctx: dict[str, PlayerContext]
) -> None:
    """The model's own lagged view, so cohorts are defined on exactly what Alpha saw."""
    rows = _fetch(
        con,
        """
        SELECT player_id, position, team, games_played_prior, snap_pct_avg_last3,
               fp_ppr_avg_last3, fp_ppr_avg_season_to_date,
               team_epa_avg_last3, team_plays_avg_last3
        FROM player_week_features WHERE season = ? AND week = ?
        """,
        [season, week],
    )
    for pid, pos, team, gpp, snap3, fp3, fpstd, epa, plays in rows:
        c = ctx.setdefault(pid, PlayerContext(player_id=pid, position=pos))
        c.position = pos or c.position
        c.team = team
        c.games_played_prior = int(gpp or 0)
        c.snap_pct_avg_last3 = None if snap3 is None else float(snap3)
        c.fp_ppr_avg_last3 = None if fp3 is None else float(fp3)
        c.fp_ppr_avg_season_to_date = None if fpstd is None else float(fpstd)
        c.team_epa_avg_last3 = None if epa is None else float(epa)
        c.team_plays_avg_last3 = None if plays is None else float(plays)


def attach_prior_season_rank(
    con: duckdb.DuckDBPyConnection, season: int, ctx: dict[str, PlayerContext]
) -> None:
    """Positional rank by the **previous** season's total PPR points. Class B by construction.

    The `player_id` tiebreak is load-bearing, not cosmetic: 13 TEs finished 2020 on exactly 0.0
    points, and a `row_number()` whose ORDER BY leaves them tied returns a different rank
    depending on the query plan. W5's own G2 gate caught 3,268 such movements across 8 sampled
    weeks -- not leakage, but an instrument that would not have reproduced."""
    rows = _fetch(
        con,
        """
        SELECT player_id, position, rk FROM (
            SELECT s.player_id, s.position,
                   row_number() OVER (
                       PARTITION BY s.position
                       ORDER BY sum(s.fantasy_points_ppr) DESC, s.player_id
                   ) rk
            FROM player_week_stats s WHERE s.season = ? GROUP BY 1, 2
        ) WHERE rk <= 400
        """,
        [season - 1],
    )
    for pid, _pos, rk in rows:
        if pid in ctx:
            ctx[pid].prior_season_rank = int(rk)


def attach_rookie_season(con: duckdb.DuckDBPyConnection, ctx: dict[str, PlayerContext]) -> None:
    for pid, rookie in _fetch(
        con, "SELECT player_id, rookie_season FROM players WHERE rookie_season IS NOT NULL", []
    ):
        if pid in ctx:
            ctx[pid].rookie_season = int(rookie)


def attach_opponent(
    con: duckdb.DuckDBPyConnection, season: int, week: int, ctx: dict[str, PlayerContext]
) -> None:
    """Opponent identity (from the fixed schedule) and the opponent's **prior** points allowed.

    Opponent identity is the cleanest Class B signal in the repository: the schedule is published
    months ahead, so no timestamp question arises. Points-allowed is averaged over strictly prior
    weeks of the same season and is reported only when at least `MIN_OPPONENT_WEEKS` exist, so an
    early-season figure built on one game is never presented as a matchup measure."""
    opp_of: dict[str, str] = {}
    for home, away in _fetch(
        con,
        "SELECT home_team, away_team FROM games WHERE season=? AND week=? AND game_type='REG'",
        [season, week],
    ):
        opp_of[home], opp_of[away] = away, home
    pa: dict[tuple[str, str], tuple[float, int]] = {}
    for opp, pos, pa_list, n in _fetch(
        con,
        """
        SELECT g.opp, s.position,
               list(s.fantasy_points_ppr ORDER BY s.week, s.player_id),
               count(DISTINCT s.week)
        FROM player_week_stats s
        JOIN (
            SELECT season, week, home_team AS team, away_team AS opp FROM games WHERE game_type='REG'
            UNION ALL
            SELECT season, week, away_team AS team, home_team AS opp FROM games WHERE game_type='REG'
        ) g ON g.season=s.season AND g.week=s.week AND g.team=s.team
        WHERE s.season = ? AND s.week < ?
        GROUP BY 1, 2
        """,
        [season, week],
    ):
        pa[(opp, pos)] = (_exact_mean(pa_list or []) or 0.0, int(n))
    for c in ctx.values():
        if not c.team:
            continue
        c.opponent = opp_of.get(c.team)
        if c.opponent and c.position:
            val, n = pa.get((c.opponent, c.position), (None, 0))
            if n >= MIN_OPPONENT_WEEKS:
                c.opponent_pa_prior, c.opponent_pa_weeks = val, n
            else:
                c.opponent_pa_weeks = n


# ---------------------------------------------------------------------------------------
# Sources that live only as immutable snapshots, never as DuckDB tables. Each is wired into
# a TEMP VIEW once per run and carries its own cutoff rule.
# ---------------------------------------------------------------------------------------


def wire_snapshot_views(con: duckdb.DuckDBPyConnection, seasons: tuple[int, ...]) -> dict:
    """Materialise `injuries`, `depth_charts` and `ep_weekly` as canonical-id TEMP VIEWs.

    Returns a provenance dict of the sha256s actually used, so a result can be tied to the exact
    snapshot vintage rather than to "whatever was on disk". Seasons whose file does not carry the
    column a view needs are **left out and reported**, never filled in."""
    import json as _json

    from alpha_squad.identity.canonical import reader_expr

    con.execute(
        "CREATE OR REPLACE TEMP VIEW _gsis AS "
        "SELECT id_value AS gsis_id, player_id FROM player_id_map WHERE id_type = 'gsis_id'"
    )

    def latest_by_season(source: str, dataset: str) -> dict[int, dict]:
        out: dict[int, dict] = {}
        for params, path, sha, cols in con.execute(
            "SELECT params_json, local_path, sha256, columns_json FROM snapshot_registry "
            "WHERE source = ? AND dataset = ? ORDER BY captured_at",
            [source, dataset],
        ).fetchall():
            raw = _json.loads(params).get("season")
            if raw is None:
                continue
            out[int(raw)] = {"path": path, "sha256": sha, "columns": _json.loads(cols)}
        return out

    prov: dict = {}

    inj = latest_by_season("nflverse", "injuries")
    # 2025 has no `date_modified`; including it would mean either fabricating a timestamp or
    # silently treating post-Friday edits as pre-Friday. Both are excluded by CLAUDE.md.
    inj_use = [s for s in seasons if s in inj and "date_modified" in inj[s]["columns"]]
    prov["injuries"] = {
        "seasons_used": inj_use,
        "seasons_dropped": [s for s in seasons if s not in inj_use],
        "sha256": {s: inj[s]["sha256"] for s in inj_use},
    }
    if inj_use:
        union = " UNION ALL ".join(
            'SELECT CAST(season AS INTEGER) AS "season", CAST(week AS INTEGER) AS "week", '
            'CAST(gsis_id AS VARCHAR) AS "gsis_id", team AS "team", position AS "position", '
            'report_status AS "report_status", practice_status AS "practice_status", '
            f'CAST(date_modified AS DATE) AS "modified_on" FROM {reader_expr(inj[s]["path"])} '
            "WHERE game_type = 'REG'"
            for s in inj_use
        )
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW _injuries AS "
            f"SELECT g.player_id, x.* FROM ({union}) x JOIN _gsis g ON g.gsis_id = x.gsis_id"
        )
    else:  # pragma: no cover - only if every season's file loses the column
        con.execute(
            "CREATE OR REPLACE TEMP VIEW _injuries AS SELECT NULL::VARCHAR player_id, "
            "NULL::INTEGER season, NULL::INTEGER week, NULL::VARCHAR gsis_id, NULL::VARCHAR team, "
            "NULL::VARCHAR position, NULL::VARCHAR report_status, NULL::VARCHAR practice_status, "
            "NULL::DATE modified_on WHERE FALSE"
        )

    dc = latest_by_season("nflverse", "depth_charts")
    # 2025 is a different, week-less shape (daily `dt` snapshots, `pos_rank` instead of
    # `depth_team`). It is the only season with a real timestamp and the only one W5 cannot use,
    # because it has no week key to join on. Reported, not bridged.
    dc_use = [s for s in seasons if s in dc and "depth_team" in dc[s]["columns"]]
    prov["depth_charts"] = {
        "seasons_used": dc_use,
        "seasons_dropped": [s for s in seasons if s not in dc_use],
        "sha256": {s: dc[s]["sha256"] for s in dc_use},
    }
    if dc_use:
        union = " UNION ALL ".join(
            'SELECT CAST(season AS INTEGER) AS "season", CAST(week AS INTEGER) AS "week", '
            'CAST(gsis_id AS VARCHAR) AS "gsis_id", '
            'CAST(depth_team AS INTEGER) AS "depth_team", '
            f'position AS "position" FROM {reader_expr(dc[s]["path"])} '
            "WHERE game_type = 'REG' AND formation = 'Offense'"
            for s in dc_use
        )
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW _depth AS "
            f"SELECT g.player_id, x.* FROM ({union}) x JOIN _gsis g ON g.gsis_id = x.gsis_id"
        )
    else:  # pragma: no cover
        con.execute(
            "CREATE OR REPLACE TEMP VIEW _depth AS SELECT NULL::VARCHAR player_id, "
            "NULL::INTEGER season, NULL::INTEGER week, NULL::VARCHAR gsis_id, "
            "NULL::INTEGER depth_team, NULL::VARCHAR position WHERE FALSE"
        )

    ep = latest_by_season("ffopportunity", "ep_weekly")
    ep_use = [s for s in seasons if s in ep]
    prov["ep_weekly"] = {"seasons_used": ep_use, "sha256": {s: ep[s]["sha256"] for s in ep_use}}
    union = " UNION ALL ".join(
        'SELECT CAST(season AS INTEGER) AS "season", CAST(week AS INTEGER) AS "week", '
        'CAST(player_id AS VARCHAR) AS "gsis_id", '
        'CAST(total_fantasy_points_exp AS DOUBLE) AS "points_exp", '
        'CAST(receptions_exp AS DOUBLE) AS "receptions_exp" '
        f"FROM {reader_expr(ep[s]['path'])}"
        for s in ep_use
    )
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW _usage AS "
        f"SELECT g.player_id, x.* FROM ({union}) x JOIN _gsis g ON g.gsis_id = x.gsis_id"
    )
    return prov


def attach_injury(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    cutoff_date,
    ctx: dict[str, PlayerContext],
) -> None:
    """The player's own injury row and his position-mates' — under both cutoff variants.

    `None` in `injury`/`practice` means **no usable row survived the cutoff**, which is not the
    same as "healthy" and is never collapsed into it: most healthy players simply never appear on
    an injury report. `teammates_out` counts same-team, same-position players listed Out or
    Doubtful under the variant -- the mechanism by which one player's injury creates another
    player's opportunity, which is Part 8's actual question."""
    if season not in INJURY_SEASONS:
        return
    for variant in INJURY_VARIANTS:
        cmp_op = "<" if variant == "STRICT" else "<="
        rows = _fetch(
            con,
            f"SELECT player_id, team, position, report_status, practice_status "
            f"FROM _injuries WHERE season = ? AND week = ? AND modified_on {cmp_op} ?",
            [season, week, cutoff_date],
        )
        out_by_team_pos: dict[tuple[str, str], int] = {}
        for pid, team, pos, report, practice in rows:
            if pid in ctx:
                ctx[pid].injury[variant] = report
                ctx[pid].practice[variant] = practice
            if report in ("Out", "Doubtful") and team and pos:
                key = (team, pos)
                out_by_team_pos[key] = out_by_team_pos.get(key, 0) + 1
        for c in ctx.values():
            if c.team and c.position:
                n = out_by_team_pos.get((c.team, c.position), 0)
                # A player listed Out himself should not count as his own competition.
                if c.injury.get(variant) in ("Out", "Doubtful"):
                    n -= 1
                c.teammates_out[variant] = max(0, n)


def attach_prior_depth_chart(
    con: duckdb.DuckDBPyConnection, season: int, week: int, ctx: dict[str, PlayerContext]
) -> None:
    """The player's depth-chart position in the **previous** week.

    The current week's chart is Class C -- `nflverse/depth_charts` carries no timestamp for
    2015-2024, so there is no way to show it was published before Friday. The previous week's
    chart unambiguously was, so that is what W5 uses. The distinction is the whole point of §9."""
    if week <= 1:
        return
    for pid, depth in _fetch(
        con,
        "SELECT player_id, min(depth_team) FROM _depth WHERE season = ? AND week = ? GROUP BY 1",
        [season, week - 1],
    ):
        if pid in ctx and depth is not None:
            ctx[pid].depth_team_prior = int(depth)


def attach_team_environment_delta(
    con: duckdb.DuckDBPyConnection, season: int, week: int, ctx: dict[str, PlayerContext]
) -> None:
    """Change in the team's lagged EPA between week w-1 and week w.

    Alpha already has the *level* (`team_epa_avg_last3`); this is the *change*, which a
    tree on the level alone cannot see, and which is the concrete version of "is the lagged
    team-environment representation insufficient?" (Part 10)."""
    if week <= 1:
        return
    prev = {
        t: float(v)
        for t, v in _fetch(
            con,
            "SELECT team, team_epa_avg_last3 FROM team_week_features WHERE season=? AND week=? "
            "AND team_epa_avg_last3 IS NOT NULL",
            [season, week - 1],
        )
    }
    for c in ctx.values():
        if c.team and c.team_epa_avg_last3 is not None and c.team in prev:
            c.team_epa_delta = c.team_epa_avg_last3 - prev[c.team]


def load_usage_points(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    points_per_reception: float = 1.0,
) -> dict[str, float]:
    """The week's usage-expected fantasy points. **Class D** -- post-game, diagnostic only.

    Used exclusively to build `ORACLE_USAGE`, which bounds what perfect *opportunity* foresight
    could buy. It must never reach a cohort definition or an explanatory variable, and a validity
    gate asserts that it does not.

    **ffopportunity publishes full PPR.** Verified rather than assumed: its `total_fantasy_points`
    differs from this repository's `fantasy_points_ppr` by a mean absolute **0.0124** over 4,686
    RB/WR/TE player-weeks, against 1.259 for Half-PPR and 2.512 for standard. A Half-PPR board
    therefore needs the reception credit removed, by exactly the identity W1 established for
    realized points (`points(r) = ppr - (1 - r) * receptions`) applied to the *expected* reception
    count. Ranking a Half-PPR board by a full-PPR usage score would over-rank high-volume
    receivers inside the one oracle that is supposed to be scoring-format neutral."""
    scale = 1.0 - float(points_per_reception)
    return {
        pid: float(pts) - scale * float(rec or 0.0)
        for pid, pts, rec in _fetch(
            con,
            "SELECT player_id, points_exp, receptions_exp FROM _usage "
            "WHERE season = ? AND week = ? AND points_exp IS NOT NULL",
            [season, week],
        )
    }
