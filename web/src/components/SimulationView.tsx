import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import type { SimulationResponse } from "../types";

export function SimulationView() {
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [team, setTeam] = useState("KC");
  const [nSimulations, setNSimulations] = useState(1000);
  const [result, setResult] = useState<SimulationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function runSimulation() {
    if (!team.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const body = await api.postSimulation({
        team: team.trim().toUpperCase(),
        season,
        n_simulations: nSimulations,
      });
      setResult(body);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2>Team Simulation</h2>
      <p className="muted">
        Calls the exact same M13 function the CLI does (`simulate_team_season`) — this panel has
        no independent simulation logic. Every trial draws one joint (plays, pass_rate,
        team_points) sample from the team's real historical covariance, and every rostered
        player's simulated points come from that same trial's draw via their real opportunity
        share and efficiency, which is what makes players who share a team environment come out
        genuinely correlated (docs/DECISIONS.md D8, D29) — see the QB/WR1 stack correlation below.
      </p>

      <div className="controls">
        <label>
          Team{" "}
          <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="KC" style={{ width: "4em" }} />
        </label>
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Simulations{" "}
          <input
            type="number"
            value={nSimulations}
            onChange={(e) => setNSimulations(Number(e.target.value))}
            step={100}
            min={100}
          />
        </label>
        <button onClick={runSimulation} disabled={submitting || !team.trim()}>
          {submitting ? "Simulating…" : "Run simulation"}
        </button>
      </div>

      {error && <p className="error">Error: {error}</p>}

      {result && (
        <>
          <div className="card">
            <div>
              <strong>
                {result.team} {result.season}
              </strong>{" "}
              — {result.n_simulations} simulations × {result.n_weeks} weeks
            </div>
            <div>
              <strong>Mean team points:</strong> {result.mean_team_points.toFixed(1)} (std{" "}
              {result.std_team_points.toFixed(1)})
            </div>
            <div>
              <strong>QB/WR1 stack correlation:</strong>{" "}
              {result.qb_wr1_correlation != null ? result.qb_wr1_correlation.toFixed(3) : "-"}
            </div>
            <div>
              <strong>Same-position (WR/TE) correlation:</strong>{" "}
              {result.same_position_correlation != null
                ? result.same_position_correlation.toFixed(3)
                : "-"}
            </div>
            <div className="muted">Simulation run recorded: {result.run_id}</div>
          </div>

          <h3>Player-level simulated season totals</h3>
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th>Mean</th>
                <th>Std</th>
                <th>p10-p90</th>
              </tr>
            </thead>
            <tbody>
              {result.players.map((p) => (
                <tr key={p.player_id}>
                  <td>{p.display_name ?? p.player_id}</td>
                  <td>{p.position}</td>
                  <td>{p.mean_points.toFixed(1)}</td>
                  <td>{p.std_points.toFixed(1)}</td>
                  <td>
                    {p.p10.toFixed(0)} – {p.p90.toFixed(0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
