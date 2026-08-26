// Lets any view make a player name clickable and land on the Player Detail tab, without
// prop-drilling a callback through every intermediate component (Dashboard -> action list item,
// My Team -> roster row, Action Center -> add/drop/trade-signal row, etc. all need this).
import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";

interface PlayerSelectionValue {
  selectedPlayerId: string | null;
  openPlayer: (playerId: string) => void;
}

const PlayerSelectionCtx = createContext<PlayerSelectionValue | null>(null);

export function PlayerSelectionProvider({
  children,
  onOpen,
}: {
  children: ReactNode;
  onOpen: (playerId: string) => void;
}) {
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);

  function openPlayer(playerId: string) {
    setSelectedPlayerId(playerId);
    onOpen(playerId);
  }

  return (
    <PlayerSelectionCtx.Provider value={{ selectedPlayerId, openPlayer }}>{children}</PlayerSelectionCtx.Provider>
  );
}

export function usePlayerSelection(): PlayerSelectionValue {
  const ctx = useContext(PlayerSelectionCtx);
  if (!ctx) throw new Error("usePlayerSelection must be used within a PlayerSelectionProvider");
  return ctx;
}

export function PlayerLink({ playerId, children }: { playerId: string; children: ReactNode }) {
  const { openPlayer } = usePlayerSelection();
  return (
    <button className="player-link" onClick={() => openPlayer(playerId)}>
      {children}
    </button>
  );
}
