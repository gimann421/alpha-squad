"""GET /seasons/latest -- the newest season each real table actually has data for. D48:
several frontend views defaulted to a hardcoded season, which is exactly how the app once
showed an already-played rookie class after the season rolled over (docs/DECISIONS.md D40) --
this is the same fix generalized: read the real newest season from the tables each view
actually depends on, instead of a constant that silently goes stale every year."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends

from alpha_squad.api.deps import get_db

router = APIRouter(prefix="/seasons", tags=["seasons"])


def _max_season(con: duckdb.DuckDBPyConnection, table: str) -> int | None:
    return con.execute(f"SELECT max(season) FROM {table}").fetchone()[0]  # noqa: S608 - table is a fixed internal literal, never user input


@router.get("/latest", response_model=dict[str, int | None])
def get_latest_seasons(con: duckdb.DuckDBPyConnection = Depends(get_db)) -> dict[str, int | None]:
    return {
        "uncertainty": _max_season(con, "uncertainty_predictions"),
        "weekly": _max_season(con, "weekly_projection_snapshot"),
        "edge": _max_season(con, "edge_snapshot"),
        "evidence": _max_season(con, "evidence_events"),
    }
