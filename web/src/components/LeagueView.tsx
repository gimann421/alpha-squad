import { useEffect, useState } from "react";
import { api } from "../api";
import { useLeague } from "../league-context";
import type { LeagueContext } from "../types";
import { AsyncSection } from "./common";

// League settings/context + roster-need lookup. League/team selection itself now lives in the
// always-visible LeagueSelectorBar (App.tsx) -- this view just reads the shared selection.
// Draft recommendations moved to their own Draft tab.
export function LeagueView() {
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const [context, setContext] = useState<LeagueContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [rosterPositions, setRosterPositions] = useState("QB");
  const [rosterNeed, setRosterNeed] = useState<Record<string, number> | null>(null);
  const [rosterNeedError, setRosterNeedError] = useState<string | null>(null);
  const [rosterNeedLoading, setRosterNeedLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    setLoading(true);
    setError(null);
    api
      .getLeagueContext(leagueId)
      .then(setContext)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    setRosterNeed(null);
    setRosterNeedError(null);
  }, [leagueId]);

  async function checkRosterNeed() {
    if (!leagueId) return;
    setRosterNeedLoading(true);
    setRosterNeedError(null);
    try {
      const useRosterId = teamsSupported && rosterId != null;
      const result = await api.getRosterNeed(leagueId, {
        roster_id: useRosterId ? (rosterId ?? undefined) : undefined,
        roster_positions: useRosterId ? undefined : rosterPositions,
      });
      setRosterNeed(result.need);
    } catch (e) {
      setRosterNeedError(String(e));
    } finally {
      setRosterNeedLoading(false);
    }
  }

  if (!leagueId) {
    return (
      <section>
        <h2>League</h2>
        <p className="muted">Connect and select a league above.</p>
      </section>
    );
  }

  return (
    <section>
      <h2>League</h2>
      <p className="muted">
        Real league settings and roster need — calls the same `roster_need` the draft and waiver
        recommendations use internally (`league/roster.py`).
      </p>

      <AsyncSection
        loading={loading}
        error={error}
        data={context}
        render={(ctx) => (
          <div className="card">
            <div>
              <strong>Format:</strong> {ctx.format} · <strong>Teams:</strong> {ctx.teams}
            </div>
            <div>
              <strong>Lineup:</strong>{" "}
              {Object.entries(ctx.lineup)
                .map(([pos, n]) => `${pos}×${n}`)
                .join(", ")}
            </div>
          </div>
        )}
      />

      <h3>Roster need</h3>
      <div className="controls">
        {!(teamsSupported && rosterId != null) && (
          <label>
            Roster positions{" "}
            <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
          </label>
        )}
        <button onClick={checkRosterNeed} disabled={rosterNeedLoading}>
          {rosterNeedLoading ? "Checking…" : "Check roster need"}
        </button>
      </div>
      {rosterNeedError && <p className="error">Error: {rosterNeedError}</p>}
      {rosterNeed && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Position</th>
                <th>Need score</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(rosterNeed).map(([pos, need]) => (
                <tr key={pos}>
                  <td>{pos}</td>
                  <td>{need.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
