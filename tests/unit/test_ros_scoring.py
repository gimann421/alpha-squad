"""Configurable fantasy scoring (alpha_squad.ros.scoring)."""

from __future__ import annotations

import glob

import pandas as pd
import pytest

from alpha_squad.ros.scoring import ScoringRules, score_stat_lines

pytestmark = pytest.mark.unit


def _line(**kw):
    base = dict(
        position="QB",
        passing_yards=0,
        passing_tds=0,
        passing_interceptions=0,
        rushing_yards=0,
        rushing_tds=0,
        receptions=0,
        receiving_yards=0,
        receiving_tds=0,
        sack_fumbles_lost=0,
        rushing_fumbles_lost=0,
        receiving_fumbles_lost=0,
        completions=0,
        attempts=0,
    )
    base.update(kw)
    return pd.DataFrame([base])


def test_standard_qb_line_by_hand():
    df = _line(
        passing_yards=300, passing_tds=3, passing_interceptions=1, rushing_yards=20, rushing_tds=1
    )
    # 300*.04 + 3*4 - 2 + 20*.1 + 6 = 12 + 12 - 2 + 2 + 6
    assert score_stat_lines(df, ScoringRules.nflverse_standard())[0] == pytest.approx(30.0)


def test_ppr_and_half_ppr_receptions():
    df = _line(position="WR", receptions=6, receiving_yards=80, receiving_tds=1)
    assert score_stat_lines(df, ScoringRules.nflverse_standard())[0] == pytest.approx(14.0)
    assert score_stat_lines(df, ScoringRules(rec=0.5))[0] == pytest.approx(17.0)
    assert score_stat_lines(df, ScoringRules.nflverse_ppr())[0] == pytest.approx(20.0)


def test_te_premium_applies_only_to_tight_ends():
    wr = _line(position="WR", receptions=4)
    te = _line(position="TE", receptions=4)
    r = ScoringRules(rec=1.0, te_premium=0.5)
    assert score_stat_lines(wr, r)[0] == pytest.approx(4.0)
    assert score_stat_lines(te, r)[0] == pytest.approx(6.0)


def test_passing_td_value_yard_bonus_and_interception_are_configurable():
    df = _line(passing_yards=410, passing_tds=2, passing_interceptions=2)
    r = ScoringRules(pass_td=6.0, pass_int=-3.0, pass_300_bonus=3.0, pass_400_bonus=2.0)
    assert score_stat_lines(df, r)[0] == pytest.approx(410 * 0.04 + 12 - 6 + 3 + 2)


def test_fumbles_lost_and_two_point_conversions():
    df = _line(sack_fumbles_lost=1, rushing_fumbles_lost=1, passing_2pt_conversions=1)
    assert score_stat_lines(df, ScoringRules())[0] == pytest.approx(-4.0 + 2.0)


def test_missing_columns_score_zero_rather_than_raise():
    assert score_stat_lines(
        pd.DataFrame([{"position": "QB", "passing_yards": 100}]), ScoringRules()
    )[0] == pytest.approx(4.0)


def test_from_league_reads_ppr_value_and_overrides():
    class L:
        scoring = {"ppr": True, "ppr_value": 0.5, "pass_td": 6}

    r = ScoringRules.from_league(L())
    assert (r.rec, r.pass_td) == (0.5, 6.0)
    assert ScoringRules.from_league({"scoring": {"ppr": True}}).rec == 1.0
    assert ScoringRules.from_league({"scoring": {}}).rec == 0.0


@pytest.mark.skipif(
    not glob.glob("data/raw/nflverse/stats_player_week/*/season-2024*"),
    reason="raw nflverse data not present",
)
def test_reproduces_nflverse_columns_exactly_on_real_data():
    import duckdb

    f = glob.glob("data/raw/nflverse/stats_player_week/*/season-2024*")[0]
    df = duckdb.connect().execute(f"select * from '{f}' where season_type='REG'").df()
    assert (
        score_stat_lines(df, ScoringRules.nflverse_standard()) - df["fantasy_points"]
    ).abs().max() < 1e-9
    assert (
        score_stat_lines(df, ScoringRules.nflverse_ppr()) - df["fantasy_points_ppr"]
    ).abs().max() < 1e-9
