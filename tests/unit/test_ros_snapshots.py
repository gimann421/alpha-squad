"""Snapshot panel construction: timing contract, target definition, missing/inconsistent data."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from alpha_squad.ros import snapshots as sn
from tests.unit.ros_fixtures import SEASON, gameday, make_inputs, make_schedule

pytestmark = pytest.mark.unit


def rows(inp, spec, **kw):
    return sn.build_snapshot_rows(inp, spec, **kw).set_index("gsis_id")


def test_features_use_only_games_before_the_scrape_date_target_only_after():
    inp, spec = make_inputs(scrape_week=8)
    r = rows(inp, spec)
    # AAA/BBB have a week-5 bye: weeks 1-7 minus bye = 6 past games; future = weeks 8..17 = 10 games
    assert r.loc["00-QA", "team_games_played"] == 6
    assert r.loc["00-QA", "apps"] == 6
    assert r.loc["00-QA", "n_remaining"] == 10
    assert r.loc["00-QC", "team_games_played"] == 7 and r.loc["00-QC", "n_remaining"] == 10
    # target = points in weeks 8..17 only
    st = inp.stats
    want = st[(st.player_id == "00-QB") & (st.week >= 8)]["pts"].sum()
    assert r.loc["00-QB", "y_total"] == pytest.approx(want)
    assert r.loc["00-QB", "y_apps"] == 10


def test_game_on_the_scrape_date_is_in_neither_features_nor_target():
    inp, spec = make_inputs(scrape_week=8)
    # move the scrape onto week 8's game day itself
    spec = sn.SnapshotSpec(spec.season, spec.week, gameday(8))
    inp.ecr["scrape_date"] = spec.scrape_date
    r = rows(inp, spec)
    assert r.loc["00-QB", "n_ambiguous_games"] == 1
    assert r.loc["00-QB", "team_games_played"] == 6  # weeks 1-7 minus the bye
    assert r.loc["00-QB", "n_remaining"] == 9  # weeks 9-17, week 8 excluded
    st = inp.stats
    assert r.loc["00-QB", "y_total"] == pytest.approx(
        st[(st.player_id == "00-QB") & (st.week >= 9)]["pts"].sum()
    )


def test_bye_weeks_reduce_remaining_games_not_points_per_game():
    inp, spec = make_inputs(scrape_week=3)
    r = rows(inp, spec)
    assert r.loc["00-QA", "n_remaining"] == 14  # weeks 3..17 minus bye week 5
    assert r.loc["00-QC", "n_remaining"] == 15


def test_missed_future_game_counts_as_zero_points_but_still_a_scheduled_game():
    inp, spec = make_inputs(scrape_week=8)
    inp.stats = inp.stats[~((inp.stats.player_id == "00-QB") & (inp.stats.week.between(10, 12)))]
    r = rows(inp, spec)
    assert r.loc["00-QB", "n_remaining"] == 10 and r.loc["00-QB", "y_apps"] == 7
    assert r.loc["00-QB", "y_rate"] == pytest.approx(r.loc["00-QB", "y_total"] / 10)


def test_unmapped_fantasypros_ids_are_dropped_not_guessed():
    inp, spec = make_inputs()
    inp.id_map.pop("1")
    assert "00-QB" not in rows(inp, spec).index


def test_player_with_no_stats_gets_nan_features_and_flags_not_zeros():
    inp, spec = make_inputs()
    inp.stats = inp.stats[inp.stats.player_id != "00-QC"]
    r = rows(inp, spec)
    assert r.loc["00-QC", "has_season_stats"] == 0.0
    assert np.isnan(r.loc["00-QC", "ppg_app"]) and r.loc["00-QC", "apps"] == 0


def test_incomplete_horizon_is_flagged_not_scored():
    sched = make_schedule(played_through=12)
    inp, spec = make_inputs()
    inp.schedule = sched
    r = sn.build_snapshot_rows(inp, spec)
    assert not r["target_complete"].any()


def test_select_snapshots_prefers_dates_without_games_and_skips_unavailable_weeks():
    sched = make_schedule()
    fri = gameday(8) - timedelta(days=2)
    on_game_day = gameday(9)
    specs = sn.select_snapshots([fri, on_game_day], sched, [SEASON], weeks=(8, 9, 10))
    assert [(s.week, s.scrape_date) for s in specs] == [
        (8, fri)
    ]  # week 9's only scrape is a game day; week 10 has none


def test_select_snapshots_takes_latest_clean_date_in_window():
    sched = make_schedule()
    early, late = gameday(8) - timedelta(days=5), gameday(8) - timedelta(days=2)
    specs = sn.select_snapshots([early, late], sched, [SEASON], weeks=(8,))
    assert specs[0].scrape_date == late


def test_id_map_drops_ambiguous_fantasypros_ids(tmp_path):
    p = tmp_path / "ids.csv"
    p.write_text("fantasypros_id,gsis_id\n1,A\n2,B\n2,C\n3,NA\n")
    assert sn.load_id_map(p) == {"1": "A"}


def test_team_aliases_are_normalised():
    assert (
        sn.norm_team("JAC") == "JAX" and sn.norm_team("LAR") == "LA" and sn.norm_team(None) is None
    )
