"""The most important tests in this project (CLAUDE.md: "no future-data leakage" is a
hard quality bar, not a nice-to-have). `build_player_week_features` is supposed to be
leakage-safe *by construction* — every lag column uses a SQL window frame that structurally
excludes the current and future rows. These tests try hard to disprove that, rather than
just confirming the happy path, per the adversarial evaluation posture in
ACCEPTANCE_CRITERIA.md / AGENT_CONTRACTS.md (`evaluation_qa`).

All fixtures are synthetic (schema-accurate, invented values) and entirely offline — this
suite operates directly on `player_week_stats`, seeded by hand, rather than through the raw
nflverse ingestion path (which is covered separately by the live network test in
tests/integration/test_features_live.py)."""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pytest

from alpha_squad.features.panel import build_player_week_features
from alpha_squad.storage.db import init_db

PLAYER_ID = "asq_test1"
GSIS_ID = "00-9999001"


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO players (player_id, gsis_id) VALUES (?, ?)", [PLAYER_ID, GSIS_ID]
    )
    yield connection
    connection.close()


def _seed_week(
    con,
    season: int,
    week: int,
    game_date: date,
    fp_ppr: float,
    *,
    targets=5.0,
    carries=0.0,
    receptions=3.0,
) -> None:
    game_id = f"{season}_{week:02d}_TST_TST"
    con.execute(
        "INSERT INTO games (game_id, season, week, game_type, game_date) VALUES (?, ?, ?, 'REG', ?) "
        "ON CONFLICT DO NOTHING",
        [game_id, season, week, game_date],
    )
    con.execute(
        """
        INSERT INTO player_week_stats
            (player_id, season, week, game_id, game_date, team, position, targets, carries,
             receptions, fantasy_points_ppr, source_snapshot_id)
        VALUES (?, ?, ?, ?, ?, 'TST', 'WR', ?, ?, ?, ?, 'test-snapshot')
        """,
        [PLAYER_ID, season, week, game_id, game_date, targets, carries, receptions, fp_ppr],
    )


def _rows(con, order_by="week"):
    return con.execute(
        f"SELECT week, games_played_prior, fp_ppr_avg_last3, fp_ppr_avg_season_to_date, "
        f"target_fantasy_points_ppr FROM player_week_features WHERE player_id = '{PLAYER_ID}' "
        f"ORDER BY {order_by}"
    ).fetchall()


class TestPoisonFutureData:
    def test_a_poisoned_future_week_never_leaks_into_earlier_rows(self, con):
        for wk, fp in enumerate([10.0, 12.0, 14.0, 16.0, 18.0], start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        # An outlandish sentinel value for a *future* week relative to weeks 1-5.
        _seed_week(con, 2024, 6, date(2024, 10, 20), 999.0)

        build_player_week_features(con)

        rows = _rows(con)
        for week, _prior, avg_last3, avg_season, _target in rows:
            if week < 6:
                # Normal fantasy output here is well under 100; if the 999 sentinel had
                # leaked into a 3-game trailing average it would push it above ~330.
                assert avg_last3 is None or avg_last3 < 100, (
                    f"week {week} lag feature {avg_last3} appears poisoned by the future sentinel"
                )
                assert avg_season is None or avg_season < 100

    def test_the_poisoned_week_itself_only_sees_its_own_prior_history(self, con):
        for wk, fp in enumerate([10.0, 12.0, 14.0, 16.0, 18.0], start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        _seed_week(con, 2024, 6, date(2024, 10, 20), 999.0)

        build_player_week_features(con)

        week6 = next(r for r in _rows(con) if r[0] == 6)
        _week, _prior, avg_last3, _avg_season, target = week6
        assert target == 999.0, "the poisoned week's own target must reflect its real outcome"
        assert avg_last3 == pytest.approx((14.0 + 16.0 + 18.0) / 3), (
            "week 6's lag feature must be computed from weeks 3-5 only, not include itself"
        )


class TestTargetIsolation:
    def test_first_career_game_has_null_lag_features(self, con):
        """A player's very first game has no prior history — the lag features must be NULL,
        not accidentally equal to that same game's own outcome."""
        _seed_week(con, 2024, 1, date(2024, 9, 8), 42.0)
        build_player_week_features(con)

        row = _rows(con)[0]
        _week, games_played_prior, avg_last3, avg_season, target = row
        assert games_played_prior == 0
        assert avg_last3 is None
        assert avg_season is None
        assert target == 42.0

    def test_lag_features_match_independent_python_recomputation(self, con):
        """Recompute the expected trailing-3 average independently in Python (not reusing
        any of the production SQL) and compare row by row — the strongest form of this
        check, since it doesn't trust the same logic it's verifying."""
        fps = [10.0, 20.0, 30.0, 40.0, 50.0, 15.0, 25.0]
        for wk, fp in enumerate(fps, start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        build_player_week_features(con)

        rows = _rows(con)
        for week, _prior, avg_last3, _avg_season, target in rows:
            assert target == fps[week - 1]
            prior_values = fps[: week - 1][-3:]
            if not prior_values:
                assert avg_last3 is None
            else:
                assert avg_last3 == pytest.approx(sum(prior_values) / len(prior_values))

    def test_season_to_date_average_excludes_current_week_and_resets_each_season(self, con):
        _seed_week(con, 2023, 1, date(2023, 9, 8), 100.0)
        _seed_week(con, 2023, 2, date(2023, 9, 15), 200.0)
        _seed_week(con, 2024, 1, date(2024, 9, 6), 5.0)
        _seed_week(con, 2024, 2, date(2024, 9, 13), 15.0)
        build_player_week_features(con)

        rows = con.execute(
            f"SELECT season, week, fp_ppr_avg_season_to_date FROM player_week_features "
            f"WHERE player_id = '{PLAYER_ID}' ORDER BY season, week"
        ).fetchall()
        # 2024 week 1 must not carry over 2023's season-to-date average (reset per season).
        s2024w1 = next(r for r in rows if r[0] == 2024 and r[1] == 1)
        assert s2024w1[2] is None
        s2024w2 = next(r for r in rows if r[0] == 2024 and r[1] == 2)
        assert s2024w2[2] == pytest.approx(5.0)


class TestRebuildInvariance:
    def test_appending_future_weeks_and_rebuilding_does_not_change_past_rows(self, con):
        for wk, fp in enumerate([10.0, 20.0, 30.0], start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        build_player_week_features(con)
        before = _rows(con)

        for wk, fp in enumerate([999.0, 5.0], start=4):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        build_player_week_features(con)
        after = [r for r in _rows(con) if r[0] <= 3]

        assert before == after, (
            "appending future weeks must not change already-built historical rows"
        )

    def test_rebuilding_with_no_new_data_is_a_pure_noop(self, con):
        for wk, fp in enumerate([10.0, 20.0, 30.0], start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        build_player_week_features(con)
        first = _rows(con)
        build_player_week_features(con)
        second = _rows(con)
        assert first == second


class TestFeaturesAsOf:
    def test_features_as_of_excludes_games_not_yet_played(self, con):
        from alpha_squad.features.panel import features_as_of

        for wk, fp in enumerate([10.0, 20.0, 30.0], start=1):
            _seed_week(con, 2024, wk, (date(2024, 9, 1) + timedelta(weeks=wk - 1)), fp)
        build_player_week_features(con)

        as_of_before_week3 = date(2024, 9, 15)  # week 3's game_date is 2024-09-15
        rows = features_as_of(con, as_of_before_week3)
        weeks_visible = {r["week"] for r in rows}
        assert weeks_visible == {1, 2}, "a game on the as-of date itself must not be visible yet"
