"""Which ECR series is a *weekly* consensus board, and what each one actually ranks (W1).

This is D56's rule applied to the weekly program: **a market series is the pair
`(ecr_type, page_type)`, never `ecr_type` alone**, because DynastyProcess's `db_fpecr` mirror
labels several independently-ranked FantasyPros pages with the same `ecr_type`. The weekly
pages are a different set from the four draft pages `market/series.py` resolves, and the
difference matters more than it looks.

Measured on the real mirror (W1, `scripts/research/w1_weekly_foundation_audit.py`)
---------------------------------------------------------------------------------
Seven weekly series exist under the modern `/nfl/rankings/*.php` labels, each with **96 scrape
dates spanning 2020-10-16 to 2026-09-18**:

    wp / weekly-qb    /nfl/rankings/qb.php             QB, 1..N
    wp / weekly-rb    /nfl/rankings/ppr-rb.php         RB, 1..N
    wp / weekly-wr    /nfl/rankings/ppr-wr.php         WR, 1..N
    wp / weekly-te    /nfl/rankings/ppr-te.php         TE, 1..N
    wp / weekly-k     /nfl/rankings/k.php              K,  1..N
    wp / weekly-dst   /nfl/rankings/dst.php            DST, 1..N (team-coded, no player id)
    wsf/ weekly-op    /nfl/rankings/ppr-superflex.php  QB+RB+WR+TE, one cross-position 1..N

Two consequences, both load-bearing, both established by measurement rather than assumed:

**1. There is no 1-QB weekly overall/FLEX board.** `ppr-flex.php` appears in the mirror only
between 2019-12-27 and 2020-10-12 under the pre-rename labels (`wo/weekly-offense`, 7 dates),
and never again. The only weekly *cross-position* board from 2020-10-16 onward is the
**superflex** one. This is exactly the trap D56 caught for the draft board, where every number
recorded before D56 had been measured against `rsf` and therefore described a superflex
league. `flex_reference_series()` is named to make that inheritance impossible to miss.

**2. Removing QBs from the superflex board is a defensible FLEX reconstruction, and W1
measured how defensible.** Within-position Spearman between the ordering `wsf/weekly-op`
induces and the dedicated positional board, over all 96 boards:

    RB  median 0.9965   p10 0.9916   min 0.9866   (median n = 115)
    WR  median 0.9997   p10 0.9988   min 0.9862   (median n = 165)
    TE  median 0.9992   p10 0.9962   min 0.9817   (median n =  98)

So the superflex board and the positional boards are the same product's two views, and
dropping QBs yields an RB/WR/TE ordering consistent with FantasyPros' own positional
rankings. **What this does NOT establish** is that the superflex board's *cross-position*
RB-vs-WR-vs-TE calibration equals what a 1-QB flex board would publish; no such board exists
to check against. The reconstruction is an assumption with measured internal support, and it
is recorded as an assumption in `docs/weekly/W1_FOUNDATION_AUDIT.md`, not as an equivalence.

**3. Full PPR only.** The mirror contains no `half-point-ppr-*` page and no standard-scoring
page at any date -- verified by pattern search over every distinct `fp_page` value. The weekly
RB/WR/TE boards are the PPR pages. A Half-PPR ECR benchmark therefore does not exist
historically and cannot be reconstructed; see `docs/weekly/W1_FOUNDATION_AUDIT.md`.

Not ingested
------------
`market/consensus.py::DEFAULT_ECR_TYPES` is `("ro", "do", "rsf", "dsf")` -- the four *draft*
series. None of the weekly `ecr_type`s above is written into `market_snapshot`, so weekly ECR
is present in the snapshot this project already downloads and absent from its database. That
is a one-line widening of an existing filter, and it is a **production change**, so W1 does
not make it; the audit reads the recorded `fp_ecr_history` snapshot directly instead.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The mirror relabelled every page on 2020-10-16 (D95 recorded the same cutover for the draft
#: series). Weekly rows before that date carry different `page_type` labels for the same
#: FantasyPros pages and are deliberately NOT wired in as a fallback -- adopting them would
#: change what a "weekly board" means mid-series, which is a series-definition decision needing
#: its own pre-registration rather than a silent substitution (D56's rule).
FIRST_MODERN_WEEKLY_DATE = "2020-10-16"


@dataclass(frozen=True)
class WeeklyMarketSeries:
    """One coherent, independently-ranked weekly consensus board."""

    ecr_type: str
    page_type: str
    fp_page: str
    #: Positions this board ranks. A cross-position board carries several; a positional board
    #: carries exactly one.
    positions: tuple[str, ...]
    label: str
    #: True when rows identify a team defense by team code rather than a player id, so the
    #: join is `FANTASYPROS_TEAM_ALIASES` + `asq_dst_<team>` rather than `fantasypros_id`.
    team_coded: bool = False

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.ecr_type}/{self.page_type}"


WEEKLY_QB = WeeklyMarketSeries("wp", "weekly-qb", "/nfl/rankings/qb.php", ("QB",), "weekly QB")
WEEKLY_RB = WeeklyMarketSeries(
    "wp", "weekly-rb", "/nfl/rankings/ppr-rb.php", ("RB",), "weekly RB (PPR)"
)
WEEKLY_WR = WeeklyMarketSeries(
    "wp", "weekly-wr", "/nfl/rankings/ppr-wr.php", ("WR",), "weekly WR (PPR)"
)
WEEKLY_TE = WeeklyMarketSeries(
    "wp", "weekly-te", "/nfl/rankings/ppr-te.php", ("TE",), "weekly TE (PPR)"
)
WEEKLY_K = WeeklyMarketSeries("wp", "weekly-k", "/nfl/rankings/k.php", ("K",), "weekly K")
WEEKLY_DST = WeeklyMarketSeries(
    "wp", "weekly-dst", "/nfl/rankings/dst.php", ("DST",), "weekly DST", team_coded=True
)
#: The ONLY weekly cross-position board that exists after 2020-10-12. It is a **superflex**
#: board -- read this module's docstring before using it as anything else.
WEEKLY_OVERALL_SUPERFLEX = WeeklyMarketSeries(
    "wsf",
    "weekly-op",
    "/nfl/rankings/ppr-superflex.php",
    ("QB", "RB", "WR", "TE"),
    "weekly overall (SUPERFLEX)",
)

ALL_WEEKLY_SERIES: tuple[WeeklyMarketSeries, ...] = (
    WEEKLY_QB,
    WEEKLY_RB,
    WEEKLY_WR,
    WEEKLY_TE,
    WEEKLY_K,
    WEEKLY_DST,
    WEEKLY_OVERALL_SUPERFLEX,
)

_POSITIONAL: dict[str, WeeklyMarketSeries] = {
    "QB": WEEKLY_QB,
    "RB": WEEKLY_RB,
    "WR": WEEKLY_WR,
    "TE": WEEKLY_TE,
    "K": WEEKLY_K,
    "DST": WEEKLY_DST,
}


def positional_series(position: str) -> WeeklyMarketSeries:
    """The dedicated weekly board for one position. Raises on an unknown position rather than
    defaulting, for D56's reason: a silently-substituted board is a wrong measurement that
    still produces a number."""
    try:
        return _POSITIONAL[position]
    except KeyError:
        known = ", ".join(sorted(_POSITIONAL))
        raise ValueError(f"no weekly board for position {position!r}; known: {known}") from None


def flex_reference_series() -> WeeklyMarketSeries:
    """The board a FLEX (RB/WR/TE) benchmark must be reconstructed from, with its QB rows
    dropped and the survivors re-ranked densely.

    Deliberately *not* called `weekly_flex_series`: there is no weekly FLEX series in the
    mirror, and naming this one as though there were is how a superflex measurement gets
    restated as a 1-QB one. See the module docstring for the measured support and the
    explicit limit of that support."""
    return WEEKLY_OVERALL_SUPERFLEX
