"""POST /simulate/team-season -- the exact `simulate_team_season` function the CLI's
`alpha-squad simulate team-season` calls, over the same DuckDB tables (D8/D29/D45 pattern:
no parallel decision logic in the API layer). A real Monte Carlo run at n_simulations=1000 is
real compute (seconds, not milliseconds), so this is a POST that runs synchronously and
returns the full result -- not a cheap read -- matching how the CLI already treats it (a
one-shot command, not a background job)."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from alpha_squad.api.deps import get_db
from alpha_squad.api.schemas import PlayerSimResultRow, SimulationRequest, SimulationResponse
from alpha_squad.models.simulation.correlated import (
    MIN_TEAM_WEEKS,
    record_simulation_run,
    simulate_team_season,
)

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("/team-season", response_model=SimulationResponse)
def post_team_season_simulation(
    body: SimulationRequest, con: duckdb.DuckDBPyConnection = Depends(get_db)
) -> SimulationResponse:
    result = simulate_team_season(
        con, body.team, body.season, body.n_weeks, body.n_simulations, body.seed
    )
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough real history for {body.team} before {body.season} "
                f"(need >= {MIN_TEAM_WEEKS} prior weeks of team_week_stats/team_week_points)."
            ),
        )
    run_id = record_simulation_run(con, result, body.seed)

    player_ids = [p.player_id for p in result.players]
    names: dict[str, str | None] = {}
    if player_ids:
        placeholders = ", ".join("?" for _ in player_ids)
        rows = con.execute(
            f"SELECT player_id, display_name FROM players WHERE player_id IN ({placeholders})",
            player_ids,
        ).fetchall()
        names = dict(rows)

    return SimulationResponse(
        run_id=run_id,
        team=result.team,
        season=result.season,
        n_simulations=result.n_simulations,
        n_weeks=result.n_weeks,
        mean_team_points=result.mean_team_points,
        std_team_points=result.std_team_points,
        qb_wr1_correlation=result.qb_wr1_correlation,
        same_position_correlation=result.same_position_correlation,
        players=[
            PlayerSimResultRow(
                player_id=p.player_id,
                display_name=names.get(p.player_id),
                position=p.position,
                mean_points=p.mean_points,
                std_points=p.std_points,
                p10=p.p10,
                p50=p.p50,
                p90=p.p90,
            )
            for p in result.players
        ],
    )
