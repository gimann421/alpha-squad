"""W14 amendment A2: put the isolated 2026 database's <= 2025 rows back in the canonical order.

Production's `features build` re-upserts every `player_week_features` / `team_week_features` row,
which rewrites their physical order. Production's loader reads without ORDER BY and CatBoost is
order-sensitive, so the same 2015-2025 data in a new order trains a different model. This restores
the canonical database's physical (rowid) order for every row the canonical database has, appends
the rest (2026) in the target's own order, and verifies the loader sequence afterwards. It changes
row order only: never a value, never a row set.

    uv run python scripts/research/w14_row_order.py --db data/w14/alpha_squad_2026.duckdb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.models.established.data import load_position_week_data  # noqa: E402

CANONICAL_DB = "data/alpha_squad.duckdb"
TABLES: dict[str, tuple[str, ...]] = {
    "player_week_features": ("player_id", "season", "week"),
    "team_week_features": ("team", "season", "week"),
}
POSITIONS = ("QB", "RB", "WR", "TE")


def restore(
    con: duckdb.DuckDBPyConnection, canonical: str, table: str, keys: tuple[str, ...]
) -> dict:
    """Reorder `table` in place: canonical rows in canonical rowid order, then the rest in the
    table's current order. Returns row counts; raises if the row set or any value changed."""
    k = ", ".join(keys)
    cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
    collist = ", ".join(cols)
    con.execute(f"ATTACH '{canonical}' AS _canon (READ_ONLY)")
    try:
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE _w14_ord AS SELECT {k}, rowid AS _canon_r "
            f"FROM _canon.{table}"
        )
        con.execute(
            f"CREATE OR REPLACE TEMP TABLE _w14_new AS SELECT t.*, o._canon_r, t.rowid AS _own_r "
            f"FROM {table} t LEFT JOIN _w14_ord o USING ({k})"
        )
        before = con.execute(f"SELECT count(*), sum(hash({collist})) FROM {table}").fetchone()
        n_canon = con.execute(
            "SELECT count(*) FROM _w14_new WHERE _canon_r IS NOT NULL"
        ).fetchone()[0]
        # two autocommitted statements: re-inserting a deleted primary key inside the same
        # transaction trips DuckDB's index; the before/after check below guards the gap
        con.execute(f"DELETE FROM {table}")
        con.execute(
            f"INSERT INTO {table} ({collist}) SELECT {collist} FROM _w14_new "
            "ORDER BY (_canon_r IS NULL), _canon_r, _own_r"
        )
        after = con.execute(f"SELECT count(*), sum(hash({collist})) FROM {table}").fetchone()
        if before != after:
            raise RuntimeError(f"{table}: row set or values changed by the reorder")
        return {"rows": int(after[0]), "canonical_rows": int(n_canon)}
    finally:
        con.execute("DROP TABLE IF EXISTS _w14_ord")
        con.execute("DROP TABLE IF EXISTS _w14_new")
        con.execute("DETACH _canon")


def loader_matches(con, canonical_con, through: int = 2025) -> dict[str, bool]:
    """Does production's own loader return the canonical 2015-`through` sequence, row for row?"""
    out = {}
    for pos in POSITIONS:
        a = load_position_week_data(canonical_con, pos, 2015, through)
        b = load_position_week_data(con, pos, 2015, through)
        out[pos] = list(zip(a.player_id, a.season, a.week, strict=True)) == list(
            zip(b.player_id, b.season, b.week, strict=True)
        ) and a.equals(b)
    return out


def restore_all(con: duckdb.DuckDBPyConnection, canonical: str = CANONICAL_DB) -> dict:
    report = {t: restore(con, canonical, t, keys) for t, keys in TABLES.items()}
    canon = duckdb.connect(canonical, read_only=True)
    try:
        report["loader_matches_canonical"] = loader_matches(con, canon)
    finally:
        canon.close()
    if not all(report["loader_matches_canonical"].values()):
        raise RuntimeError(f"loader order still differs: {report['loader_matches_canonical']}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/w14/alpha_squad_2026.duckdb")
    ap.add_argument("--canonical", default=CANONICAL_DB)
    args = ap.parse_args()
    con = duckdb.connect(args.db)
    print(restore_all(con, args.canonical))
    con.close()


if __name__ == "__main__":
    main()
