"""Unit tests for D112's feasibility audit (`scripts/research/d112_feasibility_audit.py`).

D112's conclusion is a NEGATIVE one — the legality constraint never binds on Alpha — and a
negative result is only worth anything if the instrument that produced it could have detected the
positive. So these tests are mostly about making the detector fire:

  * the A/B/C/D classifier returns **C** on a roster that genuinely is at the feasibility frontier
    with a better non-deficit candidate available, and **D** when the restriction happens to agree;
  * the feasibility slack is the quantity claimed, including the identity that it falls by exactly
    one for a pick that does not fill a mandatory slot and is unchanged by one that does;
  * the reported margin is the one measured while a mandatory slot is still outstanding — the
    whole-draft minimum is arithmetic (it is always 1, at the final pick) and must not be quoted;
  * the capacity counterfactual recovers the un-penalised score exactly, since the penalty is a
    pure multiplication by `OVER_CAP_VALUE_MULTIPLIER`;
  * the parity gate raises rather than warning when the control drifts off D111's baseline.

Loaded the same way `test_d111_ecr_incremental.py` loads its runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster import OVER_CAP_VALUE_MULTIPLIER, unfilled_dedicated_slots

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "research"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load("d112_feasibility_audit")


def _league() -> LeagueContext:
    """The shipped target shape in miniature: six dedicated slots, one flex, a small bench."""
    return LeagueContext(
        league_id="d112_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1},
        roster={"bench": 1, "roster_size": 8},
    )


class _Scored:
    """The four fields the classifier reads off a `CandidateScore`."""

    def __init__(self, player_id, position, score, feasibility_multiplier=None):
        self.player_id = player_id
        self.position = position
        self.score = score
        self.feasibility_multiplier = feasibility_multiplier


def classify(league, roster_positions, picks_remaining, scored):
    """`MODULE.classify_pick` with Alpha's unrestricted argmax supplied, which is what the runner
    passes. Calls the runner's own function, so these tests pin the real code path rather than a
    restatement of it."""
    pick = sorted(scored, key=lambda c: (-c.score, c.player_id))[0].player_id
    return MODULE.classify_pick(league, roster_positions, picks_remaining, scored, pick)[1]


class TestTheClassifierCanFire:
    def test_C_when_the_constraint_changes_the_pick(self):
        """The detector must be able to return C, or a measured 0% of C means nothing.

        Roster holds QB/RB/WR/TE/K — only DEF is outstanding — with exactly one pick left. The
        best-scoring candidate is a WR; legality must force the DST."""
        league = _league()
        roster = ["QB", "RB", "WR", "TE", "K"]
        assert sum(unfilled_dedicated_slots(league, roster).values()) == 1
        scored = [_Scored("wr_best", "WR", 100.0), _Scored("dst_ok", "DST", 10.0)]
        assert classify(league, roster, picks_remaining=1, scored=scored) == "C"

    def test_D_when_the_constraint_binds_but_agrees(self):
        league = _league()
        roster = ["QB", "RB", "WR", "TE", "K"]
        scored = [_Scored("dst_ok", "DST", 100.0), _Scored("wr_best", "WR", 10.0)]
        assert classify(league, roster, picks_remaining=1, scored=scored) == "D"

    def test_B_when_a_slot_is_outstanding_but_there_is_room(self):
        league = _league()
        roster = ["QB", "RB", "WR", "TE", "K"]
        scored = [_Scored("wr_best", "WR", 100.0), _Scored("dst_ok", "DST", 10.0)]
        assert classify(league, roster, picks_remaining=5, scored=scored) == "B"

    def test_A_when_every_mandatory_slot_is_filled(self):
        league = _league()
        roster = ["QB", "RB", "WR", "TE", "K", "DST"]
        assert unfilled_dedicated_slots(league, roster) == {}
        scored = [_Scored("wr_best", "WR", 100.0)]
        assert classify(league, roster, picks_remaining=2, scored=scored) == "A"

    def test_the_slot_alias_is_respected_so_DEF_is_filled_by_DST(self):
        """A config's `DEF` slot is filled by the `DST` position (CLAUDE.md D58). If the alias
        were missing the slot would never register as filled and every draft would look illegal —
        which would fake the very problem this phase is testing for."""
        league = _league()
        assert "DST" in unfilled_dedicated_slots(league, ["QB", "RB", "WR", "TE", "K"])
        assert unfilled_dedicated_slots(league, ["QB", "RB", "WR", "TE", "K", "DST"]) == {}


class TestFeasibilitySlack:
    def test_slack_starts_at_rounds_minus_mandatory_slots(self):
        league = _league()
        total = sum(unfilled_dedicated_slots(league, []).values())
        rounds = int(league.roster["roster_size"])
        assert rounds - total == 8 - 6  # 8 rounds, 6 dedicated slots

    def test_a_pick_that_fills_a_mandatory_slot_leaves_slack_unchanged(self):
        league = _league()
        before = 5 - sum(unfilled_dedicated_slots(league, ["QB"]).values())
        after = 4 - sum(unfilled_dedicated_slots(league, ["QB", "RB"]).values())
        assert before == after

    def test_a_pick_that_does_not_fill_a_mandatory_slot_costs_one_slack(self):
        league = _league()
        before = 5 - sum(unfilled_dedicated_slots(league, ["QB"]).values())
        after = 4 - sum(unfilled_dedicated_slots(league, ["QB", "QB"]).values())
        assert after == before - 1

    def test_the_rule_activates_exactly_at_zero_slack(self):
        league = _league()
        roster = ["QB", "RB", "WR", "TE", "K"]
        deficit = sum(unfilled_dedicated_slots(league, roster).values())
        scored = [_Scored("wr_best", "WR", 100.0), _Scored("dst_ok", "DST", 10.0)]
        # slack = picks_remaining - deficit; the restriction fires at slack <= 0 and not before.
        assert classify(league, roster, picks_remaining=deficit + 1, scored=scored) == "B"
        assert classify(league, roster, picks_remaining=deficit, scored=scored) == "C"


class TestTheReportedMarginIsTheLiveOne:
    def test_the_whole_draft_minimum_is_arithmetic_not_a_feasibility_fact(self):
        """Once the deficit is zero, slack is just `picks_remaining`, so the whole-draft minimum
        is 1 at the final pick in every draft that finishes legally. The runner records both and
        the report quotes `min_live_slack`; this pins the distinction that makes that necessary."""
        rows = [
            {"round": 1, "slack": 8, "total_deficit": 6},
            {"round": 5, "slack": 5, "total_deficit": 2},
            {"round": 7, "slack": 2, "total_deficit": 0},
            {"round": 8, "slack": 1, "total_deficit": 0},
        ]
        live = [r for r in rows if r["total_deficit"] > 0]
        assert min(r["slack"] for r in rows) == 1  # arithmetic, at the last pick
        assert min(r["slack"] for r in live) == 5  # the real margin
        assert max(r["round"] for r in live) == 5


class TestCapacityCounterfactual:
    def test_the_uncapped_score_is_recovered_exactly(self):
        """The penalty is a pure multiply, so dividing it out is exact rather than an estimate."""
        raw = 123.456
        penalised = raw * OVER_CAP_VALUE_MULTIPLIER
        assert penalised / OVER_CAP_VALUE_MULTIPLIER == pytest.approx(raw, rel=1e-12)

    def test_removing_the_cap_can_change_the_argmax(self):
        scored = [
            _Scored(
                "qb3",
                "QB",
                90.0 * OVER_CAP_VALUE_MULTIPLIER,
                feasibility_multiplier=OVER_CAP_VALUE_MULTIPLIER,
            ),
            _Scored("te2", "TE", 50.0),
        ]
        capped = sorted(scored, key=lambda c: (-c.score, c.player_id))[0].player_id
        uncapped = sorted(
            scored,
            key=lambda c: (
                -(
                    c.score / OVER_CAP_VALUE_MULTIPLIER
                    if c.feasibility_multiplier is not None
                    else c.score
                ),
                c.player_id,
            ),
        )[0].player_id
        assert capped == "te2"
        assert uncapped == "qb3"


class TestRegisteredDesign:
    def test_the_parity_gate_raises_rather_than_warns(self):
        with pytest.raises(MODULE.ParityError):
            MODULE.report_parity(
                {"vintage": "x", "means": {"target_league": 1900.0, "dynasty_1qb": 2061.5}}
            )

    def test_the_parity_target_is_d111s_recorded_control(self):
        assert MODULE.D111_CONTROL == {"target_league": 2002.9, "dynasty_1qb": 2061.5}

    def test_the_audit_walks_every_draft_slot(self):
        assert list(MODULE.ALL_SLOTS) == list(range(1, 11))
        assert MODULE.D111_SLOTS == (1, 4, 7, 10)

    def test_all_six_positions_are_audited(self):
        assert MODULE.POSITIONS == ("QB", "RB", "WR", "TE", "K", "DST")
