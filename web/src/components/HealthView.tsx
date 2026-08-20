import { useEffect, useState } from "react";
import { api } from "../api";
import type { SourceHealthRow } from "../types";
import { AsyncSection, Badge } from "./common";

export function HealthView() {
  const [rows, setRows] = useState<SourceHealthRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSourceHealth()
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section>
      <h2>Source Health</h2>
      <p className="muted">
        Direct projection of `source_health_log` (M1) — the latest real check per source.
        BLOCKED/NO_CREDENTIALS sources are shown honestly, not hidden behind a generic status.
      </p>
      <AsyncSection
        loading={loading}
        error={error}
        data={rows}
        render={(rows) => (
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Dataset</th>
                <th>Status</th>
                <th>Checked</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.source}/${r.dataset}`}>
                  <td>{r.source}</td>
                  <td>{r.dataset}</td>
                  <td>
                    <Badge value={r.status} />
                  </td>
                  <td className="muted">{r.checked_at}</td>
                  <td className="muted">{r.detail ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      />
    </section>
  );
}
