import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import type { EdgeRow } from "../types";
import { AsyncSection, Badge } from "./common";

const ACTIONS = ["", "BUY", "SELL", "HOLD", "WATCH"];

export function EdgeView() {
  const [season, setSeason] = useState(2025);
  const [action, setAction] = useState("BUY");
  const [rows, setRows] = useState<EdgeRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getEdge({ season, action: action || undefined, limit: 50 })
      .then(setRows)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [season, action]);

  return (
    <section>
      <h2>EDGE</h2>
      <p className="muted">
        Model-vs-market disagreement (M8/M9), gated so a raw ranking discrepancy alone can
        never produce BUY/SELL. Click a row to see the real reasons the engine stored.
      </p>
      <div className="controls">
        <label>
          Season{" "}
          <input type="number" value={season} onChange={(e) => setSeason(Number(e.target.value))} />
        </label>
        <label>
          Action{" "}
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a || "ALL"}
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
                <th>Model Rank</th>
                <th>Market Rank</th>
                <th>Rank Edge</th>
                <th>Points Edge</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.player_id}>
                  <tr
                    onClick={() => setExpanded(expanded === r.player_id ? null : r.player_id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td>{r.display_name ?? r.player_id}</td>
                    <td>{r.position}</td>
                    <td>{r.model_rank}</td>
                    <td>{r.market_rank}</td>
                    <td>{r.rank_edge > 0 ? `+${r.rank_edge}` : r.rank_edge}</td>
                    <td>
                      {r.projected_points_edge != null
                        ? r.projected_points_edge > 0
                          ? `+${r.projected_points_edge.toFixed(1)}`
                          : r.projected_points_edge.toFixed(1)
                        : "-"}
                    </td>
                    <td>
                      <Badge value={r.action} />
                    </td>
                  </tr>
                  {expanded === r.player_id && (
                    <tr>
                      <td colSpan={7} className="reasons">
                        <ul>
                          {r.reasons.map((reason, i) => (
                            <li key={i}>{reason}</li>
                          ))}
                        </ul>
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
