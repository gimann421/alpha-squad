import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { PlayerLink } from "../player-context";
import type { DecisionResponse, PickAssetRequest, TradePackageResponse } from "../types";
import { Badge } from "./common";
import { PlayerPicker } from "./PlayerPicker";

function PlayerChipList({
  playerIds,
  onRemove,
  nameFor,
}: {
  playerIds: string[];
  onRemove: (id: string) => void;
  nameFor: (id: string) => string;
}) {
  if (playerIds.length === 0) return <p className="muted">No players added yet.</p>;
  return (
    <ul className="action-list">
      {playerIds.map((id) => (
        <li key={id}>
          <PlayerLink playerId={id}>{nameFor(id)}</PlayerLink>{" "}
          <button className="secondary" onClick={() => onRemove(id)}>
            remove
          </button>
        </li>
      ))}
    </ul>
  );
}

function PickEditor({ picks, onChange }: { picks: PickAssetRequest[]; onChange: (picks: PickAssetRequest[]) => void }) {
  function update(i: number, field: keyof PickAssetRequest, value: number) {
    const next = picks.slice();
    next[i] = { ...next[i], [field]: value };
    onChange(next);
  }
  function add() {
    onChange([...picks, { round: 1, pick_in_round: null, years_out: 0 }]);
  }
  function remove(i: number) {
    onChange(picks.filter((_, idx) => idx !== i));
  }
  return (
    <div>
      {picks.map((p, i) => (
        <div className="controls" key={i} style={{ margin: "0.25rem 0" }}>
          <label>
            Round <input type="number" value={p.round} onChange={(e) => update(i, "round", Number(e.target.value))} />
          </label>
          <label>
            Years out{" "}
            <input type="number" value={p.years_out ?? 0} onChange={(e) => update(i, "years_out", Number(e.target.value))} />
          </label>
          <button className="secondary" onClick={() => remove(i)}>
            remove pick
          </button>
        </div>
      ))}
      <button className="secondary" onClick={add}>
        + add future pick
      </button>
    </div>
  );
}

export function TradeView() {
  const { leagueId, teams } = useLeague();
  const latestSeason = useLatestSeason("edge", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);
  const [ecrType, setEcrType] = useState("rsf");

  // Single-player buy/sell/hold evaluation.
  const [playerId, setPlayerId] = useState("");
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function runTrade() {
    if (!leagueId || !playerId.trim()) return;
    setSubmitting(true);
    setDecisionError(null);
    setDecision(null);
    try {
      const result = await api.postTrade(leagueId, { season, player_id: playerId.trim(), ecr_type: ecrType });
      setDecision(result);
    } catch (e) {
      setDecisionError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  // Multi-asset package comparison.
  const [sideAPlayers, setSideAPlayers] = useState<string[]>([]);
  const [sideBPlayers, setSideBPlayers] = useState<string[]>([]);
  const [sideAPicks, setSideAPicks] = useState<PickAssetRequest[]>([]);
  const [sideBPicks, setSideBPicks] = useState<PickAssetRequest[]>([]);
  const [addToSideA, setAddToSideA] = useState("");
  const [addToSideB, setAddToSideB] = useState("");
  const [mySide, setMySide] = useState<"side_a" | "side_b">("side_a");
  const [pkg, setPkg] = useState<TradePackageResponse | null>(null);
  const [pkgError, setPkgError] = useState<string | null>(null);
  const [pkgSubmitting, setPkgSubmitting] = useState(false);

  const myRosterIds = new Set(
    teams?.flatMap((t) => t.players.map((p) => p.player_id)) ?? [],
  );
  const nameFor = (id: string) =>
    teams?.flatMap((t) => t.players).find((p) => p.player_id === id)?.display_name ?? id;

  async function runPackage() {
    if (!leagueId) return;
    setPkgSubmitting(true);
    setPkgError(null);
    setPkg(null);
    try {
      const result = await api.postTradePackage(leagueId, {
        season,
        ecr_type: ecrType,
        side_a: { player_ids: sideAPlayers, picks: sideAPicks },
        side_b: { player_ids: sideBPlayers, picks: sideBPicks },
      });
      setPkg(result);
    } catch (e) {
      setPkgError(String(e));
    } finally {
      setPkgSubmitting(false);
    }
  }

  let verdict: { label: string; className: string } | null = null;
  if (pkg) {
    if (pkg.favors === "even") verdict = { label: "CONSIDER — roughly even", className: "HOLD" };
    else if (pkg.favors === mySide) verdict = { label: "ACCEPT — favors you", className: "BUY" };
    else verdict = { label: "REJECT — favors them", className: "SELL" };
  }

  return (
    <section>
      <h2>Trade</h2>

      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          ECR type <input value={ecrType} onChange={(e) => setEcrType(e.target.value)} placeholder="rsf" />
        </label>
      </div>

      <h3>Single-player value</h3>
      <p className="muted">
        Calls the exact same M10 function the CLI does (`recommend_dynasty_trade`) — real EDGE
        blended with real dynasty market value and a documented age-curve heuristic
        (docs/DECISIONS.md D25).
      </p>
      <div className="controls">
        <span className="picker-field">
          <span className="picker-field-label">Player</span>
          <PlayerPicker value={playerId} onChange={setPlayerId} />
        </span>
        <button onClick={runTrade} disabled={submitting || !leagueId || !playerId.trim()}>
          {submitting ? "Evaluating…" : "Evaluate"}
        </button>
      </div>
      {decisionError && <p className="error">Error: {decisionError}</p>}
      {decision && (
        <div className="card">
          <div>
            <Badge value={decision.action ?? "WATCH"} />
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

      <h3>Trade package: should I accept this?</h3>
      <p className="muted">
        Calls `evaluate_trade_package` (D45) — sums real age-adjusted dynasty value for every
        player plus real future-pick value on each side. Mark which side is yours so the verdict
        below (ACCEPT / REJECT / CONSIDER) is phrased from your perspective.
      </p>
      <div className="controls">
        <label>
          My side{" "}
          <select value={mySide} onChange={(e) => setMySide(e.target.value as "side_a" | "side_b")}>
            <option value="side_a">Side A</option>
            <option value="side_b">Side B</option>
          </select>
        </label>
      </div>

      <div className="dashboard-grid">
        <div className="card">
          <strong>Side A {mySide === "side_a" ? "(you)" : ""}</strong>
          <span className="picker-field">
            <span className="picker-field-label">Add player</span>
            <PlayerPicker
              value={addToSideA}
              onChange={(id) => {
                if (id && !sideAPlayers.includes(id)) setSideAPlayers((p) => [...p, id]);
                setAddToSideA("");
              }}
            />
          </span>
          <PlayerChipList
            playerIds={sideAPlayers}
            onRemove={(id) => setSideAPlayers((p) => p.filter((x) => x !== id))}
            nameFor={nameFor}
          />
          <PickEditor picks={sideAPicks} onChange={setSideAPicks} />
        </div>
        <div className="card">
          <strong>Side B {mySide === "side_b" ? "(you)" : ""}</strong>
          <span className="picker-field">
            <span className="picker-field-label">Add player</span>
            <PlayerPicker
              value={addToSideB}
              onChange={(id) => {
                if (id && !sideBPlayers.includes(id)) setSideBPlayers((p) => [...p, id]);
                setAddToSideB("");
              }}
            />
          </span>
          <PlayerChipList
            playerIds={sideBPlayers}
            onRemove={(id) => setSideBPlayers((p) => p.filter((x) => x !== id))}
            nameFor={nameFor}
          />
          <PickEditor picks={sideBPicks} onChange={setSideBPicks} />
        </div>
      </div>

      <div className="controls">
        <button
          onClick={runPackage}
          disabled={pkgSubmitting || !leagueId || (sideAPlayers.length === 0 && sideAPicks.length === 0 && sideBPlayers.length === 0 && sideBPicks.length === 0)}
        >
          {pkgSubmitting ? "Evaluating…" : "Evaluate trade package"}
        </button>
      </div>
      {pkgError && <p className="error">Error: {pkgError}</p>}
      {pkg && verdict && (
        <div className="card">
          <div>
            <Badge value={verdict.className} /> {verdict.label}
          </div>
          <div>
            Side A value: {pkg.side_a_value.toFixed(0)} · Side B value: {pkg.side_b_value.toFixed(0)} · Delta:{" "}
            {pkg.delta >= 0 ? "+" : ""}
            {pkg.delta.toFixed(0)}
          </div>
          {teams && (
            <div className="muted">
              Roster impact: {[...sideAPlayers, ...sideBPlayers].filter((id) => myRosterIds.has(id)).length} of the
              players in this trade are on your real roster.
            </div>
          )}
          <div className="reasons">
            <strong>Side A reasons</strong>
            <ul>
              {pkg.side_a_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
            <strong>Side B reasons</strong>
            <ul>
              {pkg.side_b_reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
