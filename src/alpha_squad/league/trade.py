"""Dynasty trade recommendation: buy/hold/sell/watch using real dynasty market value
(DynastyProcess `dynasty_values`, M8) and real model-vs-market EDGE (`edge_snapshot`, M8),
with a documented age-curve heuristic. The age curve is explicitly NOT a trained model -- no
ground-truth dynasty-value-decay dataset exists to fit one in this environment, so it is
disclosed as a documented assumption (D25), exactly like every other assumption in
docs/DECISIONS.md, and reported as such in every recommendation's reasons rather than
presented as validated."""

from __future__ import annotations

import json
from dataclasses import dataclass

import duckdb

# Position-specific age curve breakpoints, fantasy-analytics convention (peak, decline
# start, cliff). A documented heuristic (D25), not fit from data.
AGE_CURVE_PARAMS: dict[str, dict[str, int]] = {
    "RB": {"peak": 24, "decline_start": 27, "cliff": 30},
    "WR": {"peak": 26, "decline_start": 29, "cliff": 33},
    "TE": {"peak": 27, "decline_start": 30, "cliff": 34},
    "QB": {"peak": 28, "decline_start": 34, "cliff": 38},
}


def age_curve_multiplier(position: str | None, age: float | None) -> float:
    """1.0 through decline_start, linearly decaying to 0.5 at the cliff age, floored at 0.3
    beyond it. Missing age or an unrecognized position returns 1.0 -- no adjustment, rather
    than a fabricated guess."""
    params = AGE_CURVE_PARAMS.get(position) if position else None
    if params is None or age is None or age <= params["decline_start"]:
        return 1.0
    if age <= params["cliff"]:
        span = params["cliff"] - params["decline_start"]
        progress = (age - params["decline_start"]) / span if span > 0 else 1.0
        return 1.0 - 0.5 * progress
    return 0.3


@dataclass
class TradeRecommendation:
    player_id: str
    action: str
    dynasty_value_2qb: float | None
    age: float | None
    age_curve_multiplier: float
    age_adjusted_value: float | None
    reasons: list[str]


def recommend_dynasty_trade(
    con: duckdb.DuckDBPyConnection, player_id: str, season: int, ecr_type: str = "rsf"
) -> TradeRecommendation:
    dv_row = con.execute(
        "SELECT value_2qb, age FROM dynasty_values WHERE player_id = ?", [player_id]
    ).fetchone()
    dynasty_value, age = dv_row if dv_row else (None, None)

    edge_row = con.execute(
        "SELECT action, reasons_json, position FROM edge_snapshot "
        "WHERE player_id = ? AND season = ? AND ecr_type = ? ORDER BY built_at DESC LIMIT 1",
        [player_id, season, ecr_type],
    ).fetchone()
    if edge_row is None:
        action, edge_reasons, position = "WATCH", [], None
    else:
        action, reasons_json, position = edge_row
        edge_reasons = json.loads(reasons_json)

    mult = age_curve_multiplier(position, age)
    age_adjusted_value = dynasty_value * mult if dynasty_value is not None else None

    reasons = list(edge_reasons)
    if age is not None and position:
        reasons.append(
            f"age {age:.1f} at {position}: age-curve multiplier {mult:.2f} "
            "(documented heuristic, not a trained model -- docs/DECISIONS.md D25)"
        )
    if dynasty_value is not None:
        reasons.append(f"current dynasty value (2QB): {dynasty_value:.0f}")
    if not edge_row:
        reasons.append(
            f"no EDGE on record for this player/season/{ecr_type}; action defaults to WATCH"
        )

    return TradeRecommendation(
        player_id=player_id,
        action=action,
        dynasty_value_2qb=dynasty_value,
        age=age,
        age_curve_multiplier=mult,
        age_adjusted_value=age_adjusted_value,
        reasons=reasons,
    )
