"""The weekly program's leakage boundary (W1).

`evaluation/weekly/snapshots.py` defines who may be ranked at a given cutoff. Everything the
weekly program measures is computed downstream of that universe, so a defect here is not
recoverable by any later care --- which puts these tests in the same category as
`test_player_week_features_leakage.py` (CLAUDE.md: "no future-data leakage").

These tests try to *disprove* the boundary rather than confirm it, per the adversarial posture
in ACCEPTANCE_CRITERIA.md / AGENT_CONTRACTS.md. The specific failure they are written against
is the real one W1 measured: a Friday board sits AFTER the Thursday night game, and 78 of the
90 canonical historical boards carry at least one player whose game had already kicked off.

All fixtures are synthetic and offline.
"""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from alpha_squad.evaluation.weekly.snapshots import (
    MAX_LEAD_DAYS,
    WeeklySnapshot,
    assign_snapshots,
    canonical_snapshots,
    dense_rank,
    eligible_board_rows,
    teams_already_playing,
)
from alpha_squad.storage.db import init_db

#: A synthetic week shaped like a real one: a Thursday game, then a Sunday slate.
THU = date(2024, 10, 3)
FRI = date(2024, 10, 4)
SUN = date(2024, 10, 6)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    rows = [
        ("g_thu", 2024, 5, "REG", THU, "THU_H", "THU_A"),
        ("g_sun1", 2024, 5, "REG", SUN, "SUN_H", "SUN_A"),
        ("g_sun2", 2024, 5, "REG", SUN, "OTH_H", "OTH_A"),
        # The following week, so snapshot assignment has something to be wrong about.
        ("g_w6_thu", 2024, 6, "REG", date(2024, 10, 10), "W6_H", "W6_A"),
        ("g_w6_sun", 2024, 6, "REG", date(2024, 10, 13), "W6_S", "W6_T"),
    ]
    for r in rows:
        connection.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            list(r),
        )
    yield connection
    connection.close()


class TestSnapshotAssignment:
    def test_friday_board_attaches_to_the_week_whose_sunday_follows_it(self, con):
        """The off-by-one this is written against: anchoring on the week's FIRST game
        (Thursday) would push a Friday board onto the following week and score it against the
        wrong week's outcomes entirely."""
        (snap,) = assign_snapshots(con, [FRI])
        assert (snap.season, snap.week) == (2024, 5)
        assert snap.lead_days == 2

    def test_a_board_scraped_after_the_sunday_slate_belongs_to_the_next_week(self, con):
        """A Monday board cannot rank a Sunday that already happened."""
        (snap,) = assign_snapshots(con, [date(2024, 10, 7)])
        assert (snap.season, snap.week) == (2024, 6)

    def test_a_board_with_no_sunday_within_the_window_is_dropped(self, con):
        """Never attach a board to a week it cannot plausibly be about. Silently stretching
        the window is how an August board would end up ranking week 5."""
        assert assign_snapshots(con, [date(2024, 8, 1)]) == []

    def test_lead_window_boundary_is_respected(self, con):
        """Exactly MAX_LEAD_DAYS is in; one more is out."""
        inside = SUN.toordinal() - MAX_LEAD_DAYS
        assert assign_snapshots(con, [date.fromordinal(inside)])
        assert assign_snapshots(con, [date.fromordinal(inside - 1)]) == []

    def test_only_regular_season_weeks_are_assignable(self, con):
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team)"
            " VALUES ('g_post', 2024, 19, 'POST', DATE '2025-01-12', 'P_H', 'P_A')"
        )
        assert all(s.week != 19 for s in assign_snapshots(con, [date(2025, 1, 10)]))


class TestCanonicalSnapshot:
    def test_one_snapshot_per_week_and_it_is_the_latest(self, con):
        """Four real weeks carry two vintages that both precede the same Sunday. Keeping both
        double-counts the week and mixes a Tuesday information set into a Friday series."""
        snaps = assign_snapshots(con, [date(2024, 10, 1), FRI])
        assert len(snaps) == 2
        (canon,) = canonical_snapshots(snaps)
        assert canon.scrape_date == FRI
        assert canon.lead_days == 2

    def test_distinct_weeks_are_both_kept(self, con):
        snaps = assign_snapshots(con, [FRI, date(2024, 10, 11)])
        assert [(s.season, s.week) for s in canonical_snapshots(snaps)] == [(2024, 5), (2024, 6)]


class TestAlreadyPlayedExclusion:
    def test_thursday_night_teams_are_excluded_from_a_friday_cutoff(self, con):
        """The central leakage case. At a Friday cutoff the Thursday game is decided, so those
        players' outcomes are known and must not be scoreable by any system."""
        (snap,) = assign_snapshots(con, [FRI])
        assert teams_already_playing(con, snap) == frozenset({"THU_H", "THU_A"})

    def test_nothing_is_excluded_at_a_cutoff_before_the_thursday_game(self, con):
        """A Tuesday/Wednesday cutoff precedes every game, so the full board is live. The rule
        must follow the cutoff date, not hardcode 'drop the TNF teams'."""
        (snap,) = assign_snapshots(con, [date(2024, 10, 1)])
        assert teams_already_playing(con, snap) == frozenset()

    def test_a_saturday_cutoff_excludes_more_than_the_thursday_pair(self, con):
        """Two real vintages are Saturday. Assuming 'already played == TNF' would silently
        readmit completed Saturday games into the universe."""
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team)"
            " VALUES ('g_sat', 2024, 5, 'REG', DATE '2024-10-05', 'SAT_H', 'SAT_A')"
        )
        (snap,) = assign_snapshots(con, [date(2024, 10, 5)])
        # Saturday date == game date: the strict inequality treats a same-day game as not yet
        # played, which is the conservative direction given `games` stores no kickoff time.
        assert teams_already_playing(con, snap) == frozenset({"THU_H", "THU_A"})
        con.execute("UPDATE games SET game_date = DATE '2024-10-04' WHERE game_id = 'g_sat'")
        assert teams_already_playing(con, snap) == frozenset({"THU_H", "THU_A", "SAT_H", "SAT_A"})

    def test_eligible_board_rows_removes_exactly_the_excluded_teams(self):
        board = [
            ("p_thu", "WR", "THU_H", 3.0),
            ("p_sun", "RB", "SUN_H", 1.0),
            ("p_oth", "TE", "OTH_A", 2.0),
        ]
        kept = eligible_board_rows(board, frozenset({"THU_H", "THU_A"}))
        assert [r[0] for r in kept] == ["p_sun", "p_oth"]

    def test_exclusion_is_applied_before_ranking_not_after(self):
        """If a already-played player is merely ignored at scoring time rather than removed
        from the universe, every system's ranks are still computed against a contaminated
        board and the depth cutoffs (top 10/25/50) mean different things."""
        board = [
            ("p_thu", "WR", "THU_H", 1.0),
            ("p_sun", "RB", "SUN_H", 2.0),
            ("p_oth", "TE", "OTH_A", 3.0),
        ]
        contaminated = dense_rank(board)
        clean = dense_rank(eligible_board_rows(board, frozenset({"THU_H"})))
        assert contaminated["p_sun"] == 2
        assert clean["p_sun"] == 1


class TestDenseRank:
    def test_a_filtered_board_is_renumbered_from_one(self):
        """Removing QBs and already-played teams leaves a subset of a published 1..N ranking,
        whose raw ECR values are no longer 1..N. Comparing those against a dense rank would be
        comparing two different scales."""
        board = [("a", "RB", "T1", 4.5), ("b", "WR", "T2", 12.0), ("c", "TE", "T3", 30.1)]
        assert dense_rank(board) == {"a": 1, "b": 2, "c": 3}

    def test_ties_break_deterministically(self):
        """A non-deterministic tie-break makes a comparison irreproducible run to run."""
        board = [("z", "RB", "T1", 5.0), ("a", "WR", "T2", 5.0)]
        assert dense_rank(board) == {"a": 1, "z": 2}
        assert dense_rank(list(reversed(board))) == {"a": 1, "z": 2}


def test_snapshot_records_its_own_lead_days(con):
    """`lead_days` is the audit trail for the cutoff: a snapshot with an unusual lead has a
    different information set, and a series that silently mixes them measures two questions."""
    (snap,) = assign_snapshots(con, [FRI])
    assert isinstance(snap, WeeklySnapshot)
    assert snap.first_sunday == SUN
    assert snap.scrape_date + timedelta(days=snap.lead_days) == SUN
