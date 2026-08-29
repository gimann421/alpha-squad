"""Draft recommendation: expected pick value, positional opportunity cost, next-pick survival
probability, roster fit, alternatives with reasoning -- mirrors AGENT_CONTRACTS.md's Decision
contract (recommendation/alternatives/expected_value/confidence/reasons).

Score, when the caller can supply the roster's actual player ids (D63, D67):

    score = (marginal_starter_value + w * VORP_draft_aware + positional_opportunity_cost)
            x roster_fit x confidence x survival x [0.1 if past this league's usable cap]

with `w` = DRAFT_VORP_WEIGHT = 1.0. Falls back to the value base alone (D55's formula) when only
position counts are known, since marginal starter value is not computable without the roster's
actual players:

    score = (VORP_draft_aware + positional_opportunity_cost) x roster_fit x confidence x survival
            x [0.1 if the position is past this league's usable cap]

**Why the surplus term is draft-aware (D67).** Through D66 the replacement level inside VORP was
computed once from the full season pool, so it was numerically identical at pick 1 and pick 160 --
measured on real 2022 data at round 13 it sat +178.2 too high for QB and +69.1 for WR but only
+2.2 for K, meaning the engine was not over-valuing kickers so much as under-valuing everyone
else. It now moves with the board: replacement is the best player at a position who will still be
undrafted when the draft ends, drawn at the demand one mock draft on the preseason consensus board
says a full draft of this league consumes (`replacement.py::market_draft_demand`, which has no
free parameter and sums to `roster_size` by construction). Measured +32.1 mean starter points over
the D63 formula, 95% CI [+11.5, +52.7], passing every pre-registered gate, and +75.5 [+38.6,
+112.3] out-of-format on `legacy_2qb_dynasty` -- see docs/DECISIONS.md D67, including why the
uniform demand-depth multiplier it replaced was a positional re-weighting in disguise.

Only the VALUE BASE is draft-aware. Season-long `VORP` still drives the opportunity-cost replay,
the reported `DraftCandidate.vorp` field and the candidate-universe filter: that term prices
near-term availability against a season-level scale and was measured that way, so re-basing it
would silently change a second mechanism.

**Why the SUM rather than either term alone (D63).** The two value bases fail in opposite
regimes, and the engine has now shipped each one alone and measured both failing:

- **VORP** (D55) encodes league-wide positional scarcity -- it correctly refuses an early QB in
  a 1-QB league -- but prices a bench K/DST against positional replacement level with no
  knowledge that neither position has flex eligibility, so a "good" bench kicker scores
  positive VORP despite having zero chance of ever starting. Production drafted ~3.8 K and
  ~2.3 DST per 16-round draft as a result.
- **Marginal starter value** (D60) encodes lineup saturation -- once a position's startable
  slots are full, one more body there is worth exactly what he would displace, so the K/DST
  hoarding disappears by construction -- but on an EMPTY roster it is mathematically identical
  to the candidate's own projection, i.e. pure best-player-available by raw points. In a 1-QB
  league raw points favour quarterbacks, which is precisely what VORP existed to correct: the
  engine took a QB in round 2 in 68% of drafts and reached its first RB at mean round 5.24.

Adding them keeps both signals. Measured over 500 real drafts (2021-2025 x 10 slots x 10
value-base variants) against the fair, roster-aware benchmark opponent, under the pre-registered
decision rule in `evaluation/draft_forensics.py` (tier N4): **+39.9 mean starter points over the
D60 formula, 95% CI [+9.1, +70.6], winning 37 of 50 drafts**, passing all four pre-registered
gates and surviving leave-one-season-out on every season. Alternatives that clamp between the
two rather than summing them (`min(vorp, msv)`, and marginal starter value measured over
replacement) were both measured and both LOST to the control -- see docs/DECISIONS.md D63.

`roster_player_ids` is optional and additive, not a hard requirement, so this stays the exact
D55 formula for any caller that only knows roster composition by position count (some
API/agent callers do not yet track individual picks). `roster_positions` is unchanged and
still drives `roster_fit_multiplier`/`positional_feasibility_cap` in every case.

The opportunity-cost term (D55) is the fix for the root cause the M17 forensic audit
identified (docs/DRAFT_ENGINE_FORENSIC_AUDIT.md): the score previously had no representation
of *positional* opportunity cost, only a single-*player* survival probability, so a position
could empty out between this team's turns without anything in the score ever noticing. See
`league/opportunity_cost.py` for the mechanism and why `positional_scarcity()` is deliberately
NOT used here (adding it made the pathology measurably worse). D63 re-measured it rather than
assuming it still helps under a changed value base: switching it off is significantly worse on
three of the five value bases tested (VORP -94.0, min -75.3, msv-over-replacement -81.0, all
95% CIs excluding zero) and statistically indistinguishable on this one (-3.6, CI [-22.3,
+15.2]). It is kept: the evidence for removing it is absent, and it is what protects against
the positional-depletion pathology if the value base ever changes again."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.opportunity_cost import (
    load_market_ranks,
    picks_until_next_turn,
    positional_opportunity_cost,
)
from alpha_squad.league.replacement import (
    best_lineup_points,
    demand_boundary_replacement,
    load_season_projections,
    marginal_starter_value,
    marginal_value_over_replacement,
    market_draft_demand,
)
from alpha_squad.league.roster import (
    OVER_CAP_VALUE_MULTIPLIER,
    positional_feasibility_cap,
    roster_fit_multiplier,
    roster_need,
)
from alpha_squad.market.series import resolve_market_series, series_for_ecr_type
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

# Weight on the VORP term in the D63 value base `msv + w * VORP`. PRE-REGISTERED at 1.0
# before the N-tier ablation ran -- equal weighting, the Occam choice with no free dial to
# tune, and the value the already-measured M1 tier used. It is a named constant rather than a
# literal so the ablation tier and production provably share one number.
DRAFT_VORP_WEIGHT = 1.0


@dataclass
class DraftCandidate:
    player_id: str
    position: str
    vorp: float
    confidence: float | None
    survival_probability: float | None
    score: float
    reasons: list[str]
    marginal_starter_value: float | None = None


@dataclass
class DraftRecommendation:
    recommendation: str
    alternatives: list[str]
    expected_value: float
    confidence: float
    reasons: list[str]
    candidates: list[DraftCandidate]


def _confidence_for(con: duckdb.DuckDBPyConnection, player_id: str, season: int) -> float | None:
    row = con.execute(
        "SELECT confidence FROM uncertainty_predictions WHERE player_id = ? AND season = ? AND model_version = ?",
        [player_id, season, UNCERTAINTY_MODEL_VERSION],
    ).fetchone()
    return row[0] if row else None


def next_pick_survival_probability(
    con: duckdb.DuckDBPyConnection,
    player_id: str,
    next_pick_overall: int,
    season: int,
    ecr_type: str = "rsf",
) -> float | None:
    """P(player is still available at next_pick_overall), modeling the player's true draft
    rank as Uniform(ecr_best, ecr_worst) -- the real expert-rank dispersion already captured
    in market_snapshot (M4/M8's ecr_best/ecr_worst), not a fabricated distribution. Returns
    None when no market dispersion is on record for this player (no opinion to model).

    Restricted to `season`'s own Jul/Aug preseason snapshot -- the same leakage-safe pattern
    `market/edge.py::_preseason_overall_market` already uses -- rather than simply the latest
    snapshot ever recorded. Without this, a draft for a past `season` could see expert-rank
    dispersion recorded years after that draft actually happened (found via a real historical
    draft simulation, docs/DECISIONS.md D54: many players' market_snapshot rows span 2021 to
    2026, so an un-scoped "latest" lookup for a 2021 draft could read a 2026 snapshot).

    Also scoped to a single `page_type` (D56/D61 Stage 1.5), mirroring
    `market/edge.py::_preseason_overall_market`: `ecr_type` alone is not a coherent rank
    space -- 'ro' merges the PPR draft board with a separately-ranked IDP board -- and this
    function was the one market consumer still filtering on `ecr_type` alone. An `ecr_type`
    with no known series (e.g. a live-capture ecr_type with only one page) stays unscoped."""
    try:
        page_type: str | None = series_for_ecr_type(ecr_type).page_type
    except ValueError:
        page_type = None
    where = (
        "player_id = ? AND ecr_type = ? AND ecr_best IS NOT NULL AND ecr_worst IS NOT NULL "
        "AND year(scrape_date) = ? AND month(scrape_date) IN (7, 8)"
    )
    params: list[object] = [player_id, ecr_type, season]
    if page_type is not None:
        where += " AND page_type = ?"
        params.append(page_type)
    row = con.execute(
        f"""
        SELECT ecr_best, ecr_worst FROM market_snapshot
        WHERE {where}
        ORDER BY scrape_date DESC LIMIT 1
        """,
        params,
    ).fetchone()
    if row is None:
        return None
    best, worst = row
    if worst <= best:
        return 0.0 if next_pick_overall >= best else 1.0
    if next_pick_overall <= best:
        return 1.0
    if next_pick_overall >= worst:
        return 0.0
    prob_gone = (next_pick_overall - best) / (worst - best)
    return 1.0 - prob_gone


def recommend_draft_pick(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    roster_positions: list[str],
    available_player_ids: set[str],
    next_pick_overall: int | None = None,
    ecr_type: str | None = None,
    top_n: int = 5,
    current_pick_overall: int | None = None,
    roster_player_ids: list[str] | None = None,
) -> DraftRecommendation:
    # Which consensus board this league's market signals should come from is a property of
    # the league, not a constant (D56): a 1-QB league and a superflex league price QBs very
    # differently, and reading the wrong board reads the wrong market. An explicit ecr_type
    # still wins, so a caller can compare against a specific series deliberately.
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type

    projections, positions = load_season_projections(con, season)
    vorp = marginal_value_over_replacement(league, projections, positions)
    needs = roster_need(league, roster_positions)

    # Draft-aware replacement level (D67). Until D67, `vorp` above was the ONLY replacement
    # measure the engine had, and it is computed from the full season pool -- `available_player_ids`
    # never reached it, so the level a pick was scored against was numerically identical at pick
    # 1 and pick 160. Measured on real 2022 data at round 13, that static level sat +178.2 too
    # high for QB and +69.1 for WR but only +2.2 for K, so the engine was not over-valuing
    # kickers so much as under-valuing everyone else.
    #
    # The demand target is derived, not tuned: one mock draft of this league on the preseason
    # consensus board says how many players at each position a full draft consumes, and
    # replacement is drawn at that boundary among the players still on the board -- the classic
    # VBD definition ("the best player still freely available after the draft") made literal.
    # See `market_draft_demand` for why the earlier depth targets were wrong in SHAPE and why a
    # uniform multiplier on `startable_slots` could not fix them.
    #
    # `vorp` stays STATIC and is what the opportunity-cost replay, the reported candidate field
    # and the candidate-universe filter all use: the D55 opportunity-cost term prices near-term
    # availability against a season-level scale and was measured that way, so re-basing it here
    # would silently change a second mechanism. Only the VALUE BASE moves to the draft-aware
    # level, which is exactly the D67 tier that was measured.
    #
    # It applies only when `available_player_ids` plausibly IS the remaining board. That is not
    # guaranteed: `POST /league/{id}/draft` lets a caller pass any set, and a four-player
    # shortlist means "these are the players I am asking about", not "these are the only players
    # left in the league". Read as a board, such a shortlist says ~all players are drafted, which
    # would collapse every position's demand to zero and price the whole shortlist at no surplus.
    # The bound is structural, not a threshold: a draft removes at most `teams * roster_size`
    # players, so a pool implying more than that cannot be a draft in progress. At the real
    # benchmark's last pick exactly `teams * roster_size` are gone, so this never fires there.
    market_ranks = load_market_ranks(con, ecr_type, season)
    max_drafted = league.teams * int(league.roster.get("roster_size", 0))
    pool_is_a_board = max_drafted > 0 and len(projections) - len(available_player_ids) <= max_drafted
    draft_aware_levels: dict[str, float] = {}
    if pool_is_a_board:
        draft_aware_levels = demand_boundary_replacement(
            league,
            set(available_player_ids),
            projections,
            positions,
            market_draft_demand(league, market_ranks, projections, positions),
        )
    have_at_position: dict[str, int] = {}
    for pos_on_roster in roster_positions:
        have_at_position[pos_on_roster] = have_at_position.get(pos_on_roster, 0) + 1

    # Positional opportunity cost (D55). Computed ONCE per call, for each position present in
    # the candidate pool -- not once per candidate. That is the mechanism's real shape (the
    # cost is a property of the position, not of any individual player), and it is what keeps
    # the opponent replay affordable: measured at ~9x faster than the per-candidate form with
    # byte-identical results. Degrades to all-zero (i.e. exactly the pre-D55 score) when the
    # caller cannot say where in the draft we are, rather than guessing.
    n_opponent_picks = picks_until_next_turn(current_pick_overall, next_pick_overall)
    opportunity_costs: dict[str, float] = {}
    if n_opponent_picks > 0:
        candidate_positions = {
            p for pid in available_player_ids if (p := positions.get(pid)) is not None
        }
        opportunity_costs = positional_opportunity_cost(
            set(available_player_ids),
            positions,
            vorp,
            market_ranks,
            n_opponent_picks,
            candidate_positions,
        )

    # Marginal starter value (D60): "would this player actually improve MY starting lineup,
    # and by how much" -- only computable when the caller knows the roster's actual players,
    # not just position counts. The base lineup value depends on the current roster alone, so
    # it is hoisted out of the per-candidate loop exactly like the opportunity-cost replay
    # above; recomputing it per candidate would be the same class of waste D55 already fixed.
    base_lineup_points = None
    if roster_player_ids is not None:
        base_lineup_points = best_lineup_points(league, roster_player_ids, projections, positions)

    candidates: list[DraftCandidate] = []
    for player_id in available_player_ids:
        if player_id not in vorp:
            continue
        pos = positions[player_id]
        confidence = _confidence_for(con, player_id, season)
        survival = (
            next_pick_survival_probability(con, player_id, next_pick_overall, season, ecr_type)
            if next_pick_overall is not None
            else None
        )
        fit_mult = roster_fit_multiplier(needs.get(pos, 0.0))
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))

        # The value base is marginal starter value when the roster's actual players are known
        # (D60), else VORP (D55) -- see the module docstring for why, and for the measured
        # comparison that decided it. Either way it is added to the opportunity cost *before*
        # the multipliers rather than to the finished score, for the same two reasons D55
        # established: the term cannot overwhelm the score, because it is discounted by the
        # same roster-fit and confidence factors as the value it augments; and chasing a
        # position the roster is already saturated at is automatically damped by that
        # position's own fit multiplier.
        opportunity_cost = opportunity_costs.get(pos, 0.0)
        # D67: the value base's surplus term is measured against the draft-aware level.
        # `projections[player_id] - draft_aware_levels[pos]` rather than `vorp[player_id]`,
        # falling back to the static VORP for a position the demand model does not cover.
        draft_aware_vorp = (
            projections[player_id] - draft_aware_levels[pos]
            if pos in draft_aware_levels
            else vorp[player_id]
        )
        msv_for_candidate = None
        if base_lineup_points is not None:
            msv_for_candidate = marginal_starter_value(
                league,
                roster_player_ids,
                player_id,
                projections,
                positions,
                base_points=base_lineup_points,
            )
            # D63: the value base is the SUM, not either term alone -- see the module
            # docstring for the measurement that decided it.
            value_base = msv_for_candidate + DRAFT_VORP_WEIGHT * draft_aware_vorp
        else:
            value_base = draft_aware_vorp
        score = (value_base + opportunity_cost) * fit_mult * risk_mult * survival_mult

        # Hard feasibility floor, past which one more body at this position cannot start.
        # Complements the D54 saturation fix (which tapers `fit_mult`) rather than replacing it.
        cap = positional_feasibility_cap(league, pos)
        over_cap = cap > 0 and have_at_position.get(pos, 0) >= cap
        if over_cap:
            score *= OVER_CAP_VALUE_MULTIPLIER

        reasons = [
            f"VORP {draft_aware_vorp:+.1f} pts above the {pos} still on the board "
            f"(replacement {draft_aware_levels.get(pos, 0.0):.1f}; season-long VORP "
            f"{vorp[player_id]:+.1f} vs a static {pos} replacement)"
        ]
        if msv_for_candidate is not None:
            reasons.append(f"marginal starter value {msv_for_candidate:+.1f} pts to your roster")
        reasons.append(
            f"roster fit multiplier {fit_mult:.2f} ({'need' if needs.get(pos, 0) > 0 else 'depth'} at {pos})"
        )
        if opportunity_cost > 0:
            reasons.append(
                f"{pos} opportunity cost +{opportunity_cost:.1f} pts "
                f"(that much {pos} value is expected to be gone in the {n_opponent_picks} "
                f"picks before your next turn at #{next_pick_overall})"
            )
        if over_cap:
            reasons.append(
                f"already hold {have_at_position.get(pos, 0)} {pos} vs this league's usable "
                f"cap of {cap}; valued at {OVER_CAP_VALUE_MULTIPLIER:g}x"
            )
        if confidence is not None:
            reasons.append(f"model confidence {confidence:.2f}")
        if survival is not None:
            reasons.append(
                f"{survival:.0%} chance of surviving to your next pick (#{next_pick_overall})"
            )

        candidates.append(
            DraftCandidate(
                player_id,
                pos,
                vorp[player_id],
                confidence,
                survival,
                score,
                reasons,
                marginal_starter_value=msv_for_candidate,
            )
        )

    # player_id is a deterministic tie-break, not a ranking preference: `candidates` is built
    # by iterating `available_player_ids` (a `set`), whose order depends on hash randomization
    # that differs across process runs -- without this, an exact score tie could pick a
    # different player on a re-run of the identical historical draft. See docs/DECISIONS.md D54.
    candidates.sort(key=lambda c: (-c.score, c.player_id))
    top = candidates[:top_n]
    if not top:
        raise RuntimeError(
            "no evaluable available players for this draft recommendation -- "
            "check that uncertainty predictions exist for this season"
        )

    best = top[0]
    return DraftRecommendation(
        recommendation=best.player_id,
        alternatives=[c.player_id for c in top[1:]],
        expected_value=best.score,
        confidence=best.confidence if best.confidence is not None else 0.5,
        reasons=best.reasons,
        candidates=top,
    )
