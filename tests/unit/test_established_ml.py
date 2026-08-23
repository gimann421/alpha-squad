"""Unit tests for established-player ML's walk-forward discipline — the models themselves
are standard sklearn/CatBoost/XGBoost, so the thing worth testing directly is that training
data never includes the target season (the same leakage discipline as M3/M4), using small
synthetic fixtures rather than real data."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from alpha_squad.models.established.data import load_position_week_data
from alpha_squad.models.established.features import FULL_FEATURES
from alpha_squad.models.established.season_level import load_season_level_data
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_week_feature_row(con, player_id, season, week, position, **overrides):
    values = {col: 0.0 for col in FULL_FEATURES}
    values.update(overrides)
    con.execute(
        f"""
        INSERT INTO player_week_features
            (player_id, season, week, game_date, position, {", ".join(FULL_FEATURES)},
             target_fantasy_points_ppr, feature_version, built_at)
        VALUES (?, ?, ?, ?, ?, {", ".join("?" for _ in FULL_FEATURES)}, ?, 'test', ?)
        """,
        [
            player_id,
            season,
            week,
            date(season, 9, 1),
            position,
            *[values[c] for c in FULL_FEATURES],
            values.get("target_fantasy_points_ppr", 10.0),
            date(season, 9, 1),
        ],
    )


def _seed_season(con, player_id, season, total_points, position="WR"):
    con.execute(
        """
        INSERT INTO player_season_stats
            (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game)
        VALUES (?, ?, ?, 15, ?, ?)
        """,
        [player_id, season, position, total_points, total_points / 15],
    )


class TestWeeklyDataLoaderWalkForward:
    def test_load_position_week_data_can_be_scoped_to_prior_seasons_only(self, con):
        _seed_week_feature_row(con, "p1", 2023, 1, "WR")
        _seed_week_feature_row(con, "p1", 2024, 1, "WR")
        train = load_position_week_data(con, "WR", 2015, 2023)
        assert set(train["season"]) == {2023}

    def test_missing_lag_values_are_imputed_to_zero_not_dropped(self, con):
        con.execute(
            f"""
            INSERT INTO player_week_features
                (player_id, season, week, game_date, position, {", ".join(FULL_FEATURES)},
                 target_fantasy_points_ppr, feature_version, built_at)
            VALUES ('p1', 2023, 1, '2023-09-01', 'WR', {", ".join("NULL" for _ in FULL_FEATURES)}, 5.0, 'test', '2023-09-01')
            """
        )
        df = load_position_week_data(con, "WR", 2015, 2023)
        assert len(df) == 1
        assert (df[FULL_FEATURES].fillna(-999) != -999).all().all(), (
            "NaNs should have been imputed to 0.0"
        )


class TestSeasonLevelWalkForward:
    def test_training_rows_never_include_the_target_season_itself(self, con):
        for season, pts in [
            (2020, 100.0),
            (2021, 110.0),
            (2022, 120.0),
            (2023, 130.0),
            (2024, 999.0),
        ]:
            _seed_season(con, "p1", season, pts, position="WR")

        df = load_season_level_data(con, "WR", 2015, 2024)
        # target_season = prior_season + 1, so a row with target_season==2024 uses season
        # 2023 as its "prior" features — the 999.0 poison value for season 2024 must only
        # ever appear as somebody's *target*, never as a feature input for an earlier row.
        assert 999.0 not in df["prior_weighted_total"].to_numpy()
        assert 999.0 not in df["prior_ppg"].to_numpy()

    def test_missing_preseason_ecr_is_imputed_to_a_deliberately_bad_rank(self, con):
        _seed_season(con, "p1", 2022, 100.0, position="WR")
        _seed_season(con, "p1", 2023, 110.0, position="WR")
        df = load_season_level_data(con, "WR", 2015, 2023)
        assert (df["preseason_ecr_rank"] == 999.0).all()


class TestReproducibility:
    """CLAUDE.md: 'no untested claims' -- every MODEL_SPECS entry in models/established/train.py
    already sets a fixed random_state/random_seed=42, but that guarantee had never actually
    been exercised end to end. Runs the real CatBoost/XGBoost/Ridge fit-predict path (not a
    reimplementation of it) twice against identical small synthetic data and diffs the
    persisted evaluation_results, rather than trusting the presence of a seed kwarg alone."""

    @pytest.fixture(autouse=True)
    def _seed(self, con):
        # 4 players x 14 weeks of 2020 = 56 rows, enough to clear MIN_TRAINING_ROWS=50 for
        # WR; QB/RB/TE get zero rows and are skipped by run_established_ml, keeping this cheap.
        for i, player_id in enumerate(["wr_a", "wr_b", "wr_c", "wr_d"]):
            for week in range(1, 15):
                con.execute(
                    "INSERT INTO players (player_id, gsis_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                    [player_id, f"00-test-{player_id}"],
                )
                _seed_week_feature_row(
                    con,
                    player_id,
                    2020,
                    week,
                    "WR",
                    fp_ppr_avg_last3=6.0 + i * 2.0 + (week % 4),
                    targets_avg_last3=4.0 + i + (week % 3),
                    target_fantasy_points_ppr=8.0 + i * 2.0 + (week % 3),
                )
            _seed_week_feature_row(
                con,
                player_id,
                2021,
                1,
                "WR",
                fp_ppr_avg_last3=6.0 + i * 2.0,
                targets_avg_last3=4.0 + i,
                target_fantasy_points_ppr=9.0 + i,
            )
            _seed_season(con, player_id, 2021, 150.0 + i * 10, position="WR")
        self.con = con

    def test_same_input_data_produces_identical_evaluation_results(self):
        from alpha_squad.models.established.train import run_established_ml

        query = (
            "SELECT model_name, season, position, n, mae, rmse, spearman FROM evaluation_results "
            "WHERE season = 2021 AND n > 0 ORDER BY model_name, position"
        )

        def normalized(rows):
            # NaN != NaN under plain equality (e.g. spearman on a model whose predictions
            # happen to be constant across this tiny synthetic set); a real reproducibility
            # check must not let that mask a genuine mismatch elsewhere in the same row, so
            # only NaN-vs-NaN is treated as equal, via a shared sentinel.
            return [
                tuple("NaN" if isinstance(v, float) and v != v else v for v in row) for row in rows
            ]

        run_established_ml(self.con, season_start=2021, season_end=2021, min_train_season=2020)
        first = normalized(self.con.execute(query).fetchall())
        assert first, "expected at least the WR models to have trained and been evaluated"

        run_established_ml(self.con, season_start=2021, season_end=2021, min_train_season=2020)
        second = normalized(self.con.execute(query).fetchall())

        assert first == second, (
            "training on identical data twice must produce bit-identical evaluation metrics "
            "given every model's fixed random_state/random_seed=42"
        )
