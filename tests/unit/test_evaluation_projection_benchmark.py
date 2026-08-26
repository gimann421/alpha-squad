"""Unit tests for the cross-model projection benchmark (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.projection_benchmark import (
    ALPHA_SEASON_MODELS,
    BASELINE_MODELS,
    build_projection_benchmark,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_eval_result(con, model_name, season, position, mae, spearman=0.5, n=10):
    con.execute(
        """
        INSERT INTO evaluation_results
            (model_name, season, position, n, mae, rmse, r2, spearman, top12_hit_rate,
             top24_hit_rate, tier_accuracy, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, 0.5, ?, 0.5, 0.5, 0.5, current_timestamp)
        """,
        [model_name, season, position, n, mae, mae, spearman],
    )


def _seed_every_model_family(con, season, position, mae_by_alpha_model=None):
    """One row per baseline + one per Alpha season-level model, all at `season`/`position` --
    the realistic shape (every family covering the same seasons uniformly) this report's
    strict "every model family has a row" intersection is designed around."""
    for baseline in BASELINE_MODELS:
        _seed_eval_result(con, baseline, season, position, mae=20.0)
    for alpha_model in ALPHA_SEASON_MODELS:
        mae = (mae_by_alpha_model or {}).get(alpha_model, 15.0)
        _seed_eval_result(con, f"{alpha_model}_{position.lower()}", season, position, mae=mae)


class TestSeasonIntersection:
    def test_only_common_seasons_are_included(self, con):
        # Every family covers 2020-2022 except one Alpha model, which only covers 2021-2022.
        for season in (2020, 2021, 2022):
            for baseline in BASELINE_MODELS:
                _seed_eval_result(con, baseline, season, "WR", mae=20.0)
            _seed_eval_result(con, "ml_season_ridge_wr", season, "WR", mae=15.0)
            _seed_eval_result(con, "ml_season_xgboost_wr", season, "WR", mae=15.0)
        for season in (2021, 2022):
            _seed_eval_result(con, "ml_season_catboost_wr", season, "WR", mae=15.0)

        result = build_projection_benchmark(con, 2020, 2022)
        assert result["common_seasons"] == [2021, 2022]
        wr_rows = [r for r in result["by_position"] if r["position"] == "WR"]
        baseline_row = next(r for r in wr_rows if r["model"] == "baseline_previous_year")
        assert baseline_row["n_seasons"] == 2  # 2020 correctly excluded, not inflating the average

    def test_missing_model_family_empties_the_intersection(self, con):
        for baseline in BASELINE_MODELS:
            _seed_eval_result(con, baseline, 2021, "WR", mae=20.0)
        # No ml_season_* rows seeded at all -- an entire model family is absent.
        result = build_projection_benchmark(con, 2021, 2021)
        assert set(ALPHA_SEASON_MODELS) <= set(result["missing_models"])
        assert result["common_seasons"] == []

    def test_lower_mae_model_sorts_first_within_a_position(self, con):
        _seed_every_model_family(con, 2021, "QB", mae_by_alpha_model={"ml_season_catboost": 5.0})
        result = build_projection_benchmark(con, 2021, 2021)
        qb_rows = [r for r in result["by_position"] if r["position"] == "QB"]
        assert qb_rows[0]["model"] == "ml_season_catboost"
        assert qb_rows[0]["mean_mae"] == pytest.approx(5.0)

    def test_all_position_rollup_rows_are_excluded_from_by_position_breakdown(self, con):
        _seed_every_model_family(con, 2021, "QB")
        # Also seed a real 'ALL' rollup row for every family, as evaluate_and_record really does.
        for baseline in BASELINE_MODELS:
            _seed_eval_result(con, baseline, 2021, "ALL", mae=20.0)
        result = build_projection_benchmark(con, 2021, 2021)
        positions_seen = {r["position"] for r in result["by_position"]}
        assert "ALL" not in positions_seen

    def test_baseline_real_per_position_row_is_not_collapsed_to_all(self, con):
        """Regression: baselines record their real position in the row itself (not the model
        name), so a naive name-suffix-only position derivation would misclassify every
        baseline row as position='ALL' and silently drop it from the comparison entirely."""
        _seed_every_model_family(con, 2021, "RB")
        result = build_projection_benchmark(con, 2021, 2021)
        rb_models = {r["model"] for r in result["by_position"] if r["position"] == "RB"}
        assert set(BASELINE_MODELS) <= rb_models
