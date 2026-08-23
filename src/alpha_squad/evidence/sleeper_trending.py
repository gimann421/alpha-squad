"""Real-time Sleeper community add/drop momentum as a structured Weak-tier evidence signal
(PRODUCT_SPEC.md's Weak tier explicitly includes "social media"/buzz-type signals; this was
undevelopable under D5/D22 since no such source was reachable at all -- see docs/DECISIONS.md
D31/D32).

Architecturally distinct from the four detectors in evidence/events.py: those reconstruct
evidence for an arbitrary *past* week from already-ingested nflverse snapshots (pure over
stored data, no network I/O of their own). Sleeper's trending endpoints have no lookback API
-- every call returns only *current* activity, with no way to ask what was trending in some
past week -- so this module fetches live itself and always represents "evidence as of right
now," attributed to whatever (season, week) the caller says it should inform. `week=1` is the
natural choice before a season has started (this is genuinely useful there: it is the first
evidence signal available at the same preseason horizon as M8's EDGE, unlike the in-season-only
Strong-tier detectors -- see D23's documented horizon mismatch)."""

from __future__ import annotations

import json

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.evidence.events import record_event
from alpha_squad.sources.sleeper import SleeperSource
from alpha_squad.storage.snapshots import record_snapshot

_DATASETS = (("trending_adds", 1), ("trending_drops", -1))


def detect_sleeper_trending(
    con: duckdb.DuckDBPyConnection, settings: Settings, season: int, week: int
) -> int:
    sleeper = SleeperSource(settings)
    n = 0
    for dataset, direction in _DATASETS:
        snap = sleeper.fetch(dataset)
        record_snapshot(con, snap)
        entries = json.loads(snap.local_path.read_bytes())

        for rank, entry in enumerate(entries, start=1):
            row = con.execute(
                "SELECT player_id FROM player_id_map WHERE id_type = 'sleeper_id' AND id_value = ?",
                [str(entry["player_id"])],
            ).fetchone()
            if row is None:
                continue
            player_id = row[0]
            direction_word = "add" if direction > 0 else "drop"
            record_event(
                con,
                player_id=player_id,
                season=season,
                week=week,
                event_date=snap.captured_at.date().isoformat(),
                event_type="social_media_buzz",
                source=f"sleeper_{dataset}",
                direction=direction,
                structured_impact={
                    "rank": rank,
                    "count": entry["count"],
                    "sleeper_player_id": entry["player_id"],
                },
                summary=(
                    f"#{rank} trending {direction_word} on Sleeper "
                    f"({entry['count']} real owner actions in the lookback window)"
                ),
                source_snapshot_id=snap.snapshot_id,
            )
            n += 1
    return n
