"""W6 --- the validity gates that must pass BEFORE any W6 result is interpreted.

`docs/weekly/W6_PREREGISTRATION.md` §11 lists them and states the rule: *"If any gate fails, stop
and fix the instrument before reading results."* W5's G10 is the precedent -- it failed, it was
real, and the fix had to precede interpretation.

  G1  control fidelity   retraining with production's loss reproduces production's stored
                         predictions EXACTLY. Without this, no arm comparison means anything.
  G2  single-variable    the arms differ from production in `loss_function` and nothing else
  G3  universe           every arm predicts the same keys, and every board scores the same players
  G4  causality          no arm's training frame contains the season it predicts
  G5  no-ECR             each board's order is reproducible from its own predictions alone
  G6  already-played     no evaluated player's team had kicked off at the cutoff
  G7  null-calibration   the copula null achieves the Spearman it is asked for
  G8  determinism        the runner produces byte-identical output on a repeat run
  G9  upstream           W3, W4 and W5 still reproduce exactly

**G1 is the load-bearing one.** Everything W6 claims is a difference between a re-implementation
and itself with one argument changed; if the re-implementation is not production, the difference
is measuring something else.

Exit code is non-zero if any gate fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import (  # noqa: E402
    arms as arms_mod,
)
from alpha_squad.evaluation.weekly import (  # noqa: E402
    audit,
    benchmark,
    nulls,
    snapshots,
)
from alpha_squad.evaluation.weekly.metrics import spearman  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from alpha_squad.models.established.data import load_position_week_data  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES, TARGET_COLUMN  # noqa: E402
from alpha_squad.models.established.train import MODEL_SPECS  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    ALL_POSITIONS,
    SEASONS,
    positional_cell,
)

#: G7 is a 200-draw calibration per cell, so it samples weeks at a fixed stride rather than
#: running them all. The stride is positional, never chosen by which weeks pass.
SAMPLE_EVERY = 10

UPSTREAM = (
    ("W3", "scripts/research/w3_alpha_benchmark.py", "reports/weekly/w3_results.json"),
    ("W4", "scripts/research/w4_flex_forensics.py", "reports/weekly/w4_results.json"),
    ("W5", "scripts/research/w5_topboard_forensics.py", "reports/weekly/w5_results.json"),
)


def _wire(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        snap = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(snap['local_path'])}"
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


def _diff(a_path: str, b_path: str) -> dict:
    fa = dict(_flatten(json.loads(Path(a_path).read_text())))
    fb = dict(_flatten(json.loads(Path(b_path).read_text())))
    worst, numeric, other = 0.0, 0, 0
    for key in set(fa) & set(fb):
        x, y = fa[key], fb[key]
        if isinstance(x, int | float) and isinstance(y, int | float) and not isinstance(x, bool):
            numeric += 1
            worst = max(worst, abs(x - y))
        elif x != y:
            other += 1
    return {
        "numeric": numeric,
        "max_abs_diff": worst,
        "other_mismatches": other,
        "same_keys": set(fa) == set(fb),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--results", default="reports/weekly/w6_results.json")
    ap.add_argument("--skip-determinism", action="store_true")
    ap.add_argument("--skip-upstream", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    _wire(con)
    failures: list[str] = []

    # --- G1 control fidelity --------------------------------------------------------------
    trained = {arm: arms_mod.train_arm(con, arm) for arm in arms_mod.ARMS}
    fidelity = arms_mod.compare_to_production(
        trained[arms_mod.CONTROL_ARM], arms_mod.load_production_predictions(con)
    )
    print(
        f"G1 control fidelity : {fidelity['exact_matches']:,}/{fidelity['n_shared']:,} exact "
        f"({fidelity['exact_share']:.4%}), max abs diff {fidelity['max_abs_diff']}, "
        f"unmatched keys {fidelity['only_in_trained'] + fidelity['only_in_stored']}"
    )
    if fidelity["exact_share"] != 1.0 or fidelity["only_in_stored"] or fidelity["only_in_trained"]:
        failures.append("G1")

    # --- G2 single-variable ----------------------------------------------------------------
    _cls, prod_kwargs, prod_features = MODEL_SPECS["ml_catboost"]
    expected = {k: v for k, v in prod_kwargs.items() if k != "loss_function"}
    g2 = (
        dict(arms_mod.BASE_KWARGS) == dict(expected)
        and "loss_function" not in arms_mod.BASE_KWARGS
        and list(prod_features) == list(FULL_FEATURES)
        and TARGET_COLUMN == "target_fantasy_points_ppr"
    )
    print(f"G2 single-variable  : only `loss_function` differs from production: {g2}")
    if not g2:
        failures.append("G2")

    # --- G3 universe -----------------------------------------------------------------------
    keysets = [set(p.by_key) for p in trained.values()]
    same_keys = all(k == keysets[0] for k in keysets)
    board_mismatch = 0
    weeks = audit.week_coverage(con, SEASONS).snapshots
    for snap in weeks:
        for position in ALL_POSITIONS:
            base = trained[arms_mod.CONTROL_ARM].for_week(snap.season, snap.week, position)
            if not base:
                continue
            common0, board0, _ = positional_cell(con, snap, position, FULL_PPR, base)
            if len(common0.rows) < benchmark.MIN_EVALUABLE:
                continue
            universe = {r.player_id for r in board0.rows}
            for arm in arms_mod.ARMS:
                preds = trained[arm].for_week(snap.season, snap.week, position)
                _c, board, _k = positional_cell(
                    con, snap, position, FULL_PPR, preds, universe=universe
                )
                if {r.player_id for r in board.rows} != universe:
                    board_mismatch += 1
    print(
        f"G3 universe         : identical prediction keys across arms: {same_keys}; "
        f"boards scoring a different player set: {board_mismatch}"
    )
    if not same_keys or board_mismatch:
        failures.append("G3")

    # --- G4 causality ----------------------------------------------------------------------
    # Not a re-statement of the loop: it loads the frame `train_arm` actually loads and asks for
    # the newest season in it.
    leaks = 0
    for target_season in arms_mod.TRAIN_SEASONS:
        for position in ALL_POSITIONS:
            frame = load_position_week_data(
                con, position, arms_mod.MIN_TRAIN_SEASON, target_season - 1
            )
            if frame.empty:
                continue
            if int(frame["season"].max()) >= target_season:
                leaks += 1
    print(f"G4 causality        : training frames containing the predicted season: {leaks}")
    if leaks:
        failures.append("G4")

    # --- G5 no-ECR / G6 already-played -------------------------------------------------------
    ecr_dependence = contaminated = 0
    for snap in weeks:
        playing = snapshots.teams_already_playing(con, snap)
        already = {
            r[0]
            for r in con.execute(
                "SELECT s.player_id FROM player_week_stats s "
                "WHERE s.season = ? AND s.week = ? AND s.team = ANY(?)",
                [snap.season, snap.week, list(playing) or [""]],
            ).fetchall()
        }
        for position in ALL_POSITIONS:
            base = trained[arms_mod.CONTROL_ARM].for_week(snap.season, snap.week, position)
            if not base:
                continue
            common0, board0, _ = positional_cell(con, snap, position, FULL_PPR, base)
            if len(common0.rows) < benchmark.MIN_EVALUABLE:
                continue
            universe = {r.player_id for r in board0.rows}
            contaminated += len(universe & already)
            for arm in arms_mod.ARMS:
                preds = trained[arm].for_week(snap.season, snap.week, position)
                _c, board, kept = positional_cell(
                    con, snap, position, FULL_PPR, preds, universe=universe
                )
                expect = [p for p in sorted(kept, key=lambda p: (-kept[p], p)) if p in universe]
                got = [r.player_id for r in sorted(board.rows, key=lambda r: r.ecr)]
                if expect != got:
                    ecr_dependence += 1
    print(f"G5 no-ECR           : boards needing more than their own predictions: {ecr_dependence}")
    print(f"G6 already-played   : evaluated players whose team had kicked off: {contaminated}")
    failures += [g for g, bad in (("G5", ecr_dependence), ("G6", contaminated)) if bad]

    # --- G7 null calibration -----------------------------------------------------------------
    worst, checked = 0.0, 0
    for snap in weeks[::SAMPLE_EVERY]:
        for position in ("RB", "WR", "TE"):
            base = trained[arms_mod.PRIMARY_ARM].for_week(snap.season, snap.week, position)
            if not base:
                continue
            common, board, _ = positional_cell(con, snap, position, FULL_PPR, base)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            pred, real = board.ranks_and_points()
            rho = spearman(pred, real)
            if rho is None or rho <= 0:
                continue
            latent = nulls.calibrate_latent(real, rho, snap.season, snap.week, position)
            got = [
                spearman(
                    nulls.draw_null_ranking(
                        real, rho, snap.season, snap.week, position, d, latent=latent
                    ).pred_rank,
                    real,
                )
                for d in range(nulls.N_SIM)
            ]
            got = [g for g in got if g is not None]
            worst = max(worst, abs(sum(got) / len(got) - rho))
            checked += 1
    print(f"G7 null-calibration : worst |achieved - target| over {checked} cells: {worst:.2e}")
    if worst > nulls.CALIB_TOL:
        failures.append("G7")

    # --- G8 determinism ----------------------------------------------------------------------
    if args.skip_determinism:
        print("G8 determinism      : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rerun.json"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/research/w6_upper_outcome.py",
                    "--db",
                    args.db,
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            a = hashlib.sha256(Path(args.results).read_bytes()).hexdigest()
            b = hashlib.sha256(out.read_bytes()).hexdigest()
        same = a == b
        print(
            f"G8 determinism      : {a[:16]} vs {b[:16]} -> {'identical' if same else 'DIFFERENT'}"
        )
        if not same:
            failures.append("G8")

    # --- G9 upstream reproduction --------------------------------------------------------------
    if args.skip_upstream:
        print("G9 upstream         : SKIPPED")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            parts = []
            for tag, script, tracked in UPSTREAM:
                out = Path(tmp) / f"{tag}.json"
                subprocess.run(
                    [sys.executable, script, "--db", args.db, "--out", str(out)],
                    check=True,
                    capture_output=True,
                )
                d = _diff(str(out), tracked)
                parts.append(f"{tag} {d['numeric']:,} leaves diff {d['max_abs_diff']:g}")
                if d["max_abs_diff"] != 0 or d["other_mismatches"] or not d["same_keys"]:
                    failures.append("G9")
            print("G9 upstream         : " + " | ".join(parts))

    print()
    if failures:
        print(f"FAILED: {', '.join(sorted(set(failures)))} -- do not interpret W6 results.")
        return 1
    print(f"all gates PASS  ({len(weeks)} weeks, {len(arms_mod.ARMS)} arms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
