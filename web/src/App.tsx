import { useState } from "react";
import "./App.css";
import { ActionCenterView } from "./components/ActionCenterView";
import { DashboardView } from "./components/DashboardView";
import { DraftView } from "./components/DraftView";
import { EdgeView } from "./components/EdgeView";
import { EvidenceView } from "./components/EvidenceView";
import { HealthView } from "./components/HealthView";
import { LeagueSelectorBar } from "./components/LeagueSelectorBar";
import { LeagueView } from "./components/LeagueView";
import { MyTeamView } from "./components/MyTeamView";
import { PlayerDetailView } from "./components/PlayerDetailView";
import { RankingsView } from "./components/RankingsView";
import { RookiesView } from "./components/RookiesView";
import { SimulationView } from "./components/SimulationView";
import { TradeView } from "./components/TradeView";
import { WaiverView } from "./components/WaiverView";
import { LeagueProvider } from "./league-context";
import { PlayerSelectionProvider } from "./player-context";

const TABS = [
  { id: "dashboard", label: "Dashboard", render: () => <DashboardView /> },
  { id: "my-team", label: "My Team", render: () => <MyTeamView /> },
  { id: "actions", label: "Action Center", render: () => <ActionCenterView /> },
  { id: "draft", label: "Draft", render: () => <DraftView /> },
  { id: "waiver", label: "Waiver", render: () => <WaiverView /> },
  { id: "trade", label: "Trade", render: () => <TradeView /> },
  { id: "player", label: "Player", render: () => <PlayerDetailView /> },
  { id: "rankings", label: "Rankings", render: () => <RankingsView /> },
  { id: "edge", label: "EDGE", render: () => <EdgeView /> },
  { id: "rookies", label: "Rookies", render: () => <RookiesView /> },
  { id: "evidence", label: "Evidence", render: () => <EvidenceView /> },
  { id: "league", label: "League", render: () => <LeagueView /> },
  { id: "simulation", label: "Simulation", render: () => <SimulationView /> },
  { id: "health", label: "Source Health", render: () => <HealthView /> },
] as const;

function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("dashboard");
  const active = TABS.find((t) => t.id === tab)!;

  return (
    <LeagueProvider>
      <PlayerSelectionProvider onOpen={() => setTab("player")}>
        <div className="app">
          <header>
            <h1>Alpha Squad</h1>
            <p className="muted">
              Fantasy football GM assistant — connects to your real league and tells you what to
              do, with an explanation. Presentation layer only; every recommendation comes from
              the real backend decision engine.
            </p>
            <LeagueSelectorBar />
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
      </PlayerSelectionProvider>
    </LeagueProvider>
  );
}

export default App;
