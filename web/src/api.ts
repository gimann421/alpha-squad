// Thin fetch wrapper around the Alpha Squad API. Every function here does exactly one HTTP
// call and returns the parsed response -- no client-side ranking, filtering-as-truth, or
// scoring logic lives in this file (ACCEPTANCE_CRITERIA.md: "UI does not duplicate or bypass
// core model/decision logic"). If the API is unreachable, calls throw, and callers surface
// that as a real error state rather than falling back to stale/fabricated data.

import type {
  DecisionResponse,
  EdgeRow,
  EvidenceRow,
  LeagueContext,
  LeagueSummary,
  PlayerDetail,
  PlayerSummary,
  ProvenanceResponse,
  RankingRow,
  RookieComp,
  RookieRow,
  SourceHealthRow,
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
  getLeagueContext: (leagueId: string) => getJson<LeagueContext>(`/league/${leagueId}/context`),
  getRosterNeed: (leagueId: string, rosterPositions: string) =>
    getJson<{ need: Record<string, number> }>(`/league/${leagueId}/roster`, {
      roster_positions: rosterPositions,
    }),
  postDraft: (
    leagueId: string,
    body: {
      season: number;
      roster_positions?: string[];
      available_player_ids?: string[];
      next_pick_overall?: number;
      ecr_type?: string;
      top_n?: number;
    },
  ) => postJson<DecisionResponse>(`/league/${leagueId}/draft`, body),
  postWaiver: (
    leagueId: string,
    body: { season: number; week: number; player_id: string; roster_positions?: string[] },
  ) => postJson<DecisionResponse>(`/league/${leagueId}/waivers`, body),
  postTrade: (leagueId: string, body: { season: number; player_id: string; ecr_type?: string }) =>
    postJson<DecisionResponse>(`/league/${leagueId}/trade`, body),

  getProvenance: (entityId: string) => getJson<ProvenanceResponse>(`/provenance/${entityId}`),

  getSourceHealth: () => getJson<SourceHealthRow[]>("/health/sources"),
};
