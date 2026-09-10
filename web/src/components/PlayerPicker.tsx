import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlayerSummary } from "../types";

// D48: `GET /players` (list_players, real name search via `q`) had a working frontend client
// wrapper (`api.listPlayers`) that nothing ever called -- every form asking for a player_id
// made a user type the raw opaque canonical id (`asq_<hash>`) by hand, with a placeholder that
// didn't even match that format. This makes the existing endpoint genuinely reachable by
// replacing that with real name search, rather than either leaving the endpoint dead or
// deleting a working, spec-relevant capability.
export function PlayerPicker({
  value,
  onChange,
  placeholder = "Search player by name…",
  displayLabel,
}: {
  value: string;
  // The picked player is passed alongside the id so a caller can remember its display name.
  // Without it a caller holding only ids has to find the name in some other list, and shows a
  // raw `asq_<hash>` for anyone missing from that list -- which is what the draft board did for
  // any player outside the top-500 ranked pool (D78).
  onChange: (playerId: string, player?: PlayerSummary) => void;
  placeholder?: string;
  // Shown instead of the raw player_id when `value` was set externally (e.g. PlayerLink
  // jumping the Player Detail tab straight to a player_id, bypassing this picker's own
  // search-and-pick flow) rather than through a search-and-pick here.
  displayLabel?: string | null;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PlayerSummary[] | null>(null);
  const [selected, setSelected] = useState<PlayerSummary | null>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    const handle = setTimeout(() => {
      api
        .listPlayers({ q: query, limit: 10 })
        .then(setResults)
        .catch(() => setResults(null));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  function pick(p: PlayerSummary) {
    setSelected(p);
    setResults(null);
    setQuery("");
    onChange(p.player_id, p);
  }

  function clear() {
    setSelected(null);
    onChange("");
  }

  // BUG (D78, found by driving a real manual draft in a browser): this used to key off the
  // component's OWN `selected` state, which nothing cleared when the PARENT reset `value` to
  // "". A caller that consumes a pick and clears the field -- which is exactly what the draft
  // board does, once per pick -- got a picker frozen on the previous player, so entering
  // consecutive picks required clicking "change" between every one. Keying the whole branch on
  // `value` makes the parent's clear authoritative: `selected` is only ever a nicer label for
  // the id the parent is actually holding.
  const selectionMatchesValue = selected?.player_id === value;
  if (value && (selectionMatchesValue || !query)) {
    const label = selectionMatchesValue
      ? `${selected!.display_name ?? selected!.player_id} (${selected!.position ?? "?"})`
      : (displayLabel ?? value);
    return (
      <span>
        {label}{" "}
        <button type="button" onClick={clear}>
          change
        </button>
      </span>
    );
  }

  return (
    <span style={{ position: "relative" }}>
      <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={placeholder} />
      {results && (
        <ul className="player-picker-results">
          {results.length === 0 ? (
            <li className="muted">no matches</li>
          ) : (
            results.map((p) => (
              <li key={p.player_id} onClick={() => pick(p)}>
                {p.display_name ?? p.player_id} — {p.position ?? "?"}
                {p.college_name ? ` · ${p.college_name}` : ""}
              </li>
            ))
          )}
        </ul>
      )}
    </span>
  );
}
