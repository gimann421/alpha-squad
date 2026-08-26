import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type { ActionCenterResponse, LeagueContext, MyTeamResponse } from "../types";
import { Badge } from "./common";
import { ConnectLeaguePanel } from "./ConnectLeaguePanel";

// "What should I be paying attention to right now?" The landing page: a condensed real
// summary of league + roster need + the top few action items, each pulled from the exact same
// endpoints My Team / Action Center use in full -- this view is a smaller slice, not a
// separate computation.
export function DashboardView() {
  const { leagues, leagueId, rosterId, teams, teamsSupported, teamsLoading } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);

  const [context, setContext] = useState<LeagueContext | null>(null);
  const [myTeam, setMyTeam] = useState<MyTeamResponse | null>(null);
  const [actions, setActions] = useState<ActionCenterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;
    api.getLeagueContext(leagueId).then(setContext).catch(() => setContext(null));
  }, [leagueId]);

  useEffect(() => {
    if (!leagueId || rosterId == null || !teamsSupported) {
      setMyTeam(null);
      setActions(null);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      api.getMyTeam(leagueId, { season, roster_id: rosterId }),
      api.getActionCenter(leagueId, { season, week: 1, roster_id: rosterId, add_top_n: 3, drop_top_n: 2 }),
    ])
      .then(([teamResult, actionResult]) => {
        setMyTeam(teamResult);
        setActions(actionResult);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [leagueId, rosterId, teamsSupported, season]);

  if (!leagues) {
    return (
      <section>
        <h2>Dashboard</h2>
        <p className="muted">Loading…</p>
      </section>
    );
  }

  if (leagues.length === 0 || !leagueId) {
    return (
      <section>
        <h2>Dashboard</h2>
        <p className="muted">Connect your league to get started.</p>
        <ConnectLeaguePanel />
      </section>
    );
  }

  const weakestNeeds = myTeam
    ? Object.entries(myTeam.positional_needs)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
    : [];

  const combinedActions = actions
    ? [
        ...actions.adds.map((a) => ({
          key: `add-${a.player_id}`,
          label: "ADD",
          playerId: a.player_id,
          name: a.display_name ?? a.player_id,
          detail: `bid $${a.recommended_bid.toFixed(2)}`,
        })),
        ...actions.drops.map((d) => ({
          key: `drop-${d.player_id}`,
          label: "DROP",
          playerId: d.player_id,
          name: d.display_name ?? d.player_id,
          detail: d.marginal_value != null ? `${d.marginal_value.toFixed(1)} VORP` : "",
        })),
        ...actions.trade_signals.map((s) => ({
          key: `trade-${s.player_id}`,
          label: s.edge_action,
          playerId: s.player_id,
          name: s.display_name ?? s.player_id,
          detail: s.summary,
        })),
      ].slice(0, 6)
    : [];

  return (
    <section>
      <h2>Dashboard</h2>

      {context && (
        <div className="card">
          <div>
            <strong>{context.league_id}</strong> — {context.format}, {context.teams} teams
          </div>
          {teams && teams.length > 0 && teamsSupported && (
            <div className="muted">
              {teams.find((t) => t.roster_id === rosterId)?.team_name ??
                teams.find((t) => t.roster_id === rosterId)?.owner_display_name ??
                "My team"}
            </div>
          )}
        </div>
      )}

      {teamsSupported === false && (
        <p className="muted">
          This league has no real per-team roster data (manually-configured) — roster-aware
          sections below aren't available; use Rankings/EDGE/Evidence/Draft/Trade directly.
        </p>
      )}

      {(loading || teamsLoading) && <p className="muted">Loading…</p>}
      {error && <p className="error">Couldn't reach the Alpha Squad API: {error}</p>}

      {myTeam && (
        <>
          <h3>Biggest roster needs</h3>
          {weakestNeeds.length === 0 ? (
            <p className="muted">No positional needs on record.</p>
          ) : (
            <ul className="action-list">
              {weakestNeeds.map(([pos, need]) => (
                <li key={pos}>
                  {pos}: need score {need.toFixed(2)}{" "}
                  {need >= 1 ? "(can't fill starting slots)" : need > 0 ? "(thin bench depth)" : "(saturated)"}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {actions && (
        <>
          <h3>Top action items</h3>
          {combinedActions.length === 0 ? (
            <p className="muted">Nothing urgent right now.</p>
          ) : (
            <ul className="action-list">
              {combinedActions.map((item) => (
                <li key={item.key}>
                  <Badge value={item.label} /> <PlayerLink playerId={item.playerId}>{item.name}</PlayerLink>{" "}
                  <span className="muted">{item.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
      </div>
    </section>
  );
}
