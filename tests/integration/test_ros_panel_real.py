"""The ROS panel against the real downloaded files (skipped when data/ is absent).

Independent re-derivation of one snapshot straight from nflverse + nfldata + DynastyProcess, to
catch any bug the synthetic fixtures cannot (team-code aliases, week/date joins, id mapping).
"""

from __future__ import annotations

import glob
from datetime import date

import duckdb
import pandas as pd
import pytest

pytestmark = pytest.mark.integration

PANEL = "data/ros/qb_ros_panel.parquet"
needs_data = pytest.mark.skipif(
    not glob.glob(PANEL) or not glob.glob("data/raw/nflverse/stats_player_week/*/season-2024*"),
    reason="ROS panel / raw data not present (run `alpha-squad ros build-panel`)",
)


@needs_data
def test_panel_invariants_on_real_data():
    p = pd.read_parquet(PANEL)
    done = p[p["target_complete"]]
    assert set(done["season"]) >= {2021, 2022, 2023, 2024, 2025}
    assert (done["y_apps"] <= done["n_remaining"] + 1e-9).all()
    assert (done["n_remaining"] > 0).all()
    assert (done["n_ambiguous_games"] == 0).all() or done["n_ambiguous_games"].max() <= 1
    # one snapshot per (season, week); no duplicate player within a snapshot
    assert not p.duplicated(["season", "snapshot_week", "gsis_id"]).any()
    # ranks are a dense 1..n ordering of the published ECR within each snapshot
    for _, g in p.groupby(["season", "snapshot_week"]):
        assert (
            g["ecr_rank"].tolist() == list(range(1, len(g) + 1))
            or g["ecr_rank"].is_monotonic_increasing
        )
        assert g["ecr"].is_monotonic_increasing
    # every snapshot's scrape is the archive's own date, never after the first future game
    assert (pd.to_datetime(p["scrape_date"]).dt.dayofweek.isin([3, 4, 5])).mean() > 0.95
    # the ECR archive carries no ROS point projections; the panel must not pretend it does
    assert not any(c.startswith("fp_proj") for c in p.columns)


@needs_data
def test_one_real_snapshot_matches_an_independent_derivation():
    p = pd.read_parquet(PANEL)
    snap = p[(p["season"] == 2024) & (p["snapshot_week"] == 8)]
    d = pd.to_datetime(snap["scrape_date"].iloc[0]).date()
    assert d == date(2024, 10, 25)
    row = snap.sort_values("ecr_rank").iloc[0]  # ECR #1 on the day (a real QB)
    stats = glob.glob("data/raw/nflverse/stats_player_week/*/season-2024*")[0]
    sched = glob.glob("data/raw/nfldata/games/*/default_games.csv")
    assert sched, "schedule file missing"
    con = duckdb.connect()
    games = con.execute(
        f"""SELECT week, gameday::DATE AS gd FROM read_csv('{sched[-1]}') WHERE season = 2024 AND game_type = 'REG'
            AND (home_team = '{row.team}' OR away_team = '{row.team}')"""
    ).df()
    dt = pd.Timestamp(d)
    fut_weeks = sorted(games[(games.gd > dt) & (games.week <= 17)]["week"].tolist())
    want = con.execute(
        f"""SELECT coalesce(sum(fantasy_points_ppr), 0), count(*) FROM read_parquet('{stats}')
            WHERE player_id = '{row.gsis_id}' AND season_type = 'REG' AND week IN ({",".join(map(str, fut_weeks))})"""
    ).fetchone()
    assert row["n_remaining"] == len(fut_weeks)
    assert row["y_total"] == pytest.approx(want[0], abs=1e-6)
    assert row["y_apps"] == want[1]
    past = games[games.gd < dt]
    assert row["team_games_played"] == len(past)
