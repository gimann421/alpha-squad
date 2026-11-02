"""All-position ROS snapshots (QB/RB/WR/TE) for roster-level evaluation (Model F).

The roster-level backtest needs (a) a *market price* for every player so trades can be priced the
way a league would price them, (b) an expected-value input for the non-QB assets a QB trade
gives up, and (c) the realized week-by-week points of everyone, so a roster's lineup can be
scored on what actually happened. The ``ros-ppr-overall`` board of the same archive supplies (a)
and (b); nflverse weekly lines supply (c).

Same timing contract as ``snapshots``: the board is the archived scrape on ``scrape_date``;
realized points are counted only for games with ``gameday > scrape_date`` through the horizon week.
"""

from __future__ import annotations

from datetime import date

import duckdb
import numpy as np
import pandas as pd

from alpha_squad.ros.snapshots import (
    DEFAULT_HORIZON_WEEK,
    RosInputs,
    SnapshotSpec,
    norm_team,
)

OVERALL_PAGES = ("/nfl/rankings/ros-ppr-overall.php", "ros-ppr-overall")
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
#: depth of each position kept on the board (deeper than any 10-12 team league rosters)
SKILL_DEPTH = {"QB": 24, "RB": 60, "WR": 72, "TE": 30}


def load_ecr_overall(path) -> pd.DataFrame:
    con = duckdb.connect()
    pages = ", ".join(f"'{p}'" for p in OVERALL_PAGES)
    df = con.execute(
        f"""SELECT CAST(scrape_date AS DATE) AS scrape_date, id AS fp_id, player, pos, team,
                   ecr, sd, best, worst
            FROM read_parquet('{path}')
            WHERE fp_page IN ({pages}) AND pos IN ('QB','RB','WR','TE') AND ecr IS NOT NULL"""
    ).df()
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    df["team"] = df["team"].map(norm_team)
    return df


def build_skill_snapshot(
    inp: RosInputs,
    overall: pd.DataFrame,
    spec: SnapshotSpec,
    *,
    horizon_week: int = DEFAULT_HORIZON_WEEK,
    live_today: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(players, weekly): one row per board player; and one row per (player, future NFL week).

    ``weekly`` has a row for every *scheduled* future team game: ``pts`` is the realized points
    (0 if he did not play) and ``played`` flags appearance; weeks with no row for a team are
    byes. In live mode ``pts`` is NaN (nothing has happened yet)."""
    s, d = spec.season, spec.scrape_date
    live = live_today is not None
    b = overall[overall["scrape_date"] == d].copy()
    b["gsis_id"] = b["fp_id"].map(inp.id_map)
    b = b.dropna(subset=["gsis_id"]).sort_values(["ecr", "best", "fp_id"]).reset_index(drop=True)
    b["overall_rank"] = np.arange(1, len(b) + 1)
    b["pos_rank"] = b.groupby("pos").cumcount() + 1
    b = b[b.apply(lambda r: r["pos_rank"] <= SKILL_DEPTH[r["pos"]], axis=1)]

    sch = inp.schedule[inp.schedule["season"] == s]
    if live:
        fut = sch[sch["pts_for"].isna() & (sch["week"] <= horizon_week)]
    else:
        fut = sch[(sch["gameday"] > d) & (sch["week"] <= horizon_week)]
    fut_weeks = {t: sorted(g["week"].tolist()) for t, g in fut.groupby("team")}
    st = inp.stats[(inp.stats["season"] == s)]
    played_future = (
        st[(st["gameday"] > d) & (st["week"] <= horizon_week)] if not live else st.iloc[0:0]
    )
    key = played_future.set_index(["player_id", "week"])

    rows, wrows = [], []
    for r in b.itertuples(index=False):
        weeks = fut_weeks.get(r.team, [])
        tot, apps = 0.0, 0
        for wk in weeks:
            if (r.gsis_id, wk) in key.index:
                rec = key.loc[(r.gsis_id, wk)]
                pts = (
                    float(rec["pts"].sum()) if isinstance(rec, pd.DataFrame) else float(rec["pts"])
                )
                played = 1
            else:
                pts, played = (np.nan if live else 0.0), 0
            tot += 0.0 if live else pts
            apps += played
            wrows.append((s, spec.week, r.gsis_id, wk, pts, played))
        rows.append(
            dict(
                season=s,
                snapshot_week=spec.week,
                scrape_date=d,
                gsis_id=r.gsis_id,
                player=r.player,
                position=r.pos,
                team=r.team,
                overall_ecr=float(r.ecr),
                overall_rank=int(r.overall_rank),
                pos_rank=int(r.pos_rank),
                n_remaining=len(weeks),
                y_total=np.nan if live else tot,
                y_apps=np.nan if live else float(apps),
            )
        )
    players = pd.DataFrame(rows)
    weekly = pd.DataFrame(
        wrows, columns=["season", "snapshot_week", "gsis_id", "nfl_week", "pts", "played"]
    )
    if len(players):
        players["y_rate"] = players["y_total"] / players["n_remaining"].clip(lower=1)
    return players, weekly
