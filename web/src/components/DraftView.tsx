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
  // Blank means "let the server resolve the board from the league" (D56):
  // a 1-QB league gets the 1-QB board, a superflex league the superflex one.
  const [ecrType, setEcrType] = useState("");
  const [topN, setTopN] = useState(5);

  const [pool, setPool] = useState<RankingRow[] | null>(null);
  const [poolError, setPoolError] = useState<string | null>(null);
  const [draftedIds, setDraftedIds] = useState<string[]>([]);
  const [addDraftedId, setAddDraftedId] = useState("");
  // Which of the drafted players are on MY team. Deliberately a separate list from
  // `draftedIds` (the league-wide pool): the engine's roster-aware value base needs my own
  // roster, and `draftedIds` is not it. See the request body below.
  const [myPickIds, setMyPickIds] = useState<string[]>([]);
  const [addMyPickId, setAddMyPickId] = useState("");
  const usingRealRoster = teamsSupported && rosterId != null;

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
    // My picks are a strict subset of the drafted pool -- un-drafting a player has to drop
    // him from my roster too, or the two lists disagree about who is even off the board.
    setMyPickIds((ids) => ids.filter((id) => id !== playerId));
  }

  // Taking a player both removes him from the board AND puts him on my roster, so this adds
  // to both lists. `draftedIds` keeps its existing league-wide meaning untouched; this only
  // adds the "which of them are mine" split.
  function addMyPick(playerId: string) {
    if (!playerId) return;
    addDrafted(playerId);
    setMyPickIds((ids) => (ids.includes(playerId) ? ids : [...ids, playerId]));
  }

  function removeMyPick(playerId: string) {
    setMyPickIds((ids) => ids.filter((id) => id !== playerId));
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
        // D60/D63/D67: the benchmarked roster-aware value base needs THIS team's own picks.
        // `draftedIds` is the league-wide drafted pool and must never be sent here -- it
        // would tell the engine "my roster already holds every position anyone has drafted",
        // which is actively wrong, not merely incomplete. `myPickIds` is the separate
        // my-picks list this view now tracks for exactly this purpose.
        //
        // Sent only when non-empty: `[]` asserts a KNOWN empty roster, and if the user
        // simply has not marked their picks that assertion is false -- so the engine keeps
        // its documented VORP fallback for an unknown roster instead. When a real Sleeper
        // team is connected the server resolves the actual roster from `roster_id` and that
        // supersedes this field entirely.
        roster_player_ids: myPickIds.length > 0 ? myPickIds : undefined,
        ecr_type: ecrType || undefined,
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
          ECR type <input value={ecrType} onChange={(e) => setEcrType(e.target.value)} placeholder="auto (from league)" />
        </label>
        <label>
          Top N alternatives <input type="number" value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
        </label>
        {!usingRealRoster && (
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

      {!usingRealRoster && (
        <>
          <h3>My picks</h3>
          <p className="muted">
            Which of the drafted players above are on <em>your</em> team — a separate list from
            the league-wide pool. This is what lets the engine price how much a candidate would
            actually improve your own starting lineup, rather than scoring him against
            league-wide replacement level alone. With a connected Sleeper team the server reads
            your real roster instead and this section is unnecessary.
          </p>
          <div className="controls">
            <span className="picker-field">
              <span className="picker-field-label">Mark my pick</span>
              <PlayerPicker
                value={addMyPickId}
                onChange={(id) => {
                  setAddMyPickId(id);
                  if (id) {
                    addMyPick(id);
                    setAddMyPickId("");
                  }
                }}
              />
            </span>
          </div>
          {myPickIds.length > 0 && (
            <ul className="action-list">
              {myPickIds.map((id) => (
                <li key={id}>
                  {nameFor(id)}{" "}
                  <button className="secondary" onClick={() => removeMyPick(id)}>
                    undo
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
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
            </button>{" "}
            {!usingRealRoster && (
              <button className="secondary" onClick={() => addMyPick(decision.recommendation)}>
                mark as my pick
              </button>
            )}
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
