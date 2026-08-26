"""Unit tests for the league decision engine: context loading, replacement/scarcity (the
value-based-drafting-with-flex algorithm), roster need, and draft/waiver/trade
recommendations, against synthetic data."""

from __future__ import annotations

import duckdb
import pytest
import yaml

from alpha_squad.league.context import (
    LeagueContext,
    list_registered_leagues,
    load_league_context,
    resolve_league,
)
from alpha_squad.league.draft import next_pick_survival_probability, recommend_draft_pick
from alpha_squad.league.replacement import (
    compute_league_starters,
    marginal_value_over_replacement,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.roster import roster_fit_multiplier, roster_need
from alpha_squad.league.trade import (
    PickAsset,
    TradePackageSide,
    age_curve_multiplier,
    evaluate_trade_package,
    pick_value,
    recommend_dynasty_trade,
)
from alpha_squad.league.waiver import rank_waiver_targets, recommend_waiver_pickup
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


class TestResolveLeague:
    """docs/DECISIONS.md D33: `resolve_league` is the seamless-switching entry point --
    looks a league_id up in a registry and dispatches to whichever source it declares,
    rather than every caller hardcoding a single YAML path."""

    def test_default_league_id_matches_the_old_hardcoded_behavior_exactly(self):
        assert resolve_league() == load_league_context()

    def test_unregistered_league_id_raises_an_actionable_error(self):
        with pytest.raises(RuntimeError, match="no league registered"):
            resolve_league("does_not_exist")

    def test_a_yaml_entry_with_a_relative_path_resolves_relative_to_the_registry_file(
        self, tmp_path
    ):
        league_yaml = tmp_path / "my_league.yaml"
        league_yaml.write_text(
            yaml.dump(
                {
                    "league_id": "my_league",
                    "format": "redraft",
                    "teams": 8,
                    "scoring": {"ppr": True},
                    "lineup": {"QB": 1, "RB": 2, "WR": 2},
                    "roster": {"bench": 5},
                    "faab": {"budget": 0},
                }
            )
        )
        registry = tmp_path / "registry.yaml"
        registry.write_text(yaml.dump({"my_league": {"source": "yaml", "path": "my_league.yaml"}}))

        league = resolve_league("my_league", registry_path=registry)
        assert league.teams == 8
        assert league.league_id == "my_league"

    def test_an_entry_with_an_unknown_source_raises_rather_than_silently_defaulting(self, tmp_path):
        registry = tmp_path / "registry.yaml"
        registry.write_text(yaml.dump({"weird": {"source": "espn_scrape"}}))
        with pytest.raises(RuntimeError, match="unknown source"):
            resolve_league("weird", registry_path=registry)

    def test_list_registered_leagues_reflects_the_real_registry_file(self):
        leagues = list_registered_leagues()
        assert "target_league" in leagues
        assert leagues["target_league"]["source"] == "yaml"

    def test_list_registered_leagues_on_a_missing_file_is_an_empty_dict_not_an_error(
        self, tmp_path
    ):
        assert list_registered_leagues(tmp_path / "nope.yaml") == {}


class TestRegisterSleeperLeague:
    """D53: the "Connect League" onboarding action -- validates a real Sleeper league by
    actually loading it, then persists it so resolve_league/list_registered_leagues see it
    without any file edit."""

    def test_registers_a_real_reachable_league_and_makes_it_resolvable(
        self, con, settings, monkeypatch
    ):
        import httpx

        from alpha_squad.league.context import register_sleeper_league

        body = {
            "league_id": "999888777",
            "name": "My New League",
            "season": "2026",
            "total_rosters": 10,
            "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN"],
            "scoring_settings": {"rec": 1.0},
            "settings": {"type": 2, "waiver_budget": 100},
        }

        def fake_get(url, **kwargs):
            import json as _json

            from tests.fixtures.httpx_fakes import FakeGetResponse

            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

        league = register_sleeper_league(
            con, "999888777", settings=settings, league_id="my_new_league"
        )
        assert league.teams == 10
        assert league.format == "dynasty"

        registry = list_registered_leagues(con=con)
        assert registry["my_new_league"]["source"] == "sleeper"
        assert registry["my_new_league"]["sleeper_league_id"] == "999888777"

        resolved = resolve_league("my_new_league", con=con, settings=settings)
        assert resolved.teams == 10

    def test_registering_the_same_league_again_updates_rather_than_duplicates(
        self, con, settings, monkeypatch
    ):
        import httpx

        from alpha_squad.league.context import register_sleeper_league

        body = {
            "league_id": "111",
            "name": "Original Name",
            "total_rosters": 8,
            "roster_positions": ["QB", "BN"],
            "scoring_settings": {},
            "settings": {"type": 0},
        }

        def fake_get(url, **kwargs):
            import json as _json

            from tests.fixtures.httpx_fakes import FakeGetResponse

            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

        register_sleeper_league(con, "111", settings=settings, league_id="dupe_test")
        register_sleeper_league(con, "111", settings=settings, league_id="dupe_test")

        n = con.execute(
            "SELECT count(*) FROM registered_leagues WHERE league_id = 'dupe_test'"
        ).fetchone()[0]
        assert n == 1

    def test_unreachable_league_raises_rather_than_registering_anyway(
        self, con, settings, monkeypatch
    ):
        import httpx

        from alpha_squad.league.context import register_sleeper_league
        from alpha_squad.sources.base import SourceError

        def fake_get_404(url, **kwargs):
            from tests.fixtures.httpx_fakes import FakeGetResponse

            return FakeGetResponse(404, None, b"not found")

        monkeypatch.setattr(httpx, "get", fake_get_404)

        with pytest.raises(SourceError):
            register_sleeper_league(con, "does-not-exist", settings=settings)

        n = con.execute("SELECT count(*) FROM registered_leagues").fetchone()[0]
        assert n == 0


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

    def _seed(self, con, player_id, best, worst, scrape_date="2025-08-01"):
        con.execute(
            "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst) "
            "VALUES (?, ?, 'rsf', 'WR', ?, ?, ?)",
            [player_id, scrape_date, (best + worst) / 2, best, worst],
        )

    def test_certainly_gone_before_the_best_case_rank(self, con):
        self._seed(con, "p1", best=5, worst=15)
        assert next_pick_survival_probability(
            con, "p1", next_pick_overall=20, season=2025
        ) == pytest.approx(0.0)

    def test_certainly_available_after_the_worst_case_rank(self, con):
        self._seed(con, "p1", best=5, worst=15)
        assert next_pick_survival_probability(
            con, "p1", next_pick_overall=1, season=2025
        ) == pytest.approx(1.0)

    def test_interpolates_within_the_expert_dispersion(self, con):
        self._seed(con, "p1", best=10, worst=20)
        prob = next_pick_survival_probability(con, "p1", next_pick_overall=15, season=2025)
        assert 0.0 < prob < 1.0
        assert prob == pytest.approx(0.5)

    def test_no_market_data_returns_none(self, con):
        assert (
            next_pick_survival_probability(con, "nobody", next_pick_overall=10, season=2025) is None
        )

    def test_does_not_leak_a_snapshot_recorded_after_the_draft_season(self, con):
        """Regression (D54): a real historical draft simulation for season 2021 must not see
        expert-rank dispersion recorded in 2026 -- found live via a real draft_simulation.py
        run where many players' market_snapshot rows span 2021-2026 and the un-scoped
        `ORDER BY scrape_date DESC LIMIT 1` picked up the 2026 row regardless of which
        historical season was being drafted."""
        self._seed(con, "p1", best=5, worst=15, scrape_date="2026-08-01")
        assert next_pick_survival_probability(con, "p1", next_pick_overall=20, season=2021) is None

    def test_uses_the_snapshot_from_the_season_being_drafted_not_a_later_one(self, con):
        self._seed(con, "p1", best=5, worst=15, scrape_date="2021-08-01")
        self._seed(con, "p1", best=50, worst=60, scrape_date="2026-08-01")
        assert next_pick_survival_probability(
            con, "p1", next_pick_overall=20, season=2021
        ) == pytest.approx(0.0)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def settings(tmp_path):
    from alpha_squad.config.settings import Settings

    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


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

    def test_exact_score_ties_break_deterministically_by_player_id(self, con):
        """Regression (D54): candidates are built by iterating `available_player_ids` (a
        `set`), whose order depends on hash randomization that differs across process runs
        (confirmed: PYTHONHASHSEED unset in this environment) -- an exact score tie could
        otherwise pick a different player on a re-run of the identical historical draft."""
        league = load_league_context()
        _seed_uncertainty(con, "zeta", 2025, "QB", 300.0)
        _seed_uncertainty(con, "alpha_p", 2025, "QB", 300.0)
        rec = recommend_draft_pick(con, league, 2025, [], {"zeta", "alpha_p"})
        assert rec.recommendation == "alpha_p"


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


class TestRankWaiverTargets:
    """D53: the Action Center's "who should I add" data -- real free agents (not rostered on
    ANY real team) ranked by the exact same scoring `recommend_waiver_pickup` already does for
    one player."""

    LEAGUE_ID = "waiver_rank_test"

    def _league(self) -> LeagueContext:
        return LeagueContext(
            league_id=self.LEAGUE_ID,
            format="dynasty",
            teams=2,
            lineup={"WR": 1},
            faab={"budget": 100},
            source="sleeper",
            sleeper_league_id=self.LEAGUE_ID,
        )

    def _fake_get(self, monkeypatch, rostered_sleeper_ids):
        import httpx

        from tests.fixtures.httpx_fakes import FakeGetResponse

        rosters = [
            {"roster_id": 1, "owner_id": "u1", "players": rostered_sleeper_ids},
            {"roster_id": 2, "owner_id": "u2", "players": []},
        ]
        users = [{"user_id": "u1", "display_name": "me", "metadata": {}}]

        def fake_get(url, **kwargs):
            import json as _json

            if url.endswith("/rosters"):
                body = rosters
            elif url.endswith("/users"):
                body = users
            else:
                raise AssertionError(f"unexpected url {url}")
            return FakeGetResponse(200, body, _json.dumps(body).encode())

        monkeypatch.setattr(httpx, "get", fake_get)

    def _seed_bridged_player(self, con, player_id, position, points, sleeper_id):
        _seed_uncertainty(con, player_id, 2025, position, points)
        con.execute(
            "INSERT INTO players (player_id, gsis_id, display_name, position) VALUES "
            "(?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [player_id, f"gsis_{player_id}", player_id, position],
        )
        con.execute(
            "INSERT INTO player_id_map (id_type, id_value, player_id, source) VALUES "
            "('sleeper_id', ?, ?, 'test')",
            [sleeper_id, player_id],
        )

    def test_excludes_rostered_players_and_ranks_free_agents(self, con, monkeypatch):
        self._seed_bridged_player(con, "rostered_wr", "WR", 300, "sl_rostered")
        self._seed_bridged_player(con, "fa_best", "WR", 250, "sl_fa_best")
        self._seed_bridged_player(con, "fa_worst", "WR", 60, "sl_fa_worst")
        self._fake_get(monkeypatch, ["sl_rostered"])

        results = rank_waiver_targets(con, self._league(), 2025, 5, roster_id=2)

        ids = [r.player_id for r in results]
        assert "rostered_wr" not in ids
        assert ids[0] == "fa_best"

    def test_position_filter_restricts_candidates(self, con, monkeypatch):
        self._seed_bridged_player(con, "fa_wr", "WR", 200, "sl_wr")
        self._seed_bridged_player(con, "fa_rb", "RB", 200, "sl_rb")
        self._fake_get(monkeypatch, [])

        results = rank_waiver_targets(con, self._league(), 2025, 5, roster_id=2, positions={"WR"})
        assert {r.player_id for r in results} == {"fa_wr"}

    def test_unsupported_league_raises(self, con):
        with pytest.raises(RuntimeError, match="no real per-team roster source"):
            rank_waiver_targets(con, load_league_context(), 2025, 5, roster_id=1)


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


class TestPickValue:
    """D45: future-draft-pick valuation, a documented heuristic on the same value_2qb scale."""

    def test_earlier_round_is_worth_more_than_later_round(self):
        v1, _ = pick_value(round_=1, teams=10, pick_in_round=6)
        v2, _ = pick_value(round_=2, teams=10, pick_in_round=6)
        v3, _ = pick_value(round_=3, teams=10, pick_in_round=6)
        assert v1 > v2 > v3 > 0

    def test_earlier_slot_within_round_is_worth_more(self):
        first, _ = pick_value(round_=1, teams=10, pick_in_round=1)
        last, _ = pick_value(round_=1, teams=10, pick_in_round=10)
        assert first > last > 0

    def test_further_out_years_are_worth_less(self):
        this_year, _ = pick_value(round_=1, teams=10, pick_in_round=1, years_out=0)
        next_year, _ = pick_value(round_=1, teams=10, pick_in_round=1, years_out=1)
        two_years, _ = pick_value(round_=1, teams=10, pick_in_round=1, years_out=2)
        assert this_year > next_year > two_years > 0

    def test_unknown_slot_uses_round_midpoint_between_first_and_last(self):
        unknown, _ = pick_value(round_=1, teams=10, pick_in_round=None)
        first, _ = pick_value(round_=1, teams=10, pick_in_round=1)
        last, _ = pick_value(round_=1, teams=10, pick_in_round=10)
        assert last < unknown < first

    def test_reason_string_discloses_this_is_a_heuristic_not_a_trained_model(self):
        _, reason = pick_value(round_=1, teams=10, pick_in_round=1)
        assert "heuristic" in reason
        assert "D45" in reason


class TestEvaluateTradePackage:
    """D45: real multi-asset trade comparison summing player + pick value on each side."""

    def _seed_player(self, con, player_id, age, value_2qb):
        con.execute(
            "INSERT INTO dynasty_values (player_id, scrape_date, age, value_2qb, updated_at) "
            "VALUES (?, '2026-08-01', ?, ?, current_timestamp)",
            [player_id, age, value_2qb],
        )

    def test_lopsided_package_favors_the_richer_side(self, con):
        self._seed_player(con, "star", 24.0, 9000)
        self._seed_player(con, "scrub", 30.0, 50)

        side_a = TradePackageSide(player_ids=["star"])
        side_b = TradePackageSide(player_ids=["scrub"], picks=[PickAsset(round=4)])

        result = evaluate_trade_package(con, side_a, side_b, season=2025, teams=10)
        assert result.favors == "side_a"
        assert result.side_a_value > result.side_b_value
        assert result.delta > 0
        assert any("star" in r for r in result.side_a_reasons)

    def test_a_pick_can_balance_a_trade(self, con):
        self._seed_player(con, "playerA", 25.0, 2500)
        self._seed_player(con, "playerB", 25.0, 2500)

        # Identical players on both sides plus a real 1st-round pick added to side_b should tip
        # the trade toward side_b, not stay even.
        side_a = TradePackageSide(player_ids=["playerA"])
        side_b = TradePackageSide(
            player_ids=["playerB"], picks=[PickAsset(round=1, pick_in_round=1)]
        )

        result = evaluate_trade_package(con, side_a, side_b, season=2025, teams=10)
        assert result.favors == "side_b"

    def test_roughly_equal_packages_are_reported_even(self, con):
        self._seed_player(con, "playerA", 25.0, 2500)
        self._seed_player(con, "playerB", 25.0, 2500)

        side_a = TradePackageSide(player_ids=["playerA"])
        side_b = TradePackageSide(player_ids=["playerB"])

        result = evaluate_trade_package(con, side_a, side_b, season=2025, teams=10)
        assert result.favors == "even"

    def test_empty_sides_do_not_error(self, con):
        result = evaluate_trade_package(
            con, TradePackageSide(), TradePackageSide(), season=2025, teams=10
        )
        assert result.side_a_value == 0.0
        assert result.side_b_value == 0.0
        assert result.favors == "even"
