import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type { MyTeamResponse } from "../types";
import { Badge } from "./common";

// "Show me what is wrong with my roster." Every number is a direct read of what
// GET /league/{id}/my-team already computed (real roster, joined with projection/uncertainty/
// EDGE/dynasty value, plus real positional need/scarcity/replacement level and a real
// starter/bench split) -- this view only renders it.
export function MyTeamView() {
  const { leagueId, rosterId, teamsSupported, teamsLoading } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);

  const [report, setReport] = useState<MyTeamResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!leagueId || rosterId == null || !teamsSupported) {
      setReport(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .getMyTeam(leagueId, { season, roster_id: rosterId })
      .then(setReport)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [leagueId, rosterId, teamsSupported, season]);

  if (!leagueId) {
    return (
      <section>
        <h2>My Team</h2>
        <p className="muted">Connect and select a league above to see your roster.</p>
      </section>
    );
  }

  if (teamsSupported === false) {
    return (
      <section>
        <h2>My Team</h2>
        <p className="muted">
          This league has no real per-team roster data (it's a manually-configured league, not
          Sleeper-connected) — roster intelligence isn't available for it.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h2>My Team</h2>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
      </div>

      {(loading || teamsLoading) && <p className="muted">Loading…</p>}
      {error && <p className="error">Couldn't reach the Alpha Squad API: {error}</p>}

      {report && (
        <>
          <div className="card">
            <div>
              <strong>{report.team_name ?? report.owner_display_name ?? `Team ${report.roster_id}`}</strong>
            </div>
            <div>Total projected points: {report.total_projected_points.toFixed(1)}</div>
            {report.unmapped_player_count > 0 && (
              <div className="muted">
                {report.unmapped_player_count} rostered player(s) not yet in Alpha Squad's identity
                crosswalk (not shown below).
              </div>
            )}
          </div>

          <h3>Positional strengths &amp; weaknesses</h3>
          <table>
            <thead>
              <tr>
                <th>Position</th>
                <th>Need score</th>
                <th>Scarcity</th>
                <th>Replacement level</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(report.positional_needs).map((pos) => (
                <tr key={pos}>
                  <td>{pos}</td>
                  <td>{report.positional_needs[pos].toFixed(2)}</td>
                  <td>{report.positional_scarcity[pos]?.toFixed(1) ?? "-"}</td>
                  <td>{report.replacement_levels[pos]?.toFixed(1) ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Positive need = can't yet fill starting slots; small positive = thin bench depth; negative =
            saturated beyond healthy bench depth.
          </p>

          <h3>Roster</h3>
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th>Role</th>
                <th>Projection</th>
                <th>p10–p90</th>
                <th>Market rank</th>
                <th>EDGE</th>
                <th>Dynasty value</th>
                <th>VORP</th>
              </tr>
            </thead>
            <tbody>
              {report.players.map((p) => (
                <tr key={p.player_id}>
                  <td>
                    <PlayerLink playerId={p.player_id}>{p.display_name ?? p.player_id}</PlayerLink>
                  </td>
                  <td>{p.position}</td>
                  <td>{p.is_starter ? "Starter" : "Bench"}</td>
                  <td>{p.projection?.toFixed(1) ?? "-"}</td>
                  <td>
                    {p.p10?.toFixed(0) ?? "-"} – {p.p90?.toFixed(0) ?? "-"}
                  </td>
                  <td>{p.market_rank ?? "-"}</td>
                  <td>{p.edge_action ? <Badge value={p.edge_action} /> : "-"}</td>
                  <td>{p.dynasty_value?.toFixed(0) ?? "-"}</td>
                  <td>{p.marginal_value != null ? p.marginal_value.toFixed(1) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
