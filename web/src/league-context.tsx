// Single shared source of "which league / which of my real teams am I looking at", replacing
// the old pattern where every view (Waiver/Trade/League) independently re-fetched the league
// registry and re-implemented its own localStorage-backed "last league" memory. Adds a second,
// equally sticky selection this session's earlier views never had: `rosterId`, the real team
// (from GET /league/{id}/teams, D53) a Sleeper-connected league's roster-aware endpoints need --
// switching leagues clears it and re-picks a sensible default rather than carrying a stale id
// from a different league's roster numbering into a new one.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { LeagueSummary, TeamRosterRow } from "./types";

const LAST_LEAGUE_KEY = "alpha-squad:last-league-id";
const rosterKeyFor = (leagueId: string) => `alpha-squad:last-roster-id:${leagueId}`;

interface LeagueContextValue {
  leagues: LeagueSummary[] | null;
  leaguesError: string | null;
  leagueId: string | null;
  setLeagueId: (id: string | null) => void;
  refreshLeagues: () => void;

  teams: TeamRosterRow[] | null;
  teamsSupported: boolean | null;
  teamsError: string | null;
  teamsLoading: boolean;
  refreshTeams: () => void;

  rosterId: number | null;
  setRosterId: (id: number | null) => void;
}

const LeagueCtx = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const [leagues, setLeagues] = useState<LeagueSummary[] | null>(null);
  const [leaguesError, setLeaguesError] = useState<string | null>(null);
  const [leagueId, setLeagueIdState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_LEAGUE_KEY);
    } catch {
      return null;
    }
  });

  const [teams, setTeams] = useState<TeamRosterRow[] | null>(null);
  const [teamsSupported, setTeamsSupported] = useState<boolean | null>(null);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [teamsReloadToken, setTeamsReloadToken] = useState(0);

  const [rosterId, setRosterIdState] = useState<number | null>(null);

  const loadLeagues = useCallback(() => {
    api
      .listLeagues()
      .then((rows) => {
        setLeagues(rows);
        setLeaguesError(null);
        setLeagueIdState((current) => {
          if (current && rows.some((r) => r.league_id === current)) return current;
          return rows[0]?.league_id ?? null;
        });
      })
      .catch((e) => setLeaguesError(String(e)));
  }, []);

  // Loads once on mount; refreshLeagues() (e.g. right after registering a new league) re-runs
  // it on demand instead of needing a second effect keyed on some other trigger.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => loadLeagues(), []);

  const setLeagueId = useCallback((id: string | null) => {
    setLeagueIdState(id);
    try {
      if (id) localStorage.setItem(LAST_LEAGUE_KEY, id);
    } catch {
      // per-browser convenience only
    }
  }, []);

  const setRosterId = useCallback(
    (id: number | null) => {
      setRosterIdState(id);
      if (leagueId) {
        try {
          if (id != null) localStorage.setItem(rosterKeyFor(leagueId), String(id));
        } catch {
          // per-browser convenience only
        }
      }
    },
    [leagueId],
  );

  useEffect(() => {
    if (!leagueId) {
      setTeams(null);
      setTeamsSupported(null);
      setRosterIdState(null);
      return;
    }
    setTeamsLoading(true);
    setTeamsError(null);
    api
      .getLeagueTeams(leagueId)
      .then((resp) => {
        setTeams(resp.teams);
        setTeamsSupported(resp.supported);
        let stored: number | null = null;
        try {
          const raw = localStorage.getItem(rosterKeyFor(leagueId));
          if (raw !== null) stored = Number(raw);
        } catch {
          // ignore
        }
        if (stored !== null && resp.teams.some((t) => t.roster_id === stored)) {
          setRosterIdState(stored);
        } else {
          setRosterIdState(resp.teams[0]?.roster_id ?? null);
        }
      })
      .catch((e) => setTeamsError(String(e)))
      .finally(() => setTeamsLoading(false));
  }, [leagueId, teamsReloadToken]);

  const refreshTeams = useCallback(() => setTeamsReloadToken((n) => n + 1), []);

  return (
    <LeagueCtx.Provider
      value={{
        leagues,
        leaguesError,
        leagueId,
        setLeagueId,
        refreshLeagues: loadLeagues,
        teams,
        teamsSupported,
        teamsError,
        teamsLoading,
        refreshTeams,
        rosterId,
        setRosterId,
      }}
    >
      {children}
    </LeagueCtx.Provider>
  );
}

export function useLeague(): LeagueContextValue {
  const ctx = useContext(LeagueCtx);
  if (!ctx) throw new Error("useLeague must be used within a LeagueProvider");
  return ctx;
}
