"""Unit tests for the league decision engine: context loading, replacement/scarcity (the
value-based-drafting-with-flex algorithm), roster need, and draft/waiver/trade
recommendations, against synthetic data."""

from __future__ import annotations

import duckdb
import pytest
import yaml

from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.draft import next_pick_survival_probability, recommend_draft_pick
from alpha_squad.league.replacement import (
    compute_league_starters,
    marginal_value_over_replacement,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.roster import roster_fit_multiplier, roster_need
from alpha_squad.league.trade import age_curve_multiplier, recommend_dynasty_trade
from alpha_squad.league.waiver import recommend_waiver_pickup
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


class TestLeagueContext:
    def test_loads_the_target_league_config_exactly(self):
        league = load_league_context()
        assert league.league_id == "target_league"
        assert league.format == "dynasty"
        assert league.teams == 10
        assert league.lineup == {"QB": 2, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2}
        assert league.is_ppr
        assert league.bench_size == 10
        assert league.faab_budget == 100

    def test_dedicated_and_flex_slots_split_correctly(self):
        league = load_league_context()
        assert league.dedicated_slots() == {"QB": 2, "RB": 2, "WR": 2, "TE": 1}
        assert league.flex_slots() == {"FLEX": 2}

    def test_missing_config_raises_actionable_error(self, tmp_path):
        with pytest.raises(RuntimeError, match="league context"):
            load_league_context(tmp_path / "nope.yaml")

    def test_arbitrary_league_settings_round_trip(self, tmp_path):
        raw = {
            "league_id": "custom",
            "format": "redraft",
            "teams": 12,
            "scoring": {"ppr": False},
            "lineup": {"QB": 1, "RB": 2, "WR": 3, "SUPERFLEX": 1},
            "roster": {"bench": 6},
            "faab": {"budget": 200},
            "some_future_field": {"nested": True},
        }
        path = tmp_path / "custom.yaml"
        path.write_text(yaml.dump(raw))
        league = load_league_context(path)
        assert league.teams == 12
        assert not league.is_ppr
        assert league.dedicated_slots() == {"QB": 1, "RB": 2, "WR": 3}
        assert league.flex_slots() == {"SUPERFLEX": 1}


def _flat_league(teams, lineup, bench=6, faab=100) -> LeagueContext:
    return LeagueContext(
        league_id="test",
        format="redraft",
        teams=teams,
        scoring={"ppr": True},
        lineup=lineup,
        roster={"bench": bench},
        faab={"budget": faab},
    )


class TestComputeLeagueStarters:
    def test_dedicated_slots_filled_by_within_position_rank(self):
        league = _flat_league(2, {"QB": 1})
        projections = {"q1": 300, "q2": 250, "q3": 200}
        positions = {"q1": "QB", "q2": "QB", "q3": "QB"}
        result = compute_league_starters(league, projections, positions)
        assert result["dedicated_starters"]["QB"] == ["q1", "q2"]
        assert result["replacement_pool"]["QB"] == ["q3"]

    def test_flex_slots_are_earned_by_value_not_evenly_split(self):
        league = _flat_league(1, {"RB": 1, "WR": 1, "FLEX": 1})
        # After 1 dedicated RB and 1 dedicated WR are removed, two WRs remain that both
        # outvalue the best remaining RB -- the flex slot should go to a WR, not be forced
        # to alternate positions.
        projections = {"rb1": 100, "rb2": 40, "wr1": 90, "wr2": 80, "wr3": 70}
        positions = {"rb1": "RB", "rb2": "RB", "wr1": "WR", "wr2": "WR", "wr3": "WR"}
        result = compute_league_starters(league, projections, positions)
        assert result["dedicated_starters"]["RB"] == ["rb1"]
        assert result["dedicated_starters"]["WR"] == ["wr1"]
        assert result["flex_starters"] == ["wr2"]  # wr2 (80) beats rb2 (40) for the flex slot
        assert "rb2" in result["replacement_pool"]["RB"]

    def test_starters_set_is_the_union_of_dedicated_and_flex(self):
        league = _flat_league(1, {"RB": 1, "FLEX": 1})
        projections = {"rb1": 100, "rb2": 50, "wr1": 60}
        positions = {"rb1": "RB", "rb2": "RB", "wr1": "WR"}
        result = compute_league_starters(league, projections, positions)
        assert result["starters"] == {"rb1", "wr1"}


class TestReplacementLevel:
    def test_two_qb_league_has_materially_deeper_qb_replacement_than_one_qb_league(self):
        # 10 real-shaped QB projections, strictly decreasing.
        projections = {f"qb{i}": 300 - i * 8 for i in range(1, 11)}
        positions = {f"qb{i}": "QB" for i in range(1, 11)}
        one_qb = _flat_league(5, {"QB": 1})  # 5 starters
        two_qb = _flat_league(5, {"QB": 2})  # 10 starters -- the whole real pool

        one_qb_level = replacement_level(one_qb, projections, positions)["QB"]
        two_qb_level = replacement_level(two_qb, projections, positions)["QB"]
        # 1QB replacement = qb6's value; 2QB replacement = whatever's left after all 10
        # starters are taken (0.0, an empty pool) -- either way, materially different, and
        # the 2QB league values the position's depth far more (lower/zero replacement means
        # every real QB is above replacement, i.e. scarce).
        assert two_qb_level <= one_qb_level

    def test_replacement_pool_empty_returns_zero_not_an_error(self):
        league = _flat_league(1, {"QB": 5})
        projections = {"q1": 100}
        positions = {"q1": "QB"}
        levels = replacement_level(league, projections, positions)
        assert levels["QB"] == 0.0


class TestPositionalScarcityAndVorp:
    def test_scarcity_is_the_gap_between_mean_starter_value_and_replacement(self):
        league = _flat_league(1, {"QB": 1})
        projections = {"q1": 100, "q2": 40}
        positions = {"q1": "QB", "q2": "QB"}
        scarcity = positional_scarcity(league, projections, positions)
        assert scarcity["QB"] == pytest.approx(100 - 40)

    def test_marginal_value_over_replacement_matches_hand_computation(self):
        league = _flat_league(1, {"QB": 1})
        projections = {"q1": 100, "q2": 40}
        positions = {"q1": "QB", "q2": "QB"}
        vorp = marginal_value_over_replacement(league, projections, positions)
        assert vorp["q1"] == pytest.approx(60)
        assert vorp["q2"] == pytest.approx(0)


class TestRosterNeed:
    def test_understaffed_position_is_urgent_need(self):
        league = _flat_league(1, {"QB": 2})
        needs = roster_need(league, ["QB"])
        assert needs["QB"] == pytest.approx(1.0)

    def test_saturated_position_is_negative_need(self):
        league = _flat_league(1, {"QB": 1})
        needs = roster_need(league, ["QB", "QB", "QB", "QB", "QB"])
        assert needs["QB"] < 0

    def test_fit_multiplier_is_bounded(self):
        assert roster_fit_multiplier(100) == pytest.approx(1.3)
        assert roster_fit_multiplier(-100) == pytest.approx(0.7)
        assert roster_fit_multiplier(0) == pytest.approx(1.0)


class TestNextPickSurvivalProbability:
    @pytest.fixture
    def con(self):
        connection = duckdb.connect(":memory:")
        init_db(connection)
        yield connection
        connection.close()

    def _seed(self, con, player_id, best, worst):
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst) "
            "VALUES (?, '2025-08-01', 'rsf', 'WR', ?, ?, ?)",
            [player_id, (best + worst) / 2, best, worst],
        )

    def test_certainly_gone_before_the_best_case_rank(self, con):
        self._seed(con, "p1", best=5, worst=15)
        assert next_pick_survival_probability(con, "p1", next_pick_overall=20) == pytest.approx(0.0)

    def test_certainly_available_after_the_worst_case_rank(self, con):
        self._seed(con, "p1", best=5, worst=15)
        assert next_pick_survival_probability(con, "p1", next_pick_overall=1) == pytest.approx(1.0)

    def test_interpolates_within_the_expert_dispersion(self, con):
        self._seed(con, "p1", best=10, worst=20)
        prob = next_pick_survival_probability(con, "p1", next_pick_overall=15)
        assert 0.0 < prob < 1.0
        assert prob == pytest.approx(0.5)

    def test_no_market_data_returns_none(self, con):
        assert next_pick_survival_probability(con, "nobody", next_pick_overall=10) is None


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_uncertainty(con, player_id, season, position, point_pred, confidence=0.8, top24_prob=0.3):
    con.execute(
        """
        INSERT INTO uncertainty_predictions
            (prediction_id, player_id, season, position, model_version, feature_version,
             point_prediction, top24_prob, confidence, calibration_season, predicted_at)
        VALUES (?, ?, ?, ?, ?, 'test_v1', ?, ?, ?, ?, current_timestamp)
        """,
        [
            f"pred_{player_id}",
            player_id,
            season,
            position,
            UNCERTAINTY_MODEL_VERSION,
            point_pred,
            top24_prob,
            confidence,
            season - 1,
        ],
    )


class TestRecommendDraftPick:
    def test_recommends_the_highest_scoring_available_player(self, con):
        league = load_league_context()
        for i, pts in enumerate([300, 250, 200, 150]):
            _seed_uncertainty(con, f"qb{i}", 2025, "QB", pts)
        rec = recommend_draft_pick(con, league, 2025, [], {"qb0", "qb1", "qb2", "qb3"})
        assert rec.recommendation == "qb0"
        assert rec.alternatives == ["qb1", "qb2", "qb3"]
        assert rec.reasons

    def test_raises_when_no_candidates_are_evaluable(self, con):
        league = load_league_context()
        with pytest.raises(RuntimeError):
            recommend_draft_pick(con, league, 2025, [], {"nobody"})


class TestRecommendWaiverPickup:
    def test_raises_for_a_player_with_no_projection(self, con):
        league = load_league_context()
        with pytest.raises(RuntimeError):
            recommend_waiver_pickup(con, league, 2025, 5, "nobody", [])

    def test_bid_is_bounded_by_the_faab_budget_fraction(self, con):
        league = load_league_context()
        for i, pts in enumerate([300, 250, 200, 150, 100]):
            _seed_uncertainty(con, f"wr{i}", 2025, "WR", pts)
        rec = recommend_waiver_pickup(con, league, 2025, 5, "wr0", [])
        assert 0 <= rec.recommended_bid <= league.faab_budget * 0.40 + 1e-6

    def test_recent_evidence_spike_can_produce_a_bid_despite_negative_marginal_value(self, con):
        # A small league (1 team, 1 dedicated WR slot, no flex) so a handful of synthetic
        # players is enough to create a genuine replacement pool below "sleeper".
        league = _flat_league(1, {"WR": 1}, faab=100)
        for i, pts in enumerate([300, 280, 260, 240, 220]):
            _seed_uncertainty(con, f"wr{i}", 2025, "WR", pts)
        _seed_uncertainty(con, "sleeper", 2025, "WR", 50.0)  # well below replacement
        con.execute(
            """
            INSERT INTO evidence_events
                (event_id, player_id, season, week, event_date, captured_at, event_type,
                 source, strength_label, strength, direction, structured_impact_json, summary)
            VALUES ('ev1', 'sleeper', 2025, 5, '2025-10-01', current_timestamp,
                    'usage_share_spike', 'test', 'STRONG', 0.9, 1, '{}', 'big spike')
            """
        )
        rec = recommend_waiver_pickup(con, league, 2025, 5, "sleeper", [])
        assert rec.marginal_value < 0
        assert rec.value_spike_probability > 0.5
        assert rec.recommended_bid > 0


class TestAgeCurveMultiplier:
    def test_at_or_before_peak_is_full_value(self):
        assert age_curve_multiplier("RB", 23) == pytest.approx(1.0)

    def test_at_the_cliff_is_half_value(self):
        assert age_curve_multiplier("RB", 30) == pytest.approx(0.5)

    def test_past_the_cliff_is_floored(self):
        assert age_curve_multiplier("RB", 40) == pytest.approx(0.3)

    def test_missing_age_or_position_is_neutral(self):
        assert age_curve_multiplier("RB", None) == pytest.approx(1.0)
        assert age_curve_multiplier(None, 30) == pytest.approx(1.0)
        assert age_curve_multiplier("K", 30) == pytest.approx(1.0)


class TestRecommendDynastyTrade:
    def test_uses_the_real_stored_edge_action_and_reasons(self, con):
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('p1', '2026-08-01', 26.0, 8000, current_timestamp)"
        )
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, projected_points_edge, evidence_score, confidence,
                 action, reasons_json, built_at)
            VALUES ('e1', 'p1', 2025, 'WR', 'rsf', 'edge_v1', 5, 40, 35, 50.0, 0.5, 0.8,
                    'BUY', '["real edge reason"]', current_timestamp)
            """
        )
        rec = recommend_dynasty_trade(con, "p1", 2025)
        assert rec.action == "BUY"
        assert "real edge reason" in rec.reasons
        assert rec.age_adjusted_value == pytest.approx(8000 * age_curve_multiplier("WR", 26.0))

    def test_no_edge_on_record_defaults_to_watch(self, con):
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES ('p1', '2026-08-01', 26.0, 8000, current_timestamp)"
        )
        rec = recommend_dynasty_trade(con, "p1", 2025)
        assert rec.action == "WATCH"
