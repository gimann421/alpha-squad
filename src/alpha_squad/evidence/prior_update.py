"""Bounded, explainable evidence-driven adjustment (ARCHITECTURE.md: "evidence never
directly overwrites model output"; PRODUCT_SPEC.md: "current information updates the prior;
it does not automatically override it"). Reads weekly_projection_snapshot (the real M5
established-ML weekly point prediction) and evidence_events, and writes a separate
projection_deltas row -- the base prediction is never mutated, only ever read."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import duckdb

from alpha_squad.sources.base import utcnow

# Bounded: no single week's evidence adjustment can move a projection by more than this
# fraction, regardless of how much evidence accumulates -- evidence informs the prior, it
# does not get to dictate an unbounded rewrite of the model's own output.
MAX_ADJUSTMENT_PCT = 0.15


def _delta_id(player_id: str, season: int, week: int, base_model_name: str) -> str:
    digest = hashlib.md5(f"{player_id}:{season}:{week}:{base_model_name}".encode()).hexdigest()[:16]
    return f"delta_{digest}"


def aggregate_evidence(
    con: duckdb.DuckDBPyConnection, player_id: str, season: int, week: int
) -> tuple[float, list[dict]]:
    """Signed aggregate evidence for (player, season, week), clipped to [-1, 1]: sum of
    strength*direction across every event recorded for that target week. Every event that
    can reach this is already leakage-safe (events.py only ever dates evidence strictly
    before the week it informs), so no additional as-of filtering is needed here."""
    rows = con.execute(
        """
        SELECT event_id, strength, direction, event_type, summary
        FROM evidence_events WHERE player_id = ? AND season = ? AND week = ?
        """,
        [player_id, season, week],
    ).fetchall()
    if not rows:
        return 0.0, []
    raw = sum(strength * direction for _, strength, direction, _, _ in rows)
    bounded = max(-1.0, min(1.0, raw))
    detail = [
        {"event_id": r[0], "strength": r[1], "direction": r[2], "event_type": r[3], "summary": r[4]}
        for r in rows
    ]
    return bounded, detail


@dataclass
class ProjectionDelta:
    player_id: str
    season: int
    week: int
    base_model_name: str
    base_value: float
    adjusted_value: float
    adjustment_pct: float
    evidence_score: float
    reason: str
    evidence_ids: list[str]


def _store_delta(con: duckdb.DuckDBPyConnection, delta: ProjectionDelta) -> None:
    con.execute(
        """
        INSERT INTO projection_deltas
            (delta_id, player_id, season, week, base_model_name, base_value, adjusted_value,
             adjustment_pct, evidence_score, reason, evidence_ids_json, built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (player_id, season, week, base_model_name) DO UPDATE SET
            base_value = excluded.base_value, adjusted_value = excluded.adjusted_value,
            adjustment_pct = excluded.adjustment_pct, evidence_score = excluded.evidence_score,
            reason = excluded.reason, evidence_ids_json = excluded.evidence_ids_json,
            built_at = excluded.built_at
        """,
        [
            _delta_id(delta.player_id, delta.season, delta.week, delta.base_model_name),
            delta.player_id,
            delta.season,
            delta.week,
            delta.base_model_name,
            delta.base_value,
            delta.adjusted_value,
            delta.adjustment_pct,
            delta.evidence_score,
            delta.reason,
            json.dumps(delta.evidence_ids),
            utcnow(),
        ],
    )


def apply_evidence_adjustment(
    con: duckdb.DuckDBPyConnection,
    player_id: str,
    season: int,
    week: int,
    base_model_name: str = "ml_catboost",
) -> ProjectionDelta | None:
    base_row = con.execute(
        "SELECT predicted_points FROM weekly_projection_snapshot "
        "WHERE player_id = ? AND season = ? AND week = ? AND model_name = ?",
        [player_id, season, week, base_model_name],
    ).fetchone()
    if base_row is None:
        return None
    base_value = base_row[0]

    signed_score, detail = aggregate_evidence(con, player_id, season, week)
    adjustment_pct = signed_score * MAX_ADJUSTMENT_PCT
    adjusted_value = base_value * (1.0 + adjustment_pct)

    if detail:
        reason = f"Evidence-adjusted {adjustment_pct:+.1%}: " + "; ".join(
            f"{d['event_type']} ({d['summary']})" for d in detail
        )
    else:
        reason = "No evidence events recorded for this player/week; base projection unadjusted."

    delta = ProjectionDelta(
        player_id=player_id,
        season=season,
        week=week,
        base_model_name=base_model_name,
        base_value=base_value,
        adjusted_value=adjusted_value,
        adjustment_pct=adjustment_pct,
        evidence_score=abs(signed_score),
        reason=reason,
        evidence_ids=[d["event_id"] for d in detail],
    )
    _store_delta(con, delta)
    return delta


def evidence_score_for_action(
    con: duckdb.DuckDBPyConnection, player_id: str, season: int, action_sign: int
) -> float:
    """0-1: how much real structured evidence recorded *before that season's own Week 1*
    supports an action leaning `action_sign` (+1 bullish, -1 bearish, 0 no lean -> always
    neutral). 0.5 means no evidence, not a penalty -- evidence detectors (events.py) only
    ever produce in-season events starting week 2, so a preseason-anchored EDGE build
    (market/edge.py, D21) will honestly see no evidence yet for the season it is predicting;
    this is real, not a placeholder pretending otherwise, and is documented as D23.

    The cutoff uses that season's real Week 1 game date from `games` when it has been
    ingested (real NFL Week 1 dates run 2023-2025 fall in the first week of September, not
    August), falling back to September 1st -- a defensible early estimate, not "before Week 1"
    literally -- only for a season with no games ingested yet (a genuinely future/current
    season, like a preseason evidence build; D32 found the docstring's own "before Week 1"
    claim didn't match an earlier hardcoded August 1st cutoff, which silently excluded ~5
    weeks of real preseason evidence)."""
    if action_sign == 0:
        return 0.5
    week1_date = con.execute(
        "SELECT min(game_date) FROM games WHERE season = ? AND week = 1", [season]
    ).fetchone()[0]
    season_start = str(week1_date) if week1_date is not None else f"{season}-09-01"
    rows = con.execute(
        "SELECT strength, direction FROM evidence_events "
        "WHERE player_id = ? AND season = ? AND event_date < ?",
        [player_id, season, season_start],
    ).fetchall()
    if not rows:
        return 0.5
    raw = sum(strength * direction for strength, direction in rows)
    bounded = max(-1.0, min(1.0, raw))
    return 0.5 + 0.5 * bounded * action_sign


def run_prior_update(
    con: duckdb.DuckDBPyConnection, season: int, week: int, base_model_name: str = "ml_catboost"
) -> list[ProjectionDelta]:
    player_ids = con.execute(
        "SELECT DISTINCT player_id FROM weekly_projection_snapshot "
        "WHERE season = ? AND week = ? AND model_name = ?",
        [season, week, base_model_name],
    ).fetchall()
    deltas = []
    for (player_id,) in player_ids:
        delta = apply_evidence_adjustment(con, player_id, season, week, base_model_name)
        if delta is not None:
            deltas.append(delta)
    return deltas
