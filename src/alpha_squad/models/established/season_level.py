"""Season-level (preseason) established-player ML — the genuine apples-to-apples comparison
against M4's baselines (previous_year, weighted_2yr, ecr_implied), all of which predict
season S using only information available *before* S starts.

This is distinct from train.py's weekly/in-season models, which additionally use season S's
own trailing weeks (recent within-season form) and therefore answer a different real-world
question — a mid-season update, not a preseason projection. Comparing train.py's models
directly against M4's preseason baselines would overstate ML's advantage, since it has
strictly more information available. See docs/DECISIONS.md D18."""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from alpha_squad.models.evaluate import EvaluationMetrics, evaluate_and_record
from alpha_squad.sources.base import utcnow

FEATURE_VERSION = "established_season_level_ml_v1"
POSITIONS = ("QB", "RB", "WR", "TE")
FEATURES = ["prior_ppg", "prior_games", "prior_weighted_total", "preseason_ecr_rank"]
TARGET_COLUMN = "target_points"
MIN_TRAINING_ROWS = 30

MODEL_SPECS: dict[str, tuple[type, dict]] = {
    "ml_season_ridge": (Ridge, {"alpha": 5.0}),
    "ml_season_catboost": (
        CatBoostRegressor,
        {
            "iterations": 150,
            "depth": 3,
            "learning_rate": 0.08,
            "loss_function": "MAE",
            "verbose": False,
            "random_seed": 42,
        },
    ),
    "ml_season_xgboost": (
        XGBRegressor,
        {"n_estimators": 150, "max_depth": 3, "learning_rate": 0.08, "random_state": 42},
    ),
}


def load_season_level_data(
    con: duckdb.DuckDBPyConnection, position: str, season_start: int, season_end: int
) -> pd.DataFrame:
    """One row per (player, target_season): season S-1 aggregate + preseason ECR for season
    S (both strictly pre-S information), target = season S's real total. ECR is left-joined
    (not every player has a preseason rank) and missing values are imputed to a deliberately
    bad rank (999) rather than 0, so "no market opinion" doesn't look like "elite consensus.\""""
    df = con.execute(
        """
        SELECT
            s1.player_id,
            s1.season + 1 AS target_season,
            s1.ppr_points_per_game AS prior_ppg,
            s1.games_played AS prior_games,
            COALESCE(0.65 * s1.total_fantasy_points_ppr + 0.35 * s2.total_fantasy_points_ppr,
                     s1.total_fantasy_points_ppr) AS prior_weighted_total,
            m.ecr_rank AS preseason_ecr_rank,
            st.total_fantasy_points_ppr AS target_points
        FROM player_season_stats s1
        LEFT JOIN player_season_stats s2 ON s2.player_id = s1.player_id AND s2.season = s1.season - 1
        JOIN player_season_stats st ON st.player_id = s1.player_id AND st.season = s1.season + 1
        LEFT JOIN (
            SELECT player_id, ecr_rank, year(scrape_date) AS yr,
                   row_number() OVER (PARTITION BY player_id, year(scrape_date) ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot WHERE ecr_type = 'ro' AND month(scrape_date) IN (7, 8)
        ) m ON m.player_id = s1.player_id AND m.yr = s1.season + 1 AND m.rn = 1
        WHERE s1.position = ? AND s1.season + 1 BETWEEN ? AND ?
        """,
        [position, season_start, season_end],
    ).fetchdf()
    df["preseason_ecr_rank"] = df["preseason_ecr_rank"].fillna(999.0)
    return df


@dataclass
class SeasonLevelTrainReport:
    metrics: list[EvaluationMetrics] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _register_model(con, model_name, position, season_start, season_end, notes):
    con.execute(
        """
        INSERT INTO model_registry
            (model_name, position, version, feature_version, training_season_start,
             training_season_end, trained_at, validated, notes)
        VALUES (?, ?, 'v1', ?, ?, ?, ?, true, ?)
        ON CONFLICT (model_name, position, version) DO UPDATE SET
            training_season_start = excluded.training_season_start,
            training_season_end = excluded.training_season_end,
            trained_at = excluded.trained_at,
            notes = excluded.notes
        """,
        [model_name, position, FEATURE_VERSION, season_start, season_end, utcnow(), notes],
    )


def run_season_level_established_ml(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int, min_train_season: int = 2015
) -> SeasonLevelTrainReport:
    report = SeasonLevelTrainReport()

    for target_season in range(season_start, season_end + 1):
        for position in POSITIONS:
            all_data = load_season_level_data(con, position, min_train_season, target_season)
            train_df = all_data[all_data["target_season"] < target_season]
            predict_df = all_data[all_data["target_season"] == target_season]

            if len(train_df) < MIN_TRAINING_ROWS or predict_df.empty:
                report.skipped.append(f"{position}/{target_season}: {len(train_df)} training rows")
                continue

            x_train = train_df[FEATURES].to_numpy()
            y_train = train_df[TARGET_COLUMN].to_numpy()
            x_pred = predict_df[FEATURES].to_numpy()

            for model_name, (model_cls, kwargs) in MODEL_SPECS.items():
                model = model_cls(**kwargs)
                model.fit(x_train, y_train)
                preds = model.predict(x_pred)
                predicted = dict(
                    zip(predict_df["player_id"].tolist(), (float(p) for p in preds), strict=True)
                )

                metrics = evaluate_and_record(
                    con, f"{model_name}_{position.lower()}", target_season, predicted
                )
                report.metrics.extend(m for m in metrics if m.position == "ALL")
                _register_model(
                    con,
                    model_name,
                    position,
                    min_train_season,
                    target_season - 1,
                    "preseason (season-level) model; directly comparable to M4 baselines",
                )

    return report
