"""W13 validity and leakage gates (pre-registration §10). All must pass before any W13 result is read.

uv run python scripts/research/w13_validity_gates.py --repro-summary <W5-W12 record>
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, context  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly import timestamped as ts  # noqa: E402
from alpha_squad.identity.canonical import reader_expr  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w12_timestamped as w12  # noqa: E402
from scripts.research import w13_injury_flex as w13  # noqa: E402
from scripts.research.w7_validity_gates import _wire  # noqa: E402
from scripts.research.w9_validity_gates import _eq  # noqa: E402

POSITIONS = w13.POSITIONS
SEASONS = w13.DEFAULT_SEASONS
KEYS = w13.KEYS
OWN = w13.OWN
RUNNER = Path("scripts/research/w13_injury_flex.py")
N_ADVERSARIAL = 40
N_SQL = 300
N_UPSTREAM = 13
N_WEEKS = 63


def _diff(a: pd.DataFrame, b: pd.DataFrame, cols) -> int:
    a = a.set_index(KEYS).sort_index()
    b = b.set_index(KEYS).sort_index()
    if list(a.index) != list(b.index):
        return max(len(a), 1)
    return sum(0 if _eq(x, y) else 1 for c in cols for x, y in zip(a[c], b[c], strict=True))


def _cells(mine: dict, theirs: dict) -> tuple[int, int]:
    theirs = {k: v for k, v in theirs.items() if int(k.split("-")[0]) in SEASONS}
    if set(mine) != set(theirs) or not mine:
        return 0, 1
    n = bad = 0
    for k, row in theirs.items():
        for m, v in row.items():
            if m in mine[k]:
                n += 1
                bad += int(mine[k][m] != v)
    return n, bad


def _num(v) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w13_results.json")
    ap.add_argument("--w10", default="reports/weekly/w10_results.json")
    ap.add_argument("--repro-summary", default=None)
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, max(SEASONS) + 1)))
    res = json.loads(Path(args.results).read_text())
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

    # --- G2 pre-cutoff --------------------------------------------------------------------------
    snaps = audit.week_coverage(con, SEASONS).snapshots
    fridays = w12.cutoff_fridays(con, snaps)
    rows, prov = w12.injury_rows(con)
    panel = op.build_panel(con, POSITIONS)
    inj = w12.injury_table(con, panel, fridays, rows, strict=False)
    cands = sorted(
        (s, w, t)
        for (s, w, t), rs in rows.items()
        if s in SEASONS
        and (s, w) in fridays
        and any(r["position"] in POSITIONS and r["player_id"] for r in rs)
    )
    moved_late = set_early = checked = 0
    for s, w, t in random.Random(31).sample(cands, N_ADVERSARIAL):
        k = ts.cutoff_instant(fridays[(s, w)])
        base = rows[(s, w, t)]
        me, pos = sorted(
            (r["player_id"], r["position"])
            for r in base
            if r["position"] in POSITIONS and r["player_id"]
        )[0]
        for delta, tag in ((dt.timedelta(seconds=1), "late"), (-dt.timedelta(seconds=1), "early")):
            fake = {
                "player_id": me,
                "position": pos,
                "status": "Out",
                "practice": "Did Not Participate In Practice",
                "modified": k + delta,
            }
            before = ts.features(me, pos, base, k, {}, set())
            after = ts.features(me, pos, [*base, fake], k, {}, set())
            if tag == "late":
                moved_late += int(before != after)
            else:
                set_early += int(after["own_status"] == 3.0 and after["own_practice"] == 2.0)
        checked += 1
    pruned = {
        key: [
            r
            for r in rs
            if (key[0], key[1]) in fridays
            and r["modified"] <= ts.cutoff_instant(fridays[(key[0], key[1])])
        ]
        for key, rs in rows.items()
    }
    n_late = sum(len(v) for v in rows.values()) - sum(len(v) for v in pruned.values())
    pruned = {k: v for k, v in pruned.items() if v}
    diff_c = _diff(inj, w12.injury_table(con, panel, fridays, pruned, strict=False), OWN)
    print(
        f"G2  pre-cutoff         : own Out rows 1 s after the cutoff that moved a feature: "
        f"{moved_late}/{checked}; own Out rows 1 s before that set status 3 / practice 2: "
        f"{set_early}/{checked}; own-feature values moved by deleting all {n_late:,} "
        f"post-cutoff rows: {diff_c}"
    )
    if moved_late or set_early != checked or not checked or diff_c or not n_late:
        failures.append("G2")

    # --- G3 arm A is W10 ------------------------------------------------------------------------
    r10 = json.loads(Path(args.w10).read_text())
    n3 = bad3 = 0
    for tag in ("full_ppr", "half_ppr"):
        for pos in (*POSITIONS, "FLEX"):
            n, b = _cells(
                res[tag]["cells"].get(f"{pos}|{w13.ARM_A}", {}),
                r10[tag]["cells"][f"{pos}|{w13.ARM_A}"],
            )
            n3, bad3 = n3 + n, bad3 + b
    print(f"G3  A = W10            : {n3:,} per-week values (2021-2024), mismatches {bad3}")
    if bad3 or not n3:
        failures.append("G3")

    # --- G4 only the two own features -----------------------------------------------------------
    dur = w9.durable_table(con, through=max(SEASONS))
    fr = w13.frames(panel, dur, inj)
    cols = {arm: list(f.columns) for arm, (f, _c) in fr.items()}
    extras = {arm: list(c) for arm, (_f, c) in fr.items()}
    want = [*KEYS, *w13.DURABLE, *OWN]
    ok_cols = (
        cols[w13.ARM_B] == want
        and cols[w13.ARM_N] == want
        and cols[w13.ARM_S] == [*KEYS, *w13.DURABLE, "own_status"]
        and extras[w13.ARM_B] == want[3:]
        and extras[w13.ARM_N] == want[3:]
        and extras[w13.ARM_S] == [*w13.DURABLE, "own_status"]
    )
    forbidden = ("ecr", "news", "depth", "tm_", "vegas", "market", "adp", "y_", "xfp")
    bad_tokens = sorted({c for cs in extras.values() for c in cs if any(t in c for t in forbidden)})
    # N is a within-(season, week, position) permutation of B's values, nothing else
    pos = panel[[*KEYS, "position"]]
    fb = fr[w13.ARM_B][0].merge(pos, on=KEYS)
    fn = fr[w13.ARM_N][0].merge(pos, on=KEYS)

    def _multisets(f: pd.DataFrame) -> dict:
        out: dict = {}
        for key, block in f.groupby(["season", "week", "position"], sort=True):
            out[key] = sorted(
                (-1.0 if math.isnan(a) else a, -1.0 if math.isnan(b) else b)
                for a, b in zip(block.own_status, block.own_practice, strict=True)
            )
        return out

    perm_ok = _multisets(fb) == _multisets(fn)
    seasons_eval = sorted(
        {
            int(k.split("-")[0])
            for tag in ("full_ppr", "half_ppr")
            for w in res[tag]["cells"].values()
            for k in w
        }
    )
    used = sorted(s for s, v in prov["seasons"].items() if v["used"])
    print(
        f"G4  own features only  : frame columns exact {ok_cols}; forbidden tokens "
        f"{bad_tokens or 'none'}; N a within-group permutation of B {perm_ok}; evaluated seasons "
        f"{seasons_eval}; injury seasons used {used[0]}-{used[-1]}"
    )
    if not ok_cols or bad_tokens or not perm_ok or seasons_eval != list(SEASONS) or 2025 in used:
        failures.append("G4")

    # --- G5 ECR never a feature: exactly the declared training calls ----------------------------
    tree = ast.parse(RUNNER.read_text())
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
    frames_used = sorted(ast.unparse(c.args[1]) for c in calls if len(c.args) > 1)
    train_b = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "w11m.train_b"
    ]
    # no ECR-bearing string anywhere in the code that builds or trains the arms (docstrings aside)
    ecr_literals = [
        n.value
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef) and fn.name in ("frames", "trainings")
        for stmt in fn.body[1 if ast.get_docstring(fn) else 0 :]
        for n in ast.walk(stmt)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "ecr" in n.value.lower()
    ]
    ok5 = (
        arms == sorted(["ARM_B", "ARM_N", "ARM_S"])
        and frames_used == sorted(["frame_b", "frame_n", "frame_s"])
        and len(train_b) == 1
        and not ecr_literals
    )
    print(
        f"G5  ECR never a feature: {len(calls)} one-change training calls {arms} on {frames_used}; "
        f"W10 trainer calls {len(train_b)}; ECR-bearing string literals {ecr_literals or 'none'}"
    )
    if not ok5:
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

    # --- G7 identity: own status against an independent SQL computation -------------------------
    teams = {r[0] for r in con.execute("SELECT DISTINCT home_team FROM games").fetchall()}
    bad_teams = sorted({t for (_s, _w, t) in rows} - teams)
    rate = 1 - prov["unmapped"] / max(prov["rows"], 1)
    pool = inj[inj.season.isin(SEASONS)].merge(panel[[*KEYS, "team"]], on=KEYS).sort_values(KEYS)
    recs = list(
        zip(
            pool.player_id,
            pool.season,
            pool.week,
            pool.team,
            pool.own_status,
            pool.own_practice,
            strict=True,
        )
    )
    flagged = [r for r in recs if _num(r[4]) is not None and r[4] > 0]
    other = [r for r in recs if not (_num(r[4]) is not None and r[4] > 0)]
    rng = random.Random(32)
    sample = rng.sample(flagged, N_SQL // 2) + rng.sample(other, N_SQL - N_SQL // 2)
    paths = {
        int(json.loads(p)["season"]): lp
        for p, lp in con.execute(
            "SELECT params_json, local_path FROM snapshot_registry "
            "WHERE source = 'nflverse' AND dataset = 'injuries' ORDER BY captured_at"
        ).fetchall()
    }
    inv = {v: k2 for k2, v in ts.TEAM_ALIAS.items()}
    wrong = 0
    for pid, season, week, team, st, pr in sample:
        k = ts.cutoff_instant(fridays[(int(season), int(week))])
        n_known, sql_st, sql_pr = con.execute(
            f"""
            WITH t AS (
              SELECT i.gsis_id, i.report_status, i.practice_status
              FROM {reader_expr(paths[int(season)])} i
              WHERE i.game_type = 'REG' AND CAST(i.week AS INTEGER) = ?
                AND i.team IN (?, ?) AND i.date_modified <= ?
            ),
            o AS (
              SELECT t.* FROM t JOIN player_id_map m
                ON m.id_type = 'gsis_id' AND m.id_value = t.gsis_id AND m.player_id = ?
            )
            SELECT
              (SELECT count(*) FROM t),
              (SELECT coalesce(max(CASE report_status WHEN 'Questionable' THEN 1
                 WHEN 'Doubtful' THEN 2 WHEN 'Out' THEN 3 ELSE 0 END), 0) FROM o),
              (SELECT coalesce(max(CASE practice_status
                 WHEN 'Limited Participation in Practice' THEN 1
                 WHEN 'Did Not Participate In Practice' THEN 2
                 WHEN 'Out (Definitely Will Not Play)' THEN 2 ELSE 0 END), 0) FROM o)
            """,
            [int(week), team, inv.get(team, team), k, pid],
        ).fetchone()
        exp = (None, None) if n_known == 0 else (float(sql_st), float(sql_pr))
        wrong += int(exp != (_num(st), _num(pr)))
    print(
        f"G7  identity           : unmapped team codes {bad_teams or 'none'}; gsis map rate "
        f"{rate:.4f}; own_status/own_practice wrong in {wrong}/{len(sample)} independent SQL "
        f"checks ({len(flagged):,} designated player-weeks in the pool)"
    )
    if bad_teams or wrong or rate != 1.0 or len(sample) != N_SQL:
        failures.append("G7")

    # --- G8 order-free --------------------------------------------------------------------------
    rev = {k: list(reversed(v)) for k, v in reversed(list(rows.items()))}
    d8 = _diff(
        inj,
        w12.injury_table(con, panel.iloc[::-1].reset_index(drop=True), fridays, rev, strict=False),
        OWN,
    )
    print(f"G8  order-free         : own-feature values differing with every input reversed: {d8}")
    if d8:
        failures.append("G8")

    # --- G9 universe and cutoff -----------------------------------------------------------------
    n9 = bad9 = 0
    for tag in ("full_ppr", "half_ppr"):
        for pos in (*POSITIONS, "FLEX"):
            for b in ("CF_A", "ECR"):
                n, b_ = _cells(
                    res[tag]["cells"].get(f"{pos}|{b}", {}), r10[tag]["cells"][f"{pos}|{b}"]
                )
                n9, bad9 = n9 + n, bad9 + b_
    weeks = res["full_ppr"]["summary"]["n_weeks"], res["half_ppr"]["summary"]["n_weeks"]
    print(
        f"G9  universe / cutoff  : {n9:,} CF_A/ECR values vs W10's committed cells, "
        f"mismatches {bad9}; weeks {weeks}"
    )
    if bad9 or not n9 or weeks != (N_WEEKS, N_WEEKS):
        failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism        : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w13.json"
            subprocess.run(
                [sys.executable, str(RUNNER), "--db", args.db, "--out", str(out)],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(out.read_bytes()).hexdigest()
        b = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
        print(
            f"G10 determinism        : {a[:16]} vs {b[:16]} -> {'identical' if a == b else 'DIFFERENT'}"
        )
        if a != b:
            failures.append("G10")

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

    # --- G12 null construction ------------------------------------------------------------------
    paired = res["full_ppr"]["summary"]["all"]["paired"]
    parts = []
    for pos in POSITIONS:
        for mt in ("capture@5", "capture@10"):
            r = paired[f"{pos}|{w13.ARM_N}_vs_{pos}|{w13.ARM_A}"][mt]
            ok = r["ci_low"] <= 0.0 <= r["ci_high"]
            parts.append(
                f"{pos} {mt} {r['mean_diff']:+.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}]"
                f"{'' if ok else ' FAIL'}"
            )
            if not ok:
                failures.append(f"G12:{pos}:{mt}")
    print("G12 null construction  : " + " | ".join(parts))

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
