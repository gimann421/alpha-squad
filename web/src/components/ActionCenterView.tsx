import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type { ActionCenterResponse } from "../types";
import { Badge } from "./common";

// The central "what should I do" view: pure aggregation of the real waiver-target, drop-
// candidate, and trade-signal engines (GET /league/{id}/actions), grouped by action type
// rather than forced onto a single fabricated cross-type ranking -- a FAAB dollar amount, a
// bench VORP deficit, and a market rank edge aren't comparable numbers.
export function ActionCenterView() {
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [week, setWeek] = useState(1);

  const [report, setReport] = useState<ActionCenterResponse | null>(null);
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
      .getActionCenter(leagueId, { season, week, roster_id: rosterId, add_top_n: 10, drop_top_n: 5 })
      .then(setReport)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [leagueId, rosterId, teamsSupported, season, week]);

  if (!leagueId) {
    return (
      <section>
        <h2>Action Center</h2>
        <p className="muted">Connect and select a league above.</p>
      </section>
    );
  }

  if (teamsSupported === false) {
    return (
      <section>
        <h2>Action Center</h2>
        <p className="muted">
          This league has no real per-team roster data — use the Waiver/Trade tabs directly with a
          manually-entered roster instead.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h2>Action Center</h2>
      <p className="muted">What should I be paying attention to right now?</p>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Week <input type="number" value={week} onChange={(e) => setWeek(Number(e.target.value))} />
        </label>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Couldn't reach the Alpha Squad API: {error}</p>}

      {report && (
        <div className="dashboard-grid">
          <div>
            <h3>Add (waiver / FAAB)</h3>
            {report.adds.length === 0 ? (
              <p className="muted">No real free-agent candidates found.</p>
            ) : (
              <ul className="action-list">
                {report.adds.map((a) => (
                  <li key={a.player_id}>
                    <div>
                      <strong>
                        <PlayerLink playerId={a.player_id}>{a.display_name ?? a.player_id}</PlayerLink>
                      </strong>{" "}
                      ({a.position}) — bid ${a.recommended_bid.toFixed(2)}
                    </div>
                    <div className="reasons">
                      <ul>
                        {a.reasons.slice(0, 2).map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3>Drop candidates</h3>
            {report.drops.length === 0 ? (
              <p className="muted">No clear drop candidates on the bench.</p>
            ) : (
              <ul className="action-list">
                {report.drops.map((d) => (
                  <li key={d.player_id}>
                    <div>
                      <strong>
                        <PlayerLink playerId={d.player_id}>{d.display_name ?? d.player_id}</PlayerLink>
                      </strong>{" "}
                      ({d.position ?? "?"})
                    </div>
                    <div className="reasons">
                      <ul>
                        {d.reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3>Trade signals (your roster)</h3>
            {report.trade_signals.length === 0 ? (
              <p className="muted">No BUY/SELL EDGE on any of your rostered players right now.</p>
            ) : (
              <ul className="action-list">
                {report.trade_signals.map((s) => (
                  <li key={s.player_id}>
                    <div>
                      <Badge value={s.edge_action} />{" "}
                      <strong>
                        <PlayerLink playerId={s.player_id}>{s.display_name ?? s.player_id}</PlayerLink>
                      </strong>
                    </div>
                    <div className="muted">{s.summary}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
