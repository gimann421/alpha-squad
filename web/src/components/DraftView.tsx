import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type { DecisionResponse, RankingRow } from "../types";
import { PlayerPicker } from "./PlayerPicker";

// "I'm on the clock. Who should I take?" Calls the exact same M10 function the CLI/API already
// call (`recommend_draft_pick`) -- this panel has no independent scoring logic. `available_player_ids`
// is derived client-side as "every currently-ranked player minus who's already been drafted"
// (a plain id-set subtraction over data GET /rankings already returned, not a scoring
// decision) so repeated picks through a real draft don't require re-typing the whole pool.
export function DraftView() {
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [rosterPositions, setRosterPositions] = useState("");
  const [nextPick, setNextPick] = useState(10);
  const [ecrType, setEcrType] = useState("rsf");
  const [topN, setTopN] = useState(5);

  const [pool, setPool] = useState<RankingRow[] | null>(null);
  const [poolError, setPoolError] = useState<string | null>(null);
  const [draftedIds, setDraftedIds] = useState<string[]>([]);
  const [addDraftedId, setAddDraftedId] = useState("");

  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const nameFor = (playerId: string) => pool?.find((p) => p.player_id === playerId)?.display_name ?? playerId;

  async function loadPool() {
    setPoolError(null);
    try {
      const rows = await api.getRankings({ season, limit: 500 });
      setPool(rows);
    } catch (e) {
      setPoolError(String(e));
    }
  }

  useEffect(() => {
    loadPool();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season]);

  function addDrafted(playerId: string) {
    if (!playerId || draftedIds.includes(playerId)) return;
    setDraftedIds((ids) => [...ids, playerId]);
  }

  function removeDrafted(playerId: string) {
    setDraftedIds((ids) => ids.filter((id) => id !== playerId));
  }

  async function runDraft() {
    if (!leagueId || !pool) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const availableIds = pool.map((p) => p.player_id).filter((id) => !draftedIds.includes(id));
      const useRosterId = teamsSupported && rosterId != null;
      const result = await api.postDraft(leagueId, {
        season,
        roster_positions: useRosterId
          ? undefined
          : rosterPositions
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
        roster_id: useRosterId ? (rosterId ?? undefined) : undefined,
        available_player_ids: availableIds,
        next_pick_overall: nextPick,
        // D55: the engine prices in how much value at each position disappears before your
        // next turn. It needs to know where the draft is now -- every pick you have marked
        // drafted, plus the one you are on.
        current_pick_overall: draftedIds.length + 1,
        ecr_type: ecrType,
        top_n: topN,
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
      <h2>Draft</h2>
      <p className="muted">
        Calls the exact same M10 function the CLI does (`recommend_draft_pick`) — this panel has
        no independent scoring logic. As you draft, add each taken player to "already drafted"
        below so the next recommendation excludes them.
      </p>

      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Next pick # <input type="number" value={nextPick} onChange={(e) => setNextPick(Number(e.target.value))} />
        </label>
        <label>
          ECR type <input value={ecrType} onChange={(e) => setEcrType(e.target.value)} placeholder="rsf" />
        </label>
        <label>
          Top N alternatives <input type="number" value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
        </label>
        {!(teamsSupported && rosterId != null) && (
          <label>
            Roster positions{" "}
            <input value={rosterPositions} onChange={(e) => setRosterPositions(e.target.value)} placeholder="QB,RB" />
          </label>
        )}
      </div>

      <h3>Already drafted</h3>
      {poolError && <p className="error">Couldn't load the ranked player pool: {poolError}</p>}
      <div className="controls">
        <span className="picker-field">
          <span className="picker-field-label">Mark drafted</span>
          <PlayerPicker
            value={addDraftedId}
            onChange={(id) => {
              setAddDraftedId(id);
              if (id) {
                addDrafted(id);
                setAddDraftedId("");
              }
            }}
          />
        </span>
      </div>
      {draftedIds.length > 0 && (
        <ul className="action-list">
          {draftedIds.map((id) => (
            <li key={id}>
              {nameFor(id)} <button className="secondary" onClick={() => removeDrafted(id)}>undo</button>
            </li>
          ))}
        </ul>
      )}

      <div className="controls">
        <button onClick={runDraft} disabled={submitting || !leagueId || !pool}>
          {submitting ? "Recommending…" : "Who should I take?"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          <div>
            <strong>Recommended pick:</strong>{" "}
            <PlayerLink playerId={decision.recommendation}>{nameFor(decision.recommendation)}</PlayerLink>{" "}
            <button className="secondary" onClick={() => addDrafted(decision.recommendation)}>
              mark drafted
            </button>
          </div>
          <div>
            <strong>Expected value:</strong> {decision.expected_value?.toFixed(1) ?? "-"} ·{" "}
            <strong>Confidence:</strong> {decision.confidence?.toFixed(2) ?? "-"}
          </div>
          <div>
            <strong>Alternatives:</strong>{" "}
            {decision.alternatives.length === 0
              ? "none"
              : decision.alternatives.map((id, i) => (
                  <span key={id}>
                    {i > 0 && ", "}
                    <PlayerLink playerId={id}>{nameFor(id)}</PlayerLink>
                  </span>
                ))}
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
