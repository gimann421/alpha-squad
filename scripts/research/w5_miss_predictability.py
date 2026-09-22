"""W5/E1 --- **EXPLORATORY**: is an Alpha top-of-board miss predictable before the cutoff?

`docs/weekly/W5_PREREGISTRATION.md` §10 registers this as exploratory and bars it from every
decision rule. It may generate a hypothesis; it may not confirm one, and it is **not** a feature
proposal. A model trained to predict its own parent model's errors is a diagnostic instrument.

The question, made concrete
---------------------------
Alpha elevates ten players into each positional top-10. Some of them finish outside the realized
top-24 -- the pre-registered FALSE POSITIVE. If that outcome were predictable on Friday from
information Alpha already holds, the cliff would be a *representation* failure: the signal is in
the inputs and the model is not using it. If it is close to unpredictable, the cliff is closer to
irreducible weekly variance and no amount of re-representing those inputs will move it.

Design
------
* **Unit**: one player-week that Alpha ranked inside its positional top-10.
* **Target**: 1 if the player finished outside the realized top-24 of that position.
* **Features**: pre-cutoff only -- Alpha's own prediction and lagged features, the role-change
  measures, prior-season rank, the opponent's prior points allowed. No current-week outcome, no
  usage, no ECR, no injury (whose STRICT coverage is 0.2%, see the results document).
* **Walk-forward**: trained on seasons strictly before the evaluated one, exactly as Alpha is.
* **Baseline**: the same model on 200 label permutations *within season*, so the reported AUC is
  read against what this sample size and class balance produce by chance rather than against 0.5.

    uv run python scripts/research/w5_miss_predictability.py --out reports/weekly/w5_e1.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import duckdb
import numpy as np
from catboost import CatBoostClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context  # noqa: E402
from alpha_squad.evaluation.weekly.regret import FP_PRED_DEPTH, FP_REAL_DEPTH  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR  # noqa: E402
from scripts.research.w5_topboard_forensics import (  # noqa: E402
    CONFIRMATORY_POSITIONS,
    SEASONS,
    build_context,
    positional_cell,
)

#: Fixed here, before the diagnostic was run. Deliberately the same shape as the production
#: weekly model so the answer is about the information, not about a bigger classifier.
MODEL_KWARGS = {
    "iterations": 200,
    "depth": 4,
    "learning_rate": 0.05,
    "loss_function": "Logloss",
    "verbose": False,
    "random_seed": 42,
}
N_PERMUTATIONS = 200
MIN_TRAIN_ROWS = 200

FEATURES = (
    "predicted_points",
    "predicted_rank",
    "games_played_prior",
    "snap_pct_avg_last3",
    "fp_ppr_avg_last3",
    "fp_ppr_avg_season_to_date",
    "opportunity_last1",
    "opportunity_avg_prior3",
    "opportunity_delta",
    "snap_delta",
    "snap_sd_prior3",
    "weeks_since_last_game",
    "prior_season_rank",
    "opponent_pa_prior",
    "team_epa_avg_last3",
    "team_epa_delta",
    "depth_team_prior",
)


def _auc(y: list[int], p: list[float]) -> float | None:
    """Rank-based AUC (the Mann-Whitney form), ties averaged.

    Hand-implemented for the reason every statistic in this package is: it enters a reported
    number, so it should be readable here rather than depend on a resolved library version."""
    pos = [i for i, v in enumerate(y) if v == 1]
    neg = [i for i, v in enumerate(y) if v == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(p)), key=lambda i: p[i])
    ranks = [0.0] * len(p)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and p[order[j + 1]] == p[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return (sum(ranks[i] for i in pos) - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def collect(con) -> dict[str, list[dict]]:
    """One row per player-week Alpha ranked inside its positional top-10."""
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    rows: dict[str, list[dict]] = {p: [] for p in CONFIRMATORY_POSITIONS}
    for snap in snapshots:
        ctx = build_context(con, snap)
        for position in CONFIRMATORY_POSITIONS:
            common, _alpha_b, preds = positional_cell(con, snap, position, FULL_PPR)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            realized = {r.player_id: float(r.realized) for r in common.rows}
            universe = sorted(preds)
            pred_order = sorted(universe, key=lambda p: (-preds[p], p))
            real_rank = {
                p: i
                for i, p in enumerate(sorted(universe, key=lambda p: (-realized[p], p)), start=1)
            }
            for rank, pid in enumerate(pred_order[:FP_PRED_DEPTH], start=1):
                c = ctx.get(pid)
                row = {
                    "season": snap.season,
                    "week": snap.week,
                    "player_id": pid,
                    "predicted_points": preds[pid],
                    "predicted_rank": float(rank),
                    "y": 1 if real_rank[pid] > FP_REAL_DEPTH else 0,
                }
                for f in FEATURES:
                    if f in row:
                        continue
                    row[f] = None if c is None else getattr(c, f, None)
                rows[position].append(row)
    return rows


def evaluate(rows: list[dict], rng_seed: int = 0) -> dict:
    """Walk-forward AUC, against a within-season label-permutation baseline."""
    out: dict = {"by_season": {}, "n": len(rows), "base_rate": None}
    ys = [r["y"] for r in rows]
    out["base_rate"] = sum(ys) / len(ys) if ys else None
    all_y: list[int] = []
    all_p: list[float] = []
    for season in SEASONS:
        train = [r for r in rows if r["season"] < season]
        test = [r for r in rows if r["season"] == season]
        if len(train) < MIN_TRAIN_ROWS or not test:
            continue
        if len({r["y"] for r in train}) < 2:
            continue
        x_tr = np.array([[_f(r[f]) for f in FEATURES] for r in train], dtype=float)
        y_tr = np.array([r["y"] for r in train])
        x_te = np.array([[_f(r[f]) for f in FEATURES] for r in test], dtype=float)
        model = CatBoostClassifier(**MODEL_KWARGS)
        model.fit(x_tr, y_tr)
        p_te = [float(v) for v in model.predict_proba(x_te)[:, 1]]
        y_te = [r["y"] for r in test]
        auc = _auc(y_te, p_te)
        out["by_season"][str(season)] = {
            "n_train": len(train),
            "n_test": len(test),
            "base_rate": sum(y_te) / len(y_te),
            "auc": auc,
        }
        all_y += y_te
        all_p += p_te
    out["pooled_auc"] = _auc(all_y, all_p)
    out["pooled_n"] = len(all_y)

    # Permutation baseline: shuffle labels, keep the model and the features fixed. Answers
    # "what AUC does this sample size and class balance produce by chance", which 0.5 does not.
    rng = np.random.default_rng(rng_seed)
    null_aucs = []
    for _ in range(N_PERMUTATIONS):
        shuffled = list(all_y)
        rng.shuffle(shuffled)
        a = _auc(shuffled, all_p)
        if a is not None:
            null_aucs.append(a)
    if null_aucs:
        null_aucs.sort()
        out["permutation_baseline"] = {
            "mean": statistics.fmean(null_aucs),
            "p95": null_aucs[int(0.95 * (len(null_aucs) - 1))],
            "p05": null_aucs[int(0.05 * (len(null_aucs) - 1))],
            "n": len(null_aucs),
        }
        out["exceeds_permutation_p95"] = bool(
            out["pooled_auc"] is not None and out["pooled_auc"] > out["permutation_baseline"]["p95"]
        )
    return out


def _f(v) -> float:
    """Missing values become NaN, which CatBoost handles natively.

    Deliberately NOT `fillna(0.0)` like the production loader: a missing `opponent_pa_prior`
    means "not enough prior weeks", and coding that as zero points allowed would invent the
    strongest possible matchup. The production model's choice is audited in the results
    document, not copied here."""
    return float("nan") if v is None else float(v)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w5_e1.json")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        snap = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(snap['local_path'])}"
        )
    context.wire_snapshot_views(con, SEASONS)

    print("EXPLORATORY (W5 §10 E1) -- may generate a hypothesis, may not confirm one.\n")
    print("collecting Alpha's predicted top-10 player-weeks ...")
    rows = collect(con)
    result = {
        "model": MODEL_KWARGS,
        "features": list(FEATURES),
        "alpha_model": alpha_mod.WEEKLY_PROJECTION_BASE_MODEL,
        "target": f"predicted top-{FP_PRED_DEPTH}, finished outside realized top-{FP_REAL_DEPTH}",
        "positions": {},
    }
    for position, data in rows.items():
        print(
            f"  {position}: {len(data):,} rows, base rate {sum(r['y'] for r in data) / len(data):.3f}"
        )
        result["positions"][position] = evaluate(data)
    print()
    for position, r in result["positions"].items():
        pb = r.get("permutation_baseline", {})
        print(
            f"  {position}: pooled AUC={r['pooled_auc']:.4f} (n={r['pooled_n']:,}), "
            f"permutation p95={pb.get('p95', float('nan')):.4f} -> "
            f"{'above chance' if r.get('exceeds_permutation_p95') else 'NOT above chance'}"
        )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
