"""Persists a recommendation into `decisions`, mirroring AGENT_CONTRACTS.md's Decision
contract. Kept separate from league/draft.py, waiver.py, trade.py so those stay
side-effect-free and unit-testable; the CLI layer calls this at the point a recommendation
is actually requested."""

from __future__ import annotations

import hashlib
import json

import duckdb

from alpha_squad.sources.base import utcnow


def _decision_id(decision_type: str, league_id: str, season: int, recommendation: str, built_at) -> str:
    digest = hashlib.md5(
        f"{decision_type}:{league_id}:{season}:{recommendation}:{built_at}".encode()
    ).hexdigest()[:16]
    return f"dec_{digest}"


def record_decision(
    con: duckdb.DuckDBPyConnection,
    decision_type: str,
    league_id: str,
    season: int,
    recommendation: str,
    alternatives: list[str],
    expected_value: float | None,
    confidence: float | None,
    reasons: list[str],
    provenance: dict,
) -> str:
    now = utcnow()
    decision_id = _decision_id(decision_type, league_id, season, recommendation, now)
    con.execute(
        """
        INSERT INTO decisions
            (decision_id, decision_type, league_id, season, recommendation, alternatives_json,
             expected_value, confidence, reasons_json, provenance_json, built_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            decision_id,
            decision_type,
            league_id,
            season,
            recommendation,
            json.dumps(alternatives),
            expected_value,
            confidence,
            json.dumps(reasons),
            json.dumps(provenance),
            now,
        ],
    )
    return decision_id
