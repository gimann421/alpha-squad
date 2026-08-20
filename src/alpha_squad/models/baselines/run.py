"""Walk-forward baseline runner: for each target season, every registered baseline predicts
using only prior-season/prior-market data, then gets scored against that season's real
outcome through the shared evaluation harness."""

from __future__ import annotations

import duckdb

from alpha_squad.models.baselines.market_implied import MARKET_ECR_IMPLIED, ecr_implied_baseline
from alpha_squad.models.baselines.simple import (
    PREVIOUS_YEAR,
    WEIGHTED_2YR,
    previous_year_baseline,
    weighted_two_year_baseline,
)
from alpha_squad.models.evaluate import EvaluationMetrics, evaluate_and_record

BASELINES = {
    PREVIOUS_YEAR: previous_year_baseline,
    WEIGHTED_2YR: weighted_two_year_baseline,
    MARKET_ECR_IMPLIED: ecr_implied_baseline,
}


def run_baselines(con: duckdb.DuckDBPyConnection, seasons: list[int]) -> list[EvaluationMetrics]:
    results: list[EvaluationMetrics] = []
    for season in seasons:
        for name, predict_fn in BASELINES.items():
            predicted = predict_fn(con, season)
            if not predicted:
                continue
            results.extend(evaluate_and_record(con, name, season, predicted))
    return results
