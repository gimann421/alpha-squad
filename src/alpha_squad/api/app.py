"""FastAPI application entrypoint. `uvicorn alpha_squad.api.app:app` or `make serve`.

Every route is a thin read (or a call into an M10 recommendation function) over the same
DuckDB tables the CLI and orchestrator use — no business logic lives in this package
(ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass core model/decision logic")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    seasons,
    simulate,
)
from alpha_squad.config.settings import get_settings
from alpha_squad.storage.db import get_connection, init_db


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One base connection lives for the app's whole life; api/deps.py::get_db() derives a
    # lightweight per-request connection from it via .cursor() rather than calling
    # duckdb.connect() fresh per request. Two real bugs, both found running the real app with
    # Playwright (not synthetic tests), made this necessary:
    #  1. init_db (CREATE TABLE IF NOT EXISTS + ALTER TABLE migrations) must run exactly once:
    #     DuckDB doesn't support concurrent ALTER/DDL from multiple connections against the
    #     same file, and running it per-request raised a real
    #     `TransactionException: write-write conflict` under real concurrent traffic.
    #  2. duckdb.connect() itself isn't safe to call concurrently against the same file from
    #     multiple requests -- two requests arriving close together raised a real
    #     `BinderException: Unique file handle conflict: Cannot attach "alpha_squad" -- the
    #     database file ... is already attached`. `.cursor()` is DuckDB's own documented way
    #     to hand out an independent connection per thread/request that shares one already-
    #     open database instance, without a second `duckdb.connect()` call.
    con = get_connection(get_settings())
    app.state.db_connection = con
    init_db(con)
    try:
        yield
    finally:
        con.close()


app = FastAPI(
    title="Alpha Squad API",
    description=(
        "Fantasy football market-inefficiency intelligence — a read/decision layer over the "
        "real, validated M1-M11 pipeline. Every response is a direct projection of "
        "already-computed, already-tested engine output; killing the engine (the DuckDB "
        "store) breaks this API rather than silently serving stale demo data."
    ),
    version="0.1.0",
    lifespan=_lifespan,
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
app.include_router(seasons.router)
app.include_router(simulate.router)


@app.get("/")
def root() -> dict:
    return {"service": "alpha-squad-api", "docs": "/docs"}
