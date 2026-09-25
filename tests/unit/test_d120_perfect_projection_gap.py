"""Unit tests for D120's perfect-projection gap audit
(`scripts/research/d120_perfect_projection_gap.py`).

D120's conclusions rest on these properties, pinned here rather than asserted in prose:

  * INSTRUMENT DEFECT (regression): D103's committed `oracle_static` -- the ORACLE_Y1 arm --
    replaces `projections` and `vorp` but leaves `replacement_levels` (and scarcity, and
    confidence) at their Y1 values, although its docstring says replacement levels are
    recomputed. D120 does not edit D103; it pins the behaviour and builds corrected arms beside it;
  * the corrected arms change EXACTLY the field they name and nothing else;
  * confidence is recomputed with M6's own construction (its interval offsets kept, its formula
    re-evaluated at the new point), not set to 1.0;
  * ARM 1 must reproduce D115's stored ORACLE_Y1 exactly or the run stops;
  * the decomposition is computed from measured arms, interaction included, never assumed additive.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import inspect
from pathlib import Path

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import SeasonStatic
from alpha_squad.league.context import resolve_league
from alpha_squad.league.replacement import marginal_value_over_replacement, replacement_level
from alpha_squad.models.uncertainty.conformal import confidence_from_interval_width

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d120_perfect_projection_gap")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d120_perfect_projection_gap.py").read_text()
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")


def _synthetic(season: int = 2023):
    """A board of 40 players per position with Y1 projections, and a DIFFERENT realized table,
    so every projection-derived quantity must move under perfect projections."""
    league = resolve_league("target_league")
    projections, positions, realized = {}, {}, {}
    for pos in POSITIONS:
        for i in range(40):
            pid = f"{pos}{i:02d}"
            positions[pid] = pos
            projections[pid] = 300.0 - 6.0 * i
            realized[pid] = 250.0 - 4.0 * i + (40.0 if i % 7 == 0 else 0.0)
    levels = replacement_level(league, projections, positions)
    static = SeasonStatic(
        season=season,
        ecr_type="ro",
        projections=projections,
        positions=positions,
        vorp=marginal_value_over_replacement(league, projections, positions),
        replacement_levels=levels,
        scarcity_raw=dict.fromkeys(POSITIONS, 1.0),
        scarcity_norm=dict.fromkeys(POSITIONS, 0.5),
        market_rank={p: (positions[p], float(i)) for i, p in enumerate(sorted(projections))},
        confidence={p: 0.5 for p in projections},
        ecr_dispersion={},
    )
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE player_season_stats (player_id VARCHAR, season INTEGER, "
        "total_fantasy_points_ppr DOUBLE)"
    )
    con.executemany(
        "INSERT INTO player_season_stats VALUES (?, ?, ?)",
        [(p, season, v) for p, v in realized.items()],
    )
    return con, league, static, realized


class TestInstrumentDefectRegression:
    def test_oracle_static_leaves_replacement_levels_stale(self):
        """D120 finding, pinned: D103's ORACLE_Y1 arm recomputes projections and VORP but NOT the
        static replacement levels its docstring says it recomputes. If D103 is ever fixed, this
        test fails and the D120 report's ARM 1 vs ARM 2 distinction must be revisited."""
        con, league, static, realized = _synthetic()
        arm1 = M.D103.oracle_static(con, league, static.season, static)
        assert arm1.projections == {p: realized[p] for p in static.projections}
        assert arm1.replacement_levels == static.replacement_levels  # stale: the defect
        assert arm1.replacement_levels != replacement_level(
            league, arm1.projections, arm1.positions
        )
        assert arm1.confidence == static.confidence  # stale by design (a rule question)
        assert arm1.scarcity_raw == static.scarcity_raw

    def test_but_its_vorp_is_internally_consistent(self):
        """VORP recomputes its own replacement level internally, so ARM 1's VORP is correct even
        though its stored replacement_levels are stale."""
        con, league, static, _ = _synthetic()
        arm1 = M.D103.oracle_static(con, league, static.season, static)
        assert arm1.vorp == marginal_value_over_replacement(
            league, arm1.projections, arm1.positions
        )

    def test_the_docstring_claim_that_diverges_from_the_code(self):
        src = inspect.getsource(M.D103.oracle_static)
        assert "`vorp`, `replacement_levels`" in src
        assert "dataclasses.replace(static, projections=projections, vorp=vorp)" in src


class TestCorrectedArms:
    def test_confidence_uses_m6s_offsets_and_formula(self):
        intervals = {"a": (100.0, 40.0, 190.0), "b": (50.0, -10.0, 140.0)}
        new = M.recomputed_confidence({"a": 250.0, "b": 20.0, "c": 99.0}, intervals)
        assert new["a"] == pytest.approx(confidence_from_interval_width(250.0, 190.0, 340.0))
        assert new["b"] == pytest.approx(confidence_from_interval_width(20.0, -40.0, 110.0))
        assert "c" not in new  # no M6 row -> keeps the shipped 0.7 fallback

    def test_confidence_is_not_simply_set_to_one(self):
        new = M.recomputed_confidence({"a": 60.0}, {"a": (100.0, 20.0, 200.0)})
        assert new["a"] < 1.0

    def test_arm2_changes_only_replacement_levels(self):
        con, league, static, _ = _synthetic()
        arm1 = M.D103.oracle_static(con, league, static.season, static)
        levels = replacement_level(league, arm1.projections, arm1.positions)
        arm2 = dataclasses.replace(arm1, replacement_levels=levels)
        changed = [
            f.name
            for f in dataclasses.fields(arm1)
            if getattr(arm1, f.name) != getattr(arm2, f.name)
        ]
        assert changed == ["replacement_levels"]

    def test_the_arm_builder_is_wired_as_documented(self):
        src = inspect.getsource(M.arm_statics)
        assert "D103.oracle_static(" in src
        assert '"ARM2": dataclasses.replace(arm1, replacement_levels=levels)' in src
        assert '"ARM3": dataclasses.replace(arm1, confidence=conf)' in src
        assert (
            '"ARM4": dataclasses.replace(arm1, replacement_levels=levels, confidence=conf)' in src
        )
        assert "projections_override=dict(arm1.projections)" in src


class TestReproductionGate:
    def test_arm1_must_reproduce_d115(self):
        assert "does not reproduce D115's ORACLE_Y1" in RUNNER_SOURCE
        assert "STOP, no new arm is interpretable" in RUNNER_SOURCE

    def test_the_control_rollout_is_reverified(self):
        assert "control rollout != D115's" in RUNNER_SOURCE

    def test_weekly_join_refuses_a_different_draft(self):
        row = {
            "league": "target_league",
            "season": 2023,
            "slot": 1,
            "overall_pick": 1,
            "alpha_rollout_weekly": 100.0,
        }
        weekly = {
            ("target_league", 2023, 1, 1): {
                "alpha_rollout_weekly": 101.0,
                "oracle_rollout_weekly": 150.0,
                "regret_weekly": 49.0,
            }
        }
        with pytest.raises(M.UnreconstructibleError):
            M.join_weekly([row], weekly)
        weekly[("target_league", 2023, 1, 1)]["alpha_rollout_weekly"] = 100.0
        M.join_weekly([row], weekly)
        assert row["regret_weekly"] == 49.0


class TestDecomposition:
    def test_components_include_the_interaction(self):
        summ = {
            "ARM1": {"recovery": 0.70},
            "ARM2": {"recovery": 0.72},
            "ARM3": {"recovery": 0.75},
            "ARM4": {"recovery": 0.80},
        }
        d = M.decompose(summ)
        assert d["residual_arm1"] == pytest.approx(0.30)
        assert d["stale_replacement_effect"] == pytest.approx(0.02)
        assert d["stale_risk_effect"] == pytest.approx(0.05)
        assert d["interaction"] == pytest.approx(0.03)
        assert d["other_decision_residual"] == pytest.approx(0.20)
        # the parts reconstruct the ARM 1 residual exactly
        assert (
            d["stale_replacement_effect"]
            + d["stale_risk_effect"]
            + d["interaction"]
            + d["other_decision_residual"]
        ) == pytest.approx(d["residual_arm1"])

    def test_season_ci_k5(self):
        res = M.season_ci({2021: 1.0, 2022: 2.0, 2023: 3.0, 2024: 4.0, 2025: 5.0})
        assert res["k"] == 5 and res["mean"] == 3.0
        assert res["mde"] == pytest.approx(2.776 * (2.5**0.5) / (5**0.5))


def _row(season, arm_picks, oracle="o", oracle_pos="RB", regret=100.0, rollouts=None):
    rollouts = rollouts or {}
    return {
        "league": "target_league",
        "season": season,
        "slot": 1,
        "round": 1,
        "phase": "R1-6",
        "overall_pick": 1,
        "alpha_pick": "a",
        "oracle_player": oracle,
        "oracle_position": oracle_pos,
        "oracle_rollout": 1000.0,
        "regret_roster": regret,
        "regret_weekly": None,
        "oracle_rollout_weekly": None,
        "arms": {
            arm: {
                "pick": pick,
                "position": pos,
                "changed": pick != "a",
                "delta": rollouts.get(arm, 0.0),
                "delta_weekly": 0.0,
                "rollout": 900.0 + rollouts.get(arm, 0.0),
                "rollout_weekly": 0.0,
            }
            for arm, (pick, pos) in arm_picks.items()
        },
        "arm4_attribution": {"arm4_pick_is_oracle": arm_picks["ARM4"][0] == oracle},
    }


class TestResidualAttribution:
    def test_a_b_split_and_regret_shares(self):
        picks_same = {a: ("x", "RB") for a in (*M.ARMS, M.AUDIT_ARM)}
        picks_diff = {a: ("y", "WR") for a in (*M.ARMS, M.AUDIT_ARM)}
        rows = [_row(2023, picks_same), _row(2024, picks_diff)]
        ra = M.residual_attribution(rows)
        assert ra["A_right_position_wrong_player"]["n"] == 1
        assert ra["B_wrong_position"]["n"] == 1
        assert ra["A_right_position_wrong_player"]["pct_regret"] == pytest.approx(50.0)

    def test_a_pick_equal_to_the_oracle_is_not_attributed(self):
        picks = {a: ("o", "RB") for a in (*M.ARMS, M.AUDIT_ARM)}
        ra = M.residual_attribution([_row(2023, picks)])
        assert ra["arm_equals_oracle"] == 1
        assert ra["A_right_position_wrong_player"]["n"] == 0


class TestDiscipline:
    def test_no_tuning(self):
        for forbidden in ("GridSearch", "for alpha in", "for weight in", "optimize"):
            assert forbidden not in RUNNER_SOURCE

    def test_production_untouched_and_read_only(self):
        assert "read_only=True" in RUNNER_SOURCE
        assert "src_dirty" in RUNNER_SOURCE

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()
