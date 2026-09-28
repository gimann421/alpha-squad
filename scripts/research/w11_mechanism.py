"""W11 stage 1 --- does a pre-Friday role-change signal explain where W10's historical memory
helps and where it hurts? Runs exactly `docs/weekly/W11_PREREGISTRATION.md` §4-§6. **Research only.**

No model is changed here. Arm B is W10's `ALPHA_PLUS_HISTORICAL`, retrained identically (G3 proves
it). Every player-week in the evaluated universe is classified by comparing this season's role
(games before the week) with last season's, and B - A capture@10 is split exactly by class.

    uv run python scripts/research/w11_mechanism.py --out reports/weekly/w11_mechanism.json

Stage 2 (`w11_role_model.py`) reads this file and runs only if the pre-registered mechanism is
established at RB or WR.
"""

from __future__ import annotations

import argparse
import bisect
import json
import random
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, context, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import historical as hist  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly import rolechange as rc  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from alpha_squad.identity.canonical import reader_expr  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research.w7_opportunity import universes  # noqa: E402

DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ("RB", "WR", "TE")
PRIMARY = ("RB", "WR")
K = 10
ARM_B = "ALPHA_PLUS_HISTORICAL"  # W10's arm, exactly
POS_INDEX = {"RB": 1, "WR": 2, "TE": 3}
ZERO = w8.ZERO
_put = w8._put
_gate = w8._gate
_num = w9._num


# ---------------------------------------------------------------------------------------
# The current-vs-history role table (Class A: this season's games before the week)
# ---------------------------------------------------------------------------------------


def role_table(con, dur: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """(player_id, season, week) -> the PRIMARY role features and every threshold set's class.

    Current role reads only `player_week_stats` rows of the same season with `week` < the
    predicted week. Last season's role is the W9/W10 durable row."""
    rows = con.execute(
        "SELECT player_id, season, week, targets, carries, offense_snap_pct, fantasy_points_ppr "
        "FROM player_week_stats ORDER BY player_id, season, week"
    ).fetchall()
    by: dict[tuple[str, int], list[dict]] = {}
    for pid, season, week, tgt, car, snap, ppr in rows:
        by.setdefault((pid, int(season)), []).append(
            {
                "week": int(week),
                "opp": float(tgt or 0) + float(car or 0),
                "snap": None if snap is None else float(snap),
                "ppr": None if ppr is None else float(ppr),
            }
        )
    for games in by.values():
        games.sort(key=lambda g: g["week"])
    weeks_of = {k: [g["week"] for g in v] for k, v in by.items()}
    prior = {
        (r["player_id"], int(r["season"])): {
            c: _num(r.get(c)) for c in ("has_prior", "prior_opp_pg", "prior_snap", "prior_ppg")
        }
        for r in dur.to_dict("records")
    }
    out = []
    for pid, season, week in sorted(
        zip(keys.player_id, keys.season.astype(int), keys.week.astype(int), strict=True)
    ):
        games = by.get((pid, season), [])
        cut = bisect.bisect_left(weeks_of.get((pid, season), []), week)
        current = games[:cut]
        p = prior.get((pid, season), {})
        rec: dict = {"player_id": pid, "season": season, "week": week}
        for name, (t_opp, t_snap) in rc.THRESHOLDS.items():
            s = rc.role_state(p, current, t_opp, t_snap)
            rec[f"cls_{name}"] = s["cls"]
            rec[f"tdir_{name}"] = s["transient_dir"]
            if name == "PRIMARY":
                rec.update({f: s[f] for f in rc.ROLE_FEATURES})
                rec["n_current"] = len(current)
        out.append(rec)
    frame = pd.DataFrame(out)
    for f in rc.ROLE_FEATURES:
        frame[f] = frame[f].astype(float)
    return frame


def role_panel(panel: pd.DataFrame, roles: pd.DataFrame, shuffle: bool) -> pd.DataFrame:
    """The three PRIMARY role features on every panel key. With `shuffle`, the features are
    permuted across players within (season, week, position) -- the W11 null arm."""
    keys = panel[["player_id", "season", "week", "position"]].copy()
    frame = keys.merge(
        roles[["player_id", "season", "week", *rc.ROLE_FEATURES]],
        on=["player_id", "season", "week"],
        how="left",
        validate="one_to_one",
    )
    if shuffle:
        parts = []
        for (season, week, pos), block in frame.groupby(["season", "week", "position"], sort=True):
            block = block.sort_values("player_id").reset_index(drop=True)
            perm = list(range(len(block)))
            seed = 3_000_000 + int(season) * 1_000 + int(week) * 10 + POS_INDEX.get(pos, 0)
            random.Random(seed).shuffle(perm)
            feats = block[list(rc.ROLE_FEATURES)].iloc[perm].reset_index(drop=True)
            parts.append(pd.concat([block[["player_id", "season", "week"]], feats], axis=1))
        frame = pd.concat(parts, ignore_index=True)
    return frame[["player_id", "season", "week", *rc.ROLE_FEATURES]]


def train_b(con, panel, dur, seasons):
    """W10's arm B, exactly as W10 trained it."""
    return arms_mod.train_with_extra_features(
        con,
        w9.durable_panel(panel, dur, shuffle=False),
        list(mech.DURABLE_FEATURES),
        arm=ARM_B,
        seasons=seasons,
    )


def wire(con, seasons) -> list:
    from alpha_squad.identity.canonical import require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    return context.wire_snapshot_views(con, tuple(range(2015, max(seasons) + 1)))


def inputs(con, seasons):
    """Panel, forecasts, the durable and role tables, and the evaluated weeks."""
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
    roles = role_table(con, dur, panel[["player_id", "season", "week"]])
    return panel, snapshots, fc, fc_half, fc_opp, dur, roles


# ---------------------------------------------------------------------------------------
# The mechanism measurements
# ---------------------------------------------------------------------------------------


def analyse(con, snapshots, fmt, panel, fc, fc_opp, b_arm, dur, roles) -> dict:
    ppr = fmt.points_per_reception
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    rl = {(r["player_id"], int(r["season"]), int(r["week"])): r for r in roles.to_dict("records")}
    dl = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    cells = w8.collect(con, universes(con, snapshots, fmt), panel, fc, fc_opp, ppr)
    store: dict = {}
    counts: dict = {}
    week_of: dict[str, int] = {}
    b_cells: dict = {}
    for (key, pos), cell in sorted(cells.items()):
        snap, rows, common = cell["snap"], cell["rows"], cell["common"]
        week_of[key] = snap.week
        ids = sorted(rows)
        pts = {p: rows[p].pts for p in ids}
        board_b = alpha_mod.alpha_board(
            common, b_arm.for_week(snap.season, snap.week, pos), tiebreak=cell["rank_a"]
        )[0]
        _gate({r.player_id for r in board_b.rows} == set(ids), f"{key} {pos} B universe")
        order_a, order_b = cell["order_a"], w8._order(board_b)
        pr, rlz = board_b.ranks_and_points()
        b_cells.setdefault(f"{pos}|{ARM_B}", {})[key] = evaluate_cell(
            pr, rlz, depths=topboard.W5_DEPTHS
        ).as_row()
        rank_a = {p: n for n, p in enumerate(order_a, start=1)}
        rank_b = {p: n for n, p in enumerate(order_b, start=1)}
        real = hist.realized_ranks(pts)
        state = {}
        for p in ids:
            r = rl.get((p, snap.season, snap.week))
            _gate(r is not None, f"{key} {pos} {p}: no role row")
            state[p] = r
        dec = adv.decompose_gap(order_b, order_a, rows, K)
        for name in rc.THRESHOLDS:
            cls = {p: state[p][f"cls_{name}"] for p in ids}
            attr = mech.attribute_piece(order_b, order_a, rows, K, cls, "G")
            if attr is not None:
                _gate(abs(sum(attr.values()) - dec["G"]) < 1e-9, f"{key} {pos} {name}: attribution")
                for c in rc.CLASSES:
                    _put(store, f"{pos}|ATTR|{name}", key, c, attr.get(c, 0.0))
            # M3: substantial movers, grouped
            mv: dict[str, float] = {}
            for p in ids:
                c = cls[p]
                counts.setdefault(f"{pos}|{name}", {}).setdefault(c, 0)
                counts[f"{pos}|{name}"][c] += 1
                if not rc.is_mover(rank_a[p], rank_b[p]):
                    continue
                outcome = rc.move_outcome(rank_a[p], rank_b[p], real[p])
                if outcome is None:
                    continue
                for tag in (c, rc.group_of(c)):
                    if tag is None:
                        continue
                    mv[f"mov_{tag}"] = mv.get(f"mov_{tag}", 0.0) + 1.0
                    mv[f"wrong_{tag}"] = mv.get(f"wrong_{tag}", 0.0) + float(outcome == "WRONG")
            for m, v in sorted(mv.items()):
                _put(store, f"{pos}|MOVE|{name}", key, m, v)
            # R: does a sustained change persist into this week more than a one-game one?
            rel: dict[str, float] = {}
            for p in ids:
                tag = rc.reliability_tag(cls[p], state[p][f"tdir_{name}"])
                if tag is None:
                    continue
                prior_opp = _num((dl.get((p, snap.season)) or {}).get("prior_opp_pg"))
                y = _num(panel.at[idx[(p, snap.season, snap.week)], "y_opp"])
                if prior_opp is None or y is None:
                    continue
                rel[f"{tag}_sum"] = rel.get(f"{tag}_sum", 0.0) + (y - prior_opp)
                rel[f"{tag}_n"] = rel.get(f"{tag}_n", 0.0) + 1.0
            for m, v in sorted(rel.items()):
                _put(store, f"{pos}|REL|{name}", key, m, v)
        # Diagnostics on PRIMARY: B's rank error against A's, and W5's misses, by class
        cls = {p: state[p]["cls_PRIMARY"] for p in ids}
        diag: dict[str, float] = {}
        for p in ids:
            if min(rank_a[p], rank_b[p], real[p]) > rc.REGION:
                continue
            c = cls[p]
            diag[f"n_{c}"] = diag.get(f"n_{c}", 0.0) + 1.0
            diag[f"abs_{c}"] = diag.get(f"abs_{c}", 0.0) + (
                abs(rank_b[p] - real[p]) - abs(rank_a[p] - real[p])
            )
            diag[f"move_{c}"] = diag.get(f"move_{c}", 0.0) + (rank_b[p] - rank_a[p])
            for board, rk in (("A", rank_a), ("B", rank_b)):
                fp = rk[p] <= hist.FP_PRED_DEPTH and real[p] > hist.FP_REAL_DEPTH
                fn = real[p] <= hist.FN_REAL_DEPTH and rk[p] > hist.FN_PRED_DEPTH
                diag[f"fp{board}_{c}"] = diag.get(f"fp{board}_{c}", 0.0) + float(fp)
                diag[f"fn{board}_{c}"] = diag.get(f"fn{board}_{c}", 0.0) + float(fn)
        for m, v in sorted(diag.items()):
            _put(store, f"{pos}|DIAG", key, m, v)
    return {"store": store, "counts": counts, "week_of": week_of, "b_cells": b_cells}


def _subset(store: dict, keep) -> dict:
    return {s: {k: r for k, r in w.items() if keep(k)} for s, w in store.items()}


def _series(store: dict, system: str, metric: str) -> dict[str, float]:
    return {k: r.get(metric, 0.0) for k, r in store.get(system, {}).items()}


def summarise(res: dict) -> dict:
    store, week_of = res["store"], res["week_of"]
    zero: dict = {}
    for w in store.values():
        for k, r in w.items():
            zero.setdefault(k, {}).update({m: 0.0 for m in r})
    store[ZERO] = zero
    out: dict = {"counts": res["counts"]}
    windows = {"FULL": lambda k: True} | {
        name: (lambda k, n=name: mech.period_of(week_of[k]) == n) for name, _lo, _hi in mech.PERIODS
    }
    for pos in POSITIONS:
        p_out: dict = {}
        for name in rc.THRESHOLDS:
            t_out: dict = {}
            for wname, keep in windows.items():
                if name != "PRIMARY" and wname != "FULL":
                    continue
                st = _subset(store, keep)
                attr = w8.compare(st, f"{pos}|ATTR|{name}", ZERO, list(rc.CLASSES))
                mv = st.get(f"{pos}|MOVE|{name}", {})
                rel = st.get(f"{pos}|REL|{name}", {})

                def s(sysd, m):
                    return {k: r.get(m, 0.0) for k, r in sysd.items()}

                m3 = rc.ratio_diff_ci(
                    s(mv, "wrong_CHANGE"),
                    s(mv, "mov_CHANGE"),
                    s(mv, "wrong_STABLE"),
                    s(mv, "mov_STABLE"),
                )
                r_up = rc.ratio_diff_ci(
                    s(rel, "up_sum"), s(rel, "up_n"), s(rel, "tup_sum"), s(rel, "tup_n")
                )
                r_down = rc.ratio_diff_ci(
                    s(rel, "down_sum"), s(rel, "down_n"), s(rel, "tdown_sum"), s(rel, "tdown_n")
                )
                wrong_rates = {
                    c: w8.ratio_ci(s(mv, f"wrong_{c}"), s(mv, f"mov_{c}"))
                    for c in (*rc.CLASSES, "CHANGE", "STABLE")
                    if any(s(mv, f"mov_{c}").values())
                }
                t_out[wname] = {
                    "attribution": attr,
                    "M3": m3,
                    "R_up": r_up,
                    "R_down": r_down,
                    "wrong_rates": wrong_rates,
                    "mechanism": rc.mechanism(attr.get("QUIET"), attr.get("ROLE_UP"), m3, r_up),
                }
            if name == "PRIMARY":
                t_out["per_season"] = {
                    c: {
                        str(season): (
                            w8.compare(
                                _subset(store, lambda k, s_=season: k.startswith(f"{s_}-")),
                                f"{pos}|ATTR|{name}",
                                ZERO,
                                [c],
                            ).get(c, {})
                        ).get("mean_diff")
                        for season in DEFAULT_SEASONS
                    }
                    for c in ("QUIET", "ROLE_UP", "ROLE_DOWN", "TRANSIENT", "TOO_EARLY")
                }
            p_out[name] = t_out
        diag = store.get(f"{pos}|DIAG", {})
        p_out["diagnostics"] = {
            c: {
                "mean_abs_err_change": w8.ratio_ci(
                    _series(store, f"{pos}|DIAG", f"abs_{c}"),
                    _series(store, f"{pos}|DIAG", f"n_{c}"),
                ),
                "mean_move": w8.ratio_ci(
                    _series(store, f"{pos}|DIAG", f"move_{c}"),
                    _series(store, f"{pos}|DIAG", f"n_{c}"),
                ),
                "fp_A": sum(r.get(f"fpA_{c}", 0.0) for r in diag.values()),
                "fp_B": sum(r.get(f"fpB_{c}", 0.0) for r in diag.values()),
                "fn_A": sum(r.get(f"fnA_{c}", 0.0) for r in diag.values()),
                "fn_B": sum(r.get(f"fnB_{c}", 0.0) for r in diag.values()),
                "n_region": sum(r.get(f"n_{c}", 0.0) for r in diag.values()),
            }
            for c in rc.CLASSES
            if any(r.get(f"n_{c}") for r in diag.values())
        }
        out[pos] = p_out
    out["established"] = {
        pos: out[pos]["PRIMARY"]["FULL"]["mechanism"]["established"] for pos in POSITIONS
    }
    out["run_stage_2"] = any(out["established"][p] for p in PRIMARY)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w11_mechanism.json")
    ap.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS))
    args = ap.parse_args()
    seasons = tuple(int(s) for s in args.seasons.split(","))
    con = duckdb.connect(args.db, read_only=True)
    sources = wire(con, seasons)

    print(f"[1/4] panel, forecasts, durable and role tables (seasons {seasons}) ...")
    panel, snapshots, fc, fc_half, fc_opp, dur, roles = inputs(con, seasons)
    print("[2/4] arm B (W10's model, retrained identically) ...")
    b_arm = train_b(con, panel, dur, seasons)
    print("[3/4] mechanism measurements, Full PPR and Half-PPR ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, b_arm, dur, roles)
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, b_arm, dur, roles)
    out = {
        "full_ppr": {
            "n_weeks": len(full["week_of"]),
            "summary": summarise(full),
            "b_cells": full["b_cells"],
        },
        "half_ppr": {
            "n_weeks": len(half["week_of"]),
            "summary": summarise(half),
            "b_cells": half["b_cells"],
        },
        "provenance": {
            "seasons": list(seasons),
            "thresholds": {k: list(v) for k, v in rc.THRESHOLDS.items()},
            "window": rc.WINDOW,
            "persistence": rc.PERSISTENCE,
            "classes": list(rc.CLASSES),
            "arm_b": b_arm.by_position,
            "sources": sources,
        },
    }
    out["run_stage_2"] = out["full_ppr"]["summary"]["run_stage_2"]
    print("[4/4] writing ...")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
