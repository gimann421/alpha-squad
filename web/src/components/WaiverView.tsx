import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import type { DecisionResponse } from "../types";
import { PlayerPicker } from "./PlayerPicker";

export function WaiverView() {
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const useRosterId = teamsSupported && rosterId != null;

  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [week, setWeek] = useState(1);
  const [playerId, setPlayerId] = useState("");
  const [rosterPositions, setRosterPositions] = useState("QB");
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
        roster_id: useRosterId ? (rosterId ?? undefined) : undefined,
        roster_positions: useRosterId
          ? undefined
          : rosterPositions
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
        the single FAAB bid returned below. Looking for a ranked list of every free agent
        instead? See the Action Center tab.
      </p>

      {!leagueId && <p className="muted">Connect and select a league above.</p>}

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
        {!useRosterId && (
          <label>
            Roster positions{" "}
            <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
          </label>
        )}
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
