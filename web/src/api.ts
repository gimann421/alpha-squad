// Thin fetch wrapper around the Alpha Squad API. Every function here does exactly one HTTP
// call and returns the parsed response -- no client-side ranking, filtering-as-truth, or
// scoring logic lives in this file (ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass
// core model/decision logic"). If the API is unreachable, calls throw, and callers surface
// that as a real error state rather than falling back to stale/fabricated data.

import type {
  ActionCenterResponse,
  DecisionResponse,
  DropCandidateRow,
  EdgeRow,
  EvidenceRow,
  LeagueContext,
  LeagueSummary,
  LeagueTeamsResponse,
  MyTeamResponse,
  PlayerDetail,
  PlayerDetailFull,
  PlayerSummary,
  ProvenanceResponse,
  RankingRow,
  RookieComp,
  RookieRow,
  SimulationResponse,
  SleeperDraftState,
  SourceHealthRow,
  TradePackageRequest,
  TradePackageResponse,
  WaiverTargetRow,
  WeeklyRankingRow,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function getJson<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(new URL(path, API_BASE).toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listPlayers: (params?: { position?: string; q?: string; limit?: number }) =>
    getJson<PlayerSummary[]>("/players", params),
  getPlayer: (playerId: string) => getJson<PlayerDetail>(`/players/${playerId}`),
  getPlayerDetail: (
    playerId: string,
    params: { season: number; ecr_type?: string; league_id?: string; roster_id?: number },
  ) => getJson<PlayerDetailFull>(`/players/${playerId}/detail`, params),

  getRankings: (params: { season: number; position?: string; limit?: number }) =>
    getJson<RankingRow[]>("/rankings", params),

  getWeeklyRankings: (params: { season: number; week: number; position?: string; limit?: number }) =>
    getJson<WeeklyRankingRow[]>("/rankings/weekly", params),

  getRookieClasses: () => getJson<number[]>("/rookies/classes"),
  getRookies: (params: { draft_class: number; position?: string; limit?: number }) =>
    getJson<RookieRow[]>("/rookies", params),
  getRookieComps: (playerId: string, params: { draft_class: number; position: string; k?: number }) =>
    getJson<RookieComp[]>(`/rookies/${playerId}/comps`, params),

  getEdge: (params: { season: number; action?: string; ecr_type?: string; limit?: number }) =>
    getJson<EdgeRow[]>("/edge", params),

  getEvidence: (params: { player_id?: string; season?: number; week?: number; limit?: number }) =>
    getJson<EvidenceRow[]>("/evidence", params),

  listLeagues: () => getJson<LeagueSummary[]>("/league"),
  registerLeague: (body: { sleeper_league_id: string; league_id?: string }) =>
    postJson<LeagueSummary>("/league/register", body),
  getLeagueTeams: (leagueId: string) => getJson<LeagueTeamsResponse>(`/league/${leagueId}/teams`),
  getLeagueContext: (leagueId: string) => getJson<LeagueContext>(`/league/${leagueId}/context`),
  getSleeperDraft: (leagueId: string, params?: { roster_id?: number }) =>
    getJson<SleeperDraftState>(`/league/${leagueId}/sleeper-draft`, params),
  getRosterNeed: (leagueId: string, params: { roster_positions?: string; roster_id?: number }) =>
    getJson<{ need: Record<string, number>; roster_positions: string[] }>(
      `/league/${leagueId}/roster`,
      params,
    ),
  getMyTeam: (leagueId: string, params: { season: number; roster_id: number; ecr_type?: string }) =>
    getJson<MyTeamResponse>(`/league/${leagueId}/my-team`, params),
  getWaiverTargets: (
    leagueId: string,
    params: { season: number; week: number; roster_id: number; position?: string; top_n?: number },
  ) => getJson<WaiverTargetRow[]>(`/league/${leagueId}/waiver-targets`, params),
  getDropCandidates: (
    leagueId: string,
    params: { season: number; roster_id: number; top_n?: number; ecr_type?: string },
  ) => getJson<DropCandidateRow[]>(`/league/${leagueId}/drop-candidates`, params),
  getActionCenter: (
    leagueId: string,
    params: {
      season: number;
      week: number;
      roster_id: number;
      add_top_n?: number;
      drop_top_n?: number;
      ecr_type?: string;
    },
  ) => getJson<ActionCenterResponse>(`/league/${leagueId}/actions`, params),
  postDraft: (
    leagueId: string,
    body: {
      season: number;
      roster_positions?: string[];
      roster_id?: number;
      // This team's own drafted players -- NOT the league-wide drafted pool. Enables the
      // benchmarked roster-aware value base (D60/D63/D67); omitted, the engine falls back
      // to VORP. Superseded server-side by a resolved `roster_id`.
      roster_player_ids?: string[];
      available_player_ids?: string[];
      next_pick_overall?: number;
      current_pick_overall?: number;
      ecr_type?: string;
      top_n?: number;
    },
  ) => postJson<DecisionResponse>(`/league/${leagueId}/draft`, body),
  postWaiver: (
    leagueId: string,
    body: {
      season: number;
      week: number;
      player_id: string;
      roster_positions?: string[];
      roster_id?: number;
    },
  ) => postJson<DecisionResponse>(`/league/${leagueId}/waivers`, body),
  postTrade: (leagueId: string, body: { season: number; player_id: string; ecr_type?: string }) =>
    postJson<DecisionResponse>(`/league/${leagueId}/trade`, body),
  postTradePackage: (leagueId: string, body: TradePackageRequest) =>
    postJson<TradePackageResponse>(`/league/${leagueId}/trade-package`, body),

  postSimulation: (body: {
    team: string;
    season: number;
    n_simulations?: number;
    n_weeks?: number;
    seed?: number;
  }) => postJson<SimulationResponse>("/simulate/team-season", body),

  getProvenance: (entityId: string) => getJson<ProvenanceResponse>(`/provenance/${entityId}`),

  getSourceHealth: () => getJson<SourceHealthRow[]>("/health/sources"),

  getLatestSeasons: () =>
    getJson<{ uncertainty: number | null; weekly: number | null; edge: number | null; evidence: number | null }>(
      "/seasons/latest",
    ),
};
