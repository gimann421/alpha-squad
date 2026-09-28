"""W11 stage 2 --- does letting current role override stale history improve W10's model?

Runs exactly `docs/weekly/W11_PREREGISTRATION.md` §5-§8. **Research only.** Runs only if stage 1
(`w11_mechanism.py`) established the mechanism at RB or WR; otherwise it records the verdict
MECHANISM NOT ESTABLISHED and trains nothing.

  A  CURRENT ALPHA              production's stored predictions
  B  HISTORICAL ALPHA           W10's model, exactly (the baseline to beat)
  C  HISTORY + ROLE-AWARE       B + the three PRIMARY role features
  N  ROLE NULL                  B + the role features permuted within (season, week, position)

    uv run python scripts/research/w11_role_model.py --out reports/weekly/w11_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import benchmark, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import historical as hist  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import rolechange as rc  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w11_mechanism as w11m  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    flex_cell,
    leave_one_season_out,
    per_season,
    summarise,
)
from scripts.research.w7_opportunity import universes  # noqa: E402

POSITIONS = w11m.POSITIONS
DEPTHS = topboard.W5_DEPTHS
K = 10
ARM_B = w11m.ARM_B
ARM_C = "ALPHA_PLUS_HISTORY_ROLE"
ARM_N = "ALPHA_PLUS_HISTORY_ROLE_NULL"
MODEL_ARMS = (ARM_B, ARM_C, ARM_N)
KEYS = ["player_id", "season", "week"]
GUARD_POSITIONAL = ("capture@5", "capture@10", "capture@20", "capture@50", "spearman", "pairwise")
GUARD_FLEX = ("capture@10", "capture@25", "spearman", "pairwise")
ROBUST_METRICS = ("capture@5", "capture@10", "capture@20", "spearman")
ZERO = w8.ZERO
_put = w8._put
_gate = w8._gate


def trainings(con, panel, dur, roles, seasons) -> dict:
    cols = [*mech.DURABLE_FEATURES, *rc.ROLE_FEATURES]
    dp = w9.durable_panel(panel, dur, shuffle=False)
    rp = w11m.role_panel(panel, roles, shuffle=False)
    rpn = w11m.role_panel(panel, roles, shuffle=True)
    frame_c = dp.merge(rp, on=KEYS, how="left", validate="one_to_one")
    frame_n = dp.merge(rpn, on=KEYS, how="left", validate="one_to_one")
    return {
        ARM_B: w11m.train_b(con, panel, dur, seasons),
        ARM_C: arms_mod.train_with_extra_features(con, frame_c, cols, arm=ARM_C, seasons=seasons),
        ARM_N: arms_mod.train_with_extra_features(con, frame_n, cols, arm=ARM_N, seasons=seasons),
    }


def analyse(con, snapshots, fmt, panel, fc, fc_opp, trained, roles) -> dict:
    ppr = fmt.points_per_reception
    points = ppr == FULL_PPR.points_per_reception
    rl = {(r["player_id"], int(r["season"]), int(r["week"])): r for r in roles.to_dict("records")}
    cells = w8.collect(con, universes(con, snapshots, fmt), panel, fc, fc_opp, ppr)
    m: dict = {}
    ex: dict = {}
    week_of: dict[str, int] = {}
    for (key, pos), cell in sorted(cells.items()):
        snap, rows, common = cell["snap"], cell["rows"], cell["common"]
        week_of[key] = snap.week
        ids = sorted(rows)
        pts = {p: rows[p].pts for p in ids}
        boards = {"CF_A": cell["board_a"], "ECR": common}
        preds = {"CF_A": cell["alpha_pred"]}
        for arm in MODEL_ARMS:
            preds[arm] = trained[arm].for_week(snap.season, snap.week, pos)
            boards[arm] = alpha_mod.alpha_board(common, preds[arm], tiebreak=cell["rank_a"])[0]
        orders = {}
        for name, board in boards.items():
            _gate({r.player_id for r in board.rows} == set(ids), f"{key} {pos} {name} universe")
            orders[name] = w8._order(board)
            pr, rlz = board.ranks_and_points()
            row = evaluate_cell(pr, rlz, depths=DEPTHS).as_row()
            row.update(hist.miss_counts(orders[name], pts))
            m.setdefault(f"{pos}|{name}", {})[key] = row
        for name in (ARM_B, ARM_C) if points else ():
            err = [preds[name][p] - pts[p] for p in ids]
            m[f"{pos}|{name}"][key].update(
                mae=math.fsum(abs(e) for e in err) / len(err),
                bias=math.fsum(err) / len(err),
            )
        dec = adv.decompose_gap(orders[ARM_C], orders[ARM_B], rows, K)
        if dec:
            for piece in ("G", "G_F", "G_S", "G_C"):
                _put(ex, f"{pos}|C_vs_B", key, piece, dec[piece])
        cls = {}
        for p in ids:
            r = rl.get((p, snap.season, snap.week))
            _gate(r is not None, f"{key} {pos} {p}: no role row")
            cls[p] = r["cls_PRIMARY"]
        for tag, arm in (("ATTR_CB", ARM_C), ("ATTR_NB", ARM_N), ("ATTR_BA", None)):
            a, b = (orders[arm], orders[ARM_B]) if arm else (orders[ARM_B], orders["CF_A"])
            attr = mech.attribute_piece(a, b, rows, K, cls, "G")
            d = adv.decompose_gap(a, b, rows, K)
            if attr is not None:
                _gate(abs(sum(attr.values()) - d["G"]) < 1e-9, f"{key} {pos} {tag}: attribution")
                for c in rc.CLASSES:
                    _put(ex, f"{pos}|{tag}", key, c, attr.get(c, 0.0))
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
        for arm in MODEL_ARMS:
            pa = {}
            for pos in POSITIONS:
                pa.update(trained[arm].for_week(snap.season, snap.week, pos))
            fb[arm] = flex_cell(con, snap, fmt, pa, universe=uni)[1]
        for name, board in fb.items():
            _gate({r.player_id for r in board.rows} == uni, f"FLEX {key} {name} universe")
            pr, rlz = board.ranks_and_points()
            m.setdefault(f"FLEX|{name}", {})[key] = evaluate_cell(pr, rlz, depths=DEPTHS).as_row()
    return {"m": m, "ex": ex, "week_of": week_of}


def _subset(store: dict, keep) -> dict:
    return {s: {k: r for k, r in w.items() if keep(k)} for s, w in store.items()}


def summaries(res: dict) -> dict:
    m, ex, week_of = res["m"], res["ex"], res["week_of"]
    pos_flex = (*POSITIONS, "FLEX")
    pairs = ((ARM_C, ARM_B), (ARM_B, "CF_A"), (ARM_C, "CF_A"), (ARM_N, ARM_B), (ARM_C, ARM_N))
    comps = [(f"{p}|{a}", f"{p}|{b}") for p in pos_flex for a, b in pairs]
    comps += [(f"{p}|ECR", f"{p}|{b}") for p in pos_flex for b in ("CF_A", ARM_B, ARM_C)]
    out: dict = {"all": summarise(m, comps)}
    primary = [(f"{p}|{a}", f"{p}|{b}") for p in pos_flex for a, b in pairs]
    out["periods"] = {
        name: summarise(_subset(m, lambda k, n=name: mech.period_of(week_of[k]) == n), primary)[
            "paired"
        ]
        for name, _lo, _hi in mech.PERIODS
    }
    out["per_season"] = {
        f"{p}|{mt}": per_season(m, f"{p}|{ARM_C}", f"{p}|{ARM_B}", mt)
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["loso"] = {
        f"{p}|{mt}": leave_one_season_out(m, f"{p}|{ARM_C}", f"{p}|{ARM_B}", mt)
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["null_per_season"] = per_season(m, f"RB|{ARM_C}", f"RB|{ARM_N}", "capture@10")
    zero: dict = {}
    for w in ex.values():
        for k, r in w.items():
            zero.setdefault(k, {}).update({mt: 0.0 for mt in r})
    ex[ZERO] = zero
    out["attribution"] = {
        f"{p}|{tag}": w8.compare(ex, f"{p}|{tag}", ZERO, list(rc.CLASSES))
        for p in POSITIONS
        for tag in ("ATTR_CB", "ATTR_NB", "ATTR_BA")
    }
    out["attribution_periods"] = {
        name: {
            p: w8.compare(
                _subset(ex, lambda k, n=name: mech.period_of(week_of[k]) == n),
                f"{p}|ATTR_CB",
                ZERO,
                list(rc.CLASSES),
            )
            for p in POSITIONS
        }
        for name, _lo, _hi in mech.PERIODS
    }
    out["decomposition"] = {
        p: w8.compare(ex, f"{p}|C_vs_B", ZERO, ["G", "G_F", "G_S", "G_C"]) for p in POSITIONS
    }
    out["misses_points"] = {
        p: w8.compare(
            m, f"{p}|{ARM_C}", f"{p}|{ARM_B}", ["false_positive", "false_negative", "mae", "bias"]
        )
        for p in POSITIONS
    }
    out["misses_levels"] = {
        p: {
            b: {
                mt: statistics.fmean(r[mt] for r in m[f"{p}|{b}"].values())
                for mt in ("false_positive", "false_negative")
            }
            for b in ("CF_A", ARM_B, ARM_C, "ECR")
        }
        for p in POSITIONS
    }
    return out


def verdict_inputs(summ: dict, established: bool) -> dict:
    paired = summ["all"]["paired"]

    def row(p, mt, a=ARM_C, b=ARM_B):
        return paired.get(f"{p}|{a}_vs_{p}|{b}", {}).get(mt)

    guard = {f"{p}|{mt}": row(p, mt) for p in POSITIONS for mt in GUARD_POSITIONAL}
    guard.update({f"FLEX|{mt}": row("FLEX", mt) for mt in GUARD_FLEX})
    return {
        "mechanism_established": established,
        "rb": row("RB", "capture@10"),
        "rb_role_up": summ["attribution"]["RB|ATTR_CB"].get("ROLE_UP"),
        "rb_null": row("RB", "capture@10", ARM_C, ARM_N),
        "rb_seasons": [r["mean_diff"] for r in summ["per_season"]["RB|capture@10"].values()],
        "rb_loso": list(summ["loso"]["RB|capture@10"].values()),
        "wr": row("WR", "capture@10"),
        "wr_vs_a": row("WR", "capture@10", ARM_C, "CF_A"),
        "guard": guard,
        "any_gain": {f"{p}|capture@10": row(p, "capture@10") for p in POSITIONS},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w11_results.json")
    ap.add_argument("--mechanism", default="reports/weekly/w11_mechanism.json")
    ap.add_argument("--seasons", default=",".join(str(s) for s in w11m.DEFAULT_SEASONS))
    args = ap.parse_args()
    seasons = tuple(int(s) for s in args.seasons.split(","))
    stage1 = json.loads(Path(args.mechanism).read_text())
    _gate(
        stage1["provenance"]["seasons"] == list(seasons),
        "stage 1 was run on different seasons",
    )
    established = bool(stage1["run_stage_2"])
    if not established:
        out = {"verdict": "MECHANISM NOT ESTABLISHED", "stage_1": stage1["full_ppr"]["summary"]}
        Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
        print(f"mechanism not established at RB or WR -- no model trained; wrote {args.out}")
        return

    con = duckdb.connect(args.db, read_only=True)
    sources = w11m.wire(con, seasons)
    print(f"[1/5] panel, forecasts, durable and role tables (seasons {seasons}) ...")
    panel, snapshots, fc, fc_half, fc_opp, dur, roles = w11m.inputs(con, seasons)
    print("[2/5] the three declared trainings (B, C, role null) ...")
    trained = trainings(con, panel, dur, roles, seasons)
    print("[3/5] Full PPR ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, trained, roles)
    print("[4/5] Half-PPR ...")
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, trained, roles)
    out: dict = {}
    for tag, res in (("full_ppr", full), ("half_ppr", half)):
        summ = summaries(res)
        vin = verdict_inputs(summ, established)
        out[tag] = {
            "n_weeks": len(res["week_of"]),
            "summary": summ,
            "verdict_inputs": vin,
            "verdict": rc.model_verdict(vin),
            "cells": res["m"],
            "decomp_cells": {k: v for k, v in res["ex"].items() if k != ZERO},
        }
    out["provenance"] = {
        "seasons": list(seasons),
        "features": {"durable": list(mech.DURABLE_FEATURES), "role": list(rc.ROLE_FEATURES)},
        "arms": {k: v.by_position for k, v in trained.items()},
        "sources": sources,
    }
    print("[5/5] writing ...")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
