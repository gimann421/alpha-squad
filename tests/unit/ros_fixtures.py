"""Synthetic, schema-accurate inputs for the ROS tests (no real data, fully offline)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from alpha_squad.ros import snapshots as sn
from alpha_squad.ros.scoring import ScoringRules

SEASON = 2024
SEASON_START = date(2024, 9, 8)  # a Sunday: week 1
TEAMS = ["AAA", "BBB", "CCC", "DDD"]
BYE = {"AAA": 5, "BBB": 5}


def gameday(week: int) -> date:
    return SEASON_START + timedelta(days=7 * (week - 1))


def make_schedule(weeks: int = 17, played_through: int = 17) -> pd.DataFrame:
    rows = []
    for w in range(1, weeks + 1):
        active = [t for t in TEAMS if BYE.get(t) != w]
        for i in range(0, len(active), 2):
            a, b = active[i], active[i + 1]
            played = w <= played_through
            for team, opp in ((a, b), (b, a)):
                rows.append(
                    dict(
                        game_id=f"{SEASON}_{w:02d}_{a}_{b}",
                        season=SEASON,
                        week=w,
                        gameday=gameday(w),
                        gametime="13:00",
                        team=team,
                        opp=opp,
                        pts_for=20.0 + w if played else np.nan,
                        pts_against=17.0 if played else np.nan,
                    )
                )
    return pd.DataFrame(rows)


def stat_line(
    pid, team, opp, week, pos="QB", att=30, yds=250, td=2, ints=1, carries=3, rush=15, **kw
):
    base = dict(
        player_id=pid,
        player_display_name=pid,
        position=pos,
        season=SEASON,
        week=week,
        season_type="REG",
        team=team,
        opponent_team=opp,
        completions=int(att * 0.65),
        attempts=att,
        passing_yards=yds,
        passing_tds=td,
        passing_interceptions=ints,
        sacks_suffered=2,
        sack_fumbles_lost=0,
        passing_air_yards=200,
        passing_epa=3.0,
        passing_cpoe=1.0,
        carries=carries,
        rushing_yards=rush,
        rushing_tds=0,
        rushing_fumbles_lost=0,
        receptions=0,
        targets=0,
        receiving_yards=0,
        receiving_tds=0,
        receiving_fumbles_lost=0,
        passing_2pt_conversions=0,
        rushing_2pt_conversions=0,
        receiving_2pt_conversions=0,
        special_teams_tds=0,
    )
    base.update(kw)
    return base


def make_stats(schedule: pd.DataFrame, qbs: dict[str, str], seed: int = 0) -> pd.DataFrame:
    """qbs: {gsis_id: team}. One stat line per team game; scores vary with a seeded RNG."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid, team in qbs.items():
        for r in schedule[schedule["team"] == team].itertuples():
            if pd.isna(r.pts_for):
                continue
            rows.append(
                stat_line(
                    pid,
                    team,
                    r.opp,
                    r.week,
                    att=int(rng.integers(22, 42)),
                    yds=int(rng.integers(150, 380)),
                    td=int(rng.integers(0, 4)),
                )
            )
    return pd.DataFrame(rows)


def make_inputs(scrape_week: int = 8, seed: int = 0) -> tuple[sn.RosInputs, sn.SnapshotSpec]:
    sched = make_schedule()
    qbs = {"00-QA": "AAA", "00-QB": "BBB", "00-QC": "CCC", "00-QD": "DDD"}
    stats = make_stats(sched, qbs, seed)
    d = gameday(scrape_week) - timedelta(days=2)  # the Friday before week `scrape_week`'s Sunday
    ecr = pd.DataFrame(
        [
            dict(
                scrape_date=d,
                fp_id=str(i),
                player=pid,
                pos="QB",
                team=team,
                ecr=float(i + 1),
                sd=1.0,
                best=float(i + 1),
                worst=float(i + 2),
                ecr_type="rp",
                page_type="redraft-qb",
                fp_page="/nfl/rankings/ros-qb.php",
            )
            for i, (pid, team) in enumerate(qbs.items())
        ]
    )
    id_map = {str(i): pid for i, pid in enumerate(qbs)}
    inj = pd.DataFrame(
        columns=["season", "week", "gsis_id", "report_status", "date_modified", "modified_date"]
    )
    pbp_p = pd.DataFrame(
        columns=[
            "season",
            "week",
            "player_id",
            "rz20_pass_att",
            "rz10_pass_att",
            "dropbacks",
            "designed_rush",
            "scrambles",
            "gl_rush",
            "rz10_rush",
        ]
    )
    pbp_t = pd.DataFrame(
        {
            "season": [SEASON] * 0,
            "week": [],
            "team": [],
            "plays": [],
            "dropbacks": [],
            "epa_play": [],
        }
    )
    inp = sn.prepare_inputs(
        ecr, id_map, sched, stats, pbp_p, pbp_t, inj, ScoringRules.nflverse_ppr()
    )
    return inp, sn.SnapshotSpec(SEASON, scrape_week, d)
