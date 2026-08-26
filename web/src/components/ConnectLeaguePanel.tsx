import { useState } from "react";
import { api } from "../api";
import { useLeague } from "../league-context";

// The "Connect League" onboarding action (D53): registers a real Sleeper league
// (POST /league/register, which validates it's real and reachable before persisting) and
// switches to it. Manual/YAML leagues have no runtime "connect" flow -- they're a
// server-side config file edit (config/league_configs/registry.yaml), documented there and
// in README.md; this panel is specifically the automatic-import path.
export function ConnectLeaguePanel({ onConnected }: { onConnected?: () => void }) {
  const { setLeagueId, refreshLeagues } = useLeague();
  const [sleeperLeagueId, setSleeperLeagueId] = useState("");
  const [friendlyId, setFriendlyId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState<string | null>(null);

  async function connect() {
    if (!sleeperLeagueId.trim()) return;
    setSubmitting(true);
    setError(null);
    setConnected(null);
    try {
      const result = await api.registerLeague({
        sleeper_league_id: sleeperLeagueId.trim(),
        league_id: friendlyId.trim() || undefined,
      });
      setConnected(result.league_id);
      refreshLeagues();
      setLeagueId(result.league_id);
      // Deferred: calling onConnected() (which closes/unmounts this panel in the parent)
      // in the same batch as setConnected() above meant "Connected as ..." never actually
      // painted -- React commits the parent's re-render (panel gone) before the confirmation
      // the user is meant to see. Give it a beat on screen first.
      setTimeout(() => onConnected?.(), 1500);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card">
      <div>
        <strong>Connect a Sleeper league</strong>
      </div>
      <p className="muted">
        Enter the numeric league id from your league's Sleeper URL (
        <code>sleeper.com/leagues/&lt;this number&gt;/...</code>). Alpha Squad validates it's a
        real, reachable league before connecting — nothing is fabricated if the id is wrong.
      </p>
      <div className="controls">
        <label>
          Sleeper league ID{" "}
          <input
            value={sleeperLeagueId}
            onChange={(e) => setSleeperLeagueId(e.target.value)}
            placeholder="1234567890123456789"
          />
        </label>
        <label>
          Friendly name (optional){" "}
          <input value={friendlyId} onChange={(e) => setFriendlyId(e.target.value)} placeholder="my_league" />
        </label>
        <button onClick={connect} disabled={submitting || !sleeperLeagueId.trim()}>
          {submitting ? "Connecting…" : "Connect league"}
        </button>
      </div>
      {error && <p className="error">Couldn't connect: {error}</p>}
      {connected && <p className="muted">Connected as "{connected}" — pick your team above.</p>}
      <p className="muted">
        Not on Sleeper? Register a league manually: add an entry to
        <code> config/league_configs/registry.yaml</code> (see that file's own comments).
      </p>
    </div>
  );
}
