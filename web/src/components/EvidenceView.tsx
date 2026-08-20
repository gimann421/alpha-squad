import { useEffect, useState } from "react";
import { api } from "../api";
import type { EvidenceRow } from "../types";
import { AsyncSection, Badge } from "./common";

export function EvidenceView() {
  const [season, setSeason] = useState(2024);
  const [week, setWeek] = useState(8);
  const [rows, setRows] = useState<EvidenceRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getEvidence({ season, week, limit: 50 })
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [season, week]);

  return (
    <section>
      <h2>Evidence</h2>
      <p className="muted">
        Direct projection of `evidence_events` (M9) — real depth-chart moves, injury
        reports, roster transactions, and usage-share shifts detected from officially-sourced
        structured data. Strength is Strong/Medium/Weak per PRODUCT_SPEC.md's taxonomy.
      </p>
      <div className="controls">
        <label>
          Season <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Week <input type="number" value={week} onChange={(e) => setWeek(Number(e.target.value))} />
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
                <th>Type</th>
                <th>Strength</th>
                <th>Direction</th>
                <th>Summary</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.event_id}>
                  <td>{r.display_name ?? r.player_id}</td>
                  <td>{r.event_type}</td>
                  <td>
                    <Badge value={r.strength_label} />
                  </td>
                  <td>{r.direction > 0 ? "▲" : r.direction < 0 ? "▼" : "–"}</td>
                  <td>{r.summary}</td>
                  <td className="muted">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      />
    </section>
  );
}
