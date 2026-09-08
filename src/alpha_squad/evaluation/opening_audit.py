"""Opening-draft audit: what does the REAL production engine recommend at a given draft slot's
first few picks, why, and does that answer survive a change of opponent behaviour?

This module is a *harness*, not a second engine. Every recommendation it reports comes from
`league/draft.py::recommend_draft_pick` -- the same function the CLI, `POST /league/{id}/draft`,
the web Draft view and the Claude review endpoint all call. What this module adds is:

1. **A draft loop with pluggable opponents.** `evaluation/draft_simulation.py::simulate_draft`
   only offers the two benchmark opponent fields (`market_consensus` and the fair
   `market_consensus_roster_aware`). Asking "is the opening robust to who else is in the room"
   needs opponents that draft differently on purpose -- receiver-heavy, back-heavy, noisy.
   Those belong here, in an investigation module, rather than being added to the benchmark's
   own strategy list where they would look like validated opponent models.

2. **A score decomposition that is verified, not asserted.** `DraftCandidate` carries the
   finished score, the static VORP, confidence, survival and marginal starter value, but not
   the draft-aware replacement level, the opportunity cost or the multipliers. Those are
   recomputed here from the same production functions and then **reassembled and compared to
   the production score**. `decompose_candidate` raises if the reassembly disagrees by more
   than `REASSEMBLY_TOLERANCE`, so a decomposition can never silently describe a formula the
   engine is not running. D81 recorded a real instance of this class of error: a projection
   override that never reached the engine, caught only because the reassembly failed.

Nothing here is imported by `src/alpha_squad/league/`, `models/` or the API. It is diagnostic
infrastructure, in the same category as `evaluation/draft_forensics.py`.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import DraftCandidate, recommend_draft_pick
from alpha_squad.league.opportunity_cost import (
    best_by_market_rank,
    load_market_ranks,
    picks_until_next_turn,
    positional_opportunity_cost,
    roster_aware_market_pick,
)
from alpha_squad.league.replacement import (
    demand_boundary_replacement,
    load_season_projections,
    marginal_value_over_replacement,
    market_draft_demand,
)
from alpha_squad.league.roster import (
    OVER_CAP_VALUE_MULTIPLIER,
    positional_feasibility_cap,
    roster_fit_multiplier,
    roster_need,
)
from alpha_squad.market.series import resolve_market_series

# The production score is a product of floats computed in a different order here than in
# `recommend_draft_pick`, so exact equality is not available; this is a floating-point
# reassembly tolerance, not a modelling allowance. Scores are O(100-1000), so 1e-6 absolute is
# roughly 1e-9 relative -- far tighter than any real formula difference could hide under.
REASSEMBLY_TOLERANCE = 1e-6


@dataclass
class ScoreDecomposition:
    """Every term of the production score for one candidate, plus the reassembled product.

    `value_base = msv + DRAFT_VORP_WEIGHT * da_vorp` when the roster's player ids are known
    (always, here), else `da_vorp` alone. `reassembled` is checked against the engine's own
    `score` by `decompose_candidate`."""

    player_id: str
    position: str
    projection: float
    msv: float | None
    da_vorp: float
    static_vorp: float
    replacement_level: float | None
    opportunity_cost: float
    fit_multiplier: float
    risk_multiplier: float
    survival_probability: float | None
    survival_multiplier: float
    cap_multiplier: float
    value_base: float
    score: float
    reassembled: float


@dataclass
class PickAudit:
    """One pick made by the team under audit, with the full candidate slate that produced it."""

    overall_pick: int
    round_no: int
    next_pick_overall: int | None
    picks_until_next_turn: int
    roster_before: list[str]
    roster_positions_before: list[str]
    available_pool_size: int
    # The exact board this pick faced. Retained (rather than only its size) so a counterfactual
    # can re-score the identical state without replaying the draft a second time and risking a
    # different one -- see `evaluation/decision_counterfactuals.py`.
    available_before: set[str]
    recommendation: str
    recommended_position: str
    score_gap_to_runner_up: float | None
    candidates: list[ScoreDecomposition]
    best_by_position: dict[str, ScoreDecomposition] = field(default_factory=dict)


@dataclass
class OpeningAuditResult:
    season: int
    draft_slot: int
    world: str
    ecr_type: str
    league_id: str
    audited_picks: list[PickAudit]
    full_roster_positions: list[str]
    full_roster_player_ids: list[str]


# --------------------------------------------------------------------------------------------
# Opponent worlds
# --------------------------------------------------------------------------------------------
# An opponent world is a callable with the signature every strategy below shares. It receives
# the live board and that opponent's own roster, and returns the player it takes. `rng` is
# supplied per draft (seeded) so a stochastic world is reproducible.

OpponentPick = Callable[..., str]


def _default_world(
    available: set[str],
    market_rank: dict[str, tuple[str, float]],
    positions: dict[str, str],
    league: LeagueContext,
    roster_positions: list[str],
    picks_remaining: int,
    rng: random.Random,
) -> str:
    """The production benchmark's fair opponent (`market_consensus_roster_aware`, D61). This is
    the field every published draft number in this project was measured against."""
    return roster_aware_market_pick(
        available, market_rank, positions, league, roster_positions, picks_remaining
    )


def _pure_ecr_world(
    available: set[str],
    market_rank: dict[str, tuple[str, float]],
    positions: dict[str, str],
    league: LeagueContext,
    roster_positions: list[str],
    picks_remaining: int,
    rng: random.Random,
) -> str:
    """Straight best-available by consensus rank, with no endgame roster legality. Kept as a
    distinct world because it is the opponent every pre-D61 number was measured against."""
    return best_by_market_rank(available, market_rank)


def _position_biased_world(bias_position: str, take_through_rank: int) -> OpponentPick:
    """An opponent that prefers `bias_position` whenever a member of it is ranked inside
    `take_through_rank` places of the overall best available, and otherwise drafts consensus.

    The bias is expressed as a *rank tolerance*, not as a fixed quota, so the opponent still
    behaves like a drafter rather than a script: it will not reach 60 places for a running back,
    but it will happily take one 12 places early. Roster legality (the endgame mandatory-slot
    reservation) is retained so these worlds still field legal lineups and stay comparable to
    the default world."""

    def _pick(
        available: set[str],
        market_rank: dict[str, tuple[str, float]],
        positions: dict[str, str],
        league: LeagueContext,
        roster_positions: list[str],
        picks_remaining: int,
        rng: random.Random,
    ) -> str:
        consensus = roster_aware_market_pick(
            available, market_rank, positions, league, roster_positions, picks_remaining
        )
        # Never override the endgame reservation: if the consensus pick is already forced by
        # roster legality, biasing away from it would field an illegal lineup.
        deficits = sum(n for n in _unfilled(league, roster_positions).values() if n > 0)
        if deficits > 0 and picks_remaining <= deficits:
            return consensus
        best_rank = market_rank[consensus][1] if consensus in market_rank else float("inf")
        biased = [
            p
            for p in available
            if positions.get(p) == bias_position
            and p in market_rank
            and market_rank[p][1] <= best_rank + take_through_rank
        ]
        if not biased:
            return consensus
        return best_by_market_rank(set(biased), market_rank)

    return _pick


def _unfilled(league: LeagueContext, roster_positions: list[str]) -> dict[str, int]:
    from alpha_squad.league.roster import unfilled_dedicated_slots

    return unfilled_dedicated_slots(league, roster_positions)


def _stochastic_world(sigma: float) -> OpponentPick:
    """Consensus opponents who reach and slide. Each pick draws a perturbed rank
    `rank + Normal(0, sigma)` for the top of the board and takes the best perturbed rank.

    Only the top 40 available players are perturbed, for two reasons: it is where real reaches
    and slides happen, and perturbing the whole 600-player board would let a rank-500 player
    occasionally go in round 1, which is not a plausible opponent, just noise."""

    def _pick(
        available: set[str],
        market_rank: dict[str, tuple[str, float]],
        positions: dict[str, str],
        league: LeagueContext,
        roster_positions: list[str],
        picks_remaining: int,
        rng: random.Random,
    ) -> str:
        deficits = sum(n for n in _unfilled(league, roster_positions).values() if n > 0)
        if deficits > 0 and picks_remaining <= deficits:
            return roster_aware_market_pick(
                available, market_rank, positions, league, roster_positions, picks_remaining
            )
        ranked = sorted(
            (p for p in available if p in market_rank),
            key=lambda p: (market_rank[p][1], p),
        )[:40]
        if not ranked:
            return best_by_market_rank(available, market_rank)
        return min(ranked, key=lambda p: market_rank[p][1] + rng.gauss(0.0, sigma))

    return _pick


WORLDS: dict[str, OpponentPick] = {
    "default": _default_world,
    "pure_ecr": _pure_ecr_world,
    "wr_heavy": _position_biased_world("WR", 12),
    "rb_heavy": _position_biased_world("RB", 12),
    "te_heavy": _position_biased_world("TE", 12),
    "qb_heavy": _position_biased_world("QB", 12),
    "stochastic_s4": _stochastic_world(4.0),
    "stochastic_s8": _stochastic_world(8.0),
}


# --------------------------------------------------------------------------------------------
# Decomposition
# --------------------------------------------------------------------------------------------


@dataclass
class _BoardState:
    """The per-call quantities `recommend_draft_pick` derives internally, recomputed here from
    the same production functions so a decomposition can be checked against the real score."""

    projections: dict[str, float]
    positions: dict[str, str]
    static_vorp: dict[str, float]
    market_ranks: dict[str, tuple[str, float]]


def load_board_state(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    ecr_type: str,
) -> _BoardState:
    projections, positions = load_season_projections(con, season)
    return _BoardState(
        projections=projections,
        positions=positions,
        static_vorp=marginal_value_over_replacement(league, projections, positions),
        market_ranks=load_market_ranks(con, ecr_type, season),
    )


def replacement_levels_at(
    league: LeagueContext,
    board: _BoardState,
    available: set[str],
) -> dict[str, float]:
    """The draft-aware replacement level the engine would use for this exact board state,
    including the same `pool_is_a_board` guard `recommend_draft_pick` applies. Returns {} when
    the guard fails, which is what the engine reads as "fall back to static VORP"."""
    max_drafted = league.teams * int(league.roster.get("roster_size", 0))
    if max_drafted <= 0 or len(board.projections) - len(available) > max_drafted:
        return {}
    return demand_boundary_replacement(
        league,
        set(available),
        board.projections,
        board.positions,
        market_draft_demand(league, board.market_ranks, board.projections, board.positions),
    )


def decompose_candidate(
    league: LeagueContext,
    board: _BoardState,
    candidate: DraftCandidate,
    *,
    roster_positions: list[str],
    da_levels: dict[str, float],
    opportunity_costs: dict[str, float],
) -> ScoreDecomposition:
    """Recompute every term of the production score for `candidate` and verify the product
    reproduces the engine's own `candidate.score`.

    Raises `AssertionError` if it does not. That is deliberate: a decomposition that silently
    disagrees with the engine is worse than no decomposition, because it reads as evidence."""
    pos = candidate.position
    projection = board.projections[candidate.player_id]
    da_vorp = (
        projection - da_levels[pos] if pos in da_levels else board.static_vorp[candidate.player_id]
    )
    needs = roster_need(league, roster_positions)
    fit = roster_fit_multiplier(needs.get(pos, 0.0))
    risk = candidate.confidence if candidate.confidence is not None else 0.7
    survival_mult = (
        1.0
        if candidate.survival_probability is None
        else (1.0 + 0.3 * (1.0 - candidate.survival_probability))
    )
    have = sum(1 for p in roster_positions if p == pos)
    cap = positional_feasibility_cap(league, pos)
    cap_mult = OVER_CAP_VALUE_MULTIPLIER if (cap > 0 and have >= cap) else 1.0

    from alpha_squad.league.draft import DRAFT_VORP_WEIGHT

    if candidate.marginal_starter_value is not None:
        value_base = candidate.marginal_starter_value + DRAFT_VORP_WEIGHT * da_vorp
    else:
        value_base = da_vorp
    oc = opportunity_costs.get(pos, 0.0)
    reassembled = (value_base + oc) * fit * risk * survival_mult * cap_mult

    if abs(reassembled - candidate.score) > REASSEMBLY_TOLERANCE:
        raise AssertionError(
            f"score decomposition does not reproduce the production score for "
            f"{candidate.player_id} ({pos}): reassembled {reassembled!r} vs engine "
            f"{candidate.score!r}. The decomposition describes a formula the engine is not "
            f"running -- fix the decomposition rather than reporting it."
        )

    return ScoreDecomposition(
        player_id=candidate.player_id,
        position=pos,
        projection=projection,
        msv=candidate.marginal_starter_value,
        da_vorp=da_vorp,
        static_vorp=board.static_vorp[candidate.player_id],
        replacement_level=da_levels.get(pos),
        opportunity_cost=oc,
        fit_multiplier=fit,
        risk_multiplier=risk,
        survival_probability=candidate.survival_probability,
        survival_multiplier=survival_mult,
        cap_multiplier=cap_mult,
        value_base=value_base,
        score=candidate.score,
        reassembled=reassembled,
    )


# --------------------------------------------------------------------------------------------
# The audited draft
# --------------------------------------------------------------------------------------------


def snake_overall_pick(round_no: int, slot: int, teams: int) -> int:
    if round_no % 2 == 1:
        return (round_no - 1) * teams + slot
    return (round_no - 1) * teams + (teams - slot + 1)


def audit_opening(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    draft_slot: int,
    *,
    world: str = "default",
    audit_rounds: int = 3,
    seed: int = 0,
    ecr_type: str | None = None,
    top_n: int = 25,
) -> OpeningAuditResult:
    """Run one full snake draft with `draft_slot` on the real production engine and every other
    seat drafting by `world`, capturing the full decomposed candidate slate for the first
    `audit_rounds` of our own picks.

    The draft runs to completion (all `roster_size` rounds) rather than stopping after the
    audited picks, so `full_roster_positions` reports what the engine actually builds -- an
    opening cannot be judged without knowing what it leads to."""
    if world not in WORLDS:
        raise ValueError(f"unknown opponent world {world!r}; known: {sorted(WORLDS)}")
    if not (1 <= draft_slot <= league.teams):
        raise ValueError(f"draft_slot must be in [1, {league.teams}], got {draft_slot}")
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type

    board = load_board_state(con, league, season, ecr_type)
    opponent_pick = WORLDS[world]
    rng = random.Random(seed)

    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    available = set(board.projections)
    drafted: list[str] = []
    my_roster_positions: list[str] = []
    opponent_rosters: dict[int, list[str]] = {
        slot: [] for slot in range(1, league.teams + 1) if slot != draft_slot
    }
    audited: list[PickAudit] = []

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        picks_remaining = total_rounds - round_no + 1
        for slot in order:
            if not available:
                break
            if slot == draft_slot:
                current = snake_overall_pick(round_no, slot, league.teams)
                nxt = (
                    snake_overall_pick(round_no + 1, slot, league.teams)
                    if round_no < total_rounds
                    else None
                )
                want_audit = round_no <= audit_rounds
                rec = recommend_draft_pick(
                    con,
                    league,
                    season,
                    my_roster_positions,
                    available,
                    next_pick_overall=nxt,
                    ecr_type=ecr_type,
                    top_n=top_n if want_audit else 1,
                    current_pick_overall=current,
                    roster_player_ids=drafted,
                )
                pick = rec.recommendation
                if want_audit:
                    audited.append(
                        _build_audit(
                            league,
                            board,
                            rec,
                            available=available,
                            roster=list(drafted),
                            roster_positions=list(my_roster_positions),
                            overall_pick=current,
                            round_no=round_no,
                            next_pick_overall=nxt,
                        )
                    )
                drafted.append(pick)
                my_roster_positions.append(board.positions.get(pick, "UNKNOWN"))
            else:
                pick = opponent_pick(
                    available,
                    board.market_ranks,
                    board.positions,
                    league,
                    opponent_rosters[slot],
                    picks_remaining,
                    rng,
                )
                opponent_rosters[slot].append(board.positions.get(pick, "UNKNOWN"))
            available.discard(pick)

    return OpeningAuditResult(
        season=season,
        draft_slot=draft_slot,
        world=world,
        ecr_type=ecr_type,
        league_id=league.league_id,
        audited_picks=audited,
        full_roster_positions=my_roster_positions,
        full_roster_player_ids=drafted,
    )


def _build_audit(
    league: LeagueContext,
    board: _BoardState,
    rec,
    *,
    available: set[str],
    roster: list[str],
    roster_positions: list[str],
    overall_pick: int,
    round_no: int,
    next_pick_overall: int | None,
) -> PickAudit:
    da_levels = replacement_levels_at(league, board, available)
    n_opp = picks_until_next_turn(overall_pick, next_pick_overall)
    if n_opp > 0:
        candidate_positions = {
            p for pid in available if (p := board.positions.get(pid)) is not None
        }
        opportunity_costs = positional_opportunity_cost(
            set(available),
            board.positions,
            board.static_vorp,
            board.market_ranks,
            n_opp,
            candidate_positions,
        )
    else:
        opportunity_costs = {}

    decomposed = [
        decompose_candidate(
            league,
            board,
            c,
            roster_positions=roster_positions,
            da_levels=da_levels,
            opportunity_costs=opportunity_costs,
        )
        for c in rec.candidates
    ]
    best_by_position: dict[str, ScoreDecomposition] = {}
    for d in decomposed:
        if d.position not in best_by_position:
            best_by_position[d.position] = d

    return PickAudit(
        overall_pick=overall_pick,
        round_no=round_no,
        next_pick_overall=next_pick_overall,
        picks_until_next_turn=n_opp,
        roster_before=list(roster),
        roster_positions_before=list(roster_positions),
        available_pool_size=len(available),
        available_before=set(available),
        recommendation=rec.recommendation,
        recommended_position=board.positions.get(rec.recommendation, "UNKNOWN"),
        score_gap_to_runner_up=rec.trace.score_gap_to_runner_up,
        candidates=decomposed,
        best_by_position=best_by_position,
    )
