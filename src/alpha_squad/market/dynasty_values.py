"""Normalizes DynastyProcess's `values-players.csv` (the operating substitute for the
blocked KeepTradeCut site — docs/DECISIONS.md D3) into `dynasty_values`, identity-joined via
`fantasypros_id` (verified 97.6% coverage: 681/698 real rows). Unlike `fp_ecr_history`, this
file is a re-scraped-in-place current snapshot, not a historical time series, so the table
holds one row per player and is replaced wholesale on each build rather than accumulated."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot
from alpha_squad.sources.base import utcnow


def build_dynasty_values(con: duckdb.DuckDBPyConnection, settings: Settings) -> int:
    snap = require_snapshot(con, "dynastyprocess", "dynasty_values_players")
    src = reader_expr(snap["local_path"])
    snapshot_id = snap["snapshot_id"]

    rows = con.execute(
        f"""
        INSERT INTO dynasty_values
            (player_id, scrape_date, team, age, ecr_pos, ecr_1qb, ecr_2qb, value_1qb,
             value_2qb, source_snapshot_id, updated_at)
        SELECT
            m.player_id, CAST(d.scrape_date AS DATE), d.team, d.age, d.ecr_pos, d.ecr_1qb,
            d.ecr_2qb, d.value_1qb, d.value_2qb, ?, ?
        FROM {src} d
        JOIN player_id_map m ON m.id_type = 'fantasypros_id' AND m.id_value = CAST(d.fp_id AS VARCHAR)
        ON CONFLICT (player_id) DO UPDATE SET
            scrape_date = excluded.scrape_date, team = excluded.team, age = excluded.age,
            ecr_pos = excluded.ecr_pos, ecr_1qb = excluded.ecr_1qb, ecr_2qb = excluded.ecr_2qb,
            value_1qb = excluded.value_1qb, value_2qb = excluded.value_2qb,
            source_snapshot_id = excluded.source_snapshot_id, updated_at = excluded.updated_at
        RETURNING player_id
        """,
        [snapshot_id, utcnow()],
    ).fetchall()
    return len(rows)
