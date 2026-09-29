"""W12 --- can verified pre-Friday information tell a real RB breakout from a blip, and can Alpha use it?

Runs exactly `docs/weekly/W12_PREREGISTRATION.md`. **Research only.** The only Class A source is the
NFL injury report (nflverse `injuries`, 2015-2024, last-modified timestamps; see
`docs/weekly/W12_DATA_AUDIT.md`). ECR is a benchmark only, never a feature.

  A  CURRENT ALPHA          production's stored predictions
  B  W10                    history (exactly W10's model)
  C  W11                    history + role (exactly W11's model)
  D  W12                    C + the five Class A injury-report features
  N  NULL                   C + the five features permuted within (season, week, position)
  D-tm / D-own              attribution ablations
  E  EXPLORATORY (Class B)  D + the current-week nflverse depth chart; never a verdict input

    uv run python scripts/research/w12_timestamped.py --out reports/weekly/w12_results.json
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
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import benchmark, topboard  # noqa: E402
from alpha_squad.evaluation.weekly import historical as hist  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.evaluation.weekly import rolechange as rc  # noqa: E402
from alpha_squad.evaluation.weekly import timestamped as ts  # noqa: E402
from alpha_squad.evaluation.weekly.metrics import evaluate_cell  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from alpha_squad.identity.canonical import reader_expr  # noqa: E402
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
KEYS = ["player_id", "season", "week"]
PRIMARY_SEASONS = (2021, 2022, 2023, 2024)
ARM_B = w11m.ARM_B
ARM_C = "ALPHA_PLUS_HISTORY_ROLE"  # W11's arm, exactly
ARM_D = "ALPHA_PLUS_TIMESTAMPED"
ARM_N = "ALPHA_PLUS_TIMESTAMPED_NULL"
ARM_E = "EXPLORATORY_CLASS_B_DEPTH"
ABLATIONS = {
    "D_minus_teammate": ts.CATEGORIES["own"],
    "D_minus_own": ts.CATEGORIES["teammate"],
}
MODEL_ARMS = (ARM_B, ARM_C, ARM_D, ARM_N, *ABLATIONS, ARM_E)
GUARD_POSITIONAL = ("capture@5", "capture@10", "capture@20", "capture@50", "spearman", "pairwise")
GUARD_FLEX = ("capture@10", "capture@25", "spearman", "pairwise")
ROBUST_METRICS = ("capture@5", "capture@10", "capture@20", "spearman")
POS_INDEX = {"RB": 1, "WR": 2, "TE": 3}
VAC_GROUPS = ("VACANCY", "NO_VACANCY", "UNKNOWN")
ZERO = w8.ZERO
_put = w8._put
_gate = w8._gate


# ---------------------------------------------------------------------------------------
# Cutoffs and the Class A injury-report table
# ---------------------------------------------------------------------------------------


def cutoff_fridays(con, snapshots) -> dict[tuple[int, int], dt.date]:
    """(season, week) -> the Friday before the week's first Sunday game, for every REG week."""
    firsts: dict[tuple[int, int], dt.date] = {}
    for season, week, d in con.execute(
        "SELECT season, week, game_date FROM games WHERE game_type = 'REG'"
    ).fetchall():
        d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10])
        if d.weekday() == 6:
            k = (int(season), int(week))
            firsts[k] = min(firsts.get(k, d), d)
    out = {k: ts.friday_before(v) for k, v in firsts.items()}
    for s in snapshots:
        f = out[(s.season, s.week)]
        _gate(
            f == s.scrape_date
            or (s.scrape_date.weekday() == 5 and f == s.scrape_date - dt.timedelta(1)),
            f"{s.season}-{s.week}: cutoff Friday {f} vs snapshot {s.scrape_date}",
        )
    return out


def injury_rows(con) -> tuple[dict, dict]:
    """(season, week, team) -> report rows, for every season whose file carries `date_modified`.
    Returns the rows and a provenance/coverage record."""
    gsis = dict(
        con.execute(
            "SELECT id_value, player_id FROM player_id_map WHERE id_type = 'gsis_id'"
        ).fetchall()
    )
    reg = con.execute(
        "SELECT params_json, local_path, sha256, columns_json FROM snapshot_registry "
        "WHERE source = 'nflverse' AND dataset = 'injuries' ORDER BY captured_at"
    ).fetchall()
    latest: dict[int, tuple[str, str, list]] = {}
    for params, path, sha, cols in reg:
        latest[int(json.loads(params)["season"])] = (path, sha, json.loads(cols))
    out: dict[tuple[int, int, str], list[dict]] = {}
    prov = {"seasons": {}, "unmapped": 0, "rows": 0}
    for season in sorted(latest):
        path, sha, cols = latest[season]
        if "date_modified" not in cols:
            prov["seasons"][season] = {"sha256": sha, "used": False, "reason": "no date_modified"}
            continue
        prov["seasons"][season] = {"sha256": sha, "used": True}
        for week, team, gid, pos, status, practice, mod in con.execute(
            "SELECT CAST(week AS INTEGER), team, gsis_id, position, report_status, "
            f"practice_status, date_modified FROM {reader_expr(path)} "
            "WHERE game_type = 'REG' ORDER BY week, team, gsis_id, date_modified"
        ).fetchall():
            pid = gsis.get(gid)
            prov["rows"] += 1
            prov["unmapped"] += int(pid is None)
            out.setdefault((season, int(week), ts.team_code(team)), []).append(
                {
                    "player_id": pid,
                    "position": pos,
                    "status": status,
                    "practice": practice,
                    "modified": mod,
                }
            )
    return out, prov


def injury_table(con, panel: pd.DataFrame, fridays: dict, rows: dict, strict: bool) -> pd.DataFrame:
    """The five §4 features for every panel key (missing where no Class A report exists)."""
    games: dict[tuple[str, int], list[tuple[int, float]]] = {}
    for pid, season, week, car, tgt in con.execute(
        "SELECT player_id, season, week, carries, targets FROM player_week_stats"
    ).fetchall():
        games.setdefault((pid, int(season)), []).append(
            (int(week), float(car or 0) + float(tgt or 0))
        )
    team_weeks: dict[tuple[int, str], list[int]] = {}
    for season, week, home, away in con.execute(
        "SELECT season, week, home_team, away_team FROM games WHERE game_type = 'REG'"
    ).fetchall():
        for t in (home, away):
            team_weeks.setdefault((int(season), t), []).append(int(week))
    appeared = {(pid, s, w) for (pid, s), g in games.items() for w, _t in g}
    cache: dict = {}
    recs = []
    for pid, season, week, team, pos in zip(
        panel.player_id,
        panel.season.astype(int),
        panel.week.astype(int),
        panel.team,
        panel.position,
        strict=True,
    ):
        rec = {"player_id": pid, "season": season, "week": week}
        team_rows = rows.get((season, week, team))
        friday = fridays.get((season, week))
        if team_rows is None or friday is None:
            recs.append(rec | {f: None for f in ts.FEATURES})
            continue
        key = (season, week, team)
        if key not in cache:
            prev = [w for w in sorted(team_weeks.get((season, team), [])) if w < week]
            last = prev[-1] if prev else None
            tpg, missed = {}, set()
            for r in team_rows:
                j = r["player_id"]
                if j is None:
                    continue
                tpg[j] = ts.touches_per_game(games.get((j, season), []), week)
                played = any(w < week for w, _t in games.get((j, season), []))
                if played and last is not None and (j, season, last) not in appeared:
                    missed.add(j)
            cache[key] = (tpg, missed)
        tpg, missed = cache[key]
        k = ts.cutoff_instant(friday, strict=strict)
        recs.append(rec | ts.features(pid, pos, team_rows, k, tpg, missed))
    frame = pd.DataFrame(recs)
    for f in ts.FEATURES:
        frame[f] = frame[f].astype(float)
    return frame


def permuted(panel: pd.DataFrame, inj: pd.DataFrame) -> pd.DataFrame:
    """The null: the five features shuffled across players within (season, week, position)."""
    frame = panel[[*KEYS, "position"]].merge(inj, on=KEYS, how="left", validate="one_to_one")
    parts = []
    for (season, week, pos), block in frame.groupby(["season", "week", "position"], sort=True):
        block = block.sort_values("player_id").reset_index(drop=True)
        perm = list(range(len(block)))
        seed = 5_000_000 + int(season) * 1_000 + int(week) * 10 + POS_INDEX.get(pos, 0)
        random.Random(seed).shuffle(perm)
        feats = block[list(ts.FEATURES)].iloc[perm].reset_index(drop=True)
        parts.append(pd.concat([block[KEYS], feats], axis=1))
    return pd.concat(parts, ignore_index=True)[[*KEYS, *ts.FEATURES]]


def depth_now(con, panel: pd.DataFrame) -> pd.DataFrame:
    """CLASS B, exploratory only: the current-week nflverse depth chart (2015-2024)."""
    d = con.execute(
        "SELECT player_id, season, week, min(depth_team) AS depth_now FROM _depth GROUP BY 1, 2, 3"
    ).fetchdf()
    out = panel[KEYS].merge(d, on=KEYS, how="left", validate="one_to_one")
    out["depth_now"] = out["depth_now"].astype(float)
    return out


def trainings(con, panel, dur, roles, inj, seasons) -> dict:
    cols_c = [*mech.DURABLE_FEATURES, *rc.ROLE_FEATURES]
    feats = list(ts.FEATURES)
    dp = w9.durable_panel(panel, dur, shuffle=False)
    rp = w11m.role_panel(panel, roles, shuffle=False)
    frame_c = dp.merge(rp, on=KEYS, how="left", validate="one_to_one")
    frame_d = frame_c.merge(inj[[*KEYS, *feats]], on=KEYS, how="left", validate="one_to_one")
    frame_n = frame_c.merge(permuted(panel, inj), on=KEYS, how="left", validate="one_to_one")
    frame_e = frame_d.merge(depth_now(con, panel), on=KEYS, how="left", validate="one_to_one")
    out = {
        ARM_B: w11m.train_b(con, panel, dur, seasons),
        ARM_C: arms_mod.train_with_extra_features(con, frame_c, cols_c, arm=ARM_C, seasons=seasons),
        ARM_D: arms_mod.train_with_extra_features(
            con, frame_d, cols_c + feats, arm=ARM_D, seasons=seasons
        ),
        ARM_N: arms_mod.train_with_extra_features(
            con, frame_n, cols_c + feats, arm=ARM_N, seasons=seasons
        ),
        ARM_E: arms_mod.train_with_extra_features(
            con, frame_e, cols_c + feats + ["depth_now"], arm=ARM_E, seasons=seasons
        ),
    }
    for name, keep in ABLATIONS.items():
        cols = cols_c + list(keep)
        out[name] = arms_mod.train_with_extra_features(
            con, frame_d[[*KEYS, *cols]], cols, arm=name, seasons=seasons
        )
    return out


# ---------------------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------------------


def _tally(q: dict, tag: str, flag: bool, hit: bool) -> None:
    q[f"n_{tag}_{int(flag)}"] = q.get(f"n_{tag}_{int(flag)}", 0.0) + 1.0
    q[f"y_{tag}_{int(flag)}"] = q.get(f"y_{tag}_{int(flag)}", 0.0) + float(hit)


def _vac_tag(f: dict | None) -> str:
    v = ts.vacancy(f or {})
    return "UNKNOWN" if v is None else ("VACANCY" if v else "NO_VACANCY")


def analyse(con, snapshots, fmt, panel, fc, fc_opp, trained, roles, inj, inj_strict, dur, qa: bool):
    ppr = fmt.points_per_reception
    idx = {
        (r.player_id, int(r.season), int(r.week)): i
        for i, r in zip(panel.index, panel.itertuples(index=False), strict=True)
    }
    rl = {(r["player_id"], int(r["season"]), int(r["week"])): r for r in roles.to_dict("records")}
    fl = {(r["player_id"], int(r["season"]), int(r["week"])): r for r in inj.to_dict("records")}
    fs = {
        (r["player_id"], int(r["season"]), int(r["week"])): r for r in inj_strict.to_dict("records")
    }
    dl = {(r["player_id"], int(r["season"])): r for r in dur.to_dict("records")}
    cells = w8.collect(con, universes(con, snapshots, fmt), panel, fc, fc_opp, ppr)
    m: dict = {}
    ex: dict = {}
    qa_store: dict = {}
    week_of: dict[str, int] = {}
    for (key, pos), cell in sorted(cells.items()):
        snap, rows, common = cell["snap"], cell["rows"], cell["common"]
        week_of[key] = snap.week
        ids = sorted(rows)
        pts = {p: rows[p].pts for p in ids}
        boards = {"CF_A": cell["board_a"], "ECR": common}
        for arm in MODEL_ARMS:
            preds = trained[arm].for_week(snap.season, snap.week, pos)
            boards[arm] = alpha_mod.alpha_board(common, preds, tiebreak=cell["rank_a"])[0]
        orders = {}
        for name, board in boards.items():
            _gate({r.player_id for r in board.rows} == set(ids), f"{key} {pos} {name} universe")
            orders[name] = w8._order(board)
            pr, rlz = board.ranks_and_points()
            row = evaluate_cell(pr, rlz, depths=DEPTHS).as_row()
            row.update(hist.miss_counts(orders[name], pts))
            m.setdefault(f"{pos}|{name}", {})[key] = row
        if pos != "RB":
            continue
        real = hist.realized_ranks(pts)
        cls = {p: rl[(p, snap.season, snap.week)]["cls_PRIMARY"] for p in ids}
        risers = [p for p in ids if cls[p] == "ROLE_UP"]
        best = math.fsum(sorted(pts.values(), reverse=True)[:K])
        for name in ("CF_A", ARM_B, ARM_C, ARM_D, ARM_E):
            rank = {p: n for n, p in enumerate(orders[name], start=1)}
            _put(
                m,
                f"RB|RISER|{name}",
                key,
                "missed_breakouts",
                float(sum(1 for p in risers if real[p] <= 5 and rank[p] > 24)),
            )
            _put(
                m,
                f"RB|RISER|{name}",
                key,
                "false_top10",
                float(sum(1 for p in risers if rank[p] <= K and real[p] > 24)),
            )
            _put(
                m,
                f"RB|RISER|{name}",
                key,
                "riser_regret",
                (
                    math.fsum(pts[p] for p in risers if real[p] <= K and rank[p] > K) / best
                    if best > 0
                    else 0.0
                ),
            )
        top_c, top_d = set(orders[ARM_C][:K]), set(orders[ARM_D][:K])
        _put(ex, "RB|OVERLAP", key, "top10_overlap_D_C", len(top_c & top_d) / K)
        vac_tags = {p: _vac_tag(fl.get((p, snap.season, snap.week))) for p in ids}
        for tag, grp, groups in (
            ("ATTR_DC_CLASS", cls, rc.CLASSES),
            ("ATTR_DC_VAC", vac_tags, VAC_GROUPS),
        ):
            attr = mech.attribute_piece(orders[ARM_D], orders[ARM_C], rows, K, grp, "G")
            d = adv.decompose_gap(orders[ARM_D], orders[ARM_C], rows, K)
            if attr is not None:
                _gate(abs(sum(attr.values()) - d["G"]) < 1e-9, f"{key} {tag}: attribution")
                for g in groups:
                    _put(ex, f"RB|{tag}", key, g, attr.get(g, 0.0))
        if not qa or snap.season not in PRIMARY_SEASONS:
            continue
        # Question A: risers with an observable report, and the whole RB universe for context
        rank_c = {p: n for n, p in enumerate(orders[ARM_C], start=1)}
        q: dict[str, float] = {}

        for p in ids:
            f = fl.get((p, snap.season, snap.week)) or {}
            vac = ts.vacancy(f)
            if vac is None:
                continue
            brk = real[p] <= K
            _tally(q, "U", vac, brk)
            if cls[p] != "ROLE_UP":
                continue
            _tally(q, "QA1", vac, brk)
            q["breakouts"] = q.get("breakouts", 0.0) + float(brk)
            q["risers"] = q.get("risers", 0.0) + 1.0
            q["vacancy"] = q.get("vacancy", 0.0) + float(vac)
            q["top5"] = q.get("top5", 0.0) + float(real[p] <= 5)
            if rank_c[p] > K:
                _tally(q, "QA2", vac, brk)
            prior = w9._num((dl.get((p, snap.season)) or {}).get("prior_opp_pg"))
            y = w9._num(panel.at[idx[(p, snap.season, snap.week)], "y_opp"])
            if prior is not None and y is not None:
                _tally(q, "QA3", vac, (y - prior) >= rc.THRESHOLDS["PRIMARY"][0])
            own = w9._num(f.get("own_status"))
            if own is not None:
                _tally(q, "QA4", own >= 1.0, brk)
            ret = w9._num(f.get("tm_ret_opp"))
            if ret is not None:
                _tally(q, "QA5", ret >= ts.VACANCY_TOUCHES, brk)
            vs = ts.vacancy(fs.get((p, snap.season, snap.week)) or {})
            if vs is not None:
                _tally(q, "QAS", vs, brk)
        for mt, v in sorted(q.items()):
            _put(qa_store, "QA", key, mt, v)
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
    return {"m": m, "ex": ex, "qa": qa_store, "week_of": week_of, "cells": cells}


def depth_question(con, snapshots, fridays, roles, full_cells) -> dict:
    """QA-D (exploratory, 2025, Class A ESPN captures): BREAKOUT for risers listed RB1."""
    import json as _json

    reg = [
        (p, lp)
        for p, lp in con.execute(
            "SELECT params_json, local_path FROM snapshot_registry "
            "WHERE source = 'nflverse' AND dataset = 'depth_charts'"
        ).fetchall()
        if str(_json.loads(p)["season"]) == "2025"
    ]
    if not reg:
        return {"available": False}
    con.execute(f"CREATE OR REPLACE TEMP VIEW _d25x AS SELECT * FROM {reader_expr(reg[-1][1])}")
    caps = sorted(r[0] for r in con.execute("SELECT DISTINCT dt FROM _d25x").fetchall())
    gsis = dict(
        con.execute(
            "SELECT id_value, player_id FROM player_id_map WHERE id_type = 'gsis_id'"
        ).fetchall()
    )
    rl = {
        (r["player_id"], int(r["season"]), int(r["week"])): r["cls_PRIMARY"]
        for r in roles.to_dict("records")
    }
    q: dict = {}
    promoted = 0
    for s in snapshots:
        if s.season != 2025 or (f"2025-{s.week}", "RB") not in full_cells:
            continue
        cut = ts.cutoff_instant(fridays[(2025, s.week)])
        before = [c for c in caps if dt.datetime.fromisoformat(c.replace("Z", "+00:00")) <= cut]
        prev = [
            c
            for c in caps
            if dt.datetime.fromisoformat(c.replace("Z", "+00:00")) <= cut - dt.timedelta(days=7)
        ]
        if not before or not prev:
            continue
        ranks = {}
        for c in (before[-1], prev[-1]):
            ranks[c] = {
                gsis.get(g): r
                for g, r in con.execute(
                    "SELECT gsis_id, min(pos_rank) FROM _d25x WHERE dt = ? AND pos_abb = 'RB' GROUP BY 1",
                    [c],
                ).fetchall()
            }
        cell = full_cells[(f"2025-{s.week}", "RB")]
        pts = {p: r.pts for p, r in cell["rows"].items()}
        real = hist.realized_ranks(pts)
        for p in sorted(pts):
            if rl.get((p, 2025, s.week)) != "ROLE_UP":
                continue
            now, was = ranks[before[-1]].get(p), ranks[prev[-1]].get(p)
            promoted += int(now is not None and was is not None and now < was)
            flag = now == 1
            k = f"2025-{s.week}"
            q.setdefault(k, {})
            q[k][f"n_{int(flag)}"] = q[k].get(f"n_{int(flag)}", 0.0) + 1.0
            q[k][f"y_{int(flag)}"] = q[k].get(f"y_{int(flag)}", 0.0) + float(real[p] <= K)
    ser = {t: {k: r.get(t, 0.0) for k, r in q.items()} for t in ("n_1", "y_1", "n_0", "y_0")}
    return {
        "available": True,
        "weeks": len(q),
        "promotions": promoted,
        "rb1_vs_not": rc.ratio_diff_ci(ser["y_1"], ser["n_1"], ser["y_0"], ser["n_0"]),
    }


def _subset(store: dict, keep) -> dict:
    return {s: {k: r for k, r in w.items() if keep(k)} for s, w in store.items()}


def _season(k: str) -> int:
    return int(k.split("-")[0])


def summaries(res: dict, window: tuple[int, ...]) -> dict:
    keep = lambda k: _season(k) in window  # noqa: E731
    m, week_of = _subset(res["m"], keep), res["week_of"]
    ex = _subset(res["ex"], keep)
    pos_flex = (*POSITIONS, "FLEX")
    pairs = (
        (ARM_D, ARM_C),
        (ARM_C, ARM_B),
        (ARM_B, "CF_A"),
        (ARM_C, "CF_A"),
        (ARM_D, "CF_A"),
        (ARM_D, ARM_N),
        (ARM_N, ARM_C),
        (ARM_D, "D_minus_teammate"),
        (ARM_D, "D_minus_own"),
        (ARM_E, ARM_D),
        (ARM_E, ARM_C),
        ("ECR", ARM_D),
        ("ECR", ARM_C),
    )
    comps = [(f"{p}|{a}", f"{p}|{b}") for p in pos_flex for a, b in pairs]
    out: dict = {"n_weeks": len({k for w in m.values() for k in w}), "all": summarise(m, comps)}
    primary = [(f"{p}|{ARM_D}", f"{p}|{ARM_C}") for p in pos_flex] + [
        (f"{p}|{ARM_N}", f"{p}|{ARM_C}") for p in pos_flex
    ]
    out["periods"] = {
        name: summarise(_subset(m, lambda k, n=name: mech.period_of(week_of[k]) == n), primary)[
            "paired"
        ]
        for name, _lo, _hi in mech.PERIODS
    }
    out["per_season"] = {
        f"{p}|{mt}": {
            s: r
            for s, r in per_season(m, f"{p}|{ARM_D}", f"{p}|{ARM_C}", mt).items()
            if int(s) in window
        }
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["loso"] = {
        f"{p}|{mt}": {
            s: r
            for s, r in leave_one_season_out(m, f"{p}|{ARM_D}", f"{p}|{ARM_C}", mt).items()
            if int(s.split("_")[1]) in window
        }
        for p in pos_flex
        for mt in ROBUST_METRICS
    }
    out["null_per_season"] = per_season(m, f"RB|{ARM_D}", f"RB|{ARM_N}", "capture@10")
    riser_metrics = ["missed_breakouts", "false_top10", "riser_regret"]
    out["risers"] = {
        f"{a}_vs_{b}": w8.compare(m, f"RB|RISER|{a}", f"RB|RISER|{b}", riser_metrics)
        for a, b in ((ARM_D, ARM_C), (ARM_C, ARM_B), (ARM_B, "CF_A"), (ARM_E, ARM_C))
    }
    out["riser_levels"] = {
        b: {
            mt: statistics.fmean(r[mt] for r in m[f"RB|RISER|{b}"].values()) for mt in riser_metrics
        }
        for b in ("CF_A", ARM_B, ARM_C, ARM_D, ARM_E)
        if m.get(f"RB|RISER|{b}")
    }
    zero: dict = {}
    for w in ex.values():
        for k, r in w.items():
            zero.setdefault(k, {}).update({mt: 0.0 for mt in r})
    ex[ZERO] = zero
    out["attribution_class"] = w8.compare(ex, "RB|ATTR_DC_CLASS", ZERO, list(rc.CLASSES))
    out["attribution_vacancy"] = w8.compare(ex, "RB|ATTR_DC_VAC", ZERO, list(VAC_GROUPS))
    ov = [r["top10_overlap_D_C"] for r in ex.get("RB|OVERLAP", {}).values()]
    out["top10_overlap_D_C"] = statistics.fmean(ov) if ov else None
    return out


def question_a(res: dict) -> dict:
    qa = res["qa"].get("QA", {})

    def s(mt):
        return {k: r.get(mt, 0.0) for k, r in qa.items()}

    out = {
        tag: rc.ratio_diff_ci(s(f"y_{tag}_1"), s(f"n_{tag}_1"), s(f"y_{tag}_0"), s(f"n_{tag}_0"))
        for tag in ("QA1", "QA2", "QA3", "QA4", "QA5", "QAS", "U")
    }
    out["coverage"] = {
        "risers": int(math.fsum(s("risers").values())),
        "vacancy": int(math.fsum(s("vacancy").values())),
        "breakouts": int(math.fsum(s("breakouts").values())),
        "top5": int(math.fsum(s("top5").values())),
        "vacancy_weeks": sum(1 for v in s("vacancy").values() if v > 0),
    }
    return out


def verdict_inputs(summ: dict, qa: dict) -> dict:
    paired = summ["all"]["paired"]

    def row(p, mt, a=ARM_D, b=ARM_C):
        return paired.get(f"{p}|{a}_vs_{p}|{b}", {}).get(mt)

    guard = {f"{p}|{mt}": row(p, mt) for p in POSITIONS for mt in GUARD_POSITIONAL}
    guard.update({f"FLEX|{mt}": row("FLEX", mt) for mt in GUARD_FLEX})
    return {
        "coverage": qa["coverage"],
        "qa1": qa["QA1"],
        "rb": row("RB", "capture@10"),
        "rb_null": row("RB", "capture@10", ARM_D, ARM_N),
        "rb_seasons": [r["mean_diff"] for r in summ["per_season"]["RB|capture@10"].values()],
        "rb_loso": list(summ["loso"]["RB|capture@10"].values()),
        "guard": guard,
        "wr": row("WR", "capture@10"),
        "wr_vs_a": row("WR", "capture@10", ARM_D, "CF_A"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w12_results.json")
    ap.add_argument("--seasons", default=",".join(str(s) for s in w11m.DEFAULT_SEASONS))
    args = ap.parse_args()
    seasons = tuple(int(s) for s in args.seasons.split(","))
    con = duckdb.connect(args.db, read_only=True)
    sources = w11m.wire(con, seasons)

    print(f"[1/6] panel, forecasts, durable and role tables (seasons {seasons}) ...")
    panel, snapshots, fc, fc_half, fc_opp, dur, roles = w11m.inputs(con, seasons)
    print("[2/6] the Class A injury-report table (primary and strict cutoffs) ...")
    fridays = cutoff_fridays(con, snapshots)
    rows, inj_prov = injury_rows(con)
    inj = injury_table(con, panel, fridays, rows, strict=False)
    inj_strict = injury_table(con, panel, fridays, rows, strict=True)
    print("[3/6] the declared trainings ...")
    trained = trainings(con, panel, dur, roles, inj, seasons)
    print("[4/6] Full PPR and Half-PPR ...")
    full = analyse(
        con, snapshots, FULL_PPR, panel, fc, fc_opp, trained, roles, inj, inj_strict, dur, qa=True
    )
    half = analyse(
        con,
        snapshots,
        HALF_PPR,
        panel,
        fc_half,
        fc_opp,
        trained,
        roles,
        inj,
        inj_strict,
        dur,
        qa=False,
    )
    print("[5/6] summaries, Question A, verdict ...")
    qa = question_a(full)
    out: dict = {
        "question_a": qa,
        "question_a_depth_2025": depth_question(con, snapshots, fridays, roles, full["cells"]),
    }
    for tag, res in (("full_ppr", full), ("half_ppr", half)):
        prim = summaries(res, PRIMARY_SEASONS)
        allw = summaries(res, seasons)
        vin = verdict_inputs(prim, qa)
        out[tag] = {
            "primary_2021_2024": prim,
            "all_weeks": allw,
            "verdict_inputs": vin,
            "verdict": ts.verdict(vin),
            "cells": res["m"],
        }
    cov = inj[inj.season.isin(PRIMARY_SEASONS)]
    out["provenance"] = {
        "seasons": list(seasons),
        "primary_seasons": list(PRIMARY_SEASONS),
        "features": list(ts.FEATURES),
        "injury_source": inj_prov,
        "feature_coverage_2021_2024": {f: float(cov[f].notna().mean()) for f in ts.FEATURES},
        "feature_coverage_2025": {
            f: float(inj[inj.season == 2025][f].notna().mean()) for f in ts.FEATURES
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
