import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type {
  ClaudeReviewResponse,
  DecisionResponse,
  LeagueContext,
  RankingRow,
  SleeperDraftState,
} from "../types";
import { PlayerPicker } from "./PlayerPicker";

// PART 1 (2026-09-03 product-gap request): a reasonable, non-aggressive refresh cadence for a
// live draft assistant -- frequent enough that a real draft doesn't feel stale, far below any
// rate limit.
const SLEEPER_POLL_INTERVAL_MS = 8000;

// PART 3: state is scoped to league_id, never one global draft-state object, and split by mode
// -- a Sleeper league's own completed picks are NEVER what's persisted here (they always come
// live from GET /league/{id}/sleeper-draft and must never be overridden by a stale local copy);
// only UI prefs (season/ecr/topN) and, for a genuinely manual/non-Sleeper league, the
// hand-tracked pick lists are.
function draftStateKey(leagueId: string, mode: "sleeper" | "manual"): string {
  return `alpha-squad:draft-view:${mode}:${leagueId}`;
}

interface PersistedUiPrefs {
  season?: number;
  nextPick?: number;
  ecrType?: string;
  topN?: number;
}
interface PersistedManualState extends PersistedUiPrefs {
  rosterPositions?: string;
  draftedIds?: string[];
  myPickIds?: string[];
}

function loadJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? (parsed as T) : null;
  } catch {
    return null; // corrupted/invalid stored state fails safely -- caller falls back to defaults
  }
}

function saveJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // per-browser convenience only
  }
}

// "I'm on the clock. Who should I take?" Calls the exact same M10 function the CLI/API already
// call (`recommend_draft_pick`) -- this panel has no independent scoring logic.
//
// Two draft-tracking modes:
//  - Sleeper-connected (a real roster_id): PART 1 polls GET /league/{id}/sleeper-draft, which
//    reconstructs the board from Sleeper's own authoritative completed-pick feed. The user never
//    types an opponent's pick; this view only ever *reads* Sleeper's state.
//  - Manual/non-Sleeper: unchanged from before -- `available_player_ids` is "every ranked player
//    minus who's been marked drafted" (a plain id-set subtraction, not a scoring decision).
export function DraftView() {
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const usingRealRoster = Boolean(teamsSupported && rosterId != null);
  const mode: "sleeper" | "manual" = usingRealRoster ? "sleeper" : "manual";

  const [season, setSeason] = useState(latestSeason);
  const [rosterPositions, setRosterPositions] = useState("");
  const [nextPick, setNextPick] = useState(10);
  // Blank means "let the server resolve the board from the league" (D56).
  const [ecrType, setEcrType] = useState("");
  const [topN, setTopN] = useState(5);

  // Manual-mode-only tracked lists (unused/hidden once a real Sleeper roster is connected).
  const [draftedIds, setDraftedIds] = useState<string[]>([]);
  const [addDraftedId, setAddDraftedId] = useState("");
  const [myPickIds, setMyPickIds] = useState<string[]>([]);
  const [addMyPickId, setAddMyPickId] = useState("");

  const [pool, setPool] = useState<RankingRow[] | null>(null);
  const [poolError, setPoolError] = useState<string | null>(null);

  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [leagueContext, setLeagueContext] = useState<LeagueContext | null>(null);

  const [draftSync, setDraftSync] = useState<SleeperDraftState | null>(null);
  const [draftSyncError, setDraftSyncError] = useState<string | null>(null);

  // How many real picks had landed (across the whole league) when the current `decision` was
  // computed -- lets the UI flag a recommendation as stale the instant a NEW pick comes in
  // from Sleeper before the user acts on it (Phase 3/6: "no stale recommendation survives a
  // material board change"). `null` while no decision has been requested yet.
  const [decisionPickCount, setDecisionPickCount] = useState<number | null>(null);

  // Stage 1 Claude strategic decision layer (D74). Opt-in and separate from Alpha's own
  // recommendation request: Alpha must stay immediately available with zero dependency on
  // Claude (Phase 6), so this is a second, independent, non-blocking call the user triggers
  // deliberately -- never automatic on every pick, both for latency and API-cost discipline
  // during a real live draft (Phase 11/15/16).
  const [claudeReview, setClaudeReview] = useState<ClaudeReviewResponse | null>(null);
  const [claudeReviewError, setClaudeReviewError] = useState<string | null>(null);
  const [claudeReviewLoading, setClaudeReviewLoading] = useState(false);
  const [claudeReviewPickCount, setClaudeReviewPickCount] = useState<number | null>(null);

  const nameFor = (playerId: string) =>
    pool?.find((p) => p.player_id === playerId)?.display_name ??
    draftSync?.picks.find((p) => p.player_id === playerId)?.display_name ??
    playerId;

  // Load persisted state whenever the league or mode changes -- restores season/ECR/topN
  // always, and (manual mode only) the hand-tracked pick lists. Corrupted/invalid stored JSON
  // (loadJson returns null) just falls back to the current in-memory defaults rather than
  // throwing. `hydrated` gates the save effect below: without it, the save effect's *own*
  // first invocation for this league/mode fires in the same commit as this one, before the
  // setState calls here have flowed into a new render -- so it would see the OLD (pre-load)
  // state and immediately overwrite the just-read persisted value with stale defaults. This is
  // not a hypothetical: it reproduces every time under React StrictMode's double-effect-invoke
  // and was caught by a real reload-and-check with Playwright, not just reasoned about.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    setHydrated(false);
    if (!leagueId) return;
    const persisted = loadJson<PersistedManualState>(draftStateKey(leagueId, mode));
    if (persisted?.season) setSeason(persisted.season);
    else setSeason(latestSeason);
    if (persisted?.nextPick) setNextPick(persisted.nextPick);
    if (persisted?.ecrType !== undefined) setEcrType(persisted.ecrType);
    if (persisted?.topN) setTopN(persisted.topN);
    if (mode === "manual") {
      setRosterPositions(persisted?.rosterPositions ?? "");
      setDraftedIds(persisted?.draftedIds ?? []);
      setMyPickIds(persisted?.myPickIds ?? []);
    }
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leagueId, mode]);

  // Persist UI prefs (both modes) and manual pick-tracking (manual mode only) on every change,
  // but only once this league/mode's persisted state has actually been loaded (see `hydrated`
  // above) -- otherwise this fires with default/pre-load state and clobbers the real data.
  useEffect(() => {
    if (!leagueId || !hydrated) return;
    const value: PersistedManualState = { season, nextPick, ecrType, topN };
    if (mode === "manual") {
      value.rosterPositions = rosterPositions;
      value.draftedIds = draftedIds;
      value.myPickIds = myPickIds;
    }
    saveJson(draftStateKey(leagueId, mode), value);
  }, [leagueId, mode, hydrated, season, nextPick, ecrType, topN, rosterPositions, draftedIds, myPickIds]);

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

  useEffect(() => {
    if (!leagueId) {
      setLeagueContext(null);
      return;
    }
    api
      .getLeagueContext(leagueId)
      .then(setLeagueContext)
      .catch(() => setLeagueContext(null)); // disclosure-only; never blocks the draft panel
  }, [leagueId]);

  // PART 1: poll Sleeper's authoritative draft state for a connected league. Stops polling once
  // the draft reports complete (nothing left to sync) -- a "reasonable interval... not an
  // aggressive polling loop" per the request.
  useEffect(() => {
    if (!usingRealRoster || !leagueId || rosterId == null) {
      setDraftSync(null);
      setDraftSyncError(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const state = await api.getSleeperDraft(leagueId!, { roster_id: rosterId! });
        if (cancelled) return;
        setDraftSync(state);
        setDraftSyncError(null);
        if (state.status !== "complete") {
          timer = setTimeout(poll, SLEEPER_POLL_INTERVAL_MS);
        }
      } catch (e) {
        // A transient Sleeper failure keeps showing the last known state (never wipes it) and
        // keeps polling -- exactly "handle temporary Sleeper errors" without losing the board.
        if (!cancelled) {
          setDraftSyncError(String(e));
          timer = setTimeout(poll, SLEEPER_POLL_INTERVAL_MS);
        }
      }
    }
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [usingRealRoster, leagueId, rosterId]);

  // Auto-recommend the instant it becomes the user's turn (PART 1: "detect when it is the
  // user's turn... refresh/recompute the recommendation when relevant"). Tracked via a ref so
  // this fires once on the true->false->true transition, not on every unrelated poll tick.
  const wasUsersTurn = useRef<boolean | null>(null);

  // Reset that transition-tracking ref whenever the connected league/roster changes. Without
  // this, switching from a league where it was already the user's turn (ref left at `true`)
  // into a different league that also happens to open on the user's turn would read as "no
  // transition" and silently skip the auto-recommend for the new league/roster.
  useEffect(() => {
    wasUsersTurn.current = null;
  }, [leagueId, rosterId]);

  useEffect(() => {
    if (!usingRealRoster || !draftSync || !pool) return;
    const isTurnNow = draftSync.is_users_turn === true;
    if (isTurnNow && wasUsersTurn.current !== true) {
      runDraft();
    }
    wasUsersTurn.current = draftSync.is_users_turn;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftSync?.is_users_turn, draftSync?.drafted_player_ids.length, usingRealRoster, pool]);

  function addDrafted(playerId: string) {
    if (!playerId || draftedIds.includes(playerId)) return;
    setDraftedIds((ids) => [...ids, playerId]);
  }

  function removeDrafted(playerId: string) {
    setDraftedIds((ids) => ids.filter((id) => id !== playerId));
    setMyPickIds((ids) => ids.filter((id) => id !== playerId));
  }

  function addMyPick(playerId: string) {
    if (!playerId) return;
    addDrafted(playerId);
    setMyPickIds((ids) => (ids.includes(playerId) ? ids : [...ids, playerId]));
  }

  function removeMyPick(playerId: string) {
    setMyPickIds((ids) => ids.filter((id) => id !== playerId));
  }

  // Shared by `runDraft` and `runClaudeReview` -- both endpoints take the same request shape
  // (api/schemas.py::ClaudeDraftReviewRequest extends DraftRequest), and building it in one
  // place means the two calls can never silently drift into asking about different boards.
  function buildDraftRequestBody() {
    if (!pool) return null;
    // PART 1: for a Sleeper-connected draft, drafted ids / current-pick / next-pick all come
    // from the live sync rather than manual tracking. `roster_player_ids` is intentionally
    // left unsent here -- the server resolves this team's real roster from `roster_id` and
    // that supersedes any client-supplied list (see api/routers/league.py::post_draft).
    const draftedFromSync = usingRealRoster ? (draftSync?.drafted_player_ids ?? []) : draftedIds;
    const availableIds = pool.map((p) => p.player_id).filter((id) => !draftedFromSync.includes(id));
    return {
      season,
      roster_positions: usingRealRoster
        ? undefined
        : rosterPositions
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
      roster_id: usingRealRoster ? (rosterId ?? undefined) : undefined,
      available_player_ids: availableIds,
      next_pick_overall: usingRealRoster ? (draftSync?.next_pick_overall ?? undefined) : nextPick,
      current_pick_overall: usingRealRoster
        ? (draftSync?.current_pick_overall ?? undefined)
        : draftedIds.length + 1,
      roster_player_ids: !usingRealRoster && myPickIds.length > 0 ? myPickIds : undefined,
      ecr_type: ecrType || undefined,
      top_n: topN,
    };
  }

  async function runDraft() {
    if (!leagueId || !pool) return;
    // A connected Sleeper draft's first sync is asynchronous: without this guard, a click (or
    // the auto-recommend effect, which already checks `draftSync` itself) landing before the
    // initial poll resolves would treat NO players as drafted yet and could recommend someone
    // already off the board -- exactly the "recommendation reflects the correct roster state"
    // failure this hardening pass targets. Manual mode has no such fetch to wait for.
    if (usingRealRoster && !draftSync) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    // A fresh Alpha recommendation makes any prior Claude review stale by construction (it
    // reviewed the OLD recommendation) -- clear it rather than leaving a mismatched opinion on
    // screen next to the new pick.
    setClaudeReview(null);
    setClaudeReviewError(null);
    try {
      const body = buildDraftRequestBody();
      if (!body) return;
      const result = await api.postDraft(leagueId, body);
      setDecision(result);
      setDecisionPickCount(usingRealRoster ? (draftSync?.drafted_player_ids.length ?? null) : null);
    } catch (e) {
      setDecisionError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function runClaudeReview() {
    if (!leagueId || !pool) return;
    if (usingRealRoster && !draftSync) return;
    setClaudeReviewLoading(true);
    setClaudeReviewError(null);
    try {
      const body = buildDraftRequestBody();
      if (!body) return;
      const result = await api.postDraftClaudeReview(leagueId, {
        ...body,
        is_users_turn: usingRealRoster ? draftSync?.is_users_turn : undefined,
      });
      setClaudeReview(result);
      setClaudeReviewPickCount(usingRealRoster ? (draftSync?.drafted_player_ids.length ?? null) : null);
    } catch (e) {
      setClaudeReviewError(String(e));
    } finally {
      setClaudeReviewLoading(false);
    }
  }

  // A material board change (a new real pick landing) since this recommendation was computed
  // means it may no longer reflect who's actually still available (Phase 3/6: "no stale
  // recommendation survives a material board change"). This never hides or auto-clears the
  // recommendation -- during a live draft the user may still want to see it -- it only flags
  // that it should be refreshed before acting on it.
  const decisionIsStale =
    usingRealRoster &&
    decision != null &&
    decisionPickCount != null &&
    (draftSync?.drafted_player_ids.length ?? decisionPickCount) !== decisionPickCount;

  // Same staleness check as Alpha's own recommendation, applied to the Claude review (Phase
  // 11: "a Claude decision must become invalid if the underlying draft context materially
  // changes... do not blindly apply the old Claude response to the new board"). The board's
  // `context_fingerprint` (echoed back from the server) is the authoritative identity check
  // server-side; this pick-count comparison is the same cheap client-side proxy for it Alpha's
  // own staleness banner already uses, so both banners behave identically to the user.
  const claudeReviewIsStale =
    usingRealRoster &&
    claudeReview != null &&
    claudeReviewPickCount != null &&
    (draftSync?.drafted_player_ids.length ?? claudeReviewPickCount) !== claudeReviewPickCount;

  const pprValue = leagueContext ? (leagueContext.scoring as Record<string, unknown>)?.ppr_value : undefined;
  const scoringMismatch =
    leagueContext?.source === "sleeper" && typeof pprValue === "number" && Math.abs(pprValue - 1.0) > 1e-9;

  const syncStatus = draftSync?.status ?? null;

  return (
    <section>
      <h2>Draft</h2>
      <p className="muted">
        Calls the exact same M10 function the CLI does (`recommend_draft_pick`) — this panel has
        no independent scoring logic.{" "}
        {usingRealRoster
          ? "Connected to Sleeper: picks sync automatically from your league's real draft."
          : "As you draft, add each taken player to \"already drafted\" below so the next recommendation excludes them."}
      </p>

      {scoringMismatch && (
        <p className="error">
          This league scores {Number(pprValue).toFixed(2)} pts/reception. Alpha Squad's
          projections assume full PPR (1.0 pt/reception) — recommendations may under- or
          over-value pass-catchers relative to your league's real scoring.
        </p>
      )}

      {usingRealRoster && (
        <div className="card">
          {draftSyncError && (
            <p className="error">Sleeper sync issue (showing last known state): {draftSyncError}</p>
          )}
          {syncStatus === "no_draft" && <p className="muted">No Sleeper draft found for this league yet.</p>}
          {syncStatus === "pre_draft" && <p className="muted">Draft not started yet.</p>}
          {syncStatus === "paused" && <p className="muted">Draft paused.</p>}
          {syncStatus === "complete" && <p className="muted">Draft complete.</p>}
          {syncStatus === "drafting" && draftSync && (
            <p>
              <strong>Pick #{draftSync.current_pick_overall ?? "?"}</strong> on the clock
              {draftSync.on_the_clock_roster_id != null && ` (roster ${draftSync.on_the_clock_roster_id})`}
              {draftSync.is_users_turn ? " — your turn!" : ""}
              {draftSync.next_pick_overall != null && (
                <> · your next pick: #{draftSync.next_pick_overall}</>
              )}
            </p>
          )}
          {draftSync && draftSync.unmapped_sleeper_ids.length > 0 && (
            <p className="muted">
              {draftSync.unmapped_sleeper_ids.length} drafted player(s) could not be matched to
              Alpha Squad's player database (shown as "unmapped player" below) and are not
              removed from the available pool for the recommendation.
            </p>
          )}
        </div>
      )}

      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        {!usingRealRoster && (
          <label>
            Next pick # <input type="number" value={nextPick} onChange={(e) => setNextPick(Number(e.target.value))} />
          </label>
        )}
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

      {poolError && <p className="error">Couldn't load the ranked player pool: {poolError}</p>}

      {usingRealRoster ? (
        <>
          <h3>Drafted so far (from Sleeper)</h3>
          {draftSync && draftSync.picks.length > 0 ? (
            <ul className="action-list">
              {draftSync.picks.map((p) => (
                <li key={p.pick_no}>
                  #{p.pick_no} (round {p.round}): {p.display_name ?? (p.player_id ? nameFor(p.player_id) : "unmapped player")}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No picks reported yet.</p>
          )}
          <h3>My picks (from Sleeper)</h3>
          {draftSync && rosterId != null && draftSync.picks.some((p) => p.roster_id === rosterId) ? (
            <ul className="action-list">
              {draftSync.picks
                .filter((p) => p.roster_id === rosterId)
                .map((p) => (
                  <li key={p.pick_no}>
                    #{p.pick_no}: {p.display_name ?? (p.player_id ? nameFor(p.player_id) : "unmapped player")}
                  </li>
                ))}
            </ul>
          ) : (
            <p className="muted">None yet.</p>
          )}
        </>
      ) : (
        <>
          <h3>Already drafted</h3>
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
        <button
          onClick={runDraft}
          disabled={
            submitting ||
            !leagueId ||
            !pool ||
            (usingRealRoster && !draftSync) ||
            syncStatus === "complete"
          }
        >
          {submitting
            ? "Recommending…"
            : syncStatus === "complete"
              ? "Draft complete"
              : usingRealRoster && !draftSync
                ? "Waiting for Sleeper sync…"
                : "Who should I take?"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          {decisionIsStale && (
            <p className="error">
              A new pick has come in since this recommendation was computed — refresh ("Who
              should I take?") before acting on it.
            </p>
          )}
          <div>
            <strong>Recommended pick:</strong>{" "}
            <PlayerLink playerId={decision.recommendation}>{nameFor(decision.recommendation)}</PlayerLink>{" "}
            {!usingRealRoster && (
              <>
                <button className="secondary" onClick={() => addDrafted(decision.recommendation)}>
                  mark drafted
                </button>{" "}
                <button className="secondary" onClick={() => addMyPick(decision.recommendation)}>
                  mark as my pick
                </button>
              </>
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
          {decision.trace && decision.trace.runner_up_player_id && (
            <p className="muted">
              Beat runner-up <PlayerLink playerId={decision.trace.runner_up_player_id}>
                {nameFor(decision.trace.runner_up_player_id)}
              </PlayerLink>{" "}
              by {decision.trace.score_gap_to_runner_up?.toFixed(1) ?? "-"} score pts, out of{" "}
              {decision.trace.available_pool_size} evaluable players on the board.
            </p>
          )}
          {decision.trace && decision.trace.top_candidates.length > 1 && (
            <details>
              <summary>Decision trace: all {decision.trace.top_candidates.length} candidates considered</summary>
              <table>
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Pos</th>
                    <th>Score</th>
                    <th>VORP</th>
                    <th>MSV</th>
                    <th>Survival</th>
                  </tr>
                </thead>
                <tbody>
                  {decision.trace.top_candidates.map((c) => (
                    <tr key={c.player_id}>
                      <td>{nameFor(c.player_id)}</td>
                      <td>{c.position}</td>
                      <td>{c.score.toFixed(1)}</td>
                      <td>{c.vorp.toFixed(1)}</td>
                      <td>{c.marginal_starter_value?.toFixed(1) ?? "-"}</td>
                      <td>{c.survival_probability != null ? `${(c.survival_probability * 100).toFixed(0)}%` : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          <div className="muted">Decision recorded: {decision.decision_id}</div>

          <div className="controls">
            <button
              className="secondary"
              onClick={runClaudeReview}
              disabled={claudeReviewLoading || (usingRealRoster && !draftSync) || syncStatus === "complete"}
            >
              {claudeReviewLoading ? "Claude is thinking…" : "Get Claude's strategic review"}
            </button>
          </div>
          {claudeReviewError && (
            <p className="error">Claude review unavailable right now: {claudeReviewError}</p>
          )}
          {claudeReview && (
            <div className="card">
              {claudeReviewIsStale && (
                <p className="error">
                  A new pick has come in since Claude reviewed this board — refresh before
                  trusting this opinion.
                </p>
              )}
              {claudeReview.status !== "ok" && (
                <p className="muted">
                  Claude's strategic review isn't available for this pick ({claudeReview.status.replace(/_/g, " ")}
                  {claudeReview.error_message ? `: ${claudeReview.error_message}` : ""}). Alpha's
                  recommendation above is unaffected.
                </p>
              )}
              {claudeReview.status === "ok" && claudeReview.decision && (
                <>
                  <div>
                    {claudeReview.agrees_with_alpha ? (
                      <strong>✓ Claude agrees with Alpha: {nameFor(claudeReview.decision.selected_player_id)}</strong>
                    ) : (
                      <strong>
                        ⚠ Claude override: {nameFor(claudeReview.decision.selected_player_id)} over{" "}
                        {nameFor(claudeReview.alpha.recommendation)}
                      </strong>
                    )}
                  </div>
                  <div>
                    <strong>Claude confidence:</strong> {claudeReview.decision.confidence.toFixed(2)}
                  </div>
                  {claudeReview.decision.override_reason && (
                    <div>
                      <strong>Reason:</strong> {claudeReview.decision.override_reason}
                    </div>
                  )}
                  {claudeReview.decision.key_factors.length > 0 && (
                    <div className="reasons">
                      <strong>Key factors:</strong>
                      <ul>
                        {claudeReview.decision.key_factors.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {claudeReview.decision.risk_flags.length > 0 && (
                    <div className="reasons">
                      <strong>Risk flags:</strong>
                      <ul>
                        {claudeReview.decision.risk_flags.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {claudeReview.decision.missing_information.length > 0 && (
                    <p className="muted">
                      Claude noted missing information: {claudeReview.decision.missing_information.join("; ")}
                    </p>
                  )}
                  <div className="muted">
                    {claudeReview.model} · prompt {claudeReview.prompt_version} · review{" "}
                    {claudeReview.claude_decision_id}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
