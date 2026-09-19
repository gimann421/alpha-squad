"""Weekly fantasy ground truth for Half-PPR and Full-PPR (W1).

What a week's "actual fantasy points" are is the one quantity every weekly metric is computed
against, so it is defined here once, derived rather than assumed, and verified against real
player-weeks by `tests/unit/test_weekly_scoring.py`.

The derivation
--------------
`player_week_stats` carries two nflverse-sourced columns, `fantasy_points` (standard, 0 PPR)
and `fantasy_points_ppr` (1.0 PPR), plus `receptions`. Reception point value is the *only*
thing that differs between the three common formats, so every format in between is an exact
linear function of what is already stored::

    points(r) = fantasy_points_ppr - (1 - r) * receptions

Verified on the real 2024 weekly file (W1): an explicit standard-PPR formula written out from
the scoring rules reproduces `fantasy_points_ppr` to **0.0 maximum absolute difference across
all 5,864 REG QB/RB/WR/TE player-weeks, zero mismatches**, and the two independent routes to
half-PPR (`ppr - 0.5*rec` and `standard + 0.5*rec`) agree to 0.0 on the same rows. So this is
an identity over the stored columns, not a re-implementation that could drift from them.

Why not re-score from raw components
------------------------------------
Re-deriving points from `passing_yards`, `rushing_tds` and so on would introduce a second,
independently-maintained scoring implementation that could disagree with the one every
existing season-long number in this repository was measured under. The verification above is
what earns the right to use the stored column instead: it establishes that the stored column
*is* the explicit formula, so using it keeps the weekly program and the draft program scoring
the same events the same way.

K and DST
---------
Kickers and team defenses have no receptions, so all three formats coincide for them --
`features/kicking_defense.py` writes the identical computed value into both `fantasy_points`
and `fantasy_points_ppr` (D57/D78). The formula above therefore needs no positional special
case, and `COALESCE(receptions, 0)` covers the NULL those rows carry.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass(frozen=True)
class ScoringFormat:
    """A weekly scoring format, identified by its point value per reception.

    `points_per_reception` is the whole parameterisation because it is the only rule that
    differs between the formats W1 scoped (PRODUCT: Half-PPR and Full-PPR). A format that
    changed anything else -- TE premium, a different passing-TD value -- would not be
    expressible here, and adding one means re-deriving from raw components rather than
    widening this dataclass, because the identity in the module docstring would no longer
    hold."""

    name: str
    points_per_reception: float

    def sql_expr(self, table_alias: str = "s") -> str:
        """The SQL expression for realized points under this format.

        Written against `player_week_stats`'s column names. Kept as an expression rather than
        a materialized column so a caller can drop it into any query shape without this module
        owning the FROM clause."""
        a = table_alias
        deduction = 1.0 - self.points_per_reception
        if deduction == 0.0:
            return f"{a}.fantasy_points_ppr"
        return f"({a}.fantasy_points_ppr - {deduction} * COALESCE({a}.receptions, 0))"


#: The two shipped formats. `HALF_PPR` is not stored anywhere -- it is derived by the identity
#: above every time it is needed, so it can never fall out of sync with `FULL_PPR`.
FULL_PPR = ScoringFormat("full_ppr", 1.0)
HALF_PPR = ScoringFormat("half_ppr", 0.5)
STANDARD = ScoringFormat("standard", 0.0)

#: What W1 scoped. `STANDARD` is defined above because it is what `fantasy_points` already is
#: and naming it makes the identity checkable in tests, NOT because it is a product format.
SHIPPED_FORMATS: tuple[ScoringFormat, ...] = (HALF_PPR, FULL_PPR)

#: Positions the weekly product ranks (PRODUCT: no IDP).
RANKED_POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "K", "DST")

#: FLEX eligibility for the weekly product. Deliberately a separate constant from
#: `league/context.py::FLEX_ELIGIBILITY`, which is keyed by a *league config's* slot names: the
#: weekly FLEX ranking is a product surface that exists whether or not any league is loaded.
FLEX_POSITIONS: tuple[str, ...] = ("RB", "WR", "TE")


def format_by_name(name: str) -> ScoringFormat:
    """Look up a format by name, raising rather than defaulting.

    Defaulting an unknown name would silently score a comparison under a format nobody
    chose -- the same class of bug D56 recorded for market series."""
    for fmt in (HALF_PPR, FULL_PPR, STANDARD):
        if fmt.name == name:
            return fmt
    known = ", ".join(f.name for f in (HALF_PPR, FULL_PPR, STANDARD))
    raise ValueError(f"unknown scoring format {name!r}; known: {known}")


def load_realized_points(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    fmt: ScoringFormat,
    *,
    positions: tuple[str, ...] = RANKED_POSITIONS,
) -> dict[str, float]:
    """`{player_id: realized fantasy points}` for everyone who PLAYED in `(season, week)`.

    A player absent from the result did not play -- bye, inactive, injured, not on a roster.
    Nothing is imputed and no zero row is fabricated, the same contract
    `evaluation/weekly_objective.py::load_weekly_points` already established for the draft
    program's weekly objective. Distinguishing "played and scored 0.0" from "did not play" is
    exactly what the production-forecast / availability split in W1 depends on, and imputing a
    zero here would destroy it."""
    rows = con.execute(
        f"""
        SELECT s.player_id, {fmt.sql_expr("s")}
        FROM player_week_stats s
        WHERE s.season = ? AND s.week = ? AND s.position = ANY(?)
        """,
        [season, week, list(positions)],
    ).fetchall()
    return {r[0]: float(r[1] or 0.0) for r in rows}
