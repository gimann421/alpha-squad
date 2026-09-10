"""GET /rankings -- THE board: exactly the player universe the draft engine drafts from,
ordered by the same point prediction the models produced. No re-ranking or re-scoring here.

**Why this reads `load_season_projections` rather than `uncertainty_predictions` (D79).** Until
D79 it queried `uncertainty_predictions` alone, which covers established QB/RB/WR/TE only. The
engine's board (`league/replacement.py::load_season_projections`) additionally carries rookies
(M7 `rookie_predictions`) and kickers/defenses (D57's baseline in `projection_snapshot`). The web
Draft view builds `available_player_ids` from this endpoint, so those three sources were missing
from every recommendation the product ever made -- measured on the real 2021-2025 boards, 163-179
players per season, including **every kicker and every team defense** in a league that starts one
of each, and 6-13 of the engine's own top 100 (2025's highest-projected running back among them).

That had two consequences, both fixed by serving one universe rather than two:

1. Alpha could never recommend a K, a DST or a rookie. An unfilled mandatory starting slot is
   worth roughly -130 realized points (D67), and the benchmark's own opponent is *forced* to fill
   those slots while the product's engine could not suggest them.
2. `league/draft.py::recommend_draft_pick` guards its draft-aware replacement level (D67) behind
   `len(projections) - len(available) <= teams * roster_size`, whose premise is that everything
   missing from `available` was DRAFTED. With 163-179 players never in the pool at all, that
   guard failed from the very first pick of every season, and the engine silently fell back to
   the static full-season replacement level -- the D65 defect D67 was shipped to remove, and the
   largest measured draft-layer change in the project. The fix is to make the guard's premise
   true, not to loosen the guard.

`tests/unit/test_api.py` pins the invariant (this endpoint's universe == the engine's) so the two
cannot drift apart again. Rookie and K/DST rows carry no conformal interval, so their
`p10`/`p90`/`top12_prob`/`confidence` come back null rather than fabricated -- see
`models/baselines/kicking_defense.py` for why K/DST are deliberately baselines, not models.

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
from alpha_squad.league.replacement import load_season_projections
from alpha_squad.models.established.train import WEEKLY_PROJECTION_BASE_MODEL
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

router = APIRouter(prefix="/rankings", tags=["rankings"])

# What a board row reports when it did NOT come from M6's uncertainty model -- a rookie
# projection or a K/DST baseline. Naming the composite board explicitly is more honest than
# reporting M6's version for a row M6 never produced, and it is what makes the source of a
# null `confidence` legible in the response rather than ambiguous.
BOARD_MODEL_VERSION = "season_board_v1"
BOARD_FEATURE_VERSION = "season_board_v1"


#: Enough to serve a whole season's board in one request. The real 2021-2026 boards run 602-651
#: players, and the Draft view needs ALL of them in one call: a truncated board is not a board,
#: and truncating it silently reintroduces exactly the defect described in the module docstring.
#: `alpha-squad train projection-status` is the gate that a season's board exists at all.
MAX_RANKING_ROWS = 2000


@router.get("", response_model=list[RankingRow])
def get_rankings(
    season: int = Query(...),
    position: str | None = Query(None),
    limit: int = Query(50, le=MAX_RANKING_ROWS),
    con: duckdb.DuckDBPyConnection = Depends(get_db),
) -> list[RankingRow]:
    # D79: the universe and the point predictions come from `load_season_projections` -- the
    # SAME function `league/draft.py::recommend_draft_pick` calls -- so the board the product
    # shows and the board the engine drafts from cannot disagree. Reusing the function rather
    # than reimplementing its three-source precedence in SQL is the point: that precedence
    # (M6 wins over M7 wins over the K/DST baseline) is exactly what would drift.
    projections, positions = load_season_projections(con, season)
    ordered = sorted(
        (pid for pid in projections if not position or positions.get(pid) == position),
        key=lambda pid: (-projections[pid], pid),
    )[:limit]
    if not ordered:
        return []

    # D78: pin the shipped model version. `uncertainty_predictions` is keyed by
    # (player_id, season, model_version), so once a second specification exists this query
    # returns EVERY player twice -- once per version, with different point predictions, ordered
    # against each other. Verified on real 2026 data before the fix: 610 duplicated players, and
    # a top-of-board that interleaved v1 and v2 rows. The draft engine was never affected
    # (`load_season_projections` has always pinned the version); this is the served ranking list
    # the UI reads, which is exactly where a stale projection would be hardest to notice.
    detail = {
        r[0]: r
        for r in con.execute(
            """
            SELECT player_id, prediction_id, p10, p25, median, p75, p90, top12_prob,
                   top24_prob, confidence, model_version, feature_version
            FROM uncertainty_predictions
            WHERE season = ? AND model_version = ? AND player_id = ANY(?)
            """,
            [season, UNCERTAINTY_MODEL_VERSION, ordered],
        ).fetchall()
    }
    names = dict(
        con.execute(
            "SELECT player_id, display_name FROM players WHERE player_id = ANY(?)", [ordered]
        ).fetchall()
    )

    rows: list[RankingRow] = []
    for player_id in ordered:
        d = detail.get(player_id)
        rows.append(
            RankingRow(
                prediction_id=(d[1] if d else f"board_{season}_{player_id}"),
                player_id=player_id,
                display_name=names.get(player_id),
                position=positions[player_id],
                season=season,
                point_prediction=projections[player_id],
                # A rookie projection (M7) and a K/DST baseline (D57) carry no conformal
                # interval, so these stay null rather than being invented. `RankingRow` already
                # declares every one of them optional.
                p10=d[2] if d else None,
                p25=d[3] if d else None,
                median=d[4] if d else None,
                p75=d[5] if d else None,
                p90=d[6] if d else None,
                top12_prob=d[7] if d else None,
                top24_prob=d[8] if d else None,
                confidence=d[9] if d else None,
                model_version=d[10] if d else BOARD_MODEL_VERSION,
                feature_version=d[11] if d else BOARD_FEATURE_VERSION,
            )
        )
    return rows


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
