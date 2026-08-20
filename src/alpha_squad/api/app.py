"""FastAPI application entrypoint. `uvicorn alpha_squad.api.app:app` or `make serve`.

Every route is a thin read (or a call into an M10 recommendation function) over the same
DuckDB tables the CLI and orchestrator use — no business logic lives in this package
(ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass core model/decision logic")."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alpha_squad.api.routers import (
    edge,
    evidence,
    health,
    league,
    players,
    provenance,
    rankings,
    rookies,
)

app = FastAPI(
    title="Alpha Squad API",
    description=(
        "Fantasy football market-inefficiency intelligence — a read/decision layer over the "
        "real, validated M1-M11 pipeline. Every response is a direct projection of "
        "already-computed, already-tested engine output; killing the engine (the DuckDB "
        "store) breaks this API rather than silently serving stale demo data."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players.router)
app.include_router(rankings.router)
app.include_router(rookies.router)
app.include_router(edge.router)
app.include_router(evidence.router)
app.include_router(league.router)
app.include_router(provenance.router)
app.include_router(health.router)


@app.get("/")
def root() -> dict:
    return {"service": "alpha-squad-api", "docs": "/docs"}
