"""Waiver/FAAB recommendation: meaningful-role probability, expected fantasy value, dynasty
value, value-spike probability, roster fit, replacement player, competing-bid likelihood,
FAAB budget/rules (PRODUCT_SPEC.md's exact "Waiver/FAAB should incorporate" list)."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.evidence.prior_update import aggregate_evidence
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import (
    load_season_projections,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.roster import roster_fit_multiplier, roster_need
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION

MAX_BID_FRACTION_OF_BUDGET = 0.40


@dataclass
class WaiverRecommendation:
    player_id: str
    position: str
    expected_points: float
    meaningful_role_probability: float | None
    dynasty_value: float | None
    value_spike_probability: float
    replacement_level: float
    marginal_value: float
    roster_fit_multiplier: float
    competing_bid_likelihood: float
    recommended_bid: float
    reasons: list[str]


def _value_spike_probability(
    con: duckdb.DuckDBPyConnection, player_id: str, season: int, week: int
) -> float:
    """0-1 read on recent structured evidence (M9) as a proxy for "is this player's value
    about to spike": maps the signed, bounded aggregate_evidence score ([-1, 1], recent-week
    evidence only) onto 0-1. 0.5 = no recent evidence either way, not a penalty."""
    signed_score, _ = aggregate_evidence(con, player_id, season, week)
    return 0.5 + 0.5 * signed_score


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi <= lo:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def recommend_waiver_pickup(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    week: int,
    player_id: str,
    roster_positions: list[str],
) -> WaiverRecommendation:
    projections, positions = load_season_projections(con, season)
    if player_id not in projections:
        raise RuntimeError(f"no projection for {player_id} in season {season}; cannot evaluate")
    position = positions[player_id]

    levels = replacement_level(league, projections, positions)
    scarcity = positional_scarcity(league, projections, positions)
    scarcity_normalized = _normalize(scarcity)

    role_row = con.execute(
        "SELECT top24_prob FROM uncertainty_predictions WHERE player_id = ? AND season = ? AND model_version = ?",
        [player_id, season, UNCERTAINTY_MODEL_VERSION],
    ).fetchone()
    meaningful_role_prob = role_row[0] if role_row else None

    dynasty_row = con.execute(
        "SELECT value_2qb FROM dynasty_values WHERE player_id = ?", [player_id]
    ).fetchone()
    dynasty_value = dynasty_row[0] if dynasty_row else None

    spike_prob = _value_spike_probability(con, player_id, season, week)
    marginal_value = projections[player_id] - levels.get(position, 0.0)
    needs = roster_need(league, roster_positions)
    fit_mult = roster_fit_multiplier(needs.get(position, 0.0))

    competing_bid_likelihood = min(
        1.0,
        max(
            0.0,
            (scarcity_normalized.get(position, 0.5) * 0.6) + ((meaningful_role_prob or 0.0) * 0.4),
        ),
    )

    # Scale relative to the deepest starter-level VORP so both terms are meaningful within
    # this league's own value range, not an arbitrary absolute points threshold.
    scale = max((v for v in levels.values()), default=1.0) or 1.0
    # A real recent value spike (M9 evidence -- e.g. a rookie's real in-season role change)
    # must be able to justify a real bid even when the static, season-level marginal_value
    # is negative or small: a waiver add is precisely a bet on what just happened, not a
    # restatement of the preseason baseline. spike_prob=0.5 (no recent evidence) contributes
    # nothing; a confirmed spike (spike_prob near 1.0) contributes up to half of `scale`.
    spike_contribution = max(0.0, spike_prob - 0.5) * 2.0 * (scale * 0.5)
    bid_signal = (
        (max(0.0, marginal_value) + spike_contribution)
        * fit_mult
        * (0.5 + 0.5 * competing_bid_likelihood)
    )
    bid_fraction = min(MAX_BID_FRACTION_OF_BUDGET, bid_signal / (scale * 2))
    recommended_bid = round(league.faab_budget * bid_fraction, 2)

    reasons = [
        f"marginal value {marginal_value:+.1f} pts above {position} replacement ({levels.get(position, 0.0):.1f})",
        f"roster fit multiplier {fit_mult:.2f}",
        f"competing-bid likelihood {competing_bid_likelihood:.0%} (position scarcity + role probability)",
        f"value-spike read {spike_prob:.2f} from recent structured evidence",
    ]
    if meaningful_role_prob is not None:
        reasons.append(f"meaningful-role (top-24) probability {meaningful_role_prob:.2f}")
    if dynasty_value is not None:
        reasons.append(f"dynasty value (2QB) {dynasty_value:.0f}")

    return WaiverRecommendation(
        player_id=player_id,
        position=position,
        expected_points=projections[player_id],
        meaningful_role_probability=meaningful_role_prob,
        dynasty_value=dynasty_value,
        value_spike_probability=spike_prob,
        replacement_level=levels.get(position, 0.0),
        marginal_value=marginal_value,
        roster_fit_multiplier=fit_mult,
        competing_bid_likelihood=competing_bid_likelihood,
        recommended_bid=recommended_bid,
        reasons=reasons,
    )
