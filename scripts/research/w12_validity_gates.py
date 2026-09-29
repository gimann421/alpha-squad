"""W12 validity and leakage gates (pre-registration §10). All must pass before any W12 result is read.

uv run python scripts/research/w12_validity_gates.py --repro-summary <W5-W11 record>
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
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
from scripts.research import w12_timestamped as w12  # noqa: E402
from scripts.research.w7_validity_gates import _wire  # noqa: E402
from scripts.research.w9_validity_gates import _eq  # noqa: E402

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
KEYS = ["player_id", "season", "week"]
RUNNER = Path("scripts/research/w12_timestamped.py")
N_ADVERSARIAL = 40
N_SQL = 300
N_UPSTREAM = 12


def _diff(a: pd.DataFrame, b: pd.DataFrame) -> int:
    a = a.set_index(KEYS).sort_index()
    b = b.set_index(KEYS).sort_index()
    if list(a.index) != list(b.index):
        return max(len(a), 1)
    return sum(0 if _eq(x, y) else 1 for c in ts.FEATURES for x, y in zip(a[c], b[c], strict=True))


def _cells(mine: dict, theirs: dict) -> tuple[int, int]:
    if set(mine) != set(theirs) or not mine:
        return 0, 1
    n = bad = 0
    for k, row in theirs.items():
        for m, v in row.items():
            if m in mine[k]:
                n += 1
                bad += int(mine[k][m] != v)
    return n, bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w12_results.json")
    ap.add_argument("--w10", default="reports/weekly/w10_results.json")
    ap.add_argument("--w11", default="reports/weekly/w11_results.json")
    ap.add_argument("--repro-summary", default=None)
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
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
    # (b) adversarial: a 20-touch teammate listed Out 1 s after vs 1 s before the cutoff
    cands = sorted(
        (s, w, t)
        for (s, w, t), rs in rows.items()
        if s in w12.PRIMARY_SEASONS and (s, w) in fridays and any(r["position"] == "RB" for r in rs)
    )
    moved_late = moved_early = checked = 0
    for s, w, t in random.Random(21).sample(cands, N_ADVERSARIAL):
        k = ts.cutoff_instant(fridays[(s, w)])
        base = rows[(s, w, t)]
        rbs = sorted({r["player_id"] for r in base if r["position"] == "RB" and r["player_id"]})
        if not rbs:
            continue
        me = rbs[0]
        tpg = {"__fake__": 20.0}
        for delta, tag in ((dt.timedelta(seconds=1), "late"), (-dt.timedelta(seconds=1), "early")):
            fake = {
                "player_id": "__fake__",
                "position": "RB",
                "status": "Out",
                "practice": None,
                "modified": k + delta,
            }
            before = ts.features(me, "RB", base, k, tpg, set())
            after = ts.features(me, "RB", [*base, fake], k, tpg, set())
            if tag == "late":
                moved_late += int(before != after)
            else:
                moved_early += int(
                    after["tm_out_opp"] is not None
                    and abs(after["tm_out_opp"] - (before["tm_out_opp"] or 0.0) - 20.0) < 1e-9
                )
        checked += 1
    # (c) deleting every row modified after its cutoff changes nothing
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
    diff_c = _diff(inj, w12.injury_table(con, panel, fridays, pruned, strict=False))
    print(
        f"G2  pre-cutoff         : adversarial 1-s-late Out rows that moved a feature: "
        f"{moved_late}/{checked}; 1-s-early rows correctly counted: {moved_early}/{checked}; "
        f"features moved by deleting all {n_late:,} post-cutoff rows: {diff_c}"
    )
    if moved_late or moved_early != checked or not checked or diff_c or not n_late:
        failures.append("G2")

    # --- G3 B and C are W10's and W11's ---------------------------------------------------------
    r10 = json.loads(Path(args.w10).read_text())
    r11 = json.loads(Path(args.w11).read_text())
    n3 = bad3 = 0
    for tag in ("full_ppr", "half_ppr"):
        for pos in (*POSITIONS, "FLEX"):
            for arm, ref in ((w12.ARM_B, r10), (w12.ARM_C, r11)):
                n, b = _cells(
                    res[tag]["cells"].get(f"{pos}|{arm}", {}), ref[tag]["cells"][f"{pos}|{arm}"]
                )
                n3, bad3 = n3 + n, bad3 + b
    print(f"G3  B = W10, C = W11   : {n3:,} per-week values, mismatches {bad3}")
    if bad3 or not n3:
        failures.append("G3")

    # --- G4 no Class B/C in the primary features ------------------------------------------------
    f25 = inj[inj.season == 2025]
    leaked25 = int(f25[list(ts.FEATURES)].notna().sum().sum())
    forbidden = ("ecr", "news", "vegas", "depth", "y_", "xfp", "usage", "market", "adp")
    bad_tokens = [f for f in ts.FEATURES if any(t in f for t in forbidden)]
    tree = ast.parse(RUNNER.read_text())
    depth_uses = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == "depth_now"
    ]
    print(
        f"G4  Class A only       : non-missing 2025 injury features {leaked25}; injury seasons used "
        f"{sorted(s for s, v in prov['seasons'].items() if v['used'])}; forbidden tokens "
        f"{bad_tokens or 'none'}; `depth_now` literals in the runner: {len(depth_uses)} (arm E only)"
    )
    if leaked25 or bad_tokens or 2025 in [s for s, v in prov["seasons"].items() if v["used"]]:
        failures.append("G4")

    # --- G5 ECR never a feature -------------------------------------------------------------------
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
    ok5 = (
        arms == sorted(["ARM_C", "ARM_D", "ARM_N", "ARM_E", "name"])
        and frames
        == sorted(["frame_c", "frame_d", "frame_n", "frame_e", "frame_d[[*KEYS, *cols]]"])
        and assigns.get("frame_c", "").startswith("dp.merge(rp,")
        and assigns.get("frame_d", "").startswith("frame_c.merge(inj[")
        and assigns.get("frame_n", "").startswith("frame_c.merge(permuted(panel, inj)")
        and assigns.get("frame_e", "").startswith("frame_d.merge(depth_now(con, panel)")
    )
    print(f"G5  ECR never a feature: {len(calls)} training calls {arms}; frames {frames}")
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

    # --- G7 joins -------------------------------------------------------------------------------
    teams = {r[0] for r in con.execute("SELECT DISTINCT home_team FROM games").fetchall()}
    bad_teams = sorted({t for (_s, _w, t) in rows} - teams)
    rate = 1 - prov["unmapped"] / max(prov["rows"], 1)
    pool = (
        inj[inj.season.isin(w12.PRIMARY_SEASONS) & inj.tm_out_opp.notna()]
        .merge(panel[[*KEYS, "team", "position"]], on=KEYS)
        .sort_values(KEYS)
    )
    sample = random.Random(22).sample(
        list(
            zip(
                pool.player_id,
                pool.season,
                pool.week,
                pool.team,
                pool.position,
                pool.tm_out_opp,
                strict=True,
            )
        ),
        N_SQL,
    )
    paths = {
        int(json.loads(p)["season"]): lp
        for p, lp in con.execute(
            "SELECT params_json, local_path FROM snapshot_registry WHERE source = 'nflverse' AND dataset = 'injuries'"
        ).fetchall()
    }
    from alpha_squad.identity.canonical import reader_expr

    wrong = 0
    for pid, season, week, team, pos, val in sample:
        k = ts.cutoff_instant(fridays[(int(season), int(week))])
        inv = {v: k2 for k2, v in ts.TEAM_ALIAS.items()}
        codes = [team, inv.get(team, team)]
        (sql_val,) = con.execute(
            f"""
            WITH o AS (
              SELECT m.player_id AS j FROM {reader_expr(paths[int(season)])} i
              JOIN player_id_map m ON m.id_type = 'gsis_id' AND m.id_value = i.gsis_id
              WHERE i.game_type = 'REG' AND i.week = ? AND i.team IN (?, ?) AND i.position = ?
                AND i.report_status IN ('Out', 'Doubtful') AND i.date_modified <= ?
                AND m.player_id <> ?
            ),
            g AS (
              SELECT player_id, coalesce(carries, 0) + coalesce(targets, 0) AS t,
                     row_number() OVER (PARTITION BY player_id ORDER BY week DESC) AS rn
              FROM player_week_stats WHERE season = ? AND week < ? AND player_id IN (SELECT j FROM o)
            )
            SELECT coalesce(sum(tpg), 0) FROM (
              SELECT o.j, coalesce((SELECT avg(t) FROM g WHERE g.player_id = o.j AND rn <= 3), 0) AS tpg
              FROM o
            )
            """,
            [int(week), codes[0], codes[1], pos, k, pid, int(season), int(week)],
        ).fetchone()
        wrong += int(abs(float(sql_val) - float(val)) > 1e-9)
    print(
        f"G7  joins              : unmapped team codes {bad_teams or 'none'}; gsis map rate {rate:.4f}; "
        f"tm_out_opp wrong in {wrong}/{N_SQL} independent SQL checks"
    )
    if bad_teams or wrong:
        failures.append("G7")

    # --- G8 order-free --------------------------------------------------------------------------
    rev = {k: list(reversed(v)) for k, v in reversed(list(rows.items()))}
    d8 = _diff(
        inj,
        w12.injury_table(con, panel.iloc[::-1].reset_index(drop=True), fridays, rev, strict=False),
    )
    print(f"G8  order-free         : feature values differing with every input reversed: {d8}")
    if d8:
        failures.append("G8")

    # --- G9 universe and arm A ------------------------------------------------------------------
    n9 = bad9 = 0
    for tag in ("full_ppr", "half_ppr"):
        for pos in (*POSITIONS, "FLEX"):
            for b in ("CF_A", "ECR"):
                n, b_ = _cells(
                    res[tag]["cells"].get(f"{pos}|{b}", {}), r10[tag]["cells"][f"{pos}|{b}"]
                )
                n9, bad9 = n9 + n, bad9 + b_
    weeks = res["full_ppr"]["all_weeks"]["n_weeks"], res["full_ppr"]["primary_2021_2024"]["n_weeks"]
    print(
        f"G9  universe / arm A   : {n9:,} values vs W10's committed cells, mismatches {bad9}; weeks {weeks}"
    )
    if bad9 or not n9 or weeks != (79, 63):
        failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism        : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w12.json"
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

    # --- G12 null arm ---------------------------------------------------------------------------
    paired = res["full_ppr"]["primary_2021_2024"]["all"]["paired"]
    parts = []
    for pos in POSITIONS:
        for mt in ("capture@5", "capture@10"):
            r = paired[f"{pos}|{w12.ARM_N}_vs_{pos}|{w12.ARM_C}"][mt]
            ok = r["ci_low"] <= 0.0 <= r["ci_high"]
            parts.append(
                f"{pos} {mt} {r['mean_diff']:+.4f} [{r['ci_low']:+.4f},{r['ci_high']:+.4f}]{'' if ok else ' FAIL'}"
            )
            if not ok:
                failures.append(f"G12:{pos}:{mt}")
    print("G12 null arm           : " + " | ".join(parts))

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
