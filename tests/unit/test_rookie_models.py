"""Unit tests for rookie modeling's walk-forward-by-draft-class discipline and the
historical comps nearest-neighbor logic, against synthetic fixtures."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.features.rookie import build_rookie_features
from alpha_squad.models.rookie.comps import find_historical_comps
from alpha_squad.models.rookie.data import load_rookie_class_data
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_rookie(
    con, player_id, draft_class, position, points, breakout, round_=3, pick=80, forty=4.6
):
    con.execute(
        """
        INSERT INTO rookie_features
            (player_id, draft_class, position, draft_round, draft_pick, forty, breakout_top24,
             rookie_year_ppr_points, rookie_year_games, built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 15, current_timestamp)
        """,
        [player_id, draft_class, position, round_, pick, forty, breakout, points],
    )


class TestWalkForwardByDraftClass:
    def test_load_rookie_class_data_scopes_to_the_requested_class_range(self, con):
        _seed_rookie(con, "p1", 2022, "WR", 100.0, False)
        _seed_rookie(con, "p2", 2023, "WR", 150.0, True)
        df = load_rookie_class_data(con, "WR", 2015, 2022)
        assert set(df["draft_class"]) == {2022}

    def test_undrafted_players_get_a_deliberately_bad_capital_not_zero(self, con):
        con.execute(
            """
            INSERT INTO rookie_features
                (player_id, draft_class, position, draft_round, draft_pick, breakout_top24,
                 rookie_year_ppr_points, built_at)
            VALUES ('udfa1', 2023, 'RB', NULL, NULL, false, 20.0, current_timestamp)
            """
        )
        df = load_rookie_class_data(con, "RB", 2015, 2023)
        row = df[df["player_id"] == "udfa1"].iloc[0]
        assert row["draft_round"] > 7  # worse than any real drafted round
        assert row["draft_pick"] > 260  # worse than any real drafted pick


class TestHistoricalComps:
    def test_comps_never_include_players_from_the_same_or_later_class(self, con):
        _seed_rookie(con, "early1", 2020, "RB", 100.0, False)
        _seed_rookie(con, "early2", 2021, "RB", 110.0, False)
        _seed_rookie(con, "target", 2023, "RB", 200.0, True)
        _seed_rookie(con, "future1", 2024, "RB", 50.0, False)  # must never appear as a comp

        comps = find_historical_comps(con, "target", 2023, "RB", k=5)
        classes = {c["draft_class"] for c in comps}
        assert all(c < 2023 for c in classes)
        assert "future1" not in {c["player_id"] for c in comps}

    def test_most_similar_player_is_ranked_first(self, con):
        _seed_rookie(con, "near", 2020, "WR", 100.0, False, round_=3, pick=80, forty=4.55)
        _seed_rookie(con, "far", 2021, "WR", 100.0, False, round_=7, pick=250, forty=4.9)
        _seed_rookie(con, "target", 2023, "WR", 100.0, False, round_=3, pick=82, forty=4.56)

        comps = find_historical_comps(con, "target", 2023, "WR", k=2)
        assert comps[0]["player_id"] == "near"
        assert comps[0]["similarity_distance"] < comps[1]["similarity_distance"]

    def test_empty_pool_returns_no_comps_rather_than_erroring(self, con):
        _seed_rookie(con, "only_class", 2023, "TE", 50.0, False)
        comps = find_historical_comps(con, "only_class", 2023, "TE", k=5)
        assert comps == []


def test_build_rookie_features_marks_breakout_correctly_against_real_position_ranks(con):
    """Integration-flavored unit test: seed a realistic player_season_stats pool and verify
    build_rookie_features derives breakout_top24 from actual within-position rank, not from
    a hardcoded points threshold."""
    con.execute(
        "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, draft_pick, rookie_season) VALUES ('r1', 'g1', 'WR', 'KC', 1, 5, 2023)"
    )
    for i in range(30):
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game) "
            "VALUES (?, 2023, 'WR', 15, ?, ?)",
            [f"other{i}", 300.0 - i * 5, (300.0 - i * 5) / 15],
        )
    # r1 finishes 5th overall among WRs (inserted at rank ~5 by score) -> should be top24.
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, total_fantasy_points_ppr, ppr_points_per_game) "
        "VALUES ('r1', 2023, 'WR', 15, 280.0, 18.67)"
    )
    build_rookie_features(con)
    row = con.execute("SELECT breakout_top24 FROM rookie_features WHERE player_id='r1'").fetchone()
    assert row == (True,)


class TestAblationArmsAreIndependent:
    """docs/DECISIONS.md D39: the two ablation arms must not overwrite each other.
    evaluation_results/classification_results are keyed on (model_name, season|cohort,
    position) and rookie_predictions is PK'd on prediction_id, so without distinct model
    names and a feature_version-aware prediction_id the second arm silently clobbers the
    first (or hard-fails on a PK violation) and the comparison is meaningless."""

    def _seed_class(self, con, draft_class, n=30):
        for i in range(n):
            player_id = f"p{draft_class}_{i}"
            con.execute(
                "INSERT INTO players (player_id, gsis_id, position, rookie_season) "
                "VALUES (?, ?, 'WR', ?)",
                [player_id, f"g{draft_class}_{i}", draft_class],
            )
            con.execute(
                "INSERT INTO player_season_stats (player_id, season, position, games_played, "
                "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'WR', 15, ?, ?)",
                [player_id, draft_class, 300.0 - i * 5, (300.0 - i * 5) / 15],
            )
            con.execute(
                """
                INSERT INTO rookie_features
                    (player_id, draft_class, position, draft_round, draft_pick, forty,
                     college_usage_overall, college_usage_pass, college_usage_rush,
                     breakout_top24, rookie_year_ppr_points, rookie_year_games, built_at)
                VALUES (?, ?, 'WR', ?, ?, 4.5, ?, ?, ?, ?, ?, 15, current_timestamp)
                """,
                [
                    player_id,
                    draft_class,
                    (i % 7) + 1,
                    i * 8 + 1,
                    0.05 * (i % 10),
                    0.04 * (i % 10),
                    0.03 * (i % 10),
                    i < 8,
                    300.0 - i * 5,
                ],
            )

    def test_both_arms_persist_distinct_rows_rather_than_overwriting(self, con):
        from alpha_squad.models.rookie.features import (
            COLLEGE_FEATURE_VERSION,
            FEATURES_WITH_COLLEGE,
        )
        from alpha_squad.models.rookie.train import run_rookie_models

        self._seed_class(con, 2022)
        self._seed_class(con, 2023)

        baseline = run_rookie_models(con, 2023, 2023, min_train_class=2000)
        candidate = run_rookie_models(
            con,
            2023,
            2023,
            min_train_class=2000,
            features=FEATURES_WITH_COLLEGE,
            feature_version=COLLEGE_FEATURE_VERSION,
            model_suffix="_college",
        )

        assert baseline.regression_metrics and candidate.regression_metrics

        models = {
            r[0]
            for r in con.execute("SELECT DISTINCT model_name FROM evaluation_results").fetchall()
        }
        assert "ml_rookie_regression_wr" in models
        assert "ml_rookie_regression_wr_college" in models

        # Both feature_versions coexist in rookie_predictions -- the PK-collision case.
        versions = {
            r[0]
            for r in con.execute("SELECT DISTINCT model_version FROM rookie_predictions").fetchall()
        }
        assert versions == {"rookie_features_v1", COLLEGE_FEATURE_VERSION}

    def test_arms_are_evaluated_on_identical_folds(self, con):
        """A delta between arms is only meaningful if both scored the same players."""
        from alpha_squad.models.rookie.features import (
            COLLEGE_FEATURE_VERSION,
            FEATURES_WITH_COLLEGE,
        )
        from alpha_squad.models.rookie.train import run_rookie_models

        self._seed_class(con, 2022)
        self._seed_class(con, 2023)

        run_rookie_models(con, 2023, 2023, min_train_class=2000)
        run_rookie_models(
            con,
            2023,
            2023,
            min_train_class=2000,
            features=FEATURES_WITH_COLLEGE,
            feature_version=COLLEGE_FEATURE_VERSION,
            model_suffix="_college",
        )

        rows = con.execute(
            "SELECT model_name, n FROM evaluation_results "
            "WHERE model_name IN ('ml_rookie_regression_wr', 'ml_rookie_regression_wr_college') "
            "AND position = 'ALL'"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][1] == rows[1][1] > 0

    def test_model_registry_feature_version_is_refreshed_not_left_stale(self, con):
        """Regression: _register_model's ON CONFLICT DO UPDATE omitted feature_version, so
        re-training an existing (model_name, position, version) row kept the OLD feature
        version while updating everything else around it."""
        from alpha_squad.models.rookie.features import (
            COLLEGE_FEATURE_VERSION,
            FEATURES_WITH_COLLEGE,
        )
        from alpha_squad.models.rookie.train import run_rookie_models

        self._seed_class(con, 2022)
        self._seed_class(con, 2023)

        run_rookie_models(
            con,
            2023,
            2023,
            min_train_class=2000,
            features=FEATURES_WITH_COLLEGE,
            feature_version=COLLEGE_FEATURE_VERSION,
        )
        run_rookie_models(con, 2023, 2023, min_train_class=2000)  # same names, v2 features

        fv = con.execute(
            "SELECT feature_version FROM model_registry "
            "WHERE model_name = 'ml_rookie_regression' AND position = 'WR'"
        ).fetchone()[0]
        assert fv == "rookie_features_v1"


class TestCollegeUsageJoin:
    """docs/DECISIONS.md D38: college_usage (CFBD, espn_id-bridged) joined into
    rookie_features for the rookie's *final college season only* (rookie_season - 1)."""

    def test_college_usage_for_the_final_college_season_is_joined_in(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO college_usage (player_id, season, usage_overall, usage_pass, usage_rush) "
            "VALUES ('r1', 2023, 0.624, 0.915, 0.222)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall, college_usage_pass, college_usage_rush "
            "FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (0.624, 0.915, 0.222)

    def test_the_rookies_own_nfl_season_year_is_never_used_as_the_join_key(self, con):
        """A college_usage row that happens to share the rookie's *NFL* season number (not
        their final *college* season, rookie_season - 1) must not leak in -- that would be a
        look-ahead the same way using the rookie's own NFL-season team stats would be."""
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO college_usage (player_id, season, usage_overall, usage_pass, usage_rush) "
            "VALUES ('r1', 2024, 0.999, 0.999, 0.999)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (None,)

    def test_missing_college_usage_leaves_the_columns_null_not_erroring(self, con):
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, draft_team, draft_round, "
            "draft_pick, rookie_season) VALUES ('r1', 'g1', 'QB', 'CHI', 1, 1, 2024)"
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES ('r1', 2024, 'QB', 17, 300.0, 17.65)"
        )
        build_rookie_features(con)
        row = con.execute(
            "SELECT college_usage_overall, college_usage_pass, college_usage_rush "
            "FROM rookie_features WHERE player_id='r1'"
        ).fetchone()
        assert row == (None, None, None)


class TestProjectingAnUnplayedDraftClass:
    """docs/DECISIONS.md D40: `rookie_features` INNER JOINs player_season_stats on the rookie's
    own season and declares the outcome NOT NULL, so a class whose season hasn't been played
    cannot exist in it. That is why the app was still showing an already-played 2025 class in
    August 2026. Projection uses a separate unlabeled table built from the SAME feature SQL."""

    def _seed_labeled_class(self, con, draft_class, n=30):
        for i in range(n):
            pid = f"lab{draft_class}_{i}"
            con.execute(
                "INSERT INTO players (player_id, gsis_id, position, rookie_season, draft_round, "
                "draft_pick, draft_team) VALUES (?, ?, 'RB', ?, ?, ?, 'KC')",
                [pid, f"g{pid}", draft_class, (i % 7) + 1, i * 8 + 1],
            )
            con.execute(
                "INSERT INTO player_season_stats (player_id, season, position, games_played, "
                "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'RB', 15, ?, ?)",
                [pid, draft_class, 300.0 - i * 5, (300.0 - i * 5) / 15],
            )

    def test_unplayed_class_is_projected_and_excluded_from_the_training_table(self, con):
        from alpha_squad.features.rookie import (
            build_rookie_features,
            build_rookie_projection_features,
        )
        from alpha_squad.models.rookie.train import project_rookie_class

        self._seed_labeled_class(con, 2024)
        self._seed_labeled_class(con, 2025)
        # The incoming class: on the spine with real draft capital, but no season played.
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position, rookie_season, "
            "draft_round, draft_pick, draft_team) "
            "VALUES ('rookie26', 'g26', 'Incoming Guy', 'RB', 2026, 1, 3, 'KC')"
        )

        build_rookie_features(con)
        built = build_rookie_projection_features(con, 2026)

        assert built == 1
        # The unlabeled row must NOT be in the labeled training table.
        assert (
            con.execute("SELECT count(*) FROM rookie_features WHERE draft_class = 2026").fetchone()[
                0
            ]
            == 0
        )

        report = project_rookie_class(con, 2026, min_train_class=2000)

        assert report.predictions_written == 1
        row = con.execute(
            "SELECT predicted_rookie_points, breakout_probability FROM rookie_predictions "
            "WHERE draft_class = 2026"
        ).fetchone()
        assert row[0] is not None and row[1] is not None

    def test_projection_records_no_evaluation_metrics(self, con):
        """There is no outcome to score against; publishing a metric would fabricate one."""
        from alpha_squad.features.rookie import build_rookie_projection_features
        from alpha_squad.models.rookie.train import project_rookie_class

        self._seed_labeled_class(con, 2024)
        self._seed_labeled_class(con, 2025)
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position, rookie_season, draft_round, "
            "draft_pick, draft_team) VALUES ('r26', 'g26', 'RB', 2026, 1, 3, 'KC')"
        )
        build_rookie_projection_features(con, 2026)
        project_rookie_class(con, 2026, min_train_class=2000)

        assert (
            con.execute("SELECT count(*) FROM evaluation_results WHERE season = 2026").fetchone()[0]
            == 0
        )
        assert (
            con.execute(
                "SELECT count(*) FROM classification_results WHERE cohort = 2026"
            ).fetchone()[0]
            == 0
        )

    def test_training_never_uses_the_class_being_projected(self, con):
        """Walk-forward discipline still applies: a future class has no labels, but the guard
        must be structural, not incidental."""
        from alpha_squad.features.rookie import build_rookie_features
        from alpha_squad.models.rookie.data import load_rookie_class_data

        self._seed_labeled_class(con, 2024)
        self._seed_labeled_class(con, 2025)
        build_rookie_features(con)

        train = load_rookie_class_data(con, "RB", 2000, 2025)
        assert train["draft_class"].max() == 2025
        assert 2026 not in set(train["draft_class"])
