"""Round-trip tests for the snapshot registry. Regression coverage for a real bug found
during M1: `sources status` was writing real files to disk and reporting AVAILABLE without
ever calling record_snapshot, so the registry table silently stayed empty while the CLI
reported success. These tests assert the registry actually reflects what was fetched."""

from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from alpha_squad.sources.base import RawSnapshot, SourceHealth, SourceStatus
from alpha_squad.storage.db import init_db
from alpha_squad.storage.snapshots import latest_snapshot, record_health, record_snapshot


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _snapshot(**overrides) -> RawSnapshot:
    defaults = dict(
        source="nflverse",
        dataset="players",
        captured_at=datetime(2026, 8, 20, 12, 0, 0),
        url="https://example.test/players.parquet",
        local_path=Path("/tmp/players.parquet"),
        sha256="abc123",
        rows=100,
        columns=("gsis_id", "display_name"),
        params=(),
    )
    defaults.update(overrides)
    return RawSnapshot(**defaults)


def test_record_snapshot_is_queryable_afterward(con):
    snap = _snapshot()
    record_snapshot(con, snap)

    row = latest_snapshot(con, "nflverse", "players")
    assert row is not None
    assert row["rows"] == 100
    assert row["sha256"] == "abc123"
    assert row["source"] == "nflverse"


def test_record_snapshot_round_trips_through_a_status_check_style_flow(con):
    """Mirrors what `alpha-squad sources status` now does: fetch, then record_snapshot AND
    record_health for the same outcome. Both must be visible afterward."""
    snap = _snapshot(dataset="stats_player_week", params=(("season", "2024"),))
    record_snapshot(con, snap)
    record_health(
        con,
        SourceHealth(
            "nflverse", "stats_player_week", SourceStatus.AVAILABLE, snap.captured_at, "ok"
        ),
    )

    snap_row = latest_snapshot(con, "nflverse", "stats_player_week", season="2024")
    assert snap_row is not None

    health_rows = con.execute(
        "SELECT status FROM source_health_log WHERE source=? AND dataset=?",
        ["nflverse", "stats_player_week"],
    ).fetchall()
    assert health_rows == [("AVAILABLE",)]


def test_latest_snapshot_prefers_most_recent_capture(con):
    older = _snapshot(captured_at=datetime(2026, 1, 1), sha256="old")
    newer = _snapshot(captured_at=datetime(2026, 8, 20), sha256="new")
    record_snapshot(con, older)
    record_snapshot(con, newer)

    row = latest_snapshot(con, "nflverse", "players")
    assert row["sha256"] == "new"


def test_latest_snapshot_returns_none_when_absent(con):
    assert latest_snapshot(con, "nflverse", "does_not_exist") is None


def test_params_disambiguate_snapshots_for_the_same_dataset(con):
    s2023 = _snapshot(dataset="stats_player_week", params=(("season", "2023"),), sha256="s2023")
    s2024 = _snapshot(dataset="stats_player_week", params=(("season", "2024"),), sha256="s2024")
    record_snapshot(con, s2023)
    record_snapshot(con, s2024)

    row = latest_snapshot(con, "nflverse", "stats_player_week", season="2023")
    assert row["sha256"] == "s2023"
