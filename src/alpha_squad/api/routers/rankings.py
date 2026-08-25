"""GET /rankings -- direct projection of `uncertainty_predictions` (M6), the season-level
(preseason) point/uncertainty model. No re-ranking or re-scoring logic here; the ORDER BY is
the same point_prediction the model produced.

GET /rankings/weekly -- direct projection of `weekly_projection_snapshot` (M5's in-season
weekly model) LEFT JOINed with `projection_deltas` (M9's bounded evidence adjustment, D46):
"current information updates the prior; it does not automatically override it"
(PRODUCT_SPEC.md). Ordered by the evidence-adjusted value, falling back to the unadjusted base
prediction for players with no evidence on record that week -- the ranking a user actually
sees already reflects evidence, not just the raw model output, which is what
`docs/CURRENT_STATE_AUDIT.md` found was previously missing end to end."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, Query

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import RankingRow, WeeklyRankingRow
from alpha_squad.models.established.train import WEEKLY_PROJECTION_BASE_MODEL

router = APIRouter(prefix="/rankings", tags=["rankings"])


@router.get("", response_model=list[RankingRow])
def get_rankings(
    season: int = Query(...),
    position: str | None = Query(None),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[RankingRow]:
    where = ["u.season = ?"]
    params: list = [season]
    if position:
        where.append("u.position = ?")
        params.append(position)
    rows = con.execute(
        f"""
        SELECT u.prediction_id, u.player_id, p.display_name, u.position, u.season,
               u.point_prediction, u.p10, u.p25, u.median, u.p75, u.p90, u.top12_prob,
               u.top24_prob, u.confidence, u.model_version, u.feature_version
        FROM uncertainty_predictions u
        LEFT JOIN players p ON p.player_id = u.player_id
        WHERE {" AND ".join(where)}
        ORDER BY u.point_prediction DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        RankingRow(
            prediction_id=r[0],
            player_id=r[1],
            display_name=r[2],
            position=r[3],
            season=r[4],
            point_prediction=r[5],
            p10=r[6],
            p25=r[7],
            median=r[8],
            p75=r[9],
            p90=r[10],
            top12_prob=r[11],
            top24_prob=r[12],
            confidence=r[13],
            model_version=r[14],
            feature_version=r[15],
        )
        for r in rows
    ]


@router.get("/weekly", response_model=list[WeeklyRankingRow])
def get_weekly_rankings(
    season: int = Query(...),
    week: int = Query(...),
    position: str | None = Query(None),
    model_name: str = Query(WEEKLY_PROJECTION_BASE_MODEL),
    limit: int = Query(50, le=500),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[WeeklyRankingRow]:
    where = ["w.season = ?", "w.week = ?", "w.model_name = ?"]
    params: list = [season, week, model_name]
    if position:
        where.append("w.position = ?")
        params.append(position)
    rows = con.execute(
        f"""
        SELECT w.player_id, p.display_name, w.position, w.season, w.week,
               w.predicted_points AS base_value,
               COALESCE(d.adjusted_value, w.predicted_points) AS adjusted_value,
               d.adjustment_pct, d.evidence_score, d.reason, w.model_name
        FROM weekly_projection_snapshot w
        LEFT JOIN projection_deltas d
            ON d.player_id = w.player_id AND d.season = w.season AND d.week = w.week
            AND d.base_model_name = w.model_name
        LEFT JOIN players p ON p.player_id = w.player_id
        WHERE {" AND ".join(where)}
        ORDER BY adjusted_value DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        WeeklyRankingRow(
            player_id=r[0],
            display_name=r[1],
            position=r[2],
            season=r[3],
            week=r[4],
            base_value=r[5],
            adjusted_value=r[6],
            adjustment_pct=r[7],
            evidence_score=r[8],
            reason=r[9],
            model_name=r[10],
        )
        for r in rows
    ]
