"""W11 validity and leakage gates (pre-registration §11). Stage 1's gates must pass before stage 1
is read; all gates must pass before stage 2 is read.

    uv run python scripts/research/w11_validity_gates.py --stage 1 --repro-summary <record>
    uv run python scripts/research/w11_validity_gates.py --stage 2 --repro-summary <record>
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, context  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly import rolechange as rc  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w11_mechanism as w11m  # noqa: E402
from scripts.research.w7_validity_gates import _wire  # noqa: E402
from scripts.research.w9_validity_gates import FORBIDDEN_IN_FEATURES, _eq  # noqa: E402
from scripts.research.w10_validity_gates import _Reversed  # noqa: E402

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
ARM_B = "ALPHA_PLUS_HISTORICAL"
ARM_N = "ALPHA_PLUS_HISTORY_ROLE_NULL"
N_REDACT = 40
N_SCRAMBLE = 10
N_SQL = 300
N_UPSTREAM = 10
STAGE1 = Path("scripts/research/w11_mechanism.py")
STAGE2 = Path("scripts/research/w11_role_model.py")
ROLE_COLS = [*rc.ROLE_FEATURES, *(f"cls_{n}" for n in rc.THRESHOLDS)]
KEYS = ["player_id", "season", "week"]


def _before(db: str, season: int, week: int, scramble: bool = False):
    """A database whose `player_week_stats` holds only rows before (season, week) -- or, with
    `scramble`, holds every row but with (season, week)-and-later outcomes replaced by noise."""
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    if not scramble:
        con.execute(
            "CREATE VIEW player_week_stats AS SELECT * FROM src.player_week_stats "
            f"WHERE season < {season} OR (season = {season} AND week < {week})"
        )
        return con
    later = f"(season = {season} AND week >= {week})"
    noise = "(hash(player_id || '-' || CAST(week AS VARCHAR) || '-{c}') % 1000) / 25.0"
    con.execute(
        "CREATE TABLE player_week_stats AS SELECT * REPLACE ("
        f"CASE WHEN {later} THEN CAST({noise.format(c='t')} AS INTEGER) ELSE targets END "
        "AS targets, "
        f"CASE WHEN {later} THEN CAST({noise.format(c='c')} AS INTEGER) ELSE carries END "
        "AS carries, "
        f"CASE WHEN {later} THEN {noise.format(c='n')} / 40.0 ELSE offense_snap_pct END "
        "AS offense_snap_pct, "
        f"CASE WHEN {later} THEN {noise.format(c='p')} ELSE fantasy_points_ppr END "
        "AS fantasy_points_ppr) FROM src.player_week_stats"
    )
    return con


def _rows_equal(a: pd.DataFrame, b: pd.DataFrame) -> int:
    """Number of (key, column) cells that differ between two role tables on the same keys."""
    a = a.set_index(KEYS).sort_index()
    b = b.set_index(KEYS).sort_index()
    if list(a.index) != list(b.index):
        return max(len(a), 1)
    return sum(0 if _eq(x, y) else 1 for c in ROLE_COLS for x, y in zip(a[c], b[c], strict=True))


def _cells_mismatch(mine: dict, theirs: dict) -> tuple[int, int]:
    if set(mine) != set(theirs) or not mine:
        return 0, 1
    n = bad = 0
    for k, row in theirs.items():
        for m, v in row.items():
            if m in mine[k]:
                n += 1
                bad += int(mine[k][m] != v)
    return n, bad


def _calls(path: Path):
    tree = ast.parse(path.read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "train_with_extra_features"
    ]
    arms = sorted(
        kw.value.id
        for c in calls
        for kw in c.keywords
        if kw.arg == "arm" and isinstance(kw.value, ast.Name)
    )
    frames = sorted(ast.unparse(c.args[1]) for c in calls if len(c.args) > 1)
    assigns = {
        t.id: ast.unparse(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    return calls, arms, frames, assigns


def _rerun(runner: Path, db: str, committed: str, extra: list[str]) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rerun.json"
        subprocess.run(
            [sys.executable, str(runner), "--db", db, "--out", str(out), *extra],
            check=True,
            capture_output=True,
        )
        a = hashlib.sha256(out.read_bytes()).hexdigest()
    return a, hashlib.sha256(Path(committed).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--mechanism", default="reports/weekly/w11_mechanism.json")
    ap.add_argument("--results", default="reports/weekly/w11_results.json")
    ap.add_argument("--w10", default="reports/weekly/w10_results.json")
    ap.add_argument("--repro-summary", default=None)
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    r10 = json.loads(Path(args.w10).read_text())
    s1 = json.loads(Path(args.mechanism).read_text())
    failures: list[str] = []

    # --- G1 parity ------------------------------------------------------------------------------
    control = arms_mod.train_with_extra_features(con, pd.DataFrame(columns=KEYS), [])
    stored = {
        k: v for k, v in arms_mod.load_production_predictions(con).items() if k in control.by_key
    }
    fid = arms_mod.compare_to_production(control, stored)
    print(
        f"G1  parity             : {fid['exact_matches']:,}/{fid['n_shared']:,} exact, "
        f"max abs diff {fid['max_abs_diff']}"
    )
    if fid["exact_share"] != 1.0 or fid["only_in_trained"] or fid["only_in_stored"]:
        failures.append("G1")

    # --- G2 the current role is pre-Friday --------------------------------------------------------
    panel = op.build_panel(con, POSITIONS)
    keys = panel[KEYS]
    dur = w9.durable_table(con)
    roles = w11m.role_table(con, dur, keys)
    weeks = [(s.season, s.week) for s in audit.week_coverage(con, SEASONS).snapshots]
    sample = random.Random(11).sample(weeks, N_REDACT)
    moved = checked = 0
    for season, week in sorted(sample):
        k = keys[(keys.season == season) & (keys.week == week)]
        red = _before(args.db, season, week)
        try:
            rd = w11m.role_table(red, w9.durable_table(red, through=season), k)
        finally:
            red.close()
        mine = roles.merge(k, on=KEYS)
        checked += len(mine)
        moved += _rows_equal(mine, rd)
    print(
        f"G2  role is pre-Friday : {N_REDACT} (season, week) pairs rebuilt from rows before the "
        f"week ({checked:,} player-weeks): values moved {moved}"
    )
    if moved or not checked:
        failures.append("G2")

    # --- G3 arm B is W10's -----------------------------------------------------------------------
    n3 = bad3 = 0
    sources = [("stage 1", s1)]
    if args.stage == 2:
        sources.append(("stage 2", json.loads(Path(args.results).read_text())))
    for label, res in sources:
        for tag in ("full_ppr", "half_ppr"):
            mine_all = res[tag]["b_cells"] if label == "stage 1" else res[tag]["cells"]
            for pos in (*POSITIONS, *(("FLEX",) if label == "stage 2" else ())):
                n, b = _cells_mismatch(
                    mine_all.get(f"{pos}|{ARM_B}", {}), r10[tag]["cells"][f"{pos}|{ARM_B}"]
                )
                n3, bad3 = n3 + n, bad3 + b
    print(
        f"G3  B is W10's arm     : {n3:,} per-week values vs W10's committed cells, mismatches {bad3}"
    )
    if bad3 or not n3:
        failures.append("G3")

    # --- G4 no future information ----------------------------------------------------------------
    bad_tokens = [
        f for f in rc.ROLE_FEATURES if any(t in f for t in (*FORBIDDEN_IN_FEATURES, "ecr"))
    ]
    moved4 = control4 = checked4 = 0
    for season, week in sorted(
        random.Random(12).sample([w for w in weeks if w[1] < 17], N_SCRAMBLE)
    ):
        k = keys[(keys.season == season) & (keys.week == week)]
        k_next = keys[(keys.season == season) & (keys.week == week + 1)]
        sc = _before(args.db, season, week, scramble=True)
        try:
            sd = w9.durable_table(sc, through=season)
            moved4 += _rows_equal(roles.merge(k, on=KEYS), w11m.role_table(sc, sd, k))
            control4 += int(
                _rows_equal(roles.merge(k_next, on=KEYS), w11m.role_table(sc, sd, k_next)) > 0
            )
        finally:
            sc.close()
        checked4 += len(k)
    print(
        f"G4  no future info     : forbidden tokens {bad_tokens or 'none'}; role values moved when "
        f"week-w-and-later outcomes were scrambled: {moved4} ({checked4:,} player-weeks); the "
        f"scramble reached week w + 1 (positive control) in {control4}/{N_SCRAMBLE} pairs"
    )
    if bad_tokens or moved4 or control4 != N_SCRAMBLE:
        failures.append("G4")

    # --- G5 ECR never a feature -------------------------------------------------------------------
    c1, a1, f1, as1 = _calls(STAGE1)
    c2, a2, f2, as2 = _calls(STAGE2)
    ok1 = (len(c1), a1, f1) == (1, ["ARM_B"], ["w9.durable_panel(panel, dur, shuffle=False)"])
    ok2 = (
        (len(c2), a2, f2) == (2, ["ARM_C", "ARM_N"], ["frame_c", "frame_n"])
        and as2.get("frame_c", "").startswith("dp.merge(rp,")
        and as2.get("frame_n", "").startswith("dp.merge(rpn,")
        and as2.get("dp") == "w9.durable_panel(panel, dur, shuffle=False)"
        and as2.get("rp") == "w11m.role_panel(panel, roles, shuffle=False)"
        and as2.get("rpn") == "w11m.role_panel(panel, roles, shuffle=True)"
    )
    tables = sorted(set(re.findall(r"FROM\s+(\w+)", inspect.getsource(w11m.role_table))))
    ecr_names = [
        f
        for f in (*FULL_FEATURES, *mech.DURABLE_FEATURES, *rc.ROLE_FEATURES)
        if any(t in f.lower() for t in ("ecr", "market", "adp", "preseason", "rank_e"))
    ]
    print(
        f"G5  ECR never a feature: stage 1 calls {len(c1)} {a1} {f1}; stage 2 calls {len(c2)} {a2} "
        f"{f2}; role table reads {tables}; ECR-like names {ecr_names or 'none'}"
    )
    if not (ok1 and ok2) or tables != ["player_week_stats"] or ecr_names:
        failures.append("G5")

    # --- G6 walk-forward ------------------------------------------------------------------------
    leaks = 0
    for position in POSITIONS:
        for season in SEASONS:
            frame = arms_mod.load_position_week_data(
                con, position, arms_mod.MIN_TRAIN_SEASON, season - 1
            )
            leaks += int(not frame.empty and int(frame.season.max()) >= season)
    print(f"G6  walk-forward       : training frames containing the predicted season: {leaks}")
    if leaks:
        failures.append("G6")

    # --- G7 joins and alignment -------------------------------------------------------------------
    dup = int(roles.duplicated(KEYS).sum())
    m = panel.merge(roles[[*KEYS, "n_current"]], on=KEYS)
    gp = int((m.n_current != m.games_played_prior).sum())
    pool = roles[(roles.n_current >= 1) & roles.role_d_opp.notna()].sort_values(KEYS)
    sample7 = random.Random(13).sample(
        list(
            zip(
                pool.player_id,
                pool.season,
                pool.week,
                pool.role_d_opp,
                pool.role_d_snap,
                strict=True,
            )
        ),
        N_SQL,
    )
    wrong = 0
    for pid, season, week, d_opp, d_snap in sample7:
        cur = con.execute(
            "SELECT avg(coalesce(targets, 0) + coalesce(carries, 0)), avg(offense_snap_pct) FROM ("
            "SELECT * FROM player_week_stats WHERE player_id = ? AND season = ? AND week < ? "
            "ORDER BY week DESC LIMIT 3)",
            [pid, int(season), int(week)],
        ).fetchone()
        pri = con.execute(
            "SELECT avg(coalesce(targets, 0) + coalesce(carries, 0)), avg(offense_snap_pct) "
            "FROM player_week_stats WHERE player_id = ? AND season = ?",
            [pid, int(season) - 1],
        ).fetchone()
        e_opp = cur[0] - pri[0]
        e_snap = None if cur[1] is None or pri[1] is None else cur[1] - pri[1]
        wrong += int(abs(e_opp - d_opp) > 1e-9)
        wrong += int(
            not (
                (e_snap is None and pd.isna(d_snap))
                or (e_snap is not None and abs(e_snap - d_snap) <= 1e-9)
            )
        )
    print(
        f"G7  joins / alignment  : duplicate role keys {dup}; current-game count != "
        f"games_played_prior on {gp} of {len(m):,} panel rows; role deltas wrong in {wrong} of "
        f"{2 * N_SQL} independent SQL checks (the runners also abort on any universe mismatch or "
        "attribution that does not sum)"
    )
    if dup or gp or wrong:
        failures.append("G7")

    # --- G8 order-free ----------------------------------------------------------------------------
    rev = w11m.role_table(_Reversed(con), dur, keys)
    diff8 = _rows_equal(roles, rev)
    print(f"G8  order-free table   : role values differing with input reversed: {diff8}")
    if diff8:
        failures.append("G8")

    # --- G9 universe and arm A (stage 2) ----------------------------------------------------------
    if args.stage == 2:
        res = json.loads(Path(args.results).read_text())
        n9 = bad9 = 0
        for tag in ("full_ppr", "half_ppr"):
            for pos in (*POSITIONS, "FLEX"):
                for b in ("CF_A", "ECR"):
                    n, b_ = _cells_mismatch(
                        res[tag]["cells"].get(f"{pos}|{b}", {}), r10[tag]["cells"][f"{pos}|{b}"]
                    )
                    n9, bad9 = n9 + n, bad9 + b_
        weeks9 = (res["full_ppr"]["n_weeks"], res["half_ppr"]["n_weeks"])
        print(
            f"G9  universe / arm A   : {n9:,} values vs W10's committed A and ECR cells, mismatches {bad9}; weeks {weeks9}"
        )
        if bad9 or not n9 or weeks9 != (79, 79):
            failures.append("G9")
    else:
        weeks9 = (s1["full_ppr"]["n_weeks"], s1["half_ppr"]["n_weeks"])
        print(
            f"G9  universe           : stage-1 weeks {weeks9} (A/ECR cells are checked in stage 2)"
        )
        if weeks9 != (79, 79):
            failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism        : SKIPPED")
    else:
        runs = [(STAGE1, args.mechanism, [])]
        if args.stage == 2:
            runs.append((STAGE2, args.results, ["--mechanism", args.mechanism]))
        parts = []
        for runner, committed, extra in runs:
            a, b = _rerun(runner, args.db, committed, extra)
            parts.append(
                f"{runner.stem} {a[:16]} vs {b[:16]} -> {'identical' if a == b else 'DIFFERENT'}"
            )
            if a != b:
                failures.append(f"G10:{runner.stem}")
        print("G10 determinism        : " + "; ".join(parts))

    # --- G11 upstream ---------------------------------------------------------------------------
    if args.repro_summary:
        lines = Path(args.repro_summary).read_text().strip().splitlines()
        ok = len(lines) == N_UPSTREAM and all("BYTE-IDENTICAL" in ln for ln in lines)
        print(
            f"G11 upstream           : {len(lines)} reproduced artifacts, all byte-identical: {ok}"
        )
        if not ok:
            failures.append("G11")
    else:
        print("G11 upstream           : no reproduction record supplied")
        failures.append("G11")

    # --- G12 null arm (stage 2) -------------------------------------------------------------------
    if args.stage == 2:
        paired = res["full_ppr"]["summary"]["all"]["paired"]
        parts = []
        for pos in POSITIONS:
            for mt in ("capture@5", "capture@10"):
                r = paired[f"{pos}|{ARM_N}_vs_{pos}|{ARM_B}"][mt]
                ok = r["ci_low"] <= 0.0 <= r["ci_high"]
                parts.append(
                    f"{pos} {mt} {r['mean_diff']:+.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}]"
                    f"{'' if ok else ' FAIL'}"
                )
                if not ok:
                    failures.append(f"G12:{pos}:{mt}")
        print("G12 null arm           : " + " | ".join(parts))

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
