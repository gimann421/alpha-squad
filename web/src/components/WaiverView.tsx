import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import type { DecisionResponse, LeagueSummary } from "../types";
import { PlayerPicker } from "./PlayerPicker";

const LAST_LEAGUE_STORAGE_KEY = "alpha-squad:last-league-id";

export function WaiverView() {
  const [leagues, setLeagues] = useState<LeagueSummary[] | null>(null);
  const [leaguesError, setLeaguesError] = useState<string | null>(null);
  const [leagueId, setLeagueId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_LEAGUE_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [week, setWeek] = useState(1);
  const [playerId, setPlayerId] = useState("");
  const [rosterPositions, setRosterPositions] = useState("QB");
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .listLeagues()
      .then((rows) => {
        setLeagues(rows);
        // Nothing picked yet (first visit, or a stored id that's no longer registered) --
        // default to the first registered league so the view is never stuck on nothing.
        if (!leagueId || !rows.some((r) => r.league_id === leagueId)) {
          setLeagueId(rows[0]?.league_id ?? null);
        }
      })
      .catch((e) => setLeaguesError(String(e)));
    // Only ever runs once on mount -- switching leagues afterward changes `leagueId`
    // directly via the dropdown, it doesn't need to re-list the registry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!leagueId) return;
    try {
      localStorage.setItem(LAST_LEAGUE_STORAGE_KEY, leagueId);
    } catch {
      // per-browser convenience only -- fine if storage is unavailable (private mode etc.)
    }
  }, [leagueId]);

  async function runWaiver() {
    if (!leagueId || !playerId.trim()) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const result = await api.postWaiver(leagueId, {
        season,
        week,
        player_id: playerId.trim(),
        roster_positions: rosterPositions
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setDecision(result);
    } catch (e) {
      setDecisionError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2>Waiver / FAAB</h2>
      <p className="muted">
        Calls the exact same M10 function the CLI does (`recommend_waiver_pickup`) — this panel
        has no independent scoring logic. Meaningful-role probability, dynasty value, a
        value-spike read from recent evidence, roster fit, and competing-bid likelihood all feed
        the single FAAB bid returned below.
      </p>

      <div className="controls">
        <label>
          League{" "}
          {leaguesError ? (
            <span className="error">Error: {leaguesError}</span>
          ) : (
            <select
              value={leagueId ?? ""}
              onChange={(e) => setLeagueId(e.target.value)}
              disabled={!leagues || leagues.length === 0}
            >
              {!leagues && <option>Loading…</option>}
              {leagues?.length === 0 && <option>No leagues registered</option>}
              {leagues?.map((l) => (
                <option key={l.league_id} value={l.league_id}>
                  {l.league_id} ({l.source})
                </option>
              ))}
            </select>
          )}
        </label>
      </div>

      <h3>Waiver recommendation</h3>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Week <input type="number" value={week} onChange={(e) => setWeek(Number(e.target.value))} />
        </label>
        <span className="picker-field">
          <span className="picker-field-label">Player</span>
          <PlayerPicker value={playerId} onChange={setPlayerId} />
        </span>
        <label>
          Roster positions{" "}
          <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
        </label>
        <button onClick={runWaiver} disabled={submitting || !leagueId || !playerId.trim()}>
          {submitting ? "Recommending…" : "Recommend"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          <div>
            <strong>Player:</strong> {decision.recommendation}
          </div>
          <div>
            <strong>Recommended FAAB bid:</strong>{" "}
            {decision.expected_value != null ? `$${decision.expected_value.toFixed(2)}` : "-"}
          </div>
          <div>
            <strong>Meaningful-role (top-24) probability:</strong>{" "}
            {decision.confidence != null ? decision.confidence.toFixed(2) : "-"}
          </div>
          <div className="reasons">
            <ul>
              {decision.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
          <div className="muted">Decision recorded: {decision.decision_id}</div>
        </div>
      )}
    </section>
  );
}
