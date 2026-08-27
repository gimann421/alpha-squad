"""Unit + regression tests for the positional opportunity-cost mechanism (docs/DECISIONS.md
D55, docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import (
    best_by_market_rank,
    picks_until_next_turn,
    positional_opportunity_cost,
    replay_opponent_picks,
)
from alpha_squad.league.roster import OVER_CAP_VALUE_MULTIPLIER, positional_feasibility_cap
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league(**overrides) -> LeagueContext:
    base = dict(
        league_id="t",
        format="redraft",
        teams=2,
        scoring={"ppr": True},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1},
        roster={"bench": 4, "roster_size": 8},
    )
    base.update(overrides)
    return LeagueContext(**base)


class TestPicksUntilNextTurn:
    def test_counts_only_intervening_picks(self):
        assert picks_until_next_turn(1, 20) == 18

    def test_snake_turn_is_zero(self):
        """Draft slot 1 picks at overall #20 and #21 back to back -- nothing happens in
        between, so nothing can be lost by waiting. Zero is the correct answer here, not a
        degenerate one."""
        assert picks_until_next_turn(20, 21) == 0

    def test_missing_endpoint_disables_the_term_rather_than_guessing(self):
        assert picks_until_next_turn(None, 20) == 0
        assert picks_until_next_turn(1, None) == 0

    def test_never_negative(self):
        assert picks_until_next_turn(30, 10) == 0


class TestReplayOpponentPicks:
    def test_removes_exactly_n_best_ranked_players(self):
        market = {"a": ("RB", 1.0), "b": ("RB", 2.0), "c": ("WR", 3.0), "d": ("WR", 4.0)}
        assert replay_opponent_picks(set(market), market, 2) == {"c", "d"}

    def test_zero_picks_changes_nothing(self):
        market = {"a": ("RB", 1.0), "b": ("RB", 2.0)}
        assert replay_opponent_picks(set(market), market, 0) == {"a", "b"}

    def test_does_not_mutate_the_caller_pool(self):
        market = {"a": ("RB", 1.0), "b": ("RB", 2.0)}
        available = set(market)
        replay_opponent_picks(available, market, 1)
        assert available == {"a", "b"}

    def test_more_picks_than_players_does_not_raise(self):
        market = {"a": ("RB", 1.0)}
        assert replay_opponent_picks(set(market), market, 99) == set()

    def test_deterministic_under_tied_market_ranks(self):
        """Regression (D54/D55): `available` is a set, and real ECR ranks tie. Without the
        player_id tie-break the replay could differ between processes."""
        market = {"zeta": ("RB", 5.0), "alpha_p": ("RB", 5.0), "mid": ("RB", 5.0)}
        assert {best_by_market_rank(set(market), market) for _ in range(25)} == {"alpha_p"}


class TestPositionalOpportunityCost:
    def _fixture(self):
        positions = {"rb1": "RB", "rb2": "RB", "wr1": "WR", "wr2": "WR"}
        vorp = {"rb1": 100.0, "rb2": 10.0, "wr1": 90.0, "wr2": 85.0}
        market = {"rb1": ("RB", 1.0), "wr1": ("WR", 2.0), "rb2": ("RB", 3.0), "wr2": ("WR", 4.0)}
        return positions, vorp, market

    def test_prices_the_real_drop_off_at_each_position(self):
        """RB falls off a cliff (100 -> 10) while WR barely moves (90 -> 85). The whole point
        of the mechanism is that this is visible in points."""
        positions, vorp, market = self._fixture()
        costs = positional_opportunity_cost(
            set(positions), positions, vorp, market, 2, ["RB", "WR"]
        )
        assert costs["RB"] == pytest.approx(90.0)
        assert costs["WR"] == pytest.approx(5.0)

    def test_zero_when_no_opponent_picks_intervene(self):
        positions, vorp, market = self._fixture()
        costs = positional_opportunity_cost(
            set(positions), positions, vorp, market, 0, ["RB", "WR"]
        )
        assert costs == {"RB": 0.0, "WR": 0.0}

    def test_never_negative(self):
        positions, vorp, market = self._fixture()
        costs = positional_opportunity_cost(
            set(positions), positions, vorp, market, 3, ["RB", "WR"]
        )
        assert all(v >= 0.0 for v in costs.values())

    def test_clamped_at_replacement_level(self):
        """Both sides clamp at 0 so two below-replacement players cannot manufacture a cost.
        Real case from 2021: the best available RB late was VORP -135.4; 'losing' a player
        already worse than the waiver wire costs nothing."""
        positions = {"rb1": "RB", "rb2": "RB"}
        vorp = {"rb1": -100.0, "rb2": -200.0}
        market = {"rb1": ("RB", 1.0), "rb2": ("RB", 2.0)}
        costs = positional_opportunity_cost(set(positions), positions, vorp, market, 1, ["RB"])
        assert costs["RB"] == pytest.approx(0.0)

    def test_unknown_position_yields_zero_not_keyerror(self):
        positions, vorp, market = self._fixture()
        costs = positional_opportunity_cost(set(positions), positions, vorp, market, 1, ["TE"])
        assert costs["TE"] == pytest.approx(0.0)

    def test_deterministic_under_tied_vorp(self):
        """Maxing over VORP *values* means tied players cannot change the figure, regardless
        of set iteration order."""
        positions = {f"rb{i}": "RB" for i in range(6)}
        vorp = dict.fromkeys(positions, 50.0)
        market = {p: ("RB", float(i)) for i, p in enumerate(positions)}
        seen = {
            positional_opportunity_cost(set(positions), positions, vorp, market, 3, ["RB"])["RB"]
            for _ in range(25)
        }
        assert len(seen) == 1


class TestPositionalFeasibilityCap:
    def test_scales_with_the_leagues_configured_bench(self):
        assert positional_feasibility_cap(_league(roster={"bench": 20}), "QB") > (
            positional_feasibility_cap(_league(roster={"bench": 0}), "QB")
        )

    def test_respects_league_specific_starting_slots(self):
        two_qb = _league(lineup={"QB": 2, "RB": 1, "WR": 1, "TE": 1})
        one_qb = _league(lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1})
        assert positional_feasibility_cap(two_qb, "QB") > positional_feasibility_cap(one_qb, "QB")

    def test_at_least_the_starting_requirement(self):
        assert positional_feasibility_cap(_league(roster={"bench": 0}), "QB") >= 1


def _seed(con, player_id, season, position, points, confidence=0.8, ecr_rank=1.0):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top12_prob, top24_prob, confidence, calibration_season, predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, ?, ?, current_timestamp)
        """,
        [
            f"p_{player_id}",
            player_id,
            season,
            position,
            UNCERTAINTY_MODEL_VERSION,
            points,
            confidence,
            season - 1,
        ],
    )
    con.execute(
        "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
        "VALUES (?, ?, 'rsf', ?, ?)",
        [player_id, f"{season}-08-01", position, ecr_rank],
    )


class TestRecommendDraftPickIntegration:
    def test_backward_compatible_without_current_pick(self, con):
        """Callers that cannot say where the draft is must get exactly the pre-D55 behavior --
        the opportunity-cost term is omitted, not guessed."""
        for i, pts in enumerate([300.0, 250.0, 200.0]):
            _seed(con, f"qb{i}", 2025, "QB", pts, ecr_rank=float(i + 1))
        league = _league()
        available = {"qb0", "qb1", "qb2"}
        rec = recommend_draft_pick(con, league, 2025, [], available, next_pick_overall=20)
        assert rec.recommendation == "qb0"
        assert not any("opportunity cost" in r for r in rec.reasons)

    def test_snake_turn_adds_no_opportunity_cost(self, con):
        for i, pts in enumerate([300.0, 250.0]):
            _seed(con, f"qb{i}", 2025, "QB", pts, ecr_rank=float(i + 1))
        league = _league()
        rec = recommend_draft_pick(
            con,
            league,
            2025,
            [],
            {"qb0", "qb1"},
            next_pick_overall=21,
            current_pick_overall=20,
        )
        assert not any("opportunity cost" in r for r in rec.reasons)

    def test_opportunity_cost_flips_the_pick_to_the_scarcer_position(self, con):
        """THE headline regression test (D55, and the mechanism this whole change exists for).

        Deterministic synthetic scenario, no real data. The distinction being tested is subtle
        and is exactly what the M17 forensic audit found production was blind to:

        - VORP already prices a position's *end-of-draft* floor (its replacement level). Both
          positions here are equally deep in that sense.
        - Opportunity cost prices what is available at *this team's next specific turn*, which
          is a different question -- and the only one that answers "will a player this good at
          this position still be there when I pick again?"

        Setup: `wr_best` is the superficially better player (VORP 100 vs `rb_best`'s 85), so the
        pre-D55 score takes him. But the market has `rb_best` going first overall while
        `wr_best` lasts; replaying even one opponent pick removes `rb_best` and leaves the WR
        board untouched. So waiting on RB costs 85 points and waiting on WR costs nothing.

        Taking `rb_best` is the correct decision, and the opportunity-cost term is what makes
        the engine able to see it.
        """
        season = 2025
        # ecr_rank drives the opponent replay: opponents take the best-ranked player first.
        # rb_best is the consensus 1.01 and will be gone; wr_best lasts.
        _seed(con, "rb_best", season, "RB", 280.0, ecr_rank=1.0)
        _seed(con, "rb_b", season, "RB", 195.0, ecr_rank=2.0)
        _seed(con, "rb_c", season, "RB", 194.0, ecr_rank=3.0)
        _seed(con, "wr_best", season, "WR", 300.0, ecr_rank=10.0)
        _seed(con, "wr_b", season, "WR", 200.0, ecr_rank=11.0)
        _seed(con, "wr_c", season, "WR", 199.0, ecr_rank=12.0)

        # teams=1 keeps replacement level trivially inspectable: it is simply each position's
        # second-best player, so wr_best VORP = 300-200 = 100 and rb_best VORP = 280-195 = 85.
        league = _league(teams=1, lineup={"RB": 1, "WR": 1}, roster={"bench": 2, "roster_size": 4})
        available = {"rb_best", "rb_b", "rb_c", "wr_best", "wr_b", "wr_c"}

        without = recommend_draft_pick(con, league, season, [], set(available), next_pick_overall=3)
        # current=1, next=3 -> exactly one opponent pick intervenes, taking rb_best.
        with_cost = recommend_draft_pick(
            con,
            league,
            season,
            [],
            set(available),
            next_pick_overall=3,
            current_pick_overall=1,
        )

        assert without.recommendation == "wr_best", (
            "precondition: on raw value the WR is the better player and the naive pick"
        )
        assert with_cost.recommendation == "rb_best", (
            "opportunity cost should make the scarcer RB the correct pick"
        )
        assert any("opportunity cost" in r for r in with_cost.reasons)

        # And the term is *why* -- not some incidental reordering.
        rb = next(c for c in with_cost.candidates if c.player_id == "rb_best")
        wr = next(c for c in with_cost.candidates if c.player_id == "wr_best")
        assert rb.score > wr.score
        assert rb.vorp < wr.vorp, "the RB wins despite being the lower-VORP player"

    def test_over_cap_position_is_heavily_discounted(self, con):
        for i, pts in enumerate([300.0, 290.0, 280.0, 270.0, 260.0, 250.0]):
            _seed(con, f"qb{i}", 2025, "QB", pts, ecr_rank=float(i + 1))
        _seed(con, "rb0", 2025, "RB", 100.0, ecr_rank=9.0)
        league = _league()
        cap = positional_feasibility_cap(league, "QB")
        rec = recommend_draft_pick(
            con, league, 2025, ["QB"] * cap, {"qb5", "rb0"}, next_pick_overall=20
        )
        assert rec.recommendation == "rb0", "a capped position must not beat a real need"
        qb = next(c for c in rec.candidates if c.player_id == "qb5")
        assert any("usable cap" in r for r in qb.reasons)

    def test_deterministic_across_repeated_calls(self, con):
        for i, pts in enumerate([300.0, 300.0, 300.0]):
            _seed(con, f"qb{i}", 2025, "QB", pts, ecr_rank=1.0)
        league = _league()
        picks = {
            recommend_draft_pick(
                con,
                league,
                2025,
                [],
                {"qb0", "qb1", "qb2"},
                next_pick_overall=20,
                current_pick_overall=1,
            ).recommendation
            for _ in range(15)
        }
        assert len(picks) == 1

    def test_over_cap_multiplier_is_the_documented_constant(self):
        assert OVER_CAP_VALUE_MULTIPLIER == 0.1
