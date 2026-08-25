"""Pydantic response/request models for the API. Every response schema is a direct
projection of an already-persisted table the CLI reads from too (uncertainty_predictions,
rookie_predictions, edge_snapshot, evidence_events, ...) -- no field here is computed by a
separate code path from what the CLI/orchestrator already produced."""

from __future__ import annotations

from pydantic import BaseModel


class PlayerSummary(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None
    college_name: str | None
    draft_year: int | None
    status: str | None


class PlayerDetail(PlayerSummary):
    gsis_id: str
    birth_date: str | None
    draft_round: int | None
    draft_pick: int | None
    draft_team: str | None
    rookie_season: int | None
    last_season: int | None
    id_map: dict[str, str]


class RankingRow(BaseModel):
    prediction_id: str
    player_id: str
    display_name: str | None
    position: str
    season: int
    point_prediction: float
    p10: float | None
    p25: float | None
    median: float | None
    p75: float | None
    p90: float | None
    top12_prob: float | None
    top24_prob: float | None
    confidence: float | None
    model_version: str
    feature_version: str


class WeeklyRankingRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str
    season: int
    week: int
    base_value: float
    adjusted_value: float
    adjustment_pct: float | None
    evidence_score: float | None
    reason: str | None
    model_name: str


class RookieRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str
    draft_class: int
    predicted_rookie_points: float | None
    breakout_probability: float | None
    model_version: str


class RookieComp(BaseModel):
    player_id: str
    display_name: str | None
    draft_class: int
    similarity_distance: float


class EdgeRow(BaseModel):
    player_id: str
    display_name: str | None
    season: int
    position: str
    ecr_type: str
    model_rank: int
    market_rank: int
    rank_edge: int
    projected_points_edge: float | None
    probability_edge: float | None
    evidence_score: float
    confidence: float | None
    action: str
    reasons: list[str]
    prediction_id: str | None


class EvidenceRow(BaseModel):
    event_id: str
    player_id: str
    display_name: str | None
    season: int
    week: int
    event_date: str
    event_type: str
    strength_label: str
    strength: float
    direction: int
    summary: str
    source: str


class PlayerRankingInfo(BaseModel):
    season: int
    point_prediction: float
    p10: float | None
    p25: float | None
    median: float | None
    p75: float | None
    p90: float | None
    top12_prob: float | None
    top24_prob: float | None
    confidence: float | None
    model_version: str


class PlayerEdgeInfo(BaseModel):
    season: int
    ecr_type: str
    model_rank: int
    market_rank: int
    rank_edge: int
    action: str
    reasons: list[str]


class PlayerRookieInfo(BaseModel):
    draft_class: int
    predicted_rookie_points: float | None
    breakout_probability: float | None


class PlayerLeagueValue(BaseModel):
    league_id: str
    is_mine: bool | None
    roster_need: float | None
    trade_action: str | None
    trade_reasons: list[str]
    age_adjusted_dynasty_value: float | None


class PlayerDetailFull(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None
    college_name: str | None
    draft_year: int | None
    status: str | None
    gsis_id: str
    birth_date: str | None
    draft_round: int | None
    draft_pick: int | None
    draft_team: str | None
    rookie_season: int | None
    last_season: int | None
    id_map: dict[str, str]
    ranking: PlayerRankingInfo | None
    edge: PlayerEdgeInfo | None
    recent_evidence: list[EvidenceRow]
    rookie: PlayerRookieInfo | None
    league_value: PlayerLeagueValue | None


class SourceHealthRow(BaseModel):
    source: str
    dataset: str
    status: str
    checked_at: str
    detail: str | None


class LeagueSummary(BaseModel):
    league_id: str
    source: str
    detail: str | None = None


class RegisterLeagueRequest(BaseModel):
    sleeper_league_id: str
    league_id: str | None = None


class RosterPlayerRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None


class TeamRosterRow(BaseModel):
    roster_id: int
    owner_display_name: str | None
    team_name: str | None
    players: list[RosterPlayerRow]
    unmapped_count: int


class LeagueTeamsResponse(BaseModel):
    league_id: str
    supported: bool
    teams: list[TeamRosterRow]


class MyTeamPlayerRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None
    projection: float | None
    p10: float | None
    p90: float | None
    confidence: float | None
    top24_prob: float | None
    market_rank: int | None
    rank_edge: int | None
    edge_action: str | None
    dynasty_value: float | None
    marginal_value: float | None
    is_starter: bool


class MyTeamResponse(BaseModel):
    league_id: str
    roster_id: int
    season: int
    owner_display_name: str | None
    team_name: str | None
    players: list[MyTeamPlayerRow]
    unmapped_player_count: int
    positional_needs: dict[str, float]
    positional_scarcity: dict[str, float]
    replacement_levels: dict[str, float]
    total_projected_points: float


class ProvenanceResponse(BaseModel):
    entity_type: str
    entity_id: str
    found: bool
    record: dict | None = None


class DraftRequest(BaseModel):
    season: int
    roster_positions: list[str] = []
    roster_id: int | None = None
    available_player_ids: list[str] | None = None
    next_pick_overall: int | None = None
    ecr_type: str = "rsf"
    top_n: int = 5


class WaiverRequest(BaseModel):
    season: int
    week: int
    player_id: str
    roster_positions: list[str] = []
    roster_id: int | None = None


class TradeRequest(BaseModel):
    season: int
    player_id: str
    ecr_type: str = "rsf"


class PickAssetRequest(BaseModel):
    round: int
    pick_in_round: int | None = None
    years_out: int = 0


class TradePackageSideRequest(BaseModel):
    player_ids: list[str] = []
    picks: list[PickAssetRequest] = []


class TradePackageRequest(BaseModel):
    season: int
    side_a: TradePackageSideRequest
    side_b: TradePackageSideRequest
    ecr_type: str = "rsf"


class TradePackageResponse(BaseModel):
    side_a_value: float
    side_b_value: float
    delta: float
    favors: str
    side_a_reasons: list[str]
    side_b_reasons: list[str]


class SimulationRequest(BaseModel):
    team: str
    season: int
    n_simulations: int = 1000
    n_weeks: int = 17
    seed: int = 42


class PlayerSimResultRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str
    mean_points: float
    std_points: float
    p10: float
    p50: float
    p90: float


class SimulationResponse(BaseModel):
    run_id: str
    team: str
    season: int
    n_simulations: int
    n_weeks: int
    mean_team_points: float
    std_team_points: float
    qb_wr1_correlation: float | None
    same_position_correlation: float | None
    players: list[PlayerSimResultRow]


class DropCandidateRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None
    marginal_value: float | None
    reasons: list[str]


class WaiverTargetRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str
    expected_points: float
    meaningful_role_probability: float | None
    dynasty_value: float | None
    value_spike_probability: float
    marginal_value: float
    roster_fit_multiplier: float
    competing_bid_likelihood: float
    recommended_bid: float
    reasons: list[str]


class TradeSignalRow(BaseModel):
    player_id: str
    display_name: str | None
    position: str | None
    edge_action: str
    rank_edge: int | None
    dynasty_value: float | None
    summary: str


class ActionCenterResponse(BaseModel):
    league_id: str
    roster_id: int
    season: int
    adds: list[WaiverTargetRow]
    drops: list[DropCandidateRow]
    trade_signals: list[TradeSignalRow]


class DecisionResponse(BaseModel):
    decision_id: str
    recommendation: str
    alternatives: list[str]
    expected_value: float | None
    confidence: float | None
    reasons: list[str]
