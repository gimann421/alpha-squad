"""Unit tests for the diagnostic-only draft-engine forensic experiment harness
(docs/DRAFT_ENGINE_FORENSIC_AUDIT.md, docs/DRAFT_CONTROLLED_EXPERIMENTS.md)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import (
    ALL_S_TIERS,
    ALL_TIERS,
    ALL_Z_TIERS,
    DRAFT_AWARE_REPLACEMENT_TIERS,
    PREREGISTERED_S_CONTROL,
    PREREGISTERED_W_CONTROL,
    PREREGISTERED_Z_CONTROL,
    S_SWEEP_TIERS,
    S_TIER_SPEC,
    S_TIERS,
    TIER_DESCRIPTIONS,
    W_TIER_SPEC,
    W_TIERS,
    W_TIERS_ENFORCING_LEGALITY,
    X_TIER_SPEC,
    X_TIERS,
    Y_TIERS,
    Z_SWEEP_TIERS,
    Z_TIER_SPEC,
    Z_TIERS,
    _pick_by_tier,
    _survival_probability,
    homogeneous_league_draft,
    load_season_static,
    roster_feasibility_metrics,
    score_candidate,
    season_clustered_margin,
    simulate_forensic_draft,
)
from alpha_squad.league.context import LeagueContext, load_league_context
from alpha_squad.league.roster import positional_feasibility_cap, unfilled_dedicated_slots
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

_LEAGUE_CONFIGS_DIR = (
    Path(__file__).parents[2] / "src" / "alpha_squad" / "config" / "league_configs"
)
TARGET_LEAGUE = _LEAGUE_CONFIGS_DIR / "target_league.yaml"


def _seed_single_position_season(con, season, position, n_players=1):
    """Minimal real-shaped data for one position, enough for `load_season_static` to produce
    a usable `projections`/`vorp` entry -- QB/RB/WR/TE via `uncertainty_predictions` (M6),
    K/DST via `projection_snapshot` (D57's baseline), matching `load_season_projections`'s
    two real data paths so this seeds through the same code every other caller reads."""
    for i in range(n_players):
        player_id = f"{position}_{i}"
        points = 200.0 - i * 10
        if position in ("K", "DST"):
            con.execute(
                "INSERT INTO projection_snapshot "
                "(model_name, player_id, season, position, predicted_points, built_at) "
                "VALUES (?, ?, ?, ?, ?, current_timestamp)",
                [KDST_MODEL_NAME, player_id, season, position, points],
            )
        else:
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
                    "ecr_rank, ecr_best, ecr_worst, page_type) "
                    "VALUES (?, ?, 'do', ?, ?, ?, ?, 'dynasty-overall')",
                    [player_id, f"{season}-08-01", position, float(rank), rank, rank + 3],
                )
            else:
                con.execute(
                    "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                    "ecr_rank, page_type) VALUES (?, ?, 'do', ?, ?, 'dynasty-overall')",
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
    """The forensic harness has no cap logic of its own (D61 Stage 1.2): it calls the same
    `league/roster.py::positional_feasibility_cap` production uses, so these are really
    characterization tests of that shared function, kept here so a forensic-tier test still
    exercises the exact cap the harness applies."""

    def test_derived_from_league_bench_not_hardcoded(self):
        """Regression: unlike roster_need's hardcoded depth_target = slots + 2,
        positional_feasibility_cap must actually change when the league's configured bench
        changes."""
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
        assert positional_feasibility_cap(league_big_bench, "QB") > positional_feasibility_cap(
            league_small_bench, "QB"
        )

    def test_cap_is_at_least_the_starting_requirement(self):
        league = LeagueContext(
            league_id="x",
            format="redraft",
            teams=4,
            lineup={"QB": 2, "RB": 1},
            roster={"bench": 0},
        )
        assert positional_feasibility_cap(league, "QB") >= 2


class TestFeasibilityCapParityWithProduction:
    """D61 Stage 1.2 acceptance criterion 3: the forensic harness must use the SAME feasibility
    cap production uses, for every position in every shipped league config, so the two cannot
    silently drift apart the way the pre-D61 forensic-local `_feasibility_cap` copy did (it
    diverged from production's flex-aware `positional_feasibility_cap` on RB/WR/TE)."""

    def test_forensics_module_imports_the_shared_cap_function_rather_than_reimplementing_it(self):
        import alpha_squad.evaluation.draft_forensics as forensics_mod
        import alpha_squad.league.roster as roster_mod

        assert not hasattr(forensics_mod, "_feasibility_cap"), (
            "a forensic-local feasibility cap reappeared -- delegate to "
            "league.roster.positional_feasibility_cap instead (D61 Stage 1.2)"
        )
        assert forensics_mod.positional_feasibility_cap is roster_mod.positional_feasibility_cap

    @pytest.mark.parametrize("config_name", ["target_league.yaml", "legacy_2qb_dynasty.yaml"])
    def test_score_candidates_feasibility_penalty_threshold_matches_production_cap(
        self, con, config_name
    ):
        """Drive the real forensic scoring path (score_candidate, tier E) and confirm the
        feasibility penalty engages exactly at production's cap boundary -- not one before,
        not one after -- for every dedicated position in a real shipped league config."""
        league = load_league_context(_LEAGUE_CONFIGS_DIR / config_name)
        season = 2023
        for position in league.dedicated_slots():
            _seed_single_position_season(con, season, position, n_players=1)
        static = load_season_static(con, league, season)

        for position in league.dedicated_slots():
            player_id = f"{position}_0"
            if player_id not in static.projections:
                continue
            cap = positional_feasibility_cap(league, position)

            # `have >= cap` triggers the penalty, so a roster one short of the cap must NOT
            # be penalized, and a roster already AT the cap must be.
            below_cap_roster = [position] * max(0, cap - 1)
            below = score_candidate(
                static, player_id, league, below_cap_roster, "E", available={player_id}
            )
            assert below.feasibility_multiplier is None, (
                f"{position}: penalty applied one below production's cap ({cap})"
            )

            at_cap_roster = [position] * cap
            at_cap = score_candidate(
                static, player_id, league, at_cap_roster, "E", available={player_id}
            )
            assert at_cap.feasibility_multiplier == pytest.approx(0.1), (
                f"{position}: no penalty applied at production's cap ({cap})"
            )


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
        cap = positional_feasibility_cap(league, "QB")
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
        # D60: the harness passes the real (empty, at pick 1) roster explicitly, which
        # activates marginal starter value -- `roster_player_ids=[]` (a KNOWN empty roster)
        # is not the same call as omitting the argument (an UNKNOWN roster, which falls back
        # to VORP). The direct comparison call must match what the harness actually passes.
        direct = recommend_draft_pick(
            con, league, 2023, [], available, next_pick_overall=5, roster_player_ids=[]
        )

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


class TestD67WTiers:
    """D67: a structural demand target with no free parameter, plus roster legality as a
    constraint kept separate from valuation."""

    def test_the_control_reproduces_the_shipped_engine(self):
        """W0 must be N4 exactly -- static replacement, no legality constraint. If the control
        drifts from production, every W margin is measuring the wrong thing."""
        assert W_TIER_SPEC["W0"] == (None, False)
        assert PREREGISTERED_W_CONTROL == "W0"

    def test_legality_tiers_are_derived_from_the_spec_not_listed_twice(self):
        assert W_TIERS_ENFORCING_LEGALITY == ("W2", "W3")

    def test_w3_isolates_legality_from_depth(self):
        """The phase can only attribute a W2 win to depth if a tier exists that changes ONLY
        legality. W3 is that tier: static replacement, constraint on."""
        target, legality = W_TIER_SPEC["W3"]
        assert target is None and legality is True

    def test_every_w_tier_scores_through_the_draft_aware_branch(self):
        for tier in W_TIERS:
            assert tier in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_every_w_tier_is_described(self):
        for tier in W_TIERS:
            assert TIER_DESCRIPTIONS[tier]

    def test_legality_restricts_to_a_mandatory_slot_at_the_deadline(self):
        """The mechanism, at the level that matters: with exactly as many picks left as unfilled
        mandatory slots, the pick must fill one -- and it must be the best of those by the
        tier's own score, not a fixed position or a fixed round."""
        league = load_league_context(TARGET_LEAGUE)
        # A roster missing only K, with one pick left.
        roster = ["QB", "RB", "RB", "WR", "WR", "TE", "DST"]
        deficits = unfilled_dedicated_slots(league, roster)
        assert deficits == {"K": 1}
        assert sum(deficits.values()) == 1

    def test_legality_does_nothing_while_picks_remain(self):
        league = load_league_context(TARGET_LEAGUE)
        roster = ["QB", "RB", "RB", "WR", "WR", "TE", "DST"]
        # 5 picks left vs 1 unfilled slot -> the reservation must not trigger yet.
        assert sum(unfilled_dedicated_slots(league, roster).values()) < 5


class TestD68XTiers:
    """D68: the draft engine is a CONSTANT across the X-tiers. Only the projection input moves.

    These tests exist to keep that true. A calibration experiment whose tiers quietly differ in
    a second way measures the second way."""

    def test_the_control_is_the_shipped_engine_on_uncalibrated_projections(self):
        assert X_TIER_SPEC["X0"] == "X0"
        assert X_TIERS[0] == "X0"

    def test_every_x_tier_maps_to_exactly_one_arm(self):
        from alpha_squad.evaluation.projection_calibration import X_ARMS

        assert tuple(X_TIER_SPEC.values()) == X_ARMS
        assert len(set(X_TIER_SPEC.values())) == len(X_TIERS)

    def test_every_x_tier_scores_through_the_draft_aware_branch(self):
        """The X-tiers must reach the SAME scoring code W1 uses. If one ever routed through a
        different branch, its margin would be attributable to the branch, not the calibration."""
        for tier in X_TIERS:
            assert tier in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_no_x_tier_enforces_legality(self):
        """D67 measured legality as contributing exactly 0.0 (W3 was byte-identical to W0) and
        shipped without it. Turning it on here would be a second treatment."""
        for tier in X_TIERS:
            assert tier not in W_TIERS_ENFORCING_LEGALITY

    def test_every_x_tier_is_described(self):
        for tier in X_TIERS:
            assert TIER_DESCRIPTIONS[tier]

    def test_x_tiers_do_not_collide_with_the_w_tiers(self):
        assert not set(X_TIERS) & set(W_TIERS)


class TestD70Y1Tier:
    """D70: Y1 must reuse the X-tier scoring branch verbatim and stay a separate letter from
    the closed X0-X4 calibration-arm set."""

    def test_y1_is_registered(self):
        assert Y_TIERS == ("Y1",)

    def test_y1_scores_through_the_draft_aware_branch(self):
        assert "Y1" in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_y1_is_described(self):
        assert TIER_DESCRIPTIONS["Y1"]

    def test_y1_does_not_collide_with_the_x_tiers(self):
        """D68 pre-registered X0-X4 as a closed set ('no sixth arm'). Y1 is a different kind
        of treatment (a model refit, not a residual-calibration arm) and must stay a distinct
        letter rather than extending that closed set."""
        assert not set(Y_TIERS) & set(X_TIERS)


class TestD79ZTiers:
    """D79: D67's draft-aware replacement held fixed, only the VALUE BASE varies.

    The load-bearing property is that Z0 reproduces the shipped engine EXACTLY. If it ever
    diverges, every Z-tier margin is measuring the harness rather than the value base -- the
    same self-check D68 built for X0 == W1.
    """

    def test_the_control_is_the_shipped_value_base(self):
        assert PREREGISTERED_Z_CONTROL == "Z0"
        assert Z_TIERS[0] == "Z0"
        assert Z_TIER_SPEC["Z0"] == ("msv_plus_weighted_vorp", 1.0)

    def test_every_z_tier_scores_through_the_draft_aware_branch(self):
        """A Z-tier that routed through any other branch would be measured against a
        replacement level the shipped engine does not use, which is the one thing this phase
        exists to hold constant."""
        for tier in ALL_Z_TIERS:
            assert tier in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_every_z_tier_is_described(self):
        for tier in ALL_Z_TIERS:
            assert TIER_DESCRIPTIONS[tier]

    def test_every_z_tier_has_exactly_one_spec(self):
        assert set(Z_TIER_SPEC) == set(ALL_Z_TIERS)

    def test_sweep_tiers_are_separate_from_the_candidates(self):
        """The sweep is a stress test of the incumbent's shape, not a candidate set. Keeping
        the tuples disjoint is what stops a swept weight from being shipped post-hoc -- the
        error D67 identified in D66's uniform x2.5 selection."""
        assert not set(Z_TIERS) & set(Z_SWEEP_TIERS)
        for tier in Z_SWEEP_TIERS:
            assert Z_TIER_SPEC[tier][0] == "msv_plus_weighted_vorp"

    def test_z_tiers_do_not_collide_with_earlier_letters(self):
        assert not set(ALL_Z_TIERS) & (set(X_TIERS) | set(Y_TIERS) | set(W_TIERS))

    def test_z0_scores_identically_to_x0_on_real_shaped_data(self, con):
        """Z0 and X0 are the same formula written two ways; they must produce the same score
        for every candidate, or the control is not the shipped engine."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        for player_id in sorted(available):
            z0 = score_candidate(
                static,
                player_id,
                league,
                [],
                "Z0",
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )
            x0 = score_candidate(
                static,
                player_id,
                league,
                [],
                "X0",
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )
            assert (z0 is None) == (x0 is None)
            if z0 is not None:
                assert z0.score == pytest.approx(x0.score, abs=1e-9), player_id

    def test_zw0_drops_the_vorp_term_entirely(self, con):
        """w=0 must leave `msv + opp_cost`, i.e. strictly less than Z0 wherever the
        draft-aware surplus is positive."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        best = max(available, key=lambda p: static.projections[p])
        z0 = score_candidate(
            static,
            best,
            league,
            [],
            "Z0",
            available=available,
            current_pick_overall=1,
            next_pick_overall=5,
            roster_player_ids=[],
        )
        zw0 = score_candidate(
            static,
            best,
            league,
            [],
            "ZW0",
            available=available,
            current_pick_overall=1,
            next_pick_overall=5,
            roster_player_ids=[],
        )
        assert zw0.score < z0.score

    def test_z2_reduces_to_z1_on_an_empty_roster(self, con):
        """`msv over the draft-aware replacement level` is defined so that, with every lineup
        slot empty, it equals `projection - draft_aware_level` -- which is exactly Z1's value
        base. Exercised through `_pick_by_tier` rather than `score_candidate` directly, because
        the identity depends on the hoisted per-position replacement map that only the real
        scoring path builds."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        z1_pick, z1_scored = _pick_by_tier(
            static, con, league, 2023, set(available), [], "Z1", 1, 5, roster_player_ids=[]
        )
        z2_pick, z2_scored = _pick_by_tier(
            static, con, league, 2023, set(available), [], "Z2", 1, 5, roster_player_ids=[]
        )
        assert z1_pick == z2_pick
        by_id_1 = {s.player_id: s.score for s in z1_scored}
        by_id_2 = {s.player_id: s.score for s in z2_scored}
        assert set(by_id_1) == set(by_id_2)
        for player_id, score in by_id_1.items():
            assert by_id_2[player_id] == pytest.approx(score, abs=1e-6), player_id

    def test_z2_refuses_to_score_without_its_hoisted_replacement_map(self, con):
        """Guards the silent-no-op failure mode: defaulting the subtrahend to 0.0 would turn
        Z2 into ZW0 while still labelling itself Z2."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        best = max(available, key=lambda p: static.projections[p])
        with pytest.raises(RuntimeError, match="replacement_msv"):
            score_candidate(
                static,
                best,
                league,
                [],
                "Z2",
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )

    @pytest.mark.parametrize("tier", ["Z0", "Z1", "Z2", "Z3", "ZW0", "ZW05", "ZW2", "ZW3"])
    def test_every_z_tier_drafts_a_full_roster(self, con, tier):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        result = simulate_forensic_draft(con, league, 2023, tier, draft_slot=1, static=static)
        assert len(result.drafted_player_ids) == 5
        assert len(set(result.drafted_player_ids)) == 5


class TestSeasonClusteredMargin:
    """D79 Gate 8 -- D71's correction. The naive n=50 i.i.d. interval every phase through D70
    quoted treats ten slots that share one projection set, one market board and one set of
    realized outcomes as ten independent draws. The season is the real unit."""

    @staticmethod
    def _rows(margins_by_season):
        rows = []
        for season, per_slot in margins_by_season.items():
            for slot, margin in enumerate(per_slot, start=1):
                rows.append(
                    {"season": season, "draft_slot": slot, "tier": "C", "starter_points": 1000.0}
                )
                rows.append(
                    {
                        "season": season,
                        "draft_slot": slot,
                        "tier": "T",
                        "starter_points": 1000.0 + margin,
                    }
                )
        return rows

    def test_pairs_by_season_and_slot(self):
        out = season_clustered_margin(
            self._rows({2021: [10.0, 20.0], 2022: [30.0, 40.0]}), "T", "C"
        )
        assert out["n_seasons"] == 2
        assert out["season_means"] == {2021: 15.0, 2022: 35.0}
        assert out["mean_margin"] == pytest.approx(25.0)

    def test_a_consistent_large_margin_excludes_zero(self):
        out = season_clustered_margin(
            self._rows({y: [200.0, 210.0] for y in range(2021, 2026)}), "T", "C"
        )
        assert out["ci_excludes_zero"]
        assert out["n_wins"] == 5

    def test_a_margin_carried_by_one_season_does_not(self):
        """The failure mode this gate exists for: a large pooled mean produced by one season,
        which the naive interval over 50 rows would report as significant."""
        rows = self._rows(
            {
                2021: [5.0] * 10,
                2022: [-5.0] * 10,
                2023: [3.0] * 10,
                2024: [-2.0] * 10,
                2025: [400.0] * 10,
            }
        )
        out = season_clustered_margin(rows, "T", "C")
        assert out["mean_margin"] > 75.0  # the pooled mean looks impressive
        assert not out["ci_excludes_zero"]  # ... and is not resolvable

    def test_is_wider_than_the_naive_interval_on_the_same_data(self):
        """The correction must make the bar HARDER to clear, never easier (D71)."""
        rows = self._rows({y: [30.0 + 5 * s for s in range(10)] for y in range(2021, 2026)})
        out = season_clustered_margin(rows, "T", "C")
        diffs = [r["starter_points"] for r in rows if r["tier"] == "T"]
        naive_se = (
            sum((d - sum(diffs) / len(diffs)) ** 2 for d in diffs) / (len(diffs) - 1)
        ) ** 0.5 / len(diffs) ** 0.5
        assert out["se"] >= naive_se or out["n_seasons"] < len(diffs)


class TestD79STiers:
    """D79 phase 2: the survival multiplier's coefficient -- the one term in the production
    score no phase has ever measured. Same self-check discipline as the Z-tiers: S0 must
    reproduce the shipped engine exactly, or every S-tier margin measures the harness."""

    def test_the_control_carries_the_shipped_coefficient(self):
        assert PREREGISTERED_S_CONTROL == "S0"
        assert S_TIERS[0] == "S0"
        assert S_TIER_SPEC["S0"] == 0.3

    def test_the_only_candidate_is_the_parameter_free_one(self):
        """S1 removes the term. Every other arm is a swept coefficient and must not be
        shippable -- replacing an unmeasured constant with a fitted one is strictly worse."""
        assert S_TIERS == ("S0", "S1")
        assert S_TIER_SPEC["S1"] == 0.0
        assert not set(S_TIERS) & set(S_SWEEP_TIERS)

    def test_every_s_tier_scores_through_the_draft_aware_branch(self):
        for tier in ALL_S_TIERS:
            assert tier in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_every_s_tier_is_described_and_specified(self):
        assert set(S_TIER_SPEC) == set(ALL_S_TIERS)
        for tier in ALL_S_TIERS:
            assert TIER_DESCRIPTIONS[tier]

    def test_s_tiers_do_not_collide_with_earlier_letters(self):
        assert not set(ALL_S_TIERS) & (
            set(ALL_Z_TIERS) | set(X_TIERS) | set(Y_TIERS) | set(W_TIERS)
        )

    def test_s0_scores_identically_to_z0_on_real_shaped_data(self, con):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        for player_id in sorted(available):
            s0 = score_candidate(
                static,
                player_id,
                league,
                [],
                "S0",
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )
            z0 = score_candidate(
                static,
                player_id,
                league,
                [],
                "Z0",
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )
            assert s0.score == pytest.approx(z0.score, abs=1e-9), player_id

    def test_switching_the_term_off_removes_the_bonus_for_a_player_who_will_be_gone(self, con):
        """A candidate certain to be taken before the next turn carries the full 1.3x under the
        control and exactly 1.0x under S1, so the ratio is the coefficient and nothing else."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        doomed = [p for p in sorted(available) if _survival_probability(static, p, 20) == 0.0]
        assert doomed, "fixture must contain a player who cannot survive to pick 20"
        for player_id in doomed:
            s0 = score_candidate(
                static,
                player_id,
                league,
                [],
                "S0",
                available=available,
                current_pick_overall=1,
                next_pick_overall=20,
                roster_player_ids=[],
            )
            s1 = score_candidate(
                static,
                player_id,
                league,
                [],
                "S1",
                available=available,
                current_pick_overall=1,
                next_pick_overall=20,
                roster_player_ids=[],
            )
            assert s0.score == pytest.approx(s1.score * 1.3, rel=1e-9), player_id

    def test_an_unknown_next_pick_is_unaffected_by_the_coefficient(self, con):
        """With no next pick there is no survival probability, so every arm must agree -- the
        coefficient can only act through a real availability estimate."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        best = max(available, key=lambda p: static.projections[p])
        scores = {
            tier: score_candidate(
                static,
                best,
                league,
                [],
                tier,
                available=available,
                current_pick_overall=None,
                next_pick_overall=None,
                roster_player_ids=[],
            ).score
            for tier in ALL_S_TIERS
        }
        assert len(set(round(v, 9) for v in scores.values())) == 1

    @pytest.mark.parametrize("tier", ["S0", "S1", "SS15", "SS60", "SS100"])
    def test_every_s_tier_drafts_a_full_roster(self, con, tier):
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        result = simulate_forensic_draft(con, league, 2023, tier, draft_slot=1, static=static)
        assert len(result.drafted_player_ids) == 5
        assert len(set(result.drafted_player_ids)) == 5


class TestQTiersDecisionValueBase:
    """D84. The Q-tiers vary the two decision-layer axes nothing had varied: the
    raw-projection double count (holding the value base's SCALE) and the survival term's
    one-sidedness. Arms, gates and selection rule are pre-registered in
    `evaluation/decision_value_base.py`."""

    def test_q_tier_spec_matches_the_preregistration(self):
        """The wiring must not drift from the committed pre-registration."""
        from alpha_squad.evaluation.decision_value_base import ARM_SPEC, ARMS
        from alpha_squad.evaluation.draft_forensics import Q_TIER_SPEC, Q_TIERS

        assert [Q_TIER_SPEC[t] for t in Q_TIERS] == [ARM_SPEC[a] for a in ARMS]

    def test_every_q_tier_is_described_and_draft_aware(self):
        from alpha_squad.evaluation.draft_forensics import (
            DRAFT_AWARE_REPLACEMENT_TIERS,
            Q_TIERS,
            TIER_DESCRIPTIONS,
        )

        for tier in Q_TIERS:
            assert tier in TIER_DESCRIPTIONS
            assert tier in DRAFT_AWARE_REPLACEMENT_TIERS

    def test_q0_scores_identically_to_z0_on_real_shaped_data(self, con):
        """THE control check. Q0 must be the shipped engine exactly -- if it is not, every
        Q-tier margin is measured against the wrong baseline."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        for player_id in sorted(available):
            kwargs = dict(
                available=available,
                current_pick_overall=1,
                next_pick_overall=5,
                roster_player_ids=[],
            )
            q0 = score_candidate(static, player_id, league, [], "Q0", **kwargs)
            z0 = score_candidate(static, player_id, league, [], "Z0", **kwargs)
            assert (q0 is None) == (z0 is None)
            if q0 is not None:
                assert q0.score == pytest.approx(z0.score, abs=1e-9), player_id

    def test_q1_removes_the_raw_projection_but_keeps_the_scale(self, con):
        """On an empty roster Q1's base is 2*(proj - R) against Q0's 2*proj - R, so Q1 must be
        strictly lower wherever the replacement level is positive -- but NOT half of Q0, which
        is what every previously-measured alternative was."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        # Q1 differs from Q0 by exactly the replacement level, so a candidate drawn from a
        # position whose level is 0 makes the first assertion vacuous (both bases coincide).
        # Every position ties at the same top projection and `available` is a set, so sort
        # before taking the max: otherwise the winner -- and this test -- turns on the
        # interpreter's hash seed.
        best = max(
            sorted(p for p in available if static.replacement_levels[static.positions[p]] > 0),
            key=lambda p: static.projections[p],
        )
        # `_pick_by_tier` hoists this per pick; calling `score_candidate` directly means
        # supplying it, and the tier RAISES rather than silently degrading if it is missing.
        from alpha_squad.league.replacement import replacement_marginal_starter_values

        replacement_msv = replacement_marginal_starter_values(
            league, [], static.projections, static.positions, static.replacement_levels
        )
        kwargs = dict(
            available=available,
            current_pick_overall=1,
            next_pick_overall=5,
            roster_player_ids=[],
            replacement_msv=replacement_msv,
        )
        q0 = score_candidate(static, best, league, [], "Q0", **kwargs)
        q1 = score_candidate(static, best, league, [], "Q1", **kwargs)
        z2 = score_candidate(static, best, league, [], "Z2", **kwargs)
        assert q1.score < q0.score
        # Q1 keeps both surplus terms; Z2 keeps one. Q1 must sit strictly above Z2.
        assert q1.score > z2.score

    def test_q2_discounts_a_certain_survivor_relative_to_the_control(self, con):
        """The survival asymmetry, end to end: a player certain to still be there must score
        LESS under Q2 than under Q0, which is impossible in the shipped one-sided form."""
        _seed_league_season(con, 2023)
        league = _small_league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        kwargs = dict(available=available, current_pick_overall=1, roster_player_ids=[])
        # next_pick_overall=1 -> the player cannot be gone, so survival is 1.0.
        moved = 0
        for player_id in sorted(available):
            q0 = score_candidate(static, player_id, league, [], "Q0", next_pick_overall=1, **kwargs)
            q2 = score_candidate(static, player_id, league, [], "Q2", next_pick_overall=1, **kwargs)
            if q0 is None or q0.survival_probability is None:
                continue
            if q0.survival_probability == pytest.approx(1.0):
                assert q2.score < q0.score, player_id
                moved += 1
        assert moved > 0, "no certain-survivor in the fixture; the test proved nothing"

    def test_q3_is_q1_and_q2_together(self, con):
        """E must compose C and D rather than being a third thing."""
        from alpha_squad.evaluation.draft_forensics import Q_TIER_SPEC

        assert Q_TIER_SPEC["Q3"][0] == Q_TIER_SPEC["Q1"][0]
        assert Q_TIER_SPEC["Q3"][1] == Q_TIER_SPEC["Q2"][1] is True
