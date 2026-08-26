"""Trade evaluation (docs/DECISIONS.md D54) -- what is and is not measurable here, stated
plainly, per the phase directive's own caution about overclaiming causality on trade outcomes.

**Not feasible in this environment, and this module does not attempt it:** "did the roster
that accepted a recommended trade actually finish better than if it hadn't," across real
historical leagues. That needs a real, multi-season log of actual trades made in real leagues
plus a counterfactual (what would have happened without the trade) -- neither exists here. The
only real per-team roster history this project can reach is two *current* live Sleeper
leagues (`league/roster_import.py`), not years of historical trade transactions.

**What IS real and measurable:** `league/trade.py::recommend_dynasty_trade`'s BUY/HOLD/SELL/
WATCH action is a direct read of `edge_snapshot.action` for that player/season -- the exact
same signal M8's EDGE backtest and this phase's market-inefficiency stratification already
validate against real outcomes. A trade recommendation's *action* quality is therefore not a
separate, unvalidated claim -- it inherits the real evidence (and real limitations) already
established for EDGE. What genuinely does NOT inherit that validation is the *value number*
(`age_adjusted_value`, `pick_value`) used to compare package sides -- those are the two
heuristics `evaluation/dynasty_validation.py` checks against real draft-capital/age outcomes
separately. This module ties the two together into one honest statement rather than treating
"trade evaluation" as a third, independently-validated capability.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def build_trade_evidence_summary(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int, ecr_type: str = "rsf"
) -> list[dict]:
    rows = con.execute(
        """
        SELECT season, action, n, mean_actual_points, mean_market_implied_points,
               mean_outperformance_vs_market
        FROM edge_validation_results
        WHERE season BETWEEN ? AND ? AND ecr_type = ? AND action IN ('BUY', 'SELL')
        ORDER BY season, action
        """,
        [season_start, season_end, ecr_type],
    ).fetchall()
    return [
        {
            "season": season,
            "action": action,
            "n": n,
            "mean_actual_points": mean_actual,
            "mean_market_implied_points": mean_implied,
            "mean_outperformance_vs_market": mean_outperf,
        }
        for season, action, n, mean_actual, mean_implied, mean_outperf in rows
    ]


def write_trade_evaluation_report(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    season_start: int,
    season_end: int,
    ecr_type: str = "rsf",
) -> list[dict]:
    evidence = build_trade_evidence_summary(con, season_start, season_end, ecr_type)

    lines = [
        "# Trade evaluation: what is and is not measurable",
        "",
        "See this module's docstring for the full reasoning. Short version: a real, causal "
        '"did the accepted trade improve the roster" study needs historical trade transaction '
        "logs this environment does not have. What real data DOES support: "
        "`recommend_dynasty_trade`'s BUY/HOLD/SELL/WATCH action is a direct read of "
        "`edge_snapshot.action` for that player/season -- the same signal already validated by "
        "the EDGE backtest (`reports/edge_backtest.md`) and this phase's market-inefficiency "
        "stratification (`reports/market_inefficiency.md`). That evidence, reproduced below, "
        "IS the real evidentiary basis for a trade recommendation's action.",
        "",
        "## BUY/SELL cohort real outcomes (same signal `recommend_dynasty_trade`'s action reads)",
        "",
        "| Season | Action | n | Mean actual pts | Mean market-implied pts | Mean outperformance |",
        "|---|---|---|---|---|---|",
    ]
    for row in evidence:
        implied = (
            f"{row['mean_market_implied_points']:.1f}"
            if row["mean_market_implied_points"] is not None
            else "-"
        )
        outperf = (
            f"{row['mean_outperformance_vs_market']:+.1f}"
            if row["mean_outperformance_vs_market"] is not None
            else "-"
        )
        lines.append(
            f"| {row['season']} | {row['action']} | {row['n']} | {row['mean_actual_points']:.1f} | "
            f"{implied} | {outperf} |"
        )
    lines += [
        "",
        "Reading convention (shared with `market/edge.py`): a good BUY shows a *positive* "
        "outperformance number; a good SELL shows a *negative* one (the player actually "
        "underperformed what the market expected, exactly as the sell call predicted).",
        "",
        "## What trade recommendations add beyond the action signal",
        "",
        "A dynasty trade recommendation also compares *value* -- `age_adjusted_value` (dynasty "
        "value x the age-curve multiplier, D25) for single players, and `pick_value` (D45) for "
        "future picks in a package. Both are documented heuristics with no fitted ground truth. "
        "`reports/dynasty_heuristic_validation.md` (this phase) checks whether their assumed "
        "*shape* -- declining value by age, declining value by draft round -- matches real "
        "history; see that report for the real numbers. A correct action with an imprecise "
        "value number can still misprice which side of a multi-asset package is favored, so "
        "both pieces of evidence belong together, not just the action-level EDGE numbers above.",
        "",
        "## Not yet evaluated",
        "",
        "Whether accepting a recommended trade, specifically, produced a better season than the "
        "realistic alternative (rejecting it, or countering) -- this needs real historical "
        "trade transaction data this environment does not have. Not fabricated here.",
        "",
    ]
    path.write_text("\n".join(lines))
    return evidence
