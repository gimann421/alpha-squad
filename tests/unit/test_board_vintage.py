"""Tests for D92's board-vintage identity.

The point of the module under test is that a draft-layer result is only comparable to another
phase's if both ran against the same board. So these tests assert the two properties that makes
true: the hash MOVES when the board moves, and it does NOT move when something irrelevant moves.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import duckdb
import pytest

from alpha_squad.evaluation.board_vintage import (
    BACKTEST_SEASONS,
    D89_BOARD_SHA256,
    D89_IDMAP_SHA256,
    PROJECTION_DECIMALS,
    BoardVintage,
    VintageMismatchError,
    assert_vintage,
    board_hash,
    compute_board_vintage,
    registry_source_hash,
)
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _add_player(con, player_id: str, position: str) -> None:
    """`players.gsis_id` is NOT NULL, so a DB-backed test has to seed the spine the same way
    production writes it."""
    con.execute(
        "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES (?, ?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        [player_id, f"gsis_{player_id}", player_id, position],
    )


def _add_projection(con, player_id: str, season: int, position: str, points: float) -> None:
    """The board reads `uncertainty_predictions.point_prediction` for QB/RB/WR/TE, through the
    same NOT NULL surface production writes."""
    con.execute(
        "INSERT INTO uncertainty_predictions (prediction_id, player_id, season, position, "
        "model_version, feature_version, point_prediction, calibration_season, predicted_at) "
        "VALUES (?, ?, ?, ?, ?, 'test_fv', ?, ?, now())",
        [
            f"{player_id}:{season}:{points}",
            player_id,
            season,
            position,
            UNCERTAINTY_MODEL_VERSION,
            points,
            season - 1,
        ],
    )


def _seed_board(con, season: int = 2024, rb_points: float = 200.0) -> None:
    for pid, pos in (("asq_qb1", "QB"), ("asq_rb1", "RB")):
        _add_player(con, pid, pos)
    _add_projection(con, "asq_qb1", season, "QB", 300.0)
    _add_projection(con, "asq_rb1", season, "RB", rb_points)


def _register(
    con, dataset: str, sha: str, captured_at: str, source: str = "dynastyprocess"
) -> None:
    con.execute(
        "INSERT INTO snapshot_registry "
        "(snapshot_id, source, dataset, captured_at, url, local_path, sha256, rows) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [f"{source}/{dataset}@{captured_at}", source, dataset, captured_at, "u", "p", sha, 1],
    )


class TestBoardHash:
    def test_hash_is_stable_across_calls(self, con):
        _seed_board(con)
        assert board_hash(con, 2024) == board_hash(con, 2024)

    def test_hash_moves_when_a_projection_changes(self, con):
        _seed_board(con, rb_points=200.0)
        before = board_hash(con, 2024)
        con.execute(
            "UPDATE uncertainty_predictions SET point_prediction = 201.0 WHERE player_id = ?",
            ["asq_rb1"],
        )
        assert board_hash(con, 2024) != before

    def test_hash_moves_when_a_player_joins_the_board(self, con):
        _seed_board(con)
        before = board_hash(con, 2024)
        _add_player(con, "asq_wr1", "WR")
        _add_projection(con, "asq_wr1", 2024, "WR", 250.0)
        assert board_hash(con, 2024) != before

    def test_hash_ignores_changes_below_the_rounding_precision(self, con):
        """A difference finer than `PROJECTION_DECIMALS` cannot change a pick, so it must not
        invalidate a vintage -- otherwise every rebuild would look like a different board."""
        _seed_board(con, rb_points=200.0)
        before = board_hash(con, 2024)
        con.execute(
            "UPDATE uncertainty_predictions SET point_prediction = ? WHERE player_id = ?",
            [200.0 + 10 ** -(PROJECTION_DECIMALS + 3), "asq_rb1"],
        )
        assert board_hash(con, 2024) == before

    def test_hash_is_independent_of_insertion_order(self, con):
        _seed_board(con)
        first = board_hash(con, 2024)
        con.execute("DELETE FROM uncertainty_predictions")
        # Same two rows, opposite insertion order.
        _add_projection(con, "asq_rb1", 2024, "RB", 200.0)
        _add_projection(con, "asq_qb1", 2024, "QB", 300.0)
        assert board_hash(con, 2024) == first

    def test_different_seasons_hash_differently(self, con):
        """2025 is deliberately left empty, so its board hashes the empty universe."""
        _seed_board(con, season=2024)
        assert board_hash(con, 2024) != board_hash(con, 2025)


class TestRegistrySourceHash:
    def test_returns_the_most_recent_capture(self, con):
        _register(con, "fp_ecr_history", "old", "2026-09-04T00:00:00")
        _register(con, "fp_ecr_history", "new", "2026-09-11T00:00:00")
        assert registry_source_hash(con, "fp_ecr_history") == "new"

    def test_missing_dataset_is_none_not_an_error(self, con):
        """A fixture database has no registry rows; a caller should get a vintage with nulls
        rather than an exception."""
        assert registry_source_hash(con, "fp_ecr_history") is None


class TestComputeBoardVintage:
    def test_carries_both_upstream_hashes(self, con):
        _seed_board(con)
        _register(con, "fp_ecr_history", D89_BOARD_SHA256, "2026-09-12T00:00:00")
        _register(con, "player_ids", D89_IDMAP_SHA256, "2026-09-12T00:00:00")
        v = compute_board_vintage(con, seasons=(2024,))
        assert v.board_sha256 == D89_BOARD_SHA256
        assert v.idmap_sha256 == D89_IDMAP_SHA256
        assert v.matches_d89() is True

    def test_matches_d89_is_false_for_another_board(self, con):
        _seed_board(con)
        _register(con, "fp_ecr_history", "somethingelse", "2026-09-12T00:00:00")
        _register(con, "player_ids", D89_IDMAP_SHA256, "2026-09-12T00:00:00")
        assert compute_board_vintage(con, seasons=(2024,)).matches_d89() is False

    def test_combined_hash_covers_every_season(self, con):
        _seed_board(con, season=2024)
        one = compute_board_vintage(con, seasons=(2024,))
        two = compute_board_vintage(con, seasons=(2024, 2025))
        assert one.combined_hash != two.combined_hash

    def test_as_dict_round_trips_the_combined_hash(self, con):
        _seed_board(con)
        v = compute_board_vintage(con, seasons=(2024,))
        assert v.as_dict()["combined_hash"] == v.combined_hash

    def test_default_seasons_are_the_backtest_window(self):
        assert BACKTEST_SEASONS == (2020, 2021, 2022, 2023, 2024, 2025)


class TestAssertVintage:
    def test_passes_on_the_same_board(self, con):
        _seed_board(con)
        expected = compute_board_vintage(con, seasons=(2024,)).combined_hash
        assert assert_vintage(con, expected, seasons=(2024,)).combined_hash == expected

    def test_raises_when_the_board_moved(self, con):
        _seed_board(con, rb_points=200.0)
        expected = compute_board_vintage(con, seasons=(2024,)).combined_hash
        con.execute(
            "UPDATE uncertainty_predictions SET point_prediction = 250.0 WHERE player_id = ?",
            ["asq_rb1"],
        )
        with pytest.raises(VintageMismatchError, match="board vintage mismatch"):
            assert_vintage(con, expected, seasons=(2024,))

    def test_error_names_the_actual_hashes(self, con):
        """The message has to be actionable: a phase that trips this needs to know which season
        moved, not merely that something did."""
        _seed_board(con)
        with pytest.raises(VintageMismatchError) as excinfo:
            assert_vintage(con, "0" * 64, seasons=(2024,))
        assert "2024" in str(excinfo.value)


class TestBoardVintageDataclass:
    def test_is_frozen(self):
        v = BoardVintage(board_sha256="a", idmap_sha256="b", season_hashes={2024: "c"})
        with pytest.raises(FrozenInstanceError):
            v.board_sha256 = "x"  # type: ignore[misc]

    def test_combined_hash_is_order_independent(self):
        a = BoardVintage("x", "y", {2020: "p", 2021: "q"})
        b = BoardVintage("x", "y", {2021: "q", 2020: "p"})
        assert a.combined_hash == b.combined_hash


class TestVintageIdentifiesTheBoardNotTheSlice:
    """D92 found this the hard way: the first `--expect-vintage` run failed because the combined
    hash had been computed over six seasons and the run touched one. A vintage has to name the
    board, so a subset run and a full run must be able to quote the same identifier."""

    def test_assert_vintage_defaults_to_the_full_window_regardless_of_caller_slice(self, con):
        for season in BACKTEST_SEASONS:
            _seed_board(con, season=season)
        full = compute_board_vintage(con).combined_hash
        # A caller running only 2022 still verifies against the whole-window identifier.
        assert assert_vintage(con, full).combined_hash == full

    def test_a_narrower_explicit_window_yields_a_different_identifier(self, con):
        for season in BACKTEST_SEASONS:
            _seed_board(con, season=season)
        full = compute_board_vintage(con).combined_hash
        one = compute_board_vintage(con, seasons=(2022,)).combined_hash
        assert full != one, "a season-scoped hash must not be confusable with the full-window one"
