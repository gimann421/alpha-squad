"""Dynasty trade recommendation: buy/hold/sell/watch using real dynasty market value
(DynastyProcess `dynasty_values`, M8) and real model-vs-market EDGE (`edge_snapshot`, M8),
with a documented age-curve heuristic. The age curve is explicitly NOT a trained model -- no
ground-truth dynasty-value-decay dataset exists to fit one in this environment, so it is
disclosed as a documented assumption (D25), exactly like every other assumption in
docs/DECISIONS.md, and reported as such in every recommendation's reasons rather than
presented as validated.

`evaluate_trade_package`/`pick_value` (D45) extend this to future draft picks, on the same
value_2qb scale as `dynasty_values` so a pick and a player can be summed and compared directly.
`pick_value` is the same kind of thing as the age curve: a documented heuristic (round/pick-slot/
years-out), not fit from data -- there is no real fantasy-rookie-draft-slot outcome dataset in
this environment to fit one from (NFL draft position != fantasy startup/rookie-draft position,
and no source here provides the latter). `LeagueContext.future_picks` exists in the schema but
is always empty in this deployment (no traded-picks data source is wired for Sleeper or the
static YAML leagues, D45) -- so pick assets are taken as an explicit caller-supplied argument
here, the same way `draft.py`'s `available_player_ids` is caller-supplied rather than inferred,
instead of silently reading a field that would always be empty."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import duckdb

from alpha_squad.market.edge import DEFAULT_ECR_TYPE

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
    con: duckdb.DuckDBPyConnection, player_id: str, season: int, ecr_type: str = DEFAULT_ECR_TYPE
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


# Documented heuristic (D45), not fit from data -- see the module docstring for why no real
# fantasy-rookie-draft-slot outcome dataset exists here to fit one from. Anchored to the real
# value_2qb scale this deployment actually observes (0-10232, median 6, but a real 1st-overall
# rookie-class outcome has reached 5767-8538 in 2022-2025 classes per dynasty_values): a 1.01
# pick is valued well below that realized ceiling (which requires the pick to hit) and well
# above the median outcome (which includes every bust) -- an explicit expected-value-under-
# uncertainty compromise, not a best-case or average-case number.
PICK_ROUND_BASE_VALUE: dict[int, float] = {1: 2200.0, 2: 300.0, 3: 60.0, 4: 15.0}
PICK_ROUND_FLOOR_FRACTION = 0.4  # last pick in a round is worth this fraction of the round's base
FUTURE_YEAR_DISCOUNT = 0.85  # compounding per year out: real uncertainty a pick even conveys


def pick_value(
    round_: int, teams: int, pick_in_round: int | None = None, years_out: int = 0
) -> tuple[float, str]:
    """Value (on the `dynasty_values.value_2qb` scale) for a single draft-pick asset, plus a
    reason string. `pick_in_round=None` (unknown draft order yet) uses the round's midpoint.
    Rounds beyond 4 (rarely tradeable as standalone assets) decay by half each round past 4."""
    if round_ <= 4:
        base = PICK_ROUND_BASE_VALUE[round_]
    else:
        base = PICK_ROUND_BASE_VALUE[4] * (0.5 ** (round_ - 4))

    if pick_in_round is None:
        slot_mult = 1.0 - (1.0 - PICK_ROUND_FLOOR_FRACTION) * 0.5  # round midpoint
        slot_desc = "unknown slot (round midpoint assumed)"
    else:
        span = max(teams - 1, 1)
        progress = min(max(pick_in_round - 1, 0), span) / span
        slot_mult = 1.0 - (1.0 - PICK_ROUND_FLOOR_FRACTION) * progress
        slot_desc = f"pick {pick_in_round} of {teams}"

    year_mult = FUTURE_YEAR_DISCOUNT**years_out
    value = base * slot_mult * year_mult

    reason = (
        f"round {round_} pick, {slot_desc}, {years_out} year(s) out: "
        f"value {value:.0f} (documented heuristic, not a trained model -- docs/DECISIONS.md D45)"
    )
    return value, reason


@dataclass
class PickAsset:
    round: int
    pick_in_round: int | None = None
    years_out: int = 0


@dataclass
class TradePackageSide:
    player_ids: list[str] = field(default_factory=list)
    picks: list[PickAsset] = field(default_factory=list)


@dataclass
class TradePackageValuation:
    side_a_value: float
    side_b_value: float
    delta: float  # side_a_value - side_b_value
    favors: str  # "side_a", "side_b", or "even"
    side_a_reasons: list[str]
    side_b_reasons: list[str]


def _side_value(
    con: duckdb.DuckDBPyConnection, side: TradePackageSide, season: int, ecr_type: str, teams: int
) -> tuple[float, list[str]]:
    total = 0.0
    reasons: list[str] = []
    for player_id in side.player_ids:
        rec = recommend_dynasty_trade(con, player_id, season, ecr_type)
        if rec.age_adjusted_value is not None:
            total += rec.age_adjusted_value
        reasons.append(
            f"{player_id}: age-adjusted dynasty value "
            f"{rec.age_adjusted_value if rec.age_adjusted_value is not None else 'unknown'}"
        )
    for pick in side.picks:
        value, reason = pick_value(pick.round, teams, pick.pick_in_round, pick.years_out)
        total += value
        reasons.append(reason)
    return total, reasons


def evaluate_trade_package(
    con: duckdb.DuckDBPyConnection,
    side_a: TradePackageSide,
    side_b: TradePackageSide,
    season: int,
    teams: int,
    ecr_type: str = DEFAULT_ECR_TYPE,
    *,
    even_threshold: float = 0.10,
) -> TradePackageValuation:
    """Real multi-asset trade comparison: sums real age-adjusted dynasty value for every
    player (via `recommend_dynasty_trade`, unchanged) plus real pick value (`pick_value`, D45)
    for every pick on each side, and reports which side comes out ahead. `even_threshold` is
    the fraction of the larger side's value within which the trade is called roughly even
    rather than favoring either side -- avoids reporting a razor-thin, not-actually-meaningful
    edge as a real recommendation."""
    value_a, reasons_a = _side_value(con, side_a, season, ecr_type, teams)
    value_b, reasons_b = _side_value(con, side_b, season, ecr_type, teams)
    delta = value_a - value_b

    larger = max(value_a, value_b, 1.0)
    is_even = abs(delta) / larger < even_threshold
    favors = "even" if is_even else ("side_a" if delta > 0 else "side_b")

    return TradePackageValuation(
        side_a_value=value_a,
        side_b_value=value_b,
        delta=delta,
        favors=favors,
        side_a_reasons=reasons_a,
        side_b_reasons=reasons_b,
    )
