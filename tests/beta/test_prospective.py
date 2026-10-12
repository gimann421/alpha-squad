"""W16 prospective feature rows: production's builders over strictly-prior games, on synthetic
data shaped exactly like the production tables (schema from `init_db`)."""

from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd
import pytest

from alpha_squad.beta import prospective as pr
from alpha_squad.features.panel import build_player_week_features
from alpha_squad.features.team import (
    attach_team_features_to_player_panel,
    build_team_week_features,
)
from alpha_squad.storage.db import init_db

pytestmark = pytest.mark.leakage

TEAMS = ("AAA", "BBB")
PLAYERS = {"p_wr": ("WR", "AAA"), "p_rb": ("RB", "BBB"), "p_te": ("TE", "AAA")}


def _date(season: int, week: int) -> dt.date:
    return dt.date(season, 9, 7) + dt.timedelta(days=7 * (week - 1))


def _build(path: str, last_week_2026: int = 3, skip: set[tuple[str, int]] = frozenset()) -> None:
    con = duckdb.connect(path)
    init_db(con)
    for pid, (pos, _t) in sorted(PLAYERS.items()):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position) VALUES (?, ?, ?)",
            [pid, f"g_{pid}", pos],
        )
    con.execute(
        "INSERT INTO players (player_id, gsis_id, position) VALUES ('p_new', 'g_new', 'WR')"
    )
    for season, weeks in ((2025, range(1, 18)), (2026, range(1, last_week_2026 + 1))):
        for w in weeks:
            gid = f"{season}_{w:02d}_AAA_BBB"
            con.execute(
                "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, "
                "away_team) VALUES (?, ?, ?, 'REG', ?, 'AAA', 'BBB')",
                [gid, season, w, _date(season, w)],
            )
            for t in TEAMS:
                con.execute(
                    "INSERT INTO team_week_stats (team, season, week, game_id, game_date, plays, "
                    "pass_rate, passing_epa, rushing_epa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        t,
                        season,
                        w,
                        gid,
                        _date(season, w),
                        60 + w + (t == "BBB"),
                        0.5 + w / 100,
                        0.1 * w,
                        -0.05 * w,
                    ],
                )
            for n, (pid, (pos, team)) in enumerate(sorted(PLAYERS.items())):
                if (pid, w) in skip and season == 2026:
                    continue
                v = float(w + n + (season - 2025) * 3)
                con.execute(
                    "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, "
                    "team, position, targets, carries, receptions, target_share, "
                    "offense_snap_pct, fantasy_points, fantasy_points_ppr) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        pid,
                        season,
                        w,
                        gid,
                        _date(season, w),
                        team,
                        pos,
                        v,
                        v / 2,
                        v / 3,
                        v / 40,
                        0.5 + v / 100,
                        v,
                        v + v / 3,
                    ],
                )
    build_player_week_features(con)
    build_team_week_features(con)
    attach_team_features_to_player_panel(con)
    con.close()


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "src.duckdb")
    _build(path)
    return path


def _slots(week: int, ids=("p_new", "p_rb", "p_te", "p_wr")):
    pos = {**{k: v[0] for k, v in PLAYERS.items()}, "p_new": "WR"}
    team = {**{k: v[1] for k, v in PLAYERS.items()}, "p_new": "AAA"}
    return (
        [pr.PlayerSlot(p, pos[p], team[p], _date(2026, week)) for p in ids],
        [pr.TeamSlot(t, _date(2026, week)) for t in TEAMS],
    )


def test_prospective_rows_equal_production_rows_for_played_week(db):
    con = duckdb.connect(db, read_only=True)
    for week in (1, 2, 3):  # week 1 exercises cross-season windows
        r = pr.equivalence_check(con, 2026, week)
        assert r["exact"] and r["rows_compared"] == 3, r


def test_player_who_never_played_gets_a_row_not_dropped(db):
    con = duckdb.connect(db, read_only=True)
    players, teams = _slots(4)
    out = pr.prospective_feature_rows(con, 2026, 4, players, teams).set_index("player_id")
    assert set(out.index) == {"p_new", "p_rb", "p_te", "p_wr"}
    new = out.loc["p_new"]
    assert new["games_played_prior"] == 0 and pd.isna(new["fp_ppr_avg_last3"])
    assert not pd.isna(new["team_plays_avg_last3"])  # team environment still known
    assert out.loc["p_wr", "games_played_prior"] == 3


def test_prospective_week_needs_no_stats_row_for_that_week(db):
    """Week 4 has no game data at all in the source; the board still exists."""
    con = duckdb.connect(db, read_only=True)
    assert (
        con.execute(
            "SELECT count(*) FROM player_week_stats WHERE season=2026 AND week=4"
        ).fetchone()[0]
        == 0
    )
    players, teams = _slots(4)
    assert len(pr.prospective_feature_rows(con, 2026, 4, players, teams)) == 4


def test_week_and_later_outcomes_cannot_move_prospective_rows(tmp_path):
    """Same board built before and after weeks 3-5 are played: bit-identical week-3 rows."""
    early, late = str(tmp_path / "early.duckdb"), str(tmp_path / "late.duckdb")
    _build(early, last_week_2026=2)
    _build(late, last_week_2026=5)
    players, teams = _slots(3)
    a = pr.prospective_feature_rows(duckdb.connect(early, read_only=True), 2026, 3, players, teams)
    b = pr.prospective_feature_rows(duckdb.connect(late, read_only=True), 2026, 3, players, teams)
    pd.testing.assert_frame_equal(a, b)


def test_missed_game_player_keeps_history_and_stays_eligible(tmp_path):
    path = str(tmp_path / "skip.duckdb")
    _build(path, skip={("p_rb", 2), ("p_rb", 3)})  # injured: no stats rows for two weeks
    con = duckdb.connect(path, read_only=True)
    players, teams = _slots(4)
    out = pr.prospective_feature_rows(con, 2026, 4, players, teams).set_index("player_id")
    assert out.loc["p_rb", "games_played_prior"] == 1
    assert not pd.isna(out.loc["p_rb", "fp_ppr_avg_last3"])


def test_source_database_is_not_modified(db):
    con = duckdb.connect(db, read_only=True)
    before = con.execute(
        "SELECT count(*), sum(hash(player_id || week)) FROM player_week_features"
    ).fetchone()
    players, teams = _slots(4)
    pr.prospective_feature_rows(con, 2026, 4, players, teams)
    pr.equivalence_check(con, 2026, 3)
    after = con.execute(
        "SELECT count(*), sum(hash(player_id || week)) FROM player_week_features"
    ).fetchone()
    assert before == after


def test_duplicate_slots_rejected(db):
    con = duckdb.connect(db, read_only=True)
    players, teams = _slots(4, ids=("p_wr", "p_wr"))
    with pytest.raises(ValueError):
        pr.prospective_feature_rows(con, 2026, 4, players, teams)
