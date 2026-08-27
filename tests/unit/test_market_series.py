"""Which consensus board a league resolves to, and why `ecr_type` alone is not a rank space
(docs/DECISIONS.md D56).

The bug these cover is not hypothetical. Before D56 the draft benchmark scored a league
against `ecr_type='rsf'` -- FantasyPros' *superflex* board -- and read `ecr_type='ro'` as if
it were one ranking when it actually merges two independently-ranked pages.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import (
    DYNASTY_1QB,
    DYNASTY_SUPERFLEX,
    REDRAFT_1QB,
    REDRAFT_SUPERFLEX,
    is_superflex,
    resolve_market_series,
    series_for_ecr_type,
)
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league(**overrides) -> LeagueContext:
    base = dict(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
        roster={"bench": 6, "roster_size": 16},
    )
    base.update(overrides)
    return LeagueContext(**base)


class TestSuperflexDetection:
    def test_one_qb_slot_with_a_normal_flex_is_not_superflex(self):
        assert is_superflex(_league()) is False

    def test_two_dedicated_qb_slots_is_superflex(self):
        assert is_superflex(_league(lineup={"QB": 2, "RB": 2, "WR": 2, "TE": 1})) is True

    def test_a_qb_eligible_flex_is_superflex(self):
        """A 1-QB lineup plus a SUPERFLEX slot lets a team start two QBs, which moves the QB
        market exactly the way a second dedicated slot does."""
        lineup = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "SUPERFLEX": 1}
        assert is_superflex(_league(lineup=lineup)) is True

    def test_sleepers_underscore_spelling_is_recognised(self):
        """Sleeper's real roster_positions spelling is SUPER_FLEX (D33)."""
        lineup = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "SUPER_FLEX": 1}
        assert is_superflex(_league(lineup=lineup)) is True

    def test_a_zero_count_superflex_slot_does_not_count(self):
        lineup = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "SUPERFLEX": 0}
        assert is_superflex(_league(lineup=lineup)) is False


class TestSeriesResolution:
    def test_the_target_format_resolves_to_the_one_qb_redraft_board(self):
        assert resolve_market_series(_league()) == REDRAFT_1QB

    def test_a_superflex_redraft_league_resolves_to_the_superflex_board(self):
        league = _league(lineup={"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2})
        assert resolve_market_series(league) == REDRAFT_SUPERFLEX

    def test_dynasty_formats_resolve_to_the_dynasty_boards(self):
        assert resolve_market_series(_league(format="dynasty")) == DYNASTY_1QB
        sf = _league(format="dynasty", lineup={"QB": 2, "RB": 2, "WR": 2, "TE": 1})
        assert resolve_market_series(sf) == DYNASTY_SUPERFLEX

    def test_keeper_is_treated_as_a_dynasty_horizon(self):
        assert resolve_market_series(_league(format="keeper")) == DYNASTY_1QB

    def test_format_matching_is_case_and_whitespace_insensitive(self):
        """`format` is free-form and can arrive from Sleeper, so it is matched loosely."""
        assert resolve_market_series(_league(format="  Dynasty  ")) == DYNASTY_1QB

    def test_an_unknown_ecr_type_raises_rather_than_guessing_a_page(self):
        """Defaulting a page_type would silently reintroduce the merged-rank-space bug."""
        with pytest.raises(ValueError, match="unknown ecr_type"):
            series_for_ecr_type("not_a_series")

    def test_every_known_series_round_trips(self):
        for series in (REDRAFT_1QB, REDRAFT_SUPERFLEX, DYNASTY_1QB, DYNASTY_SUPERFLEX):
            assert series_for_ecr_type(series.ecr_type) is series


def _seed(con, player_id, position, rank, *, page_type, ecr_type="ro", season=2025):
    con.execute(
        "INSERT INTO market_snapshot "
        "(player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [player_id, f"{season}-08-01", ecr_type, position, rank, page_type],
    )


class TestPreseasonBoardIsOneRankSpace:
    def test_idp_rows_are_excluded_from_the_ro_board(self, con):
        """REGRESSION (D56). 'ro' carries FantasyPros' PPR draft board AND a separately-ranked
        IDP board. Merged, they produce colliding ranks -- in the real preseason-2024 data,
        'ro' rank 3.0 was simultaneously an LB and a WR -- so "best available by ECR" could
        return a linebacker in a league that cannot start one."""
        _seed(con, "wr1", "WR", 3.0, page_type="redraft-overall")
        _seed(con, "lb1", "LB", 3.0, page_type="redraft-idp")
        board = _preseason_overall_market(con, "ro", 2025)
        assert set(board) == {"wr1"}

    def test_the_resulting_board_has_no_colliding_ranks(self, con):
        for i, pid in enumerate(["a", "b", "c"], start=1):
            _seed(con, pid, "WR", float(i), page_type="redraft-overall")
            _seed(con, f"idp_{pid}", "LB", float(i), page_type="redraft-idp")
        board = _preseason_overall_market(con, "ro", 2025)
        ranks = [rank for _, rank in board.values()]
        assert len(ranks) == len(set(ranks)) == 3

    def test_an_explicit_page_type_overrides_the_resolved_one(self, con):
        _seed(con, "lb1", "LB", 3.0, page_type="redraft-idp")
        assert _preseason_overall_market(con, "ro", 2025) == {}
        explicit = _preseason_overall_market(con, "ro", 2025, page_type="redraft-idp")
        assert set(explicit) == {"lb1"}

    def test_an_ecr_type_with_no_known_series_is_left_unscoped(self, con):
        """The live FantasyPros capture (D38) has a single page by construction. Filtering it
        on a page_type nothing wrote would silently return an empty board."""
        _seed(con, "p1", "WR", 1.0, page_type="live-draft-overall", ecr_type="draft_overall")
        assert set(_preseason_overall_market(con, "draft_overall", 2025)) == {"p1"}

    def test_superflex_and_one_qb_boards_do_not_bleed_into_each_other(self, con):
        _seed(con, "qb_sf", "QB", 1.0, page_type="redraft-op", ecr_type="rsf")
        _seed(con, "rb_1qb", "RB", 1.0, page_type="redraft-overall", ecr_type="ro")
        assert set(_preseason_overall_market(con, "ro", 2025)) == {"rb_1qb"}
        assert set(_preseason_overall_market(con, "rsf", 2025)) == {"qb_sf"}
