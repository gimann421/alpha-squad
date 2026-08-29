"""N-tier value-base ablation and the Stage 2 fair-opponent threading (docs/DECISIONS.md D63).

The engine has now shipped three different value bases (VORP at D55, marginal starter value at
D60, their sum at D63). These tests pin down the properties that decided between them, so a
future change has to confront the same evidence rather than rediscover it.
"""

from __future__ import annotations

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import (
    ALL_N_TIERS,
    N4_VORP_WEIGHT,
    N_TIER_SPEC,
    PREREGISTERED_MAX_ROUNDS_EARLIER,
    PREREGISTERED_MAX_WORSE_SEASONS,
    PREREGISTERED_N_CONTROL,
    PREREGISTERED_R_CONTROL,
    R2_TIGHTENED_OVER_CAP_MULTIPLIER,
    R_TIER_SPEC,
    R_TIERS,
    R_TIERS_CAPACITY_TIEBREAK,
    evaluate_preregistered_gates,
    first_round_by_position,
    leave_one_season_out_margins,
    load_season_static,
    simulate_forensic_draft,
    summarize_tier_ablation,
)
from alpha_squad.evaluation.draft_simulation import (
    MARKET_CONSENSUS,
    MARKET_CONSENSUS_ROSTER_AWARE,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import DRAFT_VORP_WEIGHT
from alpha_squad.league.replacement import (
    marginal_starter_value,
    replacement_marginal_starter_values,
)
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
        format="dynasty",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1},
        roster={"bench": 1, "roster_size": 5},
    )
    base.update(overrides)
    return LeagueContext(**base)


def _seed(con, season=2023, n_per_position=6):
    rank = 1
    for position in ("QB", "RB", "WR", "TE"):
        for i in range(n_per_position):
            pid = f"{position}_{i}"
            points = 300.0 - i * 20
            con.execute(
                """
                INSERT INTO uncertainty_predictions
                    (prediction_id, player_id, season, position, model_version, feature_version,
                     point_prediction, top12_prob, top24_prob, confidence, calibration_season,
                     predicted_at)
                VALUES (?, ?, ?, ?, ?, 'test_v1', ?, 0.2, 0.4, 0.8, ?, current_timestamp)
                """,
                [
                    f"pred_{pid}",
                    pid,
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
                [pid, season, position, points, points / 15],
            )
            con.execute(
                "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                "ecr_rank, ecr_best, ecr_worst, page_type) "
                "VALUES (?, ?, 'do', ?, ?, ?, ?, 'dynasty-overall')",
                [pid, f"{season}-08-01", position, float(rank), rank, rank + 3],
            )
            rank += 1


class TestReplacementMarginalStarterValues:
    """The N3 building block: `msv - this` is marginal starter value OVER REPLACEMENT."""

    def test_reduces_to_vorp_exactly_on_an_empty_roster(self):
        """The defining property. On an empty roster both the candidate and a
        replacement-level body enter the lineup outright, so the difference is exactly
        projection - replacement_level, i.e. VORP."""
        league = _league(lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DEF": 1})
        proj = {"qb1": 300.0, "rb1": 250.0, "wr1": 240.0}
        pos = {"qb1": "QB", "rb1": "RB", "wr1": "WR"}
        levels = {"QB": 200.0, "RB": 100.0, "WR": 90.0, "TE": 80.0, "K": 120.0, "DST": 110.0}

        repl = replacement_marginal_starter_values(league, [], proj, pos, levels)
        for pid, position in pos.items():
            msv = marginal_starter_value(league, [], pid, proj, pos)
            assert msv - repl[position] == pytest.approx(proj[pid] - levels[position])

    def test_collapses_to_zero_at_a_saturated_position(self):
        """The other defining property, and the one VORP lacks: once a position cannot start
        another body, a candidate there is worth exactly what a free waiver body is worth."""
        league = _league(lineup={"QB": 1, "RB": 1, "WR": 1})
        proj = {"qb_start": 400.0, "qb_extra": 350.0}
        pos = {"qb_start": "QB", "qb_extra": "QB"}
        levels = {"QB": 100.0, "RB": 90.0, "WR": 80.0}

        roster = ["qb_start"]
        repl = replacement_marginal_starter_values(league, roster, proj, pos, levels)
        msv = marginal_starter_value(league, roster, "qb_extra", proj, pos)
        assert msv - repl["QB"] == pytest.approx(0.0)
        # VORP, by contrast, still prices the unusable backup well above replacement -- the
        # exact blind spot D60 set out to fix.
        assert proj["qb_extra"] - levels["QB"] == pytest.approx(250.0)

    def test_is_computed_per_position_not_per_candidate(self):
        league = _league(lineup={"QB": 1, "RB": 1, "WR": 1})
        proj = {"a": 100.0}
        pos = {"a": "QB"}
        levels = {"QB": 10.0, "RB": 20.0, "WR": 30.0}
        assert set(replacement_marginal_starter_values(league, [], proj, pos, levels)) == {
            "QB",
            "RB",
            "WR",
        }


class TestNTierHarnessSelfChecks:
    """N0 and N1 are the two already-shipped formulas re-expressed in the N-tier code path.
    They must reproduce their M-tier equivalents exactly, or the N-tier comparison is not
    measuring what it claims to."""

    def test_n0_reproduces_m3_the_shipped_d60_formula(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        n0 = simulate_forensic_draft(con, league, 2023, "N0", 1, static)
        m3 = simulate_forensic_draft(con, league, 2023, "M3", 1, static)
        assert n0.drafted_player_ids == m3.drafted_player_ids
        assert n0.starter_points == pytest.approx(m3.starter_points)

    def test_n1_reproduces_m0_the_d55_vorp_formula(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        n1 = simulate_forensic_draft(con, league, 2023, "N1", 1, static)
        m0 = simulate_forensic_draft(con, league, 2023, "M0", 1, static)
        assert n1.drafted_player_ids == m0.drafted_player_ids

    def test_every_n_tier_has_a_spec_and_the_x_variants_disable_opportunity_cost(self):
        assert set(N_TIER_SPEC) == set(ALL_N_TIERS)
        for tier, (_, uses_opp) in N_TIER_SPEC.items():
            assert uses_opp is not tier.endswith("x")

    def test_production_and_the_ablation_share_one_vorp_weight(self):
        """The shipped blend and the tier that justified it must use the same number, or the
        measurement does not describe what users get."""
        assert DRAFT_VORP_WEIGHT == N4_VORP_WEIGHT


class TestForensicFairOpponent:
    """D63 Stage 2: the forensic harness ran its 9-slot field on the pre-D61 unaware consensus,
    so an M-tier re-run would have re-measured the artifact D61 identified."""

    def test_opponent_strategy_is_recorded_on_the_result(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        r = simulate_forensic_draft(
            con, league, 2023, "N0", 1, static, opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE
        )
        assert r.opponent_strategy == MARKET_CONSENSUS_ROSTER_AWARE

    def test_default_opponent_stays_the_published_one_for_reproducibility(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        default = simulate_forensic_draft(con, league, 2023, "N0", 1, static)
        explicit = simulate_forensic_draft(
            con, league, 2023, "N0", 1, static, opponent_strategy=MARKET_CONSENSUS
        )
        assert default.opponent_strategy == MARKET_CONSENSUS
        assert default.drafted_player_ids == explicit.drafted_player_ids

    def test_rejects_an_unknown_opponent_strategy(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        with pytest.raises(ValueError, match="opponent"):
            simulate_forensic_draft(
                con, league, 2023, "N0", 1, static, opponent_strategy="not_a_real_field"
            )


class TestGateMetrics:
    def test_first_round_by_position_reads_off_pick_order(self):
        assert first_round_by_position(["WR", "QB", "WR", "RB"]) == {"WR": 1, "QB": 2, "RB": 4}

    def test_a_position_never_drafted_is_absent_rather_than_given_a_sentinel(self):
        """Averaging a made-up round in would misreport timing, which is what Gate 4 checks."""
        assert "K" not in first_round_by_position(["WR", "QB"])

    def test_leave_one_season_out_excludes_exactly_one_season(self):
        rows = [
            {"season": s, "tier": t, "starter_points": pts}
            for s, t, pts in [
                (2021, "A", 100.0),
                (2021, "B", 90.0),
                (2022, "A", 100.0),
                (2022, "B", 90.0),
                (2023, "A", 100.0),
                (2023, "B", 50.0),
            ]
        ]
        margins = leave_one_season_out_margins(rows, "A", "B")
        assert set(margins) == {2021, 2022, 2023}
        # Dropping 2023 removes B's bad season, so A's edge shrinks to 10.
        assert margins[2023] == pytest.approx(10.0)

    def test_gates_block_a_tier_that_wins_the_pooled_mean_on_one_season(self):
        """Gate 3's whole purpose: with only 5 real seasons, one outlier can carry a pooled
        mean. Such a tier must not ship."""
        summary = [
            {
                "tier": "ctrl",
                "mean_starter_points": 100.0,
                "mean_starter_points_by_season": {2021: 100.0, 2022: 100.0, 2023: 100.0},
                "zero_rate_by_position": {"RB": 0},
                "n_infeasible_rosters": 0,
                "mean_first_round_by_position": {"RB": 3.0},
            },
            {
                "tier": "spiky",
                "mean_starter_points": 110.0,
                "mean_starter_points_by_season": {2021: 90.0, 2022: 90.0, 2023: 150.0},
                "zero_rate_by_position": {"RB": 0},
                "n_infeasible_rosters": 0,
                "mean_first_round_by_position": {"RB": 3.0},
            },
        ]
        rows = [
            {"season": s, "tier": t, "starter_points": p}
            for t, per_season in (
                ("ctrl", {2021: 100.0, 2022: 100.0, 2023: 100.0}),
                ("spiky", {2021: 90.0, 2022: 90.0, 2023: 150.0}),
            )
            for s, p in per_season.items()
        ]
        verdict = evaluate_preregistered_gates(summary, rows, "ctrl")[0]
        assert verdict["beats_primary_metric"] is True
        assert verdict["gate3_pass"] is False
        assert verdict["ships"] is False

    def test_gate4_blocks_reaching_for_a_position_far_earlier_than_the_control(self):
        """The gate that would have caught D60's K/DST timing regression."""
        common = {
            "zero_rate_by_position": {"K": 0},
            "n_infeasible_rosters": 0,
            "mean_starter_points_by_season": {2021: 100.0},
        }
        summary = [
            {
                "tier": "ctrl",
                "mean_starter_points": 100.0,
                "mean_first_round_by_position": {"K": 14.0},
                **common,
            },
            {
                "tier": "reacher",
                "mean_starter_points": 120.0,
                "mean_first_round_by_position": {"K": 14.0 - PREREGISTERED_MAX_ROUNDS_EARLIER - 1},
                **common,
            },
        ]
        rows = [
            {"season": 2021, "tier": "ctrl", "starter_points": 100.0},
            {"season": 2021, "tier": "reacher", "starter_points": 120.0},
        ]
        verdict = evaluate_preregistered_gates(summary, rows, "ctrl")[0]
        assert verdict["gate4_pass"] is False
        assert verdict["ships"] is False

    def test_summary_reports_every_metric_the_rule_needs(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        rows = []
        for tier in ("N0", "N4"):
            r = simulate_forensic_draft(
                con,
                league,
                2023,
                tier,
                1,
                static,
                opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
            )
            rows.append(
                {
                    "season": 2023,
                    "tier": tier,
                    "draft_slot": 1,
                    "opponent_strategy": r.opponent_strategy,
                    "starter_points": r.starter_points,
                    "total_roster_points": r.total_roster_points,
                    "drafted_positions": list(r.drafted_positions),
                    "first_round_by_position": first_round_by_position(r.drafted_positions),
                    "zero_drafted_starting_positions": [],
                    "max_single_position_share": 0.5,
                }
            )
        summary = summarize_tier_ablation(rows, league)
        for row in summary:
            for field in (
                "mean_starter_points_by_season",
                "mean_first_round_by_position",
                "late_round_position_counts_per_draft",
                "opponent_strategy",
            ):
                assert field in row


class TestPreRegistrationIsPinned:
    """These constants are the pre-registered rule. A change to any of them changes what
    "ships" means, so it must be a deliberate, reviewed edit rather than a silent drift."""

    def test_control_and_thresholds_are_what_was_registered(self):
        assert PREREGISTERED_N_CONTROL == "N0"
        assert PREREGISTERED_MAX_WORSE_SEASONS == 1
        assert PREREGISTERED_MAX_ROUNDS_EARLIER == 2.0
        assert N4_VORP_WEIGHT == 1.0


class TestRTierHarness:
    """D64: the kicker-hoarding refinement tiers. R0 must reproduce the shipped engine, or the
    whole comparison is measuring something other than production."""

    def test_r0_reproduces_n4_the_shipped_engine(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        r0 = simulate_forensic_draft(con, league, 2023, "R0", 1, static)
        n4 = simulate_forensic_draft(con, league, 2023, "N4", 1, static)
        assert r0.drafted_player_ids == n4.drafted_player_ids
        assert r0.starter_points == pytest.approx(n4.starter_points)

    def test_control_is_r0_and_only_r1_r3_r4_apply_saturation(self):
        assert PREREGISTERED_R_CONTROL == "R0"
        assert set(R_TIER_SPEC) == set(R_TIERS)
        assert R_TIER_SPEC["R0"] == (False, 0.1)
        assert {t for t, (sat, _) in R_TIER_SPEC.items() if sat} == {"R1", "R3", "R4"}
        assert {
            t for t, (_, m) in R_TIER_SPEC.items() if m == R2_TIGHTENED_OVER_CAP_MULTIPLIER
        } == {
            "R2",
            "R3",
        }

    def test_every_r_tier_is_deterministic_across_repeat_runs(self, con):
        """The R4 tie-break changes the sort key, so determinism has to be re-established for
        it specifically (D54): `player_id` stays the final key."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        for tier in R_TIERS:
            first = simulate_forensic_draft(con, league, 2023, tier, 1, static)
            for _ in range(2):
                again = simulate_forensic_draft(con, league, 2023, tier, 1, static)
                assert again.drafted_player_ids == first.drafted_player_ids

    def test_r4_is_the_capacity_tiebreak_tier_and_scores_like_r1(self):
        """R4 changes ONLY the tie-break, never the score, so its scoring spec matches R1's."""
        assert R_TIERS_CAPACITY_TIEBREAK == ("R4",)
        assert R_TIER_SPEC["R4"][0] == R_TIER_SPEC["R1"][0]
        assert R_TIER_SPEC["R4"][1] == R_TIER_SPEC["R1"][1]


class TestOverCapMultiplierCannotReorderUniformlyCappedCandidates:
    """The structural reason Hypothesis B was measured inert (D64), asserted directly rather
    than left as a narrative claim: the over-cap multiplier rescales candidates, and rescaling
    cannot reorder a set whose members all receive the same factor."""

    def test_a_shared_multiplier_preserves_ordering(self):
        """Real over-cap candidate scores from the traced 2023 slot-9 round-16 pick."""
        scores = [30.1, 17.2, 9.2, 4.1]
        for multiplier in (0.1, 0.01, 0.001):
            scaled = [s * multiplier for s in scores]
            # rank order is unchanged: strictly decreasing in, strictly decreasing out
            assert all(a > b for a, b in zip(scaled, scaled[1:], strict=False))
            assert scaled.index(max(scaled)) == scores.index(max(scores))

    def test_no_positive_multiplier_lifts_a_non_positive_score_above_a_positive_one(self):
        """Why B cannot fix the third kicker: at that pick every skill alternative is at or
        below replacement (measured: RB -135.6, WR -123.0), so its score is <= 0 while the
        kicker's is positive. Scaling the kicker DOWN never makes it lose to a <= 0 score."""
        kicker, best_alternative = 0.84, 0.0
        for multiplier in (0.1, 0.01, 1e-9):
            assert kicker * multiplier > best_alternative
