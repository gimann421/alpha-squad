"""Unit tests for the source-adapter error/status vocabulary itself."""

from datetime import datetime

from alpha_squad.sources.base import (
    RawSnapshot,
    SourceBlockedError,
    SourceCredentialsError,
    SourceNotFoundError,
    SourceStatus,
)


def test_error_classes_carry_expected_status():
    assert SourceBlockedError("x").status == SourceStatus.BLOCKED_BY_POLICY
    assert SourceCredentialsError("x").status == SourceStatus.NO_CREDENTIALS
    assert SourceNotFoundError("x").status == SourceStatus.NOT_FOUND


def test_raw_snapshot_id_is_stable_and_includes_params():
    snap = RawSnapshot(
        source="nflverse",
        dataset="stats_player_week",
        captured_at=datetime(2026, 8, 20),
        url="https://example.test/x.parquet",
        local_path=__file__,  # type: ignore[arg-type]
        sha256="deadbeef",
        rows=10,
        columns=("a", "b"),
        params=(("season", "2024"),),
    )
    assert snap.snapshot_id == "nflverse/stats_player_week/season=2024@2026-08-20T00:00:00"


def test_raw_snapshot_id_without_params_uses_default_marker():
    snap = RawSnapshot(
        source="nflverse",
        dataset="players",
        captured_at=datetime(2026, 8, 20),
        url="https://example.test/players.parquet",
        local_path=__file__,  # type: ignore[arg-type]
        sha256="deadbeef",
        rows=10,
        columns=("a",),
    )
    assert snap.snapshot_id == "nflverse/players/default@2026-08-20T00:00:00"
