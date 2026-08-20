"""GET /provenance/{id} -- traces an ID across every table that could own it (predictions,
edge, decisions, evidence events, deltas, snapshots), so "why did this change" has a real,
inspectable answer (ACCEPTANCE_CRITERIA.md: "EDGE/evidence can be inspected", "every major
recommendation must be traceable to data/model/evidence versions"). No new computation --
a straight lookup against already-persisted rows."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import ProvenanceResponse

router = APIRouter(prefix="/provenance", tags=["provenance"])

# (entity_type, table, id_column)
_LOOKUPS = [
    ("uncertainty_prediction", "uncertainty_predictions", "prediction_id"),
    ("rookie_prediction", "rookie_predictions", "prediction_id"),
    ("edge_snapshot", "edge_snapshot", "edge_id"),
    ("evidence_event", "evidence_events", "event_id"),
    ("decision", "decisions", "decision_id"),
    ("projection_delta", "projection_deltas", "delta_id"),
    ("snapshot", "snapshot_registry", "snapshot_id"),
]


@router.get("/{entity_id}", response_model=ProvenanceResponse)
def get_provenance(
    entity_id: str, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> ProvenanceResponse:
    for entity_type, table, id_col in _LOOKUPS:
        cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
        row = con.execute(f"SELECT * FROM {table} WHERE {id_col} = ?", [entity_id]).fetchone()
        if row is not None:
            record = {k: (str(v) if v is not None else None) for k, v in zip(cols, row, strict=True)}
            return ProvenanceResponse(entity_type=entity_type, entity_id=entity_id, found=True, record=record)
    return ProvenanceResponse(entity_type="unknown", entity_id=entity_id, found=False)
