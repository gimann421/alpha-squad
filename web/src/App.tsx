import { useState } from "react";
import "./App.css";
import { EdgeView } from "./components/EdgeView";
import { EvidenceView } from "./components/EvidenceView";
import { HealthView } from "./components/HealthView";
import { LeagueView } from "./components/LeagueView";
import { RankingsView } from "./components/RankingsView";
import { RookiesView } from "./components/RookiesView";

const TABS = [
  { id: "rankings", label: "Rankings", render: () => <RankingsView /> },
  { id: "edge", label: "EDGE", render: () => <EdgeView /> },
  { id: "rookies", label: "Rookies", render: () => <RookiesView /> },
  { id: "evidence", label: "Evidence", render: () => <EvidenceView /> },
  { id: "league", label: "League", render: () => <LeagueView /> },
  { id: "health", label: "Source Health", render: () => <HealthView /> },
] as const;

function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("rankings");
  const active = TABS.find((t) => t.id === tab)!;

  return (
    <div className="app">
      <header>
        <h1>Alpha Squad</h1>
        <p className="muted">Fantasy football market-inefficiency intelligence — presentation layer only.</p>
        <nav>
          {TABS.map((t) => (
            <button key={t.id} className={t.id === tab ? "active" : ""} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main>{active.render()}</main>
    </div>
  );
}

export default App;
