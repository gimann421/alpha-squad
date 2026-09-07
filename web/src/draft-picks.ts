// Overall pick-number arithmetic for a manually tracked draft (#2, docs/DECISIONS.md D78).
//
// Extracted from DraftView so it can be tested directly: these are the rules that decide what
// number appears next to each player and what happens when the user corrects one, and getting
// them wrong mid-draft silently changes which players the engine thinks are still available.

/** The ordered board IS the numbering: a player's overall pick number is his 1-based index. */
export function pickNumberOf(draftedIds: readonly string[], playerId: string): number | null {
  const index = draftedIds.indexOf(playerId);
  return index < 0 ? null : index + 1;
}

/**
 * Move `playerId` to overall pick `requested`, renumbering everything between.
 *
 * Numbers are derived from position rather than stored, which is what makes them 1..N
 * contiguous by construction — a stored number can drift from the list it describes, develop
 * gaps, or duplicate; a position cannot. `requested` is clamped into range instead of rejected,
 * because a typo'd 0 or 99 during a live draft should land at the first/last slot rather than
 * appear to do nothing.
 */
export function withPickNumber(
  draftedIds: readonly string[],
  playerId: string,
  requested: number,
): string[] {
  const from = draftedIds.indexOf(playerId);
  if (from < 0) return [...draftedIds];
  if (!Number.isFinite(requested)) return [...draftedIds];
  const to = Math.min(Math.max(1, Math.trunc(requested)), draftedIds.length) - 1;
  if (to === from) return [...draftedIds];
  const next = [...draftedIds];
  next.splice(from, 1);
  next.splice(to, 0, playerId);
  return next;
}

/**
 * The overall pick numbers belonging to `slot` in a snake draft — odd rounds run 1..teams,
 * even rounds reverse. This is what lets the app show a user their picks in advance and derive
 * "my next pick" instead of asking them to remember a number.
 */
export function snakePickNumbers(teams: number, rounds: number, slot: number): number[] {
  if (teams < 1 || rounds < 1 || slot < 1 || slot > teams) return [];
  return Array.from({ length: rounds }, (_, r) =>
    r % 2 === 0 ? r * teams + slot : r * teams + (teams - slot + 1),
  );
}

/** The first scheduled pick that has not happened yet, given how many picks are logged. */
export function nextPickNumber(picks: readonly number[], picksLogged: number): number | null {
  return picks.find((n) => n > picksLogged) ?? null;
}
