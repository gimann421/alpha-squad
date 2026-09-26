"""W9 --- durable knowledge, weekly information or efficiency: where does ECR's edge come from?

Runs exactly what `docs/weekly/W9_PREREGISTRATION.md` (with amendments A1, A2) specifies.
**Research only. ECR is an instrument: it appears as a comparison board and a statistical
control, never in a trained model.** Three models are trained, all declared:

  ALPHA_PLUS_DURABLE           production's CatBoost + 7 prior-season (Class A) features -- I-D1
  ALPHA_PLUS_DURABLE_SHUFFLED  the same, features permuted within season -- G12's null
  ALPHA_ORACLE_OPP             W8's Class D ceiling (realized usage) -- the §8 counterfactual

    uv run python scripts/research/w9_mechanisms.py --out reports/weekly/w9_results.json
"""

from __future__ import annotations

import argparse
import datetime as dt
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
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from alpha_squad.identity.canonical import reader_expr  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research.w6_upper_outcome import (  # noqa: E402
    flex_cell,
    leave_one_season_out,
    per_season,
    summarise,
)
from scripts.research.w7_opportunity import universes  # noqa: E402

SEASONS = w8.SEASONS
POSITIONS = w8.POSITIONS
PRIMARY_POSITIONS = w8.PRIMARY_POSITIONS
DEPTHS = w8.DEPTHS
K = 10
REGION_DEPTH = w8.REGION_DEPTH
REGION_SENSITIVITY = (10, 30)
FLEX_DEPTHS = (10, 25)
DURABLE_ARM = "ALPHA_PLUS_DURABLE"
SHUFFLED_ARM = "ALPHA_PLUS_DURABLE_SHUFFLED"
ORACLE_ARM = w8.ORACLE_ARM
ZERO = w8.ZERO
PRESEASON_PAGES = {"RB": "redraft-rb", "WR": "redraft-wr", "TE": "redraft-te"}
BOARDS = ("ECR", "AD", "ADS", "PRE", "PPG", "OU")
_put = w8._put
_gate = w8._gate


def _num(v) -> float | None:
    """None for None or NaN (pandas turns a missing durable value into NaN)."""
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def _order(ids, score: dict[str, float], tiebreak: dict[str, float]) -> list[str]:
    return sorted(ids, key=lambda p: (-score[p], tiebreak[p], p))


def _order_ranked(ids, rank: dict[str, float], tiebreak: dict[str, float]) -> list[str]:
    """Ranked players first by rank (lower is better); unranked after, in Alpha's order."""
    big = 1e9
    return sorted(ids, key=lambda p: (rank.get(p, big), tiebreak[p], p))


# ---------------------------------------------------------------------------------------
# Durable information (Class A)
# ---------------------------------------------------------------------------------------


def durable_table(con, through: int = 2025) -> pd.DataFrame:
    """(player_id, season S) -> the 7 §4.1 features from season S-1, for S = 2016..`through`.

    Season 2015 has no prior season in the repository: its training rows get NaN everywhere
    (including `has_prior`), meaning "unknown", never "no prior season". `through` (default 2025,
    W9's range exactly) lets W10's frozen 2026 protocol build 2026's rows from 2025."""
    rows = con.execute(
        "SELECT player_id, season, week, position, fantasy_points_ppr, targets, carries, "
        "target_share, offense_snap_pct FROM player_week_stats "
        "ORDER BY player_id, season, week"
    ).fetchall()
    by: dict[tuple[str, int], list[dict]] = {}
    pos_last: dict[tuple[str, int], str] = {}
    for pid, season, week, pos, ppr, tgt, car, tsh, snap in rows:
        by.setdefault((pid, int(season)), []).append(
            {
                "week": int(week),
                "ppr": ppr,
                "targets": tgt,
                "carries": car,
                "target_share": tsh,
                "snap": snap,
                "position": pos,
            }
        )
        pos_last[(pid, int(season))] = pos
    # W5's positional rank by total PPR, player_id tiebreak -- totals by fsum (order-free).
    ranks: dict[tuple[str, int], int] = {}
    for season in range(2015, through + 1):
        groups: dict[str, list[tuple[float, str]]] = {}
        for (pid, s), wk in by.items():
            if s != season:
                continue
            per_pos: dict[str, list[float]] = {}
            for r in wk:
                per_pos.setdefault(r["position"], []).append(float(r["ppr"] or 0.0))
            for pos, vals in per_pos.items():
                groups.setdefault(pos, []).append((math.fsum(vals), pid))
        for pos, items in groups.items():
            items.sort(key=lambda t: (-t[0], t[1]))
            for n, (_tot, pid) in enumerate(items, start=1):
                if pos_last.get((pid, season)) == pos:
                    ranks[(pid, season)] = n
    players = sorted({pid for pid, _s in by})
    out = []
    for season in range(2016, through + 1):
        for pid in players:
            prev = by.get((pid, season - 1), [])
            if not by.get((pid, season)) and not prev:
                continue
            f = mech.durable_features(prev, ranks.get((pid, season - 1)))
            out.append({"player_id": pid, "season": season, **f})
    return pd.DataFrame(out)


def durable_panel(panel: pd.DataFrame, dur: pd.DataFrame, shuffle: bool) -> pd.DataFrame:
    """Durable features broadcast to every (player, season, week) of the panel."""
    d = dur.copy()
    if shuffle:
        parts = []
        for season in sorted(d.season.unique()):
            block = d[d.season == season].sort_values("player_id").reset_index(drop=True)
            perm = list(range(len(block)))
            random.Random(1000 + int(season)).shuffle(perm)
            feats = block[list(mech.DURABLE_FEATURES)].iloc[perm].reset_index(drop=True)
            parts.append(pd.concat([block[["player_id", "season"]], feats], axis=1))
        d = pd.concat(parts, ignore_index=True)
    keys = panel[["player_id", "season", "week"]].copy()
    out = keys.merge(d, on=["player_id", "season"], how="left", validate="many_to_one")
    for col in mech.DURABLE_FEATURES:
        out[col] = out[col].astype(float)
    return out


def preseason_ranks(con) -> dict[tuple[int, str], dict[str, float]]:
    """(season, position) -> player -> frozen preseason expert rank: the latest `rp redraft-*`
    scrape STRICTLY before the season's first regular-season game (Class A)."""
    first = dict(
        con.execute(
            "SELECT season, min(CAST(game_date AS DATE)) FROM games WHERE game_type='REG' GROUP BY 1"
        ).fetchall()
    )
    out: dict[tuple[int, str], dict[str, float]] = {}
    for season in SEASONS:
        for pos, page in PRESEASON_PAGES.items():
            (scrape,) = con.execute(
                "SELECT max(CAST(scrape_date AS DATE)) FROM ecr WHERE ecr_type='rp' AND "
                "page_type=? AND CAST(scrape_date AS DATE) < ?",
                [page, first[season]],
            ).fetchone()
            rows = con.execute(
                """
                WITH x AS (SELECT DISTINCT fantasypros_id, gsis_id FROM xwalk WHERE gsis_id IS NOT NULL)
                SELECT p.player_id, min(e.ecr) FROM ecr e
                JOIN x ON x.fantasypros_id = e.id JOIN players p ON p.gsis_id = x.gsis_id
                WHERE e.ecr_type='rp' AND e.page_type=? AND CAST(e.scrape_date AS DATE)=?
                  AND e.ecr IS NOT NULL
                GROUP BY 1 ORDER BY 1
                """,
                [page, scrape],
            ).fetchall()
            _gate(scrape is not None and scrape < first[season], f"preseason {season} {pos}")
            out[(season, pos)] = {pid: float(r) for pid, r in rows}
            out[(season, pos, "scrape")] = str(scrape)  # type: ignore[index]
            out[(season, pos, "first_game")] = str(first[season])  # type: ignore[index]
    return out


# ---------------------------------------------------------------------------------------
# Weekly information: classes A (documented pre-Friday) / C (timing uncertain) / B (none)
# ---------------------------------------------------------------------------------------


def _snapshot_path(con, source: str, dataset: str, season: int) -> str | None:
    rows = con.execute(
        "SELECT params_json, local_path FROM snapshot_registry WHERE source=? AND dataset=? "
        "ORDER BY captured_at",
        [source, dataset],
    ).fetchall()
    hits = [p for js, p in rows if str(json.loads(js).get("season")) == str(season)]
    return hits[-1] if hits else None


def weekly_events(con, snapshots) -> tuple[dict, dict]:
    """(season, week, player_id) -> {"strict": bool, "uncertain": bool, "sources": [...]}, and an
    audit dict recording every class-A timestamp against its cutoff (gate G4)."""
    ev: dict[tuple[int, int, str], dict] = {}
    audit_rows: list[dict] = []

    def mark(key, kind, source):
        e = ev.setdefault(key, {"strict": False, "uncertain": False, "sources": []})
        e[kind] = True
        e["sources"].append(source)

    mates: dict[tuple[int, int, str, str], list[str]] = {}
    for s, w, p, t, pos in con.execute(
        "SELECT season, week, player_id, team, position FROM player_week_stats "
        "WHERE season >= 2021 ORDER BY season, week, player_id"
    ).fetchall():
        mates.setdefault((int(s), int(w), t, pos), []).append(p)
    # injuries 2021-2024: strict (< cutoff date) and same-day (= cutoff date)
    for snap in snapshots:
        if snap.season > 2024:
            continue
        rows = con.execute(
            "SELECT player_id, team, position, report_status, modified_on FROM _injuries "
            "WHERE season = ? AND week = ? AND modified_on <= ?",
            [snap.season, snap.week, snap.scrape_date],
        ).fetchall()
        for pid, team, pos, report, mod in rows:
            kind = "strict" if mod < snap.scrape_date else "uncertain"
            if pid:
                mark((snap.season, snap.week, pid), kind, "own_injury")
                if kind == "strict":
                    audit_rows.append(
                        {"source": "injury", "ts": str(mod), "cutoff": str(snap.scrape_date)}
                    )
            if report in ("Out", "Doubtful") and team and pos:
                for p in mates.get((snap.season, snap.week, team, pos), []):
                    if p != pid:
                        mark((snap.season, snap.week, p), kind, "teammate_out")
                if kind == "strict":
                    audit_rows.append(
                        {"source": "teammate", "ts": str(mod), "cutoff": str(snap.scrape_date)}
                    )
    # injuries 2025: no timestamp at all -> timing uncertain
    p25 = _snapshot_path(con, "nflverse", "injuries", 2025)
    if p25:
        con.execute(f"CREATE OR REPLACE TEMP VIEW _inj25 AS SELECT * FROM {reader_expr(p25)}")
        rows = con.execute(
            "SELECT p.player_id, CAST(i.week AS INTEGER), i.team, i.position, i.report_status "
            "FROM _inj25 i JOIN players p ON p.gsis_id = i.gsis_id"
        ).fetchall()
        wk25 = {s.week for s in snapshots if s.season == 2025}
        for pid, week, team, pos, report in rows:
            if week not in wk25:
                continue
            mark((2025, week, pid), "uncertain", "own_injury_2025")
            if report in ("Out", "Doubtful"):
                for p in mates.get((2025, week, team, pos), []):
                    if p != pid:
                        mark((2025, week, p), "uncertain", "teammate_out_2025")
    # depth charts 2021-2024: current-week change vs previous week -> timing uncertain
    depth = {}
    for s, w, p, d in con.execute(
        "SELECT season, week, player_id, min(depth_team) FROM _depth WHERE season BETWEEN 2021 AND 2024 "
        "GROUP BY 1, 2, 3"
    ).fetchall():
        depth[(int(s), int(w), p)] = int(d) if d is not None else None
    for snap in snapshots:
        if snap.season > 2024:
            continue
        cur = {p: d for (s, w, p), d in depth.items() if s == snap.season and w == snap.week}
        prev = {p: d for (s, w, p), d in depth.items() if s == snap.season and w == snap.week - 1}
        for p in sorted(set(cur) | set(prev)):
            if cur.get(p, -1) != prev.get(p, -1):
                mark((snap.season, snap.week, p), "uncertain", "depth_change_2124")
    # depth charts 2025: ESPN snapshot strictly before the cutoff date vs one week earlier -> A
    d25 = _snapshot_path(con, "nflverse", "depth_charts", 2025)
    if d25:
        con.execute(f"CREATE OR REPLACE TEMP VIEW _d25 AS SELECT * FROM {reader_expr(d25)}")
        for snap in snapshots:
            if snap.season != 2025:
                continue
            ts = []
            for bound in (snap.scrape_date, snap.scrape_date - dt.timedelta(days=7)):
                (t,) = con.execute(
                    "SELECT max(dt) FROM _d25 WHERE CAST(substr(dt, 1, 10) AS DATE) < ?", [bound]
                ).fetchone()
                ts.append(t)
            if None in ts:
                continue
            charts = []
            for t in ts:
                charts.append(
                    {
                        (p, pos): r
                        for p, pos, r in con.execute(
                            "SELECT pl.player_id, d.pos_abb, min(d.pos_rank) FROM _d25 d "
                            "JOIN players pl ON pl.gsis_id = d.gsis_id "
                            "WHERE d.dt = ? AND d.pos_abb IN ('RB', 'WR', 'TE') GROUP BY 1, 2",
                            [t],
                        ).fetchall()
                    }
                )
            now, before = charts
            for key in sorted(set(now) | set(before)):
                if now.get(key) != before.get(key):
                    mark((2025, snap.week, key[0]), "strict", "depth_change_2025")
                    audit_rows.append(
                        {"source": "depth_2025", "ts": ts[0][:10], "cutoff": str(snap.scrape_date)}
                    )
    return ev, {"class_a_timestamps": audit_rows}


# ---------------------------------------------------------------------------------------
# Per-format analysis
# ---------------------------------------------------------------------------------------


def _x_rows(dur_lookup, pids, season):
    out = []
    for p in pids:
        f = dur_lookup.get((p, season)) or {}
        out.append([_num(f.get(c)) or 0.0 for c in mech.DURABLE_FEATURES])
    return out


def analyse(con, snapshots, fmt, panel, fc, fc_opp, trained: dict, dur: pd.DataFrame, pre, events):
    ppr = fmt.points_per_reception
    unis = universes(con, snapshots, fmt)
    cells = w8.collect(con, unis, panel, fc, fc_opp, ppr)
    thr = w8.compute_thresholds(cells, POSITIONS)
    log = {"max_identity_residual": 0.0}
    store8 = w8.positional_metrics(cells, thr, log)["store"]
    snaps_by_key = {key: cell["snap"] for (key, _p), cell in cells.items()}
    store8.update(w8.flex_metrics(con, snaps_by_key, cells, thr, fmt, ppr, panel, fc, log)["store"])
    zero8: dict = {}
    for system, weeks in store8.items():
        if system.endswith(("|DECOMP", "|OMEGA", "|P3", "|ATTR")):
            for k, r in weeks.items():
                zero8.setdefault(k, {}).update({m: 0.0 for m in r})
    store8[ZERO] = zero8

    dur_lookup = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    store: dict = {}
    counts: dict = {}
    week_of: dict[str, int] = {}
    for (key, pos), cell in sorted(cells.items()):
        snap, rows = cell["snap"], cell["rows"]
        week_of[key] = snap.week
        ids = sorted(rows)
        tb = cell["rank_a"]
        season = snap.season
        dfe = {p: dur_lookup.get((p, season)) for p in ids}
        pre_rank = pre[(season, pos)]
        usage = context.load_usage_points(con, snap.season, snap.week, ppr)
        orders = {
            "ECR": cell["order_e"],
            "AD": _order(ids, trained[DURABLE_ARM].for_week(season, snap.week, pos), tb),
            "ADS": _order(ids, trained[SHUFFLED_ARM].for_week(season, snap.week, pos), tb),
            "PRE": _order_ranked(ids, pre_rank, tb),
            "PPG": _order(
                ids,
                {
                    p: (
                        _num(dfe[p]["prior_ppg"])
                        if dfe[p] and _num(dfe[p]["prior_ppg"]) is not None
                        else -1.0
                    )
                    for p in ids
                },
                tb,
            ),
            "OU": w8._order(topboard.oracle_usage(cell["common"], cell["alpha_pred"], usage)[0]),
        }
        if ORACLE_ARM in trained:
            orders["OO"] = _order(ids, trained[ORACLE_ARM].for_week(season, snap.week, pos), tb)
        for name, order in orders.items():
            _gate(set(order) == set(ids), f"{key} {pos} {name} universe")
            for k in DEPTHS:
                dec = adv.decompose_gap(order, cell["order_a"], rows, k)
                if dec is None:
                    continue
                for piece in ("G", "G_F", "G_S", "G_C"):
                    _put(store, f"{pos}|{name}", key, f"{piece}@{k}", dec[piece])

        rank = {name: {p: float(n) for n, p in enumerate(o, start=1)} for name, o in orders.items()}
        for depth in (REGION_DEPTH, *REGION_SENSITIVITY):
            region = w8.region_of(cell, depth)
            tag = "" if depth == REGION_DEPTH else f"r{depth}_"
            d = [cell["rank_a"][p] - cell["rank_e"][p] for p in region]
            s = [rows[p].s for p in region]
            terms = mech.anticipation_terms(d, s)
            if terms is None:
                continue
            rho = math.fsum(terms) / len(terms)
            if depth == REGION_DEPTH:
                _gate(
                    abs(rho - adv.spearman_values(d, s)) < 1e-12, f"{key} {pos}: decomposable rho"
                )
            _put(store, f"{pos}|ANT", key, f"{tag}rho", rho)
            x_pub = _x_rows(dur_lookup, region, season)
            x_pre = [[cell["rank_a"][p] - rank["PRE"][p]] for p in region]
            for label, x in (("pub", x_pub), ("pre", x_pre)):
                red = mech.adjusted_reduction(d, s, x)
                if red:
                    _put(store, f"{pos}|ANT", key, f"{tag}red_{label}", red["adjusted_reduction"])
                    _put(store, f"{pos}|ANT", key, f"{tag}rawred_{label}", red["raw_reduction"])
            if depth == REGION_DEPTH:
                # G12: an independent random permutation standing in for the real features
                perm = list(range(len(region)))
                random.Random(7_000 + len(store.get(f"{pos}|ANT", {}))).shuffle(perm)
                red = mech.adjusted_reduction(d, s, [x_pub[i] for i in perm])
                if red:
                    _put(store, f"{pos}|ANT", key, "red_null", red["adjusted_reduction"])
                for name in ("AD", "PRE", "PPG"):
                    dz = [cell["rank_a"][p] - rank[name][p] for p in region]
                    _put(store, f"{pos}|ANT", key, f"rho_{name}", adv.spearman_values(dz, s))

                # tiers and weekly classes over the region; attribution over the swap set
                tier = {
                    p: mech.tier_of(_num(dfe[p]["prior_rank"]) if dfe[p] else None) for p in ids
                }
                cls = {}
                for p in ids:
                    e = events.get((season, snap.week, p), {})
                    cls[p] = mech.classify_weekly(e.get("strict", False), e.get("uncertain", False))
                for label, groups, names in (
                    ("tier", tier, mech.TIERS),
                    ("class", cls, mech.WEEKLY_CLASSES),
                ):
                    for piece in ("G", "S"):
                        attr = mech.attribute_piece(
                            cell["order_e"], cell["order_a"], rows, K, groups, piece
                        )
                        if attr is None:
                            continue
                        dec = adv.decompose_gap(cell["order_e"], cell["order_a"], rows, K)
                        whole = dec["G"] if piece == "G" else dec[f"G_{piece}"]
                        _gate(
                            abs(sum(attr.values()) - whole) < 1e-9,
                            f"{key} {pos} {label} {piece}: attribution does not sum",
                        )
                        for g in names:
                            _put(
                                store, f"{pos}|ATTR9", key, f"{label}_{piece}|{g}", attr.get(g, 0.0)
                            )
                    ta, tb2 = set(cell["order_e"][:K]), set(cell["order_a"][:K])
                    for p in sorted(ta ^ tb2):
                        c = counts.setdefault(f"{pos}|{label}_swaps", {})
                        c[groups[p]] = c.get(groups[p], 0) + 1
                    for g in names:
                        mem = [t for p, t in zip(region, terms, strict=True) if groups[p] == g]
                        _put(store, f"{pos}|GRP", key, f"{label}_sum|{g}", math.fsum(mem))
                        _put(store, f"{pos}|GRP", key, f"{label}_n|{g}", float(len(mem)))
                        cc = counts.setdefault(f"{pos}|{label}_region", {})
                        cc[g] = cc.get(g, 0) + len(mem)
                        if label == "class" and mem:
                            wk = counts.setdefault(f"{pos}|class_weeks", {})
                            wk[g] = wk.get(g, 0) + 1
                a_mem = [t for p, t in zip(region, terms, strict=True) if cls[p] == "A"]
                b_mem = [t for p, t in zip(region, terms, strict=True) if cls[p] == "B"]
                if a_mem and b_mem:
                    _put(
                        store,
                        f"{pos}|GRP",
                        key,
                        "a_minus_b",
                        statistics.fmean(a_mem) - statistics.fmean(b_mem),
                    )

    zero: dict = {}
    for weeks in store.values():
        for k, r in weeks.items():
            zero.setdefault(k, {}).update({m: 0.0 for m in r})
    store[ZERO] = zero
    flex = flex_analysis(con, cells, fmt, ppr, panel, fc, trained)
    return {
        "cells": cells,
        "store": store,
        "store8": store8,
        "counts": counts,
        "week_of": week_of,
        "flex": flex,
        "identity": log["max_identity_residual"],
    }


def flex_analysis(con, cells, fmt, ppr, panel, fc, trained) -> dict:
    """FLEX through the existing pooled path: ECR, AD and (Full PPR) OO against Alpha."""
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    by_week: dict[str, dict] = {}
    for (key, _pos), cell in cells.items():
        w = by_week.setdefault(key, {"snap": cell["snap"], "alpha": {}})
        w["alpha"].update(cell["alpha_pred"])
    store: dict = {}
    cf: dict = {}
    for key in sorted(by_week):
        snap, alpha = by_week[key]["snap"], by_week[key]["alpha"]
        commonf, boardf, _k = flex_cell(con, snap, fmt, alpha)
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        uni = {r.player_id for r in boardf.rows}
        usage = context.load_usage_points(con, snap.season, snap.week, ppr)
        rows = {}
        for r in commonf.evaluable:
            i = idx[(r.player_id, snap.season, snap.week)]
            x = usage.get(r.player_id, 0.0)
            if r.player_id not in usage:
                _gate(panel.at[i, "y_opp"] == 0, f"FLEX {key} {r.player_id}: usage")
            rows[r.player_id] = adv.PlayerWeek(
                r.player_id, float(r.realized), float(x), float(fc[r.position].at[i])
            )
        order_a, order_e = w8._order(boardf), w8._order(commonf)
        orders = {"ECR": order_e}
        for tag, arm in (("AD", DURABLE_ARM), ("OO", ORACLE_ARM)):
            if arm not in trained:
                continue
            preds = {}
            for pos in POSITIONS:
                preds.update(trained[arm].for_week(snap.season, snap.week, pos))
            _c, bz, _k2 = flex_cell(con, snap, fmt, preds, universe=uni)
            orders[tag] = w8._order(bz)
            if tag == "OO":
                pr, rl = bz.ranks_and_points()
                cf.setdefault(f"FLEX|{ORACLE_ARM}", {})[key] = evaluate_cell(
                    pr, rl, depths=topboard.W5_DEPTHS
                ).as_row()
        for board, name in ((boardf, "CF_A"), (commonf, "ECR")):
            pr, rl = board.ranks_and_points()
            cf.setdefault(f"FLEX|{name}", {})[key] = evaluate_cell(
                pr, rl, depths=topboard.W5_DEPTHS
            ).as_row()
        for name, order in orders.items():
            for k in FLEX_DEPTHS:
                dec = adv.decompose_gap(order, order_a, rows, k)
                if dec:
                    for piece in ("G", "G_F", "G_S", "G_C"):
                        _put(store, f"FLEX|{name}", key, f"{piece}@{k}", dec[piece])
    zero: dict = {}
    for weeks in store.values():
        for k, r in weeks.items():
            zero.setdefault(k, {}).update({m: 0.0 for m in r})
    store[ZERO] = zero
    return {"store": store, "counterfactual_cells": cf}


# ---------------------------------------------------------------------------------------
# Summaries and the verdict
# ---------------------------------------------------------------------------------------


def _subset(store: dict, keep) -> dict:
    return {sys_: {k: r for k, r in weeks.items() if keep(k)} for sys_, weeks in store.items()}


def _period_keep(week_of, period):
    return lambda k: mech.period_of(week_of[k]) == period


def _mean(series: dict) -> float | None:
    return statistics.fmean(series.values()) if series else None


def summarise_position(res: dict, pos: str) -> dict:
    store, week_of = res["store"], res["week_of"]
    S = w8._series
    out: dict = {}
    dec_metrics = [f"{p}@{k}" for k in DEPTHS for p in ("G", "G_F", "G_S", "G_C")]
    out["boards"] = {
        b: w8.compare(store, f"{pos}|{b}", ZERO, dec_metrics)
        for b in (*BOARDS, "OO")
        if f"{pos}|{b}" in store
    }
    ant_metrics = sorted({m for r in store.get(f"{pos}|ANT", {}).values() for m in r})
    out["anticipation"] = w8.compare(store, f"{pos}|ANT", ZERO, ant_metrics)
    rho = S(store, f"{pos}|ANT", "rho")
    out["shares"] = {
        "closure_S": w8.ratio_ci(
            S(store, f"{pos}|AD", f"G_S@{K}"), S(store, f"{pos}|ECR", f"G_S@{K}")
        ),
        "closure_G": w8.ratio_ci(S(store, f"{pos}|AD", f"G@{K}"), S(store, f"{pos}|ECR", f"G@{K}")),
        "closure_S_shuffled": w8.ratio_ci(
            S(store, f"{pos}|ADS", f"G_S@{K}"), S(store, f"{pos}|ECR", f"G_S@{K}")
        ),
        "pre_board_S": w8.ratio_ci(
            S(store, f"{pos}|PRE", f"G_S@{K}"), S(store, f"{pos}|ECR", f"G_S@{K}")
        ),
        "ppg_board_S": w8.ratio_ci(
            S(store, f"{pos}|PPG", f"G_S@{K}"), S(store, f"{pos}|ECR", f"G_S@{K}")
        ),
        "share_pub": w8.ratio_ci(S(store, f"{pos}|ANT", "red_pub"), rho),
        "share_pre": w8.ratio_ci(S(store, f"{pos}|ANT", "red_pre"), rho),
        "share_null": w8.ratio_ci(S(store, f"{pos}|ANT", "red_null"), rho),
        "anticipated_share": w8.ratio_ci(
            S(store, f"{pos}|ECR", f"G_S@{K}"), S(store, f"{pos}|OU", f"G_S@{K}")
        ),
    }
    # periods
    per = {}
    for name, _lo, _hi in mech.PERIODS:
        sub = _subset(store, _period_keep(week_of, name))
        per[name] = {
            "ECR": w8.compare(
                sub, f"{pos}|ECR", ZERO, [f"{p}@{K}" for p in ("G", "G_F", "G_S", "G_C")]
            ),
            "AD": w8.compare(sub, f"{pos}|AD", ZERO, [f"G@{K}", f"G_S@{K}"]),
            "ANT": w8.compare(sub, f"{pos}|ANT", ZERO, ["rho", "red_pub", "red_pre", "red_null"]),
            "GRP": w8.compare(sub, f"{pos}|GRP", ZERO, ["a_minus_b"]),
            "closure_S": w8.ratio_ci(
                S(sub, f"{pos}|AD", f"G_S@{K}"), S(sub, f"{pos}|ECR", f"G_S@{K}")
            ),
            "share_pub": w8.ratio_ci(S(sub, f"{pos}|ANT", "red_pub"), S(sub, f"{pos}|ANT", "rho")),
            "share_pre": w8.ratio_ci(S(sub, f"{pos}|ANT", "red_pre"), S(sub, f"{pos}|ANT", "rho")),
        }
    out["periods"] = per
    # seasons and LOSO for the verdict statistics
    stats = {
        "I-D1": (f"{pos}|AD", f"G_S@{K}"),
        "I-D2": (f"{pos}|ANT", "red_pub"),
        "I-D3": (f"{pos}|ANT", "red_pre"),
        "A_minus_B": (f"{pos}|GRP", "a_minus_b"),
    }
    out["per_season"] = {n: per_season(store, sysm, ZERO, m) for n, (sysm, m) in stats.items()}
    out["loso"] = {n: leave_one_season_out(store, sysm, ZERO, m) for n, (sysm, m) in stats.items()}
    # tiers and classes
    attr_metrics = sorted({m for r in store.get(f"{pos}|ATTR9", {}).values() for m in r})
    out["attribution"] = w8.compare(store, f"{pos}|ATTR9", ZERO, attr_metrics)
    grp = {}
    for label, names in (("tier", mech.TIERS), ("class", mech.WEEKLY_CLASSES)):
        for g in names:
            grp[f"{label}|{g}"] = w8.ratio_ci(
                S(store, f"{pos}|GRP", f"{label}_sum|{g}"), S(store, f"{pos}|GRP", f"{label}_n|{g}")
            )
    out["group_anticipation"] = grp
    out["a_minus_b"] = w8.compare(store, f"{pos}|GRP", ZERO, ["a_minus_b"])
    out["counts"] = {
        k.split("|", 1)[1]: v for k, v in res["counts"].items() if k.startswith(f"{pos}|")
    }
    return out


def efficiency_summary(res: dict, half: dict | None, pos: str) -> dict:
    """W8's EFFICIENCY rule and its §9 robustness, re-applied (not blind), plus periods."""
    s8 = w8.position_summary(res["store8"], pos, DEPTHS, variants=True)
    v = adv.verdict(s8)
    rob = w8.robustness(res["store8"], pos)

    def eff(x):
        r = x.get("routes", {})
        return bool(r.get("E-1") and (r.get("E-2a") or r.get("E-2b")))

    n_loso = sum(1 for x in rob["loso_verdicts"].values() if eff(x))
    n_var = sum(1 for p in w8.VARIANTS if eff(adv.verdict(s8, prefix=f"{p}_")))
    h = (
        eff(adv.verdict(w8.position_summary(half["store8"], pos, DEPTHS, variants=True)))
        if half
        else None
    )
    per = {}
    for name, _lo, _hi in mech.PERIODS:
        sub = _subset(res["store8"], _period_keep(res["week_of"], name))
        per[name] = w8.compare(
            sub, f"{pos}|ECR", f"{pos}|ALPHA", ["pair_ALL", "pair_CLOSE", "pair_MATCHED"]
        )
        per[name].update(w8.compare(sub, f"{pos}|DECOMP", ZERO, [f"G_C@{K}"]))
    supported = eff(v) and n_loso >= 4 and bool(h) and n_var >= 3
    return {
        "w8_routes": v.get("routes"),
        "rule_holds": eff(v),
        "loso": n_loso,
        "variants": n_var,
        "half_ppr": h,
        "supported": supported,
        "periods": per,
        "pairs": {m: s8["pairs"].get(m) for m in ("pair_ALL", "pair_CLOSE", "pair_MATCHED")},
        "G_C": s8["decomp"].get(f"G_C@{K}"),
        "G": s8["decomp"].get(f"G@{K}"),
        "large_share_of_G": (
            statistics.fmean(w8._series(res["store8"], f"{pos}|ATTR", "opp@10|LARGE").values())
            / statistics.fmean(w8._series(res["store8"], f"{pos}|DECOMP", f"G@{K}").values())
        ),
    }


def verdict_for(summary: dict, eff: dict) -> dict:
    sh = summary["shares"]
    ant = summary["anticipation"]
    ecr_gs = summary["boards"]["ECR"].get(f"G_S@{K}")
    routes = {}
    for name, red_row, share, early_row, seasons in (
        (
            "I-D1",
            summary["boards"]["AD"].get(f"G_S@{K}"),
            (sh["closure_S"] or {}).get("ratio"),
            summary["periods"]["EARLY"]["AD"].get(f"G_S@{K}"),
            summary["per_season"]["I-D1"],
        ),
        (
            "I-D2",
            ant.get("red_pub"),
            (sh["share_pub"] or {}).get("ratio"),
            summary["periods"]["EARLY"]["ANT"].get("red_pub"),
            summary["per_season"]["I-D2"],
        ),
        (
            "I-D3",
            ant.get("red_pre"),
            (sh["share_pre"] or {}).get("ratio"),
            summary["periods"]["EARLY"]["ANT"].get("red_pre"),
            summary["per_season"]["I-D3"],
        ),
    ):
        routes[name] = mech.durable_route(
            red_row, share, early_row, [r["mean_diff"] for r in seasons.values()]
        )
    d_public = routes["I-D1"]["all"] or routes["I-D2"]["all"]
    d_expert = routes["I-D3"]["all"]
    counts = summary["counts"]
    a_pw = counts.get("class_region", {}).get("A", 0)
    a_weeks = counts.get("class_weeks", {}).get("A", 0)
    measurable = a_pw >= mech.MIN_CLASS_A_PLAYER_WEEKS and a_weeks >= mech.MIN_CLASS_A_WEEKS
    swaps = counts.get("class_swaps", {})
    swap_total = sum(swaps.values())
    attr_a = summary["attribution"].get("class_S|A")
    a_share = (
        (attr_a["mean_diff"] / ecr_gs["mean_diff"])
        if attr_a and ecr_gs and ecr_gs["mean_diff"]
        else None
    )
    weekly = mech.weekly_rule(
        eff["large_share_of_G"],
        measurable,
        a_share,
        attr_a,
        (swaps.get("A", 0) / swap_total) if swap_total else None,
        summary["a_minus_b"].get("a_minus_b"),
        [r["mean_diff"] for r in summary["loso"]["A_minus_B"].values()],
    )
    pv = mech.position_verdict(d_public or d_expert, weekly["status"], eff["supported"])
    kinds = [k for k, ok in (("D_PUBLIC", d_public), ("D_EXPERT", d_expert)) if ok]
    shares = {
        "DURABLE": max(
            [
                v
                for v in (
                    (sh["closure_S"] or {}).get("ratio"),
                    (sh["share_pub"] or {}).get("ratio"),
                    (sh["share_pre"] or {}).get("ratio"),
                )
                if v is not None
            ]
            or [0.0]
        ),
        "WEEKLY": a_share or 0.0,
        "EFFICIENCY": (eff["G_C"]["mean_diff"] / eff["G"]["mean_diff"]) if eff["G"] else 0.0,
    }
    return {
        **pv,
        "durable_routes": routes,
        "durable_kind": " and ".join(kinds) or None,
        "weekly": weekly,
        "class_A_player_weeks": a_pw,
        "class_A_weeks": a_weeks,
        "class_A_share_of_GS": a_share,
        "efficiency": {
            k: eff[k] for k in ("rule_holds", "loso", "variants", "half_ppr", "supported")
        },
        "component_shares": shares,
    }


def player_level(con, res: dict, panel: pd.DataFrame, dur: pd.DataFrame, events: dict) -> dict:
    """The population first (ECR- vs Alpha-favoured player-seasons; repeat ECR-only top-10 hits),
    each described by durable tier, weekly class, period, efficiency and a 'quiet last game' flag."""
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    dur_lookup = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())
    recs = []
    for (_key, pos), cell in sorted(res["cells"].items()):
        snap, rows = cell["snap"], cell["rows"]
        top_e, top_a = set(cell["order_e"][:K]), set(cell["order_a"][:K])
        real = sorted(rows, key=lambda p: (-rows[p].pts, p))
        real_top = set(real[:K])
        for p in w8.region_of(cell, REGION_DEPTH):
            f = {
                k: _num(v)
                for k, v in (dur_lookup.get((p, snap.season)) or {}).items()
                if k in mech.DURABLE_FEATURES
            }
            last = _num(panel.at[idx[(p, snap.season, snap.week)], "T_XFP__BL_LAST"])
            e = events.get((snap.season, snap.week, p), {})
            recs.append(
                {
                    "position": pos,
                    "season": snap.season,
                    "player_id": p,
                    "period": mech.period_of(snap.week),
                    "d": cell["rank_a"][p] - cell["rank_e"][p],
                    "s": rows[p].s,
                    "c": rows[p].c,
                    "tier": mech.tier_of(f.get("prior_rank")),
                    "prior_ppg": f.get("prior_ppg"),
                    "class": mech.classify_weekly(
                        e.get("strict", False), e.get("uncertain", False)
                    ),
                    "quiet_last": (
                        1.0
                        if (
                            last is not None
                            and f.get("prior_ppg") is not None
                            and last < f["prior_ppg"]
                        )
                        else 0.0
                    ),
                    "ecr_only_hit": int(p in real_top and p in top_e and p not in top_a),
                    "alpha_only_hit": int(p in real_top and p in top_a and p not in top_e),
                }
            )
    df = pd.DataFrame(recs)
    out: dict = {}

    def profile(frame: pd.DataFrame) -> dict:
        n = len(frame)
        if not n:
            return {"n": 0}
        return {
            "n": int(n),
            **{f"tier_{t}": float((frame.tier == t).mean()) for t in mech.TIERS},
            **{f"class_{c}": float((frame["class"] == c).mean()) for c in mech.WEEKLY_CLASSES},
            **{f"period_{p}": float((frame.period == p).mean()) for p, _a, _b in mech.PERIODS},
            "quiet_last": float(frame.quiet_last.mean()),
            "mean_s": float(frame.s.mean()),
            "mean_c": float(frame.c.mean()),
            "mean_prior_ppg": float(frame.prior_ppg.dropna().mean())
            if frame.prior_ppg.notna().any()
            else None,
        }

    for pos in POSITIONS:
        sub = df[df.position == pos]
        g = sub.groupby(["player_id", "season"])
        agg = g["d"].mean().reset_index().merge(g.size().rename("n").reset_index())
        agg = agg[agg.n >= w8.MIN_REGION_WEEKS].sort_values(
            ["d", "player_id", "season"], kind="mergesort"
        )
        cut = max(1, int(round(len(agg) * w8.DECILE)))
        fav = {"ECR_FAVORED": agg.tail(cut), "ALPHA_FAVORED": agg.head(cut)}
        grp = {}
        for name, frame in fav.items():
            keys = set(zip(frame.player_id, frame.season, strict=True))
            grp[name] = profile(
                sub[[k in keys for k in zip(sub.player_id, sub.season, strict=True)]]
            )
        grp["ALL_REGION"] = profile(sub)
        grp["ECR_ONLY_HITS"] = profile(sub[sub.ecr_only_hit == 1])
        grp["ALPHA_ONLY_HITS"] = profile(sub[sub.alpha_only_hit == 1])
        hits = sub.groupby("player_id")[["ecr_only_hit", "alpha_only_hit"]].sum()
        hits["net"] = hits.ecr_only_hit - hits.alpha_only_hit
        hits = hits.reset_index().sort_values(
            ["net", "player_id"], ascending=[False, True], kind="mergesort"
        )
        top = []
        for r in hits.head(15).itertuples(index=False):
            mine = sub[(sub.player_id == r.player_id) & (sub.ecr_only_hit == 1)]
            top.append(
                {
                    "player_id": r.player_id,
                    "name": names.get(r.player_id),
                    "ecr_only": int(r.ecr_only_hit),
                    "alpha_only": int(r.alpha_only_hit),
                    **{
                        k: v
                        for k, v in profile(mine).items()
                        if k
                        in ("tier_ELITE", "class_A", "class_C", "quiet_last", "mean_s", "mean_c")
                    },
                }
            )
        out[pos] = {"groups": grp, "top_net_ecr_only": top}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w9_results.json")
    args = ap.parse_args()

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
    sources = context.wire_snapshot_views(con, tuple(range(2015, 2026)))

    print("[1/7] panel, W7 forecasts, durable table, preseason ranks ...")
    panel = op.build_panel(con, POSITIONS)
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    fc_half = {p: op.walk_forward(panel, p, "T_XFP_HALF", "M_NEW", SEASONS) for p in POSITIONS}
    fc_opp = {p: op.walk_forward(panel, p, "T_OPP", "M_NEW", SEASONS) for p in POSITIONS}
    dur = durable_table(con)
    pre = preseason_ranks(con)

    print("[2/7] weekly-information events (A / C) ...")
    events, ev_audit = weekly_events(con, snapshots)

    print("[3/7] the three declared trainings ...")
    cols = list(mech.DURABLE_FEATURES)
    trained = {
        DURABLE_ARM: arms_mod.train_with_extra_features(
            con, durable_panel(panel, dur, shuffle=False), cols, arm=DURABLE_ARM
        ),
        SHUFFLED_ARM: arms_mod.train_with_extra_features(
            con, durable_panel(panel, dur, shuffle=True), cols, arm=SHUFFLED_ARM
        ),
    }
    extra = panel[["player_id", "season", "week", "y_xfp", "y_opp"]].copy()
    _gate(
        bool((extra.loc[extra.y_xfp.isna(), "y_opp"] == 0).all()), "missing usage with opportunity"
    )
    extra[w8.ORACLE_FEATURE] = extra["y_xfp"].fillna(0.0)
    trained[ORACLE_ARM] = arms_mod.train_with_extra_features(
        con,
        extra[["player_id", "season", "week", w8.ORACLE_FEATURE]],
        [w8.ORACLE_FEATURE],
        arm=ORACLE_ARM,
    )

    print("[4/7] Full PPR ...")
    full = analyse(con, snapshots, FULL_PPR, panel, fc, fc_opp, trained, dur, pre, events)
    print("[5/7] Half-PPR ...")
    half_trained = {k: v for k, v in trained.items() if k != ORACLE_ARM}
    half = analyse(con, snapshots, HALF_PPR, panel, fc_half, fc_opp, half_trained, dur, pre, events)

    print("[6/7] summaries, verdicts, player level ...")
    out: dict = {"full_ppr": {}, "half_ppr": {}}
    for tag, res, other in (("full_ppr", full, half), ("half_ppr", half, None)):
        summ = {pos: summarise_position(res, pos) for pos in POSITIONS}
        effs = {pos: efficiency_summary(res, other, pos) for pos in POSITIONS}
        verd = {pos: verdict_for(summ[pos], effs[pos]) for pos in POSITIONS}
        ov = mech.overall(verd["RB"]["verdict"], verd["WR"]["verdict"])
        ant = [
            summ[p]["shares"]["anticipated_share"]["ratio"]
            for p in PRIMARY_POSITIONS
            if summ[p]["shares"]["anticipated_share"]
        ]
        base = ov.split(" (")[0]
        largest = None
        if base == "MIXED":
            cand = {}
            for p in PRIMARY_POSITIONS:
                for comp in verd[p]["supported"]:
                    cand[comp] = max(cand.get(comp, 0.0), verd[p]["component_shares"][comp])
            largest = max(sorted(cand), key=lambda c: cand[c]) if cand else None
        kinds = sorted(
            {verd[p]["durable_kind"] for p in PRIMARY_POSITIONS if verd[p]["durable_kind"]}
        )
        fstore = res["flex"]["store"]
        flex = {
            b: w8.compare(
                fstore,
                f"FLEX|{b}",
                ZERO,
                [f"{p}@{k}" for k in FLEX_DEPTHS for p in ("G", "G_F", "G_S", "G_C")],
            )
            for b in ("ECR", "AD", "OO")
            if f"FLEX|{b}" in fstore
        }
        flex_periods = {
            name: {
                b: w8.compare(
                    _subset(fstore, _period_keep(res["week_of"], name)),
                    f"FLEX|{b}",
                    ZERO,
                    [f"G@{K}", f"G_S@{K}", f"G_C@{K}"],
                )
                for b in ("ECR", "AD")
                if f"FLEX|{b}" in fstore
            }
            for name, _lo, _hi in mech.PERIODS
        }
        flex["closure_S"] = w8.ratio_ci(
            w8._series(fstore, "FLEX|AD", f"G_S@{K}"), w8._series(fstore, "FLEX|ECR", f"G_S@{K}")
        )
        out[tag] = {
            "n_weeks": len(res["week_of"]),
            "identity_max_residual": res["identity"],
            "summaries": summ,
            "efficiency": effs,
            "verdicts": verd,
            "overall": ov,
            "recommendation": mech.recommendation(
                ov,
                any(verd[p]["weekly_not_measurable"] for p in PRIMARY_POSITIONS),
                statistics.fmean(ant) if ant else None,
                largest,
                " and ".join(kinds) or None,
            ),
            "flex": flex,
            "flex_periods": flex_periods,
            "decomp_cells": {k: v for k, v in res["store8"].items() if k.endswith("|DECOMP")},
            "store": res["store"],
        }
    cf = w8.counterfactual_cells(con, full["cells"], trained[ORACLE_ARM], 1.0)
    cf.update(full["flex"]["counterfactual_cells"])
    comps = []
    for pos in (*POSITIONS, "FLEX"):
        comps += [
            (f"{pos}|{ORACLE_ARM}", f"{pos}|CF_A"),
            (f"{pos}|ECR", f"{pos}|CF_A"),
            (f"{pos}|ECR", f"{pos}|{ORACLE_ARM}"),
        ]
    out["full_ppr"]["counterfactual"] = summarise(cf, comps)["paired"]
    out["full_ppr"]["player_level"] = player_level(con, full, panel, dur, events)
    out["provenance"] = {
        "durable_features": list(mech.DURABLE_FEATURES),
        "arms": {k: v.by_position for k, v in trained.items()},
        "preseason": {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in pre.items() if len(k) == 3},
        "preseason_counts": {f"{k[0]}|{k[1]}": len(v) for k, v in pre.items() if len(k) == 2},
        "class_a_timestamps": len(ev_audit["class_a_timestamps"]),
        "class_a_violations": sum(
            1 for r in ev_audit["class_a_timestamps"] if not r["ts"][:10] < r["cutoff"]
        ),
        "periods": [list(p) for p in mech.PERIODS],
        "sources": sources,
    }

    print("[7/7] writing ...")
    for pos in (*POSITIONS,):
        v = out["full_ppr"]["verdicts"][pos]
        print(
            f"  {pos}: {v['verdict']}  durable={v['durable_kind']}  weekly={v['weekly']['status']}"
            f"  efficiency={v['efficiency']['supported']}  (half: {out['half_ppr']['verdicts'][pos]['verdict']})"
        )
    print(f"  overall: {out['full_ppr']['overall']}  |  {out['full_ppr']['recommendation']}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
