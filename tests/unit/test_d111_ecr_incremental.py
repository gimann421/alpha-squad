"""Unit tests for D111's ECR consensus arms (`scripts/research/d111_ecr_incremental.py`).

D111's whole claim is that the treatment differs from the control by the pre-registered ECR input
and by nothing else. That claim rests on properties of two functions, so they are pinned here
rather than asserted in prose:

  * **w = 0 is the control, exactly.** Both methods must be provable identities at zero weight --
    otherwise "Y1 + ECR vs Y1" is measuring an implementation difference, which is the class of
    silent harness defect D78, D85 and D93 each shipped once;
  * **w = 1 under M1 restricted to QB/RB/WR/TE is D104's `ecr_ordered_static`**, asserted against
    D104's own committed function rather than against a re-derivation of it -- that is what makes
    the ladder's far endpoint a published number instead of a new one;
  * the multiset of projected values at every position is exactly Y1's, so replacement levels,
    scarcity and the positional value scale do not move and the arm is an INFORMATION change;
  * the candidate universe is identical (pool parity);
  * ordering is a genuine equal-weight consensus -- it must differ from BOTH sources when they
    disagree, or the "consensus" is really just one of them;
  * every tie resolves deterministically (D54), and a tie in the BLENDED key falls back to the
    control's own order rather than to `player_id` -- PRE-REGISTRATION AMENDMENT 1, the one place
    an alphabetical accident could otherwise masquerade as ECR information;
  * no realized outcome is read by any arm but the quarantined `ORACLE_Y1`.

Loaded the same way `test_d104_ecr_floor.py` loads its runner."""

from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path

import pytest

from alpha_squad.league.context import LeagueContext

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "research"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load("d111_ecr_incremental")
D104 = _load("d104_ecr_floor")


def _league() -> LeagueContext:
    return LeagueContext(
        league_id="d111_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1},
        roster={"bench": 2, "roster_size": 8},
    )


def _static(**overrides):
    """A `SeasonStatic` whose Y1 order DISAGREES with the ECR order at WR, so a blend that
    silently reduced to either source would be visible."""
    from alpha_squad.evaluation.draft_forensics import SeasonStatic

    positions = {
        "wr_a": "WR",
        "wr_b": "WR",
        "wr_c": "WR",
        "wr_d": "WR",
        "wr_unranked": "WR",
        "rb_a": "RB",
        "rb_b": "RB",
        "k_a": "K",
        "k_b": "K",
    }
    base = dict(
        season=2023,
        ecr_type="ro",
        # Y1 likes wr_a > wr_b > wr_c > wr_d; ECR below reverses it exactly.
        projections={
            "wr_a": 300.0,
            "wr_b": 250.0,
            "wr_c": 200.0,
            "wr_d": 180.0,
            "wr_unranked": 111.0,
            "rb_a": 280.0,
            "rb_b": 240.0,
            "k_a": 130.0,
            "k_b": 120.0,
        },
        positions=positions,
        vorp={p: 0.0 for p in positions},
        replacement_levels={"WR": 150.0, "RB": 150.0, "K": 100.0},
        scarcity_raw={"WR": 1.0, "RB": 2.0, "K": 3.0},
        scarcity_norm={"WR": 0.1, "RB": 0.5, "K": 0.9},
        market_rank={
            "wr_a": ("WR", 40.0),
            "wr_b": ("WR", 30.0),
            "wr_c": ("WR", 20.0),
            "wr_d": ("WR", 10.0),
            "rb_a": ("RB", 8.0),
            "rb_b": ("RB", 4.0),
            "k_a": ("K", 200.0),
            "k_b": ("K", 190.0),
        },
        confidence={p: 0.7 for p in positions},
        ecr_dispersion={p: (1.0, 5.0) for p in positions},
        consumption_demand={"WR": 4.0, "RB": 3.0, "K": 1.0},
    )
    base.update(overrides)
    return SeasonStatic(**base)


class _Scored:
    """The two fields `consensus_pick` reads off a `CandidateScore`."""

    def __init__(self, player_id: str, score: float):
        self.player_id = player_id
        self.score = score


# --------------------------------------------------------------------------------------------
# P2 -- w = 0 is the control, provably
# --------------------------------------------------------------------------------------------
class TestZeroWeightIsTheControl:
    def test_board_blend_at_w0_returns_the_control_board_exactly(self):
        static = _static()
        out, moved, _ = MODULE.blended_static(_league(), static, 0.0)
        assert out.projections == static.projections
        assert moved == 0

    def test_board_blend_at_w0_is_a_noop_even_with_exact_projection_ties(self):
        """Exact within-position ties exist on the real board (WR 42 surplus rows in the sampled
        seasons), and a tie is precisely where an ordering convention can leak in."""
        static = _static(
            projections={
                "wr_a": 250.0,
                "wr_b": 250.0,
                "wr_c": 250.0,
                "wr_d": 180.0,
                "wr_unranked": 111.0,
                "rb_a": 280.0,
                "rb_b": 240.0,
                "k_a": 130.0,
                "k_b": 120.0,
            }
        )
        out, moved, _ = MODULE.blended_static(_league(), static, 0.0)
        assert out.projections == static.projections
        assert moved == 0

    def test_decision_blend_at_w0_returns_y1s_own_pick(self):
        static = _static()
        scored = [_Scored("wr_a", 10.0), _Scored("wr_d", 9.0), _Scored("rb_a", 8.0)]
        assert MODULE.consensus_pick(static, scored, 0.0) == "wr_a"

    def test_decision_blend_at_w0_uses_y1s_own_tie_break(self):
        """`_pick_by_tier` selects by `(-score, player_id)`; w = 0 must reproduce that, ties and
        all, or the control is not the control."""
        static = _static()
        scored = [_Scored("wr_d", 10.0), _Scored("wr_a", 10.0)]
        assert MODULE.consensus_pick(static, scored, 0.0) == "wr_a"


# --------------------------------------------------------------------------------------------
# the far endpoint -- w = 1 is D104's published arm
# --------------------------------------------------------------------------------------------
class TestFullWeightReproducesD104:
    def test_w1_on_skill_positions_is_d104s_ecr_ordered_static(self):
        """Asserted against D104's own committed function, so the ladder's endpoint is a published
        number rather than a fresh one."""
        static = _static()
        mine, _, _ = MODULE.blended_static(_league(), static, 1.0, MODULE.SKILL)
        theirs, _ = D104.ecr_ordered_static(_league(), static)
        assert mine.projections == theirs.projections
        assert mine.vorp == theirs.vorp

    def test_w1_orders_by_ecr_rank_ascending(self):
        static = _static()
        out, moved, _ = MODULE.blended_static(_league(), static, 1.0)
        assert out.projections["wr_d"] == 300.0  # ECR 10 -- best
        assert out.projections["wr_c"] == 250.0
        assert out.projections["wr_b"] == 200.0
        assert out.projections["wr_a"] == 180.0
        assert moved > 0


# --------------------------------------------------------------------------------------------
# it is a genuine consensus, not either source wearing a hat
# --------------------------------------------------------------------------------------------
class TestConsensusIsGenuinelyBoth:
    def test_the_half_weight_blend_differs_from_both_sources(self):
        """Y1 ranks the WRs a > b > c > d; this ECR ranks them c > d > a > b -- a rotation rather
        than a reversal, so the consensus has a STRICT opinion and lands on a > c > b > d, which is
        neither source's ordering."""
        static = _static(
            market_rank={
                "wr_c": ("WR", 10.0),
                "wr_d": ("WR", 20.0),
                "wr_a": ("WR", 30.0),
                "wr_b": ("WR", 40.0),
                "rb_a": ("RB", 8.0),
                "rb_b": ("RB", 4.0),
            }
        )
        half, _, _ = MODULE.blended_static(_league(), static, 0.5)
        y1, _, _ = MODULE.blended_static(_league(), static, 0.0)
        ecr, _, _ = MODULE.blended_static(_league(), static, 1.0)
        assert half.projections != y1.projections
        assert half.projections != ecr.projections
        assert [half.projections[p] for p in ("wr_a", "wr_c", "wr_b", "wr_d")] == [
            300.0,
            250.0,
            200.0,
            180.0,
        ]

    def test_a_tie_in_the_blended_key_falls_back_to_the_CONTROL_order(self):
        """PRE-REGISTRATION AMENDMENT 1. With Y1 and ECR exactly reversed over four WRs every mean
        rank is 1.5, so the consensus is genuinely indifferent. It must then keep Y1's ordering --
        NOT manufacture an alphabetical one, which is the degeneracy Phase 0 rejected
        `ecr_implied_baseline` for."""
        static = _static()
        half, _, _ = MODULE.blended_static(_league(), static, 0.5)
        for player in ("wr_a", "wr_b", "wr_c", "wr_d"):
            assert half.projections[player] == static.projections[player], player

    def test_the_blend_moves_monotonically_with_the_weight(self):
        """A player ECR likes more than Y1 does must not lose value as ECR's weight rises."""
        static = _static()
        values = [
            MODULE.blended_static(_league(), static, w)[0].projections["wr_d"]
            for w in MODULE.WEIGHT_LADDER
        ]
        assert values == sorted(values), values

    def test_decision_blend_at_w1_is_best_available_by_ecr(self):
        static = _static()
        scored = [_Scored("wr_a", 10.0), _Scored("wr_d", 1.0), _Scored("rb_a", 5.0)]
        # ECR: rb_a 8 < wr_d 10 < wr_a 40.
        assert MODULE.consensus_pick(static, scored, 1.0) == "rb_a"

    def test_decision_blend_sorts_unranked_candidates_last(self):
        """`best_by_market_rank`'s convention: a player the board does not rank still has to be
        pickable, but never preferred to a ranked one on the ECR vote alone."""
        static = _static()
        scored = [_Scored("wr_unranked", 10.0), _Scored("wr_a", 9.0)]
        assert MODULE.consensus_pick(static, scored, 1.0) == "wr_a"


# --------------------------------------------------------------------------------------------
# P3/P4 -- it is an information change, not a valuation change
# --------------------------------------------------------------------------------------------
class TestInformationNotValuation:
    @pytest.mark.parametrize("w", MODULE.WEIGHT_LADDER)
    def test_the_value_multiset_is_preserved_per_position(self, w):
        static = _static()
        out, _, _ = MODULE.blended_static(_league(), static, w)
        for position in ("WR", "RB", "K"):
            before = sorted(
                v for p, v in static.projections.items() if static.positions[p] == position
            )
            after = sorted(v for p, v in out.projections.items() if out.positions[p] == position)
            assert before == after, (position, w)

    @pytest.mark.parametrize("w", MODULE.WEIGHT_LADDER)
    def test_the_candidate_universe_is_identical(self, w):
        static = _static()
        out, _, _ = MODULE.blended_static(_league(), static, w)
        assert set(out.projections) == set(static.projections)

    def test_only_projections_and_vorp_change(self, monkeypatch):
        monkeypatch.setattr(
            MODULE, "marginal_value_over_replacement", lambda league, proj, pos: dict(proj)
        )
        static = _static()
        # w = 1 rather than 0.5: the fixture's WRs are exactly antisymmetric, so at 0.5 the
        # consensus is indifferent and AMENDMENT 1 correctly leaves the projections alone.
        out, _, _ = MODULE.blended_static(_league(), static, 1.0)
        changed = {
            f.name
            for f in dataclasses.fields(static)
            if getattr(out, f.name) != getattr(static, f.name)
        }
        assert changed == {"projections", "vorp"}, sorted(changed)

    def test_a_blend_that_broke_the_multiset_is_refused(self):
        """A guard that cannot fire is not a guard."""
        static = _static()
        real_sorted = sorted

        def _bad(values, *, key=None, reverse=False):
            ordered = real_sorted(values, key=key, reverse=reverse)
            return [v + 1.0 for v in ordered] if reverse else ordered

        MODULE.__dict__["sorted"] = _bad
        try:
            with pytest.raises(MODULE.SubstitutionError, match="multiset"):
                MODULE.blended_static(_league(), static, 0.5)
        finally:
            del MODULE.__dict__["sorted"]

    def test_unranked_players_keep_their_y1_value(self):
        static = _static()
        out, _, _ = MODULE.blended_static(_league(), static, 0.5)
        assert out.projections["wr_unranked"] == static.projections["wr_unranked"]

    def test_a_position_with_fewer_than_two_ranked_players_is_left_alone(self):
        """Pre-registered invalid-cell rule (b): the permutation is undefined on a singleton."""
        static = _static(market_rank={"wr_a": ("WR", 30.0), "rb_a": ("RB", 8.0)})
        out, _, _ = MODULE.blended_static(_league(), static, 0.5)
        assert out.projections == static.projections

    def test_kickers_and_defenses_are_included_by_default(self):
        """D111's correction to D104: `ro`/`redraft-overall` DOES rank K and DST (30-37 kickers and
        31-32 defenses every season), so holding them fixed is what produced D104's RB->K confound
        rather than a property of the board."""
        static = _static()
        out, _, _ = MODULE.blended_static(_league(), static, 1.0)
        # ECR ranks k_b (190) ahead of k_a (200), Y1 has k_a ahead -- so the values must swap.
        assert out.projections["k_b"] == 130.0
        assert out.projections["k_a"] == 120.0

    def test_the_skill_only_position_set_still_leaves_k_alone(self):
        static = _static()
        out, _, _ = MODULE.blended_static(_league(), static, 1.0, MODULE.SKILL)
        assert out.projections["k_a"] == static.projections["k_a"]
        assert out.projections["k_b"] == static.projections["k_b"]


# --------------------------------------------------------------------------------------------
# D54 determinism
# --------------------------------------------------------------------------------------------
class TestDeterminism:
    def test_ties_in_the_blended_key_break_on_player_id(self):
        static = _static(
            market_rank={
                "wr_a": ("WR", 10.0),
                "wr_b": ("WR", 10.0),
                "wr_c": ("WR", 10.0),
                "wr_d": ("WR", 10.0),
                "rb_a": ("RB", 8.0),
                "rb_b": ("RB", 4.0),
            }
        )
        out, _, _ = MODULE.blended_static(_league(), static, 1.0)
        assert out.projections["wr_a"] == 300.0
        assert out.projections["wr_b"] == 250.0
        assert out.projections["wr_c"] == 200.0
        assert out.projections["wr_d"] == 180.0

    def test_repeated_blends_are_identical(self):
        static = _static()
        a, _, _ = MODULE.blended_static(_league(), static, 0.5)
        b, _, _ = MODULE.blended_static(_league(), static, 0.5)
        assert a.projections == b.projections

    def test_a_weight_outside_the_unit_interval_is_refused(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            MODULE.blended_static(_league(), _static(), 1.5)


# --------------------------------------------------------------------------------------------
# the registered design itself
# --------------------------------------------------------------------------------------------
class TestRegisteredDesign:
    def test_the_primary_weight_is_one_half(self):
        assert MODULE.PRIMARY_W == 0.5

    def test_the_primary_treatment_arms_are_the_registered_ones(self):
        assert MODULE.PRIMARY_ARMS == ("T1_ALL_w50", "T2_w50")

    def test_the_control_is_y1(self):
        assert MODULE.CONTROL == "Y1"

    def test_the_ladder_brackets_the_two_identities(self):
        assert MODULE.WEIGHT_LADDER[0] == 0.0
        assert MODULE.WEIGHT_LADDER[-1] == 1.0
        assert MODULE.PRIMARY_W in MODULE.WEIGHT_LADDER

    def test_the_detection_floor_is_d97s_and_is_not_re_derived(self):
        assert MODULE.DETECTION_FLOOR == (172.0, 250.0)

    @pytest.mark.parametrize(
        "arm,expected",
        [
            ("Y1", ("control", 0.0)),
            ("T1_ALL_w50", ("board", 0.5)),
            ("T1_SKILL_w100", ("board", 1.0)),
            ("T2_w25", ("decision", 0.25)),
            ("ECR_ALONE", ("ecr", 1.0)),
            ("ECR_ALONE_NAIVE", ("ecr_naive", 1.0)),
            ("ORACLE_Y1", ("oracle", 0.0)),
        ],
    )
    def test_arm_names_parse_to_the_registered_spec(self, arm, expected):
        method, w, _ = MODULE.arm_spec(arm)
        assert (method, w) == expected

    def test_t1_skill_uses_the_skill_position_set_and_t1_all_does_not(self):
        assert MODULE.arm_spec("T1_SKILL_w100")[2] == MODULE.SKILL
        assert MODULE.arm_spec("T1_ALL_w100")[2] == MODULE.ALL_POSITIONS

    def test_an_unknown_arm_is_refused(self):
        with pytest.raises(ValueError, match="unknown arm"):
            MODULE.arm_spec("T9_w50")

    def test_the_phase_convention_is_d103s(self):
        assert MODULE.phase_of(1) == "EARLY (1-5)"
        assert MODULE.phase_of(6) == "MIDDLE (6-10)"
        assert MODULE.phase_of(16) == "LATE (11-16)"


class TestStatistics:
    def test_an_effect_below_the_floor_is_unresolved_even_when_positive(self):
        assert "UNRESOLVED" in MODULE.verdict_for(120.0)
        assert "UNRESOLVED" in MODULE.verdict_for(-120.0)
        assert "UNRESOLVED" in MODULE.verdict_for(200.0)
        assert MODULE.verdict_for(300.0) == "ABOVE the floor"

    def test_the_mde_uses_the_registered_t_values(self):
        c = MODULE.contrast([0.0, 10.0, 20.0, 30.0, 40.0])
        expected = (MODULE.T_CRIT_95 + MODULE.T_POWER_80) * c["se"]
        assert c["mde"] == pytest.approx(expected)
        assert c["k"] == 5

    def test_the_contrast_counts_seasons_won_and_lost(self):
        c = MODULE.contrast([5.0, -5.0, 5.0, 0.0, 5.0])
        assert (c["wins"], c["losses"], c["k"]) == (3, 1, 5)
