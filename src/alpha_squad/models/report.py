"""Markdown evaluation report generator — ACCEPTANCE_CRITERIA.md requires baseline/model
comparisons be published, not just computed and discarded. No third-party markdown-table
dependency; the format is simple enough to build directly."""

from __future__ import annotations

from pathlib import Path

import duckdb


def _fmt(x) -> str:
    if x is None:
        return "-"
    try:
        if x != x:  # NaN
            return "-"
    except TypeError:
        return str(x)
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def write_evaluation_report(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    rows = con.execute(
        """
        SELECT model_name, season, position, n, mae, rmse, r2, spearman,
               top12_hit_rate, top24_hit_rate, tier_accuracy
        FROM evaluation_results
        ORDER BY position, season, model_name
        """
    ).fetchall()

    headers = [
        "model",
        "season",
        "position",
        "n",
        "mae",
        "rmse",
        "r2",
        "spearman",
        "top12_hit",
        "top24_hit",
        "tier_acc",
    ]
    lines = [
        "# Baseline / Model Evaluation Report",
        "",
        "Walk-forward: every prediction for season S used only data from before S. "
        "See docs/DECISIONS.md D16/D17 for the ECR-implied baseline's calibration method.",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(v) for v in row) + " |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
