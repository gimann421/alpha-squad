"""Unit tests for canonical identity minting and the collision-safe mapping insert, against
synthetic DuckDB tables — no real snapshots required."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.identity.canonical import PLAYER_ID_SQL_EXPR, insert_id_mappings, mint_player_id
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_two_players(con):
    con.execute(
        """
        INSERT INTO players (player_id, gsis_id, display_name)
        VALUES ('asq_p1', '00-0000001', 'Player One'),
               ('asq_p2', '00-0000002', 'Player Two')
        """
    )


class TestMintPlayerId:
    def test_deterministic_across_calls(self):
        assert mint_player_id("00-0031234") == mint_player_id("00-0031234")

    def test_different_inputs_differ(self):
        assert mint_player_id("00-0031234") != mint_player_id("00-0039999")

    def test_matches_prefix_convention(self):
        assert mint_player_id("00-0031234").startswith("asq_")
        assert len(mint_player_id("00-0031234")) == len("asq_") + 16

    def test_python_and_sql_paths_agree(self, con):
        """Regression test: the Python mint_player_id() and the SQL PLAYER_ID_SQL_EXPR used
        in build_players_spine originally used different hash algorithms (sha256 vs md5),
        which would have minted two different player_ids for the same gsis_id depending on
        which code path ran. Caught in self-review before ever running against real data."""
        gsis_id = "00-0031234"
        sql_result = con.execute(
            f"SELECT {PLAYER_ID_SQL_EXPR} FROM (SELECT ? AS gsis_id)", [gsis_id]
        ).fetchone()[0]
        assert sql_result == mint_player_id(gsis_id)


class TestInsertIdMappings:
    def test_clean_mapping_is_inserted(self, con):
        _seed_two_players(con)
        con.execute("CREATE TEMP VIEW cand AS SELECT 'sleeper1' AS id_value, 'asq_p1' AS player_id")
        result = insert_id_mappings(
            con,
            id_type="sleeper_id",
            candidates_view="cand",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="test",
            snapshot_id="snap1",
        )
        assert result.inserted == 1
        assert result.collisions_quarantined == 0
        row = con.execute(
            "SELECT player_id FROM player_id_map WHERE id_type='sleeper_id' AND id_value='sleeper1'"
        ).fetchone()
        assert row == ("asq_p1",)

    def test_ambiguous_within_batch_is_quarantined_not_inserted(self, con):
        _seed_two_players(con)
        con.execute(
            """
            CREATE TEMP VIEW cand AS
            SELECT 'shared_id' AS id_value, 'asq_p1' AS player_id
            UNION ALL
            SELECT 'shared_id' AS id_value, 'asq_p2' AS player_id
            """
        )
        result = insert_id_mappings(
            con,
            id_type="sleeper_id",
            candidates_view="cand",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="test",
            snapshot_id="snap1",
        )
        assert result.inserted == 0
        assert result.collisions_quarantined == 1
        assert (
            con.execute(
                "SELECT count(*) FROM player_id_map WHERE id_type='sleeper_id' AND id_value='shared_id'"
            ).fetchone()[0]
            == 0
        )
        exc = con.execute(
            "SELECT exception_type, status FROM identity_exceptions WHERE subject = 'sleeper_id:shared_id'"
        ).fetchone()
        assert exc == ("ambiguous_source_mapping", "PENDING")

    def test_cross_source_collision_is_quarantined_and_original_mapping_kept(self, con):
        _seed_two_players(con)
        con.execute(
            "CREATE TEMP VIEW cand1 AS SELECT 'shared_id' AS id_value, 'asq_p1' AS player_id"
        )
        insert_id_mappings(
            con,
            id_type="espn_id",
            candidates_view="cand1",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="source_a",
            snapshot_id="snap1",
        )
        con.execute(
            "CREATE TEMP VIEW cand2 AS SELECT 'shared_id' AS id_value, 'asq_p2' AS player_id"
        )
        result = insert_id_mappings(
            con,
            id_type="espn_id",
            candidates_view="cand2",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="source_b",
            snapshot_id="snap2",
        )
        assert result.inserted == 0
        assert result.collisions_quarantined == 1
        row = con.execute(
            "SELECT player_id FROM player_id_map WHERE id_type='espn_id' AND id_value='shared_id'"
        ).fetchone()
        assert row == ("asq_p1",), (
            "the original mapping must not be overwritten by a conflicting source"
        )
        exc = con.execute(
            "SELECT exception_type FROM identity_exceptions WHERE subject = 'espn_id:shared_id'"
        ).fetchone()
        assert exc == ("cross_source_id_collision",)

    def test_reinserting_the_same_mapping_twice_is_a_harmless_noop(self, con):
        _seed_two_players(con)
        con.execute("CREATE TEMP VIEW cand AS SELECT 'x' AS id_value, 'asq_p1' AS player_id")
        insert_id_mappings(
            con,
            id_type="mfl_id",
            candidates_view="cand",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="test",
            snapshot_id="snap1",
        )
        result = insert_id_mappings(
            con,
            id_type="mfl_id",
            candidates_view="cand",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="test",
            snapshot_id="snap2",
        )
        assert result.collisions_quarantined == 0
        assert (
            con.execute(
                "SELECT count(*) FROM player_id_map WHERE id_type='mfl_id' AND id_value='x'"
            ).fetchone()[0]
            == 1
        )

    def test_null_id_values_are_skipped_not_inserted(self, con):
        _seed_two_players(con)
        con.execute(
            "CREATE TEMP VIEW cand AS SELECT NULL::VARCHAR AS id_value, 'asq_p1' AS player_id"
        )
        result = insert_id_mappings(
            con,
            id_type="mfl_id",
            candidates_view="cand",
            id_value_expr="id_value",
            player_id_expr="player_id",
            source="test",
            snapshot_id="snap1",
        )
        assert result.inserted == 0
        assert con.execute("SELECT count(*) FROM player_id_map").fetchone()[0] == 0
