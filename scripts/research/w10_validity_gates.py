"""W10 validity and leakage gates (pre-registration §10). All must pass before any W10 result is
read.

    uv run python scripts/research/w10_validity_gates.py [--skip-determinism]
        [--repro-summary /path/to/summary]   # the pre-analysis W5-W9 reproduction record (G11)
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
from types import SimpleNamespace

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import context  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research.w7_validity_gates import _wire  # noqa: E402
from scripts.research.w9_validity_gates import (  # noqa: E402
    FORBIDDEN_IN_FEATURES,
    _eq,
    _prior_redacted,
)

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
PIECES = ("G", "G_F", "G_S", "G_C")
K = 10
N_PRIOR_GAMES_SAMPLE = 300
N_UPSTREAM = 8
RUNNER = Path("scripts/research/w10_historical.py")
DECLARED_ARMS = sorted(["ARM_B", "ARM_N", "name"])  # `name` is the ablation loop variable


class _Reversed:
    """A connection whose every `execute(...).fetchall()` returns the rows in reverse order."""

    def __init__(self, con) -> None:
        self._con = con

    def execute(self, sql, *args):
        rows = self._con.execute(sql, *args).fetchall()
        return SimpleNamespace(fetchall=lambda: list(reversed(rows)))


def _scrambled(db: str, season: int):
    """A connection whose `player_week_stats` has season `season`'s outcomes replaced by noise."""
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    noise = "(hash(player_id || '-' || CAST(week AS VARCHAR) || '-{c}') % 1000) / 25.0"
    con.execute(
        "CREATE TABLE player_week_stats AS SELECT * REPLACE ("
        f"CASE WHEN season = {season} THEN {noise.format(c='p')} ELSE fantasy_points_ppr END "
        "AS fantasy_points_ppr, "
        f"CASE WHEN season = {season} THEN CAST({noise.format(c='t')} AS INTEGER) ELSE targets END "
        "AS targets, "
        f"CASE WHEN season = {season} THEN CAST({noise.format(c='c')} AS INTEGER) ELSE carries END "
        "AS carries, "
        f"CASE WHEN season = {season} THEN {noise.format(c='s')} / 40.0 ELSE target_share END "
        "AS target_share, "
        f"CASE WHEN season = {season} THEN {noise.format(c='n')} / 40.0 ELSE offense_snap_pct END "
        "AS offense_snap_pct) FROM src.player_week_stats"
    )
    return con


def _same_frame(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    a = a.sort_values(["player_id", "season"]).reset_index(drop=True)
    b = b.sort_values(["player_id", "season"]).reset_index(drop=True)
    return list(a.columns) == list(b.columns) and a.equals(b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w10_results.json")
    ap.add_argument("--w7", default="reports/weekly/w7_results.json")
    ap.add_argument("--w8", default="reports/weekly/w8_results.json")
    ap.add_argument("--w9", default="reports/weekly/w9_results.json")
    ap.add_argument("--repro-summary", default=None)
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    res = json.loads(Path(args.results).read_text())
    failures: list[str] = []

    # --- G1 parity ------------------------------------------------------------------------------
    control = arms_mod.train_with_extra_features(
        con, pd.DataFrame(columns=["player_id", "season", "week"]), []
    )
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

    # --- G2 prior-season is prior ---------------------------------------------------------------
    full = w9.durable_table(con)
    moved = checked = 0
    for season in SEASONS:
        red = _prior_redacted(args.db, season)
        try:
            rd = w9.durable_table(red)
        finally:
            red.close()
        a = full[full.season == season].set_index("player_id").sort_index()
        b = rd[rd.season == season].set_index("player_id").sort_index()
        for p in sorted(set(a.index) & set(b.index)):
            if a.at[p, "has_prior"] != 1.0:
                continue
            checked += 1
            moved += sum(0 if _eq(a.at[p, c], b.at[p, c]) else 1 for c in mech.DURABLE_FEATURES)
        moved += len(set(a[a.has_prior == 1.0].index) - set(b.index))
    panel = op.build_panel(con, POSITIONS)
    dp = w9.durable_panel(panel, full, shuffle=False)
    varying = int(
        dp.groupby(["player_id", "season"])[list(mech.DURABLE_FEATURES)]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
        .sum()
    )
    print(
        f"G2  prior is prior     : durable values moved when seasons >= S were deleted "
        f"({checked:,} player-seasons): {moved}; within-season variation: {varying}"
    )
    if moved or varying or not checked:
        failures.append("G2")

    # --- G3 arm B is W9's ALPHA_PLUS_DURABLE ------------------------------------------------------
    r9 = json.loads(Path(args.w9).read_text())
    mis3 = comp3 = 0
    for tag in ("full_ppr", "half_ppr"):
        for pos in POSITIONS:
            mine = res[tag]["decomp_cells"].get(f"{pos}|B_vs_A", {})
            theirs = r9[tag]["store"].get(f"{pos}|AD", {})
            theirs = {k: r for k, r in theirs.items() if f"G@{K}" in r}
            if set(mine) != set(theirs) or not mine:
                mis3 += 1
                continue
            for k, row in mine.items():
                for piece in PIECES:
                    comp3 += 1
                    mis3 += int(row[piece] != theirs[k][f"{piece}@{K}"])
    print(
        f"G3  B is W9's arm      : {comp3:,} per-week decomposition values vs W9's committed AD "
        f"cells, mismatches {mis3}"
    )
    if mis3 or not comp3:
        failures.append("G3")

    # --- G4 no future games / injuries / roles in any feature --------------------------------------
    bad = [f for f in mech.DURABLE_FEATURES if any(t in f for t in FORBIDDEN_IN_FEATURES)]
    moved4 = checked4 = control4 = 0
    for season in (2022, 2025):
        sc = _scrambled(args.db, season)
        try:
            sd = w9.durable_table(sc)
        finally:
            sc.close()
        checked4 += int((full.season == season).sum())
        moved4 += int(not _same_frame(full[full.season == season], sd[sd.season == season]))
        if season < 2025:  # positive control: the scramble must reach season S + 1
            control4 += int(
                not _same_frame(full[full.season == season + 1], sd[sd.season == season + 1])
            )
    print(
        f"G4  no future info     : forbidden tokens in the 7 features: {bad or 'none'}; "
        f"seasons whose features moved when their own outcomes were scrambled: {moved4} "
        f"({checked4:,} rows); scramble reached S+1 (positive control): {bool(control4)}"
    )
    if bad or moved4 or not control4:
        failures.append("G4")

    # --- G5 ECR never a feature -------------------------------------------------------------------
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
    frames = sorted(ast.unparse(c.args[1]) for c in calls if len(c.args) > 1)
    dp_src = [
        ast.unparse(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "dp" for t in n.targets)
    ]
    frames_ok = frames == sorted(
        ["dp", "dp[keys + keep]", "w9.durable_panel(panel, dur, shuffle=True)"]
    ) and dp_src == ["w9.durable_panel(panel, dur, shuffle=False)"]
    tables = sorted(set(re.findall(r"FROM\s+(\w+)", inspect.getsource(w9.durable_table))))
    ecr_names = [
        f
        for f in (*FULL_FEATURES, *mech.DURABLE_FEATURES)
        if any(t in f.lower() for t in ("ecr", "market", "adp", "preseason", "rank_e"))
    ]
    print(
        f"G5  ECR never a feature: {len(calls)} training calls, arms {arms}; frames {frames} "
        f"(dp = {dp_src}); durable table reads {tables}; ECR-like feature names "
        f"{ecr_names or 'none'}"
    )
    if (
        len(calls) != 3
        or arms != DECLARED_ARMS
        or not frames_ok
        or tables != ["player_week_stats"]
        or ecr_names
    ):
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
    dup = int(full.duplicated(["player_id", "season"]).sum())
    have = full[full.has_prior == 1.0].sort_values(["season", "player_id"])
    pool = list(zip(have.player_id, have.season, have.prior_games, strict=True))
    sample = random.Random(10).sample(pool, N_PRIOR_GAMES_SAMPLE)
    wrong = sum(
        int(
            con.execute(
                "SELECT count(*) FROM player_week_stats WHERE player_id = ? AND season = ?",
                [pid, int(season) - 1],
            ).fetchone()[0]
            != int(games)
        )
        for pid, season, games in sample
    )
    none_rows = full[full.has_prior == 0.0].sort_values(["season", "player_id"])
    zero_pool = list(zip(none_rows.player_id, none_rows.season, strict=True))
    zero_sample = random.Random(11).sample(zero_pool, min(N_PRIOR_GAMES_SAMPLE, len(zero_pool)))
    wrong_zero = sum(
        int(
            con.execute(
                "SELECT count(*) FROM player_week_stats WHERE player_id = ? AND season = ?",
                [pid, int(season) - 1],
            ).fetchone()[0]
            != 0
        )
        for pid, season in zero_sample
    )
    print(
        f"G7  joins / alignment  : duplicate durable keys {dup}; prior_games wrong in "
        f"{wrong}/{len(sample)} seeded player-seasons; has_prior=0 rows with an S-1 game: "
        f"{wrong_zero}/{len(zero_sample)} (the runner also aborts on any universe mismatch and "
        "any movement attribution that does not sum to G)"
    )
    if dup or wrong or wrong_zero or len(sample) != N_PRIOR_GAMES_SAMPLE:
        failures.append("G7")

    # --- G8 no look-ahead through aggregates ------------------------------------------------------
    rev = w9.durable_table(_Reversed(con))
    same8 = _same_frame(full, rev)
    print(f"G8  order-free table   : durable table identical with input reversed: {same8}")
    if not same8:
        failures.append("G8")

    # --- G9 universe, cutoff and arm A ------------------------------------------------------------
    r7 = json.loads(Path(args.w7).read_text())["ranking"]
    r8 = json.loads(Path(args.w8).read_text())["full_ppr"]["counterfactual"]["cells"]
    counts9: dict[str, list[int]] = {}

    def _cells(label: str, system: str, theirs: dict) -> None:
        c = counts9.setdefault(label, [0, 0])
        mine = res["full_ppr"]["cells"].get(system, {})
        if set(mine) != set(theirs) or not mine:
            c[1] += 1
            return
        for k, row in theirs.items():
            for m, v in row.items():
                if m in mine[k]:
                    c[0] += 1
                    c[1] += int(mine[k][m] != v)

    for p in POSITIONS:
        for b in ("CF_A", "ECR"):
            _cells("W8 positional", f"{p}|{b}", r8.get(f"{p}|{b}", {}))
            _cells("W7 positional", f"{p}|{b}", r7["cells"].get(f"{p}|{b}", {}))
    for b in ("CF_A", "ECR"):
        _cells("W7 FLEX", f"FLEX|{b}", r7["cells"].get(f"FLEX|{b}", {}))
    c = counts9.setdefault("W9 ECR-A decomposition", [0, 0])
    for tag in ("full_ppr", "half_ppr"):
        for pos in POSITIONS:
            mine = res[tag]["decomp_cells"].get(f"{pos}|ECR_vs_A", {})
            theirs = {k: r for k, r in r9[tag]["store"][f"{pos}|ECR"].items() if f"G@{K}" in r}
            if set(mine) != set(theirs) or not mine:
                c[1] += 1
                continue
            for k, row in mine.items():
                for piece in PIECES:
                    c[0] += 1
                    c[1] += int(row[piece] != theirs[k][f"{piece}@{K}"])
    c = counts9.setdefault("W7 cliff (A)", [0, 0])
    for pos in POSITIONS:
        mine, theirs = res["full_ppr"]["cliff"].get(f"{pos}|CF_A", {}), r7["cliff"][f"{pos}|CF_A"]
        c[0] += len(theirs)
        c[1] += int(mine != theirs or not theirs)
    weeks = (res["full_ppr"]["n_weeks"], res["half_ppr"]["n_weeks"])
    mis9 = sum(v[1] for v in counts9.values())
    detail = "; ".join(f"{k} {v[0]:,} values, {v[1]} mismatches" for k, v in counts9.items())
    print(f"G9  universe / arm A   : {detail}; weeks {weeks}")
    if mis9 or not all(v[0] for v in counts9.values()) or weeks != (79, 79):
        failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism        : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w10.json"
            subprocess.run(
                [sys.executable, str(RUNNER), "--db", args.db, "--out", str(out)],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(out.read_bytes()).hexdigest()
        b = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
        print(
            f"G10 determinism        : {a[:16]} vs {b[:16]} -> "
            f"{'identical' if a == b else 'DIFFERENT'}"
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

    # --- G12 null arm -----------------------------------------------------------------------------
    paired = res["full_ppr"]["summary"]["all"]["paired"]
    parts = []
    for pos in POSITIONS:
        for mt in ("capture@5", "capture@10"):
            r = paired[f"{pos}|ALPHA_PLUS_HISTORICAL_NULL_vs_{pos}|CF_A"][mt]
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
