import { useEffect, useState } from "react";
import { api } from "../api";
import type { DecisionResponse, LeagueContext } from "../types";
import { AsyncSection } from "./common";

const LEAGUE_ID = "target_league";

export function LeagueView() {
  const [context, setContext] = useState<LeagueContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [season, setSeason] = useState(2025);
  const [rosterPositions, setRosterPositions] = useState("QB");
  const [availableIds, setAvailableIds] = useState("");
  const [nextPick, setNextPick] = useState(10);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .getLeagueContext(LEAGUE_ID)
      .then(setContext)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function runDraft() {
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const ids = availableIds
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await api.postDraft(LEAGUE_ID, {
        season,
        roster_positions: rosterPositions
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        available_player_ids: ids.length ? ids : undefined,
        next_pick_overall: nextPick,
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
      <h2>League — {LEAGUE_ID}</h2>
      <p className="muted">
        Every recommendation below calls the exact same M10 function the CLI does
        (`recommend_draft_pick`) — this panel has no independent scoring logic. A missing
        league context returns an explicit error, never a fabricated universal answer.
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

      <h3>Draft recommendation</h3>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Roster positions{" "}
          <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
        </label>
        <label>
          Next pick #{" "}
          <input type="number" value={nextPick} onChange={(e) => setNextPick(Number(e.target.value))} />
        </label>
        <label>
          Available player IDs (comma-separated, blank = all projected){" "}
          <input value={availableIds} onChange={(e) => setAvailableIds(e.target.value)} />
        </label>
        <button onClick={runDraft} disabled={submitting}>
          {submitting ? "Recommending…" : "Recommend"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          <div>
            <strong>Recommendation:</strong> {decision.recommendation}
          </div>
          <div>
            <strong>Alternatives:</strong> {decision.alternatives.join(", ") || "none"}
          </div>
          <div>
            <strong>Confidence:</strong> {decision.confidence != null ? decision.confidence.toFixed(2) : "-"}
          </div>
          <ul>
            {decision.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <div className="muted">Decision recorded: {decision.decision_id}</div>
        </div>
      )}
    </section>
  );
}
