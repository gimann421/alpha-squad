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
}

export interface ProvenanceResponse {
  entity_type: string;
  entity_id: string;
  found: boolean;
  record: Record<string, string | null> | null;
}
