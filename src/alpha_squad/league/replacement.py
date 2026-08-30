"""Replacement level, positional scarcity, and marginal value over replacement -- derived
from the league's own lineup config (PRODUCT_SPEC.md: "replacement level... positional
scarcity... marginal points over replacement"), not a hardcoded assumption. This is what
makes a 2QB league's QB market genuinely different from a 1QB league's: with 10 teams x 2
dedicated QB slots and no QB flex eligibility, replacement level sits at QB21 instead of the
QB13-15 a 1QB league would produce.

Implements real value-based-drafting (VBD) with flex allocation: dedicated slots are filled
first by within-position rank, then flex slots are filled by the single best remaining
players across every flex-eligible position (earned by actual projected value, not assumed
evenly split) -- so a position's effective starter count, and therefore its replacement
level, reflects how competitive it actually is for the shared flex slots."""

from __future__ import annotations

import duckdb

from alpha_squad.league.context import FLEX_ELIGIBILITY, LeagueContext
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.roster import startable_slots
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION


def compute_league_starters(
    league: LeagueContext,
    projections: dict[str, float],
    positions: dict[str, str],
    *,
    teams: int | None = None,
) -> dict:
    """Returns starters/dedicated_starters/flex_starters/replacement_pool -- see module
    docstring for the allocation algorithm. replacement_pool[pos] is every non-starter at
    that position, ranked best-first; its first element is that position's replacement
    level player.

    `teams` overrides the league's own team count. Callers scoping the allocation to a
    single roster (outcome scoring, marginal starter value) pass `teams=1`; doing it here
    rather than through `league.model_copy(update={"teams": 1})` avoids a pydantic model
    copy, which matters because marginal starter value calls this once per candidate per
    pick -- on the order of a million times across a full ablation run."""
    dedicated = league.dedicated_slots()
    flex = league.flex_slots()
    teams = league.teams if teams is None else teams

    flex_eligible_positions: set[str] = set()
    for flex_name in flex:
        flex_eligible_positions.update(FLEX_ELIGIBILITY.get(flex_name, ()))

    all_positions = set(dedicated) | flex_eligible_positions
    pool_by_pos = {
        pos: sorted(
            (p for p in projections if positions.get(p) == pos), key=lambda p: -projections[p]
        )
        for pos in all_positions
    }

    dedicated_starters: dict[str, list[str]] = {}
    remaining_by_pos: dict[str, list[str]] = {}
    for pos in all_positions:
        n_start = teams * dedicated.get(pos, 0)
        dedicated_starters[pos] = pool_by_pos[pos][:n_start]
        remaining_by_pos[pos] = pool_by_pos[pos][n_start:]

    total_flex_slots = sum(teams * n for n in flex.values())
    flex_candidates: list[str] = []
    for pos in flex_eligible_positions:
        flex_candidates.extend(remaining_by_pos[pos])
    flex_candidates.sort(key=lambda p: -projections[p])
    flex_starters = flex_candidates[:total_flex_slots]
    flex_starter_set = set(flex_starters)

    replacement_pool = {
        pos: [p for p in remaining_by_pos[pos] if p not in flex_starter_set]
        for pos in all_positions
    }

    starters = set(flex_starters)
    for pos_list in dedicated_starters.values():
        starters.update(pos_list)

    return {
        "starters": starters,
        "dedicated_starters": dedicated_starters,
        "flex_starters": flex_starters,
        "replacement_pool": replacement_pool,
    }


def replacement_level(
    league: LeagueContext, projections: dict[str, float], positions: dict[str, str]
) -> dict[str, float]:
    result = compute_league_starters(league, projections, positions)
    levels = {}
    for pos, pool in result["replacement_pool"].items():
        levels[pos] = projections[pool[0]] if pool else 0.0
    return levels


def positional_scarcity(
    league: LeagueContext, projections: dict[str, float], positions: dict[str, str]
) -> dict[str, float]:
    """Mean value of that position's actual starters (dedicated + earned flex slots) minus
    its replacement level -- the classic VBD scarcity read: a large gap means a bench-caliber
    player at that position is worth much less than a real starter, i.e. the position is
    scarce; a small gap means replacement-level production is nearly as good as starting."""
    result = compute_league_starters(league, projections, positions)
    levels = replacement_level(league, projections, positions)
    scarcity = {}
    for pos, dedicated_list in result["dedicated_starters"].items():
        pos_flex_starters = [p for p in result["flex_starters"] if positions.get(p) == pos]
        pos_starters = dedicated_list + pos_flex_starters
        if not pos_starters:
            scarcity[pos] = 0.0
            continue
        mean_starter_value = sum(projections[p] for p in pos_starters) / len(pos_starters)
        scarcity[pos] = mean_starter_value - levels.get(pos, 0.0)
    return scarcity


def marginal_value_over_replacement(
    league: LeagueContext, projections: dict[str, float], positions: dict[str, str]
) -> dict[str, float]:
    """Per-player VORP: projected points minus that player's position's replacement level.
    This, not raw projected points, is what should drive draft/waiver value -- a player
    projected for fewer points at a scarce position can be worth more than a
    higher-projected player at a deep one."""
    levels = replacement_level(league, projections, positions)
    return {
        p: projections[p] - levels[positions[p]] for p in projections if positions.get(p) in levels
    }


def best_lineup_points(
    league: LeagueContext,
    roster: list[str],
    projections: dict[str, float],
    positions: dict[str, str],
) -> float:
    """Projected points of the best legal starting lineup THIS roster can field (D58).

    Reuses `compute_league_starters` with `teams: 1` so the slot allocation -- dedicated
    slots by within-position rank, then flex slots to the best remaining flex-eligible
    players -- is the same logic the benchmark scores rosters with, rather than a second
    implementation that could disagree with it.

    An incomplete roster simply leaves slots empty, which is the correct reading during a
    draft: a team with three players has three starters and seven holes."""
    roster_projections = {p: projections.get(p, 0.0) for p in roster}
    roster_positions = {p: positions.get(p, "UNKNOWN") for p in roster}
    starters = compute_league_starters(league, roster_projections, roster_positions, teams=1)
    return sum(roster_projections.get(p, 0.0) for p in starters["starters"])


def marginal_starter_value(
    league: LeagueContext,
    roster: list[str],
    candidate: str,
    projections: dict[str, float],
    positions: dict[str, str],
    *,
    base_points: float | None = None,
) -> float:
    """How much adding `candidate` would improve this roster's best starting lineup (D58).

    This is the question the pre-D58 scoring path could not ask. VORP measures a player
    against a *league-wide* replacement level, and `roster_need` measures a positional
    *count* -- so a player was scored identically whether he would be your WR1 or your WR5.
    Marginal starter value asks instead whether he would actually start, and by how much he
    would beat whoever he displaces.

    Early in a draft, when slots are empty, this equals the candidate's own projection, so it
    behaves like best-player-available. Once a position's slots are full it collapses toward
    zero, which is the honest reading: a sixth wide receiver does not improve the lineup this
    week. It is therefore a complement to VORP and opportunity cost -- which price
    season-long scarcity and near-term availability -- not a replacement for either.

    `base_points` lets a caller hoist the current-lineup calculation out of a per-candidate
    loop; it is the only thing that does not vary across candidates at one pick."""
    if base_points is None:
        base_points = best_lineup_points(league, roster, projections, positions)
    with_candidate = best_lineup_points(league, [*roster, candidate], projections, positions)
    return with_candidate - base_points


# Sentinel id for the hypothetical freely-available, replacement-level body used by
# `replacement_marginal_starter_values`. Never a real player id (real ids are `asq_`-prefixed,
# see identity/canonical.py), so it cannot collide with a drafted player.
_REPLACEMENT_SENTINEL = "__replacement_level_body__"


def replacement_marginal_starter_values(
    league: LeagueContext,
    roster: list[str],
    projections: dict[str, float],
    positions: dict[str, str],
    replacement_levels: dict[str, float],
    *,
    base_points: float | None = None,
) -> dict[str, float]:
    """{position: the marginal starter value a REPLACEMENT-LEVEL body at that position would
    add to this roster} (D63 Stage 3, tier N3).

    This is the subtrahend in "marginal starter value over replacement":

        msv_over_replacement(candidate)
            = best_lineup(roster + candidate) - best_lineup(roster + replacement body)
            = marginal_starter_value(candidate) - this[candidate's position]

    Why it is the principled unification of the two value bases the engine has used. On an
    EMPTY roster both lineups gain their new player outright, so the difference is
    `projection - replacement_level` -- exactly VORP, which is what correctly refuses an early
    QB in a 1-QB league. At a SATURATED position neither the candidate nor the replacement body
    can crack the lineup, so both terms are 0 and the difference is 0 -- exactly the lineup
    saturation that stops a bench kicker from being priced above zero. It reduces to each of
    VORP and MSV in the regime where that one is right, by construction rather than by
    clamping between them (contrast tier N2's `min(vorp, msv)`).

    Returned per POSITION, not per candidate, because the replacement body depends only on the
    position -- so a caller computes this once per pick (a handful of positions) instead of
    once per candidate (thousands). `best_lineup_points` only ever reads roster members, so the
    augmented dicts here are O(roster), not O(all players)."""
    if base_points is None:
        base_points = best_lineup_points(league, roster, projections, positions)

    roster_projections = {p: projections.get(p, 0.0) for p in roster}
    roster_positions = {p: positions.get(p, "UNKNOWN") for p in roster}
    augmented_roster = [*roster, _REPLACEMENT_SENTINEL]

    values: dict[str, float] = {}
    for position, level in replacement_levels.items():
        with_replacement = best_lineup_points(
            league,
            augmented_roster,
            {**roster_projections, _REPLACEMENT_SENTINEL: level},
            {**roster_positions, _REPLACEMENT_SENTINEL: position},
        )
        values[position] = with_replacement - base_points
    return values


def market_draft_demand(
    league: LeagueContext,
    market_rank: dict[str, tuple[str, float]],
    projections: dict[str, float],
    positions: dict[str, str],
) -> dict[str, float]:
    """{position: players at that position a full draft of THIS league consumes, per team}
    (docs/DECISIONS.md D67) -- the demand target `demand_boundary_replacement` draws
    replacement level at.

    Measured by running one mock draft of this league on the **preseason consensus board
    alone**: `teams x roster_size` picks, best-available by ECR with the endgame mandatory-slot
    reservation (`opportunity_cost.py::roster_aware_market_pick`), then counting each position.
    `sum(target) == roster_size` by construction, so league-wide demand is exactly the number of
    picks the draft makes -- the structural anchor, and the reason there is no free parameter
    here to tune.

    **Why this and not the earlier depth targets.** Replacement level is classically "the best
    player at this position still freely available after the draft". This computes that
    literally. The targets tried before it all answered a different question and got the SHAPE
    wrong, not merely the scale (measured over 2021-2025, per team, target format):

        target                     QB    RB    WR    TE     K   DST   sums to
        lineup slots                1     2     2     1     1     1     10
        startable_slots             1     4     4     3     1     1     14   (FLEX counted 3x)
        positional_capacity         2     6     6     4     2     2     22
        THIS (measured)          2.04  4.64  5.64  1.68  1.00  1.00     16   = roster_size

    `startable_slots` under-counts QB 2x and over-counts TE 1.8x, which is why no uniform
    multiplier on it can be right: D66's sweep had to reach 2.5x before QB stopped exhausting
    (QB's base is 1), and by then TE demanded 75 and K demanded 25 out of a 45-deep pool.

    **Why a multiplier looked like it worked, and why that was an artifact.** Deepening demand
    is arithmetically identical to adding a fixed bonus to every player at a position, and the
    bonus size is set by the shape of that position's projection tail. At 2.5x, measured: RB
    +120.4, QB +108.9, TE +106.4, WR +92.0, but K +30.4 and DST +10.7 -- because there are ~225
    WRs with a long tail and exactly 32 team defenses. Kicker hoarding disappeared not because
    kickers were priced correctly but because everyone else received ~100 points and kickers
    received 30. That is a positional re-weighting governed by pool depth, not by scarcity.

    **Leakage.** `market_rank` comes from `opportunity_cost.py::load_market_ranks`, already
    restricted to the drafted season's own Jul/Aug snapshots (D54), so this uses only what a
    real drafter had on draft day. No realized outcome touches it.

    Costs ~11ms per call and is therefore computed per recommendation rather than cached, so a
    re-ingest can never serve a stale target."""
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
            pick = roster_aware_market_pick(
                available, market_rank, positions, league, rosters[slot], picks_remaining
            )
            pos = positions.get(pick, "UNKNOWN")
            rosters[slot].append(pos)
            counts[pos] = counts.get(pos, 0) + 1
            available.discard(pick)

    teams = league.teams or 1
    targets = {pos: counts.get(pos, 0) / teams for pos in startable_slots(league)}
    # A position the board never reaches but the lineup requires still has to be priced against
    # something real, so its dedicated requirement is a floor rather than collapsing to zero
    # demand on pick 1. Inert in the target format (the mock draft takes all 10 kickers and all
    # 10 defenses); it exists for a board that omits a position -- measured: the real `ro` board
    # carries zero kickers in its top 160 in every season 2021-2025.
    for pos, slots in league.dedicated_slots().items():
        targets[pos] = max(targets.get(pos, 0.0), float(slots))
    return targets


def demand_boundary_replacement(
    league: LeagueContext,
    available: set[str],
    projections: dict[str, float],
    positions: dict[str, str],
    per_team_demand: dict[str, float],
) -> dict[str, float]:
    """Draft-aware replacement level: the projection of the player sitting exactly at the
    boundary of what the league still has to absorb at that position (docs/DECISIONS.md D67).

        drafted[pos]       = (players at pos in the FULL pool) - (players at pos available)
        remaining[pos]     = max(0, teams * per_team_demand[pos] - drafted[pos])
        replacement[pos]   = projection of the remaining-th best AVAILABLE player (0-indexed),
                             the worst available if demand exceeds supply, 0.0 if exhausted

    Fixes the D65 defect: production previously computed replacement once from the full season
    pool, so the level a pick was scored against was numerically identical at pick 1 and pick
    160. Measured on real 2022 data at round 13 the static level was +178.2 too high for QB and
    +69.1 for WR but only +2.2 for K -- the engine was not over-valuing kickers so much as
    under-valuing everyone else.

    When `remaining` reaches 0 -- every team that could use one already has one -- replacement
    becomes the best available player and that position's surplus is identically zero. With the
    demand target from `market_draft_demand` that happens in rounds 14-16, i.e. only once the
    position genuinely is satisfied. It is a real failure mode at a target that is too shallow:
    at `startable_slots` demand, QB exhausts by round 8.8 and WR by 9.4, and those positions go
    invisible to the value term for the rest of the draft.

    The opposite degeneracy -- `remaining` exceeding what is on the board, so the boundary player
    does not exist to be observed -- **omits the position from the result entirely**, and callers
    read that as "use the season-long static level for this position". It cannot be papered over
    by clamping to the worst available player: that would set replacement to the bottom of the
    pool and hand every other player at the position a large spurious surplus.

    That guard is not hypothetical. It never fires during a real draft (0/800 real pick-states, at
    every position and every depth measured up to 3x startable) because the board is deep. But
    `available` is not always the board: `POST /league/{id}/draft` lets a caller pass an arbitrary
    `available_player_ids`, and a shortlist of two receivers means "these are the players I am
    asking about", not "these are the only receivers left in the league". Without this guard, that
    shortlist would silently redefine replacement level as the worse of the two."""
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
    for pos, target in per_team_demand.items():
        pool = sorted(avail_by_pos.get(pos, []), key=lambda p: -projections[p])
        drafted = full_by_pos.get(pos, 0) - len(pool)
        remaining_demand = max(0, round(league.teams * target) - drafted)
        if remaining_demand > len(pool) - 1:
            continue  # boundary not on the board -- see the docstring; caller falls back
        levels[pos] = projections[pool[remaining_demand]]
    return levels


def load_season_projections(
    con: duckdb.DuckDBPyConnection, season: int
) -> tuple[dict[str, float], dict[str, str]]:
    """Real per-season projections from M6's uncertainty model (point_prediction) -- the
    same model M8's EDGE and M9's evidence adjustments already build on, so the league
    engine reasons about the same numbers the rest of the system does, not a separate path.

    M6's season-level model requires a prior season's stats and structurally excludes true
    rookies (verified against real data: 0 of 442 real 2024 uncertainty_predictions rows
    belong to a rookie_season=2024 player) -- exactly the class of player a waiver-wire or
    rookie-draft recommendation most needs. Rookies are filled in from M7's real
    rookie_predictions (draft_class == season) rather than silently omitted, so the league
    engine can still evaluate them; established players always take the M6 value when both
    exist, since M6 has more information (an actual prior season) to work with."""
    rows = con.execute(
        "SELECT player_id, position, point_prediction FROM uncertainty_predictions "
        "WHERE season = ? AND model_version = ?",
        [season, UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    projections = {r[0]: r[2] for r in rows}
    positions = {r[0]: r[1] for r in rows}

    rookie_rows = con.execute(
        "SELECT player_id, position, predicted_rookie_points FROM rookie_predictions "
        "WHERE draft_class = ? AND predicted_rookie_points IS NOT NULL",
        [season],
    ).fetchall()
    for player_id, position, predicted_points in rookie_rows:
        if player_id not in projections:
            projections[player_id] = predicted_points
            positions[player_id] = position

    # K and DST (D57). M6's uncertainty model covers QB/RB/WR/TE only -- it is trained on a
    # receiving/rushing/passing feature panel that has no meaning for a kicker or a team
    # defense. A league that starts a K and a DEF still has to be able to evaluate them, so
    # they come from the measured baseline in models/baselines/kicking_defense.py, which is
    # deliberately a baseline rather than a model (both positions carry weak year-over-year
    # signal; see that module for the numbers). Added last and only where absent, so a
    # position the primary model does cover is never overwritten by a baseline.
    kdst_rows = con.execute(
        "SELECT player_id, position, predicted_points FROM projection_snapshot "
        "WHERE model_name = ? AND season = ?",
        [KDST_MODEL_NAME, season],
    ).fetchall()
    for player_id, position, predicted_points in kdst_rows:
        if player_id not in projections:
            projections[player_id] = predicted_points
            positions[player_id] = position

    return projections, positions
