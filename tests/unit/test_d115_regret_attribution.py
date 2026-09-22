"""Unit tests for D115's regret attribution (`scripts/research/d115_regret_attribution.py`).

D115's conclusions rest on five properties, pinned here rather than asserted in prose:

  * the PRIMARY regret is D103's roster-value quantity (`OraclePick.regret`), not the raw
    player-points difference the brief's formula names -- the two differ by about an order of
    magnitude and conflating them would re-make the error D113 and D114 both measured;
  * the A/B/D attribution is disjoint and exhaustive, and C is an OVERLAY rather than a fourth
    bucket, because timing genuinely overlaps A and B;
  * the replay that supplies availability and score components walks the same draft
    `audit_draft` walks, and the runner raises rather than joining mismatched rows;
  * every arm is a COMMITTED construction, imported, with no new arm and no NAIVE recreation;
  * the arm harness reuses the regret run's own Alpha rollout values and refuses to proceed if
    they disagree with a recomputation.

Loaded the same way `test_d104_ecr_floor.py` / `test_d114_matched_state.py` load their runners.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.draft_forensics import X_TIER_SPEC
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    OracleCandidate,
    OraclePick,
)

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load("d115_regret_attribution")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d115_regret_attribution.py").read_text()


def _candidate(player_id: str, position: str, *, rollout: float, realized: float, alpha=False):
    return OracleCandidate(
        player_id=player_id,
        position=position,
        projection=0.0,
        alpha_score=0.0,
        alpha_rank=1,
        realized_points=realized,
        rollout_starter_points=rollout,
        rollout_total_points=0.0,
        unfilled_mandatory=0,
        is_alpha_pick=alpha,
    )


class TestTheRegretDefinitionIsD103s:
    def test_primary_regret_is_the_roster_value_quantity(self):
        """`OraclePick.regret` differences ROLLOUT values, not player points. D115 must read the
        primary number off that property and nothing else."""
        pick = OraclePick(
            season=2023,
            draft_slot=1,
            round_no=1,
            pick_overall=1,
            roster_positions=[],
            candidates=[
                _candidate("alpha", "RB", rollout=2000.0, realized=300.0, alpha=True),
                _candidate("oracle", "RB", rollout=2150.0, realized=250.0),
            ],
        )
        # Roster value says the oracle's man is worth +150; raw player points say he is worth -50.
        assert pick.regret == pytest.approx(150.0)
        assert pick.oracle.realized_points - pick.alpha.realized_points == pytest.approx(-50.0)

    def test_the_runner_records_both_and_labels_which_is_primary(self):
        assert '"regret_roster": regret' in RUNNER_SOURCE
        assert '"regret_raw": oracle.realized_points - alpha.realized_points' in RUNNER_SOURCE
        assert "PRIMARY" in RUNNER_SOURCE and "SECONDARY" in RUNNER_SOURCE

    def test_every_attribution_table_is_built_on_the_roster_quantity(self):
        """A table accidentally built on `regret_raw` would rank the wrong sources."""
        grouping = RUNNER_SOURCE.split("def group_regret")[1].split("def report")[0]
        assert 'r["regret_roster"]' in grouping
        assert "regret_raw" not in grouping

    def test_d103s_published_mean_is_quoted_not_rederived(self):
        assert MODULE.D103_MEAN_REGRET_TARGET == 134.8

    def test_the_oracle_is_the_slate_maximiser_not_the_oracle_y1_arm(self):
        """Two different objects. `ORACLE_Y1` is an ARM; the per-pick oracle is the slate max."""
        assert "ORACLE_Y1" in MODULE.ARM_ORDER
        assert "different objects and are never interchanged" in RUNNER_SOURCE


class TestAttributionIsDisjointAndExhaustive:
    @pytest.mark.parametrize(
        "alpha_pos,oracle_pos,regret,expected",
        [
            ("RB", "RB", 100.0, "A_wrong_player_right_position"),
            ("WR", "RB", 100.0, "B_wrong_position"),
            ("RB", "RB", 0.0, "A_wrong_player_right_position"),
            ("RB", "RB", -1.0, "D_unclassified"),
            ("UNKNOWN", "RB", 100.0, "D_unclassified"),
            ("RB", "UNKNOWN", 100.0, "D_unclassified"),
            (None, "RB", 100.0, "D_unclassified"),
            ("RB", None, 100.0, "D_unclassified"),
        ],
    )
    def test_classify(self, alpha_pos, oracle_pos, regret, expected):
        assert MODULE.classify(alpha_pos, oracle_pos, regret) == expected

    def test_the_partition_is_exhaustive_over_every_position_pair(self):
        positions = ("QB", "RB", "WR", "TE", "K", "DST")
        seen = set()
        for a in positions:
            for o in positions:
                seen.add(MODULE.classify(a, o, 10.0))
        assert seen == {"A_wrong_player_right_position", "B_wrong_position"}

    def test_categories_constant_matches_the_classifier(self):
        produced = {
            MODULE.classify("RB", "RB", 1.0),
            MODULE.classify("RB", "WR", 1.0),
            MODULE.classify(None, None, 1.0),
        }
        assert produced == set(MODULE.CATEGORIES)

    def test_timing_is_an_overlay_and_never_a_category(self):
        """C overlaps A and B by construction, so it must not appear in the disjoint partition."""
        assert not any(c[0] == "C" for c in MODULE.CATEGORIES)
        assert "C1_oracle_survives_to_next_pick" in RUNNER_SOURCE
        assert "C2_alpha_survives_if_oracle_taken" in RUNNER_SOURCE
        assert "not a bucket" in RUNNER_SOURCE or "OVERLAY" in RUNNER_SOURCE.upper()

    def test_c2_is_a_counterfactual_not_the_vacuous_membership_test(self):
        """REGRESSION. D115's first regret run asked whether Alpha's own player was in the pool
        at the next pick. He never is -- Alpha removed him by drafting him -- so the flag was
        False at 300 of 300 picks and measured nothing. C2 is now the counterfactual: had Alpha
        taken the ORACLE's player, would Alpha's own choice have survived?"""
        assert "C2_alpha_survives_to_next_pick" not in RUNNER_SOURCE
        assert "def survives_counterfactual" in RUNNER_SOURCE
        assert "vacuously False" in RUNNER_SOURCE

    def test_the_counterfactual_removes_the_oracles_player_not_alphas(self):
        body = RUNNER_SOURCE.split("def survives_counterfactual")[1].split("def run_timing")[0]
        assert 'avail = set(state["available"]) - {taken_instead}' in body
        assert "roster_aware_market_pick" in body

    def test_the_report_refuses_to_run_without_the_timing_artifact(self):
        assert "the C overlays come from --mode timing" in RUNNER_SOURCE

    def test_the_overlays_report_their_overlap_with_a_and_b(self):
        assert '"overlap_with_A"' in RUNNER_SOURCE and '"overlap_with_B"' in RUNNER_SOURCE


class TestTheReplayMustWalkTheSameDraft:
    def _record(self, pick_overall: int, alpha_id: str):
        return OraclePick(
            season=2023,
            draft_slot=1,
            round_no=1,
            pick_overall=pick_overall,
            roster_positions=[],
            candidates=[_candidate(alpha_id, "RB", rollout=1.0, realized=1.0, alpha=True)],
        )

    def test_matching_picks_join(self):
        audited = [self._record(1, "p1")]
        states = [{"overall_pick": 1, "alpha_pick": "p1"}]
        joined = MODULE.attach_replay(audited, states)
        assert len(joined) == 1 and joined[0][1]["alpha_pick"] == "p1"

    def test_a_divergent_pick_raises_rather_than_joining(self):
        audited = [self._record(1, "p1")]
        states = [{"overall_pick": 1, "alpha_pick": "SOMEONE_ELSE"}]
        with pytest.raises(MODULE.UnreconstructibleError, match="not walking the same draft"):
            MODULE.attach_replay(audited, states)

    def test_a_length_mismatch_raises(self):
        with pytest.raises(MODULE.UnreconstructibleError):
            MODULE.attach_replay([self._record(1, "p1")], [])

    def test_a_missing_state_raises(self):
        audited = [self._record(7, "p1")]
        states = [{"overall_pick": 1, "alpha_pick": "p1"}]
        with pytest.raises(MODULE.UnreconstructibleError):
            MODULE.attach_replay(audited, states)


class TestArmsAreCommittedAndUnchanged:
    def test_y1_is_the_first_arm_and_is_the_null_check(self):
        assert MODULE.ARM_ORDER[0] == "Y1"
        assert "must recover exactly 0" in RUNNER_SOURCE

    def test_the_report_refuses_a_non_zero_null_arm(self):
        assert "the Y1 null arm recovered" in RUNNER_SOURCE

    def test_the_x_arms_come_from_the_committed_tier_spec(self):
        for tier in ("X2", "X3"):
            assert tier in X_TIER_SPEC
            assert tier in MODULE.ARM_ORDER

    def test_the_ladder_arms_are_d105s_levels_at_its_own_seed(self):
        assert set(MODULE.D105.LEVELS) == {"L0", "L1", "L2", "L3", "L4"}
        assert MODULE.D105.LEVELS["L0"] == 0.0
        # L0 reproduces Y1 exactly, so it is deliberately NOT a separate arm here.
        assert "L0" not in MODULE.ARM_ORDER
        for name in ("L1", "L2", "L3", "L4"):
            assert name in MODULE.ARM_ORDER

    def test_the_ladder_is_labelled_as_a_downside_bound_not_a_candidate(self):
        assert "DEGRADE" in RUNNER_SOURCE

    def test_no_new_arm_is_defined_in_the_runner(self):
        """Every arm must be an import. A locally-defined board would be a new experiment."""
        for forbidden in (
            "def ecr_ordered_static",
            "def perturbed_static",
            "def oracle_static",
            "def naive",
            "NAIVE_TIER",
        ):
            assert forbidden not in RUNNER_SOURCE, forbidden

    def test_no_tuning_or_weight_search_anywhere_in_the_runner(self):
        for forbidden in ("for weight in", "WEIGHT_GRID", "np.linspace", "minimize(", "fit("):
            assert forbidden not in RUNNER_SOURCE, forbidden

    def test_an_arms_board_is_used_to_pick_but_never_to_score(self):
        """Scoring on a perturbed or calibrated board would move the audited states and the
        oracle -- the confound D105 names. Every rollout must be on Y1's `static`."""
        roll = RUNNER_SOURCE.split("def roll_from_state")[1].split("def run_arms")[0]
        assert "static," in roll
        assert "arms[" not in roll and "arm_static" not in roll


class TestArmHarnessReusesTheRegretNumbers:
    def test_it_reads_alpha_rollout_from_the_regret_table(self):
        arms = RUNNER_SOURCE.split("def run_arms")[1]
        assert "alpha_rollout" in arms
        assert "audit_draft(" not in arms, "arms must not re-run the expensive audit"

    def test_it_raises_when_the_stored_pick_disagrees_with_the_replay(self):
        assert "are not the same draft" in RUNNER_SOURCE

    def test_it_reverifies_the_stored_value_by_recomputation(self):
        assert "recomputed Alpha rollout" in RUNNER_SOURCE

    def test_arms_mode_refuses_to_run_without_the_regret_artifact(self):
        assert "reuses the regret run" in RUNNER_SOURCE


class TestStatistics:
    def test_gini_is_zero_for_a_flat_distribution(self):
        assert MODULE._gini([5.0] * 10) == pytest.approx(0.0, abs=1e-9)

    def test_gini_approaches_one_when_all_value_is_in_one_pick(self):
        assert MODULE._gini([0.0] * 99 + [100.0]) > 0.95

    def test_pearson_recovers_a_perfect_relationship(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        assert MODULE._pearson(xs, [2.0, 4.0, 6.0, 8.0]) == pytest.approx(1.0)
        assert MODULE._pearson(xs, [8.0, 6.0, 4.0, 2.0]) == pytest.approx(-1.0)

    def test_pearson_is_undefined_rather_than_zero_on_a_constant(self):
        got = MODULE._pearson([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])
        assert got != got  # NaN

    def test_ci_reproduces_the_d104_convention(self):
        md, t, ci, half = MODULE._ci([10.0, 20.0, 30.0, 40.0, 50.0])
        assert md == pytest.approx(30.0)
        assert half == pytest.approx(2.776 * 15.811388 / 5**0.5, rel=1e-5)

    def test_a_single_season_cannot_manufacture_an_interval(self):
        assert MODULE._ci([42.0])[2] == "n/a"

    def test_group_regret_splits_a_and_b_and_shares_sum_to_the_total(self):
        rows = [
            {"round": 1, "regret_roster": 60.0, "category": "A_wrong_player_right_position"},
            {"round": 1, "regret_roster": 40.0, "category": "B_wrong_position"},
            {"round": 2, "regret_roster": 100.0, "category": "B_wrong_position"},
        ]
        groups = group_regret_quiet(rows, 200.0, "round", "round")
        assert groups["1"]["total_regret"] == pytest.approx(100.0)
        assert groups["1"]["pct_A"] == pytest.approx(60.0)
        assert groups["1"]["pct_B"] == pytest.approx(40.0)
        assert groups["2"]["pct_B"] == pytest.approx(100.0)
        assert sum(g["pct_of_regret"] for g in groups.values()) == pytest.approx(100.0)


def group_regret_quiet(rows, total, field, label, order=None):
    """`group_regret` with its printing suppressed, so the table logic can be asserted."""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return MODULE.group_regret(rows, total, field, label, order)


class TestPopulationAndDiscipline:
    def test_the_grid_is_d103s(self):
        assert MODULE.DEFAULT_SLOTS == (1, 4, 7, 10)
        assert MODULE.FORMATS == ("target_league", "dynasty_1qb")
        assert MODULE.PRIMARY_FORMAT == "target_league"

    def test_seasons_are_the_committed_backtest_window(self):
        assert BACKTEST_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert 2020 not in BACKTEST_SEASONS

    def test_the_objective_and_tier_are_the_shipped_ones(self):
        assert SEASON_LONG == "season_long"
        assert SHIPPED_TIER == "L0"

    def test_phases_cover_every_round_of_a_16_round_draft(self):
        brief = {label for label, _, _ in MODULE.PHASES}
        d103 = {label for label, _, _ in MODULE.D103_PHASES}
        for round_no in range(1, 17):
            assert MODULE._phase_of(round_no) in brief
            assert MODULE._phase_of(round_no, MODULE.D103_PHASES) in d103

    def test_the_briefs_phase_split_is_r1_6_r7_11_r12_16(self):
        assert MODULE.PHASES == (("R1-6", 1, 6), ("R7-11", 7, 11), ("R12-16", 12, 16))

    def test_the_causality_disclaimer_is_printed_with_the_associations(self):
        assert "CORRELATION ONLY" in RUNNER_SOURCE
        assert "is NOT thereby a cause" in RUNNER_SOURCE

    def test_within_round_correlation_is_reported_beside_the_raw_one(self):
        """Every component correlates with round, and regret varies strongly by round, so the
        raw correlation alone would be a round effect wearing a component's name."""
        assert "pearson_r_within_round_mean" in RUNNER_SOURCE

    def test_naive_is_not_recreated(self):
        assert "does not exist" in RUNNER_SOURCE
        assert "def naive" not in RUNNER_SOURCE.lower()

    def test_the_naive_guard_exclusions_are_kept_in_step_with_d114s(self):
        d114 = _load("d114_matched_state")
        del d114  # importing proves it still loads; the shared list is what matters
        guard = (ROOT / "tests" / "unit" / "test_d114_matched_state.py").read_text()
        for rel in MODULE.NAIVE_GUARD_EXCLUSIONS:
            assert rel in guard, f"{rel} missing from D114's GUARD_FILES"
