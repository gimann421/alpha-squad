"""Unit tests for the source-adapter error/status vocabulary itself."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from alpha_squad.sources.base import (
    RawSnapshot,
    SourceBlockedError,
    SourceCredentialsError,
    SourceNotFoundError,
    SourceStatus,
    write_bytes_atomic,
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


def test_write_bytes_atomic_leaves_no_temp_file_behind(tmp_path):
    dest = tmp_path / "snap.json"
    write_bytes_atomic(dest, b'{"a": 1}')
    assert dest.read_bytes() == b'{"a": 1}'
    assert list(tmp_path.iterdir()) == [dest], "a .part temp file was left behind"


def test_write_bytes_atomic_never_produces_a_torn_read_under_concurrency(tmp_path):
    """Regression (D53): sleeper.py/cfbd.py/fantasypros.py used to write snapshot files via
    `dest.write_bytes(...)`, which opens in truncate mode. Two real leagues can resolve to the
    *same* underlying Sleeper league (same snapshot key), so one request re-fetching/writing
    that snapshot can race a concurrent request reading it -- confirmed live as a real
    `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` (a 0-byte read hitting a file
    another request had just truncated but not yet finished writing), and reproduced directly
    against the old `dest.write_bytes(...)` pattern by hammering one shared path with
    concurrent writer + reader threads (thousands of JSONDecodeErrors in a couple thousand
    reads). `write_bytes_atomic` writes to a uniquely-named temp file and renames it into
    place (`Path.replace`, atomic on the same filesystem), so a concurrent reader always sees
    either the old complete content or the new complete content -- never a partial write."""
    dest = tmp_path / "shared_snapshot.json"
    payload = ('{"writer": 1, "padding": "' + "x" * 5000 + '"}').encode()
    write_bytes_atomic(dest, payload)

    stop = threading.Event()
    read_errors: list[Exception] = []

    def writer() -> None:
        while not stop.is_set():
            write_bytes_atomic(dest, payload)

    def reader() -> None:
        for _ in range(500):
            try:
                json.loads(dest.read_bytes())
            except Exception as e:  # noqa: BLE001 - collecting every failure mode, not one
                read_errors.append(e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        writer_futures = [pool.submit(writer) for _ in range(3)]
        reader_futures = [pool.submit(reader) for _ in range(4)]
        for f in reader_futures:
            f.result()
        stop.set()
        for f in writer_futures:
            f.result()

    assert read_errors == [], (
        f"{len(read_errors)} reads hit a torn/partial write: {read_errors[:3]}"
    )
    leftover_parts = list(Path(tmp_path).glob("*.part"))
    assert leftover_parts == [], f"temp files leaked: {leftover_parts}"
