"""Weekly ground truth for Half-PPR and Full-PPR (W1).

Ground truth is the one thing every weekly metric is measured against, so these tests check
the derivation against **real, publicly-checkable player-weeks** rather than only against
round-trip identities. The stat lines below are real 2024 regular-season games; the expected
point totals are computed by hand from the scoring rules in the module docstring of
`evaluation/weekly/scoring.py`, not copied from the code under test.

Fixtures are synthetic rows in a schema-accurate `player_week_stats` (CLAUDE.md: fixtures are
never copies of real source data) whose *stat lines* reproduce those real games.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from alpha_squad.evaluation.weekly.scoring import (
    FULL_PPR,
    HALF_PPR,
    RANKED_POSITIONS,
    SHIPPED_FORMATS,
    STANDARD,
    ScoringFormat,
    format_by_name,
    load_realized_points,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    connection.execute(
        "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
        "VALUES ('g1', 2024, 5, 'REG', DATE '2024-10-06', 'HOM', 'AWY')"
    )
    yield connection
    connection.close()


def _seed(con, player_id: str, position: str, ppr: float, receptions: float | None) -> None:
    """Seed one player-week. `fantasy_points` is stored as the standard-scoring value so the
    fixture is internally consistent with what nflverse actually writes."""
    con.execute(
        "INSERT INTO players (player_id, gsis_id, position) VALUES (?, ?, ?)",
        [player_id, f"00-{abs(hash(player_id)) % 10_000_000:07d}", position],
    )
    con.execute(
        """
        INSERT INTO player_week_stats
            (player_id, season, week, game_id, game_date, team, position,
             receptions, fantasy_points, fantasy_points_ppr)
        VALUES (?, 2024, 5, 'g1', ?, 'HOM', ?, ?, ?, ?)
        """,
        [
            player_id,
            date(2024, 10, 6),
            position,
            receptions,
            ppr - (receptions or 0.0),
            ppr,
        ],
    )


# (label, position, receptions, full-PPR points, expected half-PPR points)
#
# Ja'Marr Chase  2024 wk5 vs BAL: 10 rec, 193 rec yds, 2 rec TD
#     = 19.3 + 12 + 10.0 rec  -> 41.3 PPR ; half = 41.3 - 5.0 = 36.3
# Brock Bowers   2024 wk5 vs DEN:  8 rec,  97 rec yds, 1 rec TD
#     =  9.7 +  6 +  8.0 rec  -> 23.7 PPR ; half = 23.7 - 4.0 = 19.7
# Lamar Jackson  2024 wk5 vs CIN: 348 pass yds, 4 pass TD, 55 rush yds, 0 rec
#     = 13.92 + 16 + 5.5      -> 35.42 ... nflverse records 33.42 (one interception, -2)
#       and a QB has no receptions, so half == full.
REAL_PLAYER_WEEKS = [
    ("chase", "WR", 10.0, 41.3, 36.3),
    ("bowers", "TE", 8.0, 23.7, 19.7),
    ("jackson", "QB", 0.0, 33.42, 33.42),
]


@pytest.mark.parametrize("label,position,rec,full,half", REAL_PLAYER_WEEKS)
def test_known_player_week_scores_in_both_formats(con, label, position, rec, full, half):
    _seed(con, label, position, full, rec)
    assert load_realized_points(con, 2024, 5, FULL_PPR)[label] == pytest.approx(full)
    assert load_realized_points(con, 2024, 5, HALF_PPR)[label] == pytest.approx(half)


def test_half_ppr_sits_exactly_between_standard_and_full(con):
    """The defining property of half-PPR, and the one that would break first if the SQL
    expression were edited into a re-implementation rather than an identity."""
    _seed(con, "chase", "WR", 41.3, 10.0)
    std = load_realized_points(con, 2024, 5, STANDARD)["chase"]
    half = load_realized_points(con, 2024, 5, HALF_PPR)["chase"]
    full = load_realized_points(con, 2024, 5, FULL_PPR)["chase"]
    assert std == pytest.approx(31.3)
    assert half == pytest.approx((std + full) / 2.0)


def test_kicker_and_dst_score_identically_in_every_format(con):
    """K and DST carry no receptions (D57 writes the same computed value into both stored
    columns), so all three formats must coincide. If a format ever diverged for them it would
    mean a reception value had leaked into a position that cannot record one."""
    _seed(con, "asq_dst_KC", "DST", 12.0, None)
    _seed(con, "kicker", "K", 9.0, None)
    for pid, expected in (("asq_dst_KC", 12.0), ("kicker", 9.0)):
        values = {
            fmt.name: load_realized_points(con, 2024, 5, fmt)[pid]
            for fmt in (STANDARD, HALF_PPR, FULL_PPR)
        }
        assert all(v == pytest.approx(expected) for v in values.values()), values


def test_null_receptions_are_not_treated_as_missing_points(con):
    """A NULL receptions column must deduct zero, not propagate NULL and erase the player's
    score. nflverse writes NULL rather than 0 for positions that cannot record a reception."""
    _seed(con, "dst", "DST", 10.0, None)
    assert load_realized_points(con, 2024, 5, HALF_PPR)["dst"] == pytest.approx(10.0)


def test_players_who_did_not_play_are_absent_not_zero(con):
    """The production-forecast / availability split depends on this distinction. A player who
    did not play must be missing from the result, never present with 0.0 -- otherwise an
    inactive player is indistinguishable from one who played and was shut out."""
    _seed(con, "played_and_scored_zero", "WR", 0.0, 0.0)
    points = load_realized_points(con, 2024, 5, FULL_PPR)
    assert points["played_and_scored_zero"] == pytest.approx(0.0)
    assert "never_played" not in points


def test_only_ranked_positions_are_returned(con):
    """No IDP (PRODUCT). An offensive lineman with incidental receiving points must not enter
    the universe just because nflverse recorded a row for him."""
    _seed(con, "tackle", "OT", 6.0, 1.0)
    _seed(con, "wideout", "WR", 12.0, 4.0)
    points = load_realized_points(con, 2024, 5, FULL_PPR)
    assert "tackle" not in points
    assert "wideout" in points
    assert "OT" not in RANKED_POSITIONS


def test_shipped_formats_are_exactly_half_and_full():
    """W1 scoped two formats. `STANDARD` exists to make the identity checkable and must not
    silently become a third product format."""
    assert SHIPPED_FORMATS == (HALF_PPR, FULL_PPR)


def test_format_by_name_raises_rather_than_defaulting():
    assert format_by_name("half_ppr") is HALF_PPR
    with pytest.raises(ValueError, match="unknown scoring format"):
        format_by_name("ppr")


def test_full_ppr_expression_does_not_touch_receptions():
    """Full PPR must read the stored column directly. Emitting a `- 0.0 * receptions` term
    would make a NULL-receptions row NULL under some engines."""
    assert FULL_PPR.sql_expr("s") == "s.fantasy_points_ppr"
    assert "receptions" in ScoringFormat("x", 0.25).sql_expr("s")
