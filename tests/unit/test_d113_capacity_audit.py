"""Unit tests for D113's capacity counterfactual (`scripts/research/d113_capacity_audit.py`).

D113's whole claim is that the treatment arm removes the capacity penalty **and nothing else**.
That claim rests on properties of the arms and of the shipped `score_board`, so they are pinned
here rather than asserted in prose:

  * the control arm is production's defaults, field for field -- a drifted control makes every
    margin a measurement of the harness;
  * `T1` differs from the control in exactly one field, `use_cap_multiplier`;
  * with no position over its cap, `T1` and the control score every candidate identically;
  * with a position over its cap, they differ by exactly `OVER_CAP_VALUE_MULTIPLIER` on that
    position's candidates and by nothing at all elsewhere;
  * the penalty is multiplicative on a SIGNED score, so it moves a negative-scored candidate
    UP -- the property D113 measures on real boards rather than assumes;
  * the pre-registered verdict function and the phase partition behave as written.

Loaded the same way `test_d104_ecr_floor.py` loads its runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.decision_counterfactuals import (
    BoardConstants,
    PickState,
    ScoringVariant,
    score_board,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster import OVER_CAP_VALUE_MULTIPLIER, positional_feasibility_cap


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "d113_capacity_audit.py"
    spec = importlib.util.spec_from_file_location("d113_capacity_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def _league() -> LeagueContext:
    """The target format's shape, small enough that a cap is reachable inside a test."""
    return LeagueContext(
        league_id="d113_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
        roster={"bench": 6, "roster_size": 16},
    )


def _board() -> BoardConstants:
    projections = {
        "rb_a": 260.0,
        "rb_b": 230.0,
        "wr_a": 240.0,
        "wr_b": 210.0,
        "k_a": 140.0,
        "k_b": 130.0,
        "dst_a": 120.0,
    }
    positions = {
        "rb_a": "RB",
        "rb_b": "RB",
        "wr_a": "WR",
        "wr_b": "WR",
        "k_a": "K",
        "k_b": "K",
        "dst_a": "DST",
    }
    return BoardConstants(
        projections=projections,
        positions=positions,
        # Deliberately hand-set rather than recomputed: this test is about the CAP multiplier,
        # and a fixed surplus keeps the arithmetic checkable by eye.
        static_vorp={p: v - 100.0 for p, v in projections.items()},
        market_ranks={p: ("overall", float(i + 1)) for i, p in enumerate(projections)},
        consumption_demand={"RB": 2.0, "WR": 2.0, "K": 1.0, "DST": 1.0},
        starter_demand={"RB": 2.0, "WR": 2.0, "K": 1.0, "DST": 1.0},
        survival_dispersion={},
        confidences={},
    )


def _state(roster_positions: list[str], roster_ids: list[str]) -> PickState:
    board = _board()
    return PickState(
        season=2023,
        ecr_type="ro",
        roster_player_ids=list(roster_ids),
        roster_positions=list(roster_positions),
        available={p for p in board.projections if p not in roster_ids},
        current_pick_overall=40,
        next_pick_overall=None,
    )


def _scores(state: PickState, variant: ScoringVariant) -> dict[str, float]:
    # `score_board` never reads its connection argument; passing None keeps the suite offline.
    return {s.player_id: s.score for s in score_board(None, _league(), _board(), state, variant)}


class TestArmsAreOneMechanismWide:
    def test_the_control_is_productions_defaults_field_for_field(self):
        """A control that has drifted from `ScoringVariant()` makes every D113 margin a
        measurement of the harness rather than of capacity."""
        control = MODULE.VARIANTS[MODULE.CONTROL]
        default = ScoringVariant()
        for field in default.__dataclass_fields__:
            if field == "name":
                continue
            assert getattr(control, field) == getattr(default, field), field

    def test_t1_differs_from_the_control_in_exactly_one_field(self):
        control = MODULE.VARIANTS[MODULE.CONTROL]
        t1 = MODULE.VARIANTS[MODULE.PRIMARY_TREATMENT]
        differing = [
            f
            for f in control.__dataclass_fields__
            if f != "name" and getattr(control, f) != getattr(t1, f)
        ]
        assert differing == ["use_cap_multiplier"]
        assert t1.use_cap_multiplier is False

    def test_t2_differs_in_exactly_the_two_saturation_fields(self):
        control = MODULE.VARIANTS[MODULE.CONTROL]
        t2 = MODULE.VARIANTS[MODULE.SECONDARY_TREATMENT]
        differing = sorted(
            f
            for f in control.__dataclass_fields__
            if f != "name" and getattr(control, f) != getattr(t2, f)
        )
        assert differing == ["use_cap_multiplier", "use_fit_multiplier"]

    def test_no_arm_defers_a_position_or_overrides_demand(self):
        """The harness can hold positions off the board and re-target demand. D113 must use
        neither -- either would be a new capacity rule rather than the removal of the old one."""
        for variant in MODULE.VARIANTS.values():
            assert variant.diagnostic_defer_positions == ()
            assert variant.demand_override == {}
            assert variant.demand_scale == {}
            assert variant.value_base == "msv_plus_vorp"
            assert variant.replacement_mode == "demand_boundary"


class TestTheTreatmentRemovesTheCapAndNothingElse:
    def test_identical_scores_when_no_position_is_over_its_cap(self):
        state = _state(["RB", "WR"], ["rb_a", "wr_a"])
        control = _scores(state, MODULE.VARIANTS[MODULE.CONTROL])
        treatment = _scores(state, MODULE.VARIANTS[MODULE.PRIMARY_TREATMENT])
        assert control == pytest.approx(treatment)

    def test_over_cap_candidates_differ_by_exactly_the_multiplier(self):
        """One kicker already on the roster is already AT this league's K capacity of 2? No --
        capacity is 2, so the second kicker is unpenalised and the third is penalised. Hold two,
        and `k_b` is over cap while every other position is untouched."""
        league = _league()
        assert positional_feasibility_cap(league, "K") == 2
        state = _state(["K", "K"], ["k_a", "wr_a"])
        control = _scores(state, MODULE.VARIANTS[MODULE.CONTROL])
        treatment = _scores(state, MODULE.VARIANTS[MODULE.PRIMARY_TREATMENT])
        assert control["k_b"] == pytest.approx(treatment["k_b"] * OVER_CAP_VALUE_MULTIPLIER)
        for player_id in control:
            if player_id != "k_b":
                assert control[player_id] == pytest.approx(treatment[player_id]), player_id

    def test_the_penalty_is_hard_rather_than_tapered(self):
        """The body AT the cap is unpenalised and the next one is penalised in full -- there is
        no gradual onset, which is why the mechanism can flip a pick outright."""
        at_cap = _state(["K"], ["k_a"])
        over_cap = _state(["K", "K"], ["k_a", "wr_a"])
        control = MODULE.VARIANTS[MODULE.CONTROL]
        treatment = MODULE.VARIANTS[MODULE.PRIMARY_TREATMENT]
        assert _scores(at_cap, control)["k_b"] == pytest.approx(_scores(at_cap, treatment)["k_b"])
        assert _scores(over_cap, control)["k_b"] != pytest.approx(
            _scores(over_cap, treatment)["k_b"]
        )


class TestTheSignPropertyOfTheMultiplier:
    def test_a_negative_score_is_moved_upward_by_the_penalty(self):
        """`score *= 0.1` on a SIGNED score. A candidate already scored below zero is moved
        TOWARD zero, i.e. promoted relative to other negative-scored candidates. This is a
        property of the shipped arithmetic; D113 measures how often it bites on real boards."""
        penalised = -50.0 * OVER_CAP_VALUE_MULTIPLIER
        assert penalised > -50.0

    def test_the_mechanism_note_records_the_sign_property(self):
        note = MODULE.run_mechanism.__doc__
        assert "negative" in note.lower()


class TestPreRegisteredRuleIsMechanical:
    @pytest.mark.parametrize(
        "mean_diff,half_width,expected",
        [
            (10.0, 5.0, "BELOW DETECTION FLOOR"),
            (-10.0, 5.0, "BELOW DETECTION FLOOR"),
            (171.9, 5.0, "BELOW DETECTION FLOOR"),
            (200.0, 500.0, "CI SPANS ZERO"),
            (200.0, 50.0, "WEAK"),
            (400.0, 50.0, "RESOLVED"),
            (-400.0, 50.0, "RESOLVED"),
        ],
    )
    def test_verdicts(self, mean_diff, half_width, expected):
        assert expected in MODULE._verdict(mean_diff, half_width)

    def test_the_detection_floor_is_quoted_not_invented(self):
        assert MODULE.DETECTION_FLOOR == (172.0, 250.0)
        assert MODULE.ECONOMIC_THRESHOLD == 25.0

    def test_the_season_window_is_the_committed_backtest_window(self):
        assert BACKTEST_SEASONS == (2021, 2022, 2023, 2024, 2025)
        assert 2020 not in BACKTEST_SEASONS

    def test_ci_reproduces_the_d104_convention(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        md, t, ci, half = MODULE._ci(values)
        assert md == pytest.approx(30.0)
        assert t == pytest.approx(30.0 / (15.811388 / 5**0.5), rel=1e-5)
        assert half == pytest.approx(2.776 * 15.811388 / 5**0.5, rel=1e-5)
        assert ci.startswith("[")

    def test_a_single_season_cannot_manufacture_an_interval(self):
        md, t, ci, half = MODULE._ci([42.0])
        assert md == 42.0
        assert ci == "n/a"


class TestPhasePartition:
    def test_every_round_of_a_16_round_draft_lands_in_exactly_one_phase(self):
        for round_no in range(1, 17):
            assert MODULE._phase_of(round_no) in {label for label, _, _ in MODULE.PHASES}
            assert MODULE._phase_of(round_no, MODULE.D103_PHASES) in {
                label for label, _, _ in MODULE.D103_PHASES
            }

    def test_the_user_specified_partition_is_r1_6_r7_11_r12_16(self):
        assert MODULE.PHASES == (("R1-6", 1, 6), ("R7-11", 7, 11), ("R12-16", 12, 16))

    def test_d103s_own_partition_is_kept_alongside_for_comparability(self):
        assert MODULE.D103_PHASES[0][1:] == (1, 5)


class TestPopulation:
    def test_the_negative_control_format_has_no_kicker_or_defense_slot(self):
        """`legacy_2qb_dynasty` is in the grid precisely because capacity cannot bind on K/DST
        there -- it has neither slot. If D113's effect is a K/DST effect it must vanish here."""
        from alpha_squad.league.context import load_league_context

        legacy = load_league_context(
            Path("src/alpha_squad/config/league_configs/legacy_2qb_dynasty.yaml")
        )
        assert "K" not in legacy.dedicated_slots()
        assert "DST" not in legacy.dedicated_slots()
        assert positional_feasibility_cap(legacy, "K") == 0

    def test_the_primary_format_is_the_target_format(self):
        assert MODULE.PRIMARY_FORMAT == "target_league"
        assert MODULE.FORMATS[0] == "target_league"

    def test_all_ten_snake_seats_are_in_the_default_grid(self):
        assert tuple(range(1, 11)) == MODULE.DEFAULT_SLOTS
