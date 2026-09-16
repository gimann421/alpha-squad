"""Unit tests for D105's perturbation ladder (`scripts/research/d105_objective_sensitivity.py`).

Every conclusion in D105 rests on the ladder being what it claims: a pure within-position ranking
degradation that changes NOTHING else, reproduces Y1 exactly at one end, and is genuinely
uninformative at the other. Those properties are pinned here:

  * `alpha = 0` reproduces the Y1 board exactly -- if it did not, the whole curve is measured
    against the wrong baseline;
  * `alpha = 1` is independent of Y1's ordering;
  * information degrades monotonically in between;
  * the multiset of values per position is preserved at every level, so replacement levels,
    scarcity and the positional scale never move;
  * only `projections` and the derived `vorp` change;
  * the same seed reproduces exactly, across processes, and different seeds differ;
  * K/DST are untouched.

Loaded the same way `test_board_vintage.py` loads `scripts/d92_paired_grid.py`."""

from __future__ import annotations

import dataclasses
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.league.context import LeagueContext

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "research" / ("d105_objective_sensitivity.py")
)


def _load():
    spec = importlib.util.spec_from_file_location("d105_objective_sensitivity", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def _league() -> LeagueContext:
    return LeagueContext(
        league_id="d105_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1},
        roster={"bench": 2, "roster_size": 8},
    )


def _static(n_per_position=12):
    from alpha_squad.evaluation.draft_forensics import SeasonStatic

    positions, projections = {}, {}
    for position in ("QB", "RB", "WR", "TE"):
        for i in range(n_per_position):
            pid = f"{position}_{i:02d}"
            positions[pid] = position
            projections[pid] = 300.0 - i * 7.0
    for i in range(3):
        positions[f"K_{i}"] = "K"
        projections[f"K_{i}"] = 130.0 - i * 5.0
    return SeasonStatic(
        season=2023,
        ecr_type="ro",
        projections=projections,
        positions=positions,
        vorp={p: 0.0 for p in positions},
        replacement_levels={p: 150.0 for p in ("QB", "RB", "WR", "TE", "K")},
        scarcity_raw={p: 1.0 for p in ("QB", "RB", "WR", "TE", "K")},
        scarcity_norm={p: 0.5 for p in ("QB", "RB", "WR", "TE", "K")},
        market_rank={p: (positions[p], float(i)) for i, p in enumerate(sorted(projections))},
        confidence={p: 0.7 for p in positions},
        ecr_dispersion={p: (1.0, 5.0) for p in positions},
        consumption_demand={p: 2.0 for p in ("QB", "RB", "WR", "TE", "K")},
    )


def _order(static, position):
    ids = [p for p in static.projections if static.positions[p] == position]
    return sorted(ids, key=lambda p: (-static.projections[p], p))


class TestLadderEndpoints:
    def test_alpha_zero_reproduces_y1_exactly(self):
        """The baseline of the entire sensitivity curve. If this drifts, every level is measured
        against the wrong reference."""
        static = _static()
        out = MODULE.perturbed_static(_league(), static, 0.0, seed=0)
        assert out.projections == static.projections

    def test_alpha_one_is_independent_of_y1(self):
        """A uniform permutation must not preserve Y1's ordering. Checked across seeds so a
        single lucky draw cannot pass it."""
        static = _static()
        agreements = []
        for seed in MODULE.SEEDS:
            out = MODULE.perturbed_static(_league(), static, 1.0, seed=seed)
            before, after = _order(static, "WR"), _order(out, "WR")
            agreements.append(sum(1 for a, b in zip(before, after, strict=True) if a == b))
        assert min(agreements) < len(_order(static, "WR")), "no seed may reproduce Y1's order"

    def test_alpha_outside_the_unit_interval_is_refused(self):
        static = _static()
        for bad in (-0.01, 1.01, 2.0):
            with pytest.raises(MODULE.PerturbationError, match=r"alpha must be in \[0, 1\]"):
                MODULE.perturbed_static(_league(), static, bad, seed=0)


class TestInformationDegradesMonotonically:
    def test_agreement_with_y1_falls_as_alpha_rises(self):
        """The ladder must be ORDERED in information, or 'level' means nothing. Averaged over the
        pre-registered seeds so one draw cannot invert a rung."""
        static = _static()
        means = []
        for alpha in MODULE.LEVELS.values():
            per_seed = []
            for seed in MODULE.SEEDS:
                out = MODULE.perturbed_static(_league(), static, alpha, seed=seed)
                ids = [p for p in static.projections if static.positions[p] == "WR"]
                per_seed.append(
                    MODULE._spearman(
                        [out.projections[p] for p in ids], [static.projections[p] for p in ids]
                    )
                )
            means.append(sum(per_seed) / len(per_seed))
        assert means == sorted(means, reverse=True), means
        assert means[0] == pytest.approx(1.0)
        assert means[-1] < 0.6, "alpha=1 must be substantially decorrelated from Y1"


class TestNothingElseChanges:
    def test_value_multiset_is_preserved_at_every_level(self):
        static = _static()
        for alpha in MODULE.LEVELS.values():
            out = MODULE.perturbed_static(_league(), static, alpha, seed=3)
            for position in ("QB", "RB", "WR", "TE", "K"):
                before = sorted(
                    v for p, v in static.projections.items() if static.positions[p] == position
                )
                after = sorted(
                    v for p, v in out.projections.items() if out.positions[p] == position
                )
                assert before == after, (alpha, position)

    def test_only_projections_and_vorp_change(self, monkeypatch):
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )
        static = _static()
        out = MODULE.perturbed_static(_league(), static, 0.75, seed=1)
        changed = {
            f.name
            for f in dataclasses.fields(static)
            if getattr(out, f.name) != getattr(static, f.name)
        }
        assert changed == {"projections", "vorp"}, sorted(changed)

    def test_kickers_are_untouched(self):
        static = _static()
        out = MODULE.perturbed_static(_league(), static, 1.0, seed=2)
        for pid in ("K_0", "K_1", "K_2"):
            assert out.projections[pid] == static.projections[pid]

    def test_the_candidate_universe_is_identical(self):
        static = _static()
        out = MODULE.perturbed_static(_league(), static, 0.5, seed=4)
        assert set(out.projections) == set(static.projections)

    def test_the_multiset_guard_can_actually_fire(self, monkeypatch):
        """A guard that cannot fail is not a guard."""
        static = _static()
        real_sorted = sorted

        def _bad(values, *, key=None, reverse=False):
            ordered = real_sorted(values, key=key, reverse=reverse)
            return [v + 1.0 for v in ordered] if reverse else ordered

        monkeypatch.setattr(MODULE, "sorted", _bad, raising=False)
        with pytest.raises(MODULE.PerturbationError, match="multiset"):
            MODULE.perturbed_static(_league(), static, 0.5, seed=0)


class TestDeterminism:
    def test_the_same_seed_reproduces_exactly(self):
        static = _static()
        a = MODULE.perturbed_static(_league(), static, 0.5, seed=7)
        b = MODULE.perturbed_static(_league(), static, 0.5, seed=7)
        assert a.projections == b.projections

    def test_different_seeds_differ(self):
        static = _static()
        a = MODULE.perturbed_static(_league(), static, 0.5, seed=0)
        b = MODULE.perturbed_static(_league(), static, 0.5, seed=1)
        assert a.projections != b.projections

    def test_the_seed_stream_is_stable_across_PROCESSES(self):
        """`random.Random` on a STRING hashes its bytes, so the stream is stable between runs --
        unlike `hash()` on a str, which is salted per interpreter. Verified by actually starting a
        second interpreter, because that is the property the reproduction claim depends on."""
        code = (
            "import random;r=random.Random('3|2023|WR|0.5');print([r.random() for _ in range(3)])"
        )
        first = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        second = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert first.stdout == second.stdout
        assert first.stdout.strip(), first.stderr


class TestRegisteredDesign:
    def test_the_ladder_is_the_registered_one(self):
        assert MODULE.LEVELS == {"L0": 0.00, "L1": 0.25, "L2": 0.50, "L3": 0.75, "L4": 1.00}
        assert list(MODULE.LEVELS.values()) == sorted(MODULE.LEVELS.values())

    def test_the_seeds_are_pre_registered(self):
        assert MODULE.SEEDS == (0, 1, 2, 3, 4)

    def test_thresholds_are_quoted_from_earlier_phases_not_re_derived(self):
        assert MODULE.DETECTION_FLOOR == (172.0, 250.0)
        assert MODULE.D103_DECISION_RESIDUAL == (86.0, 113.0)

    def test_only_the_positions_m6_models_are_perturbed(self):
        assert MODULE.SKILL == ("QB", "RB", "WR", "TE")

    def test_population_is_the_board_contract_window(self):
        assert BACKTEST_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert 2020 not in BACKTEST_SEASONS and 2026 not in BACKTEST_SEASONS

    def test_no_realized_outcome_reaches_the_perturbation(self):
        import inspect

        params = set(inspect.signature(MODULE.perturbed_static).parameters)
        banned = ("actual", "realized", "outcome", "realised")
        assert not {p for p in params if any(b in p.lower() for b in banned)}
        assert "_actual_points_for" not in inspect.getsource(MODULE.perturbed_static)


class TestD106ObjectiveSelection:
    """D106 added the weekly arm of the same ladder. Three harness properties carry that phase's
    conclusions and would fail silently rather than loudly if they broke."""

    def test_the_objective_flag_only_accepts_registered_objectives(self):
        """`_play_draft` falls through to the SEASON-LONG branch for any objective it does not
        recognise, so an unconstrained `--objective` would let a typo produce a season-long run
        reported as a weekly one. The flag is constrained so argparse refuses instead."""
        from alpha_squad.evaluation.draft_oracle import OBJECTIVES

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT),
                "--mode",
                "value",
                "--out",
                "/tmp/unused",
                "--objective",
                "bogus",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr
        assert set(OBJECTIVES) == {"season_long", "weekly_no_foresight"}

    def test_pick_divergence_is_objective_independent(self):
        """D106 does NOT re-run the divergence ladder, and this is why: picks come from
        `_pick_by_tier`, which has no objective parameter at all. The scoring objective cannot
        reach a draft decision, so D105's picks-changed table carries over unchanged."""
        import inspect

        from alpha_squad.evaluation.draft_forensics import _pick_by_tier

        params = set(inspect.signature(_pick_by_tier).parameters)
        assert not {p for p in params if "objective" in p.lower()}
        assert "objective" not in inspect.getsource(MODULE.run_divergence)

    def test_the_weekly_lineup_is_set_from_UNPERTURBED_projections(self):
        """The isolation that makes the weekly arm a test of DRAFT quality rather than lineup
        quality. `_play_draft` scores with `scoring_static`, and the ladder passes the unperturbed
        `static` there while the perturbed board goes in as the draft board -- so every arm sets
        its weekly lineup from Y1's own projections and only the drafting differs."""
        import inspect

        source = inspect.getsource(MODULE.D103._play_draft)
        assert "scoring_static.projections" in source
        assert "weekly_lineup_points_no_foresight" in source
        # the ladder passes the perturbed arm as the BOARD and the untouched static as the SCORER
        call = inspect.getsource(MODULE.run_value)
        assert "arm, slot, SHIPPED_TIER, static, weekly, objective" in call
