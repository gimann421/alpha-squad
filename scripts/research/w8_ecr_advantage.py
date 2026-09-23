"""W8 --- where does ECR's top-of-board advantage over Alpha come from?

Runs exactly what `docs/weekly/W8_PREREGISTRATION.md` specifies. **Research only: ECR is an
instrument here, never a feature -- nothing is trained, calibrated or selected with it.** The only
model fitted is the pre-registered Class D diagnostic `ALPHA_ORACLE_OPP` (production's weekly model
plus the week's own realized usage), which is a ceiling, never a candidate.

  P1  the exact decomposition of ECR's capture gap into forecastable opportunity (G_F),
      unforecast opportunity (G_S) and conversion (G_C)
  P2  top-region pairwise accuracy, ECR minus Alpha, by pair type (CLOSE / SURPRISE / MATCHED)
  P3  what ECR's disagreements with Alpha anticipate (supporting)
  + bucket attributions, the counterfactual boards, the player-level profile, FLEX, LOSO,
    per-season, Half-PPR and the pre-registered sensitivity variants

    uv run python scripts/research/w8_ecr_advantage.py --out reports/weekly/w8_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import (  # noqa: E402
    audit,
    benchmark,
    context,
    diagnostics,
    noise,
    topboard,
)
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import (  # noqa: E402
    evaluate_cell,
    topk_points_capture,
)
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    flex_cell,
    leave_one_season_out,
    per_season,
    summarise,
)
from scripts.research.w7_opportunity import universes  # noqa: E402

SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ("RB", "WR", "TE")
PRIMARY_POSITIONS = ("RB", "WR")
DEPTHS = (5, 10, 20)
PRIMARY_DEPTH = adv.PRIMARY_DEPTH
FLEX_DEPTHS = (10, 25)
REGION_DEPTH = 20
FLEX_REGION_DEPTH = 25
REGION_SENSITIVITY = (10, 30)
MIN_REGION_WEEKS = 4
DECILE = 0.10
TOP_HIT_DEPTH = 10
N_PROFILE = 15
#: Sensitivity variants for P2's CLOSE / SURPRISE split (pre-registration §9.3-9.4).
VARIANTS = ("MED", "Q", "REL", "OPP")
PROFILE_COLUMNS = (
    "targets_avg_last3",
    "carries_avg_last3",
    "games_played_prior",
    "opp_sd_last3",
    "team_plays_avg_last3",
    "team_pass_rate_avg_last3",
    "team_epa_avg_last3",
)
ORACLE_ARM = "ALPHA_ORACLE_OPP"
ORACLE_FEATURE = "xfp_realized"
ZERO = "ZERO"


def _order(board: benchmark.Board) -> list[str]:
    """A board's player ids, best first, exactly as `ranks_and_points` orders them."""
    return [r.player_id for r in sorted(board.evaluable, key=lambda r: (r.ecr, r.player_id))]


def _gate(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"GATE FAILED: {message}")


# ---------------------------------------------------------------------------------------
# Pass 1 -- collect every cell's decomposed player-weeks
# ---------------------------------------------------------------------------------------


def collect(con, unis: dict, panel: pd.DataFrame, fc: dict, fc_opp: dict, ppr: float) -> dict:
    """(week key, position) -> orders, rows, region, and the targets+carries surprise."""
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    cells: dict = {}
    for (key, position), u in sorted(unis.items()):
        snap, common = u["snap"], u["common"]
        board_a = alpha_mod.alpha_board(common, u["alpha_pred"])[0]
        order_e, order_a = _order(common), _order(board_a)
        _gate(set(order_e) == set(order_a), f"{key} {position}: boards differ in universe")
        usage = context.load_usage_points(con, snap.season, snap.week, ppr)
        rows: dict[str, adv.PlayerWeek] = {}
        s_opp: dict[str, float] = {}
        for r in common.evaluable:
            i = idx.get((r.player_id, snap.season, snap.week))
            _gate(i is not None, f"{key} {position} {r.player_id}: no panel row")
            y_opp = panel.at[i, "y_opp"]
            if r.player_id in usage:
                x = usage[r.player_id]
            else:
                # G8: a missing usage row must be a zero-opportunity week (verified, never assumed)
                _gate(y_opp == 0, f"{key} {r.player_id}: no usage row but opportunity {y_opp}")
                x = 0.0
            rows[r.player_id] = adv.PlayerWeek(
                r.player_id, float(r.realized), float(x), float(fc[position].at[i])
            )
            s_opp[r.player_id] = float(y_opp) - float(fc_opp[position].at[i])
        rank_a = {p: float(n) for n, p in enumerate(order_a, start=1)}
        rank_e = {p: float(n) for n, p in enumerate(order_e, start=1)}
        cells[(key, position)] = {
            "snap": snap,
            "order_a": order_a,
            "order_e": order_e,
            "rank_a": rank_a,
            "rank_e": rank_e,
            "rows": rows,
            "s_opp": s_opp,
            "board_a": board_a,
            "common": common,
            "alpha_pred": u["alpha_pred"],
        }
    return cells


def region_of(cell: dict, depth: int) -> list[str]:
    """Top `depth` on either board -- selected by pre-game ranks only."""
    return sorted(
        p for p in cell["rows"] if cell["rank_a"][p] <= depth or cell["rank_e"][p] <= depth
    )


# ---------------------------------------------------------------------------------------
# Pass 2 -- thresholds, fixed from the pooled distributions of s, c and |x_i - x_j| alone
# ---------------------------------------------------------------------------------------


def compute_thresholds(cells: dict, positions: tuple[str, ...]) -> dict:
    """Per position, pooled over every top-region player-week of all weeks. No board comparison
    enters any of these -- they are functions of the realized decomposition only."""
    out: dict = {}
    for position in positions:
        abs_s, c_vals, rel, s_opp, pair_dx = [], [], [], [], []
        for (_key, pos), cell in sorted(cells.items()):
            if pos != position:
                continue
            region = region_of(cell, REGION_DEPTH)
            for p in region:
                r = cell["rows"][p]
                abs_s.append(abs(r.s))
                c_vals.append(r.c)
                rel.append(abs(r.s) / max(r.f, 1.0))
                s_opp.append(abs(cell["s_opp"][p]))
            for a in range(len(region)):
                for b in range(a + 1, len(region)):
                    pair_dx.append(abs(cell["rows"][region[a]].x - cell["rows"][region[b]].x))
        out[position] = {
            "n_region_player_weeks": len(abs_s),
            "n_region_pairs": len(pair_dx),
            "opp_terciles": adv.thresholds(abs_s, (1 / 3, 2 / 3)),
            "eff_terciles": adv.thresholds(c_vals, (1 / 3, 2 / 3)),
            "match_tercile": adv.thresholds(pair_dx, (1 / 3,))[0],
            "MED": adv.thresholds(abs_s, (0.5, 0.5)),
            "Q": adv.thresholds(abs_s, (0.2, 0.8)),
            "REL": adv.thresholds(rel, (1 / 3, 2 / 3)),
            "OPP": adv.thresholds(s_opp, (1 / 3, 2 / 3)),
        }
    return out


def _variant_value(variant: str, r: adv.PlayerWeek, s_opp: float) -> float:
    if variant == "REL":
        return abs(r.s) / max(r.f, 1.0)
    if variant == "OPP":
        return abs(s_opp)
    return abs(r.s)


def pair_typer(cell: dict, thr_of, match_cut: float):
    """`(i, j) -> pair types` for one cell. `thr_of(pid)` gives that player's position thresholds
    (so FLEX pairs use each player's own position)."""
    rows, s_opp = cell["rows"], cell["s_opp"]

    def types(i: str, j: str) -> list[str]:
        out = []
        ti, tj = thr_of(i), thr_of(j)
        ri, rj = rows[i], rows[j]
        lo_i, hi_i = ti["opp_terciles"]
        lo_j, hi_j = tj["opp_terciles"]
        if abs(ri.s) <= lo_i and abs(rj.s) <= lo_j:
            out.append("CLOSE")
        if abs(ri.s) > hi_i or abs(rj.s) > hi_j:
            out.append("SURPRISE")
        if abs(ri.x - rj.x) <= match_cut:
            out.append("MATCHED")
        for v in VARIANTS:
            vi, vj = _variant_value(v, ri, s_opp[i]), _variant_value(v, rj, s_opp[j])
            (li, hi_), (lj, hj) = ti[v], tj[v]
            if vi <= li and vj <= lj:
                out.append(f"{v}_CLOSE")
            if vi > hi_ or vj > hj:
                out.append(f"{v}_SURPRISE")
        return out

    return types


# ---------------------------------------------------------------------------------------
# Pass 3 -- per-week metrics
# ---------------------------------------------------------------------------------------


def _put(store: dict, system: str, key: str, metric: str, value) -> None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return
    store.setdefault(system, {}).setdefault(key, {})[metric] = float(value)


def positional_metrics(cells: dict, thr: dict, audit_log: dict) -> dict:
    """Every per-week quantity P1-P3 and the bucket tables need, as `system -> week -> metric`."""
    store: dict = {}
    swaps: dict = {}
    for (key, position), cell in sorted(cells.items()):
        t = thr[position]
        rows = cell["rows"]
        order_a, order_e = cell["order_a"], cell["order_e"]

        # --- P1: the exact decomposition, checked against the program's own capture metric
        for k in DEPTHS:
            dec = adv.decompose_gap(order_e, order_a, rows, k)
            if dec is None:
                continue
            for board, name in ((cell["common"], "capture_a"), (cell["board_a"], "capture_b")):
                pr, rl = board.ranks_and_points()
                ref = topk_points_capture(pr, rl, k)
                _gate(abs(ref - dec[name]) < 1e-12, f"{key} {position} k={k}: capture mismatch")
            resid = dec["G"] - (dec["G_F"] + dec["G_S"] + dec["G_C"])
            audit_log["max_identity_residual"] = max(audit_log["max_identity_residual"], abs(resid))
            _gate(abs(resid) < 1e-9, f"{key} {position} k={k}: G != G_F + G_S + G_C")
            for piece in ("G", "G_F", "G_S", "G_C"):
                _put(store, f"{position}|DECOMP", key, f"{piece}@{k}", dec[piece])

        region = region_of(cell, REGION_DEPTH)
        opp_b = {p: adv.opportunity_bucket(rows[p].s, t["opp_terciles"]) for p in region}
        sgn_b = {p: adv.signed_bucket(rows[p].s, t["opp_terciles"]) for p in region}
        eff_b = {p: adv.efficiency_bucket(rows[p].c, t["eff_terciles"]) for p in region}

        # --- bucket attribution of the capture gap (sums to G, gated)
        for k in (10, 20):
            dec = adv.decompose_gap(order_e, order_a, rows, k)
            if dec is None:
                continue
            for label, buckets, names in (
                ("opp", opp_b, adv.OPP_BUCKETS),
                ("signed", sgn_b, adv.SIGNED_BUCKETS),
                ("eff", eff_b, adv.EFF_BUCKETS),
            ):
                attr = adv.attribute_gap(order_e, order_a, rows, k, buckets)
                _gate(
                    abs(sum(attr.values()) - dec["G"]) < 1e-9,
                    f"{key} {position} k={k} {label}: attribution != G",
                )
                for b in names:
                    _put(store, f"{position}|ATTR", key, f"{label}@{k}|{b}", attr.get(b, 0.0))
                cnt = adv.swap_counts(order_e, order_a, k, buckets)
                sw = swaps.setdefault(f"{position}|{label}@{k}", {})
                for b in names:
                    sw[b] = sw.get(b, 0) + cnt.get(b, 0)

        # --- P2: pairwise accuracy by pair type, ECR (a) vs Alpha (b)
        pts = {p: rows[p].pts for p in rows}
        typer = pair_typer(cell, lambda _p, _t=t: _t, t["match_tercile"])
        acc = adv.pair_accuracy_by_type(region, cell["rank_e"], cell["rank_a"], pts, typer)
        for ptype, v in acc.items():
            _put(store, f"{position}|ECR", key, f"pair_{ptype}", v["acc_a"])
            _put(store, f"{position}|ALPHA", key, f"pair_{ptype}", v["acc_b"])
            _put(store, f"{position}|NPAIRS", key, f"pair_{ptype}", v["n"])
        for prefix in ("", *(f"{v}_" for v in VARIANTS)):
            c_, s_ = acc.get(f"{prefix}CLOSE"), acc.get(f"{prefix}SURPRISE")
            if c_ and s_ and c_["n"] and s_["n"]:
                dd = (s_["acc_a"] - s_["acc_b"]) - (c_["acc_a"] - c_["acc_b"])
                _put(store, f"{position}|OMEGA", key, f"{prefix}surp_minus_close", dd)
        for depth in REGION_SENSITIVITY:
            reg = region_of(cell, depth)
            a2 = adv.pair_accuracy_by_type(reg, cell["rank_e"], cell["rank_a"], pts, typer)
            for ptype in ("ALL", "CLOSE", "SURPRISE", "MATCHED"):
                if ptype in a2 and a2[ptype]["n"]:
                    _put(store, f"{position}|ECR", key, f"r{depth}_{ptype}", a2[ptype]["acc_a"])
                    _put(store, f"{position}|ALPHA", key, f"r{depth}_{ptype}", a2[ptype]["acc_b"])
            c_, s_ = a2.get("CLOSE"), a2.get("SURPRISE")
            if c_ and s_ and c_["n"] and s_["n"]:
                dd = (s_["acc_a"] - s_["acc_b"]) - (c_["acc_a"] - c_["acc_b"])
                _put(store, f"{position}|OMEGA", key, f"r{depth}_surp_minus_close", dd)

        # --- per-player-week concordance by bucket
        ce = adv.concordance(region, cell["rank_e"], pts)
        ca = adv.concordance(region, cell["rank_a"], pts)
        for label, buckets, names in (
            ("opp", opp_b, adv.OPP_BUCKETS),
            ("signed", sgn_b, adv.SIGNED_BUCKETS),
            ("eff", eff_b, adv.EFF_BUCKETS),
        ):
            for b in names:
                members = [p for p in region if buckets[p] == b and ce[p] is not None]
                if not members:
                    continue
                _put(
                    store,
                    f"{position}|ECR",
                    key,
                    f"conc_{label}|{b}",
                    statistics.fmean(ce[p] for p in members),
                )
                _put(
                    store,
                    f"{position}|ALPHA",
                    key,
                    f"conc_{label}|{b}",
                    statistics.fmean(ca[p] for p in members),
                )

        # --- P3: what the disagreements anticipate
        d = [cell["rank_a"][p] - cell["rank_e"][p] for p in region]
        for comp in ("s", "c", "f"):
            vals = [getattr(rows[p], comp) for p in region]
            _put(store, f"{position}|P3", key, f"rho_d_{comp}", adv.spearman_values(d, vals))
    return {"store": store, "swaps": swaps}


def flex_metrics(con, snaps_by_key: dict, cells: dict, thr: dict, fmt, ppr, panel, fc, audit_log):
    """FLEX: P1 at k = 10, 25 and P2 over the top-25-on-either region, each player carrying their
    own position's surprise. The FLEX boards are the existing ones -- no FLEX model is built."""
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    store: dict = {}
    flex_cells: dict = {}
    by_week: dict[str, dict] = {}
    for (key, _pos), cell in cells.items():
        by_week.setdefault(key, {})
        by_week[key].update(cell["alpha_pred"])
    for key in sorted(by_week):
        snap = snaps_by_key[key]
        commonf, boardf, _k = flex_cell(con, snap, fmt, by_week[key])
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        usage = context.load_usage_points(con, snap.season, snap.week, ppr)
        rows, pos_of, s_opp = {}, {}, {}
        for r in commonf.evaluable:
            i = idx.get((r.player_id, snap.season, snap.week))
            _gate(i is not None, f"FLEX {key} {r.player_id}: no panel row")
            y_opp = panel.at[i, "y_opp"]
            if r.player_id in usage:
                x = usage[r.player_id]
            else:
                _gate(y_opp == 0, f"FLEX {key} {r.player_id}: no usage row but opportunity")
                x = 0.0
            rows[r.player_id] = adv.PlayerWeek(
                r.player_id, float(r.realized), float(x), float(fc[r.position].at[i])
            )
            pos_of[r.player_id] = r.position
            s_opp[r.player_id] = 0.0
        order_e, order_a = _order(commonf), _order(boardf)
        flex_cells[key] = {
            "rows": rows,
            "pos_of": pos_of,
            "s_opp": s_opp,
            "order_e": order_e,
            "order_a": order_a,
            "rank_e": {p: float(n) for n, p in enumerate(order_e, start=1)},
            "rank_a": {p: float(n) for n, p in enumerate(order_a, start=1)},
            "common": commonf,
            "board_a": boardf,
        }
    # FLEX MATCHED cut: a cross-position pair has no single position, so the |x_i - x_j| tercile is
    # pooled over FLEX region pairs (a pre-results clarification, recorded in the amendments).
    dx = []
    for cell in flex_cells.values():
        region = region_of(cell, FLEX_REGION_DEPTH)
        for a in range(len(region)):
            for b in range(a + 1, len(region)):
                dx.append(abs(cell["rows"][region[a]].x - cell["rows"][region[b]].x))
    match_cut = adv.thresholds(dx, (1 / 3,))[0]
    for key, cell in sorted(flex_cells.items()):
        rows = cell["rows"]
        for k in FLEX_DEPTHS:
            dec = adv.decompose_gap(cell["order_e"], cell["order_a"], rows, k)
            if dec is None:
                continue
            for board, name in ((cell["common"], "capture_a"), (cell["board_a"], "capture_b")):
                pr, rl = board.ranks_and_points()
                _gate(
                    abs(topk_points_capture(pr, rl, k) - dec[name]) < 1e-12,
                    f"FLEX {key} k={k}: capture mismatch",
                )
            resid = dec["G"] - (dec["G_F"] + dec["G_S"] + dec["G_C"])
            audit_log["max_identity_residual"] = max(audit_log["max_identity_residual"], abs(resid))
            _gate(abs(resid) < 1e-9, f"FLEX {key} k={k}: identity")
            for piece in ("G", "G_F", "G_S", "G_C"):
                _put(store, "FLEX|DECOMP", key, f"{piece}@{k}", dec[piece])
        region = region_of(cell, FLEX_REGION_DEPTH)
        pts = {p: rows[p].pts for p in rows}
        typer = pair_typer(cell, lambda p, _c=cell: thr[_c["pos_of"][p]], match_cut)
        acc = adv.pair_accuracy_by_type(region, cell["rank_e"], cell["rank_a"], pts, typer)
        for ptype in ("ALL", "CLOSE", "SURPRISE", "MATCHED"):
            if ptype in acc and acc[ptype]["n"]:
                _put(store, "FLEX|ECR", key, f"pair_{ptype}", acc[ptype]["acc_a"])
                _put(store, "FLEX|ALPHA", key, f"pair_{ptype}", acc[ptype]["acc_b"])
        c_, s_ = acc.get("CLOSE"), acc.get("SURPRISE")
        if c_ and s_ and c_["n"] and s_["n"]:
            dd = (s_["acc_a"] - s_["acc_b"]) - (c_["acc_a"] - c_["acc_b"])
            _put(store, "FLEX|OMEGA", key, "surp_minus_close", dd)
    return {"store": store, "match_cut": match_cut, "n_weeks": len(flex_cells)}


# ---------------------------------------------------------------------------------------
# Counterfactual boards (§6): A, B = ALPHA_ORACLE_OPP, B0 = ORACLE_USAGE, C = ECR
# ---------------------------------------------------------------------------------------


def counterfactual_cells(con, cells: dict, oracle: arms_mod.ArmPredictions, ppr: float) -> dict:
    """A, B, B0, C on every positional cell. B0 is W5's `ORACLE_USAGE` exactly as W5/W7 built it
    (a player with no usage row keeps Alpha's score), so it can be checked against W7's cells."""
    out: dict = {}
    for (key, position), cell in sorted(cells.items()):
        snap, common = cell["snap"], cell["common"]
        usage = context.load_usage_points(con, snap.season, snap.week, ppr)
        preds_b = oracle.for_week(snap.season, snap.week, position)
        boards = {
            "CF_A": cell["board_a"],
            ORACLE_ARM: alpha_mod.alpha_board(common, preds_b, tiebreak=cell["rank_a"])[0],
            "ORACLE_USAGE": topboard.oracle_usage(common, cell["alpha_pred"], usage)[0],
            "ECR": common,
        }
        players = set(cell["rows"])
        for name, board in boards.items():
            _gate({r.player_id for r in board.rows} == players, f"{key} {position} {name} universe")
            pr, rl = board.ranks_and_points()
            out.setdefault(f"{position}|{name}", {})[key] = evaluate_cell(
                pr, rl, depths=topboard.W5_DEPTHS
            ).as_row()
    return out


# ---------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------


def zero_system(store: dict, system: str) -> dict:
    return {k: {m: 0.0 for m in r} for k, r in store.get(system, {}).items()}


def compare(store: dict, a: str, b: str, metrics: list[str]) -> dict:
    out: dict = {}
    for m in metrics:
        av = {k: r[m] for k, r in store.get(a, {}).items() if m in r}
        bv = {k: r[m] for k, r in store.get(b, {}).items() if m in r}
        pd_ = noise.paired_difference(m, a, b, av, bv)
        po = diagnostics.paired_outcome(m, a, b, av, bv)
        if pd_:
            row = pd_.as_row()
            if po:
                o = po.as_row()
                row.update(
                    a_wins=o["a_wins"],
                    b_wins=o["b_wins"],
                    ties=o["ties"],
                    wilcoxon_p=o["wilcoxon_p"],
                    median_diff=o["median_diff"],
                )
            out[m] = row
    return out


def ratio_ci(num: dict[str, float], den: dict[str, float]) -> dict | None:
    """Ratio of week-means, with a bootstrap over weeks (same seeds and resample count as
    `noise`). Descriptive: the verdict reads the point ratio."""
    weeks = sorted(set(num) & set(den))
    if len(weeks) < 3:
        return None
    n_, d_ = [num[w] for w in weeks], [den[w] for w in weeks]
    point = statistics.fmean(n_) / statistics.fmean(d_) if statistics.fmean(d_) else None
    lows, highs = [], []
    per_seed = max(1, noise.BOOTSTRAP_RESAMPLES // len(noise.BOOTSTRAP_SEEDS))
    n = len(weeks)
    for seed in noise.BOOTSTRAP_SEEDS:
        rng = random.Random(seed)
        vals = []
        for _ in range(per_seed):
            ix = [rng.randrange(n) for _ in range(n)]
            dsum = sum(d_[i] for i in ix)
            if dsum != 0:
                vals.append(sum(n_[i] for i in ix) / dsum)
        vals.sort()
        lows.append(adv.quantile(vals, 0.025))
        highs.append(adv.quantile(vals, 0.975))
    return {
        "ratio": point,
        "ci_low": statistics.fmean(lows),
        "ci_high": statistics.fmean(highs),
        "n_weeks": n,
    }


def _series(store: dict, system: str, metric: str) -> dict[str, float]:
    return {k: r[metric] for k, r in store.get(system, {}).items() if metric in r}


def diff_series(store: dict, pos: str, metric: str) -> dict[str, float]:
    e, a = _series(store, f"{pos}|ECR", metric), _series(store, f"{pos}|ALPHA", metric)
    return {k: e[k] - a[k] for k in sorted(set(e) & set(a))}


def position_summary(store: dict, pos: str, depths: tuple[int, ...], variants: bool) -> dict:
    """Everything the verdict and the report read for one position (or FLEX)."""
    dec_metrics = [f"{p}@{k}" for k in depths for p in ("G", "G_F", "G_S", "G_C")]
    s: dict = {"decomp": compare(store, f"{pos}|DECOMP", ZERO, dec_metrics)}
    s["shares"] = {
        f"{p}@{k}": ratio_ci(
            _series(store, f"{pos}|DECOMP", f"{p}@{k}"), _series(store, f"{pos}|DECOMP", f"G@{k}")
        )
        for k in depths
        for p in ("G_F", "G_S", "G_C")
    }
    pair_metrics = [f"pair_{t}" for t in adv.PAIR_TYPES]
    if variants:
        pair_metrics += [f"pair_{v}_{t}" for v in VARIANTS for t in ("CLOSE", "SURPRISE")]
        pair_metrics += [f"r{d}_{t}" for d in REGION_SENSITIVITY for t in adv.PAIR_TYPES]
    s["pairs"] = compare(store, f"{pos}|ECR", f"{pos}|ALPHA", pair_metrics)
    omega = ["surp_minus_close"]
    if variants:
        omega += [f"{v}_surp_minus_close" for v in VARIANTS]
        omega += [f"r{d}_surp_minus_close" for d in REGION_SENSITIVITY]
    s["omega"] = compare(store, f"{pos}|OMEGA", ZERO, omega)
    for t in ("CLOSE", "MATCHED", "SURPRISE"):
        s["shares"][f"omega_{t}"] = ratio_ci(
            diff_series(store, pos, f"pair_{t}"), diff_series(store, pos, "pair_ALL")
        )
    return s


# ---------------------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------------------


def robustness(store: dict, pos: str) -> dict:
    """LOSO and per-season on the P1 pieces (c@10) and the P2 quantities, plus the verdict
    recomputed inside each LOSO fold."""
    z = {pos + "|DECOMP": store.get(f"{pos}|DECOMP", {}), ZERO: zero_system(store, f"{pos}|DECOMP")}
    zo = {pos + "|OMEGA": store.get(f"{pos}|OMEGA", {}), ZERO: zero_system(store, f"{pos}|OMEGA")}
    pairs = {
        f"{pos}|ECR": store.get(f"{pos}|ECR", {}),
        f"{pos}|ALPHA": store.get(f"{pos}|ALPHA", {}),
    }
    out: dict = {"loso": {}, "per_season": {}, "loso_verdicts": {}}
    for m in (
        f"G@{PRIMARY_DEPTH}",
        f"G_F@{PRIMARY_DEPTH}",
        f"G_S@{PRIMARY_DEPTH}",
        f"G_C@{PRIMARY_DEPTH}",
    ):
        out["loso"][m] = leave_one_season_out(z, f"{pos}|DECOMP", ZERO, m)
        out["per_season"][m] = per_season(z, f"{pos}|DECOMP", ZERO, m)
    for m in ("pair_ALL", "pair_CLOSE", "pair_MATCHED", "pair_SURPRISE"):
        out["loso"][m] = leave_one_season_out(pairs, f"{pos}|ECR", f"{pos}|ALPHA", m)
        out["per_season"][m] = per_season(pairs, f"{pos}|ECR", f"{pos}|ALPHA", m)
    out["loso"]["surp_minus_close"] = leave_one_season_out(
        zo, f"{pos}|OMEGA", ZERO, "surp_minus_close"
    )
    out["per_season"]["surp_minus_close"] = per_season(zo, f"{pos}|OMEGA", ZERO, "surp_minus_close")
    for drop in SEASONS:
        fold = {
            system: {k: r for k, r in weeks.items() if not k.startswith(str(drop))}
            for system, weeks in store.items()
        }
        fold[ZERO] = {}
        s = position_summary(_with_zero(fold, pos), pos, (PRIMARY_DEPTH,), variants=False)
        out["loso_verdicts"][f"drop_{drop}"] = adv.verdict(s)
    return out


def _with_zero(store: dict, pos: str) -> dict:
    """`ZERO` must span exactly the weeks each compared system covers."""
    s = dict(store)
    zero: dict = {}
    for system in (f"{pos}|DECOMP", f"{pos}|OMEGA"):
        for k, r in store.get(system, {}).items():
            zero.setdefault(k, {}).update({m: 0.0 for m in r})
    s[ZERO] = zero
    return s


# ---------------------------------------------------------------------------------------
# Player level (§6, descriptive)
# ---------------------------------------------------------------------------------------


def player_level(con, cells: dict, panel: pd.DataFrame) -> dict:
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    records = []
    hits: dict[tuple[str, str], dict[str, int]] = {}
    for (_key, position), cell in sorted(cells.items()):
        snap, rows = cell["snap"], cell["rows"]
        real_order = sorted(rows, key=lambda p: (-rows[p].pts, p))
        real_rank = {p: n for n, p in enumerate(real_order, start=1)}
        real_top = set(real_order[:TOP_HIT_DEPTH])
        top_e = set(cell["order_e"][:TOP_HIT_DEPTH])
        top_a = set(cell["order_a"][:TOP_HIT_DEPTH])
        for p in sorted(real_top):
            h = hits.setdefault(
                (position, p), {"ecr_only": 0, "alpha_only": 0, "both": 0, "top_weeks": 0}
            )
            h["top_weeks"] += 1
            if p in top_e and p not in top_a:
                h["ecr_only"] += 1
            elif p in top_a and p not in top_e:
                h["alpha_only"] += 1
            elif p in top_a and p in top_e:
                h["both"] += 1
        for p in region_of(cell, REGION_DEPTH):
            i = idx[(p, snap.season, snap.week)]
            r = rows[p]
            rec = {
                "position": position,
                "season": snap.season,
                "player_id": p,
                "d": cell["rank_a"][p] - cell["rank_e"][p],
                "s": r.s,
                "c": r.c,
                "f": r.f,
                "err_a": abs(cell["rank_a"][p] - real_rank[p]),
                "err_e": abs(cell["rank_e"][p] - real_rank[p]),
                "ecr_only_hit": int(p in real_top and p in top_e and p not in top_a),
                "alpha_only_hit": int(p in real_top and p in top_a and p not in top_e),
            }
            for col in PROFILE_COLUMNS:
                v = panel.at[i, col] if col in panel.columns else None
                rec[col] = None if v is None or pd.isna(v) else float(v)
            records.append(rec)
    df = pd.DataFrame(records)
    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())
    out: dict = {"groups": {}, "repeat_hits": {}}
    value_cols = ["d", "s", "c", "f", "err_a", "err_e", *PROFILE_COLUMNS]
    for position in POSITIONS:
        sub = df[df.position == position]
        g = sub.groupby(["player_id", "season"])
        agg = g[value_cols].mean()
        agg["n_weeks"] = g.size()
        agg = agg[agg.n_weeks >= MIN_REGION_WEEKS].sort_values(["d", "n_weeks"], kind="mergesort")
        agg = agg.reset_index().sort_values(["d", "player_id", "season"], kind="mergesort")
        n = len(agg)
        cut = max(1, int(round(n * DECILE)))
        groups = {
            "ALPHA_FAVORED": agg.head(cut),
            "ECR_FAVORED": agg.tail(cut),
            "ALL_QUALIFYING": agg,
        }
        out["groups"][position] = {
            name: {
                "n_player_seasons": int(len(frame)),
                "n_player_weeks": int(frame.n_weeks.sum()),
                **{
                    col: (None if frame[col].isna().all() else float(frame[col].mean()))
                    for col in value_cols
                },
            }
            for name, frame in groups.items()
        }
        ranked = sorted(
            ((p, h) for (pos, p), h in hits.items() if pos == position),
            key=lambda t: (-(t[1]["ecr_only"] - t[1]["alpha_only"]), t[0]),
        )
        prof = []
        for p, h in ranked[:N_PROFILE]:
            mine = sub[sub.player_id == p]
            prof.append(
                {
                    "player_id": p,
                    "name": names.get(p),
                    **h,
                    "net_ecr_only": h["ecr_only"] - h["alpha_only"],
                    "region_weeks": int(len(mine)),
                    **{
                        col: (None if mine[col].isna().all() else float(mine[col].mean()))
                        for col in ("d", "s", "c", "f", "opp_sd_last3", "games_played_prior")
                    },
                }
            )
        out["repeat_hits"][position] = {
            "top": prof,
            "totals": {
                "ecr_only": sum(h["ecr_only"] for (pos, _p), h in hits.items() if pos == position),
                "alpha_only": sum(
                    h["alpha_only"] for (pos, _p), h in hits.items() if pos == position
                ),
            },
        }
    return out


# ---------------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------------


def analyse(con, snapshots, fmt, panel, fc, fc_opp, oracle) -> dict:
    ppr = fmt.points_per_reception
    unis = universes(con, snapshots, fmt)
    cells = collect(con, unis, panel, fc, fc_opp, ppr)
    thr = compute_thresholds(cells, POSITIONS)
    audit_log = {"max_identity_residual": 0.0}
    pm = positional_metrics(cells, thr, audit_log)
    store = pm["store"]
    snaps_by_key = {key: cell["snap"] for (key, _p), cell in cells.items()}
    fm = flex_metrics(con, snaps_by_key, cells, thr, fmt, ppr, panel, fc, audit_log)
    store.update(fm["store"])
    zero: dict = {}
    for system, weeks in store.items():
        if system.endswith(("|DECOMP", "|OMEGA", "|P3", "|ATTR")):
            for k, r in weeks.items():
                zero.setdefault(k, {}).update({m: 0.0 for m in r})
    store[ZERO] = zero

    summaries = {pos: position_summary(store, pos, DEPTHS, variants=True) for pos in POSITIONS}
    summaries["FLEX"] = position_summary(store, "FLEX", FLEX_DEPTHS, variants=False)
    for pos in POSITIONS:
        summaries[pos]["p3"] = compare(store, f"{pos}|P3", ZERO, ["rho_d_s", "rho_d_c", "rho_d_f"])
        attr_metrics = sorted({m for r in store.get(f"{pos}|ATTR", {}).values() for m in r})
        summaries[pos]["attribution"] = compare(store, f"{pos}|ATTR", ZERO, attr_metrics)
        conc = sorted(
            {m for r in store.get(f"{pos}|ECR", {}).values() for m in r if m.startswith("conc_")}
        )
        summaries[pos]["concordance"] = compare(store, f"{pos}|ECR", f"{pos}|ALPHA", conc)
        summaries[pos]["concordance_levels"] = {
            system: {
                m: statistics.fmean(v)
                for m in conc
                if (v := [r[m] for r in store.get(f"{pos}|{system}", {}).values() if m in r])
            }
            for system in ("ECR", "ALPHA")
        }
        summaries[pos]["swap_counts"] = {
            k.split("|", 1)[1]: v for k, v in pm["swaps"].items() if k.startswith(f"{pos}|")
        }
        summaries[pos]["pair_counts"] = {
            m: statistics.fmean(r[m] for r in store.get(f"{pos}|NPAIRS", {}).values() if m in r)
            for m in (f"pair_{t}" for t in adv.PAIR_TYPES)
        }
    verdicts = {pos: adv.verdict(summaries[pos]) for pos in (*POSITIONS, "FLEX")}
    sensitivity = {
        pos: {v: adv.verdict(summaries[pos], prefix=f"{v}_") for v in VARIANTS} for pos in POSITIONS
    }
    for pos in POSITIONS:
        for d in REGION_SENSITIVITY:
            s2 = {
                "decomp": summaries[pos]["decomp"],
                "pairs": {
                    "pair_ALL": summaries[pos]["pairs"].get(f"r{d}_ALL"),
                    "pair_CLOSE": summaries[pos]["pairs"].get(f"r{d}_CLOSE"),
                    "pair_MATCHED": summaries[pos]["pairs"].get(f"r{d}_MATCHED"),
                },
                "omega": {
                    "surp_minus_close": summaries[pos]["omega"].get(f"r{d}_surp_minus_close")
                },
            }
            sensitivity[pos][f"region{d}"] = adv.verdict(s2)
        for k in (5, 20):
            sensitivity[pos][f"capture@{k}"] = adv.verdict(summaries[pos], depth=k)
    over = adv.overall(verdicts["RB"]["verdict"], verdicts["WR"]["verdict"])
    result = {
        "thresholds": {
            p: {k: list(v) if isinstance(v, tuple) else v for k, v in t.items()}
            for p, t in thr.items()
        },
        "flex_match_cut": fm["match_cut"],
        "n_weeks": len({key for (key, _p) in cells}),
        "n_cells": {p: sum(1 for (_k, q) in cells if q == p) for p in POSITIONS},
        "n_players": {
            p: sum(len(c["rows"]) for (_k, q), c in cells.items() if q == p) for p in POSITIONS
        },
        "flex_weeks": fm["n_weeks"],
        "identity_max_residual": audit_log["max_identity_residual"],
        "summaries": summaries,
        "verdicts": verdicts,
        "overall": over,
        "recommendation": adv.recommendation(
            over, [verdicts[p]["w_flag"] for p in PRIMARY_POSITIONS]
        ),
        "sensitivity_verdicts": sensitivity,
        "robustness": {pos: robustness(store, pos) for pos in POSITIONS},
        "cells": store,
    }
    if oracle is not None:
        cf = counterfactual_cells(con, cells, oracle, ppr)
        comps = []
        for pos in POSITIONS:
            comps += [
                (f"{pos}|{ORACLE_ARM}", f"{pos}|CF_A"),
                (f"{pos}|ORACLE_USAGE", f"{pos}|CF_A"),
                (f"{pos}|ECR", f"{pos}|CF_A"),
                (f"{pos}|ECR", f"{pos}|{ORACLE_ARM}"),
            ]
        cfs = summarise(cf, comps)
        ratios = {}
        for pos in POSITIONS:
            for m in ("capture@5", "capture@10", "capture@20", "spearman"):
                b = cfs["paired"].get(f"{pos}|{ORACLE_ARM}_vs_{pos}|CF_A", {}).get(m)
                c = cfs["paired"].get(f"{pos}|ECR_vs_{pos}|CF_A", {}).get(m)
                if b and c and c["mean_diff"]:
                    ratios.setdefault(pos, {})[m] = b["mean_diff"] / c["mean_diff"]
        result["counterfactual"] = {"summary": cfs, "b_over_c_ratio": ratios, "cells": cf}
        result["player_level"] = player_level(con, cells, panel)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w8_results.json")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    sources = context.wire_snapshot_views(con, tuple(range(2015, 2026)))

    print("[1/6] building the pre-Friday panel (W7) ...")
    panel = op.build_panel(con, POSITIONS)
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"      {len(panel):,} appearances; {len(snapshots)} evaluated weeks")

    print("[2/6] W7's Class A forecasts (M_NEW): T_XFP, T_XFP_HALF, T_OPP ...")
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    fc_half = {p: op.walk_forward(panel, p, "T_XFP_HALF", "M_NEW", SEASONS) for p in POSITIONS}
    fc_opp = {p: op.walk_forward(panel, p, "T_OPP", "M_NEW", SEASONS) for p in POSITIONS}

    print("[3/6] training the Class D diagnostic ALPHA_ORACLE_OPP (never a candidate) ...")
    extra = panel[["player_id", "season", "week", "y_xfp", "y_opp"]].copy()
    missing = extra["y_xfp"].isna()
    _gate(bool((extra.loc[missing, "y_opp"] == 0).all()), "a missing usage row had opportunity")
    extra[ORACLE_FEATURE] = extra["y_xfp"].fillna(0.0)
    oracle = arms_mod.train_with_extra_features(
        con,
        extra[["player_id", "season", "week", ORACLE_FEATURE]],
        [ORACLE_FEATURE],
        arm=ORACLE_ARM,
    )

    print("[4/6] Full PPR: decomposition, pairs, buckets, counterfactual, player level ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, oracle)
    print("[5/6] Half-PPR replication ...")
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, None)

    print("[6/6] writing ...")
    for pos in (*POSITIONS, "FLEX"):
        v = full["verdicts"][pos]
        d = full["summaries"][pos]["decomp"]
        k = PRIMARY_DEPTH
        g = d.get(f"G@{k}", {})
        print(
            f"  {pos:4s} G@{k} {g.get('mean_diff', float('nan')):+.4f}  "
            + "  ".join(
                f"{p} {d.get(f'{p}@{k}', {}).get('mean_diff', float('nan')):+.4f}"
                for p in ("G_F", "G_S", "G_C")
            )
            + f"  -> {v['verdict']}  (half: {half['verdicts'][pos]['verdict']})"
        )
    print(f"  overall: {full['overall']}  |  recommendation: {full['recommendation']}")

    result = {
        "provenance": {
            "forecast": {
                "model": "M_NEW",
                "features": list(op.S0) + list(op.NEW),
                "ridge_alpha": op.RIDGE_ALPHA,
            },
            "oracle_arm": ORACLE_ARM,
            "oracle_feature": ORACLE_FEATURE,
            "oracle_counts": oracle.by_position,
            "region_depth": REGION_DEPTH,
            "flex_region_depth": FLEX_REGION_DEPTH,
            "depths": list(DEPTHS),
            "sources": sources,
        },
        "full_ppr": full,
        "half_ppr": half,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str, sort_keys=True))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
