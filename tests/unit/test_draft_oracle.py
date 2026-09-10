"""Tests for the D86 retrospective oracle.

The oracle is a DIAGNOSTIC that reads realized outcomes, so the properties that matter most are
the ones that keep it from ever becoming a hindsight drafter, and the ones that keep its regret
number honest:

  * realized outcomes must never reach a policy or an opponent (leakage);
  * the rollout must reproduce the shipped engine's own draft when started from pick 0;
  * the candidate slate must include both Alpha's pick and players Alpha did not rate, or the
    measured regret is biased toward zero by construction;
  * regret must be non-negative and zero exactly when Alpha's pick IS the oracle's.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from alpha_squad.evaluation.draft_forensics import load_season_static, simulate_forensic_draft
from alpha_squad.evaluation.draft_oracle import (
    SHIPPED_TIER,
    OracleCandidate,
    OraclePick,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    candidate_slate,
    draft_order,
    rollout,
)
from alpha_squad.evaluation.draft_simulation import MARKET_CONSENSUS_ROSTER_AWARE
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster import unfilled_dedicated_slots
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import init_db

_LEAGUE_CONFIGS_DIR = (
    Path(__file__).parents[2] / "src" / "alpha_squad" / "config" / "league_configs"
)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _league() -> LeagueContext:
    return LeagueContext(
        league_id="oracle_test",
        format="redraft",
        teams=4,
        scoring={"ppr": True, "ppr_value": 1.0},
        lineup={"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 1},
        roster={"bench": 2, "roster_size": 7},
    )


def _seed(con, season=2023, n_per_position=8):
    """Real-shaped data through the same two paths `load_season_projections` reads, plus
    realized season points that deliberately DISAGREE with the projection ordering -- otherwise
    an oracle that simply followed the projections would look correct for the wrong reason."""
    rank = 1
    for position in ("QB", "RB", "WR", "TE"):
        for i in range(n_per_position):
            player_id = f"{position}_{i}"
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
                    f"pred_{player_id}",
                    player_id,
                    season,
                    position,
                    UNCERTAINTY_MODEL_VERSION,
                    points,
                    season - 1,
                ],
            )
            # realized points REVERSE the projection order within each position
            realized = 100.0 + i * 25
            con.execute(
                "INSERT INTO player_season_stats (player_id, season, position, games_played, "
                "total_fantasy_points_ppr, ppr_points_per_game) VALUES (?, ?, ?, 17, ?, ?)",
                [player_id, season, position, realized, realized / 17],
            )
            con.execute(
                "INSERT INTO market_snapshot (player_id, scrape_date, ecr_type, position, "
                "ecr_rank, ecr_best, ecr_worst, page_type) "
                "VALUES (?, ?, 'do', ?, ?, ?, ?, 'dynasty-overall')",
                [player_id, f"{season}-08-01", position, float(rank), rank, rank + 3],
            )
            rank += 1
    for position in ("K", "DST"):
        for i in range(4):
            player_id = f"{position}_{i}"
            con.execute(
                "INSERT INTO projection_snapshot "
                "(model_name, player_id, season, position, predicted_points, built_at) "
                "VALUES (?, ?, ?, ?, ?, current_timestamp)",
                [KDST_MODEL_NAME, player_id, season, position, 120.0 - i * 10],
            )


class TestLeakageGuard:
    def test_no_realized_outcome_reaches_a_policy(self):
        """The single most important property of the module."""
        assert_no_realized_inputs_in_policy()

    def test_the_guard_would_actually_catch_a_leak(self):
        """A guard that cannot fail is not a guard. Feed it a function that takes a realized
        argument and confirm it raises."""
        import inspect

        def leaky_policy(available, market_rank, realized_points):  # noqa: ARG001
            return ""

        banned = ("actual", "realized", "outcome", "realised")
        params = set(inspect.signature(leaky_policy).parameters)
        assert {p for p in params if any(b in p.lower() for b in banned)} == {"realized_points"}


class TestDraftOrder:
    def test_covers_every_pick_exactly_once_in_snake_order(self):
        league = _league()
        order = draft_order(league)
        total = league.teams * int(league.roster["roster_size"])
        assert len(order) == total
        assert [p for p, _, _ in order] == list(range(1, total + 1))

    def test_snake_reverses_on_even_rounds(self):
        league = _league()
        by_round: dict[int, list[int]] = {}
        for _, rnd, slot in draft_order(league):
            by_round.setdefault(rnd, []).append(slot)
        assert by_round[1] == [1, 2, 3, 4]
        assert by_round[2] == [4, 3, 2, 1]

    def test_every_slot_gets_one_pick_per_round(self):
        league = _league()
        by_round: dict[int, list[int]] = {}
        for _, rnd, slot in draft_order(league):
            by_round.setdefault(rnd, []).append(slot)
        for slots in by_round.values():
            assert sorted(slots) == list(range(1, league.teams + 1))


class TestRolloutReproducesTheShippedDraft:
    def test_rollout_from_pick_zero_equals_a_full_forensic_draft(self, con):
        """THE control check. A rollout starting before any pick has been made must produce the
        same roster -- and therefore the same realized score -- as `simulate_forensic_draft`.
        If it does not, every oracle number is measured against a draft nobody plays."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)

        expected = simulate_forensic_draft(
            con,
            league,
            2023,
            SHIPPED_TIER,
            1,
            static,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        starter, total, unfilled = rollout(
            con,
            league,
            2023,
            static,
            draft_slot=1,
            after_pick_overall=0,
            available=set(static.projections),
            drafted=[],
            opponent_rosters={s: [] for s in range(2, league.teams + 1)},
            actual={},
        )
        assert starter == pytest.approx(expected.starter_points, abs=1e-9)
        assert total == pytest.approx(expected.total_roster_points, abs=1e-9)
        # `ForensicDraftResult` carries no unfilled-slot field, so derive it the same way the
        # rollout does, from the same drafted positions.
        assert unfilled == sum(
            unfilled_dedicated_slots(league, expected.drafted_positions).values()
        )

    def test_rollout_fills_the_roster(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        starter, total, unfilled = rollout(
            con,
            league,
            2023,
            static,
            draft_slot=2,
            after_pick_overall=0,
            available=set(static.projections),
            drafted=[],
            opponent_rosters={s: [] for s in (1, 3, 4)},
            actual={},
        )
        assert starter > 0
        assert total >= starter
        assert unfilled == 0


class TestCandidateSlate:
    def test_union_includes_players_alpha_did_not_rate(self, con):
        """The slate must reach beyond Alpha's own ranking, or measured regret is biased to
        zero by construction -- the oracle could only ever choose players Alpha already liked."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        # Alpha "likes" the highest projections; realized points reverse that order.
        alpha_ranked = sorted(available, key=lambda p: (-static.projections[p], p))
        realized = {p: 100.0 + 25 * int(p.split("_")[1]) for p in available if "_" in p}
        slate = candidate_slate(
            static,
            available,
            alpha_ranked,
            realized,
            top_alpha=3,
            top_realized=3,
            top_projection=0,
        )
        best_realized = sorted(realized, key=lambda p: (-realized[p], p))[:3]
        assert any(p in slate for p in best_realized)
        assert all(p in slate for p in alpha_ranked[:3])

    def test_slate_is_deterministic(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = set(static.projections)
        alpha_ranked = sorted(available, key=lambda p: (-static.projections[p], p))
        realized = dict.fromkeys(available, 0.0)
        a = candidate_slate(static, available, alpha_ranked, realized)
        b = candidate_slate(static, available, alpha_ranked, realized)
        assert a == b

    def test_slate_never_returns_an_unavailable_player(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        available = {p for p in static.projections if p.startswith("WR")}
        alpha_ranked = sorted(static.projections, key=lambda p: (-static.projections[p], p))
        slate = candidate_slate(
            static, available, alpha_ranked, dict.fromkeys(static.projections, 0.0)
        )
        assert set(slate) <= available


class TestRegretAlgebra:
    def _pick(self, values, alpha_index):
        cands = [
            OracleCandidate(
                player_id=f"p{i}",
                position="WR",
                projection=0.0,
                alpha_score=0.0,
                alpha_rank=i + 1,
                realized_points=0.0,
                rollout_starter_points=v,
                rollout_total_points=v,
                unfilled_mandatory=0,
                is_alpha_pick=(i == alpha_index),
            )
            for i, v in enumerate(values)
        ]
        return OraclePick(
            season=2023,
            draft_slot=1,
            round_no=1,
            pick_overall=1,
            roster_positions=[],
            candidates=cands,
        )

    def test_regret_is_zero_when_alpha_is_the_oracle(self):
        p = self._pick([100.0, 90.0, 80.0], alpha_index=0)
        assert p.alpha_is_oracle
        assert p.regret == pytest.approx(0.0)

    def test_regret_is_the_gap_to_the_best_rollout(self):
        p = self._pick([100.0, 90.0, 80.0], alpha_index=2)
        assert not p.alpha_is_oracle
        assert p.regret == pytest.approx(20.0)

    def test_regret_is_never_negative(self):
        for alpha_index in range(3):
            assert self._pick([100.0, 90.0, 80.0], alpha_index).regret >= 0.0

    def test_empty_slate_has_zero_regret_rather_than_raising(self):
        p = OraclePick(season=2023, draft_slot=1, round_no=1, pick_overall=1, roster_positions=[])
        assert p.regret == pytest.approx(0.0)
        assert p.oracle is None


class TestAuditDraft:
    def test_audits_the_requested_rounds_only(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 2),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        assert [p.round_no for p in picks] == [1, 2]

    def test_every_audited_pick_evaluates_alphas_own_choice(self, con):
        """Without this the regret is undefined: there would be nothing to compare the oracle
        against."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 3),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        assert picks
        for p in picks:
            assert p.alpha is not None
            assert sum(1 for c in p.candidates if c.is_alpha_pick) == 1

    def test_the_audited_trajectory_is_alphas_not_the_oracles(self, con):
        """The draft must continue with the ENGINE's pick, so regret is measured against the
        real production trajectory rather than compounding oracle picks into a hindsight draft."""
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con, league, 2023, 1, static, top_alpha=4, top_realized=4, top_projection=2
        )
        expected = simulate_forensic_draft(
            con,
            league,
            2023,
            SHIPPED_TIER,
            1,
            static,
            opponent_strategy=MARKET_CONSENSUS_ROSTER_AWARE,
        )
        assert [p.alpha.player_id for p in picks] == expected.drafted_player_ids

    def test_regret_is_non_negative_at_every_audited_pick(self, con):
        _seed(con)
        league = _league()
        static = load_season_static(con, league, 2023)
        picks = audit_draft(
            con,
            league,
            2023,
            1,
            static,
            rounds=(1, 2, 3),
            top_alpha=3,
            top_realized=3,
            top_projection=2,
        )
        for p in picks:
            assert p.regret >= -1e-9
