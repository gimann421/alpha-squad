"""Unit tests for the historical draft simulation engine (docs/DECISIONS.md D54)."""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.draft_simulation import (
    ALL_OPPONENT_STRATEGIES,
    ALL_STRATEGIES,
    ALPHA_BPA,
    ALPHA_LEAGUE_AWARE,
    GENERIC_PRIOR_YEAR,
    MARKET_CONSENSUS,
    MARKET_CONSENSUS_ROSTER_AWARE,
    _alpha_bpa_pick,
    _generic_prior_year_pick,
    _market_consensus_pick,
    _market_consensus_roster_aware_pick,
    _next_pick_overall,
    _snake_overall_pick,
    persist_draft_sim_results,
    run_draft_simulation,
    simulate_draft,
    summarize_draft_sim,
    write_draft_simulation_report,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
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


class TestMarketConsensusRosterAwarePick:
    """D61 Stage 1.1: the fair consensus opponent. `_market_consensus_pick` never fills a
    mandatory dedicated slot it hasn't reached in real ECR order; this is the fix."""

    def _league(self, **overrides) -> LeagueContext:
        base = dict(
            league_id="t",
            format="redraft",
            teams=2,
            lineup={"QB": 1, "RB": 1, "WR": 1, "K": 1},
            roster={"bench": 2, "roster_size": 6},
        )
        base.update(overrides)
        return LeagueContext(**base)

    def test_matches_plain_consensus_when_not_yet_forced(self):
        """Early in the draft (more picks left than unfilled slots), the two must agree."""
        league = self._league()
        market_rank = {"qb1": ("QB", 1.0), "rb1": ("RB", 2.0), "k1": ("K", 50.0)}
        positions = {"qb1": "QB", "rb1": "RB", "k1": "K"}
        available = {"qb1", "rb1", "k1"}
        assert _market_consensus_roster_aware_pick(
            available, market_rank, positions, league, [], picks_remaining=6
        ) == _market_consensus_pick(available, market_rank)

    def test_forces_a_still_unfilled_mandatory_slot_once_picks_are_tight(self):
        """Roster already has QB+RB (both dedicated slots filled); 2 picks remain and WR+K
        are both still unfilled (deficit 2) -- this pick MUST go to WR or K, even though a
        much-better-ranked QB is on the board (QB is no longer deficient)."""
        league = self._league()
        market_rank = {
            "qb_extra": ("QB", 1.0),  # best rank on the board, but QB already filled
            "wr1": ("WR", 10.0),
            "k1": ("K", 50.0),
        }
        positions = {"qb_extra": "QB", "wr1": "WR", "k1": "K"}
        pick = _market_consensus_roster_aware_pick(
            {"qb_extra", "wr1", "k1"},
            market_rank,
            positions,
            league,
            ["QB", "RB"],
            picks_remaining=2,
        )
        assert pick == "wr1"  # best-by-ECR WITHIN {wr1, k1}, not qb_extra

    def test_the_restriction_stays_active_every_remaining_pick(self):
        """Filling one deficient slot must not un-trigger the restriction for the next pick:
        deficit and picks_remaining both drop by 1 together, so the equality holds again."""
        league = self._league()
        market_rank = {"rb_extra": ("RB", 1.0), "k1": ("K", 50.0)}
        positions = {"rb_extra": "RB", "k1": "K"}
        # Roster has QB, WR, and one of the two required slots already filled by a prior
        # forced pick; only K remains, with exactly 1 pick left.
        pick = _market_consensus_roster_aware_pick(
            {"rb_extra", "k1"},
            market_rank,
            positions,
            league,
            ["QB", "WR", "RB"],
            picks_remaining=1,
        )
        assert pick == "k1"

    def test_a_league_with_no_kicker_slot_is_unaffected_by_the_mechanism(self):
        """The correctness test the plan names explicitly. Fix the exact scenario that WOULD
        force a pick if a K slot existed (a much-better-ranked non-deficient QB on the board,
        one pick left, one deficient K slot) and show it stops forcing anything the instant
        the league's lineup simply has no K slot -- the mechanism has nothing to force."""
        market_rank = {"qb_extra": ("QB", 1.0), "k1": ("K", 50.0)}
        positions = {"qb_extra": "QB", "k1": "K"}
        available = {"qb_extra", "k1"}
        roster_positions = ["QB"]  # the one QB slot is already filled

        with_k = self._league(lineup={"QB": 1, "K": 1})
        assert (
            _market_consensus_roster_aware_pick(
                available, market_rank, positions, with_k, roster_positions, picks_remaining=1
            )
            == "k1"  # forced: K is the only still-unfilled mandatory slot
        )

        without_k = self._league(lineup={"QB": 1})
        assert _market_consensus_roster_aware_pick(
            available, market_rank, positions, without_k, roster_positions, picks_remaining=1
        ) == _market_consensus_pick(
            available, market_rank
        )  # unaffected: no K slot means nothing to force -- picks qb_extra like plain consensus


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
                "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, page_type) "
                # The test league is 1-QB dynasty, which resolves to the 'do' board (D56).
                "VALUES (?, ?, 'do', ?, ?, 'dynasty-overall')",
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


def _seed_k_worst_rank(con, season, n=6):
    """K players with real-shaped baseline data (`projection_snapshot`, D57 -- K comes from
    the baseline model, not `uncertainty_predictions`) but deliberately the worst real ECR
    ranks on the board (1000+, vs. 1-24 for `_seed_league_season`'s QB/RB/WR/TE) -- the shape
    that let `market_consensus` finish a real draft with its K slot unfilled (D61)."""
    for i in range(n):
        player_id = f"K_{i}"
        points = 100.0 - i * 5
        con.execute(
            "INSERT INTO projection_snapshot (model_name, player_id, season, position, "
            "predicted_points, built_at) VALUES (?, ?, ?, 'K', ?, current_timestamp)",
            [KDST_MODEL_NAME, player_id, season, points],
        )
        con.execute(
            "INSERT INTO player_season_stats (player_id, season, position, games_played, "
            "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, 'K', 15, ?, ?)",
            [player_id, season, points, points / 15],
        )
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
            "ecr_rank, page_type) VALUES (?, ?, 'do', 'K', ?, 'dynasty-overall')",
            [player_id, f"{season}-08-01", 1000.0 + i],
        )


def _league_with_kicker() -> LeagueContext:
    return LeagueContext(
        league_id="test_small_k",
        format="dynasty",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1, "K": 1},
        roster={"bench": 1, "roster_size": 7},
    )


class TestRosterAwareOpponentEndToEnd:
    """D61 Stage 1.1/1.4: the artifact and its fix, exercised through the real
    `simulate_draft` end-to-end path rather than the pick function in isolation. A large
    surplus of skill players (80, `n_per_position=20`) relative to the league-wide pick count
    (4 teams x 7 rounds = 28) mirrors the real finding: kickers ranked far worse than the
    total number of picks made are never REACHED under an unaware consensus, not merely
    disfavored -- this is what let a real 160-pick benchmark draft finish with its K slot
    unfilled (docs/DECISIONS.md D61)."""

    def test_plain_consensus_can_finish_with_the_kicker_slot_unfilled(self, con):
        _seed_league_season(con, 2023, n_per_position=20)
        _seed_k_worst_rank(con, 2023)
        league = _league_with_kicker()
        result = simulate_draft(con, league, 2023, MARKET_CONSENSUS, draft_slot=1)
        assert result.opponent_strategy == MARKET_CONSENSUS
        assert result.n_unfilled_mandatory_slots > 0
        assert not any(pid.startswith("K_") for pid in result.drafted_player_ids)

    def test_roster_aware_consensus_fills_the_kicker_slot(self, con):
        _seed_league_season(con, 2023, n_per_position=20)
        _seed_k_worst_rank(con, 2023)
        league = _league_with_kicker()
        result = simulate_draft(
            con,
            league,
            2023,
            MARKET_CONSENSUS_ROSTER_AWARE,
            draft_slot=1,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        assert result.opponent_strategy == MARKET_CONSENSUS_ROSTER_AWARE
        assert result.n_unfilled_mandatory_slots == 0
        assert any(pid.startswith("K_") for pid in result.drafted_player_ids)

    def test_opponent_strategy_changes_which_players_reach_the_team_in_question(self, con):
        """The plan's actual target is the FIXED OPPONENT FIELD, not just the
        team-in-question's own strategy. `alpha_bpa` (never wants a kicker itself; K's
        baseline points are dwarfed by every skill projection) never changes its OWN
        decision rule between the two opponent fields -- but if the opponent field's real
        behavior differs (one of the 3 opponents takes a kicker instead of hoarding another
        skill player), a different player is left on the board for alpha_bpa's own later
        picks. A different result here is the observable proof the opponent field itself
        changed, not just the team-in-question's strategy."""
        _seed_league_season(con, 2023, n_per_position=20)
        _seed_k_worst_rank(con, 2023)
        league = _league_with_kicker()
        under_plain = simulate_draft(
            con, league, 2023, ALPHA_BPA, draft_slot=1, opponent_strategy=MARKET_CONSENSUS
        )
        under_fair = simulate_draft(
            con,
            league,
            2023,
            ALPHA_BPA,
            draft_slot=1,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        assert not any(pid.startswith("K_") for pid in under_plain.drafted_player_ids)
        assert not any(pid.startswith("K_") for pid in under_fair.drafted_player_ids)
        assert under_plain.drafted_player_ids != under_fair.drafted_player_ids


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

    def test_rejects_unknown_opponent_strategy(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        with pytest.raises(ValueError, match="opponent"):
            simulate_draft(
                con, league, 2023, MARKET_CONSENSUS, draft_slot=1, opponent_strategy="not_real"
            )

    def test_default_opponent_strategy_is_market_consensus_unchanged(self, con):
        """D61 Stage 1.1 backward-compatibility requirement: an existing caller that never
        passes `opponent_strategy` must keep getting exactly the pre-D61 opponent field, so
        every number published through D60 stays reproducible under its original label."""
        _seed_league_season(con, 2023)
        league = _small_league()
        default = simulate_draft(con, league, 2023, ALPHA_BPA, draft_slot=1)
        explicit = simulate_draft(
            con, league, 2023, ALPHA_BPA, draft_slot=1, opponent_strategy=MARKET_CONSENSUS
        )
        assert default.opponent_strategy == MARKET_CONSENSUS
        assert default.drafted_player_ids == explicit.drafted_player_ids
        assert default.total_roster_points == explicit.total_roster_points


class TestRunAndPersist:
    def test_run_draft_simulation_covers_every_strategy_and_slot(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(con, league, [2023])
        assert len(results) == len(ALL_STRATEGIES) * league.teams
        assert all(r.opponent_strategy == MARKET_CONSENSUS for r in results)

    def test_opponent_strategies_param_covers_both_fields(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(
            con,
            league,
            [2023],
            strategies=[MARKET_CONSENSUS],
            opponent_strategies=list(ALL_OPPONENT_STRATEGIES),
        )
        assert len(results) == len(ALL_OPPONENT_STRATEGIES) * league.teams
        assert {r.opponent_strategy for r in results} == set(ALL_OPPONENT_STRATEGIES)

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
            assert row["opponent_strategy"] == MARKET_CONSENSUS

    def test_persist_keeps_both_opponent_fields_for_the_same_strategy_and_slot(self, con):
        """The regression this guards: `opponent_strategy` must be part of the persistence
        key, or persisting the fair-opponent run would silently overwrite the D60-comparable
        market_consensus-opponent run for the same (season, strategy, draft_slot)."""
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(
            con,
            league,
            [2023],
            strategies=[MARKET_CONSENSUS],
            opponent_strategies=list(ALL_OPPONENT_STRATEGIES),
        )
        persist_draft_sim_results(con, results)
        n = con.execute("SELECT count(*) FROM draft_simulation_results").fetchone()[0]
        assert n == len(ALL_OPPONENT_STRATEGIES) * league.teams

    def test_persist_is_idempotent_on_rerun(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(con, league, [2023], strategies=[MARKET_CONSENSUS])
        persist_draft_sim_results(con, results)
        persist_draft_sim_results(con, results)  # rerun must not duplicate rows
        n = con.execute("SELECT count(*) FROM draft_simulation_results").fetchone()[0]
        assert n == league.teams


class TestWriteDraftSimulationReport:
    """D61 Stage 1.4: a forfeited mandatory slot must be visible in the report, and the two
    opponent fields must never be silently blended into one restated number."""

    def test_market_consensus_only_run_banners_that_it_only_measured_one_opponent(
        self, con, tmp_path
    ):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(con, league, [2023], strategies=[MARKET_CONSENSUS])
        persist_draft_sim_results(con, results)
        write_draft_simulation_report(con, tmp_path / "r.md", [2023])
        report = (tmp_path / "r.md").read_text()
        assert "only measured `market_consensus`" in report
        # No DATA table for the opponent field that was never run, even though the
        # methodology section still documents what the mechanism is.
        assert f"## Overall vs `{MARKET_CONSENSUS_ROSTER_AWARE}` opponent field" not in report

    def test_both_opponents_run_reports_both_headlined_correctly(self, con, tmp_path):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(
            con,
            league,
            [2023],
            strategies=[MARKET_CONSENSUS],
            opponent_strategies=list(ALL_OPPONENT_STRATEGIES),
        )
        persist_draft_sim_results(con, results)
        write_draft_simulation_report(con, tmp_path / "r.md", [2023])
        report = (tmp_path / "r.md").read_text()
        assert f"Headline claim uses `{MARKET_CONSENSUS_ROSTER_AWARE}`" in report
        assert f"## Overall vs `{MARKET_CONSENSUS}` opponent field" in report
        assert f"## Overall vs `{MARKET_CONSENSUS_ROSTER_AWARE}` opponent field" in report
        assert "unfilled mandatory slots" in report.lower()

    def test_summary_rows_carry_opponent_strategy_and_unfilled_slot_stats(self, con, tmp_path):
        _seed_league_season(con, 2023)
        league = _small_league()
        results = run_draft_simulation(
            con,
            league,
            [2023],
            strategies=[MARKET_CONSENSUS],
            opponent_strategies=list(ALL_OPPONENT_STRATEGIES),
        )
        persist_draft_sim_results(con, results)
        summary = write_draft_simulation_report(con, tmp_path / "r.md", [2023])
        for row in summary:
            assert row["opponent_strategy"] in ALL_OPPONENT_STRATEGIES
            assert "mean_unfilled_mandatory_slots" in row
            assert "n_trials_with_unfilled_slots" in row
