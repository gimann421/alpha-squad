"""Unit tests for the diagnostic-only draft-engine forensic experiment harness
(docs/DRAFT_ENGINE_FORENSIC_AUDIT.md, docs/DRAFT_CONTROLLED_EXPERIMENTS.md)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import (
    ALL_TIERS,
    _feasibility_cap,
    homogeneous_league_draft,
    load_season_static,
    roster_feasibility_metrics,
    score_candidate,
    simulate_forensic_draft,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_league_season(con, season, n_per_position=6, with_dispersion=True):
    positions = ("QB", "RB", "WR", "TE")
    rank = 1
    for position in positions:
        for i in range(n_per_position):
            player_id = f"{position}_{i}"
            points = 300.0 - i * 20
            con.execute(
                """
                INSERT INTO uncertainty_predictions
                    (prediction_id, player_id, season, position, model_version, feature_version,
                     point_prediction, top12_prob, top24_prob, confidence, calibration_season, predicted_at)
                VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, 0.8, ?, current_timestamp)
                """,
                [
                    f"pred_{player_id}",
                    player_id,
                    season,
                    position,
                    UNCERTAINTY_MODEL_VERSION,
                    points,
                    season - 1,
                ],
            )
            con.execute(
                "INSERT INTO player_season_stats (player_id, season, position, games_played, "
                "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 15, ?, ?)",
                [player_id, season, position, points, points / 15],
            )
            if with_dispersion:
                con.execute(
                    "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                    "ecr_rank, ecr_best, ecr_worst) VALUES (?, ?, 'rsf', ?, ?, ?, ?)",
                    [player_id, f"{season}-08-01", position, float(rank), rank, rank + 3],
                )
            else:
                con.execute(
                    "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                    "ecr_rank) VALUES (?, ?, 'rsf', ?, ?)",
                    [player_id, f"{season}-08-01", position, float(rank)],
                )
            rank += 1


def _small_league() -> LeagueContext:
    return LeagueContext(
        league_id="test_small",
        format="dynasty",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1},
        roster={"bench": 4, "roster_size": 5},
    )


class TestLoadSeasonStatic:
    def test_loads_every_field(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        assert len(static.projections) == 24  # 4 positions x 6 players
        assert len(static.vorp) == 24
        assert set(static.replacement_levels) == {"QB", "RB", "WR", "TE"}
        assert len(static.confidence) == 24
        assert len(static.ecr_dispersion) == 24

    def test_scarcity_norm_is_bounded_zero_to_one(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        assert all(0.0 <= v <= 1.0 for v in static.scarcity_norm.values())


class TestFeasibilityCap:
    def test_derived_from_league_bench_not_hardcoded(self):
        """Regression: unlike roster_need's hardcoded depth_target = slots + 2,
        _feasibility_cap must actually change when the league's configured bench changes."""
        league_small_bench = LeagueContext(
            league_id="x",
            format="redraft",
            teams=4,
            lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1},
            roster={"bench": 4},
        )
        league_big_bench = LeagueContext(
            league_id="x",
            format="redraft",
            teams=4,
            lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1},
            roster={"bench": 20},
        )
        assert _feasibility_cap(league_big_bench, "QB") > _feasibility_cap(league_small_bench, "QB")

    def test_cap_is_at_least_the_starting_requirement(self):
        league = LeagueContext(
            league_id="x",
            format="redraft",
            teams=4,
            lineup={"QB": 2, "RB": 1},
            roster={"bench": 0},
        )
        assert _feasibility_cap(league, "QB") >= 2


class TestScoreCandidateTiers:
    def test_tier_a_ignores_roster_context(self, con):
        """Tier A must score purely on projection -- an already-full position must not be
        discounted at all."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        saturated = score_candidate(static, "QB_0", league, ["QB", "QB", "QB"], "A")
        fresh = score_candidate(static, "QB_0", league, [], "A")
        assert saturated.score == pytest.approx(fresh.score)
        assert saturated.score == pytest.approx(static.projections["QB_0"])

    def test_tier_b_discounts_a_saturated_position(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        fresh = score_candidate(static, "QB_0", league, [], "B")
        saturated = score_candidate(static, "QB_0", league, ["QB", "QB", "QB"], "B")
        assert saturated.score < fresh.score

    def test_tier_e_applies_a_hard_feasibility_penalty_past_the_cap(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        cap = _feasibility_cap(league, "QB")
        over_cap_roster = ["QB"] * (cap + 1)
        s = score_candidate(
            static,
            "QB_0",
            league,
            over_cap_roster,
            "E",
            available=set(static.projections),
            current_pick_overall=1,
            next_pick_overall=5,
        )
        assert s.feasibility_multiplier == pytest.approx(0.1)

    def test_tier_f_adds_a_nonnegative_opportunity_cost(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        s = score_candidate(
            static,
            "QB_0",
            league,
            [],
            "F",
            available=set(static.projections),
            current_pick_overall=1,
            next_pick_overall=9,
        )
        assert s.opportunity_cost_pts is not None
        assert s.opportunity_cost_pts >= 0.0

    def test_unknown_candidate_returns_none(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        assert score_candidate(static, "nobody", league, [], "A") is None


class TestSimulateForensicDraft:
    @pytest.mark.parametrize("tier", ALL_TIERS)
    def test_drafts_the_full_roster_for_every_tier(self, con, tier):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        result = simulate_forensic_draft(con, league, 2023, tier, draft_slot=1, static=static)
        assert len(result.drafted_player_ids) == 5
        assert len(set(result.drafted_player_ids)) == 5

    def test_trace_records_every_pick_with_a_selected_and_ranked_candidates(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        trace: list[dict] = []
        simulate_forensic_draft(con, league, 2023, "F", draft_slot=1, static=static, trace=trace)
        assert len(trace) == 5  # roster_size picks by the team in question
        for pick in trace:
            assert pick["selected"]["player_id"]
            assert len(pick["top_5_candidates"]) >= 1

    def test_tier_h_matches_a_direct_recommend_draft_pick_call(self, con):
        """The diagnostic harness's tier H must be a faithful pass-through to production, not
        a reimplementation that could silently drift from the real recommend_draft_pick."""
        from alpha_squad.league.draft import recommend_draft_pick

        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        direct = recommend_draft_pick(con, league, 2023, [], available, next_pick_overall=5)

        result = simulate_forensic_draft(con, league, 2023, "H", draft_slot=1, static=static)
        assert result.drafted_player_ids[0] == direct.recommendation


class TestHomogeneousLeagueDraft:
    def test_every_slot_drafts_a_full_roster(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        rosters = homogeneous_league_draft(con, league, 2023, "market_consensus", static)
        assert set(rosters) == {1, 2, 3, 4}
        for ids in rosters.values():
            assert len(ids) == 5

    def test_no_player_drafted_twice_across_the_whole_league(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        rosters = homogeneous_league_draft(con, league, 2023, "vorp", static)
        all_ids = [pid for ids in rosters.values() for pid in ids]
        assert len(all_ids) == len(set(all_ids))


class TestRosterFeasibilityMetrics:
    def test_zero_drafted_starting_position_is_flagged(self):
        league = _small_league()
        metrics = roster_feasibility_metrics(league, ["QB", "QB", "WR", "WR", "TE"])
        assert "RB" in metrics["zero_drafted_starting_positions"]

    def test_concentration_index_is_one_for_a_single_position_roster(self):
        league = _small_league()
        metrics = roster_feasibility_metrics(league, ["QB", "QB", "QB"])
        assert metrics["concentration_index"] == pytest.approx(1.0)

    def test_concentration_index_is_below_one_for_a_balanced_roster(self):
        league = _small_league()
        metrics = roster_feasibility_metrics(league, ["QB", "RB", "WR", "TE"])
        assert metrics["concentration_index"] < 1.0
