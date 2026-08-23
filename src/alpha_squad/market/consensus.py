"""Builds `market_snapshot` from DynastyProcess's `fp_ecr_history` (the operating substitute
for the blocked FantasyPros API — docs/DECISIONS.md D3), identity-joined via `fantasypros_id`
(verified 93.8% coverage on `ecr_type='ro'` — D16). M4 only needs the 'ro' (redraft-overall,
1QB) series for a general-purpose ECR-implied baseline; M8 extends this with the 2QB-aware
series (`rsf`/`dsf`) the target league's EDGE calculation actually needs (D21) — both are
overall, cross-position ranks, verified against real data, capturing exactly how a 2QB
league values QBs differently than 'ro' does."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot

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
        INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst, source_snapshot_id)
        SELECT
            m.player_id, CAST(e.scrape_date AS DATE), e.ecr_type, e.pos, e.ecr, e.best, e.worst, ?
        FROM {src} e
        JOIN player_id_map m ON m.id_type = 'fantasypros_id' AND m.id_value = CAST(e.id AS VARCHAR)
        WHERE e.ecr_type = ANY(?) AND e.ecr IS NOT NULL
        ON CONFLICT (player_id, scrape_date, ecr_type) DO UPDATE SET
            position = excluded.position,
            ecr_rank = excluded.ecr_rank,
            ecr_best = excluded.ecr_best,
            ecr_worst = excluded.ecr_worst,
            source_snapshot_id = excluded.source_snapshot_id
        RETURNING player_id
        """,
        [snapshot_id, list(ecr_types)],
    ).fetchall()
    return len(rows)
