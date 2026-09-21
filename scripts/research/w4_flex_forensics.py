"""W4 --- FLEX top-of-board forensic audit: is cross-position calibration the bottleneck?

Runs exactly what `docs/weekly/W4_PREREGISTRATION.md` specifies. **Builds no model, fits no
positional model, tunes nothing, and never touches production.** It reads the weekly
predictions the unmodified `alpha-squad train established` path wrote, then:

  1. reproduces the W3 baseline on the identical universe;
  2. builds the oracle / counterfactual boards that bound each half of the problem;
  3. fits four causal per-position calibrations walk-forward and applies them;
  4. decomposes pairwise ordering into within- vs cross-position buckets (the exact,
     additive decomposition);
  5. reports composition, directional pair bias, and per-season robustness.

    uv run python scripts/research/w4_flex_forensics.py --out reports/weekly/w4_results.json

Read-only against the database; writes one JSON.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import alpha as alpha_mod
from alpha_squad.evaluation.weekly import (
    audit,
    benchmark,
    calibration,
    counterfactual,
    crosspos,
    diagnostics,
    noise,
)
from alpha_squad.evaluation.weekly.metrics import evaluate_cell
from alpha_squad.evaluation.weekly.scoring import FLEX_POSITIONS, FULL_PPR

SEASONS = (2021, 2022, 2023, 2024, 2025)
#: Depth 5 is added for the positional top-of-board forensics the brief requests. It is a new
#: DEPTH of the existing metrics, not a new metric.
W4_DEPTHS: tuple[int, ...] = (5, 10, 25, 50)
HEADLINE = (
    "spearman",
    "kendall",
    "pairwise",
    "decisive",
    *(f"capture@{k}" for k in W4_DEPTHS),
    *(f"precision@{k}" for k in W4_DEPTHS),
)
#: Every system scored on the FLEX board. CF_A is current Alpha (the W3 control).
FLEX_SYSTEMS = (
    "CF_A",
    "ECR",
    "B0_season_to_date_ppg",
    *calibration.CALIBRATION_METHODS,
    *counterfactual.COUNTERFACTUALS,
)


def wire(con: duckdb.DuckDBPyConnection) -> dict:
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    ecr = require_snapshot(con, "dynastyprocess", "fp_ecr_history")
    xw = require_snapshot(con, "dynastyprocess", "player_ids")
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW ecr AS SELECT * FROM {reader_expr(ecr['local_path'])}"
    )
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW xwalk AS SELECT * FROM {reader_expr(xw['local_path'])}"
    )
    return {
        "ecr_sha256": ecr["sha256"],
        "xwalk_sha256": xw["sha256"],
        "alpha_model": alpha_mod.WEEKLY_PROJECTION_BASE_MODEL,
        "calibration_methods": list(calibration.CALIBRATION_METHODS),
        "counterfactuals": list(counterfactual.COUNTERFACTUALS),
        "min_fit_sample": calibration.MIN_FIT_SAMPLE,
    }


def _common_flex_board(con, snap):
    """The W3 universe, unchanged: ECR board -> played -> Alpha-rankable."""
    ref = benchmark.flex_board(con, snap, FULL_PPR)
    played = {r.player_id for r in ref.evaluable}
    ref_played = alpha_mod.restrict_board(ref, played)
    preds = alpha_mod.load_alpha_predictions(con, snap.season, snap.week, positions=FLEX_POSITIONS)
    alpha_b, _cov = alpha_mod.alpha_board(ref_played, preds)
    keep = {r.player_id for r in alpha_b.rows}
    common = alpha_mod.restrict_board(ref_played, keep)
    week_preds = {pid: preds[pid] for pid in keep}
    return common, alpha_b, week_preds


def run_flex(con, snapshots, *, tiebreak: bool = True) -> tuple[dict, dict, dict, dict]:
    cells: dict[str, dict] = {}
    decomp: dict[str, list] = {}
    bias: dict[str, list] = {}
    composition: dict[str, list] = {}

    for snap in snapshots:
        common, alpha_b, preds = _common_flex_board(con, snap)
        if len(common.rows) < benchmark.MIN_EVALUABLE:
            continue
        position_of = {r.player_id: r.position for r in common.rows}
        key = f"{snap.season}-{snap.week}"

        boards: dict[str, object] = {
            "CF_A": alpha_b,
            "ECR": common,
            **benchmark.baseline_boards(con, common, FULL_PPR),
        }

        # --- causal calibrations: fitted ONLY on strictly-prior completed player-weeks ---
        window = calibration.FitWindow(snap.season, snap.week)
        sample = calibration.load_prior_sample(
            con, window, FLEX_POSITIONS, alpha_mod.WEEKLY_PROJECTION_BASE_MODEL
        )
        # Ties MANUFACTURED by the step-function transforms (CAL_QUANTILE, CAL_RANKPCT map
        # distinct predictions onto the same calibrated value) resolve in favour of Alpha's
        # original order. Without this the dense re-rank falls back to player_id and reshuffles
        # players the transform was meant to leave alone, turning a pure cross-position effect
        # into a mixture of that and random within-position noise. Pre-registration Part 7;
        # verified by the monotonicity gate, which FAILED (458 violations) before this fix.
        alpha_rank = {
            r.player_id: float(i)
            for i, r in enumerate(
                sorted(common.rows, key=lambda r: (-preds[r.player_id], r.player_id)), start=1
            )
        }
        for method in calibration.CALIBRATION_METHODS:
            scores = calibration.calibrated_scores(method, sample, preds, position_of)
            cal_board, _ = alpha_mod.alpha_board(
                common, scores, tiebreak=alpha_rank if tiebreak else None
            )
            boards[method] = cal_board

        # --- oracles / counterfactuals: diagnostics only, never candidates ---
        for name in counterfactual.COUNTERFACTUALS:
            boards[name] = counterfactual.build(name, common, preds, use_tiebreak=tiebreak)

        for sysname, board in boards.items():
            pred, real = board.ranks_and_points()
            slot = cells.setdefault(sysname, {})
            if len(pred) < benchmark.MIN_EVALUABLE:
                slot[key] = {"invalid": True}
                continue
            slot[key] = evaluate_cell(pred, real, depths=W4_DEPTHS).as_row()

            ordered = sorted(board.rows, key=lambda r: r.ecr)
            pos = [r.position for r in ordered]
            pr = [r.ecr for r in ordered]
            rl = [float(r.realized) for r in ordered]
            decomp.setdefault(sysname, []).append(
                {
                    "season": snap.season,
                    "week": snap.week,
                    **crosspos.decompose_pairs(pos, pr, rl).as_row(),
                }
            )
            bias.setdefault(sysname, []).append(crosspos.pair_bias(pos, pr, rl))
            for k in W4_DEPTHS:
                comp = diagnostics.flex_composition(pos, pr, rl, k)
                if comp:
                    composition.setdefault(f"{sysname}@{k}", []).append(comp)
    return cells, decomp, bias, composition


def run_positional(con, snapshots) -> dict:
    """Positional top-of-board forensics: Alpha vs ECR vs baseline at depths 5/10/25/50."""
    cells: dict[str, dict] = {}
    for snap in snapshots:
        for position in FLEX_POSITIONS:
            ref = benchmark.positional_board(con, snap, position, FULL_PPR)
            played = {r.player_id for r in ref.evaluable}
            ref_played = alpha_mod.restrict_board(ref, played)
            preds = alpha_mod.load_alpha_predictions(
                con, snap.season, snap.week, positions=(position,)
            )
            alpha_b, _ = alpha_mod.alpha_board(ref_played, preds)
            keep = {r.player_id for r in alpha_b.rows}
            common = alpha_mod.restrict_board(ref_played, keep)
            systems = {
                "ALPHA": alpha_b,
                "ECR": common,
                **benchmark.baseline_boards(con, common, FULL_PPR),
            }
            for sysname, board in systems.items():
                pred, real = board.ranks_and_points()
                slot = cells.setdefault(f"{position}|{sysname}", {})
                key = f"{snap.season}-{snap.week}"
                if len(pred) < benchmark.MIN_EVALUABLE:
                    slot[key] = {"invalid": True}
                    continue
                slot[key] = evaluate_cell(pred, real, depths=W4_DEPTHS).as_row()
    return cells


def summarise(cells: dict, comparisons: list[tuple[str, str]]) -> dict:
    out: dict = {"distributions": {}, "paired": {}, "outcomes": {}}
    for sysname, weeks in cells.items():
        for metric in HEADLINE:
            vals = [
                r.get(metric)
                for r in weeks.values()
                if not r.get("invalid") and r.get(metric) is not None
            ]
            d = noise.describe(metric, vals)
            if d:
                out["distributions"].setdefault(sysname, {})[metric] = d.as_row()
    for a_name, b_name in comparisons:
        if a_name not in cells or b_name not in cells:
            continue
        for metric in HEADLINE:
            a = {
                k: r[metric]
                for k, r in cells[a_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            b = {
                k: r[metric]
                for k, r in cells[b_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
            if pd_:
                out["paired"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = pd_.as_row()
            po = diagnostics.paired_outcome(metric, a_name, b_name, a, b)
            if po:
                out["outcomes"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = po.as_row()
    return out


def flex_vs_positional(flex_cells: dict, pos_cells: dict) -> dict:
    """Is the FLEX deficit *larger* than the deficit Alpha already carries inside each position?

    Brief Part 22 --- "investigate whether the FLEX problem is even real". A difference of
    differences, paired within week: `(CF_A - ECR)_FLEX` minus the mean of
    `(ALPHA - ECR)_P` over RB/WR/TE. If the combination step were adding a problem of its own,
    this would be reliably negative. If FLEX is simply inheriting the positional deficit, it
    sits at zero.

    **Not one of the pre-registration's §9 robustness checks** --- it answers a separate question
    the brief asks, it was specified before any result existed, and it does **not** feed the
    §7.1 verdict, which is decided by `X` and `W` on FLEX capture@10 alone."""
    out: dict = {}
    for metric in HEADLINE:
        deltas: dict[str, float] = {}
        for week, row in flex_cells.get("CF_A", {}).items():
            ecr_row = flex_cells.get("ECR", {}).get(week, {})
            if row.get("invalid") or ecr_row.get("invalid"):
                continue
            if row.get(metric) is None or ecr_row.get(metric) is None:
                continue
            per_pos = []
            for position in FLEX_POSITIONS:
                a = pos_cells.get(f"{position}|ALPHA", {}).get(week, {})
                b = pos_cells.get(f"{position}|ECR", {}).get(week, {})
                if a.get("invalid") or b.get("invalid"):
                    continue
                if a.get(metric) is None or b.get(metric) is None:
                    continue
                per_pos.append(a[metric] - b[metric])
            if len(per_pos) != len(FLEX_POSITIONS):
                continue
            deltas[week] = (row[metric] - ecr_row[metric]) - statistics.fmean(per_pos)
        d = noise.describe(metric, list(deltas.values()))
        if d:
            out[metric] = d.as_row()
    return out


def leave_one_season_out(cells: dict, a_name: str, b_name: str, metric: str) -> dict:
    """Pre-registered robustness check 1: recompute the headline effect dropping each season."""
    out: dict = {}
    for drop in SEASONS:
        a = {
            k: r[metric]
            for k, r in cells.get(a_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and not k.startswith(str(drop))
        }
        b = {
            k: r[metric]
            for k, r in cells.get(b_name, {}).items()
            if not r.get("invalid") and r.get(metric) is not None and not k.startswith(str(drop))
        }
        pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
        if pd_:
            out[f"drop_{drop}"] = pd_.as_row()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w4_results.json")
    ap.add_argument(
        "--legacy-ties",
        action="store_true",
        help=(
            "DIAGNOSTIC ONLY. Reproduce the defective tie handling this phase caught: ties "
            "manufactured by a calibration, and ties in an oracle's realized value curve, fall "
            "back to player_id instead of the ordering they are meant to preserve. This FAILS "
            "validity gate G4 by construction. It exists so the corrected-versus-defective "
            "comparison reported in docs/weekly/W4_FLEX_FORENSICS_RESULTS.md S16 is "
            "reproducible rather than quoted from a run nobody can repeat. Never the default."
        ),
    )
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    prov = wire(con)
    print(f"provenance: {json.dumps(prov, indent=2)}")
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"weeks: {len(snapshots)}\n")

    print("[1/4] FLEX: control, ECR, baseline, 4 causal calibrations, 6 counterfactuals ...")
    if args.legacy_ties:
        print("!! --legacy-ties: DEFECTIVE tie handling, fails gate G4 by construction !!\n")
    flex_cells, decomp, bias, composition = run_flex(con, snapshots, tiebreak=not args.legacy_ties)
    print(f"      {len(flex_cells)} FLEX systems scored")

    print("[2/4] positional forensics (RB / WR / TE at depths 5/10/25/50) ...")
    pos_cells = run_positional(con, snapshots)

    print("[3/4] paired differences, win/loss, Wilcoxon ...")
    comparisons = [(m, "CF_A") for m in calibration.CALIBRATION_METHODS]
    comparisons += [(c, "CF_A") for c in counterfactual.COUNTERFACTUALS]
    comparisons += [
        ("CF_A", "ECR"),
        ("CF_A", "B0_season_to_date_ppg"),
        ("ECR", "B0_season_to_date_ppg"),
        # How far short of the benchmark each oracle still falls. Same frozen metrics, same
        # universe, same pairing -- it prices the ceiling rather than only the gain.
        ("ORACLE_XPOS", "ECR"),
        ("ORACLE_WITHIN", "ECR"),
    ]
    flex_summary = summarise(flex_cells, comparisons)
    pos_summary = summarise(
        pos_cells,
        [(f"{p}|ALPHA", f"{p}|ECR") for p in FLEX_POSITIONS]
        + [(f"{p}|ALPHA", f"{p}|B0_season_to_date_ppg") for p in FLEX_POSITIONS],
    )

    print("[4/4] robustness: leave-one-season-out on the headline calibration effect ...")
    loso = {
        m: {
            met: leave_one_season_out(flex_cells, m, "CF_A", met)
            for met in ("spearman", "capture@10")
        }
        for m in calibration.CALIBRATION_METHODS
    }

    def mean_of(sysname: str, metric: str) -> float | None:
        vals = [
            r.get(metric)
            for r in flex_cells.get(sysname, {}).values()
            if not r.get("invalid") and r.get(metric) is not None
        ]
        return statistics.fmean(vals) if vals else None

    print(
        "\n  FLEX capture@10:  "
        + "  ".join(
            f"{s}={mean_of(s, 'capture@10'):.4f}"
            for s in ("CF_A", "ECR", "ORACLE_XPOS", "ORACLE_WITHIN", "ORACLE_BOTH")
            if mean_of(s, "capture@10") is not None
        )
    )

    result = {
        "provenance": prov,
        "n_weeks": len(snapshots),
        "flex_cells": flex_cells,
        "flex_summary": flex_summary,
        "positional_cells": pos_cells,
        "positional_summary": pos_summary,
        "pair_decomposition": decomp,
        "pair_bias": bias,
        "composition": composition,
        "robustness_loso": loso,
        "flex_vs_positional": flex_vs_positional(flex_cells, pos_cells),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
