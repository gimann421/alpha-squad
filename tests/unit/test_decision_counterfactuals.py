"""The counterfactual harness must be a faithful mirror of the production engine, or every
margin it reports is measuring the harness.

Two properties carry that weight and are tested directly here:

1. `ScoringVariant.control()` reproduces `recommend_draft_pick` -- same chosen player, same
   scores -- so a variant's delta is attributable to the variant.
2. The preloaded survival/confidence tables (a pure speed optimisation, ~280x) reproduce the
   production per-player lookups exactly, including the `page_type` scoping D56/D61 added and
   the `None` cases.

Plus the pre-registered gate logic (`evaluation/timing_replacement.py`), which is the thing
that decides whether anything ships and therefore must not be able to pass an arm it should
fail.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.decision_counterfactuals import (
    PickState,
    ScoringVariant,
    assert_control_reproduces_production,
    assert_preloads_match_production,
    load_board_constants,
    next_turn_replacement,
    score_board,
    simulate_variant_draft,
    starter_demand_per_team,
    survival_from,
)
from alpha_squad.evaluation.timing_replacement import GateResult, evaluate_gates, selection
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import next_pick_survival_probability
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

SEASON = 2024
ECR = "ro"


def _league() -> LeagueContext:
    return LeagueContext(
        league_id="t",
        format="redraft",
        teams=10,
        scoring={"ppr": True},
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1},
        roster={"bench": 6, "roster_size": 16},
    )


def _seed(con, player_id, position, points, ecr_rank, *, best=None, worst=None):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season,
             predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, ?, ?, current_timestamp)
        """,
        [
            f"p_{player_id}",
            player_id,
            SEASON,
            position,
            UNCERTAINTY_MODEL_VERSION,
            points,
            0.7 + (ecr_rank % 7) / 100.0,
            SEASON - 1,
        ],
    )
    con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, "
        "ecr_best, ecr_worst, page_type) VALUES (?, ?, 'ro', ?, ?, ?, ?, 'redraft-overall')",
        [
            player_id,
            f"{SEASON}-08-01",
            position,
            ecr_rank,
            best if best is not None else max(1.0, ecr_rank - 6),
            worst if worst is not None else ecr_rank + 9,
        ],
    )


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    rank = 1
    # Interleave positions so overall ECR rank and within-position rank are not the same
    # ordering -- otherwise a bug that confused the two would pass unnoticed.
    for i in range(40):
        for pos, scale in (("QB", 340.0), ("RB", 260.0), ("WR", 268.0), ("TE", 200.0)):
            _seed(connection, f"{pos.lower()}_{i:03d}", pos, scale - 3.1 * i, float(rank))
            rank += 1
    for i in range(14):
        _seed(connection, f"k_{i:03d}", "K", 180.0 - 3.0 * i, float(rank))
        rank += 1
        _seed(connection, f"dst_{i:03d}", "DST", 110.0 - 2.0 * i, float(rank))
        rank += 1
    yield connection
    connection.close()


class TestControlReproducesProduction:
    """If this fails, no counterfactual in this module means anything."""

    @pytest.mark.parametrize(
        ("current", "nxt", "roster"),
        [
            (1, 20, []),
            (20, 21, ["wr_000"]),  # the back-to-back turn: every opportunity cost is zero
            (21, 40, ["wr_000", "qb_000"]),
            (60, 61, ["wr_000", "qb_000", "rb_000", "wr_001", "rb_001"]),
        ],
    )
    def test_control_matches_the_engine_at_every_kind_of_pick(self, con, current, nxt, roster):
        league = _league()
        board = load_board_constants(con, league, SEASON, ECR)
        available = set(board.projections) - set(roster)
        state = PickState(
            season=SEASON,
            ecr_type=ECR,
            roster_player_ids=list(roster),
            roster_positions=[board.positions[p] for p in roster],
            available=available,
            current_pick_overall=current,
            next_pick_overall=nxt,
            next_changed_board_pick=nxt if nxt > current + 1 else nxt + 19,
        )
        # Raises on any disagreement in chosen player or in any top-10 score.
        assert_control_reproduces_production(con, league, board, state)

    def test_a_deliberately_wrong_variant_does_not_match(self, con):
        """The check above is only meaningful if it can fail."""
        league = _league()
        board = load_board_constants(con, league, SEASON, ECR)
        state = PickState(
            season=SEASON,
            ecr_type=ECR,
            roster_player_ids=[],
            roster_positions=[],
            available=set(board.projections),
            current_pick_overall=1,
            next_pick_overall=20,
            next_changed_board_pick=20,
        )
        control = score_board(con, league, board, state, ScoringVariant.control())
        no_msv = score_board(
            con, league, board, state, ScoringVariant(name="x", value_base="vorp_only")
        )
        assert control[0].score != pytest.approx(no_msv[0].score)


class TestPreloadsMatchProduction:
    def test_survival_and_confidence_preloads_agree_on_every_player(self, con):
        board = load_board_constants(con, _league(), SEASON, ECR)
        for next_pick in (2, 20, 21, 40, 160):
            assert_preloads_match_production(con, board, SEASON, ECR, next_pick)

    def test_a_player_with_no_dispersion_on_record_gives_none_both_ways(self, con):
        con.execute("DELETE FROM market_snapshot WHERE player_id = 'rb_000'")
        board = load_board_constants(con, _league(), SEASON, ECR)
        assert next_pick_survival_probability(con, "rb_000", 20, SEASON, ECR) is None
        assert survival_from(board.survival_dispersion.get("rb_000"), 20) is None

    def test_survival_arithmetic_covers_the_boundary_cases(self):
        assert survival_from((5.0, 5.0), 4) == 1.0
        assert survival_from((5.0, 5.0), 5) == 0.0
        assert survival_from((10.0, 30.0), 10) == 1.0
        assert survival_from((10.0, 30.0), 30) == 0.0
        assert survival_from((10.0, 30.0), 20) == pytest.approx(0.5)
        assert survival_from(None, 20) is None
        assert survival_from((10.0, 30.0), None) is None


class TestStarterDemand:
    def test_it_sums_to_the_lineup_size(self, con):
        """Starter demand's structural anchor, the counterpart of consumption demand summing to
        `roster_size`: exactly `lineup` players per team can start."""
        league = _league()
        board = load_board_constants(con, league, SEASON, ECR)
        demand = starter_demand_per_team(league, board.projections, board.positions)
        assert sum(demand.values()) == pytest.approx(float(sum(league.lineup.values())))

    def test_it_is_shallower_than_consumption_demand_at_every_position(self, con):
        """The premise of the whole starter-vs-consumption question: a draft consumes more of
        each position than it starts, so a starter boundary is never deeper."""
        board = load_board_constants(con, _league(), SEASON, ECR)
        for pos, consumed in board.consumption_demand.items():
            assert board.starter_demand.get(pos, 0.0) <= consumed + 1e-9

    def test_a_two_qb_league_demands_more_starting_qbs(self, con):
        board = load_board_constants(con, _league(), SEASON, ECR)
        two_qb = LeagueContext(
            league_id="t2",
            format="redraft",
            teams=10,
            lineup={"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2},
            roster={"bench": 8, "roster_size": 17},
        )
        one = starter_demand_per_team(_league(), board.projections, board.positions)
        two = starter_demand_per_team(two_qb, board.projections, board.positions)
        assert two["QB"] > one["QB"]


class TestNextTurnReplacement:
    def test_it_is_the_best_survivor_not_an_end_of_draft_boundary(self, con):
        """VONA's defining property: the level is a player who is still on the board after the
        opponents pick, so it is always at least as high as any end-of-draft boundary."""
        league = _league()
        board = load_board_constants(con, league, SEASON, ECR)
        state = PickState(
            season=SEASON,
            ecr_type=ECR,
            roster_player_ids=[],
            roster_positions=[],
            available=set(board.projections),
            current_pick_overall=1,
            next_pick_overall=20,
            next_changed_board_pick=20,
        )
        vona = next_turn_replacement(board, state)
        demand = score_board(con, league, board, state, ScoringVariant.control())
        end_of_draft = {s.position: s.replacement_level for s in demand}
        for pos, level in vona.items():
            if end_of_draft.get(pos) is not None:
                assert level >= end_of_draft[pos] - 1e-9

    def test_a_zero_gap_turn_has_no_timing_information_without_the_lookahead(self, con):
        """At a back-to-back turn the next pick is one away, so nothing can be gone -- the
        reason arm T1 reads `next_changed_board_pick` rather than `next_pick_overall`."""
        league = _league()
        board = load_board_constants(con, league, SEASON, ECR)
        state = PickState(
            season=SEASON,
            ecr_type=ECR,
            roster_player_ids=[],
            roster_positions=[],
            available=set(board.projections),
            current_pick_overall=20,
            next_pick_overall=21,
            next_changed_board_pick=None,
        )
        assert next_turn_replacement(board, state) == {}


class TestVariantDraft:
    def test_the_control_draft_is_the_production_draft(self, con):
        """End to end: a full 16-round draft under the control variant must make the same picks
        production's own engine would, verified pick by pick."""
        league = _league()
        result = simulate_variant_draft(
            con, league, SEASON, 1, ScoringVariant.control(), ecr_type=ECR, verify_control=True
        )
        assert len(result.drafted_player_ids) == int(league.roster["roster_size"])
        assert len(set(result.drafted_player_ids)) == len(result.drafted_player_ids)

    def test_every_seat_gets_a_full_roster_and_nobody_is_drafted_twice(self, con):
        league = _league()
        r1 = simulate_variant_draft(
            con,
            league,
            SEASON,
            4,
            ScoringVariant(name="t1", replacement_mode="next_turn"),
            ecr_type=ECR,
        )
        assert len(r1.drafted_player_ids) == 16
        assert r1.n_unfilled_mandatory_slots >= 0


class TestPreRegisteredGates:
    @staticmethod
    def _summary(
        points, *, seasons_won=5, slots_won=10, unfilled=0.0, ci=(10.0, 50.0), counts=None
    ):
        return {
            "mean_starter_points": points,
            "seasons_won": seasons_won,
            "slots_won": slots_won,
            "mean_unfilled": unfilled,
            "clustered_ci": ci,
            "mean_counts": counts
            or {"QB": 2.0, "RB": 3.0, "WR": 5.0, "TE": 2.0, "K": 2.0, "DST": 2.0},
        }

    def _gates(self, arm, control):
        return {
            g.gate: g
            for g in evaluate_gates(
                arm, control, legacy_arm_summary=arm, legacy_control_summary=control
            )
        }

    def test_a_clearly_better_arm_passes_everything(self):
        gates = self._gates(self._summary(2200.0), self._summary(2000.0))
        assert all(g.passed for g in gates.values())

    def test_an_unresolvable_gain_fails_g6(self):
        """The binding gate, and the one this project's history says will decide the outcome:
        a positive point estimate whose season-clustered interval contains zero does not ship."""
        gates = self._gates(self._summary(2040.0, ci=(-90.0, 170.0)), self._summary(2000.0))
        assert gates["G1"].passed
        assert not gates["G6"].passed

    def test_an_interval_excluding_zero_on_the_losing_side_fails_g6(self):
        gates = self._gates(
            self._summary(1900.0, ci=(-180.0, -20.0), seasons_won=0), self._summary(2000.0)
        )
        assert not gates["G6"].passed
        assert "LOSING side" in gates["G6"].detail

    def test_hoarding_a_single_slot_position_fails_g5(self):
        arm = self._summary(2200.0, counts={"QB": 3.5, "RB": 3.0, "WR": 5.0, "K": 2.0, "DST": 2.0})
        gates = self._gates(arm, self._summary(2000.0))
        assert not gates["G5"].passed
        assert "QB" in gates["G5"].detail

    def test_hoarding_a_depth_position_fails_g5(self):
        arm = self._summary(2200.0, counts={"QB": 2.0, "RB": 5.0, "WR": 5.0, "K": 2.0, "DST": 2.0})
        gates = self._gates(arm, self._summary(2000.0))
        assert not gates["G5"].passed
        assert "RB" in gates["G5"].detail

    def test_a_target_format_only_gain_fails_g3(self):
        arm, control = self._summary(2200.0), self._summary(2000.0)
        gates = {
            g.gate: g
            for g in evaluate_gates(
                arm,
                control,
                legacy_arm_summary=self._summary(1900.0),
                legacy_control_summary=self._summary(2000.0),
            )
        }
        assert not gates["G3"].passed

    def test_unfilled_mandatory_slots_cannot_get_worse(self):
        gates = self._gates(self._summary(2200.0, unfilled=0.4), self._summary(2000.0))
        assert not gates["G4"].passed

    def test_selection_ships_nothing_when_no_arm_clears(self):
        failing = [GateResult("G6", False, "CI contains zero")]
        assert selection({"T1": failing, "T2": failing, "T3": failing}) is None

    def test_selection_prefers_the_lowest_numbered_clearing_arm(self):
        passing = [GateResult("G1", True, "")]
        failing = [GateResult("G1", False, "")]
        assert selection({"T1": failing, "T2": passing, "T3": passing}) == "T2"
