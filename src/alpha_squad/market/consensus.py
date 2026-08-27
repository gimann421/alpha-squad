"""Builds `market_snapshot` from DynastyProcess's `fp_ecr_history` (the operating substitute
for the blocked FantasyPros API — docs/DECISIONS.md D3), identity-joined via `fantasypros_id`
(verified 93.8% coverage on `ecr_type='ro'` — D16). M4 only needs the 'ro' (redraft-overall,
1QB) series for a general-purpose ECR-implied baseline; M8 extends this with the 2QB-aware
series (`rsf`/`dsf`) the target league's EDGE calculation actually needs (D21) — both are
overall, cross-position ranks, verified against real data, capturing exactly how a 2QB
league values QBs differently than 'ro' does.

`build_live_fantasypros_snapshot` (D38) captures the live FantasyPros API directly, as a
separate `source='fantasypros_live'` series in the same table — never blended into the rows
above, so nothing about the historical DynastyProcess-sourced series (or anything that reads
it for backtesting) changes. The live API has no lookback of its own, so this is a
today-only capture, accumulated forward from whenever it first runs — the same pattern
`evidence/sleeper_trending.py` (D32) established for a live-only source with no history API."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot
from alpha_squad.sources.fantasypros import FantasyProsSource
from alpha_squad.storage.snapshots import record_snapshot

DEFAULT_ECR_TYPES = ("ro", "do", "rsf", "dsf")


def build_market_snapshot(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    ecr_types: tuple[str, ...] = DEFAULT_ECR_TYPES,
) -> int:
    snap = require_snapshot(con, "dynastyprocess", "fp_ecr_history")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    rows = con.execute(
        f"""
        INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst, source_snapshot_id, page_type)
        SELECT
            m.player_id, CAST(e.scrape_date AS DATE), e.ecr_type, e.pos, e.ecr, e.best, e.worst, ?,
            COALESCE(e.page_type, '')
        FROM {src} e
        JOIN player_id_map m ON m.id_type = 'fantasypros_id' AND m.id_value = CAST(e.id AS VARCHAR)
        WHERE e.ecr_type = ANY(?) AND e.ecr IS NOT NULL
        ON CONFLICT (player_id, scrape_date, ecr_type, page_type, source) DO UPDATE SET
            position = excluded.position,
            ecr_rank = excluded.ecr_rank,
            ecr_best = excluded.ecr_best,
            ecr_worst = excluded.ecr_worst,
            source_snapshot_id = excluded.source_snapshot_id
        RETURNING player_id
        """,
        [snapshot_id, list(ecr_types)],
    ).fetchall()

    # Retire rows this rebuild has just superseded. A pre-D56 database carries its existing
    # DynastyProcess rows forward with page_type '' (the migration refuses to invent a page it
    # cannot know -- see storage/schema.py), and the widened PRIMARY KEY means those un-labelled
    # rows no longer collide with the re-ingested, properly-labelled ones: without this they
    # would sit alongside them as silent duplicates and every unscoped read would double-count.
    # Scoped to this source and to the ecr_types actually just rebuilt, so it can never touch
    # `fantasypros_live` rows (D38: a today-only capture with no lookback -- genuinely
    # irreplaceable, never reproducible by re-running this).
    if rows:
        con.execute(
            "DELETE FROM market_snapshot "
            "WHERE source = 'dynastyprocess' AND page_type = '' AND ecr_type = ANY(?)",
            [list(ecr_types)],
        )
    return len(rows)


# FantasyPros's own real response labels this 'Draft' regardless of the `type` query param
# requested (verified empirically 2026-08-23, D38 — this key's free/public tier only serves
# Draft-type consensus rankings; `type=ROS` is silently ignored, not rejected). Tagged
# 'draft_overall' rather than something implying ROS, so this table never claims data this
# key's tier doesn't actually provide.
LIVE_ECR_TYPE = "draft_overall"

# The live API returns one ranking list, not DynastyProcess's many-pages-per-ecr_type mirror,
# so its `page_type` (D56) is a single constant naming what that list actually is. Recorded
# explicitly rather than left '' so this series is addressable the same way as every other.
LIVE_PAGE_TYPE = "live-draft-overall"


def build_live_fantasypros_snapshot(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    *,
    season: int = 2026,
) -> int:
    fp = FantasyProsSource(settings)
    snap = fp.fetch("consensus_rankings", season=season, position="ALL", type="ROS", scoring="PPR")
    record_snapshot(con, snap)

    body = json.loads(snap.local_path.read_bytes())
    players = body.get("players", [])
    if not players:
        return 0

    df = pd.DataFrame(
        {
            "fp_player_id": [str(p["player_id"]) for p in players],
            "scrape_date": [snap.captured_at.date()] * len(players),
            "position": [p.get("player_position_id") for p in players],
            "ecr_rank": [p.get("rank_ecr") for p in players],
            "ecr_best": [p.get("rank_min") for p in players],
            "ecr_worst": [p.get("rank_max") for p in players],
        }
    )
    con.register("fp_live_df", df)
    try:
        rows = con.execute(
            """
            INSERT INTO market_snapshot
                (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst, source_snapshot_id, source, page_type)
            SELECT
                m.player_id, d.scrape_date, ?, d.position, d.ecr_rank, d.ecr_best, d.ecr_worst, ?, 'fantasypros_live',
                ?
            FROM fp_live_df d
            JOIN player_id_map m ON m.id_type = 'fantasypros_id' AND m.id_value = d.fp_player_id
            WHERE d.ecr_rank IS NOT NULL
            ON CONFLICT (player_id, scrape_date, ecr_type, page_type, source) DO UPDATE SET
                position = excluded.position,
                ecr_rank = excluded.ecr_rank,
                ecr_best = excluded.ecr_best,
                ecr_worst = excluded.ecr_worst,
                source_snapshot_id = excluded.source_snapshot_id
            RETURNING player_id
            """,
            [LIVE_ECR_TYPE, snap.snapshot_id, LIVE_PAGE_TYPE],
        ).fetchall()
    finally:
        con.unregister("fp_live_df")
    return len(rows)
