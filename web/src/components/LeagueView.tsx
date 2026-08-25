import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import type { DecisionResponse, LeagueContext, LeagueSummary } from "../types";
import { AsyncSection } from "./common";

const LAST_LEAGUE_STORAGE_KEY = "alpha-squad:last-league-id";

export function LeagueView() {
  const [leagues, setLeagues] = useState<LeagueSummary[] | null>(null);
  const [leaguesError, setLeaguesError] = useState<string | null>(null);
  const [leagueId, setLeagueId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_LEAGUE_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const [context, setContext] = useState<LeagueContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [rosterPositions, setRosterPositions] = useState("QB");
  const [availableIds, setAvailableIds] = useState("");
  const [nextPick, setNextPick] = useState(10);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [rosterNeed, setRosterNeed] = useState<Record<string, number> | null>(null);
  const [rosterNeedError, setRosterNeedError] = useState<string | null>(null);
  const [rosterNeedLoading, setRosterNeedLoading] = useState(false);

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
    setLoading(true);
    setError(null);
    api
      .getLeagueContext(leagueId)
      .then(setContext)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    // Switching leagues invalidates any roster-need read from the previous league's lineup.
    setRosterNeed(null);
    setRosterNeedError(null);
  }, [leagueId]);

  async function checkRosterNeed() {
    if (!leagueId) return;
    setRosterNeedLoading(true);
    setRosterNeedError(null);
    try {
      const result = await api.getRosterNeed(leagueId, rosterPositions);
      setRosterNeed(result.need);
    } catch (e) {
      setRosterNeedError(String(e));
    } finally {
      setRosterNeedLoading(false);
    }
  }

  async function runDraft() {
    if (!leagueId) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const ids = availableIds
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await api.postDraft(leagueId, {
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
      <h2>League</h2>
      <p className="muted">
        Every recommendation below calls the exact same M10 function the CLI does
        (`recommend_draft_pick`) — this panel has no independent scoring logic. A missing
        league context returns an explicit error, never a fabricated universal answer.
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
      <p className="muted">
        Calls the same `roster_need` the draft and waiver recommendations use internally
        (`league/roster.py`) — a positive score means the roster can't yet fill that position's
        starting slots, a small positive score means thin bench depth, and a negative score
        means the position is already saturated beyond a healthy bench.
      </p>
      <div className="controls">
        <label>
          Roster positions (used below for roster need and the draft recommendation){" "}
          <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
        </label>
        <button onClick={checkRosterNeed} disabled={rosterNeedLoading || !leagueId}>
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

      <h3>Draft recommendation</h3>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
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
