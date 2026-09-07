"""Controlled decision tests for the production draft engine (D79).

These are behavioural regression tests, not accuracy tests. Each one constructs a synthetic
board that isolates ONE decision factor -- positional drop-off shape, board depletion, roster
state, pick timing -- and asserts what `recommend_draft_pick` must do in response. They exist
because the aggregate starter-points benchmark cannot answer "does the engine react to
scarcity at all": a 16-round drafted roster mixes every mechanism together, and D71 established
that the benchmark's minimum detectable effect (~128 starter points at 5 seasons) is larger
than any single mechanism's contribution. A controlled test can still say, unambiguously,
whether the mechanism is wired up and pointing the right way.

The boards are synthetic BY DESIGN. Real projections cannot isolate a factor -- an elite RB is
also, in the real data, a high-projection player with particular market dispersion and a
particular confidence. Every projection curve here is stated explicitly in the test that uses
it, so a failure names the property that broke rather than "the numbers moved".

Confidence is held constant across every seeded player and ECR is assigned in projection order,
so `risk_mult` and the market terms cannot silently drive a result that reads as scarcity.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

SEASON = 2024
#: Held constant for every seeded player so the score's `risk_mult` factor is a constant and
#: cannot be mistaken for a positional effect.
FIXED_CONFIDENCE = 0.8


def _league() -> LeagueContext:
    """A small 1-QB redraft league with the target format's SHAPE (QB1/RB2/WR2/TE1/FLEX1),
    scaled down so a full mock draft inside `market_draft_demand` stays fast. No K/DEF slots:
    these tests isolate the RB/WR/QB value question, and mandatory-slot legality is a separate
    mechanism with its own tests."""
    return LeagueContext(
        league_id="controlled_1qb",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
        roster={"bench": 2, "roster_size": 8},
    )


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def seed_board(con, curves: dict[str, list[float]], *, season: int = SEASON) -> list[str]:
    """Seed `uncertainty_predictions` + `market_snapshot` from explicit per-position projection
    curves. Returns every player id, in descending projection order.

    ECR rank is assigned in descending projection order across the whole board, i.e. the market
    agrees exactly with the projections. That is deliberate: it makes the market terms
    (opportunity cost, survival) a function of the projection curve alone, so a test that varies
    only the curve is varying only one thing.
    """
    rows = [
        (f"{pos}_{i}", pos, points)
        for pos, curve in curves.items()
        for i, points in enumerate(curve)
    ]
    rows.sort(key=lambda r: -r[2])
    for rank, (player_id, position, points) in enumerate(rows, start=1):
        con.execute(
            """
            INSERT INTO uncertainty_predictions
                (prediction_id, player_id, season, position, model_version, feature_version,
                 point_prediction, top12_prob, top24_prob, confidence, calibration_season,
                 predicted_at)
            VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, ?, ?, current_timestamp)
            """,
            [
                f"pred_{player_id}",
                player_id,
                season,
                position,
                UNCERTAINTY_MODEL_VERSION,
                points,
                FIXED_CONFIDENCE,
                season - 1,
            ],
        )
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
            "ecr_rank, ecr_best, ecr_worst, page_type) "
            "VALUES (?, ?, 'ro', ?, ?, ?, ?, 'redraft-overall')",
            [player_id, f"{season}-08-01", position, float(rank), rank, rank + 4],
        )
    return [r[0] for r in rows]


def _flat(start: float, n: int, step: float) -> list[float]:
    return [start - i * step for i in range(n)]


#: A board with genuinely symmetric RB and WR curves. Any RB/WR asymmetry a test sees on top of
#: this one comes from the change that test makes, not from the baseline.
def _symmetric_curves() -> dict[str, list[float]]:
    return {
        "QB": _flat(300.0, 12, 6.0),
        "RB": _flat(240.0, 24, 5.0),
        "WR": _flat(240.0, 24, 5.0),
        "TE": _flat(180.0, 12, 5.0),
    }


def recommend(con, league, available, **kwargs):
    kwargs.setdefault("roster_positions", [])
    kwargs.setdefault("roster_player_ids", [])
    kwargs.setdefault("current_pick_overall", 1)
    kwargs.setdefault("next_pick_overall", 8)
    # The whole pool by default: these tests compare NAMED candidates, and a truncated
    # top-N turns "scored lower" into "missing", which is a much less informative failure.
    kwargs.setdefault("top_n", max(1, len(available)))
    return recommend_draft_pick(
        con,
        league,
        SEASON,
        kwargs.pop("roster_positions"),
        set(available),
        kwargs.pop("next_pick_overall"),
        None,
        kwargs.pop("top_n"),
        current_pick_overall=kwargs.pop("current_pick_overall"),
        roster_player_ids=kwargs.pop("roster_player_ids"),
        **kwargs,
    )


def score_of(rec, player_id: str) -> float:
    for c in rec.candidates:
        if c.player_id == player_id:
            return c.score
    raise AssertionError(f"{player_id} not in the returned candidates")


class TestOneProjectionParity:
    """TEST 1 -- two players with the same projection at different positions must NOT be
    treated as interchangeable. If they were, the engine would be raw-points-driven and every
    scarcity mechanism below would be decoration."""

    def test_equal_projection_different_position_is_scored_differently(self, con):
        curves = _symmetric_curves()
        # RB1 and QB1 are given the SAME projection; everything else about their positions
        # (drop-off, how many the lineup starts) differs, so their draft value must differ.
        curves["RB"][0] = 260.0
        curves["QB"][0] = 260.0
        ids = seed_board(con, curves)
        rec = recommend(con, _league(), ids)
        rb, qb = score_of(rec, "RB_0"), score_of(rec, "QB_0")
        assert rb != pytest.approx(qb, rel=0.02), (
            "equal projections at different positions produced equal draft value -- the engine "
            "is ranking by raw points"
        )
        # And in a 1-QB league the flex-eligible RB, not the QB, is the more valuable of the two.
        assert rb > qb

    def test_symmetric_positions_with_equal_projections_are_scored_equally(self, con):
        """The converse guard: when RB and WR really are symmetric, the engine must NOT invent
        a difference. This is what stops a hardcoded positional bonus from passing the test
        above."""
        ids = seed_board(con, _symmetric_curves())
        rec = recommend(con, _league(), ids)
        assert score_of(rec, "RB_0") == pytest.approx(score_of(rec, "WR_0"), rel=0.02)


class TestTwoThreePositionalScarcity:
    """TEST 2 / TEST 3 -- the drop-off shape, and nothing else, decides which position is
    worth more. Both directions are asserted, so passing requires responding to the DATA
    rather than carrying a fixed preference for either position."""

    @staticmethod
    def _cliff_at(position: str, other: str) -> dict[str, list[float]]:
        """`position` has one elite player then a cliff; `other` is flat and deep. The elite
        player at `position` is given a LOWER projection than the top of `other`, so raw points
        and scarcity disagree and the test can tell which one the engine followed.

        RB and WR ONLY. On a board that also carries quarterbacks the QB tier occupies the top
        outright (raw QB projections exceed every skill player, and the value base carries the
        raw projection at double weight -- see docs/DRAFT_DECISION_ENGINE_INVESTIGATION.md §3),
        so the RB-vs-WR comparison this test exists to make would never reach the top slot. A
        two-position board is the isolation the test needs, not a workaround.
        """
        return {
            position: [235.0] + _flat(150.0, 23, 2.0),
            other: _flat(245.0, 24, 1.5),
        }

    def test_prefers_the_scarce_rb_over_a_higher_projected_wr(self, con):
        ids = seed_board(con, self._cliff_at("RB", "WR"))
        rec = recommend(con, _league(), ids, current_pick_overall=None, next_pick_overall=None)
        assert rec.candidates[0].position == "RB"
        assert rec.recommendation == "RB_0"

    def test_prefers_the_scarce_wr_over_a_higher_projected_rb(self, con):
        ids = seed_board(con, self._cliff_at("WR", "RB"))
        rec = recommend(con, _league(), ids, current_pick_overall=None, next_pick_overall=None)
        assert rec.candidates[0].position == "WR"
        assert rec.recommendation == "WR_0"

    def test_the_scarcity_preference_is_in_the_value_base_not_the_raw_projection(self, con):
        """The scarce player wins DESPITE a lower projection, which is only possible if the
        surplus-over-replacement term is doing the work."""
        ids = seed_board(con, self._cliff_at("RB", "WR"))
        rec = recommend(con, _league(), ids, current_pick_overall=None, next_pick_overall=None)
        rb = next(c for c in rec.candidates if c.player_id == "RB_0")
        wr = next(c for c in rec.candidates if c.player_id == "WR_0")
        assert rb.marginal_starter_value < wr.marginal_starter_value  # lower raw projection
        assert rb.score > wr.score  # ... and still the better pick

    def test_a_scarce_player_who_will_survive_is_correctly_deferred(self, con):
        """The timing interaction, asserted as INTENDED behaviour rather than left implicit.

        On this board the scarce running back is ranked low enough by the market to survive to
        the user's next pick with certainty, while the flat position's best receiver will not.
        Taking the receiver now and the running back later is the correct play, and the engine
        makes it -- so the scarcity preference above is genuinely conditional on timing rather
        than a fixed positional lean.

        Recorded here because it is also the clearest illustration of a term worth watching:
        `survival_mult` is a MULTIPLICATIVE bonus of up to 1.3x on the whole score, so it can
        and here does overturn an 81-point surplus gap. Its 0.3 coefficient is the one free
        parameter in the production score that no phase has ever measured -- see
        docs/DRAFT_DECISION_ENGINE_INVESTIGATION.md.
        """
        ids = seed_board(con, self._cliff_at("RB", "WR"))
        rec = recommend(con, _league(), ids, current_pick_overall=1, next_pick_overall=8)
        rb = next(c for c in rec.candidates if c.player_id == "RB_0")
        wr = next(c for c in rec.candidates if c.player_id == "WR_0")
        assert rb.survival_probability == 1.0  # still there next turn
        assert wr.survival_probability == 0.0  # gone next turn
        assert rec.recommendation == "WR_0"


class TestFourRemoveTheRecommendedPlayer:
    """TEST 4 -- removing the recommendation must produce a different, and specifically the
    next-best, recommendation. A stale or recomputed-from-scratch answer that ignored the board
    would show up here."""

    def test_recommendation_moves_to_the_runner_up(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        first = recommend(con, league, ids)
        remaining = [p for p in ids if p != first.recommendation]
        second = recommend(con, league, remaining)
        assert second.recommendation != first.recommendation
        assert second.recommendation == first.alternatives[0]


class TestFiveRemoveTheTopOfOnePosition:
    """TEST 5 -- when a position's elite tier is stripped, the engine must move off that
    position; when the OTHER position is stripped instead, it must move the other way. Both
    directions again, for the same reason as TEST 2/3."""

    @staticmethod
    def _tiered() -> dict[str, list[float]]:
        """Both RB and WR have a 3-player elite tier then a cliff, and the two tiers are equal.
        Removing one position's tier is then the only asymmetry in the board. RB and WR only,
        for the reason given in `TestTwoThreePositionalScarcity._cliff_at`."""
        tier = [250.0, 248.0, 246.0] + _flat(160.0, 21, 2.0)
        return {"RB": list(tier), "WR": list(tier)}

    def test_stripping_the_rb_tier_moves_the_recommendation_to_wr(self, con):
        ids = seed_board(con, self._tiered())
        league = _league()
        remaining = [p for p in ids if p not in {"RB_0", "RB_1", "RB_2"}]
        rec = recommend(con, league, remaining)
        assert rec.candidates[0].position == "WR"

    def test_stripping_the_wr_tier_moves_the_recommendation_to_rb(self, con):
        ids = seed_board(con, self._tiered())
        league = _league()
        remaining = [p for p in ids if p not in {"WR_0", "WR_1", "WR_2"}]
        rec = recommend(con, league, remaining)
        assert rec.candidates[0].position == "RB"


class TestSixRosterState:
    """TEST 6 -- identical board, different roster. The engine must devalue a position this
    roster has already filled, relative to one it has not."""

    def test_holding_receivers_shifts_value_toward_running_backs(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        # Two receivers already rostered vs two running backs already rostered, on the same
        # board. The remaining pool is identical in both arms.
        pool = [p for p in ids if p not in {"WR_0", "WR_1", "RB_0", "RB_1"}]
        with_wrs = recommend(
            con,
            league,
            pool,
            roster_positions=["WR", "WR"],
            roster_player_ids=["WR_0", "WR_1"],
        )
        with_rbs = recommend(
            con,
            league,
            pool,
            roster_positions=["RB", "RB"],
            roster_player_ids=["RB_0", "RB_1"],
        )
        # Compare the SAME two candidates under the two roster states.
        rb_gain = score_of(with_wrs, "RB_2") - score_of(with_rbs, "RB_2")
        wr_gain = score_of(with_rbs, "WR_2") - score_of(with_wrs, "WR_2")
        assert rb_gain > 0, "an unfilled RB slot did not raise an RB's value"
        assert wr_gain > 0, "an unfilled WR slot did not raise a WR's value"

    def test_an_empty_roster_values_a_position_at_least_as_highly_as_a_saturated_one(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        pool = [p for p in ids if p not in {"RB_0", "RB_1", "RB_2", "RB_3"}]
        empty = recommend(con, league, pool)
        saturated = recommend(
            con,
            league,
            pool,
            roster_positions=["RB"] * 4,
            roster_player_ids=["RB_0", "RB_1", "RB_2", "RB_3"],
        )
        assert score_of(empty, "RB_4") > score_of(saturated, "RB_4")


class TestSevenPickTiming:
    """TEST 7 -- identical board and roster, different distance to the next pick. Waiting
    longer must not make a position look SAFER."""

    def test_a_longer_wait_never_lowers_the_opportunity_cost(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        soon = recommend(con, league, ids, current_pick_overall=1, next_pick_overall=3)
        later = recommend(con, league, ids, current_pick_overall=1, next_pick_overall=16)
        assert score_of(later, "RB_0") >= score_of(soon, "RB_0")

    def test_back_to_back_picks_carry_no_positional_opportunity_cost(self, con):
        """At the snake turn nothing happens between the two picks, so nothing can be lost by
        waiting. This must be exactly zero, not merely small -- it is the boundary condition
        `picks_until_next_turn` exists to get right."""
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        rec = recommend(con, league, ids, current_pick_overall=8, next_pick_overall=9)
        for c in rec.candidates:
            assert not any("opportunity cost" in r for r in c.reasons)

    def test_an_unknown_next_pick_disables_the_term_rather_than_guessing(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        rec = recommend(con, league, ids, current_pick_overall=None, next_pick_overall=None)
        for c in rec.candidates:
            assert not any("opportunity cost" in r for r in c.reasons)
            assert c.survival_probability is None


class TestEightSnakeSequence:
    """TEST 8 -- a real snake sequence, driven the way `evaluation/draft_simulation.py` drives
    it. The engine must know where it is, never repeat a player, and fill a legal lineup."""

    @staticmethod
    def _snake_pick(round_no: int, slot: int, teams: int) -> int:
        if round_no % 2 == 1:
            return (round_no - 1) * teams + slot
        return (round_no - 1) * teams + (teams - slot + 1)

    def test_a_full_snake_draft_from_every_slot_is_legal_and_distinct(self, con):
        ids = seed_board(con, _symmetric_curves())
        league = _league()
        rounds = int(league.roster["roster_size"])
        for slot in range(1, league.teams + 1):
            available = set(ids)
            my_ids: list[str] = []
            my_positions: list[str] = []
            positions = {p: p.split("_")[0] for p in ids}
            for round_no in range(1, rounds + 1):
                current = self._snake_pick(round_no, slot, league.teams)
                nxt = (
                    self._snake_pick(round_no + 1, slot, league.teams)
                    if round_no < rounds
                    else None
                )
                rec = recommend(
                    con,
                    league,
                    available,
                    roster_positions=list(my_positions),
                    roster_player_ids=list(my_ids),
                    current_pick_overall=current,
                    next_pick_overall=nxt,
                    top_n=1,
                )
                pick = rec.recommendation
                assert pick in available
                my_ids.append(pick)
                my_positions.append(positions[pick])
                available.discard(pick)
                # The other teams pick too, so the board really is depleting between turns.
                for _ in range(league.teams - 1):
                    if available:
                        available.discard(max(available, key=lambda p: p))
            assert len(set(my_ids)) == rounds
            # Every dedicated starting slot this league requires is filled.
            for position, needed in league.dedicated_slots().items():
                assert my_positions.count(position) >= needed, (
                    f"slot {slot} finished without {needed} {position}"
                )

    def test_the_trace_reports_the_pick_numbers_it_was_given(self, con):
        ids = seed_board(con, _symmetric_curves())
        rec = recommend(con, _league(), ids, current_pick_overall=4, next_pick_overall=13)
        assert rec.trace.current_pick_overall == 4
        assert rec.trace.next_pick_overall == 13
        assert rec.trace.available_pool_size == len(ids)
