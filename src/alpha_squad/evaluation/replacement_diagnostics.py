"""Diagnostic-only draft-aware replacement levels (docs/DECISIONS.md D65).

**This module is NOT used by production.** `league/draft.py` computes VORP once per call from
`load_season_projections`'s full-season pool, which never sees `available_player_ids` -- so the
replacement level a real pick is scored against is numerically identical at pick 1 and pick 160.
That staleness is the defect this module exists to quantify. Nothing here is imported by
production code; the ablation tiers in `evaluation/draft_forensics.py` are the only consumers.

**The measured problem.** Ten teams strip the skill-position pools while barely touching K/DST,
so by the late rounds the static level is wildly wrong for skill positions and almost exactly
right for kickers. Measured on real 2022 data at round 13 (`docs/DECISIONS.md` D65):

    position   static replacement   available-pool replacement   error
    WR                    149.0                          79.9   +69.1
    QB                    289.2                         111.0  +178.2
    RB                    146.7                          84.4   +62.3
    TE                    133.7                          88.1   +45.6
    K                     132.2                         130.0    +2.2
    DST                    98.7                          92.4    +6.3

So a late WR is scored against a replacement level 69 points too high (crushing its VORP toward
zero) while a late kicker is scored against a nearly correct one. The engine is not
over-valuing kickers so much as *under-valuing everyone else*.

Three definitions are offered, all derived from the league's own configuration and the observed
draft state. None introduces a tuned constant.
"""

from __future__ import annotations

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import compute_league_starters, replacement_level
from alpha_squad.league.roster import positional_capacity, startable_slots


def available_pool_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """**Candidate A -- available-pool replacement.**

        replacement_A[pos] = replacement_level(league, pool restricted to `available`)[pos]

    i.e. run the *existing, unmodified* VBD allocation (`league/replacement.py::
    replacement_level`: fill `teams x dedicated` slots by within-position rank, then flex by
    best-remaining across eligible positions, then take the best non-starter) over only the
    players still on the board.

    The most literal reading of "make replacement draft-aware", and deliberately the least
    inventive: it changes the *pool* and nothing else, so any effect is attributable to
    staleness alone. Its known weakness is that it keeps demanding `teams x slots` starters
    from a shrinking pool even in the last round, when most teams have long since filled those
    slots -- it corrects the pool but not the demand. Candidates B and C address that.
    """
    pool_projections = {p: projections[p] for p in available if p in projections}
    pool_positions = {p: positions[p] for p in available if p in positions}
    return replacement_level(league, pool_projections, pool_positions)


def _remaining_demand_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
    per_team_target: dict[str, float],
) -> dict[str, float]:
    """Shared engine for Candidates B and C: replacement is the projection of the player who
    sits exactly at the boundary of what the league still needs at that position.

        drafted[pos]           = (players at pos in the FULL pool) - (players at pos available)
        remaining_demand[pos]  = max(0, teams * per_team_target[pos] - drafted[pos])
        replacement[pos]       = projection of the remaining_demand-th best AVAILABLE player
                                 (0-indexed), or the worst available if demand exceeds supply,
                                 or 0.0 if the position is exhausted

    `remaining_demand` counts how many more players at that position the league as a whole still
    has to absorb before the position stops being contested. When it is 0 -- every team that
    could use one already has one -- replacement collapses to the best available player, which
    correctly prices a surplus body at zero surplus.
    """
    full_by_pos: dict[str, int] = {}
    for player_id in projections:
        pos = positions.get(player_id)
        if pos is not None:
            full_by_pos[pos] = full_by_pos.get(pos, 0) + 1

    avail_by_pos: dict[str, list[str]] = {}
    for player_id in available:
        pos = positions.get(player_id)
        if pos is not None and player_id in projections:
            avail_by_pos.setdefault(pos, []).append(player_id)

    levels: dict[str, float] = {}
    for pos, target in per_team_target.items():
        pool = sorted(avail_by_pos.get(pos, []), key=lambda p: -projections[p])
        if not pool:
            levels[pos] = 0.0
            continue
        drafted = full_by_pos.get(pos, 0) - len(pool)
        remaining_demand = max(0, round(league.teams * target) - drafted)
        index = min(remaining_demand, len(pool) - 1)
        levels[pos] = projections[pool[index]]
    return levels


def remaining_demand_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """**Candidate B -- remaining-demand replacement (starters only).**

    `per_team_target` = `startable_slots(league)`: the slots a position could actually start in,
    dedicated plus flex-eligible. In the 1-QB target format that is QB 1, RB 4, WR 4, TE 3,
    K 1, DST 1.

    This is the definition that makes K structurally different without naming it: the league
    needs only `10 x 1 = 10` kickers in total, so once ten are gone the eleventh is priced
    against the best available kicker and its surplus goes to zero -- while WR, needing
    `10 x 4 = 40`, stays contested far longer. Demand comes from the lineup, not from a rule.
    """
    return _remaining_demand_replacement(
        league, available, projections, positions, startable_slots(league)
    )


def hybrid_capacity_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """**Candidate C -- hybrid: remaining demand including bench depth.**

    Identical to Candidate B except `per_team_target` = `positional_capacity(league, pos)`, the
    architecture's existing notion of how many bodies at a position a roster can *use* --
    startable slots plus that position's proportional share of the bench. In the target format
    that is QB 2, RB 6, WR 6, TE 4, K 2, DST 2.

    Reusing `positional_capacity` is what keeps this defensible rather than invented: it is the
    same function `positional_feasibility_cap` already relies on, so the bench component is the
    one the project already derived and tested (D58), not a new constant. Candidate B prices a
    position as uncontested the moment its starting slots are covered; C keeps it contested
    while teams still have bench room they would plausibly spend on it.
    """
    targets = {pos: positional_capacity(league, pos) for pos in startable_slots(league)}
    return _remaining_demand_replacement(league, available, projections, positions, targets)


def dedicated_plus_one_bench_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """**Candidate C4 -- dedicated starters plus one bench slot** (D66).

    `per_team_target[pos] = dedicated_slots[pos] + 1`. In the 1-QB target format: QB 2, RB 3,
    WR 3, TE 2, K 2, DST 2.

    The documented D65 proposal, kept exactly as proposed. It sidesteps the flex over-count
    entirely by ignoring flex, then restores a uniform single unit of depth -- "every position
    can carry one backup", which is the same floor `positional_capacity` already guarantees via
    its `max(1, ...)`. Its known weakness is the mirror of C3's: by ignoring flex it *under*
    -counts the positions that genuinely contest the flex slots.
    """
    dedicated = league.dedicated_slots()
    targets = {pos: dedicated.get(pos, 0) + 1 for pos in startable_slots(league)}
    return _remaining_demand_replacement(league, available, projections, positions, targets)


def earned_starter_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """**Candidate C5 -- earned-starter demand** (D66).

    `per_team_target[pos] = (dedicated starters at pos + flex slots pos actually WINS) / teams`,
    read off `compute_league_starters` over the full season pool -- the same allocation the
    replacement level itself is built on.

    **Why this is the structurally correct target, and what it fixes.** `startable_slots` counts
    every flex slot once per *eligible* position, so in this format it sums to 14 per team while
    the lineup starts only 10 -- the 2 FLEX slots are counted 3x (RB, WR, TE) instead of once.
    Candidates B and C inherit that error and then demand 140 and 220 league-wide players for
    100 real starting slots. TE is hit hardest: its startable count of 3 assumes it wins both
    flex slots, but measured over all five real seasons **WR wins all 20 flex slots and TE wins
    none**, so TE's true starter demand is 1.00 per team, not 3 or 4. That 3-4x overstatement is
    the TE-loading mechanism D65 could not explain.

    This target sums to exactly the lineup size by construction, and it is measured from the
    projections rather than assumed -- no new constant, and it adapts automatically to a format
    where TE *does* win flex slots.
    """
    result = compute_league_starters(league, projections, positions)
    flex_by_pos: dict[str, int] = {}
    for player_id in result["flex_starters"]:
        pos = positions.get(player_id)
        if pos is not None:
            flex_by_pos[pos] = flex_by_pos.get(pos, 0) + 1
    targets: dict[str, float] = {}
    for pos in startable_slots(league):
        earned = len(result["dedicated_starters"].get(pos, [])) + flex_by_pos.get(pos, 0)
        targets[pos] = earned / league.teams if league.teams else 0.0
    return _remaining_demand_replacement(league, available, projections, positions, targets)


def mock_draft_consumption_demand(
    league: LeagueContext,
    market_rank: dict[str, tuple[str, float]],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """{position: players at that position a full draft of THIS league consumes, per team}
    (docs/DECISIONS.md D67) -- the demand target for `consumption_replacement`.

    Obtained by running one mock draft of this league on the **preseason consensus board
    alone**: `teams x roster_size` picks, best-available by ECR, with the same endgame
    mandatory-slot reservation `evaluation/draft_simulation.py::
    _market_consensus_roster_aware_pick` already implements, then counting each position.
    `sum(target) == roster_size` by construction, so league-wide demand is exactly the number
    of picks the draft makes.

    **Why this is the structural target and every previous one was not.** D66 established that
    demand *depth* governs the draft-aware replacement level, and that a uniform multiplier on
    `startable_slots` measures well. D67 established *why*, and it is not a reason to keep the
    multiplier: deepening demand is arithmetically identical to adding a fixed bonus to every
    player at a position, and the size of that bonus is set by the shape of the position's
    projection tail, not by anything about scarcity. Measured at scale x2.5 on real 2021-2025
    data, the per-position VORP bonus is RB +120.4, QB +108.9, TE +106.4, WR +92.0 -- but K
    +30.4 and DST +10.7, because there are ~45 kickers whose tail collapses to a 2.0 floor and
    exactly 32 team defenses. A knob whose effect size is governed by how many kickers exist in
    the database is a positional re-weighting in disguise, not a criterion.

    What replaces it is the classic VBD definition made literal: replacement level is the best
    player at a position who will still be undrafted when the draft ends. That question has an
    exact answer for a given board, and this function computes it.

    The measured shape (2021-2025, target format, per team) is QB 2.04, RB 4.64, WR 5.64,
    TE 1.68, K 1.00, DST 1.00 -- against `startable_slots`' QB 1, RB 4, WR 4, TE 3, K 1, DST 1.
    `startable_slots` is wrong in SHAPE, not merely in scale: it under-counts QB 2x and
    over-counts TE 1.8x, which is why no uniform multiplier can repair it, and why the scale
    that keeps QB non-degenerate (>2.5, because QB's base is 1) simultaneously drives TE demand
    to 75 and K demand to 25 against a 45-deep pool.

    Properties that make it defensible rather than fitted:

    * **No tunable.** There is no scale to choose, so there is no argmax to select.
    * **Flex resolves itself.** Flex slots go to whoever the board says; the count reflects it.
      No triple-counting (Candidates B/C), no under-counting (C4/C5), and no need to decide
      whether TE *ought* to win flex slots.
    * **Format-adaptive.** Run it on `legacy_2qb_dynasty` and it produces that format's
      allocation from that format's board, with no code change.
    * **Leakage-safe.** Preseason ECR only -- `market_rank` comes from `_preseason_overall_market`,
      which is already scoped to the Jul/Aug snapshots of the season being drafted (D54). No
      realized outcome touches it.

    Positions absent from the board contribute nothing, and a position the mock draft never
    takes gets 0.0 -- which `_remaining_demand_replacement` reads as "uncontested", the correct
    statement for a position this league's market does not draft.
    """
    from alpha_squad.evaluation.draft_simulation import _market_consensus_roster_aware_pick

    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    available = set(projections)
    rosters: dict[int, list[str]] = {slot: [] for slot in range(1, league.teams + 1)}
    counts: dict[str, int] = {}
    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        picks_remaining = total_rounds - round_no + 1
        for slot in order:
            if not available:
                break
            pick = _market_consensus_roster_aware_pick(
                available, market_rank, positions, league, rosters[slot], picks_remaining
            )
            pos = positions.get(pick, "UNKNOWN")
            rosters[slot].append(pos)
            counts[pos] = counts.get(pos, 0) + 1
            available.discard(pick)

    teams = league.teams or 1
    targets = {pos: counts.get(pos, 0) / teams for pos in startable_slots(league)}
    # A position the board never reaches but the lineup requires still has to be priced against
    # something real, so it keeps its dedicated requirement as a floor rather than collapsing to
    # zero demand on pick 1. In the target format the mock draft takes all 10 kickers and all 10
    # defenses, so this floor is inert there -- it exists for a board that omits a position
    # entirely (measured: the `ro` board carries 0 kickers in its top 160 in every season).
    for pos, slots in league.dedicated_slots().items():
        targets[pos] = max(targets.get(pos, 0.0), float(slots))
    return targets


def consumption_replacement(per_team_target: dict[str, float]):
    """Factory: draft-aware replacement drawn at `mock_draft_consumption_demand`'s target.

    Takes the target rather than computing it because it depends on the season's consensus
    board, which the per-pick variant signature does not carry -- the caller computes it once
    per season (`load_season_static`) exactly as it already does for VORP and market ranks.
    """

    def variant(
        league: LeagueContext,
        available: set[str],
        projections: dict[str, float],
        positions: dict[str, str],
    ) -> dict[str, float]:
        return _remaining_demand_replacement(
            league, available, projections, positions, per_team_target
        )

    return variant


#: Demand-depth multipliers for the D66 Phase 4 sensitivity sweep. Each scales the
#: `startable_slots` target uniformly, so the ONLY thing that varies across the sweep is how
#: deep into each position's pool the replacement level is drawn. Reference points on this
#: axis: 0.71 sums to the true lineup size (10/team), 1.00 is Candidate C2, and 1.57 is where
#: Candidate C3's `positional_capacity` target (22/team) sits.
SWEEP_SCALES = (0.75, 1.0, 1.5, 2.0, 2.5, 3.0)


def scaled_startable_replacement(scale: float):
    """Factory for the sensitivity sweep: `per_team_target[pos] = scale x startable_slots[pos]`.

    Uniform by construction -- it cannot re-shape demand BETWEEN positions, only deepen or
    shallow it everywhere at once. That is what makes the sweep a clean one-dimensional test of
    demand depth rather than another candidate definition.
    """

    def variant(
        league: LeagueContext,
        available: set[str],
        projections: dict[str, float],
        positions: dict[str, str],
    ) -> dict[str, float]:
        targets = {pos: scale * n for pos, n in startable_slots(league).items()}
        return _remaining_demand_replacement(league, available, projections, positions, targets)

    return variant


#: The diagnostic definitions, keyed by the ablation tier that uses each.
REPLACEMENT_VARIANTS = {
    "available_pool": available_pool_replacement,
    "remaining_demand": remaining_demand_replacement,
    "hybrid_capacity": hybrid_capacity_replacement,
    "dedicated_plus_one_bench": dedicated_plus_one_bench_replacement,
    "earned_starter": earned_starter_replacement,
    **{f"scale_{sc}": scaled_startable_replacement(sc) for sc in SWEEP_SCALES},
}
