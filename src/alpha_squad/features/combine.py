"""Normalizes nflverse `combine` into `combine_results`, identity-joined via `pfr_id`
through `player_id_map` — combine carries no gsis_id at all (verified in M2/identity/
crosswalk.py), so this is the same bridge pattern used there and in M3's snap-count join."""

from __future__ import annotations

import duckdb

from alpha_squad.config.settings import Settings
from alpha_squad.identity.canonical import reader_expr, require_snapshot


def build_combine_results(con: duckdb.DuckDBPyConnection, settings: Settings) -> int:
    snap = require_snapshot(con, "nflverse", "combine")
    src = reader_expr(snap["local_path"])
    rows = con.execute(
        f"""
        INSERT INTO combine_results
            (player_id, draft_year, position, forty, bench, vertical, broad_jump, cone,
             shuttle, height, weight, school, source_snapshot_id)
        SELECT
            m.player_id, c.draft_year, c.pos, c.forty, c.bench, c.vertical, c.broad_jump,
            c.cone, c.shuttle,
            -- ht is a feet-inches string ("6-0", verified against real data), not a number.
            TRY_CAST(split_part(c.ht, '-', 1) AS DOUBLE) * 12
                + TRY_CAST(split_part(c.ht, '-', 2) AS DOUBLE) AS height,
            c.wt, c.school, ?
        FROM {src} c
        JOIN player_id_map m ON m.id_type = 'pfr_id' AND m.id_value = c.pfr_id
        ON CONFLICT (player_id) DO UPDATE SET
            draft_year = excluded.draft_year, position = excluded.position,
            forty = excluded.forty, bench = excluded.bench, vertical = excluded.vertical,
            broad_jump = excluded.broad_jump, cone = excluded.cone, shuttle = excluded.shuttle,
            height = excluded.height, weight = excluded.weight, school = excluded.school,
            source_snapshot_id = excluded.source_snapshot_id
        RETURNING player_id
        """,
        [snap["snapshot_id"]],
    ).fetchall()
    return len(rows)
