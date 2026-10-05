"""W14 --- does W10's historical-player-knowledge gain hold on untouched 2026 weeks?

Runs exactly `docs/weekly/W14_PREREGISTRATION.md`. **Research only. Validation, not improvement.**
W10 is not re-implemented: this runner imports `w10_historical` and calls its own `trainings`,
`analyse`, `summaries`, `cliffs` and `calibration` on the eligible 2026 weeks. It adds only the
week-eligibility rule (§4), regret@10 / top-10 overlap from W10's own board calls, and the §6
statistics and §7 decision. ECR is a benchmark only.

  A  CURRENT ALPHA   production's stored 2026 weekly predictions (`train established`, A1)
  B  W10             ALPHA_PLUS_HISTORICAL, trained on [2015, 2025]

    uv run python scripts/research/w14_2026_validation.py --out reports/weekly/w14_results.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.evaluation.weekly import advantage as adv  # noqa: E402
from alpha_squad.evaluation.weekly import alpha as alpha_mod  # noqa: E402
from alpha_squad.evaluation.weekly import audit, benchmark, context  # noqa: E402
from alpha_squad.evaluation.weekly import holdout as ho  # noqa: E402
from alpha_squad.evaluation.weekly import opportunity as op  # noqa: E402
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR  # noqa: E402
from alpha_squad.identity.canonical import reader_expr, require_snapshot  # noqa: E402
from scripts.research import w8_ecr_advantage as w8  # noqa: E402
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w10_historical as w10  # noqa: E402
from scripts.research.w6_upper_outcome import flex_cell  # noqa: E402

SEASON = 2026
SEASONS = (SEASON,)
WEEKS = range(1, 18)
POSITIONS = w10.POSITIONS
ARM_B = w10.ARM_B
ARM_N = w10.ARM_N
K = 10
ET = ZoneInfo("America/New_York")
UTC = dt.UTC
REPORT_METRICS = (
    "capture@5",
    "capture@10",
    "capture@20",
    "capture@25",
    "capture@50",
    "spearman",
    "pairwise",
    "precision@10",
)
EXTRA_METRICS = ("regret@10", "overlap_B_A")
KEY_CELLS = (("WR", "capture@10"), ("WR", "capture@5"), ("FLEX", "capture@10"))
_gate = w8._gate


# ---------------------------------------------------------------------------------------
# §4 eligibility
# ---------------------------------------------------------------------------------------


def _captured(con) -> dt.datetime:
    """The earliest capture time of the 2026 outcome snapshots the evaluation reads (UTC)."""
    caps = [
        require_snapshot(con, "nflverse", ds, season=SEASON)["captured_at"]
        for ds in ("stats_player_week", "stats_team_week", "pbp")
    ]
    # the registry stores naive UTC (`sources.base.utcnow`)
    return min(c if c.tzinfo else c.replace(tzinfo=UTC) for c in caps)


def eligibility(con, snapshots, schedule_path: str) -> tuple[list, list[dict], dict]:
    """The §4 table for weeks 1-17 and the eligible canonical snapshots."""
    sched: dict[int, list[tuple[str, str, dt.datetime]]] = {}
    for week, day, time, home, away in con.execute(
        "SELECT CAST(week AS INTEGER), gameday, gametime, home_team, away_team "
        f"FROM {reader_expr(schedule_path)} WHERE season = ? AND game_type = 'REG' "
        "ORDER BY 1, 2, 3, 4",
        [SEASON],
    ).fetchall():
        d = dt.date.fromisoformat(str(day)[:10])
        try:
            hh, mm = (int(x) for x in str(time).split(":")[:2])
        except ValueError:  # an unset kickoff: the latest possible, the conservative direction
            hh, mm = 23, 59
        kick = dt.datetime.combine(d, dt.time(hh, mm), tzinfo=ET).astimezone(UTC)
        sched.setdefault(week, []).append((home, away, kick))
    played: dict[int, set] = {}
    for week, home, away in con.execute(
        "SELECT week, home_team, away_team FROM games WHERE season = ? AND game_type = 'REG'",
        [SEASON],
    ).fetchall():
        played.setdefault(int(week), set()).add((home, away))
    stats: dict[int, set] = {}
    for week, team in con.execute(
        "SELECT DISTINCT week, team FROM player_week_stats WHERE season = ?", [SEASON]
    ).fetchall():
        stats.setdefault(int(week), set()).add(team)
    captured = _captured(con)
    board = {s.week: s for s in snapshots if s.season == SEASON}
    table, keep = [], []
    for week in WEEKS:
        games = sched.get(week, [])
        scheduled = {(h, a) for h, a, _k in games}
        kicks = [k for _h, _a, k in games]
        last = max(kicks) if kicks else None
        ok, why = ho.week_eligibility(
            scheduled, played.get(week, set()), stats.get(week, set()), last, captured
        )
        snap = board.get(week)
        if snap is None:
            ok = False
            why = "no canonical Friday board" + ("" if not kicks else f" ({why})")
        if ok:
            status = "EVALUATED"
            keep.append(snap)
        elif kicks and min(kicks) > captured:
            status = "NOT_YET_PLAYED"
        elif snap is None and kicks and last + ho.COMPLETE_BUFFER <= captured:
            status = "NO_BOARD"
        else:
            status = "PENDING_DATA"
        table.append(
            {
                "week": week,
                "board": str(snap.scrape_date) if snap else None,
                "scheduled_games": len(scheduled),
                "games_in_data": len(played.get(week, set()) & scheduled),
                "last_kickoff_utc": last.isoformat() if last else None,
                "eligible": ok,
                "status": status,
                "reason": why,
            }
        )
    final = all(r["status"] in ("EVALUATED", "NO_BOARD") for r in table)
    return keep, table, {"captured_utc": captured.isoformat(), "final": final}


# ---------------------------------------------------------------------------------------
# regret@10 and top-10 overlap, through W10's own board calls
# ---------------------------------------------------------------------------------------


def _top(board, k=K):
    order = w8._order(board)
    pts = {r.player_id: float(r.realized) for r in board.evaluable}
    return order[:k], pts


def extras(con, res: dict, fmt, trained) -> dict:
    """Per week: regret@10 for A, B and ECR, and B's top-10 overlap with A. Each recomputed
    board's capture@10 must equal W10's own cell (gate)."""
    store: dict = {}
    checked = 0

    def put(system, key, row):
        store.setdefault(system, {}).setdefault(key, {}).update(row)

    def score(pos, key, boards):
        nonlocal checked
        tops = {}
        for name, board in boards.items():
            top, pts = _top(board)
            best = adv.best_total(pts.values(), K)
            got = math.fsum(pts[p] for p in top)
            cap = res["m"][f"{pos}|{name}"][key]["capture@10"]
            _gate(
                best <= 0 or abs(got / best - cap) < 1e-9,
                f"{pos} {key} {name}: recomputed capture@10 differs from W10's cell",
            )
            checked += 1
            tops[name] = set(top)
            put(f"{pos}|{name}", key, {"regret@10": best - got})
        put(f"{pos}|{ARM_B}", key, {"overlap_B_A": len(tops[ARM_B] & tops["CF_A"]) / K})

    for (key, pos), cell in sorted(res["cells"].items()):
        snap = cell["snap"]
        b = alpha_mod.alpha_board(
            cell["common"],
            trained[ARM_B].for_week(snap.season, snap.week, pos),
            tiebreak=cell["rank_a"],
        )[0]
        score(pos, key, {"CF_A": cell["board_a"], ARM_B: b, "ECR": cell["common"]})
    by_week: dict[str, dict] = {}
    for (key, _pos), cell in res["cells"].items():
        w = by_week.setdefault(key, {"snap": cell["snap"], "alpha": {}})
        w["alpha"].update(cell["alpha_pred"])
    for key in sorted(by_week):
        snap, alpha_all = by_week[key]["snap"], by_week[key]["alpha"]
        commonf, boardf, _k = flex_cell(con, snap, fmt, alpha_all)
        if len(commonf.rows) < benchmark.MIN_EVALUABLE:
            continue
        uni = {r.player_id for r in boardf.rows}
        pb: dict[str, float] = {}
        for pos in POSITIONS:
            pb.update(trained[ARM_B].for_week(snap.season, snap.week, pos))
        bf = flex_cell(con, snap, fmt, pb, universe=uni)[1]
        score("FLEX", key, {"CF_A": boardf, ARM_B: bf, "ECR": commonf})
    return {"store": store, "boards_checked": checked}


# ---------------------------------------------------------------------------------------
# §6 statistics
# ---------------------------------------------------------------------------------------


def _week_order(k: str) -> tuple[int, int]:
    s, w = k.split("-")
    return int(s), int(w)


def _diffs(cells: dict, a: str, b: str, metric: str) -> tuple[list[str], list[float]]:
    av, bv = cells.get(a, {}), cells.get(b, {})
    keys = sorted(
        (k for k in set(av) & set(bv) if metric in av[k] and metric in bv[k]), key=_week_order
    )
    return keys, [av[k][metric] - bv[k][metric] for k in keys]


def paired_block(m: dict, x: dict, pairs, metrics) -> dict:
    """mean, bootstrap CI, W-L-T, Wilcoxon (W10's `w8.compare`) and the exact sign-flip p."""
    store = {s: dict(w) for s, w in m.items()}
    for s, w in x.items():
        for k, row in w.items():
            store.setdefault(s, {}).setdefault(k, {})
            store[s][k] = {**store[s][k], **row}
    out: dict = {}
    for pos in (*POSITIONS, "FLEX"):
        for a, b in pairs:
            sa, sb = f"{pos}|{a}", f"{pos}|{b}"
            if sa not in store or sb not in store:
                continue
            rows = w8.compare(store, sa, sb, list(metrics))
            for mt, row in rows.items():
                _keys, d = _diffs(store, sa, sb, mt)
                row["sign_flip"] = ho.sign_flip_p(d)
            out[f"{pos}|{a}_vs_{b}"] = rows
    return out


def weekly_table(m: dict, x: dict) -> dict:
    out: dict = {}
    for pos in (*POSITIONS, "FLEX"):
        for mt in ("capture@5", "capture@10", "capture@20", "spearman"):
            keys, d = _diffs(m, f"{pos}|{ARM_B}", f"{pos}|CF_A", mt)
            out[f"{pos}|{mt}"] = dict(zip(keys, d, strict=True))
        keys, d = _diffs(x, f"{pos}|{ARM_B}", f"{pos}|CF_A", "regret@10")
        out[f"{pos}|regret@10"] = dict(zip(keys, d, strict=True))
        ov = x.get(f"{pos}|{ARM_B}", {})
        out[f"{pos}|overlap_B_A"] = {k: ov[k]["overlap_B_A"] for k in sorted(ov, key=_week_order)}
    return out


def history(w10_res: dict, tag: str, m: dict, n: int) -> dict:
    """W10's 2021-2025 evidence beside 2026 (§6): effect, folds, seasons, first-n windows, band."""
    out: dict = {}
    summ = w10_res[tag]["summary"]
    cells = w10_res[tag]["cells"]
    for pos, mt in KEY_CELLS:
        hk, hd = _diffs(cells, f"{pos}|{ARM_B}", f"{pos}|CF_A", mt)
        k26, d26 = _diffs(m, f"{pos}|{ARM_B}", f"{pos}|CF_A", mt)
        mean26 = math.fsum(d26) / len(d26) if d26 else None
        firsts = {}
        for season in sorted({_week_order(k)[0] for k in hk}):
            sub = [d for k, d in zip(hk, hd, strict=True) if _week_order(k)[0] == season][:n]
            firsts[str(season)] = math.fsum(sub) / len(sub) if sub else None
        out[f"{pos}|{mt}"] = {
            "w10_2021_2025": summ["all"]["paired"][f"{pos}|{ARM_B}_vs_{pos}|CF_A"].get(mt),
            "w10_loso": summ["loso"].get(f"{pos}|{mt}"),
            "w10_per_season": summ["per_season"].get(f"{pos}|{mt}"),
            "w10_first_n_weeks": firsts,
            "w10_weeks": len(hd),
            "y2026_mean": mean26,
            "y2026_weeks": k26,
            "band": ho.predictive_band(hd, len(d26), mean26) if d26 else {},
        }
    return out


def _guard(paired: dict) -> dict:
    g = {}
    for pos in POSITIONS:
        for mt in w10.GUARD_POSITIONAL:
            g[f"{pos}|{mt}"] = paired.get(f"{pos}|{ARM_B}_vs_CF_A", {}).get(mt)
    for mt in w10.GUARD_FLEX:
        g[f"FLEX|{mt}"] = paired.get(f"FLEX|{ARM_B}_vs_CF_A", {}).get(mt)
    return g


def decide(paired: dict, hist: dict, n: int, final: bool, valid: bool) -> dict:
    wr = paired.get(f"WR|{ARM_B}_vs_CF_A", {})
    return ho.classify(
        {
            "valid": valid,
            "final": final,
            "n_weeks": n,
            "wr10": wr.get("capture@10"),
            "wr5": wr.get("capture@5"),
            "band": hist.get("WR|capture@10", {}).get("band"),
            "guard": _guard(paired),
        }
    )


def movers_summary(con, movers: list[dict]) -> dict:
    names = dict(con.execute("SELECT player_id, display_name FROM players").fetchall())
    agg: dict = {}
    for r in movers:
        e = agg.setdefault(
            (r["position"], r["player_id"]),
            {"in_hit": 0, "in_miss": 0, "out_hit": 0, "out_miss": 0, "cats": {}},
        )
        e[f"{r['direction'].lower()}_{'hit' if r['hit'] else 'miss'}"] += 1
        e["cats"][r["category"]] = e["cats"].get(r["category"], 0) + 1
    out: dict = {}
    for pos in POSITIONS:
        items = [(pid, e) for (p, pid), e in agg.items() if p == pos]
        out[pos] = {
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
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/w14/alpha_squad_2026.duckdb")
    ap.add_argument("--schedule", default="data/w14/schedule/manifest.json")
    ap.add_argument("--w10", default="reports/weekly/w10_results.json")
    ap.add_argument("--out", default="reports/weekly/w14_results.json")
    args = ap.parse_args()

    manifest = json.loads(Path(args.schedule).read_text())
    con = duckdb.connect(args.db, read_only=True)
    # W10's own wiring, exactly (w10_historical.main)
    for view, (source, table) in {
        "ecr": ("dynastyprocess", "fp_ecr_history"),
        "xwalk": ("dynastyprocess", "player_ids"),
    }.items():
        s = require_snapshot(con, source, table)
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM {reader_expr(s['local_path'])}"
        )
    sources = context.wire_snapshot_views(con, tuple(range(2015, SEASON + 1)))

    print("[1/6] panel, canonical boards, §4 eligibility ...")
    panel = op.build_panel(con, POSITIONS)
    snapshots = audit.week_coverage(con, SEASONS).snapshots
    eligible, table, look = eligibility(con, snapshots, manifest["path"])
    n = len(eligible)
    out: dict = {
        "look": look | {"n_eligible_weeks": n, "eligible_weeks": [s.week for s in eligible]},
        "weeks": table,
    }
    if n < ho.MIN_WEEKS_VALID:
        out["verdict"] = decide({}, {}, n, look["final"], valid=False)
        Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
        print(f"wrote {args.out} (too few eligible weeks)")
        return

    print("[2/6] forecasts and the durable table (W10, unchanged) ...")
    fc = {p: op.walk_forward(panel, p, "T_XFP", "M_NEW", SEASONS) for p in POSITIONS}
    fc_half = {p: op.walk_forward(panel, p, "T_XFP_HALF", "M_NEW", SEASONS) for p in POSITIONS}
    fc_opp = {p: op.walk_forward(panel, p, "T_OPP", "M_NEW", SEASONS) for p in POSITIONS}
    dur = w9.durable_table(con, through=SEASON)
    _gate(SEASON in {int(s) for s in dur.season.unique()}, "durable table lacks 2026")

    print("[3/6] W10's declared trainings (trained on [2015, 2025]) ...")
    trained = w10.trainings(con, panel, dur, SEASONS)

    print("[4/6] W10's analysis, Full PPR (with the cliff nulls) and Half-PPR ...")
    full = w10.analyse(con, eligible, FULL_PPR, panel, fc, fc_opp, trained, dur, with_nulls=True)
    half = w10.analyse(
        con, eligible, HALF_PPR, panel, fc_half, fc_opp, trained, dur, with_nulls=False
    )
    _gate(
        sorted({w for w in full["week_of"].values()}) == [s.week for s in eligible],
        "evaluated weeks differ from the eligible weeks",
    )

    print("[5/6] regret, overlap, statistics, history, decision ...")
    w10_res = json.loads(Path(args.w10).read_text())
    pairs = ((ARM_B, "CF_A"), ("ECR", "CF_A"), ("ECR", ARM_B), (ARM_N, "CF_A"))
    for tag, res, fmt in (("full_ppr", full, FULL_PPR), ("half_ppr", half, HALF_PPR)):
        x = extras(con, res, fmt, trained)
        paired = paired_block(res["m"], x["store"], pairs, (*REPORT_METRICS, *EXTRA_METRICS))
        summ = w10.summaries(res, (*POSITIONS, "FLEX"))
        hist = history(w10_res, tag, res["m"], n)
        block = {
            "n_weeks": len(res["week_of"]),
            "paired": paired,
            "weekly": weekly_table(res["m"], x["store"]),
            "history": hist,
            "periods": summ["periods"],
            "decision": decide(paired, hist, n, look["final"], valid=True),
            "cells": res["m"],
            "extras": x["store"],
            "boards_checked": x["boards_checked"],
            "levels": {
                s: {
                    mt: statistics.fmean(r[mt] for r in w.values() if r.get(mt) is not None)
                    for mt in REPORT_METRICS
                    if any(r.get(mt) is not None for r in w.values())
                }
                for s, w in res["m"].items()
            },
        }
        if tag == "full_ppr":
            block["mechanism"] = {
                k: summ[k]
                for k in (
                    "misses_points",
                    "misses_levels",
                    "decomposition",
                    "movement",
                    "movement_counts",
                    "quiet_star",
                )
            }
            block["mechanism"]["players"] = movers_summary(con, res["movers"])
            block["cliff"] = w10.cliffs(res)
            block["calibration"] = w10.calibration(res["calib"])
        out[tag] = block
    out["verdict"] = out["full_ppr"]["decision"]
    out["section9"] = {
        "rule": "WR capture@10 and capture@5 B - A > 0, and WR capture@10 CI excludes 0",
        "evaluable": look["final"],
        "holds": out["verdict"]["section9_holds"],
    }
    out["provenance"] = {
        "season": SEASON,
        "w10_features": list(w10.mech.DURABLE_FEATURES),
        "arms": {k: v.by_position for k, v in trained.items()},
        "schedule": manifest,
        "sources": sources,
        "snapshots_2026": {
            ds: require_snapshot(con, src, ds, **({"season": SEASON} if src == "nflverse" else {}))[
                "sha256"
            ]
            for src, ds in (
                ("nflverse", "stats_player_week"),
                ("nflverse", "stats_team_week"),
                ("nflverse", "pbp"),
                ("dynastyprocess", "fp_ecr_history"),
                ("dynastyprocess", "player_ids"),
            )
        },
        "production_2026_predictions": dict(
            con.execute(
                "SELECT position, count(*) FROM weekly_projection_snapshot "
                "WHERE season = ? AND model_name = 'ml_catboost' GROUP BY 1 ORDER BY 1",
                [SEASON],
            ).fetchall()
        ),
    }

    print("[6/6] writing ...")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
