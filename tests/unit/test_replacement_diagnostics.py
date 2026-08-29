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
    available_pool_replacement,
    hybrid_capacity_replacement,
    remaining_demand_replacement,
)
from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.replacement import replacement_level

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
        assert set(REPLACEMENT_VARIANTS) == {
            "available_pool",
            "remaining_demand",
            "hybrid_capacity",
        }


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
