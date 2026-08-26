"""Roster-aware need calculation, shared by draft and waiver recommendations
(ACCEPTANCE_CRITERIA.md: "Roster fit is calculated", "Roster-aware decisions exist")."""

from __future__ import annotations

from alpha_squad.league.context import LeagueContext


def roster_need(league: LeagueContext, roster_positions: list[str]) -> dict[str, float]:
    """{position: need_score} for every position with a dedicated slot. need_score > 0 means
    the roster cannot yet fill that position's starting slots at all (urgent); a small
    positive score means the position has starters but thin bench depth; a negative score
    means the position is already saturated beyond a healthy bench depth."""
    dedicated = league.dedicated_slots()
    counts: dict[str, int] = {}
    for pos in roster_positions:
        counts[pos] = counts.get(pos, 0) + 1

    needs = {}
    for pos, slots in dedicated.items():
        have = counts.get(pos, 0)
        depth_target = slots + 2  # a little bench depth beyond the starting slots is healthy
        if have < slots:
            needs[pos] = float(slots - have)
        elif have < depth_target:
            needs[pos] = 0.3 * (depth_target - have)
        else:
            # Beyond starters + a healthy 2-deep bench, one more at this position has
            # essentially no real usable value (a 3rd+ bench QB in a 2-QB league will
            # basically never start) -- discourage it at `roster_fit_multiplier`'s full
            # floor immediately, not gradually. The old -0.2 coefficient here took ~15 extra
            # players at one position to reach the floor, which is why a real historical
            # draft simulation (docs/DECISIONS.md D54) could stack 7 QBs into a 2-QB league
            # before this ever meaningfully discouraged it -- verified by replaying the real
            # draft pick-by-pick, not just observed in the final roster.
            needs[pos] = -3.0 * (have - depth_target)
    return needs


def roster_fit_multiplier(need_score: float) -> float:
    """Bounded [0.7, 1.3] multiplier applied to a player's value based on roster need.
    Bounded deliberately: roster fit adjusts value at the margin, it never lets a marginal
    need invert a large talent gap between two very differently-valued players."""
    return max(0.7, min(1.3, 1.0 + 0.1 * need_score))
