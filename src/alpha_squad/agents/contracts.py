"""Pydantic models mirroring AGENT_CONTRACTS.md's schemas byte-for-byte (field names/shapes
match its JSON examples exactly). These are the typed interchange the orchestrator (M11) uses
between agents -- agents are deterministic Python services wrapping the real M1-M10 pipeline,
never an LLM call (ARCHITECTURE.md §6, docs/DECISIONS.md D14).

League context reuses `league.context.LeagueContext` rather than redefining it -- that model
already mirrors AGENT_CONTRACTS.md's League context contract exactly (built in M10) and is a
single source of truth other code already depends on."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Real states this project's orchestrator actually uses (IMPLEMENTATION_PLAN.md's M11 scope).
TASK_STATES = (
    "PLANNED",
    "READY",
    "RUNNING",
    "BLOCKED",
    "NEEDS_REVIEW",
    "COMPLETE",
    "FAILED",
    "REJECTED",
)

AGENT_NAMES = (
    "orchestrator",
    "data_engineering",
    "player_identity",
    "projection_ml",
    "rookie_ml",
    "market_edge",
    "news_evidence",
    "evaluation_qa",
    "fantasy_strategy",
    "research_validation",
)


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    agent: str
    objective: str
    priority: str = "MEDIUM"
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    artifacts_expected: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


class TestOutcome(BaseModel):
    name: str
    status: str


class Result(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    agent: str
    status: str
    confidence: float | None = None
    findings: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    tests: list[TestOutcome] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None


class EvidenceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    player_id: str
    event_date: str
    captured_at: str
    event_type: str
    source: str
    source_url: str | None = None
    strength: float
    structured_impact: dict = Field(default_factory=dict)
    summary: str


class PredictionContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    prediction_id: str
    prediction_date: str
    player_id: str
    model_version: str
    data_version: str | None = None
    feature_version: str
    target: str
    p10: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    p90: float | None = None
    top12_prob: float | None = None
    top24_prob: float | None = None
    confidence: float | None = None


class EdgeContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    player_id: str
    prediction_date: str
    model_rank: int
    market_rank: int
    rank_edge: int
    projected_points_edge: float | None = None
    probability_edge: float | None = None
    evidence_score: float
    confidence: float | None = None
    action: str
    reasons: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)


class DecisionContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    decision_id: str
    decision_type: str
    league_id: str
    recommendation: str
    alternatives: list[str] = Field(default_factory=list)
    expected_value: float | None = None
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)
