"""Which market/ECR series is the right consensus for a given league (docs/DECISIONS.md D56).

A market series is *not* just an `ecr_type`. DynastyProcess's `fp_ecr_history` mirror labels
several independently-ranked FantasyPros pages with the same `ecr_type`, so a series is the
pair `(ecr_type, page_type)` -- see `storage/schema.py`'s `market_snapshot.page_type` comment
for the collision this caused.

More importantly, the series has to *match the league format*. `rsf` is FantasyPros'
`ppr-superflex-cheatsheets.php` board, and it ranks QBs the way a superflex league values
them: measured on the real preseason-2024 snapshot, 9 of the overall top 15 are QBs, first QB
at ECR 1.7. `ro` is the standard `ppr-cheatsheets.php` PPR board: 0 QBs in the top 15, first
QB at ECR 23.4. Scoring a 1-QB league against `rsf` measures the wrong game entirely -- it was
the correct choice only while the target league was 2QB (D21), and every draft number recorded
before D56 was measured against it.

Resolution is derived from the league's own lineup and format, never hardcoded, so supplying a
different league config selects a different board automatically -- the 1-QB redraft default is
a default, not a limitation."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_squad.league.context import FLEX_ELIGIBILITY, LeagueContext


@dataclass(frozen=True)
class MarketSeries:
    """One coherent, independently-ranked consensus board."""

    ecr_type: str
    page_type: str
    label: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.ecr_type}/{self.page_type}"


# The four boards this deployment ingests, each pinned to the single page_type that actually
# carries its overall ranking. Verified against the real snapshot, not assumed:
#   ro  redraft-overall  /nfl/rankings/ppr-cheatsheets.php            2021-01-01 -> 2026-08-21
#   rsf redraft-op       /nfl/rankings/ppr-superflex-cheatsheets.php  2021-01-01 -> 2026-08-21
#   do  dynasty-overall  /nfl/rankings/dynasty-overall.php            2020-10-16 -> 2026-08-21
#   dsf dynasty-op       /nfl/rankings/dynasty-superflex.php          2020-10-16 -> 2026-08-21
#
# `redraft-overall` also carries `/nfl/rankings/ros-ppr-overall.php` (rest-of-season) rows, a
# genuinely different product. They never appear in July or August -- verified: ros-ppr-overall
# exists only in months 9-12 -- so the preseason Jul/Aug scoping every consumer here already
# applies (D54's leakage-safe pattern) excludes them by construction. A future non-preseason
# consumer would need to filter on fp_page as well; none exists today.
REDRAFT_1QB = MarketSeries("ro", "redraft-overall", "redraft PPR overall (1QB)")
REDRAFT_SUPERFLEX = MarketSeries("rsf", "redraft-op", "redraft PPR superflex (2QB)")
DYNASTY_1QB = MarketSeries("do", "dynasty-overall", "dynasty overall (1QB)")
DYNASTY_SUPERFLEX = MarketSeries("dsf", "dynasty-op", "dynasty superflex (2QB)")

ALL_SERIES = (REDRAFT_1QB, REDRAFT_SUPERFLEX, DYNASTY_1QB, DYNASTY_SUPERFLEX)

# The 1-QB redraft board is the product default (docs/TARGET_FORMAT_1QB.md). Callers with a
# real league context should resolve from it rather than using this.
DEFAULT_SERIES = REDRAFT_1QB


def is_superflex(league: LeagueContext) -> bool:
    """True when the league lets a team start more than one QB -- either through multiple
    dedicated QB slots or through a QB-eligible flex. Both are real superflex shapes and both
    move the QB market the same way, which is what selects the board."""
    if league.dedicated_slots().get("QB", 0) > 1:
        return True
    return any(
        "QB" in FLEX_ELIGIBILITY.get(flex_name, ()) and count > 0
        for flex_name, count in league.flex_slots().items()
    )


def is_dynasty(league: LeagueContext) -> bool:
    """Dynasty/keeper formats price multi-year value; redraft prices one season. `format` is
    free-form (it can arrive from Sleeper), so match on substring rather than equality."""
    fmt = (league.format or "").strip().lower()
    return "dynasty" in fmt or "keeper" in fmt


def resolve_market_series(league: LeagueContext) -> MarketSeries:
    """The consensus board that matches this league's format. Derived, not configured."""
    if is_dynasty(league):
        return DYNASTY_SUPERFLEX if is_superflex(league) else DYNASTY_1QB
    return REDRAFT_SUPERFLEX if is_superflex(league) else REDRAFT_1QB


def series_for_ecr_type(ecr_type: str) -> MarketSeries:
    """The series a bare `ecr_type` names, for call sites that still pass one (CLI flags,
    persisted `EvaluationConfig` rows). Raises rather than guessing: an unknown ecr_type has
    no known page_type, and defaulting one would silently reintroduce the merged-rank-space
    bug this module exists to prevent."""
    for series in ALL_SERIES:
        if series.ecr_type == ecr_type:
            return series
    known = ", ".join(s.ecr_type for s in ALL_SERIES)
    raise ValueError(f"unknown ecr_type '{ecr_type}'; known series: {known}")
