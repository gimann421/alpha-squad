"""Draft-aware replacement levels, diagnostic-only (docs/DECISIONS.md D65).

Production computes VORP from the full-season pool every pick, so the replacement level is
numerically identical at pick 1 and pick 160. These tests pin the three counterfactual
definitions that quantify what that staleness costs, and — importantly — assert the module
stays OUT of production.
"""

from __future__ import annotations

import pytest

from alpha_squad.evaluation.replacement_diagnostics import (
    REPLACEMENT_VARIANTS,
    SWEEP_SCALES,
    available_pool_replacement,
    consumption_replacement,
    dedicated_plus_one_bench_replacement,
    earned_starter_replacement,
    hybrid_capacity_replacement,
    mock_draft_consumption_demand,
    remaining_demand_replacement,
    scaled_startable_replacement,
)
from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.replacement import compute_league_starters, replacement_level
from alpha_squad.league.roster import startable_slots

TARGET = "src/alpha_squad/config/league_configs/target_league.yaml"


def _target() -> LeagueContext:
    return load_league_context(TARGET)


def _pool(n_per_pos: int = 60) -> tuple[dict[str, float], dict[str, str]]:
    """A synthetic board with a strictly decreasing projection per position, so the identity of
    the replacement-level player is unambiguous at every demand boundary."""
    projections: dict[str, float] = {}
    positions: dict[str, str] = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
        for i in range(n_per_pos):
            pid = f"{pos}_{i:03d}"
            projections[pid] = 400.0 - i
            positions[pid] = pos
    return projections, positions


class TestModuleIsDiagnosticOnly:
    def test_production_draft_engine_does_not_import_it(self):
        """The whole module is a measurement instrument. If production ever imports it, the
        control and the candidate stop being separable."""
        source = __import__("pathlib").Path("src/alpha_squad/league/draft.py").read_text()
        assert "replacement_diagnostics" not in source

    def test_every_variant_is_registered(self):
        named = {
            "available_pool",
            "remaining_demand",
            "hybrid_capacity",
            "dedicated_plus_one_bench",
            "earned_starter",
        }
        sweep = {f"scale_{sc}" for sc in SWEEP_SCALES}
        assert set(REPLACEMENT_VARIANTS) == named | sweep


class TestCandidateAAvailablePool:
    def test_on_a_full_board_it_equals_production_static_replacement(self):
        """The control property: with nothing drafted, a draft-aware level must reproduce the
        static one exactly, or differences later cannot be attributed to depletion."""
        league = _target()
        projections, positions = _pool()
        static = replacement_level(league, projections, positions)
        dynamic = available_pool_replacement(league, set(projections), projections, positions)
        for pos, level in static.items():
            assert dynamic[pos] == pytest.approx(level)

    def test_depleting_a_position_lowers_its_replacement_level(self):
        """The measured defect: strip the top of a pool and the static level does not move."""
        league = _target()
        projections, positions = _pool()
        available = {p for p in projections if not (p.startswith("WR_") and int(p[3:]) < 30)}
        static = replacement_level(league, projections, positions)
        dynamic = available_pool_replacement(league, available, projections, positions)
        assert dynamic["WR"] < static["WR"]
        # untouched positions are unaffected
        assert dynamic["K"] == pytest.approx(static["K"])

    def test_an_exhausted_position_reports_zero_rather_than_raising(self):
        league = _target()
        projections, positions = _pool()
        available = {p for p in projections if not p.startswith("K_")}
        assert available_pool_replacement(league, available, projections, positions)["K"] == (
            pytest.approx(0.0)
        )


class TestCandidateBRemainingDemand:
    def test_replacement_sits_at_the_league_wide_demand_boundary(self):
        """B's definition: demand is `teams x startable_slots`. The target league starts one
        kicker per team, so with nothing drafted the boundary is the 11th-best kicker
        (0-indexed 10) — and K projections here run 400, 399, 398, ... so that is 390."""
        league = _target()
        projections, positions = _pool()
        levels = remaining_demand_replacement(league, set(projections), projections, positions)
        assert levels["K"] == pytest.approx(390.0)

    def test_a_position_the_league_no_longer_needs_prices_its_surplus_at_zero(self):
        """The structural point, with no position named: once the league's ten kicker slots are
        absorbed, remaining demand is 0, so replacement becomes the BEST available kicker and a
        surplus kicker carries no surplus at all."""
        league = _target()
        projections, positions = _pool()
        available = {p for p in projections if not (p.startswith("K_") and int(p[2:]) < 10)}
        levels = remaining_demand_replacement(league, available, projections, positions)
        best_available_k = max(
            (projections[p] for p in available if positions[p] == "K"), default=0.0
        )
        assert levels["K"] == pytest.approx(best_available_k)

    def test_wr_stays_contested_far_longer_than_k_from_the_lineup_alone(self):
        """WR needs 10 x 4 = 40 league-wide, K needs 10 x 1 = 10 — a 4x difference that comes
        from `startable_slots`, not from any per-position rule."""
        league = _target()
        projections, positions = _pool()
        drafted = 12
        available = {
            p
            for p in projections
            if not (p.startswith(("K_", "WR_")) and int(p.split("_")[1]) < drafted)
        }
        levels = remaining_demand_replacement(league, available, projections, positions)
        best_k = max(projections[p] for p in available if positions[p] == "K")
        best_wr = max(projections[p] for p in available if positions[p] == "WR")
        assert levels["K"] == pytest.approx(best_k)  # demand exhausted
        assert levels["WR"] < best_wr  # still contested


class TestCandidateCHybridCapacity:
    def test_it_uses_the_existing_positional_capacity_not_a_new_constant(self):
        """C's bench component is `positional_capacity` (K 2, WR 6), the same function
        `positional_feasibility_cap` already relies on, so C's demand is exactly double B's for
        a position whose capacity doubles its startable count."""
        league = _target()
        projections, positions = _pool()
        b = remaining_demand_replacement(league, set(projections), projections, positions)
        c = hybrid_capacity_replacement(league, set(projections), projections, positions)
        # K: startable 1 -> demand 10 -> index 10 (390.0); capacity 2 -> demand 20 -> 380.0
        assert b["K"] == pytest.approx(390.0)
        assert c["K"] == pytest.approx(380.0)

    def test_c_is_never_above_b_because_it_demands_at_least_as_many(self):
        league = _target()
        projections, positions = _pool()
        b = remaining_demand_replacement(league, set(projections), projections, positions)
        c = hybrid_capacity_replacement(league, set(projections), projections, positions)
        for pos in b:
            assert c[pos] <= b[pos] + 1e-9


class TestDeterminism:
    def test_every_variant_is_deterministic_over_a_set_input(self):
        """`available` is a Python set and PYTHONHASHSEED is unset, so anything iterating it
        without an explicit ordering can differ between runs (D54)."""
        league = _target()
        projections, positions = _pool()
        available = {p for p in projections if hash(p) % 3}
        for fn in REPLACEMENT_VARIANTS.values():
            first = fn(league, available, projections, positions)
            for _ in range(3):
                assert fn(league, set(available), projections, positions) == first


class TestFlexOverCountIsTheTELoadingMechanism:
    """D66: the defect behind D65's Gate 3 failure. `startable_slots` counts every FLEX slot
    once per ELIGIBLE position, so the demand target it produces cannot match the lineup."""

    def test_startable_slots_sums_to_more_than_the_lineup_actually_starts(self):
        league = _target()
        startable = startable_slots(league)
        lineup_starters = sum(league.dedicated_slots().values()) + sum(league.flex_slots().values())
        assert lineup_starters == 10
        # 2 FLEX slots counted once each for RB, WR and TE => +4 over the true lineup
        assert sum(startable.values()) == 14

    def test_te_startable_assumes_it_wins_both_flex_slots(self):
        league = _target()
        assert startable_slots(league)["TE"] == 3  # 1 dedicated + 2 FLEX
        assert league.dedicated_slots()["TE"] == 1

    def test_earned_starter_target_sums_to_exactly_the_lineup(self):
        """C5's defining property, and the one C2/C3 violate."""
        league = _target()
        projections, positions = _pool()
        result = compute_league_starters(league, projections, positions)
        earned = {}
        for pos in startable_slots(league):
            n_flex = sum(1 for p in result["flex_starters"] if positions[p] == pos)
            earned[pos] = len(result["dedicated_starters"].get(pos, [])) + n_flex
        assert sum(earned.values()) == league.teams * 10


class TestCandidateC4DedicatedPlusOneBench:
    def test_target_is_dedicated_plus_one_uniformly(self):
        """QB 1+1, RB 2+1, WR 2+1, TE 1+1, K 1+1, DEF 1+1 -- flex ignored entirely."""
        league = _target()
        projections, positions = _pool()
        levels = dedicated_plus_one_bench_replacement(
            league, set(projections), projections, positions
        )
        # TE target 2 -> league demand 20 -> replacement is the 21st best TE (400-20 = 380)
        assert levels["TE"] == pytest.approx(380.0)
        # RB target 3 -> demand 30 -> 31st best RB
        assert levels["RB"] == pytest.approx(370.0)

    def test_it_demands_less_te_than_the_capacity_hybrid(self):
        league = _target()
        projections, positions = _pool()
        c3 = hybrid_capacity_replacement(league, set(projections), projections, positions)
        c4 = dedicated_plus_one_bench_replacement(league, set(projections), projections, positions)
        # a HIGHER replacement level means the position is treated as LESS contested
        assert c4["TE"] > c3["TE"]


class TestCandidateC5EarnedStarter:
    def test_te_demand_collapses_to_its_real_earned_share(self):
        """With a synthetic board where every position has identical projections, TE wins no
        flex slots, so its earned demand is exactly its dedicated count."""
        league = _target()
        projections, positions = _pool()
        levels = earned_starter_replacement(league, set(projections), projections, positions)
        result = compute_league_starters(league, projections, positions)
        n_flex_te = sum(1 for p in result["flex_starters"] if positions[p] == "TE")
        earned_te = len(result["dedicated_starters"].get("TE", [])) + n_flex_te
        pool = sorted(
            (p for p in projections if positions[p] == "TE"), key=lambda p: -projections[p]
        )
        assert levels["TE"] == pytest.approx(projections[pool[earned_te]])

    def test_it_treats_te_as_less_contested_than_every_flex_inheriting_candidate(self):
        league = _target()
        projections, positions = _pool()
        c2 = remaining_demand_replacement(league, set(projections), projections, positions)
        c3 = hybrid_capacity_replacement(league, set(projections), projections, positions)
        c5 = earned_starter_replacement(league, set(projections), projections, positions)
        assert c5["TE"] > c2["TE"]
        assert c5["TE"] > c3["TE"]

    def test_it_adapts_to_a_format_where_te_would_win_flex(self):
        """Not a TE rule: in a TE-only-flex league TE's earned demand rises automatically."""
        te_flex = LeagueContext(
            league_id="t",
            format="redraft",
            teams=10,
            lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
            roster={"bench": 6, "roster_size": 16},
        )
        projections, positions = _pool()
        # make TE the best flex option outright
        for pid in list(projections):
            if positions[pid] == "TE":
                projections[pid] += 1000.0
        result = compute_league_starters(te_flex, projections, positions)
        n_flex_te = sum(1 for p in result["flex_starters"] if positions[p] == "TE")
        assert n_flex_te > 0


class TestDemandDepthSweep:
    """D66: demand depth is the governing parameter. A target too shallow EXHAUSTS -- remaining
    demand hits zero, the replacement level becomes the best available player, and that
    position's surplus is identically zero. That is what sank Candidates C4 and C5."""

    def test_a_shallow_target_exhausts_and_zeroes_the_surplus(self):
        league = _target()
        projections, positions = _pool()
        # 15 kickers gone: a 0.75x target demands only round(10 x 0.75) = 8, long since met
        available = {p for p in projections if not (p.startswith("K_") and int(p[2:]) < 15)}
        shallow = scaled_startable_replacement(0.75)(league, available, projections, positions)
        best_k = max(projections[p] for p in available if positions[p] == "K")
        assert shallow["K"] == pytest.approx(best_k)  # exhausted -> zero surplus

    def test_a_deep_target_still_discriminates(self):
        league = _target()
        projections, positions = _pool()
        # same 15 gone, but a 2.5x target demands 25, so 10 units of demand remain
        available = {p for p in projections if not (p.startswith("K_") and int(p[2:]) < 15)}
        deep = scaled_startable_replacement(2.5)(league, available, projections, positions)
        best_k = max(projections[p] for p in available if positions[p] == "K")
        assert deep["K"] < best_k  # still below the best available -> surplus survives

    def test_depth_is_monotone_in_scale(self):
        league = _target()
        projections, positions = _pool()
        levels = [
            scaled_startable_replacement(sc)(league, set(projections), projections, positions)["WR"]
            for sc in (1.0, 1.5, 2.0, 2.5)
        ]
        assert all(a >= b for a, b in zip(levels, levels[1:], strict=False))

    def test_the_structural_threshold_matches_the_draft_size(self):
        """The plateau's explanation: league-wide demand must exceed the picks a draft actually
        consumes, or exhaustion is reachable. 160 picks / 140 at scale 1.0 => scale > 1.14."""
        league = _target()
        per_team = sum(startable_slots(league).values())
        picks = league.teams * int(league.roster["roster_size"])
        assert picks == 160
        assert league.teams * per_team == 140
        assert picks / (league.teams * per_team) == pytest.approx(1.142857, abs=1e-5)


class TestMockDraftConsumptionDemand:
    """D67: the demand target with no free parameter -- what a full draft of this league
    actually consumes, counted off the preseason consensus board."""

    @staticmethod
    def _board(projections, positions) -> dict[str, tuple[str, float]]:
        """A consensus board that ranks by projection, so the mock draft is deterministic and
        its positional allocation is predictable from the pool alone."""
        return {
            pid: (positions[pid], float(rank))
            for rank, pid in enumerate(sorted(projections, key=lambda p: -projections[p]), 1)
        }

    def test_target_sums_to_roster_size(self):
        """The structural anchor: a draft makes exactly `teams x roster_size` picks, so demand
        summed over positions must equal `roster_size` per team -- not the lineup size (10),
        not `startable_slots` (14), not `positional_capacity` (22)."""
        league = _target()
        projections, positions = _pool()
        target = mock_draft_consumption_demand(
            league, self._board(projections, positions), projections, positions
        )
        assert sum(target.values()) == pytest.approx(float(league.roster["roster_size"]))

    def test_every_mandatory_position_keeps_at_least_its_dedicated_requirement(self):
        """A board that omits a position entirely must not collapse its demand to zero on pick
        1 -- the real `ro` board carries no kickers in its top 160 in any season."""
        league = _target()
        projections, positions = _pool()
        board = self._board(projections, positions)
        no_kickers = {p: v for p, v in board.items() if positions[p] != "K"}
        target = mock_draft_consumption_demand(league, no_kickers, projections, positions)
        assert target["K"] >= league.dedicated_slots()["K"]

    def test_it_adapts_to_the_league_format(self):
        """Format-adaptivity is the whole claim that this is derived rather than hardcoded: the
        2QB league must demand more QBs per team than the 1QB league, from the config alone."""
        projections, positions = _pool()
        board = self._board(projections, positions)
        one_qb = mock_draft_consumption_demand(_target(), board, projections, positions)
        two_qb = mock_draft_consumption_demand(
            load_league_context("src/alpha_squad/config/league_configs/legacy_2qb_dynasty.yaml"),
            board,
            projections,
            positions,
        )
        assert two_qb["QB"] > one_qb["QB"]

    def test_consumption_replacement_uses_the_target_it_is_given(self):
        league = _target()
        projections, positions = _pool()
        shallow = consumption_replacement({"K": 1.0})(
            league, set(projections), projections, positions
        )
        deep = consumption_replacement({"K": 3.0})(league, set(projections), projections, positions)
        assert deep["K"] < shallow["K"]

    def test_a_full_pool_prices_the_boundary_player_not_the_best_one(self):
        league = _target()
        projections, positions = _pool()
        levels = consumption_replacement({"WR": 5.0})(
            league, set(projections), projections, positions
        )
        # demand 10 x 5 = 50 -> the 51st-best WR (0-indexed 50), a real boundary, not WR1
        assert levels["WR"] == pytest.approx(projections["WR_050"])
