"""W13 --- does a player's own Friday injury designation improve W10's FLEX top 10?

Runs exactly `docs/weekly/W13_PREREGISTRATION.md`. **Research only.** One confirmatory test: W10's
model versus W10 + `own_status` + `own_practice`, built by W12's validated timestamped pipeline
(rows last modified after the Friday cutoff do not exist, W12 A1). ECR is a benchmark only.

  CF_A  CURRENT ALPHA        production's stored predictions (the WR guardrail's reference)
  A     W10                  exactly W10's `ALPHA_PLUS_HISTORICAL`
  B     W10 + OWN INJURY     A + the player's own Friday designation and practice status
  N     NULL                 A + the two features permuted within (season, week, position)
  S     EXPLORATORY          A + `own_status` only; never a verdict input

    uv run python scripts/research/w13_injury_flex.py --out reports/weekly/w13_results.json
    uv run python scripts/research/w13_injury_flex.py --seasons 2026 --out ...   # §9, once collected
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import injuryflex as injf  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w11_mechanism as w11m  # noqa: E402
from scripts.research import w12_timestamped as w12  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    flex_cell,
    leave_one_season_out,
    per_season,
    summarise,
)
from scripts.research.w7_opportunity import universes  # noqa: E402

DEFAULT_SEASONS = (2021, 2022, 2023, 2024)
POSITIONS = ("RB", "WR", "TE")
DEPTHS = topboard.W5_DEPTHS
K = 10
KEYS = ["player_id", "season", "week"]
DURABLE = list(mech.DURABLE_FEATURES)
OWN = list(injf.OWN_FEATURES)
ARM_A = w11m.ARM_B  # "ALPHA_PLUS_HISTORICAL": W10's arm, exactly
ARM_B = "ALPHA_PLUS_OWN_INJURY"
ARM_N = "ALPHA_PLUS_OWN_INJURY_NULL"
ARM_S = "EXPLORATORY_OWN_STATUS_ONLY"
MODEL_ARMS = (ARM_A, ARM_B, ARM_N, ARM_S)
PAIRS = (
    (ARM_B, ARM_A),
    (ARM_B, ARM_N),
    (ARM_N, ARM_A),
    (ARM_S, ARM_A),
    (ARM_B, ARM_S),
    (ARM_A, "CF_A"),
    (ARM_B, "CF_A"),
    ("ECR", ARM_B),
    ("ECR", ARM_A),
)
GUARD_POSITIONAL = ("capture@10", "capture@5", "spearman")
GUARD_FLEX = ("capture@5", "capture@20", "spearman")
ROBUST_METRICS = ("capture@5", "capture@10", "capture@20", "spearman")
FLEX_EXTRA = ("regret@10",)
ZERO = w8.ZERO
_put = w8._put
_gate = w8._gate


# ---------------------------------------------------------------------------------------
# The declared trainings
# ---------------------------------------------------------------------------------------


def frames(panel: pd.DataFrame, dur: pd.DataFrame, inj: pd.DataFrame) -> dict:
    """arm -> (training frame, extra columns). B adds exactly the two own features to W10's."""
    dp = w9.durable_panel(panel, dur, shuffle=False)
    frame_b = dp.merge(inj[[*KEYS, *OWN]], on=KEYS, how="left", validate="one_to_one")
    frame_n = dp.merge(
        w12.permuted(panel, inj)[[*KEYS, *OWN]], on=KEYS, how="left", validate="one_to_one"
    )
    frame_s = frame_b[[*KEYS, *DURABLE, "own_status"]]
    return {
        ARM_B: (frame_b, DURABLE + OWN),
        ARM_N: (frame_n, DURABLE + OWN),
        ARM_S: (frame_s, [*DURABLE, "own_status"]),
    }


def trainings(con, panel, dur, inj, seasons) -> dict:
    fr = frames(panel, dur, inj)
    frame_b, cols_b = fr[ARM_B]
    frame_n, cols_n = fr[ARM_N]
    frame_s, cols_s = fr[ARM_S]
    return {
        ARM_A: w11m.train_b(con, panel, dur, seasons),
        ARM_B: arms_mod.train_with_extra_features(con, frame_b, cols_b, arm=ARM_B, seasons=seasons),
        ARM_N: arms_mod.train_with_extra_features(con, frame_n, cols_n, arm=ARM_N, seasons=seasons),
        ARM_S: arms_mod.train_with_extra_features(con, frame_s, cols_s, arm=ARM_S, seasons=seasons),
    }


# ---------------------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------------------


def _add(store: dict, system: str, key: str, metric: str, value: float) -> None:
    w = store.setdefault(system, {}).setdefault(key, {})
    w[metric] = w.get(metric, 0.0) + float(value)


def _mechanism(ex: dict, key: str, board_a, board_b, preds: dict, group_of, pos_of) -> None:
    """Full PPR, FLEX: B − A capture@10 attributed to the swapped players; movers; bias."""
    pts = {r.player_id: float(r.realized) for r in board_a.evaluable}
    rows = {p: adv.PlayerWeek(p, v, 0.0, 0.0) for p, v in pts.items()}
    order_a, order_b = w8._order(board_a), w8._order(board_b)
    d = adv.decompose_gap(order_b, order_a, rows, K)
    if d is None:
        return
    for tag, grp, groups in (
        ("ATTR_STATUS", group_of, injf.STATUS_GROUPS),
        ("ATTR_POS", pos_of, POSITIONS),
    ):
        attr = mech.attribute_piece(order_b, order_a, rows, K, grp, "G")
        _gate(
            attr is not None and abs(math.fsum(attr.values()) - d["G"]) < 1e-9,
            f"FLEX {key} {tag}: attribution does not sum to the capture gap",
        )
        for g in groups:
            _put(ex, f"FLEX|{tag}", key, g, attr.get(g, 0.0))
    top_a, top_b = set(order_a[:K]), set(order_b[:K])
    _put(ex, "FLEX|OVERLAP", key, "top10_overlap_B_A", len(top_a & top_b) / K)
    for g in injf.STATUS_GROUPS:
        for tag in ("in", "out"):
            _add(ex, "FLEX|MOVERS", key, f"n_{tag}_{g}", 0.0)
            _add(ex, "FLEX|MOVERS", key, f"pts_{tag}_{g}", 0.0)
        for arm in ("A", "B"):
            _add(ex, "FLEX|BIAS", key, f"err_{arm}_{g}", 0.0)
        _add(ex, "FLEX|BIAS", key, f"n_{g}", 0.0)
    for p in sorted(top_b - top_a):
        _add(ex, "FLEX|MOVERS", key, f"n_in_{group_of[p]}", 1.0)
        _add(ex, "FLEX|MOVERS", key, f"pts_in_{group_of[p]}", pts[p])
    for p in sorted(top_a - top_b):
        _add(ex, "FLEX|MOVERS", key, f"n_out_{group_of[p]}", 1.0)
        _add(ex, "FLEX|MOVERS", key, f"pts_out_{group_of[p]}", pts[p])
    for p in sorted(pts):
        g = group_of[p]
        _add(ex, "FLEX|BIAS", key, f"n_{g}", 1.0)
        _add(ex, "FLEX|BIAS", key, f"err_A_{g}", preds[ARM_A][p] - pts[p])
        _add(ex, "FLEX|BIAS", key, f"err_B_{g}", preds[ARM_B][p] - pts[p])


def analyse(con, snapshots, fmt, panel, fc, fc_opp, trained, inj, mechanism: bool) -> dict:
    ppr = fmt.points_per_reception
    status = {
        (r["player_id"], int(r["season"]), int(r["week"])): injf.status_group(r["own_status"])
        for r in inj.to_dict("records")
    }
    cells = w8.collect(con, universes(con, snapshots, fmt), panel, fc, fc_opp, ppr)
    m: dict = {}
    ex: dict = {}
    for (key, pos), cell in sorted(cells.items()):
        snap, common = cell["snap"], cell["common"]
        ids = set(cell["rows"])
        boards = {"CF_A": cell["board_a"], "ECR": common}
        for arm in MODEL_ARMS:
            preds = trained[arm].for_week(snap.season, snap.week, pos)
            boards[arm] = alpha_mod.alpha_board(common, preds, tiebreak=cell["rank_a"])[0]
        for name, board in boards.items():
            _gate({r.player_id for r in board.rows} == ids, f"{key} {pos} {name} universe")
            pr, rlz = board.ranks_and_points()
            m.setdefault(f"{pos}|{name}", {})[key] = evaluate_cell(pr, rlz, depths=DEPTHS).as_row()
    # FLEX, through the existing pooled path
    by_week: dict[str, dict] = {}
    for (key, _pos), cell in cells.items():
        w = by_week.setdefault(key, {"snap": cell["snap"], "alpha": {}})
        w["alpha"].update(cell["alpha_pred"])
    for key in sorted(by_week):
        snap, alpha_all = by_week[key]["snap"], by_week[key]["alpha"]
        commonf, boardf, _k = flex_cell(con, snap, fmt, alpha_all)
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        uni = {r.player_id for r in boardf.rows}
        fb = {"CF_A": boardf, "ECR": commonf}
        preds: dict[str, dict[str, float]] = {}
        pos_of: dict[str, str] = {}
        for arm in MODEL_ARMS:
            pa: dict[str, float] = {}
            for pos in POSITIONS:
                pp = trained[arm].for_week(snap.season, snap.week, pos)
                pa.update(pp)
                pos_of.update({p: pos for p in pp})
            preds[arm] = pa
            fb[arm] = flex_cell(con, snap, fmt, pa, universe=uni)[1]
        best = adv.best_total((float(r.realized) for r in commonf.evaluable), K)
        for name, board in fb.items():
            _gate({r.player_id for r in board.rows} == uni, f"FLEX {key} {name} universe")
            pr, rlz = board.ranks_and_points()
            row = evaluate_cell(pr, rlz, depths=DEPTHS).as_row()
            pts = {r.player_id: float(r.realized) for r in board.evaluable}
            top = math.fsum(pts[p] for p in w8._order(board)[:K])
            row["regret@10"] = best - top
            _gate(
                best <= 0 or abs(top / best - row["capture@10"]) < 1e-9,
                f"FLEX {key} {name}: regret@10 disagrees with capture@10",
            )
            m.setdefault(f"FLEX|{name}", {})[key] = row
        if mechanism:
            group_of = {}
            for p in sorted(uni):
                g = status.get((p, snap.season, snap.week))
                _gate(g is not None, f"FLEX {key} {p}: no injury-table row")
                group_of[p] = g
            _mechanism(ex, key, fb[ARM_A], fb[ARM_B], preds, group_of, pos_of)
    return {"m": m, "ex": ex}


# ---------------------------------------------------------------------------------------
# Summaries and the decision
# ---------------------------------------------------------------------------------------


def _weekly_diffs(m: dict, a: str, b: str, metric: str) -> list[float]:
    av, bv = m.get(a, {}), m.get(b, {})
    return [av[k][metric] - bv[k][metric] for k in sorted(set(av) & set(bv))]


def _series(store: dict, system: str, metric: str) -> dict[str, float]:
    return {k: r.get(metric, 0.0) for k, r in store.get(system, {}).items()}


def mechanism_summary(ex: dict) -> dict:
    zero: dict = {}
    for w in ex.values():
        for k, r in w.items():
            zero.setdefault(k, {}).update({mt: 0.0 for mt in r})
    store = dict(ex) | {ZERO: zero}
    out: dict = {
        "attribution_status": w8.compare(store, "FLEX|ATTR_STATUS", ZERO, list(injf.STATUS_GROUPS)),
        "attribution_position": w8.compare(store, "FLEX|ATTR_POS", ZERO, list(POSITIONS)),
    }
    ov = [r["top10_overlap_B_A"] for r in ex.get("FLEX|OVERLAP", {}).values()]
    out["top10_overlap_B_A"] = statistics.fmean(ov) if ov else None
    movers: dict = {}
    for g in injf.STATUS_GROUPS:
        row: dict = {}
        for tag in ("in", "out"):
            n = _series(ex, "FLEX|MOVERS", f"n_{tag}_{g}")
            p = _series(ex, "FLEX|MOVERS", f"pts_{tag}_{g}")
            row[f"n_{tag}"] = int(math.fsum(n.values()))
            row[f"pts_{tag}"] = math.fsum(p.values())
            row[f"mean_pts_{tag}"] = (
                row[f"pts_{tag}"] / row[f"n_{tag}"] if row[f"n_{tag}"] else None
            )
        movers[g] = row
    out["movers"] = movers
    bias: dict = {}
    for g in injf.STATUS_GROUPS:
        n = _series(ex, "FLEX|BIAS", f"n_{g}")
        row = {"n": int(math.fsum(n.values()))}
        for arm in ("A", "B"):
            err = _series(ex, "FLEX|BIAS", f"err_{arm}_{g}")
            row[f"mean_bias_{arm}"] = math.fsum(err.values()) / row["n"] if row["n"] else None
            row[f"bias_{arm}_ci"] = w8.ratio_ci(err, n) if row["n"] else None
        bias[g] = row
    out["bias"] = bias
    return out


def summaries(res: dict, window: tuple[int, ...]) -> dict:
    keep = {k for w in res["m"].values() for k in w if int(k.split("-")[0]) in window}
    m = {s: {k: r for k, r in w.items() if k in keep} for s, w in res["m"].items()}
    pos_flex = (*POSITIONS, "FLEX")
    comps = [(f"{p}|{a}", f"{p}|{b}") for p in pos_flex for a, b in PAIRS]
    out: dict = {"n_weeks": len(keep), "all": summarise(m, comps)}
    out["regret"] = {
        f"{a}_vs_{b}": w8.compare(m, f"FLEX|{a}", f"FLEX|{b}", list(FLEX_EXTRA)) for a, b in PAIRS
    }
    out["regret_levels"] = {
        b: statistics.fmean(r["regret@10"] for r in m[f"FLEX|{b}"].values())
        for b in ("CF_A", "ECR", *MODEL_ARMS)
        if m.get(f"FLEX|{b}")
    }
    out["per_season"] = {
        f"{p}|{mt}": {
            s: r
            for s, r in per_season(m, f"{p}|{ARM_B}", f"{p}|{ARM_A}", mt).items()
            if int(s) in window
        }
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["loso"] = {
        f"{p}|{mt}": {
            s: r
            for s, r in leave_one_season_out(m, f"{p}|{ARM_B}", f"{p}|{ARM_A}", mt).items()
            if int(s.split("_")[1]) in window
        }
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["sign_flip_p"] = {
        f"FLEX|capture@10|{a}_vs_{b}": injf.sign_flip_p(
            _weekly_diffs(m, f"FLEX|{a}", f"FLEX|{b}", "capture@10")
        )
        for a, b in ((ARM_B, ARM_A), (ARM_B, ARM_N))
    }
    return out


def verdict_inputs(prim: dict, prim_half: dict) -> dict:
    def row(summ, p, mt, a=ARM_B, b=ARM_A):
        return summ["all"]["paired"].get(f"{p}|{a}_vs_{p}|{b}", {}).get(mt)

    guard = {f"{p}|{mt}": row(prim, p, mt) for p in POSITIONS for mt in GUARD_POSITIONAL}
    guard.update({f"FLEX|{mt}": row(prim, "FLEX", mt) for mt in GUARD_FLEX})
    return {
        "flex": row(prim, "FLEX", "capture@10"),
        "loso": [
            prim["loso"]["FLEX|capture@10"][k] for k in sorted(prim["loso"]["FLEX|capture@10"])
        ],
        "null": row(prim, "FLEX", "capture@10", ARM_B, ARM_N),
        "half": row(prim_half, "FLEX", "capture@10"),
        "wr": row(prim, "WR", "capture@10"),
        "wr_vs_prod": row(prim, "WR", "capture@10", ARM_B, "CF_A"),
        "guard": guard,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w13_results.json")
    ap.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS))
    args = ap.parse_args()
    seasons = tuple(int(s) for s in args.seasons.split(","))
    _gate(2025 not in seasons, "2025 has no Class A injury timestamps -- pre-registration §3")
    con = duckdb.connect(args.db, read_only=True)
    sources = w11m.wire(con, seasons)

    print(f"[1/6] panel, forecasts, durable table (seasons {seasons}) ...")
    panel = op.build_panel(con, POSITIONS)
    snapshots = audit.week_coverage(con, seasons).snapshots
    _gate(bool(snapshots), f"no evaluable weeks for seasons {seasons} -- see pre-registration §9")
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", seasons) for p in POSITIONS}
    fc_half = {p: op.walk_forward(panel, p, "T_XFP_HALF", "M_NEW", seasons) for p in POSITIONS}
    fc_opp = {p: op.walk_forward(panel, p, "T_OPP", "M_NEW", seasons) for p in POSITIONS}
    dur = w9.durable_table(con, through=max(seasons))
    _gate(
        set(seasons) <= {int(s) for s in dur.season.unique()},
        f"durable table lacks a season in {seasons}",
    )
    print("[2/6] the own-injury features (W12's pipeline, primary cutoff) ...")
    fridays = w12.cutoff_fridays(con, snapshots)
    rows, inj_prov = w12.injury_rows(con)
    inj = w12.injury_table(con, panel, fridays, rows, strict=False)
    print("[3/6] the declared trainings (A = W10, B, N, S) ...")
    trained = trainings(con, panel, dur, inj, seasons)
    print("[4/6] Full PPR (with the mechanism) and Half-PPR ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, trained, inj, mechanism=True)
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, trained, inj, mechanism=False)
    print("[5/6] summaries and the decision ...")
    prim = summaries(full, seasons)
    prim_half = summaries(half, seasons)
    vin = verdict_inputs(prim, prim_half)
    out: dict = {
        "full_ppr": {
            "summary": prim,
            "mechanism": mechanism_summary(full["ex"]),
            "cells": full["m"],
        },
        "half_ppr": {"summary": prim_half, "cells": half["m"]},
        "verdict_inputs": vin,
        "verdict": injf.verdict(vin),
        "window_rule": {
            "note": "pre-registration §9: the single-season (2026) confirmation rule",
            "flex_capture10_B_minus_A_ci_above_zero": bool(vin["flex"])
            and vin["flex"]["ci_low"] > 0.0,
        },
    }
    cov = inj[inj.season.isin(seasons)]
    out["provenance"] = {
        "seasons": list(seasons),
        "features": OWN,
        "injury_source": inj_prov,
        "feature_coverage": {f: float(cov[f].notna().mean()) for f in OWN},
        "status_mix": {
            g: int(n)
            for g, n in sorted(
                cov["own_status"].map(injf.status_group).value_counts().to_dict().items()
            )
        },
        "arms": {k: v.by_position for k, v in trained.items()},
        "sources": sources,
    }
    print("[6/6] writing ...")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
