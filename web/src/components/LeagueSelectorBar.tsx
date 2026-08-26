import { useState } from "react";
import { useLeague } from "../league-context";
import { ConnectLeaguePanel } from "./ConnectLeaguePanel";

// Always-visible league/team selector, replacing the old pattern of each view (Waiver/Trade/
// League) independently rendering its own league dropdown. One selection here drives every
// roster-aware page (Dashboard/My Team/Action Center/Draft/Waiver/Trade).
export function LeagueSelectorBar() {
  const { leagues, leaguesError, leagueId, setLeagueId, teams, teamsSupported, teamsLoading, rosterId, setRosterId } =
    useLeague();
  const [showConnect, setShowConnect] = useState(false);

  return (
    <div className="league-selector-bar">
      <div className="league-selector-controls">
        <label>
          League{" "}
          {leaguesError ? (
            <span className="error">Error: {leaguesError}</span>
          ) : (
            <select value={leagueId ?? ""} onChange={(e) => setLeagueId(e.target.value)} disabled={!leagues}>
              {!leagues && <option>Loading…</option>}
              {leagues?.length === 0 && <option value="">No leagues registered</option>}
              {leagues?.map((l) => (
                <option key={l.league_id} value={l.league_id}>
                  {l.league_id} ({l.source})
                </option>
              ))}
            </select>
          )}
        </label>

        {leagueId && teamsSupported && (
          <label>
            My team{" "}
            <select
              value={rosterId ?? ""}
              onChange={(e) => setRosterId(e.target.value ? Number(e.target.value) : null)}
              disabled={teamsLoading || !teams || teams.length === 0}
            >
              {teamsLoading && <option>Loading…</option>}
              {teams?.map((t) => (
                <option key={t.roster_id} value={t.roster_id}>
                  {t.team_name ?? t.owner_display_name ?? `Team ${t.roster_id}`}
                </option>
              ))}
            </select>
          </label>
        )}

        {leagueId && teamsSupported === false && (
          <span className="muted">This league has no real per-team roster data (manual config).</span>
        )}

        <button className="secondary" onClick={() => setShowConnect((v) => !v)}>
          {showConnect ? "Close" : "Connect league…"}
        </button>
      </div>
      {showConnect && <ConnectLeaguePanel onConnected={() => setShowConnect(false)} />}
    </div>
  );
}
