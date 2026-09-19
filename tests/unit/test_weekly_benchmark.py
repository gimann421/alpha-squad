"""The W2 benchmark universe, reference baselines, noise floor and decision rules.

The universe rules are the part of W2 that a later phase could most easily break without
noticing, so they are tested against the two specific failure modes W1.1 found in the real
data: a board whose `team` column is not a historical fact, and a reference baseline that
quietly changes the player pool it is scored on.

Offline; synthetic fixtures only.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from alpha_squad.evaluation.weekly import noise
from alpha_squad.evaluation.weekly.benchmark import (
    MIN_EVALUABLE,
    Board,
    BoardRow,
    baseline_boards,
    flex_board,
    positional_board,
    rerank_board,
)
from alpha_squad.evaluation.weekly.decision_rules import (
    DEPTH_UNIFORMITY_THRESHOLD,
    evaluate_r1,
    evaluate_r2,
)
from alpha_squad.evaluation.weekly.scoring import FULL_PPR
from alpha_squad.evaluation.weekly.snapshots import WeeklySnapshot
from alpha_squad.storage.db import init_db

SNAP = WeeklySnapshot(2024, 5, date(2024, 10, 4), date(2024, 10, 6), 2)


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    init_db(c)
    c.execute(
        "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
        "VALUES ('thu', 2024, 5, 'REG', DATE '2024-10-03', 'THU_H', 'THU_A'),"
        "       ('sun', 2024, 5, 'REG', DATE '2024-10-06', 'SUN_H', 'SUN_A')"
    )
    # Minimal ecr / xwalk views matching the shapes benchmark.py reads.
    c.execute(
        """CREATE TABLE ecr (fp_page VARCHAR, ecr_type VARCHAR, page_type VARCHAR,
               scrape_date VARCHAR, id VARCHAR, pos VARCHAR, team VARCHAR, ecr DOUBLE)"""
    )
    c.execute("CREATE TABLE xwalk (fantasypros_id VARCHAR, gsis_id VARCHAR)")
    yield c
    c.close()


def _add_player(
    con,
    pid,
    gsis,
    fp_id,
    position,
    team,
    ecr,
    points,
    *,
    page="weekly-op",
    ecr_type="wsf",
    fp_page="/nfl/rankings/ppr-superflex.php",
):
    con.execute(
        "INSERT INTO players (player_id, gsis_id, position) VALUES (?,?,?)", [pid, gsis, position]
    )
    con.execute("INSERT INTO xwalk VALUES (?,?)", [fp_id, gsis])
    con.execute(
        "INSERT INTO ecr VALUES (?,?,?,?,?,?,?,?)",
        [fp_page, ecr_type, page, "2024-10-04", fp_id, position, team, ecr],
    )
    if points is not None:
        con.execute(
            """INSERT INTO player_week_stats
               (player_id, season, week, game_id, game_date, team, position,
                receptions, fantasy_points, fantasy_points_ppr)
               VALUES (?, 2024, 5, ?, ?, ?, ?, 0, ?, ?)""",
            [
                pid,
                "thu" if team in ("THU_H", "THU_A") else "sun",
                date(2024, 10, 6),
                team,
                position,
                points,
                points,
            ],
        )


class TestUniverse:
    def test_already_played_players_are_excluded_via_the_schedule_not_the_board(self, con):
        """The trap W1.1 found in the real FantasyPros payload: the board's `team` column is
        the player's CURRENT team, not his team that week. The exclusion must therefore key
        on `player_week_stats.team` + `games`, never on what the board says."""
        _add_player(con, "p_thu", "00-1", "1", "RB", "THU_H", 1.0, 20.0)
        _add_player(con, "p_sun", "00-2", "2", "WR", "SUN_H", 2.0, 10.0)
        # The board lies about p_sun's team, claiming he is on the Thursday team.
        con.execute("UPDATE ecr SET team = 'THU_H' WHERE id = '2'")
        board = flex_board(con, SNAP, FULL_PPR)
        ids = [r.player_id for r in board.rows]
        assert "p_thu" not in ids, "a player whose game already kicked off must be dropped"
        assert "p_sun" in ids, "a board's wrong team column must not drop a live player"

    def test_qbs_are_removed_from_the_flex_board(self, con):
        _add_player(con, "p_qb", "00-3", "3", "QB", "SUN_H", 1.0, 30.0)
        _add_player(con, "p_rb", "00-4", "4", "RB", "SUN_H", 2.0, 10.0)
        assert [r.position for r in flex_board(con, SNAP, FULL_PPR).rows] == ["RB"]

    def test_players_who_did_not_play_are_ranked_but_not_evaluable(self, con):
        """Availability and production forecast stay separate: a ranked player with no
        realized row is kept in `rows` (he was ranked) and excluded from `evaluable`."""
        _add_player(con, "p_played", "00-5", "5", "RB", "SUN_H", 1.0, 12.0)
        _add_player(con, "p_inactive", "00-6", "6", "WR", "SUN_H", 2.0, None)
        b = flex_board(con, SNAP, FULL_PPR)
        assert len(b.rows) == 2
        assert [r.player_id for r in b.evaluable] == ["p_played"]
        assert b.availability == pytest.approx(0.5)

    def test_a_played_zero_is_evaluable_but_an_absent_row_is_not(self, con):
        _add_player(con, "p_zero", "00-7", "7", "RB", "SUN_H", 1.0, 0.0)
        _add_player(con, "p_none", "00-8", "8", "RB", "SUN_H", 2.0, None)
        b = flex_board(con, SNAP, FULL_PPR)
        assert [r.player_id for r in b.evaluable] == ["p_zero"]

    def test_positional_board_reads_its_own_series(self, con):
        _add_player(
            con,
            "p_rb",
            "00-9",
            "9",
            "RB",
            "SUN_H",
            1.0,
            11.0,
            page="weekly-rb",
            ecr_type="wp",
            fp_page="/nfl/rankings/ppr-rb.php",
        )
        assert [r.player_id for r in positional_board(con, SNAP, "RB", FULL_PPR).rows] == ["p_rb"]

    def test_ranks_are_dense_over_the_evaluable_set(self, con):
        """A metric computed on sparse ECR values (3.2, 14.7, 88.1) is not on the same scale
        as one computed on 1..N, and every reference baseline produces 1..N."""
        for i, (pid, ecr, pts) in enumerate([("a", 3.2, 5.0), ("b", 14.7, None), ("c", 88.1, 9.0)]):
            _add_player(con, pid, f"00-1{i}", f"1{i}", "RB", "SUN_H", ecr, pts)
        ranks, points = flex_board(con, SNAP, FULL_PPR).ranks_and_points()
        assert ranks == [1.0, 2.0]
        assert points == [5.0, 9.0]


class TestReferenceBaselines:
    def test_reranking_preserves_the_player_universe_exactly(self, con):
        """If a baseline could add or drop players it would be answering a different question
        from ECR, and the comparison would be meaningless."""
        board = Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("a", "RB", 1.0, 5.0),
                BoardRow("b", "WR", 2.0, 9.0),
                BoardRow("c", "TE", 3.0, 1.0),
            ],
        )
        out = rerank_board(board, {"b": 20.0, "a": 10.0, "c": 1.0})
        assert {r.player_id for r in out.rows} == {"a", "b", "c"}
        assert [r.player_id for r in out.rows] == ["b", "a", "c"]
        assert [r.ecr for r in out.rows] == [1.0, 2.0, 3.0]

    def test_players_with_no_prior_production_sort_last_deterministically(self, con):
        board = Board(
            2024,
            5,
            "FLEX",
            [
                BoardRow("known", "RB", 1.0, 5.0),
                BoardRow("zz_unknown", "WR", 2.0, 9.0),
                BoardRow("aa_unknown", "TE", 3.0, 1.0),
            ],
        )
        out = rerank_board(board, {"known": 10.0})
        assert [r.player_id for r in out.rows] == ["known", "aa_unknown", "zz_unknown"]

    def test_both_pre_registered_baselines_are_produced(self, con):
        _add_player(con, "p", "00-20", "20", "RB", "SUN_H", 1.0, 7.0)
        b = flex_board(con, SNAP, FULL_PPR)
        out = baseline_boards(con, b, FULL_PPR)
        assert set(out) == {"B0_season_to_date_ppg", "B1_prior_season_ppg"}


class TestNoiseFloor:
    def test_paired_difference_uses_only_weeks_both_systems_cover(self):
        """Averaging each system over its own weeks and subtracting would confound the
        difference with which weeks each happened to have."""
        a = {(2024, w): 0.6 for w in range(1, 11)}
        b = {(2024, w): 0.5 for w in range(1, 6)}
        pd = noise.paired_difference("spearman", "ECR", "B0", a, b)
        assert pd is not None and pd.n_weeks == 5
        assert pd.mean_diff == pytest.approx(0.1)

    def test_mde_is_the_half_width_of_the_interval(self):
        a = {(2024, w): 0.6 + 0.01 * w for w in range(1, 40)}
        b = {(2024, w): 0.5 for w in range(1, 40)}
        pd = noise.paired_difference("m", "A", "B", a, b)
        assert pd.mde == pytest.approx((pd.ci_high - pd.ci_low) / 2.0)

    def test_bootstrap_is_deterministic_across_runs(self):
        """Seeds are pre-registered; an interval that moved run to run would make every
        reported result irreproducible."""
        a = {(2024, w): 0.5 + (w % 7) * 0.02 for w in range(1, 41)}
        b = {(2024, w): 0.4 + (w % 5) * 0.03 for w in range(1, 41)}
        first = noise.paired_difference("m", "A", "B", a, b)
        second = noise.paired_difference("m", "A", "B", a, b)
        assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)

    def test_a_zero_crossing_interval_is_reported_as_not_significant(self):
        a = {(2024, w): 0.5 + (0.2 if w % 2 else -0.2) for w in range(1, 40)}
        b = {(2024, w): 0.5 for w in range(1, 40)}
        pd = noise.paired_difference("m", "A", "B", a, b)
        assert pd.excludes_zero is False

    def test_describe_needs_at_least_three_weeks(self):
        assert noise.describe("m", [0.5, 0.6]) is None
        assert noise.describe("m", [0.5, 0.6, 0.7]) is not None


class TestDecisionRules:
    def test_r1_is_usable_when_any_effect_exceeds_its_mde(self):
        paired = {"spearman": {"mean_diff": 0.07, "mde": 0.02}}
        v = evaluate_r1(paired, reference="B0", metrics=("spearman",))
        assert v.usable is True
        assert v.effects[0].in_mde_units == pytest.approx(3.5)

    def test_r1_is_underpowered_when_every_effect_sits_inside_the_noise(self):
        paired = {
            "spearman": {"mean_diff": 0.001, "mde": 0.02},
            "pairwise": {"mean_diff": 0.002, "mde": 0.03},
        }
        assert evaluate_r1(paired, reference="B0", metrics=("spearman", "pairwise")).usable is False

    def test_r2_uniform_and_depth_dependent_around_the_frozen_threshold(self):
        assert DEPTH_UNIFORMITY_THRESHOLD == 2.0
        uniform = {
            f"capture@{k}": {"mean_diff": d, "mde": 0.01}
            for k, d in ((10, 0.020), (25, 0.025), (50, 0.030))
        }
        assert evaluate_r2(uniform).depth_uniform is True
        skewed = {
            f"capture@{k}": {"mean_diff": d, "mde": 0.01}
            for k, d in ((10, 0.010), (25, 0.030), (50, 0.050))
        }
        assert evaluate_r2(skewed).depth_uniform is False

    def test_r2_skips_depths_the_board_cannot_support(self):
        """K and DST boards have ~32 players, so capture@50 never exists for them. It must be
        skipped, not imputed."""
        v = evaluate_r2(
            {
                "capture@10": {"mean_diff": 0.04, "mde": 0.02},
                "capture@25": {"mean_diff": 0.03, "mde": 0.02},
            }
        )
        assert set(v.ratios) == {10, 25}


def test_min_evaluable_threshold_is_the_pre_registered_one():
    assert MIN_EVALUABLE == 10
