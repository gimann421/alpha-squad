"""W5 --- why does within-position ranking collapse at the top of the RB/WR/TE boards?

Runs exactly what `docs/weekly/W5_PREREGISTRATION.md` specifies. **Builds no model, fits no
positional model, tunes nothing and never touches production.** It reads the weekly predictions
the unmodified `alpha-squad train established` path wrote, then answers the three ordered
questions the pre-registration fixed:

  P1  is there a top-of-board cliff BEYOND what overall ordering quality implies?
      -> a copula null with the board's own Spearman and no top-specific structure (§5)
  P2  how much of the remaining headroom is reachable at all from pre-game information?
      -> ORACLE_USAGE (perfect opportunity) vs ORACLE_OUTCOME (perfect foresight) (§6)
  P3  does any pre-cutoff information class explain a material share of top-board regret?
      -> the exact additive regret decomposition, by cohort and by context (§7-§9)

    uv run python scripts/research/w5_topboard_forensics.py --out reports/weekly/w5_results.json

Read-only against the database; writes one JSON.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import alpha as alpha_mod
from alpha_squad.evaluation.weekly import (
    audit,
    benchmark,
    context,
    diagnostics,
    noise,
    nulls,
    regret,
    topboard,
)
from alpha_squad.evaluation.weekly.metrics import evaluate_cell, spearman, topk_precision
from alpha_squad.evaluation.weekly.metrics import topk_points_capture as capture
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR

SEASONS = (2021, 2022, 2023, 2024, 2025)
#: RB/WR/TE are confirmatory; QB is reported for contrast and excluded from every decision rule.
CONFIRMATORY_POSITIONS = ("RB", "WR", "TE")
CONTRAST_POSITIONS = ("QB",)
ALL_POSITIONS = CONFIRMATORY_POSITIONS + CONTRAST_POSITIONS
HEADLINE = (
    "spearman",
    "kendall",
    "pairwise",
    "decisive",
    *(f"capture@{k}" for k in topboard.W5_DEPTHS),
    *(f"precision@{k}" for k in topboard.W5_DEPTHS),
)


def _null_metrics(pred_rank: list[float], real: list[float]) -> dict:
    """The subset of the frozen suite the copula null needs.

    Kendall and the two pairwise passes are O(n^2) and are skipped here on purpose: 200 draws x
    237 cells x two scoring formats would spend most of the run computing statistics no decision
    rule reads. The metrics that DO drive §5's rule -- Spearman and the depth metrics -- are the
    identical functions the real boards are scored with, not reimplementations."""
    row: dict[str, float | None] = {"spearman": spearman(pred_rank, real)}
    for k in topboard.W5_DEPTHS:
        row[f"capture@{k}"] = capture(pred_rank, real, k)
        row[f"precision@{k}"] = topk_precision(pred_rank, real, k)
    return row


def _by_week(values: dict[str, float]) -> list[float]:
    """A per-week dict as a list in **canonical week order**.

    `noise._bootstrap_mean_ci` indexes its input BY POSITION, so a list whose order depends on
    anything incidental -- dict insertion order, a set intersection, the order rows happened to
    arrive in -- produces a different confidence interval on every run. Gate G10 caught exactly
    that: `aggregate_cohorts` was intersecting two dicts' keys with a bare `keys() & keys()`,
    whose iteration order for string keys varies with `PYTHONHASHSEED`. Sorting here makes the
    property structural rather than incidental, at no cost."""
    return [v for _, v in sorted(values.items())]


def _mean_of(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.fmean(vals) if vals else None


def positional_cell(con, snap, position: str, fmt):
    """The evaluated universe for one (week, position), identical in shape to W3/W4's.

    ECR's positional board -> restricted to players who actually played -> restricted to Alpha's
    coverage. Every system scored on this cell sees exactly this player set."""
    ref = benchmark.positional_board(con, snap, position, fmt)
    played = {r.player_id for r in ref.evaluable}
    ref_played = alpha_mod.restrict_board(ref, played)
    preds = alpha_mod.load_alpha_predictions(con, snap.season, snap.week, positions=(position,))
    alpha_b, _cov = alpha_mod.alpha_board(ref_played, preds)
    keep = {r.player_id for r in alpha_b.rows}
    common = alpha_mod.restrict_board(ref_played, keep)
    return common, alpha_b, {pid: preds[pid] for pid in keep}


def run_cells(con, snapshots, fmt, *, positions=ALL_POSITIONS, with_null=True, with_regret=True):
    """Score every system on every (week, position) cell, plus the null, curve and regret."""
    cells: dict[str, dict] = {}
    null_cells: dict[str, dict] = {}
    curves: list[dict] = []
    regret_rows: list[dict] = []
    cohort_rows: list[dict] = []
    coverage: list[dict] = []

    for snap in snapshots:
        ctx_cache: dict[str, context.PlayerContext] | None = None
        # Loaded on EVERY pass, not only the regret pass: `with_regret` switches off the cohort
        # work, and gating the usage load on it silently emptied ORACLE_USAGE in the Half-PPR
        # replication, which then reported U = +0.0000 exactly -- a defect, not a result. Scored
        # in the format being evaluated, never in ffopportunity's native full PPR.
        usage = context.load_usage_points(con, snap.season, snap.week, fmt.points_per_reception)
        for position in positions:
            common, alpha_b, preds = positional_cell(con, snap, position, fmt)
            if len(common.rows) < benchmark.MIN_EVALUABLE:
                continue
            key = f"{snap.season}-{snap.week}"
            realized = {r.player_id: float(r.realized) for r in common.rows}

            oracle_u, covered = topboard.oracle_usage(common, preds, usage)
            boards = {
                "CF_A": alpha_b,
                "ECR": common,
                "ORACLE_USAGE": oracle_u,
                "ORACLE_OUTCOME": topboard.oracle_outcome(common, preds),
            }
            for sysname, board in boards.items():
                pr, rl = board.ranks_and_points()
                cells.setdefault(f"{position}|{sysname}", {})[key] = evaluate_cell(
                    pr, rl, depths=topboard.W5_DEPTHS
                ).as_row()
            coverage.append(
                {
                    "season": snap.season,
                    "week": snap.week,
                    "position": position,
                    "n": len(common.rows),
                    "usage_covered": covered,
                    "usage_share": covered / len(common.rows),
                }
            )

            # --- P1: the copula null, calibrated to THIS cell's own Spearman and ties ---
            if with_null:
                pr, rl = alpha_b.ranks_and_points()
                rho = spearman(pr, rl)
                if rho is not None and rho > 0:
                    latent = nulls.calibrate_latent(rl, rho, snap.season, snap.week, position)
                    draws = [
                        _null_metrics(
                            nulls.draw_null_ranking(
                                rl, rho, snap.season, snap.week, position, d, latent=latent
                            ).pred_rank,
                            rl,
                        )
                        for d in range(nulls.N_SIM)
                    ]
                    row = {m: _mean_of(draws, m) for m in draws[0]}
                    row["latent"] = latent
                    row["target_rho"] = rho
                    # The null's own conditional correlation: the range-restriction share of
                    # the collapse W4 reported, measured rather than argued.
                    #
                    # Two statistics, because Pearson reads the SCALE of a score and the null's
                    # latent score is standard normal while Alpha's predicted points are
                    # compressed and right-skewed -- correlating each against the same outcomes
                    # would compare two different quantities and, in a first run, made the null
                    # look 5x worse at the top than Alpha purely through that mismatch.
                    #   * conditional_spearman -- scale-free, comparable as-is;
                    #   * conditional_corr     -- Pearson on ALPHA's own value curve
                    #     transplanted onto the null's ordering, so both sides read the same
                    #     spacing and the comparison is to W4's reported statistic.
                    alpha_curve = list(preds.values())
                    ids = [r.player_id for r in common.rows]
                    cond_s, cond_p = [], []
                    for d in range(nulls.N_SIM):
                        nd = nulls.draw_null_ranking(
                            rl, rho, snap.season, snap.week, position, d, latent=latent
                        )
                        order = [
                            ids[i] for i in sorted(range(len(ids)), key=lambda i: nd.pred_rank[i])
                        ]
                        synth = topboard.transplant_values(order, alpha_curve)
                        cs = topboard.conditional_spearman(synth, realized)
                        cp = topboard.conditional_correlation(synth, realized)
                        if cs is not None:
                            cond_s.append(cs)
                        if cp is not None:
                            cond_p.append(cp)
                    row["conditional_spearman"] = statistics.fmean(cond_s) if cond_s else None
                    row["conditional_corr"] = statistics.fmean(cond_p) if cond_p else None
                    null_cells.setdefault(position, {})[key] = row

            # --- the quality curve, Alpha's own ---
            curve = {
                "season": snap.season,
                "week": snap.week,
                "position": position,
                "n": len(common.rows),
                "spearman": spearman(*alpha_b.ranks_and_points()),
                "conditional_corr": topboard.conditional_correlation(preds, realized),
                "conditional_spearman": topboard.conditional_spearman(preds, realized),
            }
            for w in topboard.depth_windows(preds, realized):
                curve[f"band_{w.lo}_{w.hi}"] = w.accuracy
                curve[f"band_{w.lo}_{w.hi}_pairs"] = w.pairs
            curves.append(curve)

            # --- P3: exact additive regret, cohorts and context ---
            if with_regret:
                if ctx_cache is None:
                    ctx_cache = build_context(con, snap)
                rows = regret.player_regret(snap.season, snap.week, position, preds, realized)
                universe = [r.player_id for r in rows]
                cohorts = regret.assign_cohorts(snap.season, ctx_cache, universe)
                for depth in regret.REGRET_DEPTHS:
                    for name, share in regret.cohort_shares(rows, cohorts, depth).items():
                        cohort_rows.append(
                            {
                                "season": snap.season,
                                "week": snap.week,
                                "position": position,
                                "depth": depth,
                                "cohort": name,
                                **share,
                            }
                        )
                member_of = {
                    pid: sorted(n for n, m in cohorts.items() if pid in m) for pid in universe
                }
                for r in rows:
                    c = ctx_cache.get(r.player_id)
                    regret_rows.append(
                        {
                            **{k: v for k, v in asdict(r).items() if k != "regret"},
                            **{f"regret@{k}": v for k, v in r.regret.items()},
                            "cohorts": member_of[r.player_id],
                            "usage_points": usage.get(r.player_id),
                            "opportunity_delta": c.opportunity_delta if c else None,
                            "snap_delta": c.snap_delta if c else None,
                            "weeks_since_last_game": c.weeks_since_last_game if c else None,
                            "opponent_pa_prior": c.opponent_pa_prior if c else None,
                            "team_epa_delta": c.team_epa_delta if c else None,
                            "depth_team_prior": c.depth_team_prior if c else None,
                            "injury_strict": (c.injury.get("STRICT") if c else None),
                            "injury_friday": (c.injury.get("FRIDAY") if c else None),
                            "practice_friday": (c.practice.get("FRIDAY") if c else None),
                            "teammates_out_friday": (c.teammates_out.get("FRIDAY") if c else None),
                        }
                    )
    return {
        "cells": cells,
        "null_cells": null_cells,
        "curves": curves,
        "regret_rows": regret_rows,
        "cohort_rows": cohort_rows,
        "coverage": coverage,
    }


def build_context(con, snap) -> dict[str, context.PlayerContext]:
    """Every pre-cutoff explanatory variable for one week, assembled once for all positions."""
    ctx = context.load_role_context(con, snap.season, snap.week, ALL_POSITIONS)
    context.attach_features(con, snap.season, snap.week, ctx)
    context.attach_prior_season_rank(con, snap.season, ctx)
    context.attach_rookie_season(con, ctx)
    context.attach_opponent(con, snap.season, snap.week, ctx)
    context.attach_team_environment_delta(con, snap.season, snap.week, ctx)
    context.attach_prior_depth_chart(con, snap.season, snap.week, ctx)
    context.attach_injury(con, snap.season, snap.week, snap.scrape_date, ctx)
    return ctx


def cliff_test(cells: dict, null_cells: dict, position: str) -> dict:
    """P1. Per week: actual minus the null's mean, on the frozen depth metrics.

    A NEGATIVE difference means Alpha's top-K is worse than its own overall ordering quality
    implies -- a genuine top-of-board defect. A difference indistinguishable from zero means the
    top-of-board result is fully implied by how well Alpha orders the whole board, and there is
    no separate top-of-board problem to solve."""
    out: dict = {}
    actual = cells.get(f"{position}|CF_A", {})
    null = null_cells.get(position, {})
    for metric in (
        "spearman",
        *(f"capture@{k}" for k in topboard.W5_DEPTHS),
        *(f"precision@{k}" for k in topboard.W5_DEPTHS),
    ):
        a = {
            k: r[metric]
            for k, r in actual.items()
            if not r.get("invalid") and r.get(metric) is not None
        }
        b = {k: r[metric] for k, r in null.items() if r.get(metric) is not None}
        pd_ = noise.paired_difference(metric, "ACTUAL", "NULL", a, b)
        if pd_:
            out[metric] = pd_.as_row()
            po = diagnostics.paired_outcome(metric, "ACTUAL", "NULL", a, b)
            if po:
                out[metric]["wins"] = po.a_wins
                out[metric]["losses"] = po.b_wins
    return out


def summarise(cells: dict, comparisons: list[tuple[str, str]]) -> dict:
    out: dict = {"distributions": {}, "paired": {}, "outcomes": {}}
    for sysname, weeks in cells.items():
        for metric in HEADLINE:
            vals = _by_week(
                {
                    k: r[metric]
                    for k, r in weeks.items()
                    if not r.get("invalid") and r.get(metric) is not None
                }
            )
            d = noise.describe(metric, vals)
            if d:
                out["distributions"].setdefault(sysname, {})[metric] = d.as_row()
    for a_name, b_name in comparisons:
        if a_name not in cells or b_name not in cells:
            continue
        for metric in HEADLINE:
            a = {
                k: r[metric]
                for k, r in cells[a_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            b = {
                k: r[metric]
                for k, r in cells[b_name].items()
                if not r.get("invalid") and r.get(metric) is not None
            }
            pd_ = noise.paired_difference(metric, a_name, b_name, a, b)
            if pd_:
                out["paired"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = pd_.as_row()
            po = diagnostics.paired_outcome(metric, a_name, b_name, a, b)
            if po:
                out["outcomes"].setdefault(f"{a_name}_vs_{b_name}", {})[metric] = po.as_row()
    return out


def aggregate_cohorts(cohort_rows: list[dict]) -> dict:
    """Cohort attribution, aggregated with the WEEK as the unit of replication.

    A cohort holding 4,000 player-weeks does not carry 4,000 independent observations. Each
    (week, position, depth) cell contributes one share; the reported figure is the distribution
    of those shares over weeks, with a bootstrap CI over weeks."""
    out: dict = {}
    keys = {(r["position"], r["depth"], r["cohort"]) for r in cohort_rows}
    for position, depth, cohort in sorted(keys):
        sel = [
            r
            for r in cohort_rows
            if r["position"] == position and r["depth"] == depth and r["cohort"] == cohort
        ]
        miss = {
            f"{r['season']}-{r['week']}": r["missed_share"]
            for r in sel
            if r["missed_share"] is not None
        }
        pop = {
            f"{r['season']}-{r['week']}": r["population_share"]
            for r in sel
            if r["population_share"] is not None
        }
        # `sorted(...)`: `dict.keys() & dict.keys()` is a SET, whose iteration order for
        # string keys varies with PYTHONHASHSEED. See `_by_week` for why that mattered.
        lift = {k: miss[k] - pop[k] for k in sorted(miss.keys() & pop.keys())}
        d_miss = noise.describe("missed_share", _by_week(miss))
        d_pop = noise.describe("population_share", _by_week(pop))
        d_lift = noise.describe("lift", _by_week(lift))
        if not (d_miss and d_pop and d_lift):
            continue
        rel = (d_miss.mean / d_pop.mean - 1.0) if d_pop.mean else None
        out[f"{position}|{depth}|{cohort}"] = {
            "missed_share": d_miss.as_row(),
            "population_share": d_pop.as_row(),
            "lift": d_lift.as_row(),
            "relative_lift": rel,
            "fp": sum(r["false_positives"] for r in sel),
            "fn": sum(r["false_negatives"] for r in sel),
            "n_player_weeks": sum(r["n"] for r in sel),
        }
    return out


def context_associations(regret_rows: list[dict]) -> dict:
    """Association between each pre-cutoff context variable and top-10 regret.

    Reported as the **week-level** difference in mean regret between the top and bottom tercile
    of the variable, so the unit of replication stays the week. A player-level correlation over
    12,000 rows would look overwhelmingly significant and mean almost nothing."""
    out: dict = {}
    variables = (
        "opportunity_delta",
        "snap_delta",
        "weeks_since_last_game",
        "opponent_pa_prior",
        "team_epa_delta",
    )
    for position in ALL_POSITIONS:
        rows = [r for r in regret_rows if r["position"] == position]
        for var in variables:
            hi: dict[str, float] = {}
            lo: dict[str, float] = {}
            weeks = {(r["season"], r["week"]) for r in rows}
            for season, week in sorted(weeks):
                cell = [
                    r
                    for r in rows
                    if r["season"] == season and r["week"] == week and r.get(var) is not None
                ]
                if len(cell) < 9:
                    continue
                cell.sort(key=lambda r: (r[var], r["player_id"]))
                t = max(1, len(cell) // 3)
                key = f"{season}-{week}"
                lo[key] = statistics.fmean(r["regret@10"] for r in cell[:t])
                hi[key] = statistics.fmean(r["regret@10"] for r in cell[-t:])
            pd_ = noise.paired_difference(var, "HIGH", "LOW", hi, lo)
            if pd_:
                out[f"{position}|{var}"] = pd_.as_row()
    return out


def injury_association(regret_rows: list[dict]) -> dict:
    """Top-10 regret carried by players with an injury designation, under both cutoff variants.

    Restricted to the seasons whose injury file carries `date_modified` -- 2025 is excluded
    outright rather than imputed, so the figures below describe 2021-2024 only."""
    out: dict = {}
    for position in ALL_POSITIONS:
        for variant, field_ in (("STRICT", "injury_strict"), ("FRIDAY", "injury_friday")):
            rows = [
                r
                for r in regret_rows
                if r["position"] == position and r["season"] in context.INJURY_SEASONS
            ]
            if not rows:
                continue
            flagged = [r for r in rows if r[field_] in ("Out", "Doubtful", "Questionable")]
            missed_total = sum(max(0.0, r["regret@10"]) for r in rows)
            missed_flagged = sum(max(0.0, r["regret@10"]) for r in flagged)
            credit_flagged = sum(-min(0.0, r["regret@10"]) for r in flagged)
            credit_total = sum(-min(0.0, r["regret@10"]) for r in rows)
            out[f"{position}|{variant}"] = {
                "n": len(rows),
                "n_flagged": len(flagged),
                "population_share": len(flagged) / len(rows) if rows else None,
                "missed_share": missed_flagged / missed_total if missed_total else None,
                "slot_credit_share": (credit_flagged / credit_total if credit_total else None),
                "false_positives_flagged": sum(1 for r in flagged if r["false_positive"]),
                "false_positives_total": sum(1 for r in rows if r["false_positive"]),
            }
        rows = [
            r
            for r in regret_rows
            if r["position"] == position and r["season"] in context.INJURY_SEASONS
        ]
        if rows:
            with_out = [r for r in rows if (r["teammates_out_friday"] or 0) > 0]
            mt = sum(max(0.0, r["regret@10"]) for r in rows)
            out[f"{position}|TEAMMATE_OUT"] = {
                "n_flagged": len(with_out),
                "population_share": len(with_out) / len(rows),
                "missed_share": (
                    sum(max(0.0, r["regret@10"]) for r in with_out) / mt if mt else None
                ),
            }
    return out


def leave_one_season_out(cells: dict, null_cells: dict, position: str, metric: str) -> dict:
    out: dict = {}
    for drop in SEASONS:
        a = {
            k: r[metric]
            for k, r in cells.get(f"{position}|CF_A", {}).items()
            if not r.get("invalid") and r.get(metric) is not None and not k.startswith(str(drop))
        }
        b = {
            k: r[metric]
            for k, r in null_cells.get(position, {}).items()
            if r.get(metric) is not None and not k.startswith(str(drop))
        }
        pd_ = noise.paired_difference(metric, "ACTUAL", "NULL", a, b)
        if pd_:
            out[f"drop_{drop}"] = pd_.as_row()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--out", default="reports/weekly/w5_results.json")
    ap.add_argument("--skip-half-ppr", action="store_true")
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
    prov = {
        "alpha_model": alpha_mod.WEEKLY_PROJECTION_BASE_MODEL,
        "ecr_sha256": require_snapshot(con, "dynastyprocess", "fp_ecr_history")["sha256"],
        "n_sim": nulls.N_SIM,
        "depths": list(topboard.W5_DEPTHS),
        "cohorts": list(regret.COHORTS),
        "sources": context.wire_snapshot_views(con, SEASONS),
    }
    print(f"provenance: {json.dumps(prov, indent=1)[:1200]}")

    snapshots = audit.week_coverage(con, SEASONS).snapshots
    print(f"weeks: {len(snapshots)}\n")

    print("[1/5] Full PPR: boards, oracles, copula null, curve, regret ...")
    full = run_cells(con, snapshots, FULL_PPR)
    print(f"      {len(full['cells'])} positional cells; {len(full['regret_rows']):,} player-weeks")

    print("[2/5] P1 cliff test and P2 oracle gaps ...")
    cliff = {p: cliff_test(full["cells"], full["null_cells"], p) for p in ALL_POSITIONS}
    comparisons = []
    for p in ALL_POSITIONS:
        comparisons += [
            (f"{p}|ORACLE_USAGE", f"{p}|CF_A"),
            (f"{p}|ORACLE_OUTCOME", f"{p}|CF_A"),
            (f"{p}|CF_A", f"{p}|ECR"),
            (f"{p}|ORACLE_USAGE", f"{p}|ECR"),
        ]
    summary = summarise(full["cells"], comparisons)

    print("[3/5] P3 cohort attribution and context associations ...")
    cohorts = aggregate_cohorts(full["cohort_rows"])
    assoc = context_associations(full["regret_rows"])
    injury = injury_association(full["regret_rows"])

    print("[4/5] robustness: leave-one-season-out, Half-PPR replication ...")
    loso = {
        p: {
            m: leave_one_season_out(full["cells"], full["null_cells"], p, m)
            for m in ("capture@10", "spearman")
        }
        for p in CONFIRMATORY_POSITIONS
    }
    half = None
    if not args.skip_half_ppr:
        h = run_cells(con, snapshots, HALF_PPR, positions=CONFIRMATORY_POSITIONS, with_regret=False)
        half = {
            "cliff": {
                p: cliff_test(h["cells"], h["null_cells"], p) for p in CONFIRMATORY_POSITIONS
            },
            "summary": summarise(
                h["cells"],
                [(f"{p}|ORACLE_USAGE", f"{p}|CF_A") for p in CONFIRMATORY_POSITIONS]
                + [(f"{p}|ORACLE_OUTCOME", f"{p}|CF_A") for p in CONFIRMATORY_POSITIONS]
                + [(f"{p}|CF_A", f"{p}|ECR") for p in CONFIRMATORY_POSITIONS],
            ),
        }

    print("[5/5] writing ...")
    for p in CONFIRMATORY_POSITIONS:
        c = cliff[p].get("capture@10")
        u = summary["paired"].get(f"{p}|ORACLE_USAGE_vs_{p}|CF_A", {}).get("capture@10")
        o = summary["paired"].get(f"{p}|ORACLE_OUTCOME_vs_{p}|CF_A", {}).get("capture@10")
        if c and u and o:
            ratio = u["mean_diff"] / o["mean_diff"] if o["mean_diff"] else float("nan")
            print(
                f"  {p}: cliff d={c['mean_diff']:+.4f} CI[{c['ci_low']:+.4f},{c['ci_high']:+.4f}]"
                f"   U={u['mean_diff']:+.4f}  O={o['mean_diff']:+.4f}  U/O={ratio:.1%}"
            )

    result = {
        "provenance": prov,
        "n_weeks": len(snapshots),
        "cells": full["cells"],
        "null_cells": full["null_cells"],
        "summary": summary,
        "cliff": cliff,
        "curves": full["curves"],
        "coverage": full["coverage"],
        "cohorts": cohorts,
        "cohort_rows": full["cohort_rows"],
        "context_associations": assoc,
        "injury": injury,
        "regret_rows": full["regret_rows"],
        "robustness_loso": loso,
        "half_ppr": half,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
