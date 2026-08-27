"""Roster-aware need calculation, shared by draft and waiver recommendations
(ACCEPTANCE_CRITERIA.md: "Roster fit is calculated", "Roster-aware decisions exist")."""

from __future__ import annotations

import math

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


# The hard stop past which one more player at a position has essentially no usable value, as
# distinct from `roster_fit_multiplier`'s soft [0.7, 1.3] marginal adjustment. Measured, not
# assumed: in the D55 P-tier ablation this cap alone (tier P2) improved mean starter points
# over production and, combined with positional opportunity cost (tier P3), cut the RB=0 rate
# from 10/50 to 2/50. 0.1 rather than 0.0 so a genuinely forced pick (a roster with literally
# nothing else evaluable) still ranks these above nothing at all.
OVER_CAP_VALUE_MULTIPLIER = 0.1


def positional_feasibility_cap(league: LeagueContext, position: str) -> int:
    """How many players at `position` a roster in THIS league can realistically use: its
    starting slots plus an even share of the configured bench.

    Derived from the league's own configuration (`dedicated_slots()`, `bench_size`), never
    hardcoded per position -- a 2QB league and a 1QB league get different caps automatically,
    and a superflex or deep-bench league does too. This deliberately reads the real
    `league.bench_size`, which the M17 forensic audit found was dead code: `roster_need`'s
    `depth_target = slots + 2` is a constant with no relationship to the league's actual
    configured bench (docs/DRAFT_ENGINE_FORENSIC_AUDIT.md §3).

    The two mechanisms stack intentionally rather than duplicating each other:
    `roster_fit_multiplier` tapers value as a position fills; this is the floor past which the
    engine effectively stops considering the position at all."""
    dedicated = league.dedicated_slots()
    slots = dedicated.get(position, 0)
    n_positions = max(len(dedicated), 1)
    bench_share = league.bench_size / n_positions
    return slots + max(1, math.ceil(bench_share))
