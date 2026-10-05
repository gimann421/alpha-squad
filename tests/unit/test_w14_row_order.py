"""W14 A2: restoring the canonical physical row order changes order only, never rows or values."""

from __future__ import annotations

import duckdb

from scripts.research import w14_row_order as ro

DDL = "CREATE TABLE toy (player_id VARCHAR, season INTEGER, week INTEGER, x DOUBLE, PRIMARY KEY (player_id, season, week))"
ROWS = [("b", 2024, 1, 1.0), ("a", 2024, 1, 2.0), ("c", 2025, 3, 3.0), ("a", 2025, 2, 4.0)]


def _order(con):
    return [
        tuple(r)
        for r in con.execute("SELECT player_id, season, week, x FROM toy ORDER BY rowid").fetchall()
    ]


def test_restore_puts_canonical_rows_first_in_canonical_order(tmp_path):
    canon = tmp_path / "canon.duckdb"
    c = duckdb.connect(str(canon))
    c.execute(DDL)
    c.executemany("INSERT INTO toy VALUES (?, ?, ?, ?)", ROWS)
    c.close()
    t = duckdb.connect(str(tmp_path / "target.duckdb"))
    t.execute(DDL)
    extra = [("z", 2026, 1, 9.0), ("y", 2026, 1, 8.0)]
    t.executemany("INSERT INTO toy VALUES (?, ?, ?, ?)", [extra[0], *reversed(ROWS), extra[1]])
    rep = ro.restore(t, str(canon), "toy", ("player_id", "season", "week"))
    assert rep == {"rows": 6, "canonical_rows": 4}
    assert _order(t) == [*ROWS, *extra]


def test_restore_never_changes_a_value(tmp_path):
    canon = tmp_path / "canon.duckdb"
    c = duckdb.connect(str(canon))
    c.execute(DDL)
    c.executemany("INSERT INTO toy VALUES (?, ?, ?, ?)", ROWS)
    c.close()
    t = duckdb.connect(str(tmp_path / "target.duckdb"))
    t.execute(DDL)
    changed = [(p, s, w, x + 0.5) for p, s, w, x in reversed(ROWS)]
    t.executemany("INSERT INTO toy VALUES (?, ?, ?, ?)", changed)
    ro.restore(t, str(canon), "toy", ("player_id", "season", "week"))
    # the target keeps its own values; only the order follows the canonical database
    assert _order(t) == [(p, s, w, x + 0.5) for p, s, w, x in ROWS]
