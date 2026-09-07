"""Bounded, explainable evidence-driven adjustment (ARCHITECTURE.md: "evidence never
directly overwrites model output"; PRODUCT_SPEC.md: "current information updates the prior;
it does not automatically override it"). Reads weekly_projection_snapshot (the real M5
established-ML weekly point prediction) and evidence_events, and writes a separate
projection_deltas row -- the base prediction is never mutated, only ever read."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta

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


def nfl_week1_date(season: int) -> date:
    """The date the NFL regular season opens, from the league's own scheduling rule: the
    Thursday after Labor Day (Labor Day being the first Monday in September).

    Not a heuristic and not a constant. It reproduces every real Week 1 date in the ingested
    history exactly -- 2015-09-10, 2016-09-08, 2017-09-07, 2018-09-06, 2019-09-05, 2020-09-10,
    2021-09-09, 2022-09-08, 2023-09-07, 2024-09-05, 2025-09-04 -- which
    `tests/unit/test_evidence.py` asserts rather than leaving to this comment."""
    september_first = date(season, 9, 1)
    # weekday(): Monday == 0. Days forward to the first Monday, then +3 to Thursday.
    labor_day = september_first + timedelta(days=(7 - september_first.weekday()) % 7)
    return labor_day + timedelta(days=3)


def _season_evidence_cutoff(con: duckdb.DuckDBPyConnection, season: int) -> str:
    """The date this season's own Week 1 starts.

    A season already ingested answers exactly, from its own `games` rows. A season that has NOT
    been played -- which is exactly the season a draft cares about -- used to fall back to a
    hardcoded `{season}-09-01`. That is wrong in the one direction that loses data: the opener
    is 4-11 September, so between 1 September and kickoff (precisely the week most redraft
    leagues draft in) every real preseason event -- trending adds, depth-chart moves, injuries
    -- fell on the wrong side of the cutoff and was silently dropped. Found by D78 running the
    live suite on 7 September 2026: a real Sleeper trending signal scored a flat 0.5, and the
    live test asserting evidence moves the score had been failing since 1 September.

    D32 fixed this same defect once already, replacing a hardcoded August 1st with a hardcoded
    September 1st. A third hand-picked constant would fail the same way again, so the unplayed
    case now uses the league's actual scheduling rule (`nfl_week1_date`) instead."""
    week1_date = con.execute(
        "SELECT min(game_date) FROM games WHERE season = ? AND week = 1", [season]
    ).fetchone()[0]
    if week1_date is not None:
        return str(week1_date)
    return nfl_week1_date(season).isoformat()


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
    ingested. For a season not yet played -- which is exactly the season a draft cares about --
    it is estimated from the ingested Week 1 history instead; see `_estimated_week1_date`.
    D32 found this function's own "before Week 1" claim didn't match a hardcoded August 1st
    cutoff, which silently excluded ~5 weeks of real preseason evidence; D78 found the
    September 1st replacement had the same defect three weeks later (see below)."""
    if action_sign == 0:
        return 0.5
    season_start = _season_evidence_cutoff(con, season)
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
