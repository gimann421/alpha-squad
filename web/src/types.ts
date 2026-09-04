// Mirrors src/alpha_squad/api/schemas.py field-for-field. This file has no business logic --
// it only describes the shape of what the API already computed.

export interface PlayerSummary {
  player_id: string;
  display_name: string | null;
  position: string | null;
  college_name: string | null;
  draft_year: number | null;
  status: string | null;
}

export interface PlayerDetail extends PlayerSummary {
  gsis_id: string;
  birth_date: string | null;
  draft_round: number | null;
  draft_pick: number | null;
  draft_team: string | null;
  rookie_season: number | null;
  last_season: number | null;
  id_map: Record<string, string>;
}

export interface RankingRow {
  player_id: string;
  display_name: string | null;
  position: string;
  season: number;
  point_prediction: number;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  top12_prob: number | null;
  top24_prob: number | null;
  confidence: number | null;
  model_version: string;
  feature_version: string;
}

export interface WeeklyRankingRow {
  player_id: string;
  display_name: string | null;
  position: string;
  season: number;
  week: number;
  base_value: number;
  adjusted_value: number;
  adjustment_pct: number | null;
  evidence_score: number | null;
  reason: string | null;
  model_name: string;
}

export interface RookieRow {
  player_id: string;
  display_name: string | null;
  position: string;
  draft_class: number;
  predicted_rookie_points: number | null;
  breakout_probability: number | null;
  model_version: string;
}

export interface RookieComp {
  player_id: string;
  display_name: string | null;
  draft_class: number;
  similarity_distance: number;
}

export interface EdgeRow {
  player_id: string;
  display_name: string | null;
  season: number;
  position: string;
  ecr_type: string;
  model_rank: number;
  market_rank: number;
  rank_edge: number;
  projected_points_edge: number | null;
  probability_edge: number | null;
  evidence_score: number;
  confidence: number | null;
  action: "BUY" | "SELL" | "HOLD" | "WATCH";
  reasons: string[];
  prediction_id: string | null;
}

export interface EvidenceRow {
  event_id: string;
  player_id: string;
  display_name: string | null;
  season: number;
  week: number;
  event_date: string;
  event_type: string;
  strength_label: "STRONG" | "MEDIUM" | "WEAK";
  strength: number;
  direction: -1 | 0 | 1;
  summary: string;
  source: string;
}

export interface SourceHealthRow {
  source: string;
  dataset: string;
  status: string;
  checked_at: string;
  detail: string | null;
}

export interface LeagueSummary {
  league_id: string;
  source: string;
  detail: string | null;
}

export interface LeagueContext {
  league_id: string;
  format: string;
  teams: number;
  scoring: Record<string, unknown>;
  lineup: Record<string, number>;
  roster: Record<string, unknown>;
  faab: Record<string, unknown>;
  source?: string;
}

export interface PlayerSimResultRow {
  player_id: string;
  display_name: string | null;
  position: string;
  mean_points: number;
  std_points: number;
  p10: number;
  p50: number;
  p90: number;
}

export interface SimulationResponse {
  run_id: string;
  team: string;
  season: number;
  n_simulations: number;
  n_weeks: number;
  mean_team_points: number;
  std_team_points: number;
  qb_wr1_correlation: number | null;
  same_position_correlation: number | null;
  players: PlayerSimResultRow[];
}

export interface DecisionResponse {
  decision_id: string;
  recommendation: string;
  alternatives: string[];
  expected_value: number | null;
  confidence: number | null;
  reasons: string[];
  action?: string | null;
}

export interface ProvenanceResponse {
  entity_type: string;
  entity_id: string;
  found: boolean;
  record: Record<string, string | null> | null;
}

export interface RosterPlayerRow {
  player_id: string;
  display_name: string | null;
  position: string | null;
}

export interface TeamRosterRow {
  roster_id: number;
  owner_display_name: string | null;
  team_name: string | null;
  players: RosterPlayerRow[];
  unmapped_count: number;
}

export interface LeagueTeamsResponse {
  league_id: string;
  supported: boolean;
  teams: TeamRosterRow[];
}

export interface SleeperDraftPickRow {
  pick_no: number;
  round: number;
  roster_id: number | null;
  player_id: string | null;
  display_name: string | null;
}

export interface SleeperDraftState {
  league_id: string;
  draft_id: string | null;
  status: "no_draft" | "pre_draft" | "drafting" | "paused" | "complete" | string;
  draft_type: string | null;
  teams: number | null;
  rounds: number | null;
  picks: SleeperDraftPickRow[];
  drafted_player_ids: string[];
  unmapped_sleeper_ids: string[];
  my_player_ids: string[] | null;
  current_pick_overall: number | null;
  on_the_clock_roster_id: number | null;
  next_pick_overall: number | null;
  is_users_turn: boolean | null;
}

export interface MyTeamPlayerRow {
  player_id: string;
  display_name: string | null;
  position: string | null;
  projection: number | null;
  p10: number | null;
  p90: number | null;
  confidence: number | null;
  top24_prob: number | null;
  market_rank: number | null;
  rank_edge: number | null;
  edge_action: string | null;
  dynasty_value: number | null;
  marginal_value: number | null;
  is_starter: boolean;
}

export interface MyTeamResponse {
  league_id: string;
  roster_id: number;
  season: number;
  owner_display_name: string | null;
  team_name: string | null;
  players: MyTeamPlayerRow[];
  unmapped_player_count: number;
  positional_needs: Record<string, number>;
  positional_scarcity: Record<string, number>;
  replacement_levels: Record<string, number>;
  total_projected_points: number;
}

export interface DropCandidateRow {
  player_id: string;
  display_name: string | null;
  position: string | null;
  marginal_value: number | null;
  reasons: string[];
}

export interface WaiverTargetRow {
  player_id: string;
  display_name: string | null;
  position: string;
  expected_points: number;
  meaningful_role_probability: number | null;
  dynasty_value: number | null;
  value_spike_probability: number;
  marginal_value: number;
  roster_fit_multiplier: number;
  competing_bid_likelihood: number;
  recommended_bid: number;
  reasons: string[];
}

export interface TradeSignalRow {
  player_id: string;
  display_name: string | null;
  position: string | null;
  edge_action: string;
  rank_edge: number | null;
  dynasty_value: number | null;
  summary: string;
}

export interface ActionCenterResponse {
  league_id: string;
  roster_id: number;
  season: number;
  adds: WaiverTargetRow[];
  drops: DropCandidateRow[];
  trade_signals: TradeSignalRow[];
}

export interface PlayerRankingInfo {
  season: number;
  point_prediction: number;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  top12_prob: number | null;
  top24_prob: number | null;
  confidence: number | null;
  model_version: string;
}

export interface PlayerEdgeInfo {
  season: number;
  ecr_type: string;
  model_rank: number;
  market_rank: number;
  rank_edge: number;
  action: string;
  reasons: string[];
}

export interface PlayerRookieInfo {
  draft_class: number;
  predicted_rookie_points: number | null;
  breakout_probability: number | null;
}

export interface PlayerLeagueValue {
  league_id: string;
  is_mine: boolean | null;
  roster_need: number | null;
  trade_action: string | null;
  trade_reasons: string[];
  age_adjusted_dynasty_value: number | null;
}

export interface PlayerDetailFull extends PlayerDetail {
  ranking: PlayerRankingInfo | null;
  edge: PlayerEdgeInfo | null;
  recent_evidence: EvidenceRow[];
  rookie: PlayerRookieInfo | null;
  league_value: PlayerLeagueValue | null;
}

export interface PickAssetRequest {
  round: number;
  pick_in_round?: number | null;
  years_out?: number;
}

export interface TradePackageSideRequest {
  player_ids: string[];
  picks: PickAssetRequest[];
}

export interface TradePackageRequest {
  season: number;
  side_a: TradePackageSideRequest;
  side_b: TradePackageSideRequest;
  ecr_type?: string;
}

export interface TradePackageResponse {
  side_a_value: number;
  side_b_value: number;
  delta: number;
  favors: "side_a" | "side_b" | "even";
  side_a_reasons: string[];
  side_b_reasons: string[];
}
