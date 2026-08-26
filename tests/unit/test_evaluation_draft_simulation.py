"""Unit tests for the historical draft simulation engine (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.draft_simulation import (
    ALL_STRATEGIES,
    ALPHA_BPA,
    ALPHA_LEAGUE_AWARE,
    GENERIC_PRIOR_YEAR,
    MARKET_CONSENSUS,
    _alpha_bpa_pick,
    _generic_prior_year_pick,
    _market_consensus_pick,
    _next_pick_overall,
    _snake_overall_pick,
    persist_draft_sim_results,
    run_draft_simulation,
    simulate_draft,
    summarize_draft_sim,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db


class TestSnakeDraftMath:
    def test_odd_round_goes_forward(self):
        assert [_snake_overall_pick(1, s, 10) for s in range(1, 11)] == list(range(1, 11))

    def test_even_round_reverses(self):
        assert [_snake_overall_pick(2, s, 10) for s in range(1, 11)] == list(range(20, 10, -1))

    def test_next_pick_overall_none_on_last_round(self):
        assert _next_pick_overall(17, 3, 10, total_rounds=17) is None

    def test_next_pick_overall_correct_for_middle_round(self):
        # Round 1, slot 3 -> overall 3. Round 2 reverses, so slot 3's round-2 pick is overall 18.
        assert _next_pick_overall(1, 3, 10, total_rounds=17) == 18


class TestPureStrategyPicks:
    def test_market_consensus_picks_lowest_rank(self):
        market_rank = {"a": ("WR", 5.0), "b": ("RB", 1.0), "c": ("QB", 10.0)}
        assert _market_consensus_pick({"a", "b", "c"}, market_rank) == "b"

    def test_market_consensus_unranked_player_sorts_last(self):
        market_rank = {"a": ("WR", 5.0)}
        assert _market_consensus_pick({"a", "unranked"}, market_rank) == "a"

    def test_generic_prior_year_picks_highest_points(self):
        prior = {"a": 100.0, "b": 250.0}
        assert _generic_prior_year_pick({"a", "b"}, prior) == "b"

    def test_alpha_bpa_picks_highest_projection(self):
        proj = {"a": 100.0, "b": 250.0}
        assert _alpha_bpa_pick({"a", "b"}, proj) == "b"

    def test_market_consensus_tie_breaks_deterministically_by_player_id(self):
        """Regression (D54): `available` is a Python `set`, whose iteration order depends on
        hash randomization that differs across process runs (confirmed: PYTHONHASHSEED unset
        in this environment). Real tied ECR ranks are common (43 tied groups in the real 2025
        'rsf' data alone) -- without an explicit secondary key, a tied pick could silently
        differ between two runs of the identical historical draft, which would make this
        evaluation's own numbers unreproducible. This test cannot itself vary the
        process-level hash seed (not practical from within one pytest run); it instead pins
        down the documented tie-break rule (alphabetically-first player_id wins for `min`) as
        an explicit, verifiable contract, independent of set iteration order."""
        market_rank = {"zeta": ("WR", 5.0), "alpha_p": ("RB", 5.0), "mid": ("QB", 5.0)}
        for _ in range(20):
            assert _market_consensus_pick(set(market_rank), market_rank) == "alpha_p"

    def test_generic_prior_year_tie_breaks_deterministically_by_player_id(self):
        prior = {"zeta": 100.0, "alpha_p": 100.0, "mid": 100.0}
        for _ in range(20):
            assert _generic_prior_year_pick(set(prior), prior) == "zeta"

    def test_alpha_bpa_tie_breaks_deterministically_by_player_id(self):
        proj = {"zeta": 100.0, "alpha_p": 100.0, "mid": 100.0}
        for _ in range(20):
            assert _alpha_bpa_pick(set(proj), proj) == "zeta"


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _seed_league_season(con, season, n_per_position=6):
    """A small synthetic season: n_per_position real uncertainty_predictions + real
    player_season_stats + real preseason 'rsf' market rank per position, enough to draft a
    full small league from."""
    positions = ("QB", "RB", "WR", "TE")
    rank = 1
    for position in positions:
        for i in range(n_per_position):
            player_id = f"{position}_{i}"
            points = 300.0 - i * 20  # strictly decreasing within position
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
            con.execute(
                "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank) "
                "VALUES (?, ?, 'rsf', ?, ?)",
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
        roster={"bench": 1, "roster_size": 5},
    )


class TestSimulateDraft:
    def test_drafts_the_full_roster_size(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        result = simulate_draft(con, league, 2023, MARKET_CONSENSUS, draft_slot=1)
        assert len(result.drafted_player_ids) == 5
        assert len(set(result.drafted_player_ids)) == 5  # no duplicate picks

    def test_market_consensus_always_takes_the_best_remaining_rank(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        result = simulate_draft(con, league, 2023, MARKET_CONSENSUS, draft_slot=1)
        # Draft slot 1 picks first overall every odd round in a 4-team snake -- with a strictly
        # increasing overall rank (QB_0..QB_5 rank 1-6, RB_0..RB_5 rank 7-12, ...), the very
        # first pick must be the single best-ranked player on the board.
        assert result.drafted_player_ids[0] == "QB_0"

    def test_different_strategies_are_reproducible(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        r1 = simulate_draft(con, league, 2023, GENERIC_PRIOR_YEAR, draft_slot=2)
        r2 = simulate_draft(con, league, 2023, GENERIC_PRIOR_YEAR, draft_slot=2)
        assert r1.drafted_player_ids == r2.drafted_player_ids
        assert r1.total_roster_points == r2.total_roster_points

    def test_alpha_league_aware_runs_end_to_end(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        result = simulate_draft(con, league, 2023, ALPHA_LEAGUE_AWARE, draft_slot=1)
        assert len(result.drafted_player_ids) == 5
        assert result.total_roster_points > 0

    def test_alpha_league_aware_threads_the_historical_season_into_survival_probability(
        self, con, monkeypatch
    ):
        """Regression (D54): league/draft.py::next_pick_survival_probability used to have no
        `season` parameter at all -- it queried market_snapshot's single most-recently-scraped
        row with no scoping, so a historical draft simulation for season 2021 could read
        expert-rank dispersion recorded as late as 2026 (confirmed against real data: many
        players' market_snapshot rows span exactly that range). The fix threads `season`
        through recommend_draft_pick into next_pick_survival_probability, restricted to that
        season's own Jul/Aug window (matching market/edge.py's leakage-safe pattern). An
        end-to-end behavioral test of this is unreliable here -- the survival term is one of
        several multiplicative factors and a synthetic scenario can easily fail to put any
        candidate on a decision boundary it would flip -- so this asserts the wiring directly:
        every call the real draft path makes must carry the historical season being drafted,
        never a caller-omitted default."""
        _seed_league_season(con, 2023)
        league = _small_league()

        from alpha_squad.league import draft as draft_module

        seasons_seen: list[int] = []
        real_fn = draft_module.next_pick_survival_probability

        def spy(con_arg, player_id, next_pick_overall, season, ecr_type="rsf"):
            seasons_seen.append(season)
            return real_fn(con_arg, player_id, next_pick_overall, season, ecr_type)

        monkeypatch.setattr(draft_module, "next_pick_survival_probability", spy)

        simulate_draft(con, league, 2023, ALPHA_LEAGUE_AWARE, draft_slot=1)

        assert seasons_seen, "expected at least one survival-probability lookup during the draft"
        assert all(s == 2023 for s in seasons_seen)

    def test_starter_points_never_exceeds_total_roster_points(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        result = simulate_draft(con, league, 2023, ALPHA_BPA, draft_slot=1)
        assert result.starter_points <= result.total_roster_points

    def test_rejects_out_of_range_draft_slot(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        with pytest.raises(ValueError, match="draft_slot"):
            simulate_draft(con, league, 2023, MARKET_CONSENSUS, draft_slot=99)

    def test_rejects_unknown_strategy(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        with pytest.raises(ValueError, match="strategy"):
            simulate_draft(con, league, 2023, "not_a_real_strategy", draft_slot=1)


class TestRunAndPersist:
    def test_run_draft_simulation_covers_every_strategy_and_slot(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(con, league, [2023])
        assert len(results) == len(ALL_STRATEGIES) * league.teams

    def test_persist_and_summarize_round_trip(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(
            con, league, [2023], strategies=[MARKET_CONSENSUS, ALPHA_BPA]
        )
        persist_draft_sim_results(con, results)

        summary = summarize_draft_sim(con, [2023])
        strategies_seen = {row["strategy"] for row in summary}
        assert strategies_seen == {MARKET_CONSENSUS, ALPHA_BPA}
        for row in summary:
            assert row["n"] == league.teams

    def test_persist_is_idempotent_on_rerun(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(con, league, [2023], strategies=[MARKET_CONSENSUS])
        persist_draft_sim_results(con, results)
        persist_draft_sim_results(con, results)  # rerun must not duplicate rows
        n = con.execute("SELECT count(*) FROM draft_simulation_results").fetchone()[0]
        assert n == league.teams
