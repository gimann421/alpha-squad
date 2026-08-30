"""Positional opportunity cost: what does it cost to pass on a position *right now*, given
what the rest of the league is about to do before this team's next turn?

Motivation (docs/DRAFT_ENGINE_FORENSIC_AUDIT.md §6, ROOT CAUSE): `league/draft.py`'s score had
no representation of *positional* opportunity cost -- only a single-*player* survival
probability (`next_pick_survival_probability`), which asks "will THIS player still be there"
and never "will a player THIS GOOD AT THIS POSITION still be there". Replaying the real
production engine pick-by-pick showed both traced pathological drafts were decided in the
team's first 1-2 picks: a viable RB was a live top-5 candidate at pick #1 and gone from
consideration by pick #20, because nothing in the score said "this position empties fast,
secure it now" at the one moment it mattered.

Design, per docs/DRAFT_ENGINE_REDESIGN_RECOMMENDATION.md -- Experiment F's *continuous,
points-denominated pricing* combined with Experiment G's *literal opponent replay* as the
input to that pricing. The controlled experiments (docs/DRAFT_CONTROLLED_EXPERIMENTS.md)
measured, over 400 real drafts, that:

- G's mechanism (opponent replay) is the faithful way to estimate future availability, but its
  *binary* trigger (1.3x only if the position empties outright) missed the everyday case of a
  position merely getting worse -- G scored WORSE than doing nothing (RB=0 36% vs 20%).
- F's *shape* (continuous, priced in real VORP points) is what carried the benefit.
- `positional_scarcity()` must NOT be added: it rates QB as the most "scarce" position and RB
  as one of the least in this league's real data, and adding it made the pathology worse
  (RB=0 20% -> 32%). This module deliberately does not use it.

Two properties worth stating explicitly because they are load-bearing:

1. **Per-position, not per-candidate.** The cost is a property of the POSITION (best available
   there now vs. best available there at my next turn), so every candidate at a position gets
   the same figure. This preserves within-position ordering and shifts only cross-position
   ordering -- and it is what makes computing this once per position per pick (rather than once
   per candidate) correct rather than merely an optimization.
2. **Clamped at replacement level.** VORP is already measured against a position's replacement
   level, so a negative-VORP player is by definition worse than a freely-available waiver-wire
   body. There is no real cost to "losing" one, so both sides of the comparison are clamped at
   0 before subtracting. This is a league-derived bound (VORP's own zero point), not a tuned
   constant -- without it, late-round comparisons between two below-replacement players (real
   example from 2021: best available RB at VORP -135.4) manufacture a spurious cost.
"""

from __future__ import annotations

from collections.abc import Iterable

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.roster import unfilled_dedicated_slots
from alpha_squad.market.edge import _preseason_overall_market


def best_by_market_rank(available: set[str], market_rank: dict[str, tuple[str, float]]) -> str:
    """Best remaining player by real preseason overall ECR rank (lower = better) -- the single
    canonical implementation of the market-consensus pick, shared by the opponent replay here
    and by `evaluation/draft_simulation.py`'s `market_consensus` strategy (which delegates to
    this function so the two can never drift apart).

    `player_id` is a deterministic tie-break, not a ranking preference: real ECR ranks tie often
    (43 tied rank groups in the real 2025 'rsf' data alone) and `available` is a `set`, whose
    iteration order depends on hash randomization that differs across process runs. See
    docs/DECISIONS.md D54, where exactly this bug made the benchmark unreproducible.

    A player the projection universe covers but this season's market snapshot does not (a deep
    sleeper with no real preseason consensus rank) sorts last rather than being excluded -- a
    real drafter still has to pick someone."""
    return min(
        available,
        key=lambda p: (market_rank[p][1] if p in market_rank else float("inf"), p),
    )


def roster_aware_market_pick(
    available: set[str],
    market_rank: dict[str, tuple[str, float]],
    positions: dict[str, str],
    league: LeagueContext,
    roster_positions: list[str],
    picks_remaining: int,
) -> str:
    """`best_by_market_rank`, except once this drafter has exactly as many picks left
    (`picks_remaining`, counting this one) as it has still-unfilled *mandatory* dedicated
    starting slots, the pick is restricted to filling one of them -- a real drafter does not let
    its final picks pass without being able to field a legal lineup. Still best-available by ECR
    *within* that restricted pool: no hindsight, no projection access, nothing else changes.

    The restriction, once triggered, stays triggered for every remaining pick: filling one slot
    reduces both `picks_remaining` and the deficit by exactly 1, so the equality that triggered
    it holds again next turn -- which is what guarantees every mandatory slot is filled by the
    last pick, not just the first one after the trigger. A league with no dedicated slot this
    format doesn't require has an empty deficit throughout, so it is byte-identical to
    `best_by_market_rank` there.

    The single canonical implementation of the rule, like `best_by_market_rank` above: it is the
    fair benchmark opponent (`evaluation/draft_simulation.py`, D61 Stage 1.1) *and* the drafter
    whose positional allocation defines `replacement.py::market_draft_demand` (D67). Those two
    must not drift apart -- if the opponent and the demand model disagree about how a draft
    consumes positions, the replacement level is measured against a draft nobody plays."""
    deficits = unfilled_dedicated_slots(league, roster_positions)
    total_deficit = sum(deficits.values())
    if total_deficit > 0 and picks_remaining <= total_deficit:
        restricted = {p for p in available if positions.get(p) in deficits}
        if restricted:
            return best_by_market_rank(restricted, market_rank)
    return best_by_market_rank(available, market_rank)


def replay_opponent_picks(
    available: set[str], market_rank: dict[str, tuple[str, float]], n_opponent_picks: int
) -> set[str]:
    """Experiment G's mechanism: step the known opponent model forward `n_opponent_picks` times
    and return what is still on the board afterward.

    Deliberately a *literal replay* rather than an analytical approximation. The controlled
    experiments tested the analytical alternative (tier D: aggregate per-player survival
    probability across a position) and it did not help (RB=0 32% vs 20% for doing nothing).

    Assumption, stated rather than hidden: opponents draft best-available-by-market-consensus.
    That is exactly true inside `evaluation/draft_simulation.py` (whose nine opponent slots are
    literally that strategy) and an approximation against real human drafters -- the same class
    of assumption `next_pick_survival_probability` already makes by modelling a player's true
    draft rank as Uniform(ecr_best, ecr_worst). See docs/EVALUATION_LIMITATIONS.md."""
    if n_opponent_picks <= 0:
        return set(available)
    remaining = set(available)
    for _ in range(n_opponent_picks):
        if not remaining:
            break
        remaining.discard(best_by_market_rank(remaining, market_rank))
    return remaining


def positional_opportunity_cost(
    available: set[str],
    positions: dict[str, str],
    vorp: dict[str, float],
    market_rank: dict[str, tuple[str, float]],
    n_opponent_picks: int,
    positions_of_interest: Iterable[str],
) -> dict[str, float]:
    """{position: opportunity cost in VORP points} -- how much value at that position is
    expected to be gone by this team's next turn.

    `max(0, best_now) - max(0, best_at_next_turn)`, clamped at replacement level (see module
    docstring). Non-negative by construction: the post-replay pool is a subset of the current
    pool, so its maximum can only be lower.

    Returns all-zero when `n_opponent_picks <= 0`. That is the correct answer, not a
    degenerate one: at a snake turn (e.g. draft slot 1 picking at overall #20 and #21 back to
    back) nothing happens in between, so nothing can be lost by waiting.

    Deterministic regardless of `set` iteration order: it maxes over VORP *values*, so tied
    VORP between two players cannot change the resulting figure."""
    wanted = list(dict.fromkeys(positions_of_interest))
    if n_opponent_picks <= 0:
        return dict.fromkeys(wanted, 0.0)

    remaining = replay_opponent_picks(available, market_rank, n_opponent_picks)

    costs: dict[str, float] = {}
    for pos in wanted:
        best_now = max(
            (vorp[p] for p in available if positions.get(p) == pos and p in vorp), default=0.0
        )
        best_next = max(
            (vorp[p] for p in remaining if positions.get(p) == pos and p in vorp), default=0.0
        )
        costs[pos] = max(0.0, best_now) - max(0.0, best_next)
    return costs


def picks_until_next_turn(current_pick_overall: int | None, next_pick_overall: int | None) -> int:
    """How many picks other teams make between this team's current and next selection.

    Correct for snake order by construction because it works off real overall pick numbers
    rather than re-deriving round/slot geometry: for draft slot 1 in a 10-team league the gaps
    genuinely alternate 18, 0, 18, 0 (the back-to-back turn), and for a middle slot they are
    steady (~8-10). Returns 0 when either endpoint is unknown, which disables the
    opportunity-cost term rather than guessing."""
    if current_pick_overall is None or next_pick_overall is None:
        return 0
    return max(0, next_pick_overall - current_pick_overall - 1)


def load_market_ranks(
    con: duckdb.DuckDBPyConnection, ecr_type: str, season: int
) -> dict[str, tuple[str, float]]:
    """Season-scoped preseason (Jul/Aug) market ranks for the opponent replay.

    Delegates to `market/edge.py::_preseason_overall_market`, which is already restricted to
    the target season's own preseason window -- so this is leakage-safe by construction and
    uses only information a real drafter had on draft day. D54 found and fixed a real leak of
    exactly this kind in `next_pick_survival_probability` (it read the latest snapshot ever
    recorded, letting a 2021 draft see 2026 market data); reusing the already-scoped helper
    means that class of bug cannot recur here."""
    return _preseason_overall_market(con, ecr_type, season)
