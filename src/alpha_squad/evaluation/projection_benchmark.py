"""Cross-model projection benchmark (docs/DECISIONS.md D54): does Alpha's player intelligence
outperform reasonable baselines?

This module writes no new predictions and runs no new models -- every number it reports is
already sitting in `evaluation_results`, produced by M4's walk-forward baseline runner
(`models/baselines/run.py`) and M5's walk-forward established-player ML
(`models/established/season_level.py`), using the exact same shared harness
(`models/evaluate.py`) so every row is directly comparable. This is a report generator, not a
model: it queries what already exists, in the season range where both a baseline and an Alpha
model were actually walk-forward evaluated, and states the range plainly rather than padding it.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.models.evaluate import ALL_POSITIONS_SENTINEL, SKILL_POSITIONS

BASELINE_MODELS = ("baseline_previous_year", "baseline_weighted_2yr", "baseline_ecr_implied")
ALPHA_SEASON_MODELS = ("ml_season_ridge", "ml_season_catboost", "ml_season_xgboost")


def _rows_for(con: duckdb.DuckDBPyConnection, model_names: tuple[str, ...]) -> list[tuple]:
    """Baselines record under the bare model name at position='ALL'/'QB'/etc; Alpha's
    per-position season-level models record under `f"{model_name}_{position.lower()}"` (see
    `models/established/season_level.py::run_season_level_established_ml`) with position
    always 'ALL' inside that row (one model instance per position, not a rollup) -- so an
    Alpha row's *real* position comes from parsing its suffix, not its `position` column."""
    suffixed = [f"{m}_{p.lower()}" for m in model_names for p in SKILL_POSITIONS]
    all_names = list(model_names) + suffixed
    placeholders = ",".join("?" * len(all_names))
    return con.execute(
        f"SELECT model_name, season, position, n, mae, rmse, spearman, top12_hit_rate, "  # noqa: S608
        f"top24_hit_rate, tier_accuracy FROM evaluation_results "
        f"WHERE model_name IN ({placeholders})",
        all_names,
    ).fetchall()


def _canonical_position(
    model_name: str, row_position: str, base_names: tuple[str, ...]
) -> tuple[str, str]:
    """('display_model_name', 'position'). Alpha's season-level models store their real
    position in the *name* (row_position inside that row is always 'ALL', one model instance
    per position -- see `_rows_for`'s docstring), so their canonical position comes from the
    name suffix. Baselines store their real position in the row itself (a genuine per-position
    breakdown from the same `evaluate_and_record` call), so a bare baseline name's canonical
    position is simply its own row's position, unchanged."""
    for base in base_names:
        for pos in SKILL_POSITIONS:
            if model_name == f"{base}_{pos.lower()}":
                return base, pos
    return model_name, row_position


def build_projection_benchmark(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int
) -> dict:
    """Returns {"by_position": [...], "overall": [...]} comparing every baseline against
    every Alpha season-level model over [season_start, season_end], restricted to seasons
    where BOTH sides actually have a row (an honest intersection, not one side padded with
    missing-data placeholders)."""
    rows = _rows_for(con, BASELINE_MODELS + ALPHA_SEASON_MODELS)

    by_key: dict[tuple[str, str, int], list[tuple]] = {}
    for model_name, season, row_position, n, mae, rmse, spearman, top12, top24, tier in rows:
        if not (season_start <= season <= season_end):
            continue
        display_name, canon_pos = _canonical_position(
            model_name, row_position, BASELINE_MODELS + ALPHA_SEASON_MODELS
        )
        by_key.setdefault((display_name, canon_pos, season), []).append(
            (n, mae, rmse, spearman, top12, top24, tier)
        )

    # Seasons where every model family has at least a position-level row -- the honest,
    # non-cherry-picked intersection window this comparison is actually valid over. Every
    # expected model family is seeded with an empty set up front so a family with *zero*
    # rows anywhere correctly forces the intersection to empty, rather than being silently
    # excluded from the intersection just because it never appeared in `by_key`.
    all_model_names = set(BASELINE_MODELS) | set(ALPHA_SEASON_MODELS)
    seasons_by_model: dict[str, set[int]] = {name: set() for name in all_model_names}
    for display_name, _pos, season in by_key:
        seasons_by_model.setdefault(display_name, set()).add(season)
    common_seasons = set.intersection(*seasons_by_model.values())
    missing_models = {name for name, seasons in seasons_by_model.items() if not seasons}

    by_position: dict[tuple[str, str], list[float]] = {}
    for (display_name, pos, season), entries in by_key.items():
        if season not in common_seasons or pos == ALL_POSITIONS_SENTINEL:
            continue
        for n, mae, _rmse, spearman, _top12, _top24, _tier in entries:
            by_position.setdefault((display_name, pos), []).append((n, mae, _rmse, spearman))

    position_summary = []
    for (display_name, pos), entries in sorted(by_position.items()):
        ns = [e[0] for e in entries]
        maes = [e[1] for e in entries if e[1] == e[1]]
        spearmans = [e[3] for e in entries if e[3] == e[3]]
        position_summary.append(
            {
                "model": display_name,
                "position": pos,
                "n_seasons": len(entries),
                "total_n": sum(ns),
                "mean_mae": sum(maes) / len(maes) if maes else None,
                "mean_spearman": sum(spearmans) / len(spearmans) if spearmans else None,
            }
        )
    position_summary.sort(
        key=lambda r: (r["position"], r["mean_mae"] if r["mean_mae"] is not None else 1e9)
    )

    return {
        "season_start": season_start,
        "season_end": season_end,
        "common_seasons": sorted(common_seasons),
        "missing_models": sorted(missing_models),
        "by_position": position_summary,
        "framework_version": EVALUATION_FRAMEWORK_VERSION,
    }


def write_projection_benchmark_report(
    con: duckdb.DuckDBPyConnection, path: Path, season_start: int, season_end: int
) -> dict:
    result = build_projection_benchmark(con, season_start, season_end)
    lines = [
        "# Projection benchmark: does Alpha's player intelligence beat baselines?",
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. Requested window: "
        f"{season_start}-{season_end}. Real intersection window (every model family actually "
        f"has a walk-forward row): **{result['common_seasons'] or 'none'}**.",
        "",
    ]
    if result["missing_models"]:
        lines.append(
            f"**Not included** (no `evaluation_results` row in this window at all): "
            f"`{', '.join(result['missing_models'])}`. Not a silent omission -- see "
            "docs/EVALUATION_LIMITATIONS.md for why (FantasyPros point projections and true "
            "ADP have no historical back-series to score against in this environment)."
        )
        lines.append("")
    lines += [
        "Baselines A/B/C (previous-year, weighted-2yr, FantasyPros-ECR-implied) vs. Alpha's "
        "three season-level candidate models (Ridge/CatBoost/XGBoost), all walk-forward "
        "(each target season's model trained only on strictly prior seasons), all scored "
        "through the identical harness (`models/evaluate.py`) against real "
        "`player_season_stats` outcomes -- lower MAE is better, higher Spearman is better.",
        "",
        "| Position | Model | Seasons | Total n | Mean MAE | Mean Spearman |",
        "|---|---|---|---|---|---|",
    ]
    for row in result["by_position"]:
        mae_s = f"{row['mean_mae']:.2f}" if row["mean_mae"] is not None else "-"
        sp_s = f"{row['mean_spearman']:.3f}" if row["mean_spearman"] is not None else "-"
        lines.append(
            f"| {row['position']} | {row['model']} | {row['n_seasons']} | {row['total_n']} | "
            f"{mae_s} | {sp_s} |"
        )
    lines += [
        "",
        "## Reading this honestly",
        "",
        "This table is intentionally restricted to the season/model intersection where every "
        "row is real -- widening the window by including a season only some models cover would "
        "silently favor whichever model happens to have more (typically easier, older) seasons "
        "in its average. If a baseline's MAE is lower than every Alpha model's at a position "
        "here, that is the real result for that position over this window, not a bug to "
        "explain away.",
        "",
    ]
    path.write_text("\n".join(lines))
    return result


def dump_projection_benchmark_json(result: dict, path: Path) -> None:
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str))
