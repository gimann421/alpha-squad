"""D101 -- do D78's Y0-Y3 arms differ in TOP-6 IDENTIFICATION, as well as in MAE?

Read-only. Adds an evaluation layer on top of the registered arms; it changes no arm definition,
no gate, and no production module. `evaluation/projection_specification.py` is imported and used
verbatim -- `select_training_rows` supplies each arm's training frame and `_fit_predict` supplies
M6's estimator, exactly as `measure_arm` does -- so the predictions scored here are the same
predictions D78's gates are computed on. That identity is not assumed: `--verify` re-derives
`measure_arm`'s own MAE/RMSE/Spearman/top-decile-bias from the retained per-player predictions and
fails loudly if any of them differs.

    uv run python scripts/research/d101_y_arm_identification.py --out <dir>

PRE-REGISTRATION (written before any arm's identification result was inspected; see
docs/D101_Y0_Y3_IDENTIFICATION.md sections 3-4)
==========================================================================================

POPULATION.  `PREREGISTERED_TARGET_SEASONS` = (2022, 2023, 2024, 2025) x QB/RB/WR/TE, the window
D78 registered, unchanged. 2021 is reported as a separate, clearly-labelled transparency panel and
never as part of a decision: at target season 2021 both Y2 and Y3 fall back to their controls'
training rows exactly (verified, not asserted from prose), so every 2021 cell is a structural tie
that would dilute the contrast rather than inform it.

METRIC (primary).  `top6_hit_rate` = |realized top 6 INTERSECT projected top 6| / 6, per
(arm, season, position). Identical to D100's definition: realized top 6 is the six highest by the
realized season total within the position pool, the projected top 6 is the six highest by that
arm's prediction over the SAME pool, and both orderings break exact ties on `player_id` ascending
-- the determinism convention D54 pinned for the draft engine. The realized set depends only on
outcomes and is computed once per (season, position), never per arm.

METRICS (supporting).  Mann-Whitney AUC for realized-top-6 membership, and Spearman against the
realized total -- the latter read from `measure_arm`, not recomputed, so it is literally D78's G4
quantity. Both are imported from D100's committed script rather than reimplemented, so "the same
definition as D100" is enforced by construction instead of by comment.

COMPARISONS.  Paired against the registered control Y0 on identical (season, position) cells,
plus Y3-vs-Y1 because that is the question the phase exists to answer -- Y3's only difference from
Y1 is the Y2 sentinel repair. Reported at BOTH resolutions: the 16 position-season cells (D78's own
G5 unit) and the 4 season clusters (the independent unit D97/D99/D100 use). Wins/ties/losses are
reported alongside every interval because at four clusters the sign pattern carries more
information than the width.

MULTIPLICITY.  Declared exploratory in advance. Three arms are compared against control on a new
metric and no existing project registration corrects for it, so no identification result may be
called significant on an uncorrected interval. Bonferroni context is printed, not applied as a
gate, and no threshold is chosen after seeing a result.

WHAT THIS LAYER MAY NOT DO.  It does not modify, reweight, or re-rank any arm; the identification
metric is never fed back into training, arm selection, or the gates. D78's G1-G7 are evaluated by
`evaluation_gates` unchanged and reported beside these numbers on a separate axis.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from statistics import mean, stdev

import duckdb
import numpy as np
import pandas as pd

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.projection_specification import (
    MIN_TRAIN_ROWS,
    POSITIONS,
    PREREGISTERED_CONTROL,
    PREREGISTERED_TARGET_SEASONS,
    Y_ARMS,
    _fit_predict,
    evaluate_gates,
    measure_arm,
    select_training_rows,
)
from alpha_squad.models.established.season_level import TARGET_COLUMN, load_season_level_data
from alpha_squad.models.uncertainty.run import MODEL_VERSION

TOP_N = 6
#: The 2021 panel. Reported, never decided on -- see the module docstring.
TRANSPARENCY_SEASON = 2021
#: t(k-1, .975), two-sided.
T_CRIT = {3: 3.182, 4: 2.776, 15: 2.131}


def _load_d100():
    """D100's committed script, for its `auc` and `top_set`. Reusing the code is the only way to
    make "the same definition as D100" checkable rather than asserted in a comment."""
    path = Path(__file__).resolve().parent / "d100_feature_signal.py"
    spec = importlib.util.spec_from_file_location("d100_feature_signal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D100 = _load_d100()


class UniverseMismatchError(RuntimeError):
    """Raised when the arms are not being scored on identical player pools. Loud by design: a
    silent pool difference would make every paired comparison below compare denominators."""


def predictions_for_cell(
    con: duckdb.DuckDBPyConnection, season: int, position: str, min_train_season: int = 2015
) -> tuple[pd.DataFrame, dict[str, np.ndarray]] | None:
    """The shared target pool for one (season, position), plus each arm's prediction over it.

    The pool is `load_season_level_data`'s target slice, which depends only on (position, season)
    -- never on the arm. That is what makes the comparison paired; it is asserted, not trusted."""
    all_data = load_season_level_data(con, position, min_train_season, season)
    target = all_data[all_data["target_season"] == season]
    control_rows = select_training_rows(PREREGISTERED_CONTROL, all_data, season)
    if target.empty or len(control_rows) < MIN_TRAIN_ROWS:
        return None  # the same skip condition `measure_arm` applies

    if set(target["target_season"]) != {season}:
        raise UniverseMismatchError(f"{season}/{position}: target slice is not one season")

    predictions: dict[str, np.ndarray] = {}
    for arm in Y_ARMS:
        train = select_training_rows(arm, all_data, season)
        if train["target_season"].max() >= season:
            raise UniverseMismatchError(f"{arm} {season}/{position}: training row from >= target")
        predictions[arm] = _fit_predict(train, target)
        if len(predictions[arm]) != len(target):
            raise UniverseMismatchError(f"{arm} {season}/{position}: prediction count != pool size")
    return target, predictions


def identification_row(target: pd.DataFrame, predicted: np.ndarray) -> dict:
    """D100's top-6 identification, over a pool the caller has already proven shared."""
    pool = pd.DataFrame(
        {
            "player_id": target["player_id"].to_numpy(),
            "realized": target[TARGET_COLUMN].to_numpy(),
            "predicted": predicted,
        }
    )
    realized_top = D100.top_set(pool, "realized", ascending=False, n=TOP_N)
    projected_top = D100.top_set(pool, "predicted", ascending=False, n=TOP_N)
    labels = pool["player_id"].isin(realized_top).to_numpy().astype(int)
    hits = len(realized_top & projected_top)
    return {
        "n_pool": len(pool),
        "top6_hits": hits,
        "top6_hit_rate": hits / TOP_N,
        "auc": D100.auc(pool["predicted"].to_numpy(), labels),
    }


def _recompute_gate_metrics(target: pd.DataFrame, predicted: np.ndarray) -> dict:
    """`measure_arm`'s own metric block, re-derived from the retained predictions. Used only to
    prove the two agree -- if they ever diverge, the identification numbers describe a different
    fit from the one the gates describe, and the run must fail rather than be reported."""
    actual = target[TARGET_COLUMN].to_numpy()
    order = np.argsort(-predicted)
    k = max(1, int(round(0.10 * len(predicted))))
    top = order[:k]
    return {
        "mae": float(np.abs(actual - predicted).mean()),
        "rmse": float(np.sqrt(((actual - predicted) ** 2).mean())),
        "spearman": float(pd.Series(predicted).corr(pd.Series(actual), method="spearman")),
        "top_decile_bias": float((actual[top] - predicted[top]).mean()),
    }


def run(
    con: duckdb.DuckDBPyConnection, seasons: tuple[int, ...], verify: bool
) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    notes: list[str] = []
    for season in seasons:
        for position in POSITIONS:
            cell = predictions_for_cell(con, season, position)
            if cell is None:
                notes.append(f"skipped {season}/{position}: measure_arm's own skip condition")
                continue
            target, predictions = cell
            for arm in Y_ARMS:
                row = {"arm": arm, "season": season, "position": position}
                row.update(identification_row(target, predictions[arm]))
                recomputed = _recompute_gate_metrics(target, predictions[arm])
                row.update(recomputed)
                if verify:
                    official = measure_arm(con, arm, season, position)
                    if official is None:
                        raise UniverseMismatchError(f"{arm} {season}/{position}: measure_arm None")
                    for metric, value in recomputed.items():
                        if not np.isclose(value, getattr(official, metric), rtol=0, atol=1e-9):
                            raise UniverseMismatchError(
                                f"{arm} {season}/{position}: {metric} {value} != "
                                f"measure_arm's {getattr(official, metric)} -- the identification "
                                "layer is not scoring the same fit as the gates"
                            )
                    row["fell_back"] = official.fell_back
                    row["n_train"] = official.n_train
                    row["n_train_seasons"] = official.n_train_seasons
                rows.append(row)
    return rows, notes


def _paired(rows: list[dict], arm: str, control: str, metric: str):
    """Per-cell deltas, keyed by (season, position), for a paired comparison."""
    by_key = {(r["season"], r["position"], r["arm"]): r[metric] for r in rows}
    keys = sorted({(r["season"], r["position"]) for r in rows})
    out = {}
    for season, position in keys:
        a = by_key.get((season, position, arm))
        c = by_key.get((season, position, control))
        if a is not None and c is not None:
            out[(season, position)] = a - c
    return out


#: Sign-classification tolerance. Every delta this script classifies is a difference of means of
#: sixths, so the smallest genuinely non-zero season-level value is 1/24 ~ 0.042 -- five orders of
#: magnitude above this floor. Without it, a season whose four per-cell deltas cancel exactly
#: (e.g. +1/6 and -1/6) sums to 6.9e-18 in IEEE-754 and is counted as a WIN rather than a tie.
#: That defect was present in this script's first run and is recorded as a correction in
#: docs/D101_Y0_Y3_IDENTIFICATION.md; D54's determinism convention applies to tie CLASSIFICATION
#: just as much as to tie BREAKING.
SIGN_TOLERANCE = 1e-12


def _sign_counts(values: list[float]) -> tuple[int, int, int]:
    """(wins, ties, losses), with exact cancellation classified as a tie rather than a win."""
    w = sum(1 for v in values if v > SIGN_TOLERANCE)
    losses = sum(1 for v in values if v < -SIGN_TOLERANCE)
    return w, len(values) - w - losses, losses


def _interval(values: list[float]) -> tuple[float, float, float, str]:
    k = len(values)
    md = mean(values)
    if k < 2 or stdev(values) == 0:
        return md, float("nan"), float("nan"), "n/a (no spread)"
    se = stdev(values) / k**0.5
    tc = T_CRIT.get(k - 1, 2.776)
    return md, md / se, se, f"[{md - tc * se:+.3f}, {md + tc * se:+.3f}]"


def _report_pair(rows: list[dict], arm: str, control: str, metric: str, label: str) -> None:
    deltas = _paired(rows, arm, control, metric)
    if not deltas:
        return
    cells = list(deltas.values())
    w, t_, losses = _sign_counts(cells)
    md, tstat, _, ci = _interval(cells)
    by_season: dict[int, list[float]] = {}
    for (season, _), value in deltas.items():
        by_season.setdefault(season, []).append(value)
    season_means = [mean(v) for _, v in sorted(by_season.items())]
    smd, stat, _, sci = _interval(season_means)
    sw, st, sl = _sign_counts(season_means)
    print(
        f"  {label:<14}{md:>+9.4f}{f'{w}W/{t_}T/{losses}L':>12}{tstat:>8.2f}{ci:>20}"
        f"   | seasons {smd:>+8.4f} {sw}W/{st}T/{sl}L t={stat:>6.2f} {sci}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/alpha_squad.duckdb")
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    verify = not args.no_verify

    con = duckdb.connect(args.db, read_only=True)
    print(f"board vintage {compute_board_vintage(con).combined_hash}")
    print(f"registered window {PREREGISTERED_TARGET_SEASONS}  positions {POSITIONS}")
    print(f"control {PREREGISTERED_CONTROL}  arms {Y_ARMS}  parity verification {verify}\n")

    for season in PREREGISTERED_TARGET_SEASONS:
        if season not in BACKTEST_SEASONS:
            raise UniverseMismatchError(f"{season} is outside BACKTEST_SEASONS {BACKTEST_SEASONS}")
        if season in (2020, 2026):
            raise UniverseMismatchError(f"{season} must never enter a decision")

    rows, notes = run(con, PREREGISTERED_TARGET_SEASONS, verify)
    (out / "d101_rows.json").write_text(json.dumps(rows))
    for note in notes:
        print(f"  NOTE {note}")

    print("POOL PARITY -- are all four arms scored on identical player pools?")
    pools: dict[tuple[int, str], set[int]] = {}
    ok = True
    for r in rows:
        pools.setdefault((r["season"], r["position"]), set()).add(r["n_pool"])
    for key, sizes in sorted(pools.items()):
        if len(sizes) != 1:
            ok = False
            print(f"    MISMATCH {key}: {sizes}")
    print(f"    {len(pools)} cells, identical pool size in every one: {ok}")
    if not ok:
        raise UniverseMismatchError("arms were scored on different pools")

    print("\n  D100 universe cross-check (does this pool match `uncertainty_predictions`?)")
    for season in PREREGISTERED_TARGET_SEASONS:
        for position in POSITIONS:
            n_pred = con.execute(
                "SELECT count(*) FROM uncertainty_predictions "
                "WHERE season = ? AND position = ? AND model_version = ?",
                [season, position, MODEL_VERSION],
            ).fetchone()[0]
            n_here = next(
                r["n_pool"] for r in rows if r["season"] == season and r["position"] == position
            )
            flag = "" if n_pred == n_here else "   <-- DIFFERS"
            if flag:
                print(f"    {season} {position}: here {n_here}, uncertainty_predictions "
                      f"{n_pred}{flag}")
    print("    (only differing cells are listed)")

    if verify:
        fb = [(r["arm"], r["season"], r["position"]) for r in rows if r.get("fell_back")]
        print(f"\n  ARM FALLBACKS (arm's filter left too little, so it reverts to its unfiltered "
              f"frame): {len(fb)}")
        for arm in Y_ARMS:
            hits = sorted({(s, p) for a, s, p in fb if a == arm})
            if hits:
                print(f"    {arm}: {sorted({s for s, _ in hits})} "
                      f"({len(hits)} of {len(pools)} cells)")

    frame = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("AXIS 1 -- PROJECTION QUALITY: D78's G1-G7, evaluated by the shipped `evaluate_gates`")
    print("=" * 100)
    for arm in Y_ARMS:
        if arm == PREREGISTERED_CONTROL:
            continue
        verdict = evaluate_gates(frame, arm)
        print(f"\n  {arm}: {'PASSES all seven' if verdict.passed else 'FAILS'}")
        for gate in verdict.gates:
            print(f"    [{'PASS' if gate.passed else 'FAIL'}] {gate.name:<28} {gate.detail}")

    print("\n" + "=" * 100)
    print("AXIS 2 -- IDENTIFICATION (newly registered, exploratory)")
    print("=" * 100)
    print("\n  MEAN top6_hit_rate / mean hits per position-season")
    print(f"  {'arm':<6}" + "".join(f"{p:>10}" for p in POSITIONS) + f"{'ALL':>12}{'hits':>8}")
    for arm in Y_ARMS:
        cells = []
        for position in POSITIONS:
            vals = [r["top6_hit_rate"] for r in rows
                    if r["arm"] == arm and r["position"] == position]
            cells.append(f"{mean(vals):>10.3f}" if vals else f"{'-':>10}")
        allv = [r["top6_hit_rate"] for r in rows if r["arm"] == arm]
        hits = [r["top6_hits"] for r in rows if r["arm"] == arm]
        print(f"  {arm:<6}" + "".join(cells) + f"{mean(allv):>12.4f}{mean(hits):>8.2f}")

    print("\n  MEAN top6_hits by season (summed over the four positions, max 24)")
    print(f"  {'arm':<6}" + "".join(f"{s:>10}" for s in PREREGISTERED_TARGET_SEASONS))
    for arm in Y_ARMS:
        cells = [
            sum(r["top6_hits"] for r in rows if r["arm"] == arm and r["season"] == s)
            for s in PREREGISTERED_TARGET_SEASONS
        ]
        print(f"  {arm:<6}" + "".join(f"{c:>10}" for c in cells))

    for metric, name in (("auc", "AUC"), ("spearman", "Spearman (G4's own quantity)")):
        print(f"\n  MEAN {name}")
        print(f"  {'arm':<6}" + "".join(f"{p:>10}" for p in POSITIONS) + f"{'ALL':>12}")
        for arm in Y_ARMS:
            cells = []
            for position in POSITIONS:
                vals = [r[metric] for r in rows
                        if r["arm"] == arm and r["position"] == position]
                cells.append(f"{mean(vals):>10.3f}" if vals else f"{'-':>10}")
            allv = [r[metric] for r in rows if r["arm"] == arm]
            print(f"  {arm:<6}" + "".join(cells) + f"{mean(allv):>12.4f}")

    print("\n" + "-" * 100)
    print("PAIRED COMPARISONS -- top6_hit_rate. Left: 16 position-season cells (D78's G5 unit).")
    print("Right: 4 season clusters (the independent unit). EXPLORATORY -- see multiplicity.")
    print("-" * 100)
    print(f"  {'contrast':<14}{'mean d':>9}{'W/T/L':>12}{'t':>8}{'95% CI':>20}")
    for arm in Y_ARMS:
        if arm != PREREGISTERED_CONTROL:
            _report_pair(rows, arm, PREREGISTERED_CONTROL, "top6_hit_rate", f"{arm} - Y0")
    _report_pair(rows, "Y3", "Y1", "top6_hit_rate", "Y3 - Y1")
    _report_pair(rows, "Y3", "Y2", "top6_hit_rate", "Y3 - Y2")

    print("\n  same contrasts on AUC")
    for arm in Y_ARMS:
        if arm != PREREGISTERED_CONTROL:
            _report_pair(rows, arm, PREREGISTERED_CONTROL, "auc", f"{arm} - Y0")
    _report_pair(rows, "Y3", "Y1", "auc", "Y3 - Y1")

    print("\n  PER-POSITION sign of the Y3 - Y1 top6_hits difference")
    print(f"  {'pos':<6}" + "".join(f"{s:>8}" for s in PREREGISTERED_TARGET_SEASONS)
          + f"{'mean':>9}{'W/T/L':>10}")
    d = _paired(rows, "Y3", "Y1", "top6_hits")
    for position in POSITIONS:
        vals = [d.get((s, position)) for s in PREREGISTERED_TARGET_SEASONS]
        present = [v for v in vals if v is not None]
        cells = "".join(f"{v:>+8.0f}" if v is not None else f"{'-':>8}" for v in vals)
        w, t_, losses = _sign_counts(present)
        print(f"  {position:<6}{cells}{mean(present):>+9.2f}{f'{w}W/{t_}T/{losses}L':>10}")

    print("\n  MULTIPLICITY: 3 arms x 2 identification metrics compared against control, "
          "declared exploratory in advance.")
    print("  Bonferroni over the 3 primary-metric arm contrasts needs t(3) ~ 4.86 at k=4 seasons, "
          "t(15) ~ 2.69 at 16 cells.")
    print("  No identification result below may be called significant on an uncorrected interval.")

    # 2021 transparency panel -- reported, never decided on.
    print("\n" + "=" * 100)
    print(f"TRANSPARENCY PANEL -- target season {TRANSPARENCY_SEASON}, EXCLUDED FROM EVERY DECISION")
    print("=" * 100)
    panel, _ = run(con, (TRANSPARENCY_SEASON,), verify)
    (out / "d101_2021_panel.json").write_text(json.dumps(panel))
    print(f"  {'arm':<6}{'top6 hits (of 24)':>20}{'mean hit rate':>16}{'mean MAE':>12}")
    for arm in Y_ARMS:
        sub = [r for r in panel if r["arm"] == arm]
        print(f"  {arm:<6}{sum(r['top6_hits'] for r in sub):>20}"
              f"{mean(r['top6_hit_rate'] for r in sub):>16.4f}"
              f"{mean(r['mae'] for r in sub):>12.3f}")
    ident = {
        pair: all(
            np.isclose(
                next(r[m] for r in panel if r["arm"] == pair[0] and r["season"] == s
                     and r["position"] == p),
                next(r[m] for r in panel if r["arm"] == pair[1] and r["season"] == s
                     and r["position"] == p),
            )
            for s in (TRANSPARENCY_SEASON,)
            for p in POSITIONS
            for m in ("mae", "top6_hit_rate", "auc")
        )
        for pair in (("Y2", "Y0"), ("Y3", "Y1"))
    }
    for (a, b), same in ident.items():
        print(f"  {a} is byte-identical to {b} at {TRANSPARENCY_SEASON}: {same}")
    print("  -> 2021 contributes only structural ties for Y2/Y3 and is excluded, as registered.")


if __name__ == "__main__":
    main()
