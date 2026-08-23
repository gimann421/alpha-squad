"""Unit tests for the evidence engine's pure-DB logic: taxonomy, event recording, the
bounded prior-update adjustment, and the EDGE evidence-score wiring. The detectors in
evidence/events.py read real snapshot files (like market/consensus.py, market/dynasty_values.py)
and are covered by the live network test instead, per the codebase's existing convention."""

from __future__ import annotations

import json

import duckdb
import pytest

from alpha_squad.evidence.events import record_event
from alpha_squad.evidence.prior_update import (
    MAX_ADJUSTMENT_PCT,
    aggregate_evidence,
    apply_evidence_adjustment,
    evidence_score_for_action,
    run_prior_update,
)
from alpha_squad.evidence.taxonomy import MEDIUM, STRONG, WEAK, strength_for
from alpha_squad.storage.db import init_db


class TestTaxonomy:
    def test_strong_event_types_map_to_strong_label_and_high_score(self):
        label, score = strength_for("depth_chart_promotion")
        assert label == STRONG
        assert score == pytest.approx(0.9)

    def test_medium_and_weak_vocabulary_is_registered_even_without_a_detector(self):
        assert strength_for("coach_comment")[0] == MEDIUM
        assert strength_for("social_media_buzz")[0] == WEAK

    def test_unregistered_event_type_is_refused_not_defaulted(self):
        with pytest.raises(ValueError, match="unregistered"):
            strength_for("made_up_event_type")


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


class TestRecordEvent:
    def test_record_event_derives_strength_from_taxonomy(self, con):
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="depth_chart_promotion",
            source="test",
            direction=1,
            structured_impact={"prior_rank": 2, "new_rank": 1},
            summary="test promotion",
        )
        row = con.execute(
            "SELECT strength_label, strength, direction FROM evidence_events WHERE player_id='p1'"
        ).fetchone()
        assert row == ("STRONG", pytest.approx(0.9), 1)

    def test_record_event_is_idempotent_on_identical_input(self, con):
        kwargs = dict(
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="roster_transaction",
            source="test",
            direction=0,
            structured_impact={"prior_team": "KC", "new_team": "SF"},
            summary="traded",
        )
        record_event(con, **kwargs)
        record_event(con, **kwargs)
        n = con.execute("SELECT count(*) FROM evidence_events WHERE player_id='p1'").fetchone()[0]
        assert n == 1


class TestAggregateEvidence:
    def test_sums_strength_times_direction_across_events(self, con):
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="depth_chart_promotion",
            source="t",
            direction=1,
            structured_impact={},
            summary="promo",
        )
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="injury_own_status",
            source="t",
            direction=-1,
            structured_impact={},
            summary="questionable",
        )
        # STRONG=0.9 each: +0.9 (promotion) + (-0.9) (own injury) nets to 0.0.
        score, detail = aggregate_evidence(con, "p1", 2024, 5)
        assert score == pytest.approx(0.0)
        assert len(detail) == 2

    def test_clips_to_bounded_range(self, con):
        for i in range(5):
            record_event(
                con,
                player_id="p1",
                season=2024,
                week=5,
                event_date="2024-10-01",
                event_type="depth_chart_promotion",
                source="t",
                direction=1,
                structured_impact={"i": i},
                summary=f"promo{i}",
            )
        score, _ = aggregate_evidence(con, "p1", 2024, 5)
        assert score == pytest.approx(1.0)

    def test_no_events_returns_zero_and_empty_detail(self, con):
        score, detail = aggregate_evidence(con, "nobody", 2024, 5)
        assert score == 0.0
        assert detail == []


class TestApplyEvidenceAdjustment:
    def test_returns_none_when_no_base_projection_exists(self, con):
        assert apply_evidence_adjustment(con, "p1", 2024, 5) is None

    def test_no_evidence_leaves_projection_unadjusted(self, con):
        con.execute(
            "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        delta = apply_evidence_adjustment(con, "p1", 2024, 5)
        assert delta.adjusted_value == pytest.approx(10.0)
        assert delta.adjustment_pct == pytest.approx(0.0)
        assert "unadjusted" in delta.reason

    def test_adjustment_is_bounded_even_with_overwhelming_bullish_evidence(self, con):
        con.execute(
            "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        for i in range(10):
            record_event(
                con,
                player_id="p1",
                season=2024,
                week=5,
                event_date="2024-10-01",
                event_type="depth_chart_promotion",
                source="t",
                direction=1,
                structured_impact={"i": i},
                summary=f"promo{i}",
            )
        delta = apply_evidence_adjustment(con, "p1", 2024, 5)
        assert delta.adjustment_pct == pytest.approx(MAX_ADJUSTMENT_PCT)
        assert delta.adjusted_value == pytest.approx(10.0 * (1 + MAX_ADJUSTMENT_PCT))
        assert delta.evidence_ids

    def test_bearish_evidence_lowers_the_projection(self, con):
        con.execute(
            "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="injury_own_status",
            source="t",
            direction=-1,
            structured_impact={},
            summary="questionable",
        )
        delta = apply_evidence_adjustment(con, "p1", 2024, 5)
        assert delta.adjusted_value < 10.0
        assert delta.adjustment_pct < 0

    def test_never_mutates_the_base_weekly_projection_row(self, con):
        """Regression test for the Gate 6b requirement: evidence never directly overwrites
        model output. weekly_projection_snapshot must be byte-identical before and after."""
        con.execute(
            "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        for i in range(10):
            record_event(
                con,
                player_id="p1",
                season=2024,
                week=5,
                event_date="2024-10-01",
                event_type="depth_chart_promotion",
                source="t",
                direction=1,
                structured_impact={"i": i},
                summary=f"promo{i}",
            )
        apply_evidence_adjustment(con, "p1", 2024, 5)
        base_after = con.execute(
            "SELECT predicted_points FROM weekly_projection_snapshot WHERE player_id='p1'"
        ).fetchone()[0]
        assert base_after == pytest.approx(10.0)

    def test_material_changes_have_a_traceable_reason_and_evidence_ids(self, con):
        con.execute(
            "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
            "VALUES ('p1', 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)"
        )
        event_id = record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="depth_chart_promotion",
            source="t",
            direction=1,
            structured_impact={"prior_rank": 2, "new_rank": 1},
            summary="RB1 promoted",
        )
        delta = apply_evidence_adjustment(con, "p1", 2024, 5)
        assert delta.reason
        assert "depth_chart_promotion" in delta.reason
        assert event_id in delta.evidence_ids

        stored = con.execute(
            "SELECT reason, evidence_ids_json FROM projection_deltas WHERE player_id='p1'"
        ).fetchone()
        assert stored[0] == delta.reason
        assert json.loads(stored[1]) == [event_id]

    def test_run_prior_update_processes_every_player_with_a_base_projection(self, con):
        for pid in ("p1", "p2", "p3"):
            con.execute(
                "INSERT INTO weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points, built_at) "
                "VALUES (?, 2024, 5, 'ml_catboost', 'WR', 10.0, current_timestamp)",
                [pid],
            )
        deltas = run_prior_update(con, 2024, 5)
        assert {d.player_id for d in deltas} == {"p1", "p2", "p3"}


class TestEvidenceScoreForAction:
    def test_no_lean_is_always_neutral(self, con):
        assert evidence_score_for_action(con, "p1", 2024, action_sign=0) == pytest.approx(0.5)

    def test_no_evidence_before_season_start_is_neutral(self, con):
        # A real in-season event (week 5, October) does not count toward the preseason
        # EDGE's evidence score -- the honest D23 behavior: evidence and preseason EDGE are
        # different horizons in practice.
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=5,
            event_date="2024-10-01",
            event_type="depth_chart_promotion",
            source="t",
            direction=1,
            structured_impact={},
            summary="promo",
        )
        assert evidence_score_for_action(con, "p1", 2024, action_sign=1) == pytest.approx(0.5)

    def test_offseason_evidence_before_the_cutoff_moves_the_score(self, con):
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=1,
            event_date="2024-07-01",
            event_type="roster_transaction",
            source="t",
            direction=1,
            structured_impact={},
            summary="signed as starter",
        )
        # roster_transaction is registered STRONG=0.9; agreeing with a bullish (+1) lean.
        score = evidence_score_for_action(con, "p1", 2024, action_sign=1)
        assert score > 0.5
        # A bearish lean against the same bullish evidence should score below neutral.
        opposing = evidence_score_for_action(con, "p1", 2024, action_sign=-1)
        assert opposing < 0.5
        assert score + opposing == pytest.approx(1.0)

    def test_august_evidence_counts_when_no_real_week1_date_is_known(self, con):
        """Regression test (docs/DECISIONS.md D32): the cutoff used to be hardcoded to
        August 1st despite this function's own docstring promising "before that season's own
        Week 1" -- real NFL Week 1 dates fall in early September (2023-09-07, 2024-09-05,
        2025-09-04), so real August evidence (the entire preseason/training-camp window) was
        being silently excluded. With no `games` row for the season (as here), the fallback
        cutoff is now September 1st, not August 1st."""
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=1,
            event_date="2024-08-15",
            event_type="roster_transaction",
            source="t",
            direction=1,
            structured_impact={},
            summary="signed as starter in August",
        )
        score = evidence_score_for_action(con, "p1", 2024, action_sign=1)
        assert score > 0.5, "August evidence must count toward the preseason evidence score"

    def test_real_week1_game_date_takes_priority_over_the_fallback(self, con):
        """When the season's real Week 1 has been ingested, the cutoff uses that real date
        instead of the September 1st fallback -- evidence dated on/after the real Week 1
        kickoff must not count, even if the fallback constant would have allowed it."""
        con.execute(
            "INSERT INTO games (game_id, season, week, game_type, game_date, home_team, away_team) "
            "VALUES ('2024_01_AAA_BBB', 2024, 1, 'REG', '2024-09-05', 'AAA', 'BBB')"
        )
        record_event(
            con,
            player_id="p1",
            season=2024,
            week=1,
            event_date="2024-08-20",
            event_type="roster_transaction",
            source="t",
            direction=1,
            structured_impact={},
            summary="before the real week 1 kickoff",
        )
        record_event(
            con,
            player_id="p2",
            season=2024,
            week=1,
            event_date="2024-09-05",
            event_type="roster_transaction",
            source="t",
            direction=1,
            structured_impact={},
            summary="on the real week 1 kickoff date itself",
        )
        assert evidence_score_for_action(con, "p1", 2024, action_sign=1) > 0.5
        assert evidence_score_for_action(con, "p2", 2024, action_sign=1) == pytest.approx(0.5)
