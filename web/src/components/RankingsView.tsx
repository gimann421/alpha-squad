import { useEffect, useState } from "react";
import { api } from "../api";
import type { RankingRow } from "../types";
import { AsyncSection } from "./common";

const POSITIONS = ["", "QB", "RB", "WR", "TE"];

export function RankingsView() {
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
    <section>
      <h2>Rankings</h2>
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
    </section>
  );
}
