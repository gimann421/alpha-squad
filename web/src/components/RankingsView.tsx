import { useEffect, useState } from "react";
import { api } from "../api";
import type { RankingRow, WeeklyRankingRow } from "../types";
import { AsyncSection } from "./common";

const POSITIONS = ["", "QB", "RB", "WR", "TE"];

function PreseasonRankings() {
  const [season, setSeason] = useState(2025);
  const [position, setPosition] = useState("");
  const [rows, setRows] = useState<RankingRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getRankings({ season, position: position || undefined, limit: 50 })
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [season, position]);

  return (
    <>
      <p className="muted">
        Direct projection of `uncertainty_predictions` (M6) — the same real, calibrated
        model output the CLI reads. Sorted exactly as the model ranked them.
      </p>
      <div className="controls">
        <label>
          Season{" "}
          <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Position{" "}
          <select value={position} onChange={(e) => setPosition(e.target.value)}>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p || "ALL"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <AsyncSection
        loading={loading}
        error={error}
        data={rows}
        render={(rows) => (
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th>Projected</th>
                <th>p10-p90</th>
                <th>Top12%</th>
                <th>Top24%</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.player_id}>
                  <td>{r.display_name ?? r.player_id}</td>
                  <td>{r.position}</td>
                  <td>{r.point_prediction.toFixed(1)}</td>
                  <td>
                    {r.p10?.toFixed(0) ?? "-"} – {r.p90?.toFixed(0) ?? "-"}
                  </td>
                  <td>{r.top12_prob != null ? `${(r.top12_prob * 100).toFixed(0)}%` : "-"}</td>
                  <td>{r.top24_prob != null ? `${(r.top24_prob * 100).toFixed(0)}%` : "-"}</td>
                  <td>{r.confidence != null ? r.confidence.toFixed(2) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      />
    </>
  );
}

function WeeklyRankings() {
  const [season, setSeason] = useState(2025);
  const [week, setWeek] = useState(8);
  const [position, setPosition] = useState("");
  const [rows, setRows] = useState<WeeklyRankingRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getWeeklyRankings({ season, week, position: position || undefined, limit: 50 })
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [season, week, position]);

  return (
    <>
      <p className="muted">
        Direct projection of `weekly_projection_snapshot` (M5) left-joined with
        `projection_deltas` (M9's bounded, evidence-driven adjustment) — sorted by the
        evidence-adjusted value, not the raw model output, so this answers "why did this
        player's ranking change this week?" directly. A player with no evidence on record
        shows their unadjusted base projection.
      </p>
      <div className="controls">
        <label>
          Season{" "}
          <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Week <input type="number" value={week} onChange={(e) => setWeek(Number(e.target.value))} />
        </label>
        <label>
          Position{" "}
          <select value={position} onChange={(e) => setPosition(e.target.value)}>
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p || "ALL"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <AsyncSection
        loading={loading}
        error={error}
        data={rows}
        render={(rows) => (
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Pos</th>
                <th>Base</th>
                <th>Adjusted</th>
                <th>Change</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.player_id}>
                  <td>{r.display_name ?? r.player_id}</td>
                  <td>{r.position}</td>
                  <td>{r.base_value.toFixed(1)}</td>
                  <td>{r.adjusted_value.toFixed(1)}</td>
                  <td>
                    {r.adjustment_pct != null && r.adjustment_pct !== 0
                      ? `${r.adjustment_pct > 0 ? "+" : ""}${(r.adjustment_pct * 100).toFixed(1)}%`
                      : "-"}
                  </td>
                  <td className="reasons">{r.reason ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      />
    </>
  );
}

export function RankingsView() {
  const [mode, setMode] = useState<"preseason" | "weekly">("preseason");

  return (
    <section>
      <h2>Rankings</h2>
      <div className="controls">
        <label>
          <input
            type="radio"
            checked={mode === "preseason"}
            onChange={() => setMode("preseason")}
          />{" "}
          Preseason (season-level)
        </label>
        <label>
          <input type="radio" checked={mode === "weekly"} onChange={() => setMode("weekly")} />{" "}
          Weekly (evidence-adjusted)
        </label>
      </div>
      {mode === "preseason" ? <PreseasonRankings /> : <WeeklyRankings />}
    </section>
  );
}
