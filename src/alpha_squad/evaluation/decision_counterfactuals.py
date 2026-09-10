"""Controlled counterfactuals on the draft engine's score, one component at a time.

The question these exist to answer is *mechanistic*, not evaluative: at a given pick state,
which term of `recommend_draft_pick`'s score is responsible for the recommendation, and what
would the engine choose if that term were formed differently?

**This is a diagnostic instrument and nothing in `src/alpha_squad/league/` imports it.** Every
quantity is computed by the production functions themselves (`marginal_starter_value`,
`demand_boundary_replacement`, `positional_opportunity_cost`, `roster_fit_multiplier`, ...);
a variant changes *which* of those is called or with *what demand target*, never how any of
them works. `ScoringVariant.control()` is asserted against the real `recommend_draft_pick`
output by `assert_control_reproduces_production`, so a variant's margin can never be an
artifact of a harness that scores differently from the engine even before the change.

The vocabulary these variants explore (docs/DECISIONS.md D83's closing question):

* **Consumption demand** -- how many players at a position a full draft of this league removes
  from the board (`market_draft_demand`; sums to `roster_size`). This is what production draws
  replacement at.
* **Starter demand** -- how many players at a position actually occupy a starting lineup
  somewhere in the league, flex allocation included (`compute_league_starters`; sums to the
  lineup size). Points from a player who never starts do not enter the objective at all, so
  this is the boundary the *objective* is defined over.

The two differ by a factor that is itself position-dependent (QB 2.4x, RB 2.5x, WR 1.6x,
TE 1.9x, K/DST 1.0x on the real target-format board), which is why the choice between them is
a positional re-weighting rather than a scale change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import (
    DRAFT_VORP_WEIGHT,
    next_pick_survival_probability,
    recommend_draft_pick,
)
from alpha_squad.league.opportunity_cost import (
    load_market_ranks,
    picks_until_next_turn,
    positional_opportunity_cost,
    replay_opponent_picks,
    roster_aware_market_pick,
)
from alpha_squad.league.replacement import (
    best_lineup_points,
    compute_league_starters,
    demand_boundary_replacement,
    load_season_projections,
    marginal_starter_value,
    marginal_value_over_replacement,
    market_draft_demand,
    replacement_marginal_starter_values,
)
from alpha_squad.league.roster import (
    OVER_CAP_VALUE_MULTIPLIER,
    positional_feasibility_cap,
    roster_fit_multiplier,
    roster_need,
)
from alpha_squad.market.series import resolve_market_series

CONTROL_TOLERANCE = 1e-6

# Value-base forms. `msv_plus_vorp` is production.
VALUE_BASES = (
    "msv_plus_vorp",  # production: msv + w * daVORP
    "vorp_only",  # daVORP alone
    "msv_only",  # msv alone
    "msv_over_replacement",  # best_lineup(roster+cand) - best_lineup(roster+replacement body)
)

# Which demand target the replacement level is drawn at.
DEMAND_TARGETS = ("consumption", "starter")

# How replacement level is located at all.
#
# `demand_boundary` (production) is an END-OF-DRAFT quantity: the player sitting at the
# boundary of what the league still has to absorb at that position. Both demand targets above
# are of this kind -- they differ only in where the boundary is drawn.
#
# `next_turn` is a TIMING quantity: the best player at that position still on the board at the
# next pick of mine at which the board will actually have changed. It answers "what do I get at
# this position if I spend this pick somewhere else", which is the counterfactual the pick
# decision is actually against. It is the value-over-next-available (VONA) formulation.
#
# The distinction matters because the two can disagree by hundreds of points. On the real 2026
# board at pick #20, the end-of-draft QB boundary sits at 203.0 (QB20) while the QB actually
# available at the next changed board (#40) is 306.7 -- so an end-of-draft boundary prices the
# consensus QB1 at a surplus of +140.6 where the timing counterfactual prices him at +36.9.
REPLACEMENT_MODES = ("demand_boundary", "next_turn")


@dataclass(frozen=True)
class ScoringVariant:
    """One counterfactual. Defaults are production, so every field a variant does not set is
    guaranteed to be the shipped behaviour rather than a re-specified copy of it."""

    name: str = "control"
    value_base: str = "msv_plus_vorp"
    vorp_weight: float = DRAFT_VORP_WEIGHT
    demand_target: str = "consumption"
    replacement_mode: str = "demand_boundary"
    # Multiply the per-team demand at these positions before drawing replacement. Used to sweep
    # a single position's boundary without touching any other position (Phase 4D).
    demand_scale: dict[str, float] = field(default_factory=dict)
    # Override the per-team demand outright, per position (Phase 4D, absolute boundaries).
    demand_override: dict[str, float] = field(default_factory=dict)
    use_opportunity_cost: bool = True
    use_fit_multiplier: bool = True
    use_risk_multiplier: bool = True
    use_survival_multiplier: bool = True
    survival_coefficient: float = 0.3
    use_cap_multiplier: bool = True
    # Price opportunity cost against this many opponent picks instead of the real gap to the
    # next turn. `None` = use the real gap (production).
    opportunity_horizon: int | None = None
    # Arm T3: at a zero-gap (back-to-back) turn, price opportunity cost against the next pick
    # that actually has opponents in front of it, instead of returning all-zero costs.
    opportunity_skip_zero_turn: bool = False
    # DIAGNOSTIC ONLY, and never a shippable candidate: hold these positions off the board
    # until `diagnostic_defer_until_pick`. This is a hardcoded positional rule -- exactly the
    # kind of thing the project forbids shipping -- and it exists solely to MEASURE what the
    # engine's early kicker/defense picks cost, by comparing against an arm that cannot make
    # them. The deferral is skipped if it would leave nothing else to draft, so it can never
    # produce an illegal roster.
    diagnostic_defer_positions: tuple[str, ...] = ()
    diagnostic_defer_until_pick: int = 0

    @staticmethod
    def control() -> ScoringVariant:
        return ScoringVariant()

    def __post_init__(self) -> None:
        if self.value_base not in VALUE_BASES:
            raise ValueError(f"unknown value_base {self.value_base!r}; known: {VALUE_BASES}")
        if self.demand_target not in DEMAND_TARGETS:
            raise ValueError(
                f"unknown demand_target {self.demand_target!r}; known: {DEMAND_TARGETS}"
            )
        if self.replacement_mode not in REPLACEMENT_MODES:
            raise ValueError(
                f"unknown replacement_mode {self.replacement_mode!r}; known: {REPLACEMENT_MODES}"
            )


@dataclass
class VariantScore:
    player_id: str
    position: str
    projection: float
    value_base: float
    replacement_level: float | None
    opportunity_cost: float
    multiplier: float
    score: float


@dataclass
class PickState:
    """Everything needed to re-score one pick under any variant."""

    season: int
    ecr_type: str
    roster_player_ids: list[str]
    roster_positions: list[str]
    available: set[str]
    current_pick_overall: int
    next_pick_overall: int | None
    # The next pick of mine at which the board will actually have changed -- i.e. `next_pick_
    # overall`, except at a back-to-back snake turn, where the pick one away has zero opponent
    # picks in front of it and therefore carries no timing information at all. Only the
    # `next_turn` replacement mode reads it; production and every `demand_boundary` variant
    # ignore it entirely. `None` means there is no such pick (the draft ends first).
    next_changed_board_pick: int | None = None


def starter_demand_per_team(
    league: LeagueContext, projections: dict[str, float], positions: dict[str, str]
) -> dict[str, float]:
    """{position: players at that position occupying a starting lineup, per team}.

    Uses `compute_league_starters` -- the same allocator that fills dedicated slots by
    within-position rank and then awards flex slots to the best remaining flex-eligible players
    -- so a position's starter demand reflects how competitive it actually is for the shared
    flex slots rather than an assumed even split. Sums to the lineup size by construction.

    A dedicated slot the board cannot fill still demands its slots (the same floor
    `market_draft_demand` applies), so a position never collapses to zero demand merely because
    the projection set omits it."""
    result = compute_league_starters(league, projections, positions)
    counts: dict[str, int] = {}
    for player_id in result["starters"]:
        pos = positions.get(player_id)
        if pos is not None:
            counts[pos] = counts.get(pos, 0) + 1
    teams = league.teams or 1
    demand = {pos: n / teams for pos, n in counts.items()}
    for pos, slots in league.dedicated_slots().items():
        demand[pos] = max(demand.get(pos, 0.0), float(slots))
    return demand


@dataclass
class BoardConstants:
    """Per-season quantities that do not depend on the pick state, loaded once."""

    projections: dict[str, float]
    positions: dict[str, str]
    static_vorp: dict[str, float]
    market_ranks: dict[str, tuple[str, float]]
    consumption_demand: dict[str, float]
    starter_demand: dict[str, float]
    # {player_id: (ecr_best, ecr_worst)} and {player_id: confidence}, preloaded in one query
    # each instead of one query per candidate per pick. Purely a speed change: `survival_from`
    # below reproduces `draft.py::next_pick_survival_probability` exactly, and
    # `assert_preloads_match_production` checks that against the real function on real data.
    survival_dispersion: dict[str, tuple[float, float]] = field(default_factory=dict)
    confidences: dict[str, float] = field(default_factory=dict)


def survival_from(
    dispersion: tuple[float, float] | None, next_pick_overall: int | None
) -> float | None:
    """`draft.py::next_pick_survival_probability`'s arithmetic, over a preloaded dispersion row.

    Kept as a separate function (rather than inlined) so the equivalence to production is a
    thing that can be tested directly, and so any future change to the production formula shows
    up here as a test failure rather than as a silently divergent counterfactual."""
    if dispersion is None or next_pick_overall is None:
        return None
    best, worst = dispersion
    if worst <= best:
        return 0.0 if next_pick_overall >= best else 1.0
    if next_pick_overall <= best:
        return 1.0
    if next_pick_overall >= worst:
        return 0.0
    return 1.0 - (next_pick_overall - best) / (worst - best)


def _load_survival_dispersion(
    con: duckdb.DuckDBPyConnection, ecr_type: str, season: int
) -> dict[str, tuple[float, float]]:
    """The latest preseason (Jul/Aug) expert-rank dispersion per player, in one query.

    Mirrors `next_pick_survival_probability`'s WHERE clause and ordering exactly, including
    D56/D61's `page_type` scoping and the "an ecr_type with no known series stays unscoped"
    fallback."""
    from alpha_squad.market.series import series_for_ecr_type

    try:
        page_type: str | None = series_for_ecr_type(ecr_type).page_type
    except ValueError:
        page_type = None
    where = (
        "ecr_type = ? AND ecr_best IS NOT NULL AND ecr_worst IS NOT NULL "
        "AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)"
    )
    params: list[object] = [ecr_type, season]
    if page_type is not None:
        where += " AND page_type = ?"
        params.append(page_type)
    rows = con.execute(
        f"""
        SELECT player_id, ecr_best, ecr_worst FROM (
            SELECT player_id, ecr_best, ecr_worst,
                   row_number() OVER (PARTITION BY player_id ORDER BY scrape_date DESC) AS rn
            FROM market_snapshot WHERE {where}
        ) WHERE rn = 1
        """,
        params,
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def load_board_constants(
    con: duckdb.DuckDBPyConnection, league: LeagueContext, season: int, ecr_type: str
) -> BoardConstants:
    projections, positions = load_season_projections(con, season)
    market_ranks = load_market_ranks(con, ecr_type, season)
    confidences = dict(
        con.execute(
            "SELECT player_id, confidence FROM uncertainty_predictions "
            "WHERE season = ? AND model_version = ? AND confidence IS NOT NULL",
            [season, _uncertainty_version()],
        ).fetchall()
    )
    return BoardConstants(
        projections=projections,
        positions=positions,
        static_vorp=marginal_value_over_replacement(league, projections, positions),
        market_ranks=market_ranks,
        consumption_demand=market_draft_demand(league, market_ranks, projections, positions),
        starter_demand=starter_demand_per_team(league, projections, positions),
        survival_dispersion=_load_survival_dispersion(con, ecr_type, season),
        confidences=confidences,
    )


def assert_preloads_match_production(
    con: duckdb.DuckDBPyConnection,
    board: BoardConstants,
    season: int,
    ecr_type: str,
    next_pick_overall: int,
) -> None:
    """Check the preloaded survival/confidence tables against the production functions, for
    every player on the board. Raises on the first disagreement."""
    for player_id in board.projections:
        expected = next_pick_survival_probability(
            con, player_id, next_pick_overall, season, ecr_type
        )
        got = survival_from(board.survival_dispersion.get(player_id), next_pick_overall)
        if expected is None or got is None:
            if expected is not got:
                raise AssertionError(
                    f"survival preload disagrees for {player_id}: {got!r} vs {expected!r}"
                )
        elif abs(expected - got) > 1e-12:
            raise AssertionError(
                f"survival preload disagrees for {player_id}: {got!r} vs {expected!r}"
            )
        row = con.execute(
            "SELECT confidence FROM uncertainty_predictions "
            "WHERE player_id = ? AND season = ? AND model_version = ?",
            [player_id, season, _uncertainty_version()],
        ).fetchone()
        expected_conf = row[0] if row else None
        got_conf = board.confidences.get(player_id)
        if expected_conf != got_conf:
            raise AssertionError(
                f"confidence preload disagrees for {player_id}: {got_conf!r} vs {expected_conf!r}"
            )


def _demand_for(variant: ScoringVariant, board: BoardConstants) -> dict[str, float]:
    base = (
        board.consumption_demand if variant.demand_target == "consumption" else board.starter_demand
    )
    demand = dict(base)
    for pos, scale in variant.demand_scale.items():
        if pos in demand:
            demand[pos] = demand[pos] * scale
    demand.update(variant.demand_override)
    return demand


def next_turn_replacement(board: BoardConstants, state: PickState) -> dict[str, float]:
    """{position: projection of the best player at that position still on the board at my next
    changed-board pick} -- the value-over-next-available (VONA) replacement level.

    Uses the same literal opponent replay the production opportunity-cost term already uses
    (`replay_opponent_picks`), so this is not a second model of opponent behaviour; it is the
    existing one, read for a different purpose.

    A position with nothing left after the replay is omitted, which callers read the same way
    they read an omitted demand boundary: fall back to the static season-long level. Omitting
    is the only safe answer -- setting the level to zero would hand every remaining player at
    that position their entire projection as surplus."""
    horizon = picks_until_next_turn(
        state.current_pick_overall, state.next_changed_board_pick or state.next_pick_overall
    )
    if horizon <= 0:
        return {}
    remaining = replay_opponent_picks(set(state.available), board.market_ranks, horizon)
    levels: dict[str, float] = {}
    for player_id in remaining:
        pos = board.positions.get(player_id)
        if pos is None or player_id not in board.projections:
            continue
        value = board.projections[player_id]
        if value > levels.get(pos, float("-inf")):
            levels[pos] = value
    return levels


def score_board(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    board: BoardConstants,
    state: PickState,
    variant: ScoringVariant,
    *,
    survival_cache: dict[str, float | None] | None = None,
    confidence_cache: dict[str, float | None] | None = None,
) -> list[VariantScore]:
    """Score every available, evaluable player under `variant`, best first.

    Mirrors `recommend_draft_pick`'s structure exactly -- same guard on whether the pool is a
    board, same per-position (not per-candidate) opportunity cost, same hoisted base lineup --
    so that under `ScoringVariant.control()` the output is the production score."""
    projections, positions = board.projections, board.positions

    max_drafted = league.teams * int(league.roster.get("roster_size", 0))
    pool_is_a_board = max_drafted > 0 and len(projections) - len(state.available) <= max_drafted
    levels: dict[str, float] = {}
    if variant.replacement_mode == "next_turn":
        levels = next_turn_replacement(board, state)
    elif pool_is_a_board:
        levels = demand_boundary_replacement(
            league,
            set(state.available),
            projections,
            positions,
            _demand_for(variant, board),
        )

    n_opp = picks_until_next_turn(state.current_pick_overall, state.next_pick_overall)
    if variant.opportunity_horizon is not None:
        n_opp = variant.opportunity_horizon
    elif variant.opportunity_skip_zero_turn and n_opp <= 0:
        # Arm T3: at a back-to-back snake turn the next pick is one away, so production's
        # horizon is zero opponent picks and every opportunity cost is identically zero. The
        # board this pick is really competing against is the one at the NEXT pick that has
        # opponents in front of it. Derived from the snake geometry, not a tunable horizon.
        n_opp = picks_until_next_turn(state.current_pick_overall, state.next_changed_board_pick)
    opportunity_costs: dict[str, float] = {}
    if variant.use_opportunity_cost and n_opp > 0:
        candidate_positions = {
            p for pid in state.available if (p := positions.get(pid)) is not None
        }
        opportunity_costs = positional_opportunity_cost(
            set(state.available),
            positions,
            board.static_vorp,
            board.market_ranks,
            n_opp,
            candidate_positions,
        )

    needs = roster_need(league, state.roster_positions)
    base_lineup = best_lineup_points(league, state.roster_player_ids, projections, positions)
    msv_over_repl_by_pos: dict[str, float] = {}
    if variant.value_base == "msv_over_replacement":
        msv_over_repl_by_pos = replacement_marginal_starter_values(
            league,
            state.roster_player_ids,
            projections,
            positions,
            levels,
            base_points=base_lineup,
        )

    have: dict[str, int] = {}
    for pos_on_roster in state.roster_positions:
        have[pos_on_roster] = have.get(pos_on_roster, 0) + 1

    survival_cache = survival_cache if survival_cache is not None else {}
    confidence_cache = confidence_cache if confidence_cache is not None else {}

    deferred = (
        set(variant.diagnostic_defer_positions)
        if state.current_pick_overall < variant.diagnostic_defer_until_pick
        else set()
    )
    if deferred and not any(
        positions.get(p) not in deferred for p in state.available if p in board.static_vorp
    ):
        deferred = set()

    out: list[VariantScore] = []
    for player_id in state.available:
        if player_id not in board.static_vorp:
            continue
        pos = positions[player_id]
        if pos in deferred:
            continue
        da_vorp = (
            projections[player_id] - levels[pos] if pos in levels else board.static_vorp[player_id]
        )
        msv = marginal_starter_value(
            league,
            state.roster_player_ids,
            player_id,
            projections,
            positions,
            base_points=base_lineup,
        )
        if variant.value_base == "msv_plus_vorp":
            value_base = msv + variant.vorp_weight * da_vorp
        elif variant.value_base == "vorp_only":
            value_base = da_vorp
        elif variant.value_base == "msv_only":
            value_base = msv
        else:  # msv_over_replacement
            value_base = msv - msv_over_repl_by_pos.get(pos, 0.0)

        confidence = board.confidences.get(player_id)
        survival = survival_from(board.survival_dispersion.get(player_id), state.next_pick_overall)

        fit = roster_fit_multiplier(needs.get(pos, 0.0)) if variant.use_fit_multiplier else 1.0
        risk = (
            (confidence if confidence is not None else 0.7) if variant.use_risk_multiplier else 1.0
        )
        if variant.use_survival_multiplier and survival is not None:
            surv_mult = 1.0 + variant.survival_coefficient * (1.0 - survival)
        else:
            surv_mult = 1.0
        cap = positional_feasibility_cap(league, pos)
        cap_mult = (
            OVER_CAP_VALUE_MULTIPLIER
            if (variant.use_cap_multiplier and cap > 0 and have.get(pos, 0) >= cap)
            else 1.0
        )
        multiplier = fit * risk * surv_mult * cap_mult
        oc = opportunity_costs.get(pos, 0.0)
        out.append(
            VariantScore(
                player_id=player_id,
                position=pos,
                projection=projections[player_id],
                value_base=value_base,
                replacement_level=levels.get(pos),
                opportunity_cost=oc,
                multiplier=multiplier,
                score=(value_base + oc) * multiplier,
            )
        )

    out.sort(key=lambda s: (-s.score, s.player_id))
    return out


def _uncertainty_version() -> str:
    from alpha_squad.models.uncertainty.run import MODEL_VERSION

    return MODEL_VERSION


def assert_control_reproduces_production(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    board: BoardConstants,
    state: PickState,
    *,
    top_n: int = 10,
) -> None:
    """Fail loudly if `ScoringVariant.control()` does not reproduce `recommend_draft_pick`.

    Every counterfactual below is a delta against this control, so if the control itself
    disagrees with the engine, every margin reported is measuring the harness rather than the
    change. Checks both the chosen player and the top-`top_n` scores."""
    rec = recommend_draft_pick(
        con,
        league,
        state.season,
        state.roster_positions,
        state.available,
        next_pick_overall=state.next_pick_overall,
        ecr_type=state.ecr_type,
        top_n=top_n,
        current_pick_overall=state.current_pick_overall,
        roster_player_ids=state.roster_player_ids,
    )
    control = score_board(con, league, board, state, ScoringVariant.control())
    if control[0].player_id != rec.recommendation:
        raise AssertionError(
            f"control variant chose {control[0].player_id} but production chose "
            f"{rec.recommendation} at pick #{state.current_pick_overall}"
        )
    by_id = {s.player_id: s.score for s in control}
    for c in rec.candidates:
        if abs(by_id[c.player_id] - c.score) > CONTROL_TOLERANCE:
            raise AssertionError(
                f"control score {by_id[c.player_id]!r} != production score {c.score!r} for "
                f"{c.player_id} at pick #{state.current_pick_overall}"
            )


# --------------------------------------------------------------------------------------------
# The pre-built counterfactual set for the #20 QB question (Phase 4)
# --------------------------------------------------------------------------------------------


def qb_mechanism_variants(league: LeagueContext) -> list[ScoringVariant]:
    """The one-factor-at-a-time set. Each entry changes exactly one thing about the control,
    except the two explicitly-named combinations at the end."""
    variants = [
        ScoringVariant.control(),
        ScoringVariant(name="A_no_msv", value_base="vorp_only"),
        ScoringVariant(name="B_no_vorp", value_base="msv_only"),
        ScoringVariant(name="C_starter_demand", demand_target="starter"),
        ScoringVariant(name="E_msv_over_replacement", value_base="msv_over_replacement"),
        ScoringVariant(name="F_no_opportunity_cost", use_opportunity_cost=False),
        ScoringVariant(name="F2_oc_horizon_to_round3", opportunity_horizon=18),
        ScoringVariant(name="M_oc_skips_zero_turn", opportunity_skip_zero_turn=True),
        ScoringVariant(name="G_no_survival", use_survival_multiplier=False),
        ScoringVariant(name="G2_no_risk", use_risk_multiplier=False),
        ScoringVariant(name="G3_no_fit", use_fit_multiplier=False),
    ]
    # D: alternative QB boundaries alone, everything else production.
    for qb_demand in (1.0, 1.2, 1.5, 1.8, 2.0, 2.5):
        variants.append(
            ScoringVariant(
                name=f"D_qb_demand_{qb_demand:g}",
                demand_override={"QB": qb_demand},
            )
        )
    # Combinations worth naming because they are the two coherent economic positions, not
    # arbitrary blends: "surplus over what a starter would actually be" and "production's
    # value base but priced against the starter boundary".
    variants.append(
        ScoringVariant(
            name="H_vorp_only_starter_demand",
            value_base="vorp_only",
            demand_target="starter",
        )
    )
    variants.append(
        ScoringVariant(
            name="I_msv_over_starter_replacement",
            value_base="msv_over_replacement",
            demand_target="starter",
        )
    )
    # The timing formulation: replacement is what I could still get at this position at my next
    # changed-board pick, rather than at the end of the draft. Three value bases over it,
    # because which one is right is exactly what is in question.
    variants.append(ScoringVariant(name="J_vona_plus_msv", replacement_mode="next_turn"))
    variants.append(
        ScoringVariant(name="K_vona_only", value_base="vorp_only", replacement_mode="next_turn")
    )
    variants.append(
        ScoringVariant(
            name="L_msv_over_vona",
            value_base="msv_over_replacement",
            replacement_mode="next_turn",
        )
    )
    return variants


def resolve_ecr(league: LeagueContext) -> str:
    return resolve_market_series(league).ecr_type


def with_name(variant: ScoringVariant, name: str) -> ScoringVariant:
    return replace(variant, name=name)


# --------------------------------------------------------------------------------------------
# Variant draft simulation (Phase 11/12)
# --------------------------------------------------------------------------------------------


@dataclass
class VariantDraftResult:
    season: int
    draft_slot: int
    variant: str
    league_id: str
    drafted_player_ids: list[str]
    drafted_positions: list[str]
    starter_points: float
    total_roster_points: float
    n_unfilled_mandatory_slots: int


def simulate_variant_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    draft_slot: int,
    variant: ScoringVariant,
    *,
    ecr_type: str | None = None,
    board: BoardConstants | None = None,
    verify_control: bool = False,
) -> VariantDraftResult:
    """One full snake draft where our seat picks by `variant` and every other seat is the fair
    `market_consensus_roster_aware` benchmark opponent -- the same field every published draft
    number in this project was measured against.

    Deliberately mirrors `evaluation/draft_simulation.py::simulate_draft` pick for pick (same
    snake geometry, same opponent, same outcome scoring via `compute_league_starters` on real
    realized points) so a margin between a variant and the control is attributable to the
    variant alone. `verify_control` additionally asserts, at every one of our picks, that
    `ScoringVariant.control()` reproduces `recommend_draft_pick` on that exact state -- slow,
    so it is used on a sample rather than on every trial.
    """
    from alpha_squad.evaluation.draft_simulation import _actual_points_for
    from alpha_squad.evaluation.opening_audit import snake_overall_pick
    from alpha_squad.league.roster import unfilled_dedicated_slots

    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type
    if board is None:
        board = load_board_constants(con, league, season, ecr_type)

    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    my_picks = [snake_overall_pick(r, draft_slot, league.teams) for r in range(1, total_rounds + 1)]
    available = set(board.projections)
    drafted: list[str] = []
    my_positions: list[str] = []
    opponent_rosters: dict[int, list[str]] = {
        s: [] for s in range(1, league.teams + 1) if s != draft_slot
    }
    confidence_cache: dict[str, float | None] = {}

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
                state = PickState(
                    season=season,
                    ecr_type=ecr_type,
                    roster_player_ids=list(drafted),
                    roster_positions=list(my_positions),
                    available=available,
                    current_pick_overall=current,
                    next_pick_overall=nxt,
                    next_changed_board_pick=next((p for p in my_picks if p > current + 1), None),
                )
                if verify_control:
                    assert_control_reproduces_production(con, league, board, state)
                scored = score_board(
                    con, league, board, state, variant, confidence_cache=confidence_cache
                )
                if not scored:
                    raise RuntimeError(
                        f"no evaluable candidates at pick #{current}, season {season}"
                    )
                pick = scored[0].player_id
                drafted.append(pick)
                my_positions.append(board.positions.get(pick, "UNKNOWN"))
            else:
                pick = roster_aware_market_pick(
                    available,
                    board.market_ranks,
                    board.positions,
                    league,
                    opponent_rosters[slot],
                    picks_remaining,
                )
                opponent_rosters[slot].append(board.positions.get(pick, "UNKNOWN"))
            available.discard(pick)

    actual = _actual_points_for(con, season, drafted)
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        actual,
        {p: board.positions.get(p, "UNKNOWN") for p in drafted},
    )
    return VariantDraftResult(
        season=season,
        draft_slot=draft_slot,
        variant=variant.name,
        league_id=league.league_id,
        drafted_player_ids=drafted,
        drafted_positions=my_positions,
        starter_points=sum(actual.get(p, 0.0) for p in starters["starters"]),
        total_roster_points=sum(actual.values()),
        n_unfilled_mandatory_slots=sum(unfilled_dedicated_slots(league, my_positions).values()),
    )


def with_projection_override(
    league: LeagueContext,
    board: BoardConstants,
    overrides: dict[str, float],
) -> BoardConstants:
    """A copy of `board` with some players' projections replaced, and every quantity derived
    from projections recomputed.

    This is the Phase 7 layer-isolation instrument: it lets the SAME decision engine be run on
    a different projection layer while the market board, the opponent field and the realized
    outcomes all stay exactly as they were, so a difference in drafted rosters is attributable
    to the projection change alone.

    Recomputing the derived quantities is the whole point and is easy to get wrong: static
    VORP, the consumption-demand target and the starter-demand target are all functions of the
    projections, so overriding projections without rebuilding them would score new projections
    against old replacement levels -- a silent hybrid that is neither arm. D81 recorded the
    same class of error (an override that never reached the engine at all).

    `market_ranks` and `survival_dispersion` are deliberately NOT recomputed: they come from the
    real consensus board, which does not change because Alpha's model changed. `confidences`
    likewise stays as measured -- an override is a projection substitution, not a claim about
    the interval model.

    Never used by production; overrides live in memory and no database is written.
    """
    projections = {**board.projections, **overrides}
    unknown = set(overrides) - set(board.projections)
    if unknown:
        raise ValueError(
            f"projection override names {len(unknown)} players not on the board "
            f"(e.g. {sorted(unknown)[:3]}); an override must replace a projection, not add one"
        )
    return BoardConstants(
        projections=projections,
        positions=board.positions,
        static_vorp=marginal_value_over_replacement(league, projections, board.positions),
        market_ranks=board.market_ranks,
        consumption_demand=market_draft_demand(
            league, board.market_ranks, projections, board.positions
        ),
        starter_demand=starter_demand_per_team(league, projections, board.positions),
        survival_dispersion=board.survival_dispersion,
        confidences=board.confidences,
    )
