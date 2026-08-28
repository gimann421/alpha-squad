"""Roster-aware need calculation, shared by draft and waiver recommendations
(ACCEPTANCE_CRITERIA.md: "Roster fit is calculated", "Roster-aware decisions exist")."""

from __future__ import annotations

from alpha_squad.league.context import FLEX_ELIGIBILITY, LeagueContext


def startable_slots(league: LeagueContext) -> dict[str, int]:
    """{position: how many lineup slots this position could start in} -- its dedicated slots
    plus every flex slot it is eligible for (D58).

    Flex eligibility is counted in full rather than shared out, because a single position
    genuinely can fill every flex slot: in the target format an RB can hold both FLEX spots,
    so an RB's startable count is 2 dedicated + 2 flex = 4. Ignoring flex entirely -- which
    the pre-D58 code did -- makes RB and WR look like 2-slot positions in a league that
    routinely starts four of them, and makes K and DEF look interchangeable with them."""
    dedicated = league.dedicated_slots()
    flex = league.flex_slots()
    startable = dict(dedicated)
    for flex_name, count in flex.items():
        for position in FLEX_ELIGIBILITY.get(flex_name, ()):
            startable[position] = startable.get(position, 0) + count
    return startable


def positional_capacity(league: LeagueContext, position: str) -> int:
    """How many players at `position` a roster in THIS league can realistically use: every
    slot the position could start in, plus its share of the bench.

    The bench is allocated in proportion to how much of the starting lineup a position
    occupies, not split evenly. An even split -- what the pre-D58 code did -- breaks as soon
    as a league has more positions than the ones that need depth: adding K and DEF to the
    lineup took the divisor from 4 to 6 and cut RB's and WR's allowance by a third, while
    handing K and DEF bench room no real roster ever uses.

    Every position gets at least one bench slot's worth of headroom, so a backup is never
    structurally forbidden -- a 1-QB league still carries a second QB sometimes. Derived
    entirely from the league's own config; nothing here is hardcoded per position."""
    startable = startable_slots(league)
    slots = startable.get(position, 0)
    if slots <= 0:
        return 0
    total_startable = sum(startable.values())
    share = slots / total_startable if total_startable else 0.0
    bench_share = max(1, round(league.bench_size * share))
    return slots + bench_share


def unfilled_dedicated_slots(league: LeagueContext, roster_positions: list[str]) -> dict[str, int]:
    """{position: deficit} for every dedicated (non-flex) starting slot this roster has not
    yet filled to its minimum -- e.g. a league with `K: 1` and no kicker drafted yet reports
    `{"K": 1, ...}`. Positions already at or past their dedicated count are omitted entirely,
    so an empty dict means every mandatory slot is covered.

    Derived from `league.dedicated_slots()`, never hardcoded (D61 Stage 1.1) -- this is what
    lets a roster-aware consensus drafter (`evaluation/draft_simulation.py`) know it must fill
    a K/DEF slot in a league that has one, and correctly does nothing in a league that
    doesn't."""
    dedicated = league.dedicated_slots()
    counts: dict[str, int] = {}
    for pos in roster_positions:
        counts[pos] = counts.get(pos, 0) + 1
    return {
        pos: slots - counts.get(pos, 0)
        for pos, slots in dedicated.items()
        if counts.get(pos, 0) < slots
    }


def roster_need(league: LeagueContext, roster_positions: list[str]) -> dict[str, float]:
    """{position: need_score} for every position with a dedicated slot. need_score > 0 means
    the roster cannot yet fill that position's starting slots at all (urgent); a small
    positive score means the position has starters but no cover for its flex slots; a
    negative score means the position is saturated past what it could ever start.

    The depth target is `startable_slots` -- what this league could actually start at the
    position -- not the old `slots + 2` constant. That constant was an arbitrary
    roster-count target: it had no relationship to the league's real lineup, and in the
    1-QB format it would have asked for 3 kickers and 3 defenses."""
    dedicated = league.dedicated_slots()
    startable = startable_slots(league)
    counts: dict[str, int] = {}
    for pos in roster_positions:
        counts[pos] = counts.get(pos, 0) + 1

    needs = {}
    for pos, slots in dedicated.items():
        have = counts.get(pos, 0)
        depth_target = max(startable.get(pos, slots), slots)
        if have < slots:
            needs[pos] = float(slots - have)
        elif have < depth_target:
            needs[pos] = 0.3 * (depth_target - have)
        else:
            # Past everything this position could start, one more body has essentially no
            # usable value -- discourage it at `roster_fit_multiplier`'s full floor
            # immediately, not gradually. The old -0.2 coefficient here took ~15 extra
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
    """The hard stop past which one more body at `position` cannot start, as distinct from
    `roster_fit_multiplier`'s soft [0.7, 1.3] marginal adjustment.

    Delegates to `positional_capacity`, which is derived from the league's own configuration
    (`dedicated_slots()`, `flex_slots()`, `bench_size`) and never hardcoded per position -- a
    2QB league, a 1QB league, a superflex league and a deep-bench league all get different
    caps from their config alone.

    The two mechanisms stack intentionally rather than duplicating each other:
    `roster_fit_multiplier` tapers value as a position fills; this is the floor past which
    the engine effectively stops considering the position at all."""
    return positional_capacity(league, position)
