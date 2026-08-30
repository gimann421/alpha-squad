"""Startable-saturation of the VORP surplus (docs/DECISIONS.md D64, Hypothesis A).

D63 shipped `msv + VORP` and left a measured regression: the blend breaches the kicker cap in
32 of 50 drafts. Tracing a real hoarding draft established that late in a draft MSV is 0 for
every candidate, so the value base collapses to VORP alone — and VORP is measured against a
STATIC league-wide replacement level, so the heavily-drafted skill pools fall below replacement
while the barely-touched kicker pool stays above it.

These tests pin the structural properties that make the correction principled rather than a
per-position rule.
"""

from __future__ import annotations

import pytest

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.roster import (
    positional_feasibility_cap,
    saturated_surplus,
    startable_saturation,
    startable_slots,
)

TARGET = "src/alpha_squad/config/league_configs/target_league.yaml"


def _target() -> LeagueContext:
    return load_league_context(TARGET)


class TestStartableSaturation:
    def test_empty_roster_leaves_every_position_fully_unsaturated(self):
        assert all(v == pytest.approx(1.0) for v in startable_saturation(_target(), []).values())

    def test_k_saturates_after_one_because_it_has_no_flex_eligibility(self):
        """The distinction the directive requires to EMERGE from the lineup model rather than
        be hardcoded: K has 1 startable slot, so a second kicker can never start."""
        league = _target()
        assert startable_slots(league)["K"] == 1
        assert startable_saturation(league, ["K"])["K"] == pytest.approx(0.0)

    def test_rb_does_not_saturate_after_one_because_flex_accepts_it(self):
        """Same mechanism, opposite outcome, from the same config: RB has 2 dedicated + 2 FLEX
        = 4 startable slots, so a second RB retains most of its surplus."""
        league = _target()
        assert startable_slots(league)["RB"] == 4
        assert startable_saturation(league, ["RB"])["RB"] == pytest.approx(0.75)
        assert startable_saturation(league, ["RB", "RB", "RB"])["RB"] == pytest.approx(0.25)

    def test_a_second_kicker_and_a_third_rb_are_priced_differently_by_structure_alone(self):
        """The headline asymmetry, asserted directly: neither position is named in the
        implementation, yet a 2nd K keeps none of its surplus and a 3rd RB keeps a quarter."""
        league = _target()
        sat = startable_saturation(league, ["K", "RB", "RB"])
        assert sat["K"] == pytest.approx(0.0)
        assert sat["RB"] == pytest.approx(0.5)

    def test_saturation_never_goes_negative_when_over_startable(self):
        assert startable_saturation(_target(), ["K"] * 5)["K"] == pytest.approx(0.0)

    def test_a_league_without_flex_saturates_rb_after_its_dedicated_slots(self):
        """Config-driven, not format-specific: remove FLEX and RB behaves like K."""
        no_flex = LeagueContext(
            league_id="t",
            format="redraft",
            teams=10,
            lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
            roster={"bench": 6, "roster_size": 14},
        )
        assert startable_saturation(no_flex, ["RB", "RB"])["RB"] == pytest.approx(0.0)

    def test_superflex_keeps_qb_unsaturated_after_one(self):
        """The 2QB legacy config must reach the opposite conclusion about QB from the same code."""
        legacy = load_league_context(
            "src/alpha_squad/config/league_configs/legacy_2qb_dynasty.yaml"
        )
        assert startable_saturation(legacy, ["QB"])["QB"] > 0.0


class TestSaturatedSurplus:
    def test_full_saturation_leaves_surplus_untouched(self):
        assert saturated_surplus(30.1, 1.0) == pytest.approx(30.1)

    def test_zero_saturation_removes_the_entire_surplus(self):
        """The measured fix: the 2nd kicker's +30.1 surplus at round 11 goes to zero."""
        assert saturated_surplus(30.1, 0.0) == pytest.approx(0.0)

    def test_below_replacement_value_is_never_scaled(self):
        """Scaling the negative part would make a SATURATED position look better than an
        unsaturated one whenever both are below replacement — precisely backwards. At round 16
        of the traced draft every skill player was below replacement, so this is the regime
        that decides the late rounds."""
        for saturation in (0.0, 0.25, 0.5, 1.0):
            assert saturated_surplus(-123.0, saturation) == pytest.approx(-123.0)

    def test_partial_saturation_scales_only_the_surplus(self):
        assert saturated_surplus(4.8, 0.6666666666666666) == pytest.approx(3.2)

    def test_a_saturated_positive_never_outranks_an_unsaturated_positive_of_equal_size(self):
        assert saturated_surplus(10.0, 0.0) < saturated_surplus(10.0, 0.25)


class TestTracedPickIsCorrected:
    """The concrete pick this phase was opened to fix: 2023 draft slot 9, round 11, roster
    WR4/QB1/RB2/TE1/K1/DST1. Measured VORP surpluses at that pick were K +30.1, TE +4.8,
    RB +2.0 — so the shipped engine took a second kicker it could never start."""

    ROSTER = ["WR", "WR", "WR", "WR", "QB", "RB", "TE", "K", "RB", "DST"]

    def test_saturation_reorders_the_pick_away_from_the_unusable_second_kicker(self):
        sat = startable_saturation(_target(), self.ROSTER)
        k = saturated_surplus(30.1, sat["K"])
        te = saturated_surplus(4.8, sat["TE"])
        rb = saturated_surplus(2.0, sat["RB"])
        assert k == pytest.approx(0.0)
        assert te > k and rb > k
        assert max(k, te, rb) == te

    def test_the_over_cap_multiplier_is_not_even_engaged_at_that_pick(self):
        """Why Hypothesis B cannot fix this pick: the second kicker is taken while the roster
        is still UNDER the feasibility cap, so no over-cap multiplier applies at all."""
        league = _target()
        assert self.ROSTER.count("K") < positional_feasibility_cap(league, "K")
