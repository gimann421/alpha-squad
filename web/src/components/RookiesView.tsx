import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import type { RookieComp, RookieRow } from "../types";
import { AsyncSection } from "./common";

export function RookiesView() {
  // Defaults to the newest class the API actually has, not a hardcoded year -- a
  // hardcoded default goes stale every offseason (docs/DECISIONS.md D40).
  const [draftClass, setDraftClass] = useState<number | null>(null);
  const [rows, setRows] = useState<RookieRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comps, setComps] = useState<Record<string, RookieComp[]>>({});

  useEffect(() => {
    api
      .getRookieClasses()
      .then((classes) => setDraftClass(classes[0] ?? new Date().getFullYear()))
      .catch(() => setDraftClass(new Date().getFullYear()));
  }, []);

  useEffect(() => {
    if (draftClass === null) return;
    setLoading(true);
    setError(null);
    setComps({});
    api
      .getRookies({ draft_class: draftClass, limit: 50 })
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [draftClass]);

  async function loadComps(row: RookieRow) {
    if (comps[row.player_id]) return;
    const result = await api.getRookieComps(row.player_id, {
      draft_class: row.draft_class,
      position: row.position,
    });
    setComps((prev) => ({ ...prev, [row.player_id]: result }));
  }

  return (
    <section>
      <h2>Rookies</h2>
      <p className="muted">
        Direct projection of `rookie_predictions` (M7) — draft capital + combine + landing
        spot, walk-forward by draft class. Click a row for real historical comps.
      </p>
      <div className="controls">
        <label>
          Draft class{" "}
          <input type="number" value={draftClass ?? ""} onChange={(e) => setDraftClass(Number(e.target.value))} />
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
                <th>Predicted rookie pts</th>
                <th>Breakout prob</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.player_id}>
                  <tr onClick={() => loadComps(r)} style={{ cursor: "pointer" }}>
                    <td>{r.display_name ?? r.player_id}</td>
                    <td>{r.position}</td>
                    <td>{r.predicted_rookie_points?.toFixed(1) ?? "-"}</td>
                    <td>{r.breakout_probability != null ? `${(r.breakout_probability * 100).toFixed(0)}%` : "-"}</td>
                  </tr>
                  {comps[r.player_id] && (
                    <tr>
                      <td colSpan={4} className="reasons">
                        Comps:{" "}
                        {comps[r.player_id].map((c) => `${c.display_name ?? c.player_id} (${c.draft_class})`).join(", ") ||
                          "none found"}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      />
    </section>
  );
}
