import { useEffect, useState } from "react";
import { api } from "../api";
import { useLatestSeason } from "../hooks";
import { useLeague } from "../league-context";
import { usePlayerSelection } from "../player-context";
import type { PlayerDetailFull } from "../types";
import { Badge } from "./common";
import { PlayerPicker } from "./PlayerPicker";

// "Tell me everything important about this player." Distinguishes UNIVERSAL player value
// (projection, uncertainty, market/EDGE, evidence, rookie info -- true regardless of league)
// from MY LEAGUE value (dynasty trade action, roster fit) when a league is selected in the
// shared league bar: the same player can carry a different recommendation per league.
export function PlayerDetailView() {
  const { selectedPlayerId, openPlayer } = usePlayerSelection();
  const { leagueId, rosterId, teamsSupported } = useLeague();
  const latestSeason = useLatestSeason("uncertainty", 2025);
  const [season, setSeason] = useState(latestSeason);
  useEffect(() => setSeason(latestSeason), [latestSeason]);

  const [detail, setDetail] = useState<PlayerDetailFull | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedPlayerId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .getPlayerDetail(selectedPlayerId, {
        season,
        league_id: leagueId ?? undefined,
        roster_id: leagueId && teamsSupported ? (rosterId ?? undefined) : undefined,
      })
      .then(setDetail)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [selectedPlayerId, season, leagueId, rosterId, teamsSupported]);

  return (
    <section>
      <h2>Player</h2>
      <p className="muted">
        Universal value (projection, market, EDGE, evidence, rookie info) is the same everywhere; league
        value (dynasty trade action, roster fit) reflects the league selected above and can differ by
        league.
      </p>

      <div className="controls">
        <span className="picker-field">
          <span className="picker-field-label">Player</span>
          <PlayerPicker
            value={selectedPlayerId ?? ""}
            onChange={(id) => id && openPlayer(id)}
            displayLabel={detail?.display_name}
          />
        </span>
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
      </div>

      {!selectedPlayerId && <p className="muted">Search for a player above, or click a player name anywhere in the app.</p>}
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">Couldn't reach the Alpha Squad API: {error}</p>}

      {detail && (
        <>
          <div className="card">
            <div>
              <strong style={{ fontSize: "1.2rem" }}>{detail.display_name ?? detail.player_id}</strong>{" "}
              {detail.position} {detail.college_name ? `· ${detail.college_name}` : ""}
            </div>
            <div className="muted">
              Draft: {detail.draft_year ?? "-"} round {detail.draft_round ?? "-"} pick {detail.draft_pick ?? "-"}
              {detail.draft_team ? ` (${detail.draft_team})` : ""} · Status: {detail.status ?? "-"}
            </div>
          </div>

          <h3>Universal value ({season})</h3>
          <div className="dashboard-grid">
            <div className="card">
              <strong>Projection &amp; uncertainty</strong>
              {detail.ranking ? (
                <>
                  <div>Point estimate: {detail.ranking.point_prediction.toFixed(1)}</div>
                  <div>
                    p10–p90: {detail.ranking.p10?.toFixed(0) ?? "-"} – {detail.ranking.p90?.toFixed(0) ?? "-"}
                  </div>
                  <div>Median: {detail.ranking.median?.toFixed(1) ?? "-"}</div>
                  <div>
                    Top12 / Top24 prob:{" "}
                    {detail.ranking.top12_prob != null ? `${(detail.ranking.top12_prob * 100).toFixed(0)}%` : "-"} /{" "}
                    {detail.ranking.top24_prob != null ? `${(detail.ranking.top24_prob * 100).toFixed(0)}%` : "-"}
                  </div>
                  <div>Confidence: {detail.ranking.confidence?.toFixed(2) ?? "-"}</div>
                </>
              ) : (
                <p className="muted">No projection on record for {season}.</p>
              )}
            </div>

            <div className="card">
              <strong>Market / EDGE</strong>
              {detail.edge ? (
                <>
                  <div>
                    <Badge value={detail.edge.action} />
                  </div>
                  <div>
                    Model rank {detail.edge.model_rank} vs. market rank {detail.edge.market_rank} (
                    {detail.edge.rank_edge >= 0 ? "+" : ""}
                    {detail.edge.rank_edge})
                  </div>
                  <div className="reasons">
                    <ul>
                      {detail.edge.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                </>
              ) : (
                <p className="muted">No EDGE on record for {season}.</p>
              )}
            </div>

            {detail.rookie && (
              <div className="card">
                <strong>Rookie / prospect</strong>
                <div>Draft class {detail.rookie.draft_class}</div>
                <div>Predicted rookie points: {detail.rookie.predicted_rookie_points?.toFixed(1) ?? "-"}</div>
                <div>
                  Breakout probability:{" "}
                  {detail.rookie.breakout_probability != null
                    ? `${(detail.rookie.breakout_probability * 100).toFixed(0)}%`
                    : "-"}
                </div>
              </div>
            )}
          </div>

          {detail.league_value && (
            <>
              <h3>My league value ({detail.league_value.league_id})</h3>
              <div className="card">
                <div>
                  <Badge value={detail.league_value.trade_action ?? "WATCH"} />{" "}
                  {detail.league_value.is_mine != null &&
                    (detail.league_value.is_mine ? "· On my roster" : "· Not on my roster")}
                </div>
                <div>
                  Age-adjusted dynasty value: {detail.league_value.age_adjusted_dynasty_value?.toFixed(0) ?? "-"}
                </div>
                {detail.league_value.roster_need != null && (
                  <div>Roster need at {detail.position}: {detail.league_value.roster_need.toFixed(2)}</div>
                )}
                <div className="reasons">
                  <ul>
                    {detail.league_value.trade_reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}

          <h3>Why did this change? (recent evidence)</h3>
          {detail.recent_evidence.length === 0 ? (
            <p className="muted">No structured evidence events on record for this player.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Week</th>
                  <th>Type</th>
                  <th>Strength</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {detail.recent_evidence.map((e) => (
                  <tr key={e.event_id}>
                    <td>{e.event_date}</td>
                    <td>{e.week}</td>
                    <td>{e.event_type}</td>
                    <td>
                      <Badge value={e.strength_label} /> {e.direction > 0 ? "▲" : e.direction < 0 ? "▼" : "–"}
                    </td>
                    <td>{e.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
