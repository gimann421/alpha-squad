"""Unit tests for D103's research runner (`scripts/research/d103_pick_regret.py`).

Two properties carry the phase's conclusions and would be silent if they broke:

  * `oracle_static` -- the ORACLE_Y1 cell -- must change ONLY the projections and the quantities
    derived from them. If it also moved the market board or the confidence inputs it would be
    changing the environment or the decision rule, and "information effect" would be a misnomer.
  * the registered phase convention must stay what D103 registered, since every phase-level claim
    in the report is stated against it.

Loaded the same way `test_board_vintage.py` loads `scripts/d92_paired_grid.py`."""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.draft_oracle import SHIPPED_TIER


def _load():
    path = (
        Path(__file__).resolve().parents[2] / "scripts" / "research" / "d103_pick_regret.py"
    )
    spec = importlib.util.spec_from_file_location("d103_pick_regret", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


class TestRegisteredConvention:
    def test_phases_partition_every_round_of_the_shipped_roster_size(self):
        """EARLY 1-5, MIDDLE 6-10, LATE 11-16 -- contiguous, non-overlapping, covering all 16."""
        covered = [r for rounds in MODULE.PHASES.values() for r in rounds]
        assert sorted(covered) == list(range(1, 17))
        assert len(covered) == len(set(covered)), "phases must not overlap"

    def test_phase_of_maps_the_boundaries_the_report_quotes(self):
        assert MODULE.phase_of(1) == MODULE.phase_of(5) == "EARLY (1-5)"
        assert MODULE.phase_of(6) == MODULE.phase_of(10) == "MIDDLE (6-10)"
        assert MODULE.phase_of(11) == MODULE.phase_of(16) == "LATE (11-16)"

    def test_population_is_the_board_contract_window(self):
        assert BACKTEST_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert 2020 not in BACKTEST_SEASONS and 2026 not in BACKTEST_SEASONS

    def test_both_shipped_one_qb_formats_are_measured(self):
        assert MODULE.FORMATS == ("target_league", "dynasty_1qb")

    def test_the_rollout_policy_is_the_shipped_tier(self):
        assert SHIPPED_TIER == "L0"
        assert set(MODULE.DEFAULT_SLOTS) <= set(range(1, 11))


class TestOracleStaticScope:
    """Part 5's "establish what information it is allowed to change"."""

    def _fake_static(self):
        """A `SeasonStatic`-shaped stand-in. Built as a real dataclass instance so
        `dataclasses.replace` and field enumeration behave exactly as they do in the runner."""
        from alpha_squad.evaluation.draft_forensics import SeasonStatic

        players = {"QB_1": "QB", "RB_1": "RB", "WR_1": "WR"}
        return SeasonStatic(
            season=2023,
            ecr_type="ro",
            projections={"QB_1": 300.0, "RB_1": 250.0, "WR_1": 200.0},
            positions=players,
            vorp={"QB_1": 100.0, "RB_1": 80.0, "WR_1": 60.0},
            replacement_levels={"QB": 200.0, "RB": 170.0, "WR": 140.0},
            scarcity_raw={"QB": 1.0, "RB": 2.0, "WR": 3.0},
            scarcity_norm={"QB": 0.1, "RB": 0.5, "WR": 0.9},
            market_rank={"QB_1": ("QB", 1.0), "RB_1": ("RB", 2.0), "WR_1": ("WR", 3.0)},
            confidence={"QB_1": 0.8, "RB_1": 0.7, "WR_1": 0.6},
            ecr_dispersion={"QB_1": (1.0, 4.0), "RB_1": (2.0, 5.0), "WR_1": (3.0, 6.0)},
            consumption_demand={"QB": 1.2, "RB": 3.4, "WR": 4.1},
        )

    def test_only_projection_derived_fields_change(self, monkeypatch):
        """The narrow-scope guarantee. Everything that is NOT a function of the projections --
        the market board, the opponents' input, the uncertainty inputs, the consensus-board
        demand -- must come through untouched, or "information effect" is measuring the wrong
        thing."""
        static = self._fake_static()
        realized = {"QB_1": 120.0, "RB_1": 330.0, "WR_1": 275.0}
        monkeypatch.setattr(MODULE, "_actual_points_for", lambda con, season, ids: realized)
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )

        out = MODULE.oracle_static(None, object(), 2023, static)

        changed = {
            f.name
            for f in dataclasses.fields(static)
            if getattr(out, f.name) != getattr(static, f.name)
        }
        assert changed == {"projections", "vorp"}, (
            f"ORACLE_Y1 changed {sorted(changed)}; only projections and their derived VORP may move"
        )

    def test_projections_become_the_realized_outcomes(self, monkeypatch):
        static = self._fake_static()
        realized = {"QB_1": 120.0, "RB_1": 330.0, "WR_1": 275.0}
        monkeypatch.setattr(MODULE, "_actual_points_for", lambda con, season, ids: realized)
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )
        out = MODULE.oracle_static(None, object(), 2023, static)
        assert out.projections == realized
        assert out.projections != static.projections, "the arm must actually change information"

    def test_a_player_with_no_realized_row_scores_zero_not_his_projection(self, monkeypatch):
        """A drafted player who never played really did score nothing. Falling back to the
        projection would quietly re-introduce the very information this arm replaces."""
        static = self._fake_static()
        monkeypatch.setattr(
            MODULE, "_actual_points_for", lambda con, season, ids: {"QB_1": 120.0}
        )
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )
        out = MODULE.oracle_static(None, object(), 2023, static)
        assert out.projections["RB_1"] == 0.0
        assert out.projections["WR_1"] == 0.0


class TestLeakageQuarantine:
    def test_regret_mode_and_oracle_y1_mode_are_separate_names(self):
        """ORACLE_Y1 deliberately feeds outcomes into the policy's inputs, which is exactly what
        the regret measurement must never do. They are kept in different modes writing different
        artifacts so a reader can never mistake one for the other."""
        assert MODULE.run_regret is not MODULE.run_oracle_y1
        # The regret path never receives an oracle-substituted board: `oracle_static` is reachable
        # only from `run_oracle_y1`, and the two write different artifact filenames.
        import inspect

        assert "oracle_static" not in inspect.getsource(MODULE.run_regret)
        assert "oracle_static" in inspect.getsource(MODULE.run_oracle_y1)

    def test_the_shipped_leakage_guard_still_passes(self):
        from alpha_squad.evaluation.draft_oracle import assert_no_realized_inputs_in_policy

        assert_no_realized_inputs_in_policy()

    def test_near_zero_threshold_is_declared_not_tuned(self):
        """`NEAR_ZERO` classifies "this pick was essentially optimal". It is a reporting bucket,
        declared once, and must stay far below any regret magnitude the phase discusses."""
        assert pytest.approx(1.0) == MODULE.NEAR_ZERO
