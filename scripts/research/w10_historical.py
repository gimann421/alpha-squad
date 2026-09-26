"""W10 --- does giving Alpha last season's role and production improve its weekly ranking?

Runs exactly what `docs/weekly/W10_PREREGISTRATION.md` specifies. **Research only.** Arm B is
W9's `ALPHA_PLUS_DURABLE`, frozen: production's CatBoost + the seven prior-season features, one
conceptual change. ECR is the independent benchmark only -- never a feature.

  A  CURRENT ALPHA        production's stored predictions
  B  ALPHA + HISTORICAL   the test
  C  HISTORICAL-ONLY      rank by prior-season PPG (diagnostic)
  N  NULL                 B with the features permuted within season
  B-production / B-opportunity / B-role   attribution-only ablations

    uv run python scripts/research/w10_historical.py --out reports/weekly/w10_results.json
    uv run python scripts/research/w10_historical.py --seasons 2026 --out ...   # §9, once ingested
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context, nulls, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import historical as hist  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell, spearman  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from alpha_squad.identity.canonical import reader_expr  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    _null_metrics,
    cliff,
    flex_cell,
    leave_one_season_out,
    per_season,
    summarise,
)
from scripts.research.w7_opportunity import universes  # noqa: E402

DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ("RB", "WR", "TE")
PRIMARY = ("RB", "WR")
DEPTHS = topboard.W5_DEPTHS
K = 10
N_DECILES = 10
ARM_B = "ALPHA_PLUS_HISTORICAL"
ARM_N = "ALPHA_PLUS_HISTORICAL_NULL"
ABLATIONS = {f"B_minus_{name}": cols for name, cols in hist.CATEGORIES.items()}
MODEL_ARMS = (ARM_B, ARM_N, *ABLATIONS)
BOARDS = ("CF_A", "ECR", *MODEL_ARMS, "HIST_ONLY")
PRIMARY_METRICS = ("capture@5", "capture@10")
GUARD_POSITIONAL = ("capture@5", "capture@10", "capture@20", "capture@50", "spearman", "pairwise")
GUARD_FLEX = ("capture@10", "capture@25", "spearman", "pairwise")
ZERO = w8.ZERO
_put = w8._put
_gate = w8._gate
_num = w9._num


def trainings(con, panel, dur, seasons) -> dict:
    cols = list(mech.DURABLE_FEATURES)
    keys = ["player_id", "season", "week"]
    dp = w9.durable_panel(panel, dur, shuffle=False)
    out = {
        ARM_B: arms_mod.train_with_extra_features(con, dp, cols, arm=ARM_B, seasons=seasons),
        ARM_N: arms_mod.train_with_extra_features(
            con, w9.durable_panel(panel, dur, shuffle=True), cols, arm=ARM_N, seasons=seasons
        ),
    }
    for name, drop in ABLATIONS.items():
        keep = [c for c in cols if c not in drop]
        out[name] = arms_mod.train_with_extra_features(
            con, dp[keys + keep], keep, arm=name, seasons=seasons
        )
    return out


def _order_board(common, order: list[str]):
    """A Board over `common`'s universe in exactly `order`."""
    return alpha_mod.alpha_board(common, {p: -float(n) for n, p in enumerate(order)})[0]


def analyse(con, snapshots, fmt, panel, fc, fc_opp, trained, dur, with_nulls: bool) -> dict:
    ppr = fmt.points_per_reception
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    dl = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    cells = w8.collect(con, universes(con, snapshots, fmt), panel, fc, fc_opp, ppr)
    m: dict = {}  # system -> week -> metric row
    nm: dict = {}  # null cells for the cliff
    ex: dict = {}  # decomposition / quiet-star / movement / point diagnostics
    movers: list[dict] = []
    week_of: dict[str, int] = {}
    counts: dict = {}
    calib: dict = {}  # (pos|board) -> [(pred, pts, key, pid)] for calibration by decile
    points = ppr == FULL_PPR.points_per_reception  # predictions are PPR; Half-PPR has no target
    for (key, pos), cell in sorted(cells.items()):
        snap, rows, common = cell["snap"], cell["rows"], cell["common"]
        week_of[key] = snap.week
        ids = sorted(rows)
        tb = cell["rank_a"]
        pts = {p: rows[p].pts for p in ids}
        feat = {
            p: {
                k: _num(v)
                for k, v in (dl.get((p, snap.season)) or {}).items()
                if k in mech.DURABLE_FEATURES
            }
            for p in ids
        }
        boards = {"CF_A": cell["board_a"], "ECR": common}
        preds = {"CF_A": cell["alpha_pred"]}
        for arm in MODEL_ARMS:
            preds[arm] = trained[arm].for_week(snap.season, snap.week, pos)
            boards[arm] = alpha_mod.alpha_board(common, preds[arm], tiebreak=tb)[0]
        boards["HIST_ONLY"] = _order_board(
            common, hist.historical_only_order(ids, {p: feat[p].get("prior_ppg") for p in ids})
        )
        orders = {}
        for name, board in boards.items():
            _gate({r.player_id for r in board.rows} == set(ids), f"{key} {pos} {name} universe")
            orders[name] = w8._order(board)
            pr, rl = board.ranks_and_points()
            row = evaluate_cell(pr, rl, depths=DEPTHS).as_row()
            row.update(hist.miss_counts(orders[name], pts))
            m.setdefault(f"{pos}|{name}", {})[key] = row
        # point diagnostics (secondary; Full PPR only -- the models predict PPR points)
        for name in ("CF_A", ARM_B) if points else ():
            err = [preds[name][p] - pts[p] for p in ids]
            m[f"{pos}|{name}"][key].update(
                mae=math.fsum(abs(e) for e in err) / len(err),
                rmse=math.sqrt(math.fsum(e * e for e in err) / len(err)),
                bias=math.fsum(err) / len(err),
            )
            calib.setdefault(f"{pos}|{name}", []).extend(
                (preds[name][p], pts[p], key, p) for p in ids
            )
        # the W8 decomposition of B - A, ECR - A, ECR - B
        for tag, (a, b) in {
            "B_vs_A": (ARM_B, "CF_A"),
            "ECR_vs_A": ("ECR", "CF_A"),
            "ECR_vs_B": ("ECR", ARM_B),
        }.items():
            dec = adv.decompose_gap(orders[a], orders[b], rows, K)
            if dec:
                for piece in ("G", "G_F", "G_S", "G_C"):
                    _put(ex, f"{pos}|{tag}", key, piece, dec[piece])
        # quiet established players and movement categories
        real = hist.realized_ranks(pts)
        cat = {}
        for p in ids:
            i = idx[(p, snap.season, snap.week)]
            last = _num(panel.at[i, "T_XFP__BL_LAST"])
            recent = (_num(panel.at[i, "targets_avg_last3"]) or 0.0) + (
                _num(panel.at[i, "carries_avg_last3"]) or 0.0
            )
            f = feat[p]
            cat[p] = hist.movement_category(
                f.get("prior_rank"),
                last,
                f.get("prior_ppg"),
                _num(panel.at[i, "games_played_prior"]),
                f.get("prior_opp_pg"),
                recent,
            )
        qs_hits = [p for p in ids if cat[p] == "QUIET_STAR" and real[p] <= K]
        if qs_hits:
            _put(ex, f"{pos}|QS", key, "den", float(len(qs_hits)))
            for name in ("CF_A", ARM_B, "ECR"):
                top = set(orders[name][:K])
                _put(
                    ex, f"{pos}|QS", key, f"num_{name}", float(sum(1 for p in qs_hits if p in top))
                )
            _put(
                ex,
                f"{pos}|QS",
                key,
                "num_B_minus_A",
                ex[f"{pos}|QS"][key][f"num_{ARM_B}"] - ex[f"{pos}|QS"][key]["num_CF_A"],
            )
        attr = mech.attribute_piece(orders[ARM_B], orders["CF_A"], rows, K, cat, "G")
        dec = adv.decompose_gap(orders[ARM_B], orders["CF_A"], rows, K)
        if attr is not None:
            _gate(abs(sum(attr.values()) - dec["G"]) < 1e-9, f"{key} {pos}: movement attribution")
            for c in hist.MOVEMENT_CATEGORIES:
                _put(ex, f"{pos}|MOVE", key, c, attr.get(c, 0.0))
        tb_set, ta_set = set(orders[ARM_B][:K]), set(orders["CF_A"][:K])
        for p in sorted(tb_set ^ ta_set):
            direction = "IN" if p in tb_set else "OUT"
            c = counts.setdefault(f"{pos}|{direction}", {})
            c[cat[p]] = c.get(cat[p], 0) + 1
            movers.append(
                {
                    "position": pos,
                    "week": key,
                    "player_id": p,
                    "direction": direction,
                    "category": cat[p],
                    "hit": int(real[p] <= K),
                    "pts": pts[p],
                }
            )
        if with_nulls:
            for name in ("CF_A", ARM_B):
                pr, rl = boards[name].ranks_and_points()
                rho = spearman(pr, rl)
                if rho is not None and rho > 0:
                    latent = nulls.calibrate_latent(rl, rho, snap.season, snap.week, pos)
                    draws = [
                        _null_metrics(
                            nulls.draw_null_ranking(
                                rl, rho, snap.season, snap.week, pos, d, latent=latent
                            ).pred_rank,
                            rl,
                        )
                        for d in range(nulls.N_SIM)
                    ]
                    nm.setdefault(f"{pos}|{name}", {})[key] = {
                        k: statistics.fmean([d[k] for d in draws if d[k] is not None])
                        for k in draws[0]
                        if any(d[k] is not None for d in draws)
                    }
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
            pr, rl = board.ranks_and_points()
            m.setdefault(f"FLEX|{name}", {})[key] = evaluate_cell(pr, rl, depths=DEPTHS).as_row()
    return {
        "cells": cells,
        "m": m,
        "nm": nm,
        "ex": ex,
        "movers": movers,
        "week_of": week_of,
        "counts": counts,
        "calib": calib,
    }


def calibration(calib: dict) -> dict:
    """Mean predicted vs mean realized points by predicted decile, pooled over player-weeks."""
    out: dict = {}
    for name, recs in sorted(calib.items()):
        recs = sorted(recs, key=lambda t: (t[0], t[2], t[3]))
        bins = np.array_split(np.arange(len(recs)), N_DECILES)
        out[name] = [
            {
                "decile": d + 1,
                "n": len(b),
                "mean_pred": math.fsum(recs[i][0] for i in b) / len(b),
                "mean_realized": math.fsum(recs[i][1] for i in b) / len(b),
            }
            for d, b in enumerate(bins)
            if len(b)
        ]
    return out


def _subset(store: dict, keep) -> dict:
    return {s: {k: r for k, r in w.items() if keep(k)} for s, w in store.items()}


def summaries(res: dict, positions_flex: tuple[str, ...]) -> dict:
    m, week_of = res["m"], res["week_of"]
    comps = []
    for pos in positions_flex:
        boards = [b for b in BOARDS if b != "CF_A" and f"{pos}|{b}" in m]
        comps += [(f"{pos}|{b}", f"{pos}|CF_A") for b in boards]
        comps.append((f"{pos}|ECR", f"{pos}|{ARM_B}"))
    out = {"all": summarise(m, comps)}
    primary = (
        [(f"{p}|{ARM_B}", f"{p}|CF_A") for p in positions_flex]
        + [(f"{p}|ECR", f"{p}|CF_A") for p in positions_flex]
        + [(f"{p}|{ARM_N}", f"{p}|CF_A") for p in positions_flex]
    )
    out["periods"] = {
        name: summarise(_subset(m, lambda k, n=name: mech.period_of(week_of[k]) == n), primary)[
            "paired"
        ]
        for name, _lo, _hi in mech.PERIODS
    }
    out["per_season"] = {
        f"{p}|{mt}": per_season(m, f"{p}|{ARM_B}", f"{p}|CF_A", mt)
        for p in positions_flex
        for mt in ("capture@5", "capture@10", "capture@20", "spearman")
    }
    out["loso"] = {
        f"{p}|{mt}": leave_one_season_out(m, f"{p}|{ARM_B}", f"{p}|CF_A", mt)
        for p in positions_flex
        for mt in ("capture@5", "capture@10", "capture@20", "spearman")
    }
    out["misses_points"] = {
        p: w8.compare(
            m,
            f"{p}|{ARM_B}",
            f"{p}|CF_A",
            ["false_positive", "false_negative", "mae", "rmse", "bias"],
        )
        for p in POSITIONS
    }
    out["misses_levels"] = {
        p: {
            b: {
                mt: statistics.fmean(r[mt] for r in m[f"{p}|{b}"].values() if mt in r)
                for mt in ("false_positive", "false_negative")
            }
            for b in ("CF_A", ARM_B, "ECR")
        }
        for p in POSITIONS
    }
    ex = res["ex"]
    zero: dict = {}
    for w in ex.values():
        for k, r in w.items():
            zero.setdefault(k, {}).update({mt: 0.0 for mt in r})
    ex[ZERO] = zero
    out["decomposition"] = {
        f"{p}|{t}": w8.compare(ex, f"{p}|{t}", ZERO, ["G", "G_F", "G_S", "G_C"])
        for p in POSITIONS
        for t in ("B_vs_A", "ECR_vs_A", "ECR_vs_B")
    }
    out["movement"] = {
        p: w8.compare(ex, f"{p}|MOVE", ZERO, list(hist.MOVEMENT_CATEGORIES)) for p in POSITIONS
    }
    out["movement_counts"] = res["counts"]
    out["quiet_star"] = {}
    for p in POSITIONS:
        s = ex.get(f"{p}|QS", {})
        den = {k: r["den"] for k, r in s.items()}
        out["quiet_star"][p] = {
            "recall_A": w8.ratio_ci({k: r["num_CF_A"] for k, r in s.items()}, den),
            "recall_B": w8.ratio_ci({k: r[f"num_{ARM_B}"] for k, r in s.items()}, den),
            "recall_ECR": w8.ratio_ci({k: r["num_ECR"] for k, r in s.items()}, den),
            "B_minus_A": w8.ratio_ci({k: r["num_B_minus_A"] for k, r in s.items()}, den),
            "n_hits": int(sum(den.values())),
        }
    return out


def cliffs(res: dict) -> dict:
    return {
        f"{p}|{b}": cliff(res["m"], res["nm"], f"{p}|{b}")
        for p in POSITIONS
        for b in ("CF_A", ARM_B)
        if f"{p}|{b}" in res["nm"]
    }


def verdict_inputs(summ: dict, pos_list) -> dict:
    paired = summ["all"]["paired"]

    def row(p, mt, a=ARM_B, b="CF_A"):
        return paired.get(f"{p}|{a}_vs_{p}|{b}", {}).get(mt)

    def cell(p, mt):
        return {
            "full": row(p, mt),
            "seasons": [r["mean_diff"] for r in summ["per_season"][f"{p}|{mt}"].values()],
            "loso": list(summ["loso"][f"{p}|{mt}"].values()),
            "early": summ["periods"]["EARLY"].get(f"{p}|{ARM_B}_vs_{p}|CF_A", {}).get(mt),
            "late": summ["periods"]["LATE"].get(f"{p}|{ARM_B}_vs_{p}|CF_A", {}).get(mt),
            "ecr_minus_a": (row(p, mt, "ECR") or {}).get("mean_diff"),
        }

    success = {f"{p}|{mt}": cell(p, mt) for p in PRIMARY for mt in PRIMARY_METRICS}
    all_cells = {f"{p}|{mt}": cell(p, mt) for p in pos_list for mt in PRIMARY_METRICS}
    guard = {f"{p}|{mt}": row(p, mt) for p in pos_list for mt in GUARD_POSITIONAL}
    guard.update({f"FLEX|{mt}": row("FLEX", mt) for mt in GUARD_FLEX})
    return {"success": success, "all": all_cells, "guard": guard}


def redundancy(res: dict, panel, dur) -> dict:
    """How much of the historical information is already implied by Alpha's current features."""
    dl = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    out: dict = {}
    pairs = {
        "prior_ppg": ("fp_ppr_avg_season_to_date", "fp_ppr_avg_last3"),
        "prior_tsh": ("target_share_avg_last3",),
        "prior_snap": ("snap_pct_avg_last3",),
    }
    for pos in POSITIONS:
        for name, _lo, _hi in mech.PERIODS:
            xs, ys = [], {f: [] for f in mech.DURABLE_FEATURES if f != "has_prior"}
            for (key, p), cell in sorted(res["cells"].items()):
                if p != pos or mech.period_of(res["week_of"][key]) != name:
                    continue
                snap = cell["snap"]
                for pid in sorted(cell["rows"]):
                    f = dl.get((pid, snap.season))
                    if not f or _num(f.get("has_prior")) != 1.0:
                        continue
                    i = idx[(pid, snap.season, snap.week)]
                    xs.append([float(panel.at[i, c]) for c in op.S0])
                    for c in ys:
                        ys[c].append(_num(f.get(c)))
            row = {"n": len(xs)}
            x = np.column_stack([np.ones(len(xs)), np.asarray(xs, dtype=float)]) if xs else None
            for c, vals in ys.items():
                keep = [j for j, v in enumerate(vals) if v is not None]
                if x is None or len(keep) < 30:
                    continue
                y = np.asarray([vals[j] for j in keep], dtype=float)
                xx = x[keep]
                beta, *_ = np.linalg.lstsq(xx, y, rcond=None)
                resid = y - xx @ beta
                row[f"r2|{c}"] = float(1.0 - resid @ resid / ((y - y.mean()) @ (y - y.mean())))
            for c, currents in pairs.items():
                for cur in currents:
                    j = list(op.S0).index(cur)
                    keep = [t for t, v in enumerate(ys[c]) if v is not None]
                    a = np.asarray([ys[c][t] for t in keep], dtype=float)
                    b = np.asarray([xs[t][j] for t in keep], dtype=float)
                    if len(keep) > 30 and a.std() > 0 and b.std() > 0:
                        row[f"corr|{c}~{cur}"] = float(np.corrcoef(a, b)[0, 1])
            out[f"{pos}|{name}"] = row
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w10_results.json")
    ap.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS))
    args = ap.parse_args()
    seasons = tuple(int(s) for s in args.seasons.split(","))

    con = duckdb.connect(args.db, read_only=True)
    from alpha_squad.identity.canonical import require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    sources = context.wire_snapshot_views(con, tuple(range(2015, max(seasons) + 1)))

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

    print("[2/6] the declared trainings (B, null, three attribution ablations) ...")
    trained = trainings(con, panel, dur, seasons)

    print("[3/6] Full PPR (with the W5 cliff nulls) ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, trained, dur, with_nulls=True)
    print("[4/6] Half-PPR ...")
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, trained, dur, with_nulls=False)

    print("[5/6] summaries, verdict, redundancy ...")
    out: dict = {}
    for tag, res in (("full_ppr", full), ("half_ppr", half)):
        summ = summaries(res, (*POSITIONS, "FLEX"))
        vin = verdict_inputs(summ, POSITIONS)
        out[tag] = {
            "n_weeks": len(res["week_of"]),
            "summary": summ,
            "verdict_inputs": vin,
            "verdict": hist.verdict(vin["success"], vin["all"], vin["guard"]),
            "cells": res["m"],
            "decomp_cells": {k: v for k, v in res["ex"].items() if k != ZERO},
        }
    out["full_ppr"]["cliff"] = cliffs(full)
    out["full_ppr"]["calibration"] = calibration(full["calib"])
    out["full_ppr"]["redundancy"] = redundancy(full, panel, dur)
    mv = full["movers"]
    rescued: dict = {}
    for r in mv:
        k = (r["position"], r["player_id"])
        e = rescued.setdefault(
            k, {"in_hit": 0, "in_miss": 0, "out_hit": 0, "out_miss": 0, "cats": {}}
        )
        e[f"{r['direction'].lower()}_{'hit' if r['hit'] else 'miss'}"] += 1
        e["cats"][r["category"]] = e["cats"].get(r["category"], 0) + 1
    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())
    for pos in POSITIONS:
        items = [(pid, e) for (p, pid), e in rescued.items() if p == pos]
        out["full_ppr"].setdefault("players", {})[pos] = {
            "most_rescued": [
                {"name": names.get(pid), "player_id": pid, **e}
                for pid, e in sorted(
                    items, key=lambda t: (-(t[1]["in_hit"] - t[1]["out_hit"]), t[0])
                )[:12]
            ],
            "most_wrongly_promoted": [
                {"name": names.get(pid), "player_id": pid, **e}
                for pid, e in sorted(
                    items, key=lambda t: (-(t[1]["in_miss"] - t[1]["out_miss"]), t[0])
                )[:12]
            ],
        }
    out["provenance"] = {
        "seasons": list(seasons),
        "features": list(mech.DURABLE_FEATURES),
        "categories": {k: list(v) for k, v in hist.CATEGORIES.items()},
        "arms": {k: v.by_position for k, v in trained.items()},
        "sources": sources,
        "n_sim": nulls.N_SIM,
    }

    print("[6/6] writing ...")
    for tag in ("full_ppr", "half_ppr"):
        v = out[tag]["verdict"]
        print(f"  {tag}: {v['verdict']}  success={v['success_cells']}  breaches={v['breaches']}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
