"""Flex-aware positional capacity for the 1-QB target format (docs/DECISIONS.md D58).

The pre-D58 model split the bench evenly across `dedicated_slots()` and ignored FLEX
entirely. That was survivable while the league had four positions and a 2-QB lineup; adding
K and DEF takes the divisor from 4 to 6 and the error becomes first-order, capping RB at 3
in a league that starts 2 RB plus up to 2 FLEX.
"""

from __future__ import annotations

import pytest

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.roster import (
    positional_capacity,
    positional_feasibility_cap,
    roster_fit_multiplier,
    roster_need,
    startable_slots,
)

TARGET_LINEUP = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1}


def _league(**overrides) -> LeagueContext:
    base = dict(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup=dict(TARGET_LINEUP),
        roster={"bench": 6, "roster_size": 16},
    )
    base.update(overrides)
    return LeagueContext(**base)


class TestTargetFormatLineup:
    """The format the product now optimizes for, slot by slot."""

    def test_one_qb_starter(self):
        assert _league().dedicated_slots()["QB"] == 1

    def test_two_rb_starters(self):
        assert _league().dedicated_slots()["RB"] == 2

    def test_two_wr_starters(self):
        assert _league().dedicated_slots()["WR"] == 2

    def test_one_te_starter(self):
        assert _league().dedicated_slots()["TE"] == 1

    def test_two_flex_slots_eligible_for_rb_wr_te(self):
        league = _league()
        assert league.flex_slots() == {"FLEX": 2}
        startable = startable_slots(league)
        # Each of RB/WR/TE gains both flex slots on top of its dedicated ones.
        assert startable["RB"] == 4
        assert startable["WR"] == 4
        assert startable["TE"] == 3

    def test_one_kicker_starter(self):
        assert _league().dedicated_slots()["K"] == 1

    def test_one_defense_starter_under_the_dst_position_name(self):
        assert _league().dedicated_slots()["DST"] == 1

    def test_a_quarterback_is_not_flex_eligible_in_this_format(self):
        """The distinction that makes this a 1-QB league rather than a superflex one."""
        assert startable_slots(_league())["QB"] == 1


class TestPositionalCapacity:
    def test_flex_eligible_positions_get_capacity_beyond_their_dedicated_slots(self):
        """REGRESSION. The pre-D58 formula capped RB at 3 here."""
        league = _league()
        assert positional_capacity(league, "RB") == 6
        assert positional_capacity(league, "WR") == 6
        assert positional_capacity(league, "TE") == 4

    def test_kicker_and_defense_get_minimal_capacity(self):
        """No real roster carries three kickers. The old even split handed them the same
        bench allowance as a running back."""
        league = _league()
        assert positional_capacity(league, "K") == 2
        assert positional_capacity(league, "DST") == 2

    def test_a_backup_quarterback_is_never_structurally_forbidden(self):
        assert positional_capacity(_league(), "QB") == 2

    def test_a_position_the_league_cannot_start_has_no_capacity(self):
        assert positional_capacity(_league(), "LB") == 0

    def test_capacity_grows_with_the_configured_bench(self):
        deep = _league(roster={"bench": 12, "roster_size": 22})
        shallow = _league(roster={"bench": 2, "roster_size": 12})
        assert positional_capacity(deep, "RB") > positional_capacity(shallow, "RB")

    def test_a_superflex_league_gives_quarterbacks_more_capacity(self):
        """League-contextual, derived from config alone."""
        sf = _league(lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "SUPERFLEX": 1})
        assert startable_slots(sf)["QB"] == 2
        assert positional_capacity(sf, "QB") > positional_capacity(_league(), "QB")

    def test_the_feasibility_cap_is_the_capacity(self):
        league = _league()
        for position in ("QB", "RB", "WR", "TE", "K", "DST"):
            assert positional_feasibility_cap(league, position) == positional_capacity(
                league, position
            )

    def test_the_shipped_target_config_produces_these_capacities(self):
        """Guards the real file, not just a synthetic league built in this test."""
        league = load_league_context()
        caps = {p: positional_capacity(league, p) for p in league.dedicated_slots()}
        assert caps == {"QB": 2, "RB": 6, "WR": 6, "TE": 4, "K": 2, "DST": 2}


class TestRosterNeed:
    def test_an_empty_roster_needs_exactly_the_starting_slots(self):
        assert roster_need(_league(), []) == {
            "QB": 1.0,
            "RB": 2.0,
            "WR": 2.0,
            "TE": 1.0,
            "K": 1.0,
            "DST": 1.0,
        }

    def test_need_falls_to_a_mild_positive_once_starters_are_filled(self):
        """RB has 2 dedicated slots but 4 startable, so a third RB still has real value."""
        need = roster_need(_league(), ["RB", "RB"])
        assert 0 < need["RB"] < 1

    def test_need_goes_negative_past_what_the_position_could_ever_start(self):
        need = roster_need(_league(), ["RB"] * 5)
        assert need["RB"] < 0

    def test_a_second_kicker_is_already_past_the_depth_target(self):
        """The old `slots + 2` constant would have asked for three of them."""
        assert roster_need(_league(), ["K"])["K"] <= 0
        assert roster_need(_league(), ["K", "K"])["K"] < 0

    def test_saturation_reaches_the_multiplier_floor_promptly(self):
        """D54: the old -0.2 coefficient took ~15 extra players at one position to bite."""
        need = roster_need(_league(), ["QB", "QB", "QB"])
        assert roster_fit_multiplier(need["QB"]) == pytest.approx(0.7)

    def test_need_is_reported_for_every_dedicated_position_including_k_and_def(self):
        assert set(roster_need(_league(), [])) == {"QB", "RB", "WR", "TE", "K", "DST"}
