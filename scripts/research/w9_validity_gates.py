"""W9 validity and leakage gates (pre-registration §11, amendments A1-A2). All must pass before
any W9 result is read.

    uv run python scripts/research/w9_validity_gates.py [--skip-determinism]
        [--repro-summary /path/to/summary]   # the pre-analysis W5-W8 reproduction record (G11)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import spearman, topk_points_capture  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research.w6_upper_outcome import positional_cell  # noqa: E402
from scripts.research.w7_opportunity import _pearson, _ranks  # noqa: E402
from scripts.research.w7_validity_gates import _redacted, _same, _wire  # noqa: E402

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
REDACT_EVERY = 8
RUNNER = Path("scripts/research/w9_mechanisms.py")
FORBIDDEN_IN_FEATURES = ("injur", "depth", "news", "vegas", "ecr", "y_", "xfp", "usage", "pre_")


def _prior_redacted(db: str, season: int):
    """A connection whose `player_week_stats` holds nothing from `season` onward."""
    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    con.execute(
        f"CREATE VIEW player_week_stats AS SELECT * FROM src.player_week_stats WHERE season < {season}"
    )
    return con


def _eq(a, b) -> bool:
    fa = None if a is None or (isinstance(a, float) and math.isnan(a)) else a
    fb = None if b is None or (isinstance(b, float) and math.isnan(b)) else b
    return fa == fb


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w9_results.json")
    ap.add_argument("--w7", default="reports/weekly/w7_results.json")
    ap.add_argument("--w8", default="reports/weekly/w8_results.json")
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
        f"G1  parity             : {fid['exact_matches']:,}/{fid['n_shared']:,} exact, max abs diff {fid['max_abs_diff']}"
    )
    if fid["exact_share"] != 1.0 or fid["only_in_trained"] or fid["only_in_stored"]:
        failures.append("G1")

    # --- G2 prior-season data is truly prior ------------------------------------------------------
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
        # players who appear only in `season` itself are absent once it is deleted -- the check is
        # on every player whose durable row exists in both, i.e. everyone with a prior season
        common = sorted(set(a.index) & set(b.index))
        with_prior = [p for p in common if a.at[p, "has_prior"] == 1.0]
        for p in with_prior:
            checked += 1
            for col in mech.DURABLE_FEATURES:
                if not _eq(a.at[p, col], b.at[p, col]):
                    moved += 1
        if set(a[a.has_prior == 1.0].index) - set(b.index):
            moved += 1
    dp = w9.durable_panel(op.build_panel(con, POSITIONS), full, shuffle=False)
    varying = int(
        dp.groupby(["player_id", "season"])[list(mech.DURABLE_FEATURES)]
        .nunique(dropna=False)
        .gt(1)
        .any(axis=1)
        .sum()
    )
    pre = res["provenance"]["preseason"]
    late = [
        k
        for k, v in pre.items()
        if k.endswith("|scrape") and not v < pre[k.replace("|scrape", "|first_game")]
    ]
    print(
        f"G2  prior is prior     : durable values that moved when season >= S was deleted "
        f"({checked:,} player-seasons): {moved}; within-season variation: {varying}; "
        f"preseason scrapes not before the opener: {len(late)}"
    )
    if moved or varying or late or not checked:
        failures.append("G2")

    # --- G3 early-season / forecast information precedes the week ---------------------------------
    panel = op.build_panel(con, POSITIONS)
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    weeks = audit.week_coverage(con, SEASONS).snapshots
    committed = json.loads(Path(args.w7).read_text())["forecast"]["cells"]
    mism = comp = 0
    for snap in weeks:
        key = f"{snap.season}-{snap.week}"
        for position in POSITIONS:
            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=(position,)
            )
            if not preds:
                continue
            common, board, _k = positional_cell(con, snap, position, FULL_PPR, preds)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            rows = [
                (p, idx[(p, snap.season, snap.week)])
                for p in sorted({r.player_id for r in board.rows})
                if (p, snap.season, snap.week) in idx
            ]
            rows = [(p, i) for p, i in rows if not pd.isna(panel.at[i, "y_xfp"])]
            if len(rows) < benchmark.MIN_EVALUABLE:
                continue
            ids = [p for p, _ in rows]
            real = [float(panel.at[i, "y_xfp"]) for _, i in rows]
            pred = [float(fc[position].at[i]) for _, i in rows]
            pr = _ranks(pred, ids)
            mine = {
                "n": len(rows),
                "pearson": _pearson(pred, real),
                "spearman": spearman(pr, real),
                "mae": statistics.fmean(abs(a - b) for a, b in zip(pred, real, strict=True)),
                "capture@10": topk_points_capture(pr, real, 10),
                "capture@20": topk_points_capture(pr, real, 20),
            }
            for m, v in mine.items():
                comp += 1
                mism += int(v != committed[f"{position}|T_XFP|M_NEW"][key][m])
    moved_f = checked_f = 0
    for snap in weeks[::REDACT_EVERY]:
        red = _redacted(args.db, snap.season, snap.week)
        try:
            rp = op.build_panel(red, POSITIONS)
        finally:
            red.close()
        a = panel[(panel.season == snap.season) & (panel.week == snap.week)].set_index("player_id")
        b = rp[(rp.season == snap.season) & (rp.week == snap.week)].set_index("player_id")
        for pid in a.index:
            checked_f += 1
            moved_f += sum(0 if _same(a.at[pid, c], b.at[pid, c]) else 1 for c in op.NEW)
    print(
        f"G3  forecast is prior  : {comp:,} W7 metrics re-scored, mismatches {mism}; redaction moved {moved_f} of {checked_f:,} player-weeks' inputs"
    )
    if mism or not comp or moved_f:
        failures.append("G3")

    # --- G4 weekly information predates the cutoff ------------------------------------------------
    events, ev_audit = w9.weekly_events(con, weeks)
    ts = ev_audit["class_a_timestamps"]
    viol = sum(1 for r in ts if not r["ts"][:10] < r["cutoff"])
    precedence_ok = (
        mech.classify_weekly(False, True) == "C" and mech.classify_weekly(True, True) == "A"
    )
    print(
        f"G4  weekly is pre-Friday: class-A events {len(ts):,}, timestamp violations {viol}; C never promoted to A: {precedence_ok}"
    )
    if viol or not ts or not precedence_ok or res["provenance"]["class_a_violations"]:
        failures.append("G4")

    # --- G5 no post-Friday / realized information in any predictor --------------------------------
    src = RUNNER.read_text()
    tree = ast.parse(src)
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
    bad = [f for f in mech.DURABLE_FEATURES if any(t in f for t in FORBIDDEN_IN_FEATURES)]
    scr = panel.copy()
    rng = random.Random(0)
    rows25 = scr.index[scr.season == 2025]
    scr.loc[rows25, "y_xfp"] = [rng.uniform(0, 40) for _ in range(len(rows25))]
    changed = sum(
        int(not _same(a, b))
        for p in POSITIONS
        for a, b in zip(
            op.walk_forward(panel, p, "T_XFP", "M_NEW", (2025,)),
            op.walk_forward(scr, p, "T_XFP", "M_NEW", (2025,)),
            strict=True,
        )
    )
    print(
        f"G5  declared trainings : {len(calls)} ({arms}); forbidden tokens in durable features: {bad or 'none'}; forecasts moved by scrambled outcomes: {changed}"
    )
    if (
        len(calls) != 3
        or arms != sorted(["DURABLE_ARM", "SHUFFLED_ARM", "ORACLE_ARM"])
        or bad
        or changed
    ):
        failures.append("G5")

    # --- G6 ECR is never a feature ------------------------------------------------------------------
    ecr_in_features = [
        f
        for f in (*FULL_FEATURES, *mech.DURABLE_FEATURES)
        if any(t in f.lower() for t in ("ecr", "market", "adp", "preseason"))
    ]
    frames = [ast.unparse(c.args[1]) if len(c.args) > 1 else "" for c in calls]
    ecr_in_frames = [f for f in frames if "pre" in f.split("(")[0] or "ecr" in f.lower()]
    print(
        f"G6  ECR never a feature: ECR-like feature names {ecr_in_features or 'none'}; training frames {frames}; ECR in any frame: {bool(ecr_in_frames)}"
    )
    if ecr_in_features or ecr_in_frames:
        failures.append("G6")

    # --- G7 walk-forward ------------------------------------------------------------------------
    leaks = 0
    for position in POSITIONS:
        for season in SEASONS:
            frame = arms_mod.load_position_week_data(
                con, position, arms_mod.MIN_TRAIN_SEASON, season - 1
            )
            leaks += int(not frame.empty and int(frame.season.max()) >= season)
    print(f"G7  walk-forward       : training frames containing the predicted season: {leaks}")
    if leaks:
        failures.append("G7")

    # --- G8 joins / identity ----------------------------------------------------------------------
    dup = int(full.duplicated(["player_id", "season"]).sum())
    resid = max(res["full_ppr"]["identity_max_residual"], res["half_ppr"]["identity_max_residual"])
    print(
        f"G8  joins / identity   : duplicate durable keys {dup}; max identity residual {resid:.2e} (the runner also aborts on any "
        "attribution that does not sum, and on any decomposable rho differing from Spearman by 1e-12)"
    )
    if dup or resid >= 1e-9:
        failures.append("G8")

    # --- G9 W8 re-derived exactly --------------------------------------------------------------
    w8res = json.loads(Path(args.w8).read_text())
    dmis = dcomp = 0
    for tag in ("full_ppr", "half_ppr"):
        for system, weeks_ in res[tag]["decomp_cells"].items():
            theirs = w8res[tag]["cells"].get(system, {})
            if set(weeks_) != set(theirs):
                dmis += 1
                continue
            for k, row in weeks_.items():
                for m, v in row.items():
                    dcomp += 1
                    dmis += int(v != theirs[k].get(m))
    print(
        f"G9  W8 re-derived      : {dcomp:,} per-week decomposition values vs W8's committed cells, mismatches {dmis}; weeks {res['full_ppr']['n_weeks']}"
    )
    if dmis or not dcomp or res["full_ppr"]["n_weeks"] != 79:
        failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism        : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w9.json"
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
        ok = bool(lines) and all("BYTE-IDENTICAL" in ln for ln in lines)
        print(
            f"G11 upstream           : {len(lines)} reproduced artifacts, all byte-identical: {ok}"
        )
        if not ok:
            failures.append("G11")
    else:
        print("G11 upstream           : no reproduction record supplied")
        failures.append("G11")

    # --- G12 null construction ------------------------------------------------------------------
    parts = []
    for pos in POSITIONS:
        s = res["full_ppr"]["summaries"][pos]
        ads = s["boards"]["ADS"].get("G_S@10")
        nul = s["anticipation"].get("red_null")
        ok = (
            ads
            and ads["ci_low"] <= 0 <= ads["ci_high"]
            and nul
            and nul["ci_low"] <= 0 <= nul["ci_high"]
        )
        parts.append(
            f"{pos}: shuffled closure {ads['mean_diff']:+.4f} [{ads['ci_low']:+.4f},{ads['ci_high']:+.4f}], "
            f"null reduction {nul['mean_diff']:+.4f} [{nul['ci_low']:+.4f},{nul['ci_high']:+.4f}] -> {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            failures.append(f"G12:{pos}")
    print("G12 null construction  : " + " | ".join(parts))

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
