"""W8 validity and leakage gates (pre-registration §10). All must pass before any result is read.

G1  parity -- the one-change trainer with no added feature reproduces production exactly, so
    ALPHA_ORACLE_OPP differs from production in one Class D feature and nothing else
G2  the forecast is W7's -- W8's `f` re-scores to W7's committed M_NEW cells exactly, and W7's
    physical-redaction test re-runs on the forecast's non-production inputs
G3  realized opportunity is outcome only -- `f` is unchanged when the predicted season's realized
    usage is scrambled; the runner feeds realized usage to exactly one model, the Class D arm
G4  ECR is not in Alpha -- no ECR/market/rank token in Alpha's features, and no board or ECR
    quantity in any training frame
G5  no post-Friday news -- no injury, news, Vegas or depth-chart identifier in the W8 code
G6  no realized game information in predictors -- covered by G2 and G3
G7  walk-forward -- no training frame for `f` or ALPHA_ORACLE_OPP contains the predicted season
G8  joins and identity -- unique keys; the runner's in-line gates (G = G_F + G_S + G_C, capture
    equals the program metric, attributions sum to G, missing usage = zero opportunity)
G9  cutoff and universe -- W8's universe is W7's, and W8's CF_A / ECR / ORACLE_USAGE boards
    re-score to W7's committed cells exactly; 0 kicked-off players
G10 determinism -- the runner is byte-identical on a repeat run
G11 upstream -- W5, W6 (+ agreement) and W7 reproduce exactly (`--upstream`; otherwise the
    pre-analysis reproduction run is the record)

  uv run python scripts/research/w8_validity_gates.py [--skip-determinism] [--upstream]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import random
import re
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
from alpha_squad.evaluation.weekly import audit, benchmark, context, snapshots  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import spearman, topk_points_capture  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from scripts.research.w6_upper_outcome import positional_cell  # noqa: E402
from scripts.research.w7_opportunity import _pearson, _ranks  # noqa: E402
from scripts.research.w7_validity_gates import _redacted, _same, _wire  # noqa: E402

POSITIONS = ("RB", "WR", "TE")
SEASONS = (2021, 2022, 2023, 2024, 2025)
REDACT_EVERY = 8
RUNNER = Path("scripts/research/w8_ecr_advantage.py")
MODULE = Path("src/alpha_squad/evaluation/weekly/advantage.py")
FORBIDDEN_IDENTIFIERS = (
    "attach_injury",
    "injur",
    "practice",
    "_depth",
    "depth_chart",
    "vegas",
    "odds",
    "spread",
    "news",
)
#: Must be flagged / must NOT be flagged -- G5 checks itself on these before it checks the code,
#: so a matcher that is too loose (the first run's substring match flagged `region_depth`) or too
#: tight (flags nothing) fails loudly instead of silently.
G5_MUST_FLAG = ("_depth", "select * from _depth", "attach_injury", "vegas_total", "odds", "news")
G5_MUST_PASS = ("region_depth", "primary_depth", "flex_depths", "top_hit_depth", "w5_depths")
UPSTREAM = (
    ("W5", "scripts/research/w5_topboard_forensics.py", "reports/weekly/w5_results.json"),
    ("W6", "scripts/research/w6_upper_outcome.py", "reports/weekly/w6_results.json"),
    ("W6-agreement", "scripts/research/w6_board_agreement.py", "reports/weekly/w6_agreement.json"),
    ("W7", "scripts/research/w7_opportunity.py", "reports/weekly/w7_results.json"),
)


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def _code_identifiers(path: Path) -> set[str]:
    """Every identifier, attribute and non-docstring string literal in a file -- the things that
    can name a data source. Docstrings and comments are prose and are excluded."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        ):
            docstrings.add(id(node.body[0].value))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            out.add(node.attr.lower())
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            out.add(node.value.lower())
    return out


def _forbidden(ident: str) -> list[str]:
    """Forbidden terms appearing in `ident` as a term, not as the tail of a longer word: a term
    must not be preceded by a letter or digit. `_depth` (the depth-chart view) matches;
    `region_depth` (a board-depth constant) does not."""
    return [t for t in FORBIDDEN_IDENTIFIERS if re.search(rf"(?<![a-z0-9]){re.escape(t)}", ident)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w8_results.json")
    ap.add_argument("--w7", default="reports/weekly/w7_results.json")
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--upstream", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    context.wire_snapshot_views(con, tuple(range(2015, 2026)))
    failures: list[str] = []
    w7 = json.loads(Path(args.w7).read_text())
    w8 = json.loads(Path(args.results).read_text())

    # --- G1 parity ------------------------------------------------------------------------------
    empty = pd.DataFrame(columns=["player_id", "season", "week"])
    control = arms_mod.train_with_extra_features(con, empty, [])
    stored = {
        k: v for k, v in arms_mod.load_production_predictions(con).items() if k in control.by_key
    }
    fid = arms_mod.compare_to_production(control, stored)
    print(
        f"G1  parity            : {fid['exact_matches']:,}/{fid['n_shared']:,} exact, "
        f"max abs diff {fid['max_abs_diff']}"
    )
    if fid["exact_share"] != 1.0 or fid["only_in_trained"] or fid["only_in_stored"]:
        failures.append("G1")

    # --- G2 the forecast is W7's, and it is pre-Friday ------------------------------------------
    panel = op.build_panel(con, POSITIONS)
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    weeks = audit.week_coverage(con, SEASONS).snapshots
    committed = w7["forecast"]["cells"]
    mismatched = compared = 0
    universe: dict[tuple[str, str], set[str]] = {}
    for snap in weeks:
        key = f"{snap.season}-{snap.week}"
        for position in POSITIONS:
            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=(position,)
            )
            if not preds:
                continue
            common, board, _kept = positional_cell(con, snap, position, FULL_PPR, preds)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            players = {r.player_id for r in board.rows}
            universe[(key, position)] = players
            rows = [
                (pid, idx[(pid, snap.season, snap.week)])
                for pid in sorted(players)
                if (pid, snap.season, snap.week) in idx
            ]
            rows = [(pid, i) for pid, i in rows if not pd.isna(panel.at[i, "y_xfp"])]
            if len(rows) < benchmark.MIN_EVALUABLE:
                continue
            ids = [pid for pid, _ in rows]
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
            theirs = committed[f"{position}|T_XFP|M_NEW"][key]
            for m, v in mine.items():
                compared += 1
                if v != theirs[m]:
                    mismatched += 1
    print(
        f"G2  forecast is W7's  : {compared:,} per-week M_NEW metrics re-scored from W8's f; "
        f"mismatches vs W7's committed cells: {mismatched}"
    )
    if mismatched or not compared:
        failures.append("G2")

    moved: list[str] = []
    checked = 0
    for snap in weeks[::REDACT_EVERY]:
        red = _redacted(args.db, snap.season, snap.week)
        try:
            rp = op.build_panel(red, POSITIONS)
        finally:
            red.close()
        a = panel[(panel.season == snap.season) & (panel.week == snap.week)].set_index("player_id")
        b = rp[(rp.season == snap.season) & (rp.week == snap.week)].set_index("player_id")
        if set(a.index) != set(b.index):
            moved.append(f"{snap.season}-{snap.week}: row set changed")
            continue
        for pid in a.index:
            checked += 1
            for col in op.NEW:
                if not _same(a.at[pid, col], b.at[pid, col]):
                    moved.append(f"{snap.season}-{snap.week}:{pid}:{col}")
        if b["y_xfp"].notna().any():
            moved.append(f"{snap.season}-{snap.week}: redaction removed nothing")
    print(
        f"G2  redaction         : forecast inputs that moved when every outcome at/after the week "
        f"was removed ({checked:,} player-weeks): {len(moved)}"
    )
    if moved:
        failures.append("G2")

    # --- G3 realized opportunity is outcome only ------------------------------------------------
    scrambled = panel.copy()
    rng = random.Random(0)
    target_rows = scrambled.index[(scrambled.season == 2025)]
    scrambled.loc[target_rows, "y_xfp"] = [rng.uniform(0, 40) for _ in range(len(target_rows))]
    changed = 0
    for position in POSITIONS:
        a = op.walk_forward(panel, position, "T_XFP", "M_NEW", (2025,))
        b = op.walk_forward(scrambled, position, "T_XFP", "M_NEW", (2025,))
        changed += int(sum(1 for i in a.index if not _same(a.at[i], b.at[i])))
    src = RUNNER.read_text()
    oracle_calls = src.count("train_with_extra_features(")
    arm_named = "arm=ORACLE_ARM" in src
    print(
        f"G3  outcome only      : forecasts changed by scrambling the predicted season's realized "
        f"usage: {changed}; realized-usage model calls in the runner: {oracle_calls} "
        f"(the Class D arm: {arm_named})"
    )
    if changed or oracle_calls != 1 or not arm_named:
        failures.append("G3")

    # --- G4 ECR is not in Alpha -------------------------------------------------------------------
    bad_features = [
        f for f in FULL_FEATURES if any(t in f.lower() for t in ("ecr", "market", "rank", "adp"))
    ]
    extra_cols_line = [ln for ln in src.splitlines() if "extra[[" in ln or "extra = panel[[" in ln]
    ecr_in_extra = any("ecr" in ln.lower() or "rank" in ln.lower() for ln in extra_cols_line)
    print(
        f"G4  ECR not in Alpha  : ECR/market/rank tokens in Alpha's features: {bad_features or 'none'}"
        f"; ECR in any training frame: {ecr_in_extra}"
    )
    if bad_features or ecr_in_extra or not extra_cols_line:
        failures.append("G4")

    # --- G5 no post-Friday news ------------------------------------------------------------------
    self_ok = all(_forbidden(x) for x in G5_MUST_FLAG) and not any(
        _forbidden(x) for x in G5_MUST_PASS
    )
    hits = sorted(
        {
            (str(path), ident, tok)
            for path in (RUNNER, MODULE)
            for ident in _code_identifiers(path)
            for tok in _forbidden(ident)
        }
    )
    print(
        f"G5  no news sources   : matcher self-test {'passes' if self_ok else 'FAILS'}; "
        f"forbidden identifiers in W8 code: {hits or 'none'}"
    )
    if hits or not self_ok:
        failures.append("G5")
    print("G6  realized context : covered by G2 (redaction) and G3 (scrambled outcomes)")

    # --- G7 walk-forward ------------------------------------------------------------------------
    leaks = 0
    for position in POSITIONS:
        pos = panel[panel.position == position]
        for season in SEASONS:
            train = pos[(pos.season >= op.MIN_TRAIN_SEASON) & (pos.season < season)]
            if not train.empty and int(train.season.max()) >= season:
                leaks += 1
            frame = arms_mod.load_position_week_data(
                con, position, arms_mod.MIN_TRAIN_SEASON, season - 1
            )
            if not frame.empty and int(frame.season.max()) >= season:
                leaks += 1
    print(f"G7  walk-forward     : training frames containing the predicted season: {leaks}")
    if leaks:
        failures.append("G7")

    # --- G8 joins and identity -----------------------------------------------------------------
    dup = int(panel.duplicated(["player_id", "season", "week"]).sum())
    resid = max(w8["full_ppr"]["identity_max_residual"], w8["half_ppr"]["identity_max_residual"])
    print(
        f"G8  joins / identity  : duplicate panel keys {dup}; max |G - (G_F+G_S+G_C)| "
        f"{resid:.2e} (the runner aborts above 1e-9, on any capture mismatch, any attribution "
        f"that does not sum to G, and any missing usage row with opportunity)"
    )
    if dup or resid >= 1e-9:
        failures.append("G8")

    # --- G9 cutoff and universe ----------------------------------------------------------------
    n_w8 = w8["full_ppr"]["n_players"]
    n_w7 = {p: w7["forecast"]["pooled"][f"{p}|T_OPP|M_NEW"]["n"] for p in POSITIONS}
    n_uni = {p: sum(len(v) for (k, q), v in universe.items() if q == p) for p in POSITIONS}
    board_mismatch = board_compared = 0
    for name in ("CF_A", "ECR", "ORACLE_USAGE"):
        for position in POSITIONS:
            mine = w8["full_ppr"]["counterfactual"]["cells"][f"{position}|{name}"]
            theirs = w7["ranking"]["cells"][f"{position}|{name}"]
            if set(mine) != set(theirs):
                board_mismatch += 1
                continue
            for key, row in mine.items():
                for m, v in row.items():
                    board_compared += 1
                    t = theirs[key].get(m)
                    if not (
                        v == t
                        or (
                            isinstance(v, float)
                            and isinstance(t, float)
                            and math.isnan(v)
                            and math.isnan(t)
                        )
                    ):
                        board_mismatch += 1
    contaminated = 0
    for snap in weeks:
        playing = snapshots.teams_already_playing(con, snap)
        already = {
            r[0]
            for r in con.execute(
                "SELECT player_id FROM player_week_stats WHERE season=? AND week=? AND team = ANY(?)",
                [snap.season, snap.week, list(playing) or [""]],
            ).fetchall()
        }
        key = f"{snap.season}-{snap.week}"
        for position in POSITIONS:
            contaminated += len(universe.get((key, position), set()) & already)
    print(
        f"G9  universe / cutoff : W8 player-weeks {n_w8} vs W7 {n_w7} vs re-derived {n_uni}; "
        f"board metrics re-scored vs W7: {board_compared:,}, mismatches {board_mismatch}; "
        f"kicked-off players: {contaminated}"
    )
    if n_w8 != n_w7 or n_uni != n_w7 or board_mismatch or not board_compared or contaminated:
        failures.append("G9")

    # --- G10 determinism ------------------------------------------------------------------------
    if args.skip_determinism:
        print("G10 determinism      : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "w8.json"
            subprocess.run(
                [sys.executable, str(RUNNER), "--db", args.db, "--out", str(out)],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(out.read_bytes()).hexdigest()
        b = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
        print(
            f"G10 determinism      : {a[:16]} vs {b[:16]} -> {'identical' if a == b else 'DIFFERENT'}"
        )
        if a != b:
            failures.append("G10")

    # --- G11 upstream ---------------------------------------------------------------------------
    if not args.upstream:
        print(
            "G11 upstream         : not re-run here (the pre-analysis reproduction is the record)"
        )
    else:
        parts = []
        with tempfile.TemporaryDirectory() as tmp:
            for tag, script, committed_path in UPSTREAM:
                out = Path(tmp) / f"{tag}.json"
                subprocess.run(
                    [sys.executable, script, "--db", args.db, "--out", str(out)],
                    check=True,
                    capture_output=True,
                )
                fa = dict(_flatten(json.loads(out.read_text())))
                fb = dict(_flatten(json.loads(Path(committed_path).read_text())))
                worst = 0.0
                bad = set(fa) != set(fb)
                for k in set(fa) & set(fb):
                    x, y = fa[k], fb[k]
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                        worst = max(worst, abs(x - y))
                    elif x != y:
                        bad = True
                parts.append(f"{tag} diff {worst:g}{' KEYS/STRINGS DIFFER' if bad else ''}")
                if worst or bad:
                    failures.append(f"G11:{tag}")
        print("G11 upstream         : " + " | ".join(parts))

    print()
    print("all gates PASS" if not failures else f"FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
