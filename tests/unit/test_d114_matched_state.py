"""Unit tests for D114's matched-state estimators (`scripts/research/d114_matched_state.py`).

D114's claims rest on four properties, so they are pinned here rather than asserted in prose:

  * the ECR arm is D104's, IMPORTED rather than reimplemented -- a re-specified arm would make
    D114 a different experiment wearing D104's name, and there is no weight anywhere to tune;
  * the one-step estimator's two branches differ in exactly one pick and share the continuation
    policy, and its control branch must reproduce the control draft exactly (the runner raises
    if it does not);
  * the reconstructability audit's D97 verdict is derived from the repository, not asserted;
  * the pre-registered ECR classification is mechanical, and "tight around zero" means the whole
    interval is inside the economic threshold -- not merely that the point estimate is small.

Loaded the same way `test_d104_ecr_floor.py` and `test_d113_capacity_audit.py` load their runners.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.draft_oracle import SEASON_LONG, SHIPPED_TIER, WEEKLY_NO_FORESIGHT


def _load(name: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load("d114_matched_state")
D104 = _load("d104_ecr_floor")

#: The runner's own source. Several properties D114 depends on are structural -- which
#: functions exist, which board a rollout reads -- so they are checked against the text
#: rather than by running a 15-minute grid inside the unit suite.
RUNNER_SOURCE = (
    Path(__file__).resolve().parents[2] / "scripts" / "research" / "d114_matched_state.py"
).read_text()

#: Files whose PURPOSE is to record that D97's NAIVE arm does not exist. They necessarily
#: mention the string, so a history search over every `*.py` would match them and the guard
#: would flag itself. Excluded here, and each exclusion is re-verified by the guard.
GUARD_FILES = (
    "scripts/research/d114_matched_state.py",
    "tests/unit/test_d114_matched_state.py",
    "scripts/research/d115_regret_attribution.py",
    "tests/unit/test_d115_regret_attribution.py",
)


class TestTheArmIsD104sArm:
    def test_the_ecr_arm_is_imported_not_reimplemented(self):
        """If D114 carried its own copy of the substitution, a later edit to one could silently
        make the two phases measure different things under the same name.

        Compared by SOURCE FILE and bytecode rather than by object identity: this test and the
        runner each load `d104_ecr_floor.py` through their own `importlib` spec, so two distinct
        function objects off the same file is the expected, correct state."""
        assert Path(MODULE.D104.__file__).name == "d104_ecr_floor.py"
        assert Path(MODULE.D104.__file__) == Path(D104.__file__)
        assert (
            MODULE.D104.ecr_ordered_static.__code__.co_code
            == D104.ecr_ordered_static.__code__.co_code
        )

    def test_d114_defines_no_ecr_transformation_of_its_own(self):
        source = RUNNER_SOURCE
        assert "def ecr_ordered_static" not in source

    def test_there_is_no_ecr_weight_to_tune_anywhere_in_the_runner(self):
        """Decision rule D: no weight is introduced, searched or tuned. The arm is a rank
        permutation of Y1's own value multiset, so no weight exists to begin with."""
        source = RUNNER_SOURCE
        for forbidden in ("ecr_weight", "WEIGHT_GRID", "for weight in", "np.linspace"):
            assert forbidden not in source, forbidden

    def test_both_arms_use_the_shipped_decision_rule(self):
        """Only the projections differ between arms; the rule is production's in both."""
        source = RUNNER_SOURCE
        assert "SHIPPED_TIER" in source
        assert MODULE.CONTROL == "Y1" and MODULE.TREATMENT == "FP_ECR_Y1"
        assert SHIPPED_TIER == "L0"

    def test_the_substitution_still_preserves_the_value_multiset(self):
        """D104's own invariant, re-checked here because D114's whole comparison assumes the
        arm changes ORDERING information and nothing else. A drifted `ecr_ordered_static` would
        silently turn D114 into a valuation experiment."""
        import dataclasses

        from alpha_squad.evaluation.draft_forensics import SeasonStatic
        from alpha_squad.league.context import LeagueContext

        league = LeagueContext(
            league_id="d114_test",
            format="redraft",
            teams=4,
            scoring={"ppr": True, "ppr_value": 1.0},
            lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1},
            roster={"bench": 2, "roster_size": 8},
        )
        positions = {"wr_a": "WR", "wr_b": "WR", "wr_c": "WR", "k_a": "K"}
        projections = {"wr_a": 300.0, "wr_b": 250.0, "wr_c": 200.0, "k_a": 140.0}
        static = SeasonStatic(
            season=2023,
            ecr_type="ro",
            projections=projections,
            positions=positions,
            vorp=dict.fromkeys(projections, 0.0),
            replacement_levels={},
            scarcity_raw={},
            scarcity_norm={},
            market_rank={
                "wr_a": ("overall", 3.0),
                "wr_b": ("overall", 2.0),
                "wr_c": ("overall", 1.0),
                "k_a": ("overall", 4.0),
            },
            confidence={},
            ecr_dispersion={},
        )
        swapped, moved = D104.ecr_ordered_static(league, static)
        assert sorted(swapped.projections.values()) == sorted(projections.values())
        # ECR reverses Y1's WR order, so the substitution must actually move something.
        assert moved > 0
        assert swapped.projections["wr_c"] == 300.0
        # K is untouched: no ECR board ranks kickers, and D104 excludes them by design.
        assert swapped.projections["k_a"] == projections["k_a"]
        assert dataclasses.is_dataclass(swapped)


class TestTheOneStepEstimatorIsAMatchedState:
    def test_the_control_branch_is_verified_against_the_control_draft(self):
        """The runner recomputes the control's value through the SAME rollout call as the
        treatment's and raises if it disagrees. Without that check the two branches could
        differ by how they were computed rather than by the pick."""
        source = RUNNER_SOURCE
        assert "UnreconstructibleError" in source
        assert "is not resuming production's own draft" in source

    def test_an_unchanged_pick_contributes_exactly_zero(self):
        """Identical pick from an identical state under an identical continuation: the deviation
        is zero by construction, and the runner must not fabricate a rollout difference."""
        source = RUNNER_SOURCE
        assert 'row[f"delta_{obj}"] = 0.0' in source

    def test_the_continuation_policy_is_the_shipped_engine_on_control_projections(self):
        """Both branches roll out on `static` (Y1's board), never on the ECR board -- that is
        what makes it a ONE-STEP deviation rather than a second free-running arm."""
        source = RUNNER_SOURCE
        onestep = source.split("def run_onestep")[1].split("def attach_realized")[0]
        assert "ecr_static," not in onestep.split("rollout(")[1]
        assert onestep.count("rollout(") == 2

    def test_the_two_estimators_are_never_summed_into_each_other(self):
        """The headline interpretation risk: one-step deltas are not additive into the free-run
        effect. The runner must not compute such a sum as if it were one."""
        source = RUNNER_SOURCE
        assert "NOT the" in source and "free-run effect" in source


class TestReconstructabilityAuditIsDerivedNotAsserted:
    def test_the_audit_shells_out_to_git_rather_than_hardcoding_its_verdict(self):
        source = RUNNER_SOURCE
        audit = source.split("def run_audit")[1].split("def _control_draft")[0]
        assert '"-S", "NAIVE"' in audit
        assert "diff-filter=A" in audit and "diff-filter=D" in audit

    def test_no_naive_arm_exists_in_the_checkout(self):
        """The fact D114 stops on. If a NAIVE arm is ever added, this test fails and Experiment 2
        becomes runnable -- which is the correct trigger to revisit it.

        REGRESSION (found in D115): the first version of this test searched every `*.py` in
        history for the string, which meant that committing D114 -- whose runner and this very
        file both discuss NAIVE's absence in prose -- made the guard match itself. It passed in
        D114 only because the files were still uncommitted when the suite ran. The guard now
        excludes the files whose JOB is to document the absence, and asserts that each exclusion
        is still earning its place, so a stale exclusion is itself a failure."""
        import subprocess

        root = Path(__file__).resolve().parents[2]
        for rel in GUARD_FILES:
            path = root / rel
            if path.exists():
                assert "NAIVE" in path.read_text(), (
                    f"{rel} no longer mentions NAIVE, so excluding it from the guard hides "
                    "real history -- drop it from GUARD_FILES"
                )
        found = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--oneline",
                "-S",
                "NAIVE",
                "--",
                "*.py",
                *(f":(exclude){rel}" for rel in GUARD_FILES),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        assert found == "", f"a NAIVE arm now exists in history: {found}"

    def test_d114_does_not_define_a_naive_arm_of_its_own(self):
        source = RUNNER_SOURCE
        assert "def naive" not in source.lower()
        assert "NAIVE_TIER" not in source


class TestPreRegisteredClassificationIsMechanical:
    @pytest.mark.parametrize(
        "mean_diff,half,expected",
        [
            # tight around zero: the WHOLE interval is inside +/- 25
            (1.3, 13.4, "B: TIGHT AROUND ZERO"),
            (-4.7, 12.7, "B: TIGHT AROUND ZERO"),
            # wide: admits an economically meaningful effect
            (64.5, 83.4, "C: UNRESOLVED"),
            (-153.9, 238.3, "C: UNRESOLVED"),
            # excludes zero and is economically meaningful
            (60.0, 20.0, "A: credible effect"),
            # excludes zero but is too small to matter -- real and worthless, which is
            # neither a credible improvement nor an interval "tight around zero"
            (10.0, 5.0, "A-: excludes zero"),
        ],
    )
    def test_classifications(self, mean_diff, half, expected):
        assert expected in MODULE._classify(mean_diff, half)

    def test_a_small_point_estimate_with_a_wide_interval_is_not_closed(self):
        """The trap the brief names: a point estimate near zero does not close a question if the
        interval still admits a real effect."""
        assert "C: UNRESOLVED" in MODULE._classify(2.0, 200.0)

    def test_thresholds_and_floor_are_quoted_not_invented(self):
        assert MODULE.ECONOMIC_THRESHOLD == 25.0
        assert MODULE.D97_DETECTION_FLOOR == (172.0, 250.0)
        assert (
            MODULE.D103_TO_D105_VINTAGE
            == "ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99"
        )

    def test_d104s_published_effects_are_recorded_for_the_cross_vintage_comparison(self):
        assert MODULE.D104_PUBLISHED["target_league"]["effect"] == 77.3
        assert MODULE.D104_PUBLISHED["dynasty_1qb"]["effect"] == -132.1

    def test_ci_reproduces_the_d104_convention(self):
        md, t, ci, half = MODULE._ci([10.0, 20.0, 30.0, 40.0, 50.0])
        assert md == pytest.approx(30.0)
        assert half == pytest.approx(2.776 * 15.811388 / 5**0.5, rel=1e-5)
        assert t == pytest.approx(30.0 / (15.811388 / 5**0.5), rel=1e-5)

    def test_a_single_season_cannot_manufacture_an_interval(self):
        md, t, ci, half = MODULE._ci([42.0])
        assert md == 42.0 and ci == "n/a"


class TestPopulation:
    def test_seasons_are_the_committed_backtest_window(self):
        assert BACKTEST_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert 2020 not in BACKTEST_SEASONS

    def test_formats_are_exactly_d104s(self):
        assert MODULE.FORMATS == D104.FORMATS
        assert MODULE.PRIMARY_FORMAT == "target_league"

    def test_the_common_grid_is_d104s_slot_grid(self):
        assert MODULE.COMMON_SLOTS == D104.DEFAULT_SLOTS

    def test_both_objectives_are_the_committed_oracle_objectives(self):
        assert SEASON_LONG in ("season_long",)
        assert WEEKLY_NO_FORESIGHT in ("weekly_no_foresight",)

    def test_phase_partition_covers_every_round_of_a_16_round_draft(self):
        labels = {label for label, _, _ in MODULE.PHASES}
        for round_no in range(1, 17):
            assert MODULE._phase_of(round_no) in labels
