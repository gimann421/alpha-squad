"""Draft recommendation: expected pick value, next-pick survival probability, roster fit,
alternatives with reasoning -- mirrors AGENT_CONTRACTS.md's Decision contract
(recommendation/alternatives/expected_value/confidence/reasons)."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import load_season_projections, marginal_value_over_replacement
from alpha_squad.league.roster import roster_fit_multiplier, roster_need
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION


@dataclass
class DraftCandidate:
    player_id: str
    position: str
    vorp: float
    confidence: float | None
    survival_probability: float | None
    score: float
    reasons: list[str]


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
    ecr_type: str = "rsf",
) -> float | None:
    """P(player is still available at next_pick_overall), modeling the player's true draft
    rank as Uniform(ecr_best, ecr_worst) -- the real expert-rank dispersion already captured
    in market_snapshot (M4/M8's ecr_best/ecr_worst), not a fabricated distribution. Returns
    None when no market dispersion is on record for this player (no opinion to model)."""
    row = con.execute(
        """
        SELECT ecr_best, ecr_worst FROM market_snapshot
        WHERE player_id = ? AND ecr_type = ? AND ecr_best IS NOT NULL AND ecr_worst IS NOT NULL
        ORDER BY scrape_date DESC LIMIT 1
        """,
        [player_id, ecr_type],
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
    ecr_type: str = "rsf",
    top_n: int = 5,
) -> DraftRecommendation:
    projections, positions = load_season_projections(con, season)
    vorp = marginal_value_over_replacement(league, projections, positions)
    needs = roster_need(league, roster_positions)

    candidates: list[DraftCandidate] = []
    for player_id in available_player_ids:
        if player_id not in vorp:
            continue
        pos = positions[player_id]
        confidence = _confidence_for(con, player_id, season)
        survival = (
            next_pick_survival_probability(con, player_id, next_pick_overall, ecr_type)
            if next_pick_overall is not None
            else None
        )
        fit_mult = roster_fit_multiplier(needs.get(pos, 0.0))
        risk_mult = confidence if confidence is not None else 0.7
        survival_mult = 1.0 if survival is None else (1.0 + 0.3 * (1.0 - survival))
        score = vorp[player_id] * fit_mult * risk_mult * survival_mult

        reasons = [
            f"VORP {vorp[player_id]:+.1f} pts above {pos} replacement",
            f"roster fit multiplier {fit_mult:.2f} ({'need' if needs.get(pos, 0) > 0 else 'depth'} at {pos})",
        ]
        if confidence is not None:
            reasons.append(f"model confidence {confidence:.2f}")
        if survival is not None:
            reasons.append(
                f"{survival:.0%} chance of surviving to your next pick (#{next_pick_overall})"
            )

        candidates.append(
            DraftCandidate(player_id, pos, vorp[player_id], confidence, survival, score, reasons)
        )

    candidates.sort(key=lambda c: -c.score)
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
