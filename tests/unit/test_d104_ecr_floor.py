"""Unit tests for D104's ECR substitution (`scripts/research/d104_ecr_floor.py`).

The phase's whole claim is that `FP_ECR_Y1` changes INFORMATION and nothing else. That claim rests
on properties of one function, so they are pinned here rather than asserted in prose:

  * the multiset of projected values at every position is exactly Y1's -- otherwise replacement
    levels, scarcity and the positional value scale move too, and the arm is a new valuation
    function rather than an information change;
  * only the projections and their derived VORP change;
  * players the ECR board does not rank keep their Y1 value, so the candidate universe is
    identical and pool parity holds;
  * K and DST are untouched, because no ECR board ranks them;
  * ordering follows ECR rank ascending, with a deterministic `player_id` tie-break (D54);
  * no realized outcome is read.

Loaded the same way `test_board_vintage.py` loads `scripts/d92_paired_grid.py`."""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.league.context import LeagueContext


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "d104_ecr_floor.py"
    spec = importlib.util.spec_from_file_location("d104_ecr_floor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def _league() -> LeagueContext:
    """A real league, because `marginal_value_over_replacement` reads its lineup to find the
    replacement boundary. Small on purpose -- the substitution under test is positional, not
    format-specific."""
    return LeagueContext(
        league_id="d104_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1},
        roster={"bench": 2, "roster_size": 8},
    )


def _static(**overrides):
    """A `SeasonStatic` whose Y1 projection order DISAGREES with the ECR order, so a substitution
    that did nothing would be visible."""
    from alpha_squad.evaluation.draft_forensics import SeasonStatic

    positions = {
        "wr_a": "WR", "wr_b": "WR", "wr_c": "WR", "wr_unranked": "WR",
        "rb_a": "RB", "rb_b": "RB",
        "k_a": "K", "k_b": "K",
    }
    base = dict(
        season=2023,
        ecr_type="ro",
        # Y1 likes wr_a > wr_b > wr_c; ECR below reverses that.
        projections={
            "wr_a": 300.0, "wr_b": 250.0, "wr_c": 200.0, "wr_unranked": 111.0,
            "rb_a": 280.0, "rb_b": 240.0,
            "k_a": 130.0, "k_b": 120.0,
        },
        positions=positions,
        vorp={p: 0.0 for p in positions},
        replacement_levels={"WR": 150.0, "RB": 150.0, "K": 100.0},
        scarcity_raw={"WR": 1.0, "RB": 2.0, "K": 3.0},
        scarcity_norm={"WR": 0.1, "RB": 0.5, "K": 0.9},
        market_rank={
            "wr_a": ("WR", 30.0), "wr_b": ("WR", 20.0), "wr_c": ("WR", 10.0),
            "rb_a": ("RB", 8.0), "rb_b": ("RB", 4.0),
        },
        confidence={p: 0.7 for p in positions},
        ecr_dispersion={p: (1.0, 5.0) for p in positions},
        consumption_demand={"WR": 4.0, "RB": 3.0, "K": 1.0},
    )
    base.update(overrides)
    return SeasonStatic(**base)


class TestValuePreservation:
    def test_the_multiset_of_values_is_exactly_preserved_per_position(self):
        """The property that makes this an information change rather than a valuation change."""
        static = _static()
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        for position in ("WR", "RB", "K"):
            before = sorted(v for p, v in static.projections.items()
                            if static.positions[p] == position)
            after = sorted(v for p, v in out.projections.items()
                           if out.positions[p] == position)
            assert before == after, position

    def test_only_projections_and_vorp_change(self, monkeypatch):
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )
        static = _static()
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        changed = {
            f.name for f in dataclasses.fields(static)
            if getattr(out, f.name) != getattr(static, f.name)
        }
        assert changed == {"projections", "vorp"}, sorted(changed)

    def test_a_substitution_that_broke_the_multiset_is_refused(self, monkeypatch):
        """A guard that cannot fire is not a guard. Force the permutation to drop a value and
        confirm the invariant check raises rather than silently publishing a new value scale."""
        static = _static()

        real_sorted = sorted

        def _bad(values, *, key=None, reverse=False):
            """Corrupts ONLY the value list (the call that passes reverse=True), leaving the
            player ordering and the final invariant check on real `sorted`."""
            ordered = real_sorted(values, key=key, reverse=reverse)
            return [v + 1.0 for v in ordered] if reverse else ordered

        monkeypatch.setattr(MODULE, "sorted", _bad, raising=False)
        with pytest.raises(MODULE.SubstitutionError, match="multiset"):
            MODULE.ecr_ordered_static(_league(), static)


class TestOrdering:
    def test_values_follow_ecr_rank_ascending(self):
        """ECR ranks wr_c (10) best, then wr_b (20), then wr_a (30) -- the reverse of Y1. So the
        largest WR value must land on wr_c."""
        static = _static()
        out, moved = MODULE.ecr_ordered_static(_league(), static)
        assert out.projections["wr_c"] == 300.0
        assert out.projections["wr_b"] == 250.0
        assert out.projections["wr_a"] == 200.0
        assert moved > 0

    def test_unranked_players_keep_their_y1_value(self):
        static = _static()
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        assert out.projections["wr_unranked"] == static.projections["wr_unranked"]

    def test_the_candidate_universe_is_identical(self):
        static = _static()
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        assert set(out.projections) == set(static.projections)

    def test_kickers_and_defenses_are_untouched(self):
        """No ECR board ranks them; they come from the D57 baselines and stay there."""
        static = _static()
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        assert out.projections["k_a"] == static.projections["k_a"]
        assert out.projections["k_b"] == static.projections["k_b"]

    def test_ties_in_ecr_rank_break_on_player_id(self):
        """D54's determinism convention. Two players tied on ECR must order by `player_id`, so a
        re-run reproduces exactly."""
        static = _static(
            market_rank={
                "wr_a": ("WR", 10.0), "wr_b": ("WR", 10.0), "wr_c": ("WR", 10.0),
                "rb_a": ("RB", 8.0), "rb_b": ("RB", 4.0),
            }
        )
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        assert out.projections["wr_a"] == 300.0  # 'wr_a' < 'wr_b' < 'wr_c'
        assert out.projections["wr_b"] == 250.0
        assert out.projections["wr_c"] == 200.0

    def test_a_position_with_fewer_than_two_ranked_players_is_left_alone(self):
        static = _static(market_rank={"wr_a": ("WR", 30.0), "rb_a": ("RB", 8.0)})
        out, _ = MODULE.ecr_ordered_static(_league(), static)
        assert out.projections == static.projections


class TestRegisteredDesign:
    def test_the_three_arms_are_the_registered_ones(self):
        assert MODULE.ARMS == ("Y1", "FP_ECR_Y1", "ORACLE_Y1")

    def test_only_the_positions_m6_models_are_substituted(self):
        assert MODULE.SKILL == ("QB", "RB", "WR", "TE")

    def test_the_detection_floor_is_quoted_from_d97_not_re_derived(self):
        assert MODULE.DETECTION_FLOOR == (172.0, 250.0)

    def test_population_excludes_2020_and_2026(self):
        assert 2020 not in BACKTEST_SEASONS and 2026 not in BACKTEST_SEASONS
        assert MODULE.FORMATS == ("target_league", "dynasty_1qb")

    def test_no_realized_outcome_reaches_the_ecr_substitution(self):
        """`ecr_ordered_static` must read only `market_rank` and `projections`. If a future edit
        gives it an outcome argument this fails loudly, the same shape as the oracle's guard."""
        import inspect

        params = set(inspect.signature(MODULE.ecr_ordered_static).parameters)
        banned = ("actual", "realized", "outcome", "realised")
        assert not {p for p in params if any(b in p.lower() for b in banned)}
        source = inspect.getsource(MODULE.ecr_ordered_static)
        assert "_actual_points_for" not in source
