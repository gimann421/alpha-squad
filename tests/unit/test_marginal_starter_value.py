"""Marginal starter value and the M-tier ablation (docs/DECISIONS.md D58).

The gap this closes: VORP measures a player against a LEAGUE-WIDE replacement level and
`roster_need` measures a positional COUNT, so before D58 a player was scored identically
whether he would be your WR1 or your WR5. Nothing in the scoring path could ask whether a
candidate would actually start.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.draft_forensics import (
    M_TIERS,
    PREREGISTERED_M_CONTROL,
    TIER_DESCRIPTIONS,
    marginal_starter_multiplier,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import (
    best_lineup_points,
    compute_league_starters,
    marginal_starter_value,
)


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


PROJ = {
    "rb1": 300.0,
    "rb2": 260.0,
    "rb3": 220.0,
    "rb4": 180.0,
    "rb5": 140.0,
    "wr1": 290.0,
    "wr2": 250.0,
    "wr3": 210.0,
    "te1": 200.0,
    "qb1": 320.0,
    "k1": 130.0,
    "d1": 120.0,
    "superstar": 500.0,
}
POS = {
    "rb1": "RB",
    "rb2": "RB",
    "rb3": "RB",
    "rb4": "RB",
    "rb5": "RB",
    "wr1": "WR",
    "wr2": "WR",
    "wr3": "WR",
    "te1": "TE",
    "qb1": "QB",
    "k1": "K",
    "d1": "DST",
    "superstar": "RB",
}


def _msv(roster, candidate, league=None):
    return marginal_starter_value(league or _league(), roster, candidate, PROJ, POS)


class TestMarginalStarterValue:
    def test_filling_an_empty_slot_is_worth_the_full_projection(self):
        assert _msv([], "rb1") == pytest.approx(300.0)

    def test_a_player_who_cannot_start_is_worth_nothing(self):
        """RB's 2 dedicated slots and both FLEX slots are already held by better players."""
        full = ["rb1", "rb2", "rb3", "rb4", "wr1", "wr2", "te1"]
        assert _msv(full, "rb5") == pytest.approx(0.0)

    def test_an_upgrade_is_worth_the_margin_over_whoever_it_displaces(self):
        """The distinction VORP cannot make: `superstar` is not worth 500 to this roster, he
        is worth 500 minus the 180 the weakest current starter contributes."""
        full = ["rb1", "rb2", "rb3", "rb4", "wr1", "wr2", "te1"]
        assert _msv(full, "superstar") == pytest.approx(500.0 - 180.0)

    def test_the_same_player_is_worth_less_to_a_deeper_roster(self):
        """THE headline property. VORP would score `rb3` identically in both cases."""
        # The deep roster fills both RB slots, both WR slots, TE, and BOTH flex slots, so
        # rb3 can only enter by displacing rb4 rather than by filling a hole.
        thin = _msv(["wr1"], "rb3")
        deep = _msv(["rb1", "rb2", "rb4", "wr1", "wr2", "wr3", "te1"], "rb3")
        assert thin == pytest.approx(220.0)
        assert deep == pytest.approx(220.0 - 180.0)
        assert thin > deep

    def test_a_kicker_is_worth_his_projection_once_and_nothing_after(self):
        assert _msv([], "k1") == pytest.approx(130.0)
        assert _msv(["k1"], "k1") == pytest.approx(0.0)

    def test_it_is_never_negative(self):
        """Adding a player can never make the best available lineup worse."""
        roster = ["rb1", "rb2", "rb3", "rb4", "wr1", "wr2", "te1", "qb1", "k1", "d1"]
        for candidate in PROJ:
            assert _msv(roster, candidate) >= 0.0

    def test_a_hoisted_base_matches_computing_it_inline(self):
        """The per-pick optimization must not change the answer."""
        league, roster = _league(), ["rb1", "wr1"]
        base = best_lineup_points(league, roster, PROJ, POS)
        for candidate in ("rb2", "te1", "qb1"):
            hoisted = marginal_starter_value(league, roster, candidate, PROJ, POS, base_points=base)
            assert hoisted == pytest.approx(_msv(roster, candidate))

    def test_flex_eligibility_is_respected(self):
        """A QB cannot take a FLEX slot in this format, so a second QB is worth nothing even
        while FLEX slots sit empty."""
        assert _msv(["qb1"], "qb1") == pytest.approx(0.0)
        assert _msv(["qb1"], "rb1") > 0

    def test_a_superflex_league_values_a_second_quarterback(self):
        """League-contextual: the same roster and the same player, a different format."""
        sf = _league(lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "SUPERFLEX": 1})
        proj = dict(PROJ, qb2=280.0)
        pos = dict(POS, qb2="QB")
        assert marginal_starter_value(sf, ["qb1"], "qb2", proj, pos) > 0
        assert marginal_starter_value(_league(), ["qb1"], "qb2", proj, pos) == 0.0


class TestBestLineupPoints:
    def test_an_incomplete_roster_simply_leaves_slots_empty(self):
        assert best_lineup_points(_league(), ["rb1", "wr1"], PROJ, POS) == pytest.approx(590.0)

    def test_only_the_best_legal_lineup_counts_not_the_whole_roster(self):
        roster = ["rb1", "rb2", "rb3", "rb4", "rb5", "wr1", "wr2", "te1"]
        total = sum(PROJ[p] for p in roster)
        assert best_lineup_points(_league(), roster, PROJ, POS) < total

    def test_the_teams_override_matches_an_explicit_model_copy(self):
        """The optimization that removed a pydantic copy from the hot path must be a pure
        refactor."""
        league, roster = _league(), ["rb1", "rb2", "wr1"]
        proj = {p: PROJ[p] for p in roster}
        pos = {p: POS[p] for p in roster}
        via_override = compute_league_starters(league, proj, pos, teams=1)
        via_copy = compute_league_starters(league.model_copy(update={"teams": 1}), proj, pos)
        assert via_override == via_copy


class TestMarginalStarterMultiplier:
    def test_a_full_value_starter_reaches_the_ceiling(self):
        assert marginal_starter_multiplier(200.0, 200.0) == pytest.approx(1.3)

    def test_a_player_who_would_not_start_sits_at_the_floor(self):
        assert marginal_starter_multiplier(0.0, 200.0) == pytest.approx(0.7)

    def test_it_stays_bounded_for_out_of_range_inputs(self):
        assert marginal_starter_multiplier(1e6, 200.0) == pytest.approx(1.3)
        assert marginal_starter_multiplier(-50.0, 200.0) == pytest.approx(0.7)

    def test_a_zero_projection_falls_to_the_floor_rather_than_dividing_by_zero(self):
        assert marginal_starter_multiplier(10.0, 0.0) == pytest.approx(0.7)

    def test_it_matches_the_bounds_of_the_multiplier_it_can_replace(self):
        """M2 swaps one bounded multiplier for another rather than changing the score scale."""
        values = [marginal_starter_multiplier(m, 200.0) for m in (0, 50, 100, 150, 200)]
        assert min(values) == pytest.approx(0.7)
        assert max(values) == pytest.approx(1.3)


class TestPreRegistration:
    def test_the_control_is_the_shipped_production_formula(self):
        assert PREREGISTERED_M_CONTROL == "M0"
        assert "shipped production formula" in TIER_DESCRIPTIONS["M0"]

    def test_every_m_tier_is_described(self):
        for tier in M_TIERS:
            assert TIER_DESCRIPTIONS[tier]
