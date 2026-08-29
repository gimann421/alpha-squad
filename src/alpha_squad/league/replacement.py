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
