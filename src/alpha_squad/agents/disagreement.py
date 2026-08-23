"""Disagreement detection and resolution (AGENT_CONTRACTS.md's Orchestrator conflict
protocol): detect a real conflict between two already-computed, already-stored outputs,
classify it, resolve using validated evidence, and record BOTH positions -- the minority is
never silently discarded, only marked as resolved-against (`agent_disagreements`)."""

from __future__ import annotations

import hashlib

import duckdb

from alpha_squad.sources.base import utcnow

# Same materiality bar M8's EDGE gate already uses (D21) -- a real, already-established
# threshold for "this rank gap is meaningful," not a new arbitrary number.
RANK_DISAGREEMENT_THRESHOLD = 15
MAE_GAP_THRESHOLD = 5.0


def detect_model_vs_market_disagreements(
    con: duckdb.DuckDBPyConnection, season: int, ecr_type: str = "rsf"
) -> list[dict]:
    """Reuses M8's own already-computed rank_edge in edge_snapshot -- a real, stored
    disagreement between the model and the market -- rather than re-deriving a new
    comparison. Classified "market" per AGENT_CONTRACTS.md's disagreement-type taxonomy."""
    rows = con.execute(
        "SELECT player_id, model_rank, market_rank, rank_edge, confidence FROM edge_snapshot "
        "WHERE season = ? AND ecr_type = ? AND abs(rank_edge) >= ?",
        [season, ecr_type, RANK_DISAGREEMENT_THRESHOLD],
    ).fetchall()
    disagreements = []
    for player_id, model_rank, market_rank, rank_edge, confidence in rows:
        model_wins = (confidence or 0.0) >= 0.5
        majority_position, majority_value = (
            ("model", float(model_rank)) if model_wins else ("market", float(market_rank))
        )
        minority_position, minority_value = (
            ("market", float(market_rank)) if model_wins else ("model", float(model_rank))
        )
        disagreements.append(
            {
                "disagreement_type": "market",
                "subject": player_id,
                "season": season,
                "majority_position": majority_position,
                "majority_value": majority_value,
                "minority_position": minority_position,
                "minority_value": minority_value,
                "critique": (
                    f"rank_edge {rank_edge:+d} between model (rank {model_rank}) and market "
                    f"(rank {market_rank}); model confidence {confidence}"
                ),
            }
        )
    return disagreements


def detect_baseline_vs_ml_disagreements(
    con: duckdb.DuckDBPyConnection,
    season: int,
    position: str,
    mae_gap_threshold: float = MAE_GAP_THRESHOLD,
) -> list[dict]:
    """Compares the real, already-computed evaluation_results MAE for the ECR-implied
    baseline vs. the established-ML ensemble at the same season/position -- a real, stored
    disagreement about which approach is more trustworthy, classified "model"."""
    baseline = con.execute(
        "SELECT mae FROM evaluation_results WHERE model_name = 'baseline_ecr_implied' AND season = ? AND position = ?",
        [season, position],
    ).fetchone()
    ml = con.execute(
        "SELECT mae FROM evaluation_results WHERE model_name = ? AND season = ? AND position = ?",
        [f"ml_ensemble_{position.lower()}", season, position],
    ).fetchone()
    if baseline is None or ml is None:
        return []
    baseline_mae, ml_mae = baseline[0], ml[0]
    if abs(baseline_mae - ml_mae) < mae_gap_threshold:
        return []
    if ml_mae < baseline_mae:
        majority, majority_val = "ml_ensemble", ml_mae
        minority, minority_val = "baseline_ecr_implied", baseline_mae
    else:
        majority, majority_val = "baseline_ecr_implied", baseline_mae
        minority, minority_val = "ml_ensemble", ml_mae
    return [
        {
            "disagreement_type": "model",
            "subject": f"{position}/{season}",
            "season": season,
            "majority_position": majority,
            "majority_value": majority_val,
            "minority_position": minority,
            "minority_value": minority_val,
            "critique": f"MAE gap {abs(baseline_mae - ml_mae):.2f} exceeds {mae_gap_threshold} threshold",
        }
    ]


def _disagreement_id(disagreement_type: str, subject: str, season: int | None) -> str:
    digest = hashlib.md5(f"{disagreement_type}:{subject}:{season}".encode()).hexdigest()[:16]
    return f"dis_{digest}"


def resolve_and_record(
    con: duckdb.DuckDBPyConnection,
    run_id: str | None,
    disagreement: dict,
    resolved_by: str = "evaluation_qa",
) -> str:
    """Persists both positions, majority and minority -- the minority is never discarded,
    only recorded as resolved-against (AGENT_CONTRACTS.md's conflict protocol step 7:
    "never silently discard the minority result")."""
    resolution = f"resolved in favor of {disagreement['majority_position']}"
    disagreement_id = _disagreement_id(
        disagreement["disagreement_type"], disagreement["subject"], disagreement.get("season")
    )
    con.execute(
        """
        INSERT INTO agent_disagreements
            (disagreement_id, run_id, disagreement_type, subject, season, majority_position,
             majority_value, minority_position, minority_value, critique, resolution,
             resolved_by, detected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (disagreement_id) DO UPDATE SET
            majority_position = excluded.majority_position, majority_value = excluded.majority_value,
            minority_position = excluded.minority_position, minority_value = excluded.minority_value,
            critique = excluded.critique, resolution = excluded.resolution,
            resolved_by = excluded.resolved_by, detected_at = excluded.detected_at
        """,
        [
            disagreement_id,
            run_id,
            disagreement["disagreement_type"],
            disagreement["subject"],
            disagreement.get("season"),
            disagreement["majority_position"],
            disagreement["majority_value"],
            disagreement["minority_position"],
            disagreement["minority_value"],
            disagreement["critique"],
            resolution,
            resolved_by,
            utcnow(),
        ],
    )
    return disagreement_id
