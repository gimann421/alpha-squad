"""Leak-safe (season, snapshot, QB) panel for the midseason ROS question (D116).

One row = one quarterback listed in FantasyPros' ``ros-qb`` consensus on one archived scrape date,
with (a) the consensus itself, (b) everything about his season that was *already played* before
that scrape date, and (c) the realized fantasy points over the games played *after* it.

Timing contract (the part that makes the backtest honest)
---------------------------------------------------------
* A snapshot has a ``scrape_date`` ``d`` (the archive stores a date, not a time). Games are split
  by their ``gameday`` against ``d``:

      gameday <  d   -> PAST    : may be used to build features
      gameday >  d   -> FUTURE  : the target (through ``horizon_week``)
      gameday == d   -> AMBIGUOUS: excluded from BOTH. The archive does not say whether the scrape
                                   ran before or after kickoff, so the game is neither known nor
                                   forecast. Counted in ``n_ambiguous_games``.

  This is why the archive's Friday scrapes (which follow Thursday night football) are handled
  correctly: the Thursday game is PAST, the Sunday/Monday games are FUTURE.
* ``select_snapshots`` chooses at most ONE scrape per (season, NFL week), preferring a scrape that
  does not fall on a game day. NFL "snapshot week W" means: after week W-1's last game and before
  week W's last game.
* Every feature is computed by ``_past`` -- the single choke point that filters to
  ``gameday < d`` -- and ``tests/leakage/test_ros_leakage.py`` perturbs all post-``d`` data and
  asserts the features do not move.
* The target counts a QB's points in every future game he appears in; a game he misses
  contributes 0 (a manager who holds an injured QB gets 0 from that slot), and ``n_remaining`` is
  the number of REG-season games his team has left, so byes are respected.

What the archive is and is not
------------------------------
Source: DynastyProcess ``db_fpecr.parquet`` (the file nflreadr's ``load_ff_rankings`` reads),
FantasyPros page ``/nfl/rankings/ros-qb.php`` (``ecr_type='rp'``, ``page_type='redraft-qb'``;
before 2020-10-16 the same page is mirrored under the label ``ros-qb``). It is a *rank* archive:
there are NO ROS point projections, NO per-expert ranks, and NO timestamps finer than a day in it.
Scrapes were taken on Fridays (2020: mixed Thu/Fri). Pre-2020-09 history does not exist for ROS QB
(first scrape 2019-12-27), so the usable backtest is the 2020-2025 seasons.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from alpha_squad.ros.scoring import ScoringRules, score_stat_lines

ECR_PAGES = ("/nfl/rankings/ros-qb.php", "ros-qb")
#: FantasyPros / nflverse-stats team code -> nfldata schedule code.
TEAM_ALIAS = {"JAC": "JAX", "LAR": "LA", "OAK": "LV", "WSH": "WAS", "ARZ": "ARI", "SD": "LAC"}
DEFAULT_HORIZON_WEEK = 17  # standard fantasy championship week; week 18 is not a fantasy week
SHORT_HORIZON_WEEK = 14  # end of a standard regular season (sensitivity)
DEFAULT_WEEKS = (6, 7, 8, 9, 10)
MAX_RANK_KEPT = (
    36  # QBs below ECR 36 are never a realistic trade/waiver decision in a 10-12 team league
)
PRIOR_SHRINK_GAMES = 4.0


def norm_team(t: str | None) -> str | None:
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    return TEAM_ALIAS.get(t, t)


# --------------------------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------------------------
def load_schedule(path: str | Path) -> pd.DataFrame:
    """Team-view schedule: one row per (game, team). Scores are present only for played games."""
    g = pd.read_csv(
        path,
        usecols=lambda c: (
            c
            in {
                "game_id",
                "season",
                "game_type",
                "week",
                "gameday",
                "gametime",
                "away_team",
                "home_team",
                "away_score",
                "home_score",
            }
        ),
    )
    g = g[g["game_type"] == "REG"].copy()
    g["gameday"] = pd.to_datetime(g["gameday"]).dt.date
    home = g.assign(
        team=g.home_team, opp=g.away_team, pts_for=g.home_score, pts_against=g.away_score
    )
    away = g.assign(
        team=g.away_team, opp=g.home_team, pts_for=g.away_score, pts_against=g.home_score
    )
    cols = [
        "game_id",
        "season",
        "week",
        "gameday",
        "gametime",
        "team",
        "opp",
        "pts_for",
        "pts_against",
    ]
    out = pd.concat([home[cols], away[cols]], ignore_index=True)
    out["team"] = out["team"].map(lambda t: norm_team(t))
    out["opp"] = out["opp"].map(lambda t: norm_team(t))
    return out.sort_values(["season", "week", "team"]).reset_index(drop=True)


def load_ecr_qb(path: str | Path) -> pd.DataFrame:
    """Every archived ROS-QB consensus row (all scrape dates)."""
    con = duckdb.connect()
    pages = ", ".join(f"'{p}'" for p in ECR_PAGES)
    df = con.execute(
        f"""
        SELECT CAST(scrape_date AS DATE) AS scrape_date, id AS fp_id, player, pos, team,
               ecr, sd, best, worst, ecr_type, page_type, fp_page
        FROM read_parquet('{path}')
        WHERE fp_page IN ({pages}) AND pos = 'QB' AND ecr IS NOT NULL
        """
    ).df()
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    df["team"] = df["team"].map(norm_team)
    return df


def describe_ecr_archive(ecr: pd.DataFrame) -> dict:
    """Coverage facts about the loaded ECR archive (reported, never assumed)."""
    d = pd.to_datetime(ecr["scrape_date"])
    per = ecr.groupby("scrape_date").size()
    return {
        "first_scrape": str(min(ecr["scrape_date"])),
        "last_scrape": str(max(ecr["scrape_date"])),
        "n_scrapes": int(per.shape[0]),
        "n_rows": int(len(ecr)),
        "scrapes_by_year": {
            int(y): int(n) for y, n in d.dt.year.value_counts().sort_index().items()
        },
        "weekday_counts": {
            int(k): int(v) for k, v in d.dt.dayofweek.value_counts().sort_index().items()
        },
        "ecr_type": sorted(ecr["ecr_type"].unique().tolist()),
        "page_type": sorted(ecr["page_type"].unique().tolist()),
        "has_point_projections": False,
        "has_expert_level_ranks": False,
    }


def load_id_map(path: str | Path) -> dict[str, str]:
    """FantasyPros id -> gsis id. Ambiguous ids (one FP id, several gsis ids) are dropped, never
    resolved by name."""
    ids = pd.read_csv(path, dtype=str, na_values=["NA"], usecols=["fantasypros_id", "gsis_id"])
    ids = ids.dropna()
    n = ids.groupby("fantasypros_id")["gsis_id"].nunique()
    ok = n[n == 1].index
    ids = ids[ids["fantasypros_id"].isin(ok)].drop_duplicates()
    return dict(zip(ids["fantasypros_id"], ids["gsis_id"], strict=True))


def load_weekly_stats(paths: dict[int, str | Path]) -> pd.DataFrame:
    con = duckdb.connect()
    frames = []
    for _season, p in sorted(paths.items()):
        frames.append(
            con.execute(f"SELECT * FROM read_parquet('{p}') WHERE season_type = 'REG'").df()
        )
    df = pd.concat(frames, ignore_index=True)
    df["team"] = df["team"].map(norm_team)
    df["opponent_team"] = df["opponent_team"].map(norm_team)
    return df


_PBP_PLAYER_SQL = """
WITH p AS (
  SELECT game_id, week, posteam, passer_player_id, rusher_player_id, yardline_100, epa,
         qb_dropback, qb_scramble, qb_kneel, qb_spike, pass_attempt, rush_attempt, sack
  FROM read_parquet('{path}') WHERE season_type = 'REG' AND posteam IS NOT NULL
)
SELECT game_id, week, passer_player_id AS player_id,
       count(*) FILTER (WHERE pass_attempt = 1 AND yardline_100 <= 20) AS rz20_pass_att,
       count(*) FILTER (WHERE pass_attempt = 1 AND yardline_100 <= 10) AS rz10_pass_att,
       count(*) FILTER (WHERE qb_dropback = 1) AS dropbacks,
       0 AS designed_rush, 0 AS scrambles, 0 AS gl_rush, 0 AS rz10_rush
FROM p WHERE passer_player_id IS NOT NULL GROUP BY 1,2,3
UNION ALL
SELECT game_id, week, rusher_player_id AS player_id,
       0, 0, 0,
       count(*) FILTER (WHERE rush_attempt = 1 AND qb_scramble = 0 AND qb_kneel = 0 AND qb_spike = 0),
       count(*) FILTER (WHERE qb_scramble = 1),
       count(*) FILTER (WHERE rush_attempt = 1 AND yardline_100 <= 5 AND qb_kneel = 0),
       count(*) FILTER (WHERE rush_attempt = 1 AND yardline_100 <= 10 AND qb_kneel = 0)
FROM p WHERE rusher_player_id IS NOT NULL GROUP BY 1,2,3
"""

_PBP_TEAM_SQL = """
SELECT game_id, week, posteam AS team,
       count(*) FILTER (WHERE (pass_attempt = 1 OR rush_attempt = 1 OR sack = 1)
                        AND qb_kneel = 0 AND qb_spike = 0) AS plays,
       count(*) FILTER (WHERE qb_dropback = 1) AS dropbacks,
       avg(epa) FILTER (WHERE (pass_attempt = 1 OR rush_attempt = 1 OR sack = 1)
                        AND qb_kneel = 0 AND qb_spike = 0) AS epa_play
FROM read_parquet('{path}') WHERE season_type = 'REG' AND posteam IS NOT NULL GROUP BY 1,2,3
"""


def load_pbp_tables(paths: dict[int, str | Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player-game red-zone/rush-type table, team-game plays/pass-rate/EPA table) from pbp."""
    con = duckdb.connect()
    players, teams = [], []
    for season, p in sorted(paths.items()):
        pl = con.execute(_PBP_PLAYER_SQL.format(path=p)).df().assign(season=season)
        pl = pl.groupby(["season", "week", "player_id"], as_index=False).sum(numeric_only=True)
        players.append(pl)
        tm = con.execute(_PBP_TEAM_SQL.format(path=p)).df().assign(season=season)
        tm["team"] = tm["team"].map(norm_team)
        teams.append(tm)
    return pd.concat(players, ignore_index=True), pd.concat(teams, ignore_index=True)


def load_injuries(paths: dict[int, str | Path]) -> pd.DataFrame:
    """QB injury-report rows. ``date_modified`` is absent in some seasons' files; where it is
    missing the row is only ever used for weeks strictly before the snapshot week (see
    ``build_snapshot_rows``), never for the current week."""
    con = duckdb.connect()
    frames = []
    for _season, p in sorted(paths.items()):
        cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()}
        dm = "date_modified" if "date_modified" in cols else "NULL"
        frames.append(
            con.execute(
                f"""SELECT season, week, gsis_id, report_status, {dm} AS date_modified
                    FROM read_parquet('{p}') WHERE game_type = 'REG' AND position = 'QB'"""
            ).df()
        )
    df = pd.concat(frames, ignore_index=True)
    mod = pd.to_datetime(df["date_modified"], utc=True, errors="coerce")
    df["modified_date"] = mod.dt.date
    df.loc[mod.isna(), "modified_date"] = None
    return df


# --------------------------------------------------------------------------------------------
# snapshot selection
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SnapshotSpec:
    season: int
    week: int
    scrape_date: date


def select_snapshots(
    ecr_dates: list[date], schedule: pd.DataFrame, seasons: list[int], weeks=DEFAULT_WEEKS
) -> list[SnapshotSpec]:
    """At most one archived scrape per (season, week W): strictly after week W-1's last game day,
    strictly before week W's last game day, preferring a date with no NFL game on it, latest first.
    A (season, week) with no clean candidate is skipped (reported by the caller), never forced."""
    last_day = schedule.groupby(["season", "week"])["gameday"].max()
    game_days = schedule.groupby("season")["gameday"].apply(set)
    out: list[SnapshotSpec] = []
    for s in seasons:
        for w in weeks:
            if (s, w) not in last_day.index or (s, w - 1) not in last_day.index:
                continue
            lo, hi = last_day[(s, w - 1)], last_day[(s, w)]
            cands = sorted(d for d in ecr_dates if lo < d < hi and d not in game_days[s])
            if cands:
                out.append(SnapshotSpec(s, w, cands[-1]))
    return out


# --------------------------------------------------------------------------------------------
# panel builder
# --------------------------------------------------------------------------------------------
@dataclass
class RosInputs:
    ecr: pd.DataFrame
    id_map: dict[str, str]
    schedule: pd.DataFrame
    stats: pd.DataFrame
    pbp_player: pd.DataFrame
    pbp_team: pd.DataFrame
    injuries: pd.DataFrame
    rules: ScoringRules
    provenance: dict = field(default_factory=dict)


def _past(df: pd.DataFrame, d: date, col: str = "gameday") -> pd.DataFrame:
    """THE leakage choke point: rows from games played strictly before the scrape date."""
    return df[df[col] < d]


def prepare_inputs(
    ecr: pd.DataFrame,
    id_map: dict[str, str],
    schedule: pd.DataFrame,
    stats: pd.DataFrame,
    pbp_player: pd.DataFrame,
    pbp_team: pd.DataFrame,
    injuries: pd.DataFrame,
    rules: ScoringRules,
    provenance: dict | None = None,
) -> RosInputs:
    """Attach scoring + game dates to the weekly stat lines once."""
    st = stats.copy()
    st["pts"] = score_stat_lines(st, rules)
    st["appeared"] = (st[["attempts", "carries"]].fillna(0).sum(axis=1) > 0).astype(int)
    sched_key = schedule[["season", "week", "team", "gameday", "opp"]].rename(
        columns={"opp": "sched_opp"}
    )
    st = st.merge(sched_key, on=["season", "week", "team"], how="left")
    missing_dates = int(st["gameday"].isna().sum())
    st = st.dropna(subset=["gameday"]).copy()
    prov = dict(provenance or {})
    prov["stat_rows_without_schedule_date"] = missing_dates
    return RosInputs(ecr, id_map, schedule, st, pbp_player, pbp_team, injuries, rules, prov)


def _opp_allowed(inp: RosInputs, season: int, d: date) -> tuple[dict[str, float], float]:
    """Shrunk QB fantasy points allowed per game by each defense, from past games only."""
    st = _past(inp.stats[(inp.stats["season"] == season) & (inp.stats["position"] == "QB")], d)
    st = st[st["attempts"].fillna(0) >= 5]
    per_game = st.groupby(["opponent_team", "week"], as_index=False)["pts"].sum()
    lg = float(per_game["pts"].mean()) if len(per_game) else float("nan")
    out: dict[str, float] = {}
    for team, grp in per_game.groupby("opponent_team"):
        n = len(grp)
        out[team] = (n * grp["pts"].mean() + PRIOR_SHRINK_GAMES * lg) / (n + PRIOR_SHRINK_GAMES)
    return out, lg


def _team_asof(inp: RosInputs, season: int, d: date, live: bool = False) -> pd.DataFrame:
    sch = inp.schedule[inp.schedule["season"] == season]
    if live:
        sch = sch[sch["pts_for"].notna()]
    past = _past(sch, d)
    tg = inp.pbp_team[inp.pbp_team["season"] == season].merge(
        past[["week", "team", "pts_for"]], on=["week", "team"], how="inner"
    )
    g = tg.groupby("team").agg(
        team_plays_pg=("plays", "mean"),
        team_epa_play=("epa_play", "mean"),
        team_ppg=("pts_for", "mean"),
        _db=("dropbacks", "sum"),
        _pl=("plays", "sum"),
    )
    g["team_pass_rate"] = g["_db"] / g["_pl"]
    return g.drop(columns=["_db", "_pl"])


def _qb_features(rows: pd.DataFrame, pbp: pd.DataFrame) -> dict[str, float]:
    """Season-to-date features from one QB's PAST stat lines (already filtered)."""
    r = rows[rows["appeared"] == 1].sort_values("gameday")
    n = len(r)
    nan = float("nan")
    f: dict[str, float] = {"apps": n}
    if n == 0:
        return f
    att = r["attempts"].fillna(0)
    sacks = r["sacks_suffered"].fillna(0)
    db = att.sum() + sacks.sum()
    f.update(
        pts_total=float(r["pts"].sum()),
        ppg_app=float(r["pts"].mean()),
        last1=float(r["pts"].iloc[-1]),
        last3=float(r["pts"].tail(3).mean()),
        last5=float(r["pts"].tail(5).mean()),
        pts_sd=float(r["pts"].std(ddof=1)) if n > 1 else nan,
        att_pg=float(att.mean()),
        cmp_pct=float(r["completions"].fillna(0).sum() / att.sum()) if att.sum() else nan,
        ypa=float(r["passing_yards"].fillna(0).sum() / att.sum()) if att.sum() else nan,
        pass_td_pg=float(r["passing_tds"].fillna(0).mean()),
        int_pg=float(r["passing_interceptions"].fillna(0).mean()),
        sack_rate=float(sacks.sum() / db) if db else nan,
        air_per_att=float(r["passing_air_yards"].fillna(0).sum() / att.sum()) if att.sum() else nan,
        epa_db=float(r["passing_epa"].fillna(0).sum() / db) if db else nan,
        cpoe=float((r["passing_cpoe"].fillna(0) * att).sum() / att.sum()) if att.sum() else nan,
        rush_att_pg=float(r["carries"].fillna(0).mean()),
        rush_yds_pg=float(r["rushing_yards"].fillna(0).mean()),
        rush_td_pg=float(r["rushing_tds"].fillna(0).mean()),
        rush_pts_pg=float(
            (r["rushing_yards"].fillna(0) * 0.1 + r["rushing_tds"].fillna(0) * 6.0).mean()
        ),
        started_share=float((att >= 15).mean()),
    )
    if len(pbp):
        keyed = r[["season", "week"]].merge(pbp, on=["season", "week"], how="left")
        f.update(
            rz20_pass_pg=float(keyed["rz20_pass_att"].fillna(0).mean()),
            gl_rush_pg=float(keyed["gl_rush"].fillna(0).mean()),
            rz10_rush_pg=float(keyed["rz10_rush"].fillna(0).mean()),
            scramble_pg=float(keyed["scrambles"].fillna(0).mean()),
            designed_rush_pg=float(keyed["designed_rush"].fillna(0).mean()),
        )
    return f


def build_snapshot_rows(
    inp: RosInputs,
    spec: SnapshotSpec,
    *,
    horizon_week: int = DEFAULT_HORIZON_WEEK,
    live_today: date | None = None,
) -> pd.DataFrame:
    """All panel rows for one snapshot.

    Historical mode (``live_today=None``): features use games with ``gameday < scrape_date``,
    the target uses ``gameday > scrape_date``.

    Live mode (``live_today`` given): the ECR is the archived scrape at ``spec.scrape_date``, but
    the *features* use every game with a recorded result up to and including ``live_today``
    (newer than the ECR when results landed after the scrape), and the unplayed remainder of the
    schedule defines ``n_remaining``. Targets are NaN -- the future has not happened. The ECR's
    age is recorded in ``ecr_age_days`` so staleness is visible, not hidden.
    """
    s, w, d = spec.season, spec.week, spec.scrape_date
    live = live_today is not None
    cutoff = (live_today + timedelta(days=1)) if live else d  # `_past` keeps gameday < cutoff
    ecr = inp.ecr[inp.ecr["scrape_date"] == d].copy()
    ecr["gsis_id"] = ecr["fp_id"].map(inp.id_map)
    ecr = ecr.dropna(subset=["gsis_id"])
    ecr = ecr.sort_values(["ecr", "best", "fp_id"]).reset_index(drop=True)
    ecr["ecr_rank"] = np.arange(1, len(ecr) + 1)
    ecr = ecr[ecr["ecr_rank"] <= MAX_RANK_KEPT]

    sch_s = inp.schedule[inp.schedule["season"] == s]
    if live:
        played = sch_s["pts_for"].notna()
        past_sch = _past(sch_s[played], cutoff)
        fut_sch = sch_s[~played & (sch_s["week"] <= horizon_week)]
        amb = sch_s.iloc[0:0]
    else:
        past_sch = _past(sch_s, d)
        fut_sch = sch_s[(sch_s["gameday"] > d) & (sch_s["week"] <= horizon_week)]
        amb = sch_s[sch_s["gameday"] == d]
    fut_short = fut_sch[fut_sch["week"] <= SHORT_HORIZON_WEEK]
    fut_played = fut_sch[fut_sch["pts_for"].notna()] if not live else fut_sch.iloc[0:0]
    fut_played_by_team = fut_played.groupby("team").size()
    n_played_by_team = past_sch.groupby("team").size()
    fut_by_team = {t: g for t, g in fut_sch.groupby("team")}

    opp_allowed, lg_allowed = _opp_allowed(inp, s, cutoff)
    team_env = _team_asof(inp, s, cutoff, live=live)

    st_all = inp.stats
    cur = _past(st_all[st_all["season"] == s], cutoff)
    prev = st_all[st_all["season"] == s - 1]
    fut_stats = st_all[
        (st_all["season"] == s) & (st_all["gameday"] > cutoff) & (st_all["week"] <= horizon_week)
    ]
    if live:
        fut_stats = fut_stats.iloc[0:0]
    inj_s = inp.injuries[inp.injuries["season"] == s]
    known_before = inj_s["modified_date"].map(lambda m: m is not None and m == m and m < cutoff)
    inj = inj_s[(inj_s["week"] < w) | known_before]
    ecr_age = (live_today - d).days if live else 0

    # target completeness: every REG game through the horizon has a recorded result
    horizon_games = sch_s[sch_s["week"] <= horizon_week]
    target_complete = (
        bool(horizon_games["pts_for"].notna().all()) if len(horizon_games) and not live else False
    )

    recs = []
    for r in ecr.itertuples(index=False):
        gid = r.gsis_id
        team = r.team
        rows = cur[cur["player_id"] == gid]
        feats = _qb_features(
            rows,
            inp.pbp_player[(inp.pbp_player["season"] == s) & (inp.pbp_player["player_id"] == gid)],
        )
        team_games = int(n_played_by_team.get(team, 0)) if team else 0
        fg = fut_by_team.get(team)
        n_rem = int(len(fg)) if fg is not None else 0
        rem_opps = list(fg["opp"]) if fg is not None else []
        sched_adj = (
            float(np.mean([opp_allowed.get(o, lg_allowed) for o in rem_opps]) - lg_allowed)
            if rem_opps and not np.isnan(lg_allowed)
            else float("nan")
        )
        pv = prev[(prev["player_id"] == gid) & (prev["appeared"] == 1)]
        fs = fut_stats[fut_stats["player_id"] == gid]
        fs_short = fs[fs["week"] <= SHORT_HORIZON_WEEK]
        last_team = rows["team"].iloc[-1] if len(rows) else None
        ij = inj[inj["gsis_id"] == gid]
        ij_prev = ij[ij["week"] == w - 1]
        ij_cur = ij[ij["week"] == w]
        env = team_env.loc[team] if team in team_env.index else None
        rec = dict(
            season=s,
            snapshot_week=w,
            scrape_date=d,
            gsis_id=gid,
            fp_id=r.fp_id,
            player=r.player,
            position="QB",
            team=team,
            ecr=float(r.ecr),
            ecr_rank=int(r.ecr_rank),
            ecr_sd=r.sd,
            ecr_best=r.best,
            ecr_worst=r.worst,
            ecr_type=r.ecr_type,
            page_type=r.page_type,
            fp_page=r.fp_page,
            n_ecr_listed=int(len(ecr)),
            team_games_played=team_games,
            n_remaining=n_rem,
            n_remaining_w14=int((fut_short["team"] == team).sum()),
            n_future_played=int(fut_played_by_team.get(team, 0)),
            n_ambiguous_games=int((amb["team"] == team).sum()),
            games_missed=max(team_games - feats.get("apps", 0), 0),
            team_changed=float(last_team is not None and team is not None and last_team != team),
            has_season_stats=float(feats.get("apps", 0) > 0),
            sched_adj=sched_adj,
            ppg_prev=float(pv["pts"].mean()) if len(pv) else float("nan"),
            apps_prev=float(len(pv)),
            att_pg_prev=float(pv["attempts"].fillna(0).mean()) if len(pv) else float("nan"),
            rush_att_pg_prev=float(pv["carries"].fillna(0).mean()) if len(pv) else float("nan"),
            inj_prev_flag=float(
                len(ij_prev) > 0 and ij_prev["report_status"].isin(["Out", "Doubtful"]).any()
            ),
            inj_prev_any=float(len(ij_prev) > 0 and ij_prev["report_status"].notna().any()),
            inj_cur_flag=float(
                len(ij_cur) > 0 and ij_cur["report_status"].isin(["Out", "Doubtful"]).any()
            ),
            inj_weeks_listed=float(ij["report_status"].notna().sum()),
            target_complete=target_complete,
            ecr_age_days=ecr_age,
            y_total=float(fs["pts"].sum()),
            y_apps=float(fs["appeared"].sum()),
            y_total_w14=float(fs_short["pts"].sum()),
            y_apps_w14=float(fs_short["appeared"].sum()),
        )
        rec.update(feats)
        if env is not None:
            rec.update(
                team_plays_pg=env["team_plays_pg"],
                team_epa_play=env["team_epa_play"],
                team_ppg=env["team_ppg"],
                team_pass_rate=env["team_pass_rate"],
            )
        recs.append(rec)
    df = pd.DataFrame(recs)
    if live and len(df):
        for c in ("y_total", "y_apps", "y_total_w14", "y_apps_w14"):
            df[c] = np.nan
    if len(df):
        df["y_rate"] = np.where(
            df["n_remaining"] > 0, df["y_total"] / df["n_remaining"].clip(lower=1), np.nan
        )
        df["y_rate_w14"] = np.where(
            df["n_remaining_w14"] > 0,
            df["y_total_w14"] / df["n_remaining_w14"].clip(lower=1),
            np.nan,
        )
    return df


def build_panel(
    inp: RosInputs,
    specs: list[SnapshotSpec],
    *,
    horizon_week: int = DEFAULT_HORIZON_WEEK,
    live_today: date | None = None,
) -> pd.DataFrame:
    frames = [
        build_snapshot_rows(inp, sp, horizon_week=horizon_week, live_today=live_today)
        for sp in specs
    ]
    panel = pd.concat([f for f in frames if len(f)], ignore_index=True)
    panel["scoring_hash"] = hashlib.sha256(
        json.dumps(inp.rules.describe(), sort_keys=True).encode()
    ).hexdigest()[:12]
    panel["horizon_week"] = horizon_week
    return panel
