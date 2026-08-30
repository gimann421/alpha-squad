"""Regression coverage for schema migrations against a PRE-EXISTING database
(docs/DECISIONS.md D39).

Every other test in this suite builds a fresh in-memory database, where
`CREATE TABLE IF NOT EXISTS` produces the current schema and any drift is invisible. That is
exactly why D38 shipped broken: it added `rookie_features.college_usage_*` and
`market_snapshot.source` to schema.py, the whole suite passed, and the first run against a
real database that predated those columns crashed with
`BinderException: Referenced update column college_usage_overall not found in table`.

These tests deliberately construct the OLD schema first, then run init_db over it."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.storage.db import init_db

PRE_D38_ROOKIE_FEATURES = """
CREATE TABLE rookie_features (
    player_id VARCHAR PRIMARY KEY,
    draft_class INTEGER NOT NULL,
    position VARCHAR NOT NULL,
    draft_round INTEGER,
    draft_pick INTEGER,
    forty DOUBLE, bench DOUBLE, vertical DOUBLE, broad_jump DOUBLE, cone DOUBLE,
    shuttle DOUBLE, height DOUBLE, weight DOUBLE,
    landing_team_prior_pass_rate DOUBLE,
    landing_team_prior_plays DOUBLE,
    rookie_year_ppr_points DOUBLE NOT NULL,
    rookie_year_games INTEGER,
    breakout_top24 BOOLEAN NOT NULL,
    built_at TIMESTAMP NOT NULL
)
"""

PRE_D38_MARKET_SNAPSHOT = """
CREATE TABLE market_snapshot (
    player_id VARCHAR NOT NULL,
    scrape_date DATE NOT NULL,
    ecr_type VARCHAR NOT NULL,
    position VARCHAR,
    ecr_rank DOUBLE NOT NULL,
    ecr_best DOUBLE,
    ecr_worst DOUBLE,
    source_snapshot_id VARCHAR,
    PRIMARY KEY (player_id, scrape_date, ecr_type)
)
"""


@pytest.fixture
def pre_d38_con():
    con = duckdb.connect(":memory:")
    con.execute(PRE_D38_ROOKIE_FEATURES)
    con.execute(PRE_D38_MARKET_SNAPSHOT)
    yield con
    con.close()


def test_init_db_adds_college_usage_columns_to_an_existing_rookie_features(pre_d38_con):
    init_db(pre_d38_con)
    cols = {r[0] for r in pre_d38_con.execute("DESCRIBE rookie_features").fetchall()}
    assert {"college_usage_overall", "college_usage_pass", "college_usage_rush"} <= cols


def test_init_db_adds_source_to_an_existing_market_snapshot(pre_d38_con):
    init_db(pre_d38_con)
    cols = {r[0] for r in pre_d38_con.execute("DESCRIBE market_snapshot").fetchall()}
    assert "source" in cols


def test_market_snapshot_rebuild_preserves_existing_rows_tagged_dynastyprocess(pre_d38_con):
    """The rebuild drops and recreates the table -- pre-existing ECR history must survive it,
    correctly attributed, since 'dynastyprocess' was the only writer before D38."""
    pre_d38_con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
        "VALUES ('p1', DATE '2025-08-01', 'ro', 'WR', 12.0)"
    )
    init_db(pre_d38_con)
    rows = pre_d38_con.execute(
        "SELECT player_id, ecr_type, ecr_rank, source FROM market_snapshot"
    ).fetchall()
    assert rows == [("p1", "ro", 12.0, "dynastyprocess")]


def test_migrated_market_snapshot_accepts_both_sources_for_one_player_date_ecr_type(pre_d38_con):
    """The point of the rebuild: the widened PRIMARY KEY. Under the old 3-column key these two
    rows collide, which is the bug that would have corrupted the live FantasyPros series."""
    pre_d38_con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
        "VALUES ('p1', DATE '2025-08-01', 'ro', 'WR', 12.0)"
    )
    init_db(pre_d38_con)
    pre_d38_con.execute(
        "INSERT INTO market_snapshot "
        "(player_id, scrape_date, ecr_type, position, ecr_rank, source) "
        "VALUES ('p1', DATE '2025-08-01', 'ro', 'WR', 9.0, 'fantasypros_live')"
    )
    sources = {r[0] for r in pre_d38_con.execute("SELECT source FROM market_snapshot").fetchall()}
    assert sources == {"dynastyprocess", "fantasypros_live"}


def test_init_db_is_still_idempotent_on_an_already_migrated_database(pre_d38_con):
    init_db(pre_d38_con)
    init_db(pre_d38_con)
    init_db(pre_d38_con)
    cols = {r[0] for r in pre_d38_con.execute("DESCRIBE rookie_features").fetchall()}
    assert "college_usage_overall" in cols
    assert pre_d38_con.execute("SELECT count(*) FROM market_snapshot").fetchone()[0] == 0


def test_init_db_on_a_completely_fresh_database_still_works(pre_d38_con):
    """The migration path must not break the fresh-database case it sits alongside."""
    fresh = duckdb.connect(":memory:")
    try:
        init_db(fresh)
        cols = {r[0] for r in fresh.execute("DESCRIBE rookie_features").fetchall()}
        assert "college_usage_overall" in cols
    finally:
        fresh.close()


PRE_D56_MARKET_SNAPSHOT = """
CREATE TABLE market_snapshot (
    player_id VARCHAR NOT NULL,
    scrape_date DATE NOT NULL,
    ecr_type VARCHAR NOT NULL,
    position VARCHAR,
    ecr_rank DOUBLE NOT NULL,
    ecr_best DOUBLE,
    ecr_worst DOUBLE,
    source_snapshot_id VARCHAR,
    source VARCHAR NOT NULL DEFAULT 'dynastyprocess',
    PRIMARY KEY (player_id, scrape_date, ecr_type, source)
)
"""


@pytest.fixture
def pre_d56_con():
    """A database at the D38 schema: it has `source` but not `page_type`."""
    con = duckdb.connect(":memory:")
    con.execute(PRE_D38_ROOKIE_FEATURES)
    con.execute(PRE_D56_MARKET_SNAPSHOT)
    yield con
    con.close()


def test_init_db_adds_page_type_to_a_d38_era_market_snapshot(pre_d56_con):
    init_db(pre_d56_con)
    cols = {r[0] for r in pre_d56_con.execute("DESCRIBE market_snapshot").fetchall()}
    assert "page_type" in cols


def test_page_type_rebuild_preserves_rows_without_inventing_a_page(pre_d56_con):
    """Which FantasyPros page a pre-D56 row came from is genuinely unrecorded. The migration
    must carry the row across rather than drop it, and must leave page_type empty rather than
    guess -- a guessed page is fabricated provenance."""
    pre_d56_con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
        "VALUES ('p1', DATE '2025-08-01', 'ro', 'WR', 12.0)"
    )
    init_db(pre_d56_con)
    rows = pre_d56_con.execute(
        "SELECT player_id, ecr_type, ecr_rank, source, page_type FROM market_snapshot"
    ).fetchall()
    assert rows == [("p1", "ro", 12.0, "dynastyprocess", "")]


def test_migrated_market_snapshot_keeps_both_pages_of_one_ecr_type(pre_d56_con):
    """THE bug D56 fixes. DynastyProcess labels several independently-ranked FantasyPros pages
    with the same ecr_type: 'ro' carries both the PPR draft board (`redraft-overall`) and a
    separate 1..N IDP ranking (`redraft-idp`). Under the pre-D56 key these two rows for the
    same player and date collide, so one silently overwrites the other."""
    init_db(pre_d56_con)
    for page_type, rank in (("redraft-overall", 12.0), ("redraft-idp", 3.0)):
        pre_d56_con.execute(
            "INSERT INTO market_snapshot "
            "(player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
            "VALUES ('p1', DATE '2025-08-01', 'ro', 'WR', ?, ?)",
            [rank, page_type],
        )
    rows = dict(pre_d56_con.execute("SELECT page_type, ecr_rank FROM market_snapshot").fetchall())
    assert rows == {"redraft-overall": 12.0, "redraft-idp": 3.0}


PRE_D61_DRAFT_SIMULATION_RESULTS = """
CREATE TABLE draft_simulation_results (
    season INTEGER NOT NULL,
    strategy VARCHAR NOT NULL,
    draft_slot INTEGER NOT NULL,
    drafted_player_ids_json VARCHAR NOT NULL,
    total_roster_points DOUBLE NOT NULL,
    starter_points DOUBLE NOT NULL,
    framework_version VARCHAR NOT NULL,
    evaluated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (season, strategy, draft_slot, framework_version)
)
"""


@pytest.fixture
def pre_d61_con():
    """A database at the D60 schema: `draft_simulation_results` has no `opponent_strategy` or
    `n_unfilled_mandatory_slots` column, and its primary key has no room for opponent_strategy."""
    con = duckdb.connect(":memory:")
    con.execute(PRE_D61_DRAFT_SIMULATION_RESULTS)
    yield con
    con.close()


def test_init_db_adds_opponent_strategy_to_a_d60_era_draft_simulation_results(pre_d61_con):
    init_db(pre_d61_con)
    cols = {r[0] for r in pre_d61_con.execute("DESCRIBE draft_simulation_results").fetchall()}
    assert "opponent_strategy" in cols
    assert "n_unfilled_mandatory_slots" in cols


def test_draft_simulation_results_rebuild_drops_pre_d61_rows_without_inventing_data(pre_d61_con):
    """Unlike market_snapshot, this table is a pure evaluation-result cache the CLI fully
    repopulates on every `alpha-squad evaluate draft-simulation` run. A pre-D61 row has no
    real `opponent_strategy` distinct from 'market_consensus' (that was the only opponent
    field that ever existed) but genuinely has no measured `n_unfilled_mandatory_slots` --
    carrying it forward with an invented 0 would fabricate data no version of the code ever
    computed, so the migration drops the table outright rather than rebuild-and-carry."""
    pre_d61_con.execute(
        "INSERT INTO draft_simulation_results "
        "(season, strategy, draft_slot, drafted_player_ids_json, total_roster_points, "
        "starter_points, framework_version, evaluated_at) "
        "VALUES (2023, 'market_consensus', 1, '[]', 100.0, 90.0, 'v1', current_timestamp)"
    )
    init_db(pre_d61_con)
    n = pre_d61_con.execute("SELECT count(*) FROM draft_simulation_results").fetchone()[0]
    assert n == 0


def test_migrated_draft_simulation_results_accepts_both_opponent_strategies_for_one_trial(
    pre_d61_con,
):
    """The regression D61 Stage 1.1 needs: the same (season, strategy, draft_slot) measured
    against both opponent fields must coexist, not collide under the old primary key."""
    init_db(pre_d61_con)
    for opponent_strategy in ("market_consensus", "market_consensus_roster_aware"):
        pre_d61_con.execute(
            "INSERT INTO draft_simulation_results "
            "(season, strategy, draft_slot, drafted_player_ids_json, total_roster_points, "
            "starter_points, framework_version, evaluated_at, opponent_strategy, "
            "n_unfilled_mandatory_slots) "
            "VALUES (2023, 'alpha_bpa', 1, '[]', 100.0, 90.0, 'v1', current_timestamp, ?, 0)",
            [opponent_strategy],
        )
    rows = pre_d61_con.execute(
        "SELECT opponent_strategy FROM draft_simulation_results ORDER BY opponent_strategy"
    ).fetchall()
    assert [r[0] for r in rows] == ["market_consensus", "market_consensus_roster_aware"]


def test_init_db_is_idempotent_on_an_already_migrated_draft_simulation_results(pre_d61_con):
    init_db(pre_d61_con)
    init_db(pre_d61_con)  # must not raise on the second pass
    cols = {r[0] for r in pre_d61_con.execute("DESCRIBE draft_simulation_results").fetchall()}
    assert "opponent_strategy" in cols
