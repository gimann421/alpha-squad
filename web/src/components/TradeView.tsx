import { useEffect, useState } from "react";
import { api } from "../api";
import type { DecisionResponse, LeagueSummary } from "../types";

const LAST_LEAGUE_STORAGE_KEY = "alpha-squad:last-league-id";

export function TradeView() {
  const [leagues, setLeagues] = useState<LeagueSummary[] | null>(null);
  const [leaguesError, setLeaguesError] = useState<string | null>(null);
  const [leagueId, setLeagueId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_LEAGUE_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const [season, setSeason] = useState(2025);
  const [playerId, setPlayerId] = useState("");
  const [ecrType, setEcrType] = useState("rsf");
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

  async function runTrade() {
    if (!leagueId || !playerId.trim()) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const result = await api.postTrade(leagueId, {
        season,
        player_id: playerId.trim(),
        ecr_type: ecrType,
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
      <h2>Dynasty Trade</h2>
      <p className="muted">
        Calls the exact same M10 function the CLI does (`recommend_dynasty_trade`) — this panel
        has no independent scoring logic. This evaluates a single player's dynasty
        buy/hold/sell/watch value (real EDGE blended with real dynasty market value and a
        documented age-curve heuristic, docs/DECISIONS.md D25) — it does not compare multi-player
        trade packages, which is outside what the backend function computes today.
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

      <h3>Trade evaluation</h3>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Player ID <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} placeholder="00-0012345" />
        </label>
        <label>
          ECR type <input value={ecrType} onChange={(e) => setEcrType(e.target.value)} placeholder="rsf" />
        </label>
        <button onClick={runTrade} disabled={submitting || !leagueId || !playerId.trim()}>
          {submitting ? "Evaluating…" : "Evaluate"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          <div>
            <strong>Player:</strong> {decision.recommendation}
          </div>
          <div>
            <strong>Age-adjusted dynasty value:</strong>{" "}
            {decision.expected_value != null ? decision.expected_value.toFixed(0) : "-"}
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
