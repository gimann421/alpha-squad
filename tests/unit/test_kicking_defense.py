"""Kicker and team-defense scoring, entities, and projections (docs/DECISIONS.md D57).

Fixtures are schema-accurate synthetic data (CLAUDE.md), so every expected number here is
computed by hand from the documented scoring rules rather than copied from a real season.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.features.kicking_defense import (
    DEFAULT_DST_SCORING,
    DST_ID_PREFIX,
    DST_POSITION,
    FANTASYPROS_TEAM_ALIASES,
    build_dst_week_stats,
    build_kicker_week_points,
    dst_player_id,
    ensure_dst_entities,
)
from alpha_squad.features.season_aggregate import build_player_season_stats
from alpha_squad.models.baselines.kicking_defense import (
    DST_PRIOR_WEIGHT,
    KICKER_WEIGHTS,
    MODEL_NAME,
    build_kdst_projections,
    project_defenses,
    project_kickers,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_season_points(con, player_id, season, position, points, games=17):
    con.execute(
        "INSERT INTO player_season_stats (player_id, season, position, games_played, "
        "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, ?, ?, ?)",
        [player_id, season, position, games, points, points / games],
    )


class TestDstPointsAllowedBands:
    """The tier table is the part of DST scoring most easily got wrong at a boundary."""

    @pytest.mark.parametrize(
        ("points_allowed", "expected"),
        [
            (0, 10.0),
            (1, 7.0),
            (6, 7.0),
            (7, 4.0),
            (13, 4.0),
            (14, 1.0),
            (20, 1.0),
            (21, 0.0),
            (27, 0.0),
            (28, -1.0),
            (34, -1.0),
            (35, -4.0),
            (70, -4.0),
        ],
    )
    def test_each_band_boundary(self, points_allowed, expected):
        assert DEFAULT_DST_SCORING.points_allowed_score(points_allowed) == expected


class TestDstEntities:
    def test_ids_are_built_from_team_codes_not_names(self):
        """CLAUDE.md: never use names as production player keys."""
        assert dst_player_id("KC") == f"{DST_ID_PREFIX}KC"

    def test_entities_are_derived_from_real_team_data(self, con):
        for team in ("KC", "BUF"):
            con.execute(
                "INSERT INTO team_week_stats (team, season, week, game_id, game_date) "
                "VALUES (?, 2024, 1, ?, DATE '2024-09-08')",
                [team, f"g_{team}"],
            )
        assert ensure_dst_entities(con, [2024]) == 2
        rows = con.execute(
            "SELECT player_id, position, gsis_id FROM players ORDER BY player_id"
        ).fetchall()
        assert rows == [
            (f"{DST_ID_PREFIX}BUF", DST_POSITION, f"{DST_ID_PREFIX}BUF"),
            (f"{DST_ID_PREFIX}KC", DST_POSITION, f"{DST_ID_PREFIX}KC"),
        ]

    def test_the_synthetic_gsis_id_cannot_be_mistaken_for_a_real_one(self, con):
        """A real GSIS id looks like '00-0034796'. The prefix makes ours self-evidently ours."""
        con.execute(
            "INSERT INTO team_week_stats (team, season, week, game_id, game_date) "
            "VALUES ('KC', 2024, 1, 'g1', DATE '2024-09-08')"
        )
        ensure_dst_entities(con, [2024])
        gsis_id = con.execute("SELECT gsis_id FROM players").fetchone()[0]
        assert gsis_id.startswith(DST_ID_PREFIX)
        assert not gsis_id.startswith("00-")

    def test_rerunning_creates_no_duplicates(self, con):
        con.execute(
            "INSERT INTO team_week_stats (team, season, week, game_id, game_date) "
            "VALUES ('KC', 2024, 1, 'g1', DATE '2024-09-08')"
        )
        assert ensure_dst_entities(con, [2024]) == 1
        assert ensure_dst_entities(con, [2024]) == 0
        assert con.execute("SELECT count(*) FROM players").fetchone()[0] == 1

    def test_fantasypros_aliases_cover_only_the_three_real_mismatches(self):
        """Verified against real data: 30 of 32 team codes already agree."""
        assert FANTASYPROS_TEAM_ALIASES == {"JAC": "JAX", "LAR": "LA", "OAK": "LV"}


class TestDstWeekScoring:
    """`build_dst_week_stats` reads the raw nflverse team-week snapshot, so these tests build
    a real parquet file with the same columns rather than mocking the reader."""

    def _seed_snapshot(self, con, tmp_path, rows):
        import pandas as pd

        path = tmp_path / "team_week.parquet"
        pd.DataFrame(rows).to_parquet(path)
        con.execute(
            "INSERT INTO snapshot_registry (snapshot_id, source, dataset, captured_at, url, "
            "local_path, sha256, params_json) VALUES ('s1', 'nflverse', 'stats_team_week', "
            "current_timestamp, 'u', ?, 'x', ?)",
            [str(path), '{"season": "2024"}'],
        )

    def _base_row(self, **overrides):
        row = {
            "team": "KC",
            "season": 2024,
            "week": 1,
            "game_id": "g1",
            "def_sacks": 0.0,
            "def_interceptions": 0,
            "def_fumbles": 0,
            "def_safeties": 0,
            "def_tds": 0,
            "special_teams_tds": 0,
            "def_punt_blocks": 0,
            "def_pat_blocks": 0,
            "def_fg_blocks": 0,
        }
        row.update(overrides)
        return row

    def _setup(self, con, tmp_path, *, opponent_points, **stat_overrides):
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date) "
            "VALUES ('g1', 2024, 1, 'REG', DATE '2024-09-08')"
        )
        con.execute(
            "INSERT INTO team_week_points (team, season, week, game_id, points, opponent_points) "
            "VALUES ('KC', 2024, 1, 'g1', 27, ?)",
            [opponent_points],
        )
        con.execute(
            "INSERT INTO team_week_stats (team, season, week, game_id, game_date) "
            "VALUES ('KC', 2024, 1, 'g1', DATE '2024-09-08')"
        )
        ensure_dst_entities(con, [2024])
        self._seed_snapshot(con, tmp_path, [self._base_row(**stat_overrides)])

    def test_a_shutout_with_no_counting_stats_scores_the_top_tier(self, con, tmp_path):
        self._setup(con, tmp_path, opponent_points=0)
        assert build_dst_week_stats(con, None, [2024]) == 1
        points = con.execute("SELECT fantasy_points_ppr FROM player_week_stats").fetchone()[0]
        assert points == 10.0

    def test_counting_stats_add_to_the_points_allowed_tier(self, con, tmp_path):
        # 3 sacks (3) + 2 INT (4) + 1 fumble (2) + 1 def TD (6) = 15, plus 17 allowed -> +1.
        self._setup(
            con,
            tmp_path,
            opponent_points=17,
            def_sacks=3.0,
            def_interceptions=2,
            def_fumbles=1,
            def_tds=1,
        )
        build_dst_week_stats(con, None, [2024])
        points = con.execute("SELECT fantasy_points_ppr FROM player_week_stats").fetchone()[0]
        assert points == 16.0

    def test_the_three_block_types_all_score_as_blocked_kicks(self, con, tmp_path):
        # 1 of each block (3 x 2 = 6), 24 allowed -> 0.
        self._setup(
            con,
            tmp_path,
            opponent_points=24,
            def_punt_blocks=1,
            def_pat_blocks=1,
            def_fg_blocks=1,
        )
        build_dst_week_stats(con, None, [2024])
        points = con.execute("SELECT fantasy_points_ppr FROM player_week_stats").fetchone()[0]
        assert points == 6.0

    def test_a_blowout_loss_can_score_negative(self, con, tmp_path):
        self._setup(con, tmp_path, opponent_points=45)
        build_dst_week_stats(con, None, [2024])
        points = con.execute("SELECT fantasy_points_ppr FROM player_week_stats").fetchone()[0]
        assert points == -4.0

    def test_rebuilding_updates_rather_than_duplicating(self, con, tmp_path):
        self._setup(con, tmp_path, opponent_points=0)
        build_dst_week_stats(con, None, [2024])
        build_dst_week_stats(con, None, [2024])
        assert con.execute("SELECT count(*) FROM player_week_stats").fetchone()[0] == 1

    def test_dst_rows_roll_up_into_the_season_aggregate(self, con, tmp_path):
        """The whole point of writing into player_week_stats: the existing season aggregate
        picks DSTs up with no change of its own."""
        self._setup(con, tmp_path, opponent_points=0)
        build_dst_week_stats(con, None, [2024])
        build_player_season_stats(con, [2024])
        row = con.execute(
            "SELECT position, total_fantasy_points_ppr FROM player_season_stats"
        ).fetchone()
        assert row == (DST_POSITION, 10.0)


class TestKdstProjections:
    def test_kickers_use_the_measured_two_season_weighting(self, con):
        _seed_season_points(con, "k1", 2023, "K", 100.0)
        _seed_season_points(con, "k1", 2024, "K", 200.0)
        w1, w2 = KICKER_WEIGHTS
        assert project_kickers(con, 2025) == {"k1": pytest.approx(w1 * 200.0 + w2 * 100.0)}

    def test_a_kicker_with_one_season_is_projected_not_dropped(self, con):
        """Dropping him would make him undraftable, a worse error than a noisy estimate."""
        _seed_season_points(con, "k1", 2024, "K", 150.0)
        assert project_kickers(con, 2025) == {"k1": pytest.approx(150.0)}

    def test_defenses_shrink_hard_toward_the_positional_mean(self, con):
        _seed_season_points(con, "d1", 2024, DST_POSITION, 200.0)
        _seed_season_points(con, "d2", 2024, DST_POSITION, 0.0)
        # Walk-forward positional mean over seasons < 2025 is (200 + 0) / 2 = 100.
        w = DST_PRIOR_WEIGHT
        result = project_defenses(con, 2025)
        assert result["d1"] == pytest.approx(w * 200.0 + (1 - w) * 100.0)
        assert result["d2"] == pytest.approx(w * 0.0 + (1 - w) * 100.0)

    def test_the_positional_mean_never_reads_the_target_season(self, con):
        """LEAKAGE. A 2025 projection must not be able to see 2025's outcomes -- including
        through the positional mean, which is the easy place for one to slip in."""
        _seed_season_points(con, "d1", 2024, DST_POSITION, 100.0)
        before = project_defenses(con, 2025)
        _seed_season_points(con, "d_future", 2025, DST_POSITION, 9999.0)
        assert project_defenses(con, 2025) == before

    def test_projections_persist_and_are_idempotent(self, con):
        _seed_season_points(con, "k1", 2024, "K", 150.0)
        _seed_season_points(con, "d1", 2024, DST_POSITION, 100.0)
        assert build_kdst_projections(con, [2025]) == 2
        build_kdst_projections(con, [2025])
        rows = con.execute(
            "SELECT position, count(*) FROM projection_snapshot WHERE model_name = ? GROUP BY 1",
            [MODEL_NAME],
        ).fetchall()
        assert dict(rows) == {"K": 1, DST_POSITION: 1}

    def test_seasons_with_no_prior_history_are_skipped_not_invented(self, con):
        assert build_kdst_projections(con, [2012]) == 0


class TestKickerWeekScoring:
    """The bug this fixes: nflverse's `fantasy_points_ppr` prices only passing/rushing/
    receiving, so every kicker in `player_week_stats` scored exactly 0.0 (verified on real
    data: 571 season rows, 7 non-zero, all from incidental non-kicking plays)."""

    def _seed(self, con, tmp_path, **kicking):
        import pandas as pd

        row = {
            "player_id": "00-0011111",
            "player_display_name": "Test Kicker",
            "position": "K",
            "season": 2024,
            "week": 1,
            "fg_made_0_19": 0,
            "fg_made_20_29": 0,
            "fg_made_30_39": 0,
            "fg_made_40_49": 0,
            "fg_made_50_59": 0,
            "fg_made_60_": 0,
            "fg_missed": 0,
            "pat_made": 0,
            "pat_missed": 0,
        }
        row.update(kicking)
        path = tmp_path / "player_week.parquet"
        pd.DataFrame([row]).to_parquet(path)
        con.execute(
            "INSERT INTO snapshot_registry (snapshot_id, source, dataset, captured_at, url, "
            "local_path, sha256, params_json) VALUES ('s1', 'nflverse', 'stats_player_week', "
            "current_timestamp, 'u', ?, 'x', ?)",
            [str(path), '{"season": "2024"}'],
        )
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date) "
            "VALUES ('g1', 2024, 1, 'REG', DATE '2024-09-08')"
        )
        con.execute(
            "INSERT INTO players (player_id, gsis_id, position) VALUES ('k1', '00-0011111', 'K')"
        )
        # The row features/player.py would already have ingested: correct in every column
        # except the fantasy points, which nflverse leaves at zero for kickers.
        con.execute(
            "INSERT INTO player_week_stats (player_id, season, week, game_id, game_date, "
            "position, fantasy_points, fantasy_points_ppr) "
            "VALUES ('k1', 2024, 1, 'g1', DATE '2024-09-08', 'K', 0.0, 0.0)"
        )

    def _points(self, con):
        return con.execute(
            "SELECT fantasy_points, fantasy_points_ppr FROM player_week_stats"
        ).fetchone()

    def test_distance_bands_score_differently(self, con, tmp_path):
        """The reason kicker points are computed rather than approximated from FGs made:
        a 50-yarder is worth more than a 30-yarder. 1 x 30-39 (3) + 1 x 40-49 (4)
        + 1 x 50-59 (5) + 2 PAT (2) = 14."""
        self._seed(
            con,
            tmp_path,
            fg_made_30_39=1,
            fg_made_40_49=1,
            fg_made_50_59=1,
            pat_made=2,
        )
        assert build_kicker_week_points(con, None, [2024]) == 1
        assert self._points(con) == (14.0, 14.0)

    def test_misses_subtract(self, con, tmp_path):
        # 2 x 30-39 (6) + 3 PAT (3) - 1 FG miss (1) - 1 PAT miss (1) = 7.
        self._seed(con, tmp_path, fg_made_30_39=2, pat_made=3, fg_missed=1, pat_missed=1)
        build_kicker_week_points(con, None, [2024])
        assert self._points(con) == (7.0, 7.0)

    def test_a_kicker_who_did_nothing_still_scores_zero(self, con, tmp_path):
        self._seed(con, tmp_path)
        build_kicker_week_points(con, None, [2024])
        assert self._points(con) == (0.0, 0.0)

    def test_both_scoring_columns_are_written(self, con, tmp_path):
        """Kicking has no reception component, so PPR and standard are the same number --
        but a non-PPR consumer must not be left reading the stale zero."""
        self._seed(con, tmp_path, fg_made_50_59=2)
        build_kicker_week_points(con, None, [2024])
        standard, ppr = self._points(con)
        assert standard == ppr == 10.0
