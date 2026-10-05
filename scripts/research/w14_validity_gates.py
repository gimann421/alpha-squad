"""W14 validity and leakage gates (pre-registration §9). All must pass before any 2026 result is read.

uv run python scripts/research/w14_validity_gates.py \
    --w10-history <W10 2021-2025 re-run on the 2026 database> \
    --w10-verbatim <w10_historical.py --seasons 2026 output> \
    --repro-summary <W5-W13 byte-comparison record>
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.features.panel import build_player_week_features  # noqa: E402
from alpha_squad.features.team import (  # noqa: E402
    attach_team_features_to_player_panel,
    build_team_week_features,
)
from alpha_squad.models.established.data import load_position_week_data  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w14_2026_validation as w14  # noqa: E402
from scripts.research import w14_row_order as ro  # noqa: E402

CANONICAL_DB = "data/alpha_squad.duckdb"
CANONICAL_SHA = "fa8e32dbbb8942d890d38f0fad5c88981dc7f171238826abf13eb09ddd2a73c7"
W10_COMMIT = "5de17c1"
#: Every file on W10's code path (pre-registration §2 / G2).
W10_PATH = (
    "scripts/research/w10_historical.py",
    "scripts/research/w9_mechanisms.py",
    "scripts/research/w8_ecr_advantage.py",
    "scripts/research/w7_opportunity.py",
    "scripts/research/w6_upper_outcome.py",
    "src/alpha_squad/evaluation/weekly/advantage.py",
    "src/alpha_squad/evaluation/weekly/alpha.py",
    "src/alpha_squad/evaluation/weekly/arms.py",
    "src/alpha_squad/evaluation/weekly/audit.py",
    "src/alpha_squad/evaluation/weekly/benchmark.py",
    "src/alpha_squad/evaluation/weekly/context.py",
    "src/alpha_squad/evaluation/weekly/diagnostics.py",
    "src/alpha_squad/evaluation/weekly/historical.py",
    "src/alpha_squad/evaluation/weekly/mechanisms.py",
    "src/alpha_squad/evaluation/weekly/metrics.py",
    "src/alpha_squad/evaluation/weekly/noise.py",
    "src/alpha_squad/evaluation/weekly/nulls.py",
    "src/alpha_squad/evaluation/weekly/opportunity.py",
    "src/alpha_squad/evaluation/weekly/scoring.py",
    "src/alpha_squad/evaluation/weekly/series.py",
    "src/alpha_squad/evaluation/weekly/snapshots.py",
    "src/alpha_squad/evaluation/weekly/topboard.py",
    "src/alpha_squad/models",
    "src/alpha_squad/features",
    "src/alpha_squad/identity",
    "src/alpha_squad/sources",
    "src/alpha_squad/storage",
)
FROZEN_FEATURES = (
    "prior_ppg",
    "prior_games",
    "prior_opp_pg",
    "prior_tsh",
    "prior_snap",
    "prior_rank",
    "has_prior",
)
POSITIONS = w14.POSITIONS
SEASON = w14.SEASON
KEYS = ["player_id", "season", "week"]
RUNNER = Path("scripts/research/w14_2026_validation.py")
OUTCOME_TABLES = (
    "player_week_stats",
    "games",
    "player_week_features",
    "weekly_projection_snapshot",
    "team_week_stats",
)
N_UPSTREAM = 14
NGS_DECLARERS = {"src/alpha_squad/sources/nflverse.py", "src/alpha_squad/cli.py"}
NGS = re.compile(r"ngs_(passing|rushing|receiving)|nextgen_stats")


def _frame_hash(df: pd.DataFrame) -> str:
    df = df.sort_values(KEYS).reset_index(drop=True)
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def _cells_equal(mine: dict, theirs: dict, weeks: set[str]) -> tuple[int, int]:
    n = bad = 0
    for system, w in mine.items():
        ref = theirs.get(system)
        if ref is None:
            continue
        for k in weeks:
            if k not in w:
                continue
            if k not in ref:
                bad += 1
                continue
            for mt, v in w[k].items():
                if mt in ref[k]:
                    n += 1
                    bad += int(ref[k][mt] != v)
    return n, bad


def _wire(con) -> None:
    """The W10 runner's own wiring (ECR, crosswalk and the snapshot views `build_panel` needs)."""
    from alpha_squad.evaluation.weekly import context
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    context.wire_snapshot_views(con, tuple(range(2015, SEASON + 1)))


def _redacted_predictions(db: str, week: int) -> dict:
    """Week-`week` features and A/B predictions from a copy with every later 2026 row deleted
    and the features rebuilt by production's own builders."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "redacted.duckdb"
        shutil.copy(db, path)
        con = duckdb.connect(str(path))
        for t in (
            "player_week_stats",
            "team_week_stats",
            "player_week_features",
            "team_week_features",
            "games",
        ):
            con.execute(f"DELETE FROM {t} WHERE season = ? AND week > ?", [SEASON, week])
        build_player_week_features(con)
        build_team_week_features(con)
        attach_team_features_to_player_panel(con)
        ro.restore_all(con)  # amendment A2: the canonical order for <= 2025, as in the main copy
        _wire(con)
        feats = con.execute(
            f"SELECT player_id, season, week, {', '.join(FULL_FEATURES)}, team "
            "FROM player_week_features WHERE season = ? AND week = ? ORDER BY player_id",
            [SEASON, week],
        ).fetchdf()
        panel = op.build_panel(con, POSITIONS)
        dur = w9.durable_table(con, through=SEASON)
        a = arms_mod.train_with_extra_features(
            con, pd.DataFrame(columns=KEYS), [], seasons=(SEASON,)
        )
        b = arms_mod.train_with_extra_features(
            con,
            w9.durable_panel(panel, dur, shuffle=False),
            list(mech.DURABLE_FEATURES),
            arm=w14.ARM_B,
            seasons=(SEASON,),
        )
        con.close()
    pick = lambda arm: {k: v for k, v in arm.by_key.items() if k[2] == week}  # noqa: E731
    return {"features": feats, "A": pick(a), "B": pick(b)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/w14/alpha_squad_2026.duckdb")
    ap.add_argument("--results", default="reports/weekly/w14_results.json")
    ap.add_argument("--w10", default="reports/weekly/w10_results.json")
    ap.add_argument("--w10-history", default=None)
    ap.add_argument("--w10-verbatim", default=None)
    ap.add_argument("--repro-summary", default=None)
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--skip-redaction", action="store_true")
    args = ap.parse_args()

    res = json.loads(Path(args.results).read_text())
    con = duckdb.connect(args.db, read_only=True)
    canon = duckdb.connect(CANONICAL_DB, read_only=True)
    _wire(con)
    failures: list[str] = []
    eligible = sorted(res["look"]["eligible_weeks"])
    weeks = {f"{SEASON}-{w}" for w in eligible}

    # --- G1 parity ------------------------------------------------------------------------------
    stored = arms_mod.load_production_predictions(con)
    pos_of = {
        (p, int(s), int(w)): pos
        for p, s, w, pos in con.execute(
            "SELECT player_id, season, week, position FROM weekly_projection_snapshot "
            "WHERE model_name = 'ml_catboost'"
        ).fetchall()
    }
    c26 = arms_mod.train_with_extra_features(con, pd.DataFrame(columns=KEYS), [], seasons=(SEASON,))
    s26 = {k: v for k, v in stored.items() if k[1] == SEASON and pos_of[k] in POSITIONS}
    f26 = arms_mod.compare_to_production(c26, s26)
    chist = arms_mod.train_with_extra_features(con, pd.DataFrame(columns=KEYS), [])
    fh = arms_mod.compare_to_production(
        chist, {k: v for k, v in stored.items() if k in chist.by_key}
    )
    print(
        f"G1  parity             : 2026 {f26['exact_matches']:,}/{f26['n_shared']:,} exact "
        f"(only trained {f26['only_in_trained']}, only stored {f26['only_in_stored']}); "
        f"2021-2025 {fh['exact_matches']:,}/{fh['n_shared']:,} exact, max diff {fh['max_abs_diff']}"
    )
    if (
        f26["exact_share"] != 1.0
        or f26["only_in_trained"]
        or f26["only_in_stored"]
        or fh["exact_share"] != 1.0
        or fh["only_in_trained"]
    ):
        failures.append("G1")

    # --- G2 W10 frozen --------------------------------------------------------------------------
    diff = subprocess.run(
        ["git", "diff", "--stat", W10_COMMIT, "HEAD", "--", *W10_PATH],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tree = ast.parse(RUNNER.read_text())
    calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    trains = calls.count("w10.trainings")
    own_fits = [c for c in calls if c.endswith("train_with_extra_features") or "CatBoost" in c]
    feats_ok = tuple(mech.DURABLE_FEATURES) == FROZEN_FEATURES and res["provenance"][
        "w10_features"
    ] == list(FROZEN_FEATURES)
    print(
        f"G2  W10 frozen         : files changed since {W10_COMMIT}: {diff or 'none'}; "
        f"w10.trainings calls {trains}; own model fits {own_fits or 'none'}; 7 features frozen {feats_ok}"
    )
    if diff or trains != 1 or own_fits or not feats_ok:
        failures.append("G2")

    # --- G3 history intact ----------------------------------------------------------------------
    mism = []
    for pos in POSITIONS:
        a = load_position_week_data(canon, pos, arms_mod.MIN_TRAIN_SEASON, SEASON - 1)
        b = load_position_week_data(con, pos, arms_mod.MIN_TRAIN_SEASON, SEASON - 1)
        if _frame_hash(a) != _frame_hash(b):
            mism.append(pos)
    da = w9.durable_table(canon, through=SEASON - 1)
    db = w9.durable_table(con, through=SEASON - 1)
    dur_same = _frame_hash(da.assign(week=0)) == _frame_hash(db.assign(week=0))
    hist_ok = None
    if args.w10_history:
        hist_ok = (
            hashlib.sha256(Path(args.w10_history).read_bytes()).hexdigest()
            == hashlib.sha256(Path(args.w10).read_bytes()).hexdigest()
        )
    print(
        f"G3  history intact     : 2015-2025 training frames differing {mism or 'none'}; durable "
        f"<= 2025 identical {dur_same}; W10 2021-2025 re-run on the 2026 database byte-identical "
        f"{hist_ok if hist_ok is not None else 'NOT SUPPLIED'}"
    )
    if mism or not dur_same or hist_ok is not True:
        failures.append("G3")

    # --- G4 anti-peek ---------------------------------------------------------------------------
    sha = hashlib.sha256(Path(CANONICAL_DB).read_bytes()).hexdigest()
    rows26 = {
        t: canon.execute(f"SELECT count(*) FROM {t} WHERE season >= ?", [SEASON]).fetchone()[0]
        for t in OUTCOME_TABLES
    }
    # Every repository module the W14 runner loads (in a fresh process); only the adapter and the
    # CLI that declare the NGS download may mention it, and nothing on the path may read it.
    loaded = json.loads(
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import json, sys; import scripts.research.w14_2026_validation; "
                "print(json.dumps(sorted({getattr(m, '__file__', None) or '' "
                "for m in list(sys.modules.values())})))",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    root = Path.cwd()
    repo = [
        str(Path(f).relative_to(root))
        for f in loaded
        if f.startswith(str(root / "src")) or f.startswith(str(root / "scripts"))
    ]
    ngs = sorted(
        rel for rel in repo if rel not in NGS_DECLARERS and NGS.search(Path(rel).read_text())
    )
    print(
        f"G4  anti-peek          : canonical sha {'unchanged' if sha == CANONICAL_SHA else 'CHANGED'}; "
        f"canonical 2026 outcome rows {rows26}; of {len(repo)} repository modules the runner loads, "
        f"reading NGS: {ngs or 'none'}"
    )
    if sha != CANONICAL_SHA or any(rows26.values()) or ngs:
        failures.append("G4")

    # --- G5 walk-forward ------------------------------------------------------------------------
    leaks = 0
    for pos in POSITIONS:
        f = load_position_week_data(con, pos, arms_mod.MIN_TRAIN_SEASON, SEASON - 1)
        leaks += int(int(f.season.max()) >= SEASON)
    print(f"G5  walk-forward       : 2026 training frames containing 2026 rows: {leaks}")
    if leaks:
        failures.append("G5")

    # --- G6 later weeks cannot move earlier predictions -----------------------------------------
    if args.skip_redaction:
        print("G6  later weeks        : SKIPPED")
    else:
        full_feats = con.execute(
            f"SELECT player_id, season, week, {', '.join(FULL_FEATURES)}, team "
            "FROM player_week_features WHERE season = ? ORDER BY player_id",
            [SEASON],
        ).fetchdf()
        panel = op.build_panel(con, POSITIONS)
        dur = w9.durable_table(con, through=SEASON)
        b_full = arms_mod.train_with_extra_features(
            con,
            w9.durable_panel(panel, dur, shuffle=False),
            list(mech.DURABLE_FEATURES),
            arm=w14.ARM_B,
            seasons=(SEASON,),
        )
        parts = []
        bad6 = 0
        for week in eligible:
            r = _redacted_predictions(args.db, week)
            ref = full_feats[full_feats.week == week].reset_index(drop=True)
            same_f = ref.equals(r["features"].reset_index(drop=True))
            a_ref = {k: v for k, v in c26.by_key.items() if k[2] == week}
            b_ref = {k: v for k, v in b_full.by_key.items() if k[2] == week}
            same_a = a_ref == r["A"] and bool(a_ref)
            same_b = b_ref == r["B"] and bool(b_ref)
            bad6 += int(not (same_f and same_a and same_b))
            parts.append(
                f"wk{week}: features {'=' if same_f else '≠'} ({len(ref)}), A {'=' if same_a else '≠'} "
                f"({len(a_ref)}), B {'=' if same_b else '≠'} ({len(b_ref)})"
            )
        print("G6  later weeks        : " + "; ".join(parts))
        if bad6:
            failures.append("G6")

    # --- G7 no forbidden inputs -----------------------------------------------------------------
    dp = w9.durable_panel(
        op.build_panel(con, POSITIONS), w9.durable_table(con, through=SEASON), False
    )
    cols = list(dp.columns)
    forbidden = ("ecr", "injur", "depth", "news", "status", "practice", "vegas", "market", "2026")
    bad7 = [c for c in cols if any(t in c.lower() for t in forbidden)]
    ok7 = cols == [*KEYS, *FROZEN_FEATURES] and not bad7
    print(
        f"G7  inputs             : B's added frame columns {cols[3:]}; forbidden {bad7 or 'none'}"
    )
    if not ok7:
        failures.append("G7")

    # --- G8 eligibility -------------------------------------------------------------------------
    table = {r["week"]: r for r in res["weeks"]}
    evaluated = sorted(w for w, r in table.items() if r["status"] == "EVALUATED")
    sched = json.loads(Path("data/w14/schedule/manifest.json").read_text())
    sched_ok = hashlib.sha256(Path(sched["path"]).read_bytes()).hexdigest() == sched["sha256"]
    cells_weeks = sorted(
        {int(k.split("-")[1]) for w in res["full_ppr"]["cells"].values() for k in w}
    )
    excluded = {
        w: (r["status"], r["reason"][:60]) for w, r in table.items() if not r["eligible"] and w <= 4
    }
    print(
        f"G8  eligibility        : evaluated {evaluated}; cell weeks {cells_weeks}; schedule sha "
        f"{'ok' if sched_ok else 'MISMATCH'}; excluded so far {excluded}"
    )
    if evaluated != eligible or cells_weeks != eligible or not sched_ok:
        failures.append("G8")

    # --- G9 identity ----------------------------------------------------------------------------
    known = {r[0] for r in con.execute("SELECT player_id FROM players").fetchall()}
    ids = set()
    for key in weeks:
        ids |= {
            r[0]
            for r in con.execute(
                "SELECT player_id FROM player_week_stats WHERE season = ? AND week = ?",
                [SEASON, int(key.split("-")[1])],
            ).fetchall()
        }
    unknown = len(ids - known)
    teams = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT t FROM games, UNNEST([home_team, away_team]) AS u(t) WHERE season = ?",
            [SEASON],
        ).fetchall()
    }
    bad_teams = sorted(
        {
            r[0]
            for r in con.execute(
                "SELECT DISTINCT team FROM player_week_stats WHERE season = ?", [SEASON]
            ).fetchall()
        }
        - teams
    )
    print(
        f"G9  identity           : 2026 evaluated-week players without a canonical record "
        f"{unknown}/{len(ids)}; team codes outside games {bad_teams or 'none'}"
    )
    if unknown or bad_teams:
        failures.append("G9")

    # --- G10 W10's own numbers ------------------------------------------------------------------
    if args.w10_verbatim:
        verb = json.loads(Path(args.w10_verbatim).read_text())
        n10 = bad10 = 0
        for tag in ("full_ppr", "half_ppr"):
            n, b = _cells_equal(res[tag]["cells"], verb[tag]["cells"], weeks)
            n10, bad10 = n10 + n, bad10 + b
        checked = res["full_ppr"]["boards_checked"] + res["half_ppr"]["boards_checked"]
        print(
            f"G10 W10's own numbers  : {n10:,} per-week values vs the verbatim W10 2026 run, "
            f"mismatches {bad10}; recomputed boards matching W10's capture@10: {checked}"
        )
        if bad10 or not n10 or not checked:
            failures.append("G10")
    else:
        print("G10 W10's own numbers  : verbatim run NOT SUPPLIED")
        failures.append("G10")

    # --- G11 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G11 determinism        : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w14.json"
            subprocess.run(
                [sys.executable, str(RUNNER), "--db", args.db, "--out", str(out)],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(out.read_bytes()).hexdigest()
        b = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
        print(
            f"G11 determinism        : {a[:16]} vs {b[:16]} -> {'identical' if a == b else 'DIFFERENT'}"
        )
        if a != b:
            failures.append("G11")

    # --- G12 upstream ---------------------------------------------------------------------------
    if args.repro_summary:
        lines = Path(args.repro_summary).read_text().strip().splitlines()
        ok = len(lines) == N_UPSTREAM and all("BYTE-IDENTICAL" in ln for ln in lines)
        print(
            f"G12 upstream           : {len(lines)} reproduced artifacts, all byte-identical: {ok}"
        )
        if not ok:
            failures.append("G12")
    else:
        print("G12 upstream           : no reproduction record supplied")
        failures.append("G12")

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
