"""Diagnostic-only draft-engine forensic experiment harness (docs/DRAFT_ENGINE_FORENSIC_AUDIT.md,
docs/DRAFT_CONTROLLED_EXPERIMENTS.md).

This module is NOT used by production `league/draft.py` and does NOT replace
`evaluation/draft_simulation.py` (the official, already-validated benchmark harness behind
docs/DECISIONS.md D54's results). It exists so the *same* fixed opponent field, snake-draft
loop, and outcome scoring can run under eight explicitly-labeled, additively-constructed
scoring mechanisms (tiers A-H below) for a true ceteris-paribus ablation: isolating which
mechanism changes which failure, not picking a winner or tuning against real outcomes.

Every tier after A adds exactly one new term on top of the previous tier's score, in the order
the forensic directive specifies. Tier H calls the real, unmodified `recommend_draft_pick` so
the ablation has an honest endpoint to compare against the actual shipped behavior.

Static season data (projections, VORP, replacement levels, positional scarcity, market ranks,
confidence, ECR dispersion) is loaded ONCE per season into plain dicts rather than re-queried
per pick -- unlike `recommend_draft_pick`, which re-queries per candidate per pick (fine at
real single-user-draft scale, far too slow for the hundreds of drafts this diagnostic phase
needs). The *values* and formulas are identical to production; only the query pattern differs,
and every tier that reuses a production concept calls the production function directly
(`replacement_level`, `positional_scarcity`, `marginal_value_over_replacement`,
`roster_need`, `roster_fit_multiplier`) rather than reimplementing it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import duckdb

from alpha_squad.evaluation.draft_simulation import (
    _market_consensus_pick,
    _next_pick_overall,
    _snake_overall_pick,
)
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import (
    picks_until_next_turn,
    positional_opportunity_cost,
    replay_opponent_picks,
)
from alpha_squad.league.replacement import (
    best_lineup_points,
    load_season_projections,
    marginal_starter_value,
    marginal_value_over_replacement,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.roster import roster_fit_multiplier, roster_need
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

Tier = Literal[
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "P0",
    "P1",
    "P1b",
    "P1c",
    "P2",
    "P3",
    "M0",
    "M1",
    "M2",
    "M3",
]
ALL_TIERS: tuple[Tier, ...] = ("A", "B", "C", "D", "E", "F", "G", "H")

# --- P-tiers (D55) -----------------------------------------------------------------------
# The A-H ablation established the ROOT CAUSE but could not, by itself, tell us what to ship:
# tier F (the best performer) is `vorp x fit x scarcity x future x [feasibility] + opp_cost`,
# which INCLUDES `scarcity_mult` -- the one mechanism the experiments proved harmful -- and
# EXCLUDES production's `risk_mult` and `survival_mult`. The redesign recommendation's proposed
# formula (`production + opp_cost`) was therefore never actually measured by A-H.
#
# The P-tiers close that gap: they hold the REAL production formula fixed as the base and vary
# only what is added on top, so the measured result belongs to a formula we could actually ship.
P_TIERS: tuple[Tier, ...] = ("P0", "P1", "P1b", "P1c", "P2", "P3")

# --- M-tiers (D58): marginal STARTER value ---------------------------------------------
# The 1-QB format audit found the scoring path has no representation of the team's own
# starting lineup. VORP measures a player against a LEAGUE-WIDE replacement level and
# `roster_need` measures a positional COUNT, so a player is scored identically whether he
# would be your WR1 or your WR5 -- the engine cannot ask "would this player actually start".
#
# M0 is the shipped production formula, unchanged, as the control. M1-M3 vary only where
# marginal starter value enters, from least to most invasive, so the measurement says which
# (if any) is worth shipping rather than assuming the most elaborate one is.
M_TIERS: tuple[Tier, ...] = ("M0", "M1", "M2", "M3")

# PRE-REGISTERED DECISION RULE for the M-tiers -- committed to source BEFORE these were run
# against real data, following the same D39/D54/D55 discipline as the P-tiers above.
#
#   Primary metric : mean realized starter points (docs/BENCHMARK_SPEC.md's primary).
#   Gate 1         : no position carrying a starting requirement may be zeroed at a higher
#                    rate than M0 zeroes it.
#   Gate 2         : every drafted roster must remain able to field a legal lineup at least
#                    as often as M0's do.
#   Tie-break      : prefer FEWER added mechanisms (Occam), then the simpler formulation.
#   Ship only if   : primary is STRICTLY better than M0's, and both gates pass.
#
# A tier that produces prettier-looking rosters while losing starter points does NOT qualify,
# and neither does one that wins by a margin smaller than the season-to-season spread.
PREREGISTERED_M_CONTROL: Tier = "M0"

# `msv_mult` maps marginal starter value onto the same bounded [0.7, 1.3] shape the existing
# roster-fit and scarcity multipliers use, so tier M2 swaps one bounded multiplier for
# another rather than changing the score's scale. The ratio is the share of a candidate's own
# projection that would actually reach the starting lineup: 1.0 for a player who starts at
# full value, 0.0 for one who would not start at all.
MSV_MULT_FLOOR = 0.7
MSV_MULT_RANGE = 0.6


def marginal_starter_multiplier(msv: float, projection: float) -> float:
    """Bounded [0.7, 1.3] multiplier from marginal starter value (tier M2)."""
    if projection <= 0:
        return MSV_MULT_FLOOR
    ratio = max(0.0, min(1.0, msv / projection))
    return MSV_MULT_FLOOR + MSV_MULT_RANGE * ratio


# PRE-REGISTERED DECISION RULE -- committed before the P-tiers were ever run against real data,
# following the D39/D54 discipline of fixing the rule before seeing the outcome so a result
# cannot be rationalised after the fact.
#
#   Primary metric : mean starter points (the metric that decides real fantasy outcomes; total
#                    roster points rewards bench hoarding, which is the pathology under study).
#   Gate 1         : RB=0 rate must not exceed production's measured 10/50.
#   Gate 2         : no position carrying a starting requirement may be zeroed at a HIGHER rate
#                    than production zeroes it (guards against trading one hole for another).
#   Tie-break      : prefer the tier with FEWER added mechanisms (Occam; each mechanism is
#                    future maintenance and another way to be wrong).
#   Ship only if   : primary is STRICTLY better than P0's, and both gates pass.
#
# A tier that improves RB=0 while losing starter points does NOT qualify. Improving the
# headline pathology is not by itself evidence the system got better.
PREREGISTERED_PRIMARY_METRIC = "mean_starter_points"
PREREGISTERED_RB_ZERO_GATE = 10  # out of 50 trials; production's measured rate

TIER_DESCRIPTIONS: dict[Tier, str] = {
    "A": "raw player value only, no roster context",
    "B": "+ current roster fit (roster_need / roster_fit_multiplier, unchanged from production)",
    "C": "+ current positional scarcity (positional_scarcity -- computed in production for "
    "waiver.py but never consulted by draft.py)",
    "D": "+ analytical future positional scarcity (aggregate per-player survival-probability "
    "decay, extended from a single candidate to the whole position)",
    "E": "+ roster feasibility (a hard, league-config-derived cap, replacing roster_fit's soft "
    "bound once a position is unambiguously full)",
    "F": "+ explicit opportunity cost (current value vs. this position's expected value at my "
    "next pick, priced in points, not just a multiplier)",
    "G": "+ opponent-behavior simulation (literally replay the known real market-consensus "
    "opponent strategy forward to my next pick, rather than approximate it analytically)",
    "H": "the real, unmodified production recommend_draft_pick",
    # P-tiers: production formula held fixed as the base, only the addition varies (D55).
    "P0": "production formula reproduced in-harness (vorp x fit x risk x survival) -- the "
    "control; must match tier H closely or the harness does not model production",
    "P1": "P0 + opp_cost (raw additive) -- the redesign recommendation's literal proposal",
    "P1b": "P0 + opp_cost x risk_mult (confidence-scaled additive)",
    "P1c": "(vorp + opp_cost) x fit x risk x survival -- integrated: the opportunity cost is "
    "itself denominated in VORP points, so it is discounted by the same roster-fit and "
    "confidence factors as the value it augments",
    "P2": "P0 x feasibility_mult (hard league-derived positional cap, no opportunity cost)",
    "P3": "P1c x feasibility_mult (integrated opportunity cost + feasibility cap)",
    # M-tiers (D58): where marginal STARTER value enters, least to most invasive.
    "M0": "the shipped production formula, unchanged -- (vorp + opp_cost) x fit x risk x "
    "survival x [feasibility]. The control.",
    "M1": "M0 + marginal starter value added inside the value term: "
    "(vorp + opp_cost + msv) x fit x risk x survival x [feasibility]",
    "M2": "M0 with the COUNT-based roster-fit multiplier replaced by a starter-value one: "
    "(vorp + opp_cost) x msv_mult x risk x survival x [feasibility]",
    "M3": "marginal starter value replaces VORP as the value base: "
    "(msv + opp_cost) x fit x risk x survival x [feasibility]",
}


@dataclass
class SeasonStatic:
    """Everything needed to score any candidate at any point in a `season` draft, loaded once
    rather than per pick. `available_at_load` is irrelevant here -- VORP/replacement level are
    computed from the full season projection universe by design (standard value-based-drafting
    theory: replacement level represents the post-draft waiver-wire floor, which does not move
    just because one particular draft is in progress -- see the forensic audit's "ruled out"
    section for why this is not treated as a bug)."""

    season: int
    ecr_type: str
    projections: dict[str, float]
    positions: dict[str, str]
    vorp: dict[str, float]
    replacement_levels: dict[str, float]
    scarcity_raw: dict[str, float]
    scarcity_norm: dict[str, float]
    market_rank: dict[str, tuple[str, float]]  # player_id -> (position, ecr_rank)
    confidence: dict[str, float]
    ecr_dispersion: dict[str, tuple[float, float]]  # player_id -> (ecr_best, ecr_worst)


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return dict.fromkeys(values, 0.5)
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def load_season_static(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    ecr_type: str | None = None,
) -> SeasonStatic:
    # D56: the board has to match the league format the experiment is run against.
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type
    projections, positions = load_season_projections(con, season)
    vorp = marginal_value_over_replacement(league, projections, positions)
    levels = replacement_level(league, projections, positions)
    scarcity_raw = positional_scarcity(league, projections, positions)
    scarcity_norm = _normalize(scarcity_raw)
    market_rank = _preseason_overall_market(con, ecr_type, season)

    conf_rows = con.execute(
        "SELECT player_id, confidence FROM uncertainty_predictions "
        "WHERE season = ? AND model_version = ? AND confidence IS NOT NULL",
        [season, UNCERTAINTY_MODEL_VERSION],
    ).fetchall()
    confidence = dict(conf_rows)

    dispersion_rows = con.execute(
        """
        SELECT player_id, ecr_best, ecr_worst FROM (
            SELECT player_id, ecr_best, ecr_worst,
                   row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot
            WHERE ecr_type = ? AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)
              AND ecr_best IS NOT NULL AND ecr_worst IS NOT NULL
        ) WHERE rn = 1
        """,
        [ecr_type, season],
    ).fetchall()
    ecr_dispersion = {pid: (best, worst) for pid, best, worst in dispersion_rows}

    return SeasonStatic(
        season=season,
        ecr_type=ecr_type,
        projections=projections,
        positions=positions,
        vorp=vorp,
        replacement_levels=levels,
        scarcity_raw=scarcity_raw,
        scarcity_norm=scarcity_norm,
        market_rank=market_rank,
        confidence=confidence,
        ecr_dispersion=ecr_dispersion,
    )


def _survival_probability(
    static: SeasonStatic, player_id: str, next_pick_overall: int | None
) -> float | None:
    """Identical formula to league/draft.py::next_pick_survival_probability, evaluated against
    the pre-loaded dispersion dict instead of a fresh query."""
    if next_pick_overall is None:
        return None
    disp = static.ecr_dispersion.get(player_id)
    if disp is None:
        return None
    best, worst = disp
    if worst <= best:
        return 0.0 if next_pick_overall >= best else 1.0
    if next_pick_overall <= best:
        return 1.0
    if next_pick_overall >= worst:
        return 0.0
    return 1.0 - (next_pick_overall - best) / (worst - best)


def _feasibility_cap(league: LeagueContext, position: str) -> int:
    """A league-config-derived (not hardcoded) ceiling on how many players at one position a
    real roster can use: starting slots at that position, plus an even share of the total
    bench across every position that has a dedicated starting slot. Unlike
    `roster_need`'s existing `depth_target = slots + 2` (a constant, verified in the forensic
    audit to be unrelated to the league's actual configured bench size), this is derived from
    `league.bench_size` and the real number of distinct dedicated positions."""
    dedicated = league.dedicated_slots()
    slots = dedicated.get(position, 0)
    n_positions = max(len(dedicated), 1)
    bench_share = league.bench_size / n_positions
    return slots + max(1, math.ceil(bench_share))


@dataclass
class CandidateScore:
    player_id: str
    position: str
    projection: float
    vorp: float
    replacement_level: float
    scarcity_raw: float
    scarcity_norm: float
    roster_need: float
    fit_multiplier: float
    confidence: float | None
    survival_probability: float | None
    future_scarcity_multiplier: float | None
    feasibility_multiplier: float | None
    opportunity_cost_pts: float | None
    opponent_depletion_multiplier: float | None
    score: float
    marginal_starter_value: float | None = None
    reasons: list[str] = field(default_factory=list)


def _future_position_pool_after_market_consensus(
    static: SeasonStatic, available: set[str], position: str, n_opponent_picks: int
) -> list[str]:
    """Literal agent-based simulation (tier G): replay `n_opponent_picks` real
    market-consensus picks forward (the actual, known strategy governing every one of this
    simulation's 9 opponent slots) and return the players still available at `position`
    afterward. This is more expensive than an analytical approximation but is a direct replay
    of the real opponent model already validated in evaluation/draft_simulation.py, not a new
    behavioral assumption.

    Delegates the replay itself to `league/opportunity_cost.py::replay_opponent_picks` (the
    canonical implementation now also used by the production draft engine, D55) so the two
    cannot drift. The `, p` secondary sort key is a determinism fix (D55): the original had
    none, and real VORP/projection ties exist in production data (2021: 8 tied WR groups
    covering 17 players, 5 TE groups / 13 players), so `future_pool[0]` could differ between
    process runs under hash randomization -- the same bug class D54 fixed in
    `draft_simulation.py`."""
    remaining = replay_opponent_picks(available, static.market_rank, n_opponent_picks)
    return sorted(
        (p for p in remaining if static.positions.get(p) == position),
        key=lambda p: (-static.projections.get(p, float("-inf")), p),
    )


def _opportunity_cost_for(
    static: SeasonStatic,
    position: str,
    available: set[str] | None,
    current_pick_overall: int | None,
    next_pick_overall: int | None,
    opportunity_costs: dict[str, float] | None,
) -> float:
    """Prefer the per-pick precomputed map (see `_pick_by_tier`); fall back to computing this
    one position on demand so `score_candidate` stays usable standalone in tests."""
    if opportunity_costs is not None:
        return opportunity_costs.get(position, 0.0)
    return positional_opportunity_cost(
        available or set(),
        static.positions,
        static.vorp,
        static.market_rank,
        picks_until_next_turn(current_pick_overall, next_pick_overall),
        [position],
    )[position]


def score_candidate(
    static: SeasonStatic,
    player_id: str,
    league: LeagueContext,
    roster_positions: list[str],
    tier: Tier,
    *,
    available: set[str] | None = None,
    current_pick_overall: int | None = None,
    next_pick_overall: int | None = None,
    opportunity_costs: dict[str, float] | None = None,
    roster_player_ids: list[str] | None = None,
    base_lineup_points: float | None = None,
) -> CandidateScore | None:
    position = static.positions.get(player_id)
    if position is None or player_id not in static.vorp:
        return None

    projection = static.projections[player_id]
    vorp = static.vorp[player_id]
    level = static.replacement_levels.get(position, 0.0)
    scarcity_raw = static.scarcity_raw.get(position, 0.0)
    scarcity_norm = static.scarcity_norm.get(position, 0.5)
    needs = roster_need(league, roster_positions)
    need_score = needs.get(position, 0.0)
    fit_mult = roster_fit_multiplier(need_score)
    confidence = static.confidence.get(player_id)
    survival = _survival_probability(static, player_id, next_pick_overall)

    reasons = [f"tier {tier}: {TIER_DESCRIPTIONS[tier]}"]
    future_mult = None
    feasibility_mult = None
    opp_cost = None
    opponent_mult = None

    if tier in M_TIERS:
        # Every M-tier shares production's risk/survival/feasibility terms and the D55
        # opportunity-cost replay; only the value term and the roster multiplier vary, so a
        # difference between tiers is attributable to marginal starter value and nothing else.
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        opp_cost = _opportunity_cost_for(
            static,
            position,
            available,
            current_pick_overall,
            next_pick_overall,
            opportunity_costs,
        )
        msv = marginal_starter_value(
            league,
            roster_player_ids or [],
            player_id,
            static.projections,
            static.positions,
            base_points=base_lineup_points,
        )

        if tier == "M0":
            score = (vorp + opp_cost) * fit_mult * risk_mult * survival_mult
        elif tier == "M1":
            score = (vorp + opp_cost + msv) * fit_mult * risk_mult * survival_mult
        elif tier == "M2":
            msv_mult = marginal_starter_multiplier(msv, projection)
            score = (vorp + opp_cost) * msv_mult * risk_mult * survival_mult
            reasons.append(f"msv_mult={msv_mult:.2f} (marginal starter value {msv:+.1f})")
        else:  # M3
            score = (msv + opp_cost) * fit_mult * risk_mult * survival_mult

        cap = _feasibility_cap(league, position)
        have = sum(1 for p in roster_positions if p == position)
        if have >= cap:
            feasibility_mult = 0.1
            score *= feasibility_mult
            reasons.append(f"feasibility_mult=0.10 (already have {have} {position}, cap {cap})")

        reasons.append(f"marginal_starter_value={msv:+.1f} pts")
        if opp_cost:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost,
            opponent_depletion_multiplier=None,
            marginal_starter_value=msv,
            score=score,
            reasons=reasons,
        )

    if tier in P_TIERS:
        # Production's real scoring terms, reproduced against pre-loaded data (identical
        # formulas to league/draft.py, just without the per-candidate DB round-trips).
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        base_production = vorp * fit_mult * risk_mult * survival_mult

        opp_cost = 0.0
        if tier in ("P1", "P1b", "P1c", "P3"):
            opp_cost = _opportunity_cost_for(
                static,
                position,
                available,
                current_pick_overall,
                next_pick_overall,
                opportunity_costs,
            )

        if tier == "P0":
            score = base_production
        elif tier == "P1":
            score = base_production + opp_cost
        elif tier == "P1b":
            score = base_production + opp_cost * risk_mult
        else:  # P1c and P3 share the integrated form
            score = (vorp + opp_cost) * fit_mult * risk_mult * survival_mult

        if tier in ("P2", "P3"):
            cap = _feasibility_cap(league, position)
            have = sum(1 for p in roster_positions if p == position)
            if have >= cap:
                feasibility_mult = 0.1
                score *= feasibility_mult
                reasons.append(f"feasibility_mult=0.10 (already have {have} {position}, cap {cap})")

        opp_cost_pts = opp_cost if tier in ("P1", "P1b", "P1c", "P3") else None
        if opp_cost_pts is not None:
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
        return CandidateScore(
            player_id=player_id,
            position=position,
            projection=projection,
            vorp=vorp,
            replacement_level=level,
            scarcity_raw=scarcity_raw,
            scarcity_norm=scarcity_norm,
            roster_need=need_score,
            fit_multiplier=fit_mult,
            confidence=confidence,
            survival_probability=survival,
            future_scarcity_multiplier=None,
            feasibility_multiplier=feasibility_mult,
            opportunity_cost_pts=opp_cost_pts,
            opponent_depletion_multiplier=None,
            score=score,
            reasons=reasons,
        )

    if tier == "A":
        score = projection
    elif tier == "B":
        score = vorp * fit_mult
    elif tier in ("C", "D", "E", "F", "G"):
        scarcity_mult = 0.7 + 0.6 * scarcity_norm
        score = vorp * fit_mult * scarcity_mult
        reasons.append(f"scarcity_mult={scarcity_mult:.2f} (position scarcity {scarcity_raw:+.1f})")

        if tier in ("D", "E", "F", "G"):
            n_opponent_picks = (
                max(0, next_pick_overall - current_pick_overall - 1)
                if next_pick_overall is not None and current_pick_overall is not None
                else 0
            )
            if tier in ("D", "E", "F"):
                # Analytical approximation: expected fraction of this position's currently
                # -available depth that survives to my next pick, aggregated from the same
                # per-player Uniform(ecr_best, ecr_worst) model next_pick_survival_probability
                # already uses for one player at a time.
                pos_players = [p for p in (available or ()) if static.positions.get(p) == position]
                survivals = [
                    s
                    for p in pos_players
                    if (s := _survival_probability(static, p, next_pick_overall)) is not None
                ]
                expected_survival_rate = sum(survivals) / len(survivals) if survivals else 1.0
                # Less of a scarce position expected to survive -> larger boost, bounded the
                # same [0.7, 1.3] way as every other multiplier in this codebase for a
                # consistent scale across tiers.
                future_mult = 1.3 - 0.6 * expected_survival_rate
                score *= future_mult
                reasons.append(
                    f"future_scarcity_mult={future_mult:.2f} "
                    f"(expected {expected_survival_rate:.0%} of {position} pool survives "
                    f"{n_opponent_picks} opponent picks)"
                )
            else:  # tier G: literal opponent replay instead of the analytical approximation
                future_pool = _future_position_pool_after_market_consensus(
                    static, available or set(), position, n_opponent_picks
                )
                current_pool = sorted(
                    (p for p in (available or ()) if static.positions.get(p) == position),
                    key=lambda p: -static.projections.get(p, float("-inf")),
                )
                survives = player_id in future_pool or player_id not in current_pool
                opponent_mult = 1.0 if survives else 1.3
                score *= opponent_mult
                reasons.append(
                    f"opponent_depletion_mult={opponent_mult:.2f} "
                    f"(replayed {n_opponent_picks} real market-consensus opponent picks: "
                    f"{position} pool {len(current_pool)} -> {len(future_pool)})"
                )

        if tier in ("E", "F"):
            cap = _feasibility_cap(league, position)
            have = sum(1 for p in roster_positions if p == position)
            if have >= cap:
                feasibility_mult = 0.1
                score *= feasibility_mult
                reasons.append(
                    f"feasibility_mult=0.10 (already have {have} {position}, "
                    f"league-derived cap {cap})"
                )

        if tier == "F":
            # Explicit opportunity cost in points, not just a multiplier: value now minus the
            # expected value of the best-of-position replacement if I wait for my next pick.
            # Now delegates to the canonical `league/opportunity_cost.py` implementation (D55)
            # so the diagnostic tier and the production engine share one algorithm. That
            # implementation also clamps both sides at replacement level, which the original
            # tier-F code did not -- see the note in `_reproduce_tier_f_numbers` below.
            opp_cost = _opportunity_cost_for(
                static,
                position,
                available,
                current_pick_overall,
                next_pick_overall,
                opportunity_costs,
            )
            score += opp_cost
            reasons.append(f"opportunity_cost=+{opp_cost:.1f} pts for {position}")
    else:
        raise ValueError(
            f"score_candidate does not handle tier {tier!r} directly (use tier H's "
            "recommend_draft_pick path instead)"
        )

    return CandidateScore(
        player_id=player_id,
        position=position,
        projection=projection,
        vorp=vorp,
        replacement_level=level,
        scarcity_raw=scarcity_raw,
        scarcity_norm=scarcity_norm,
        roster_need=need_score,
        fit_multiplier=fit_mult,
        confidence=confidence,
        survival_probability=survival,
        future_scarcity_multiplier=future_mult,
        feasibility_multiplier=feasibility_mult,
        opportunity_cost_pts=opp_cost,
        opponent_depletion_multiplier=opponent_mult,
        score=score,
        reasons=reasons,
    )


def _pick_by_tier(
    static: SeasonStatic,
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    available: set[str],
    roster_positions: list[str],
    tier: Tier,
    current_pick_overall: int | None,
    next_pick_overall: int | None,
    roster_player_ids: list[str] | None = None,
) -> tuple[str, list[CandidateScore]]:
    """Returns (chosen_player_id, every scored candidate sorted best-first) -- the ranked list
    is what a JSON trace needs to show runner-up reasoning, not just the winner."""
    if tier == "H":
        needs = roster_need(league, roster_positions)
        rec = recommend_draft_pick(
            con,
            league,
            season,
            roster_positions,
            available,
            next_pick_overall=next_pick_overall,
            top_n=20,
            current_pick_overall=current_pick_overall,
            # D60: real production now uses marginal starter value when it knows the
            # roster's actual players; tier H exists to mirror real production exactly, so
            # it must pass the same thing the official benchmark does.
            roster_player_ids=roster_player_ids,
        )
        scored = [
            CandidateScore(
                player_id=c.player_id,
                position=c.position,
                projection=static.projections.get(c.player_id, 0.0),
                vorp=c.vorp,
                replacement_level=static.replacement_levels.get(c.position, 0.0),
                scarcity_raw=static.scarcity_raw.get(c.position, 0.0),
                scarcity_norm=static.scarcity_norm.get(c.position, 0.5),
                roster_need=needs.get(c.position, 0.0),
                fit_multiplier=roster_fit_multiplier(needs.get(c.position, 0.0)),
                confidence=c.confidence,
                survival_probability=c.survival_probability,
                future_scarcity_multiplier=None,
                feasibility_multiplier=None,
                opportunity_cost_pts=None,
                opponent_depletion_multiplier=None,
                score=c.score,
                reasons=list(c.reasons),
            )
            for c in rec.candidates
        ]
        return rec.recommendation, scored

    # Opportunity cost is a property of the POSITION, not the candidate, so the opponent replay
    # is computed once per pick here and reused for every candidate -- not once per candidate
    # (which is what the original tier-F code did, and why it cost ~5.5s/draft). Correctness
    # note: this is not merely an optimization, it is the mechanism's actual shape; see
    # league/opportunity_cost.py's module docstring.
    # Marginal starter value compares each candidate against the CURRENT lineup, which does
    # not vary across candidates at one pick -- so it is computed once here rather than once
    # per candidate, the same optimization the opportunity-cost replay already uses below.
    base_lineup_points = None
    if tier in M_TIERS:
        base_lineup_points = best_lineup_points(
            league, roster_player_ids or [], static.projections, static.positions
        )

    opportunity_costs: dict[str, float] | None = None
    if tier in ("P1", "P1b", "P1c", "P3", "F", *M_TIERS):
        candidate_positions = {
            pos for p in available if (pos := static.positions.get(p)) is not None
        }
        opportunity_costs = positional_opportunity_cost(
            available,
            static.positions,
            static.vorp,
            static.market_rank,
            picks_until_next_turn(current_pick_overall, next_pick_overall),
            candidate_positions,
        )

    scored = []
    for player_id in available:
        s = score_candidate(
            static,
            player_id,
            league,
            roster_positions,
            tier,
            available=available,
            current_pick_overall=current_pick_overall,
            next_pick_overall=next_pick_overall,
            opportunity_costs=opportunity_costs,
            roster_player_ids=roster_player_ids,
            base_lineup_points=base_lineup_points,
        )
        if s is not None:
            scored.append(s)
    if not scored:
        raise RuntimeError(f"no evaluable candidates for tier {tier} at season {season}")
    scored.sort(key=lambda s: (-s.score, s.player_id))
    return scored[0].player_id, scored


@dataclass
class ForensicDraftResult:
    season: int
    tier: Tier
    draft_slot: int
    drafted_player_ids: list[str] = field(default_factory=list)
    drafted_positions: list[str] = field(default_factory=list)
    total_roster_points: float = 0.0
    starter_points: float = 0.0


def simulate_forensic_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    tier: Tier,
    draft_slot: int,
    static: SeasonStatic,
    *,
    trace: list[dict] | None = None,
) -> ForensicDraftResult:
    """Same snake-draft loop, fixed 9-slot real-market-consensus opponent field, and outcome
    scoring as evaluation/draft_simulation.py::simulate_draft -- the only thing that varies is
    how the team-in-question's own pick is scored (`tier`). If `trace` is given, every pick's
    full candidate ranking is appended to it (see `trace_draft` below for the JSON shape)."""
    from alpha_squad.evaluation.draft_simulation import _actual_points_for
    from alpha_squad.league.replacement import compute_league_starters

    available = set(static.projections)
    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    drafted: list[str] = []
    my_roster_positions: list[str] = []

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        for slot in order:
            if not available:
                break
            if slot == draft_slot:
                current_pick = _snake_overall_pick(round_no, slot, league.teams)
                next_pick = _next_pick_overall(round_no, slot, league.teams, total_rounds)
                pick, scored = _pick_by_tier(
                    static,
                    con,
                    league,
                    season,
                    available,
                    my_roster_positions,
                    tier,
                    current_pick,
                    next_pick,
                    roster_player_ids=drafted,
                )
                if trace is not None:
                    top = scored[0]
                    runner_up = scored[1] if len(scored) > 1 else None
                    trace.append(
                        {
                            "season": season,
                            "tier": tier,
                            "draft_slot": draft_slot,
                            "round": round_no,
                            "overall_pick": current_pick,
                            "roster_before_pick": list(my_roster_positions),
                            "n_candidates": len(scored),
                            "selected": _candidate_to_dict(top),
                            "runner_up": _candidate_to_dict(runner_up) if runner_up else None,
                            "score_gap_to_runner_up": (
                                top.score - runner_up.score if runner_up else None
                            ),
                            "top_5_candidates": [_candidate_to_dict(c) for c in scored[:5]],
                        }
                    )
                drafted.append(pick)
                my_roster_positions.append(static.positions.get(pick, "UNKNOWN"))
            else:
                pick = _market_consensus_pick(available, static.market_rank)
            available.discard(pick)

    actual_points = _actual_points_for(con, season, drafted)
    total_points = sum(actual_points.values())
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        actual_points,
        {p: static.positions.get(p, "UNKNOWN") for p in drafted},
    )
    starter_points = sum(actual_points.get(p, 0.0) for p in starters["starters"])

    return ForensicDraftResult(
        season=season,
        tier=tier,
        draft_slot=draft_slot,
        drafted_player_ids=drafted,
        drafted_positions=my_roster_positions,
        total_roster_points=total_points,
        starter_points=starter_points,
    )


def _candidate_to_dict(c: CandidateScore) -> dict:
    return {
        "player_id": c.player_id,
        "position": c.position,
        "projection": round(c.projection, 2),
        "vorp": round(c.vorp, 2),
        "replacement_level": round(c.replacement_level, 2),
        "scarcity_raw": round(c.scarcity_raw, 2),
        "scarcity_norm": round(c.scarcity_norm, 3),
        "roster_need": round(c.roster_need, 3),
        "fit_multiplier": round(c.fit_multiplier, 3),
        "confidence": round(c.confidence, 3) if c.confidence is not None else None,
        "survival_probability": (
            round(c.survival_probability, 3) if c.survival_probability is not None else None
        ),
        "future_scarcity_multiplier": (
            round(c.future_scarcity_multiplier, 3)
            if c.future_scarcity_multiplier is not None
            else None
        ),
        "feasibility_multiplier": c.feasibility_multiplier,
        "marginal_starter_value": (
            round(c.marginal_starter_value, 2) if c.marginal_starter_value is not None else None
        ),
        "opportunity_cost_pts": (
            round(c.opportunity_cost_pts, 2) if c.opportunity_cost_pts is not None else None
        ),
        "opponent_depletion_multiplier": c.opponent_depletion_multiplier,
        "score": round(c.score, 3),
        "reasons": c.reasons,
    }


def homogeneous_league_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    strategy: Literal["market_consensus", "raw_value", "vorp"],
    static: SeasonStatic,
) -> dict[int, list[str]]:
    """Baseline sanity check (forensic directive section 14-15): draft ALL `league.teams`
    slots under the *same* homogeneous strategy -- not the 1-vs-9-market-consensus design used
    everywhere else in this codebase -- so a strategy's own roster realism can be inspected
    with no fixed-opponent confound at all. Returns {draft_slot: drafted_player_ids}.

    `market_consensus` here is a convenience re-derivation for a fully-homogeneous league;
    note this is mathematically identical to the ALREADY-COMPUTED market_consensus rows in
    draft_simulation_results (docs/DECISIONS.md D54), since every slot in that harness's
    market_consensus trials also faces 9 real market_consensus opponents -- see
    docs/DRAFT_CONTROLLED_EXPERIMENTS.md for why that existing data already answers "ADP/ECR
    vs itself" without a new run being required."""
    available = set(static.projections)
    total_rounds = int(league.roster.get("roster_size", 0))
    rosters: dict[int, list[str]] = {slot: [] for slot in range(1, league.teams + 1)}

    def pick_for(slot_available: set[str]) -> str:
        if strategy == "market_consensus":
            return _market_consensus_pick(slot_available, static.market_rank)
        if strategy == "raw_value":
            return max(slot_available, key=lambda p: (static.projections.get(p, float("-inf")), p))
        return max(slot_available, key=lambda p: (static.vorp.get(p, float("-inf")), p))  # "vorp"

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        for slot in order:
            if not available:
                break
            pick = pick_for(available)
            rosters[slot].append(pick)
            available.discard(pick)

    return rosters


def roster_feasibility_metrics(
    league: LeagueContext, drafted_positions: list[str]
) -> dict[str, object]:
    """Section 9 of the forensic directive: metrics for roster CONSTRUCTION, kept explicitly
    separate from fantasy VALUE (total/starter points, computed elsewhere). No arbitrary
    "looks normal" thresholds -- every bound here is derived from the league's own structural
    settings (dedicated_slots, bench_size), not picked to make a particular result look good
    or bad."""
    dedicated = league.dedicated_slots()
    counts: dict[str, int] = {}
    for pos in drafted_positions:
        counts[pos] = counts.get(pos, 0) + 1

    zero_drafted = [
        pos for pos, slots in dedicated.items() if slots > 0 and counts.get(pos, 0) == 0
    ]
    over_cap = {
        pos: counts.get(pos, 0)
        for pos in dedicated
        if counts.get(pos, 0) > _feasibility_cap(league, pos)
    }
    n_distinct = len([p for p in counts if counts[p] > 0])
    total_drafted = len(drafted_positions)

    return {
        "position_counts": counts,
        "starting_requirements": dedicated,
        "zero_drafted_starting_positions": zero_drafted,
        "positions_over_feasibility_cap": over_cap,
        "max_single_position_share": (
            max(counts.values()) / total_drafted if total_drafted else 0.0
        ),
        "n_distinct_positions_drafted": n_distinct,
        "concentration_index": (  # Herfindahl-style: sum of squared position shares, 1/n_pos
            # (even split) to 1.0 (one position only) -- a single scalar realism check.
            sum((c / total_drafted) ** 2 for c in counts.values()) if total_drafted else 0.0
        ),
    }


def run_tier_ablation(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    seasons: list[int],
    tiers: tuple[Tier, ...],
    slots: list[int] | None = None,
) -> list[dict]:
    """One row per (season, tier, slot): the full ceteris-paribus grid.

    `load_season_static` is called once per season and shared across every tier and slot, so
    the only thing that varies within a season is the scoring mechanism -- which is what
    makes a difference between tiers attributable to the mechanism and nothing else."""
    slots = slots if slots is not None else list(range(1, league.teams + 1))
    rows: list[dict] = []
    for season in seasons:
        static = load_season_static(con, league, season)
        for tier in tiers:
            for slot in slots:
                result = simulate_forensic_draft(con, league, season, tier, slot, static)
                feasibility = roster_feasibility_metrics(league, result.drafted_positions)
                rows.append(
                    {
                        "season": season,
                        "tier": tier,
                        "draft_slot": slot,
                        "starter_points": result.starter_points,
                        "total_roster_points": result.total_roster_points,
                        "drafted_positions": list(result.drafted_positions),
                        "position_counts": feasibility["position_counts"],
                        "zero_drafted_starting_positions": feasibility[
                            "zero_drafted_starting_positions"
                        ],
                        "positions_over_feasibility_cap": feasibility[
                            "positions_over_feasibility_cap"
                        ],
                        "max_single_position_share": feasibility["max_single_position_share"],
                    }
                )
    return rows


def summarize_tier_ablation(rows: list[dict], league: LeagueContext) -> list[dict]:
    """Per-tier aggregates, including the gate metrics the pre-registered decision rule
    names. `zero_rate_by_position` is what Gate 1 is judged on."""
    dedicated = league.dedicated_slots()
    by_tier: dict[str, list[dict]] = {}
    for row in rows:
        by_tier.setdefault(row["tier"], []).append(row)

    summary = []
    for tier, tier_rows in by_tier.items():
        n = len(tier_rows)
        starters = [r["starter_points"] for r in tier_rows]
        zero_rate = {
            pos: sum(1 for r in tier_rows if pos in r["zero_drafted_starting_positions"])
            for pos in dedicated
        }
        summary.append(
            {
                "tier": tier,
                "n": n,
                "mean_starter_points": sum(starters) / n if n else 0.0,
                "mean_total_roster_points": (
                    sum(r["total_roster_points"] for r in tier_rows) / n if n else 0.0
                ),
                "zero_rate_by_position": zero_rate,
                "n_infeasible_rosters": sum(
                    1 for r in tier_rows if r["zero_drafted_starting_positions"]
                ),
                "mean_max_position_share": (
                    sum(r["max_single_position_share"] for r in tier_rows) / n if n else 0.0
                ),
            }
        )
    summary.sort(key=lambda r: -r["mean_starter_points"])
    return summary
