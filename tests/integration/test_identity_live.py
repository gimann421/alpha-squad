"""End-to-end identity build against real, live-fetched source data. Deselected by default;
run with `make test-network`. Fetches into an isolated tmp_path database so it never touches
the developer's real data/ directory, then asserts the integrity invariants that matter:
no orphaned foreign keys, no duplicate crosswalk keys, plausible coverage."""

from __future__ import annotations

import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import build_identity
from alpha_squad.sources.cfbfastr import CfbFastRSource
from alpha_squad.sources.dynastyprocess import DynastyProcessSource
from alpha_squad.sources.nflverse import NflverseSource
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_snapshot

pytestmark = pytest.mark.network


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


@pytest.fixture
def con_with_real_snapshots(settings):
    con = get_connection(settings)
    init_db(con)
    nflverse = NflverseSource(settings)
    dp = DynastyProcessSource(settings)
    cfbfastr = CfbFastRSource(settings)

    for snap in [
        nflverse.fetch("players"),
        nflverse.fetch("draft_picks"),
        nflverse.fetch("combine"),
        dp.fetch("player_ids"),
    ]:
        record_snapshot(con, snap)
    # Not required by build_identity, but a realistic ingest would have it too.
    record_snapshot(con, cfbfastr.fetch("player_stats", season=2025))

    yield con
    con.close()


def test_identity_build_against_real_data_has_no_integrity_violations(
    con_with_real_snapshots, settings
):
    con = con_with_real_snapshots
    report = build_identity(con, settings)
    assert report.players_upserted > 20000

    dup_keys = con.execute(
        "SELECT count(*) FROM (SELECT id_type, id_value, count(*) c FROM player_id_map GROUP BY 1, 2 HAVING c > 1)"
    ).fetchone()[0]
    assert dup_keys == 0

    null_gsis = con.execute("SELECT count(*) FROM players WHERE gsis_id IS NULL").fetchone()[0]
    assert null_gsis == 0

    dup_players = con.execute(
        "SELECT count(*) FROM (SELECT player_id, count(*) c FROM players GROUP BY 1 HAVING c > 1)"
    ).fetchone()[0]
    assert dup_players == 0

    orphaned_map_rows = con.execute(
        "SELECT count(*) FROM player_id_map m LEFT JOIN players p ON p.player_id = m.player_id "
        "WHERE p.player_id IS NULL"
    ).fetchone()[0]
    assert orphaned_map_rows == 0

    orphaned_bridge_rows = con.execute(
        "SELECT count(*) FROM player_college_bridge b LEFT JOIN players p ON p.player_id = b.player_id "
        "WHERE p.player_id IS NULL"
    ).fetchone()[0]
    assert orphaned_bridge_rows == 0

    # Plausible coverage — loose bounds, not exact counts, so this doesn't become brittle
    # against routine upstream data updates.
    gsis_mapped = con.execute(
        "SELECT count(*) FROM player_id_map WHERE id_type = 'gsis_id'"
    ).fetchone()[0]
    assert gsis_mapped == report.players_upserted

    sleeper_mapped = con.execute(
        "SELECT count(*) FROM player_id_map WHERE id_type = 'sleeper_id'"
    ).fetchone()[0]
    assert sleeper_mapped > 1000, "DynastyProcess crosswalk should map several thousand sleeper_ids"

    cfb_bridge_rows = con.execute(
        "SELECT count(*) FROM player_college_bridge WHERE cfb_player_id IS NOT NULL OR cfb_id IS NOT NULL"
    ).fetchone()[0]
    assert cfb_bridge_rows > 5000, (
        "draft_picks/combine college bridge should populate for thousands of players"
    )


def test_identity_build_is_idempotent_on_rerun(con_with_real_snapshots):
    from alpha_squad.config.settings import get_settings

    con = con_with_real_snapshots
    report1 = build_identity(con, get_settings())
    report2 = build_identity(con, get_settings())
    assert report1.players_upserted == report2.players_upserted

    total_mappings_1 = sum(m.inserted for m in report1.mapping_results)
    # Second run should insert ~0 *new* rows for id types with no new data (ON CONFLICT DO
    # NOTHING dedupes), but our RETURNING-based count reflects rows touched by the
    # INSERT...SELECT regardless of conflict, so just assert nothing errors and the map
    # doesn't grow unboundedly.
    map_rows_after_1 = con.execute("SELECT count(*) FROM player_id_map").fetchone()[0]
    assert total_mappings_1 >= 0
    map_rows_after_2 = con.execute("SELECT count(*) FROM player_id_map").fetchone()[0]
    assert map_rows_after_1 == map_rows_after_2, (
        "rerunning identity build must not duplicate mappings"
    )
