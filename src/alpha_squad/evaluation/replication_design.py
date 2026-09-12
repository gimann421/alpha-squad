"""Pre-registered designs for the O1 REPLICATION / POWER / GENERALISATION phases (D87-D90).

**Committed to git before the corresponding experiment's results were seen.**
D39/D54/D55/D63/D67/D79/D82/D83/D84/D85/D86 discipline.

Why this file exists separately from `objective_candidates`
-----------------------------------------------------------
D86 pre-registered the *candidate* (O1) and the *gates*. D87/D88/D89 propose no candidate and no
gate: each is a replication of the **same** O1 at a different sample size or cost approximation.
That is a different kind of pre-registration, and keeping it in its own file makes one thing
mechanically checkable: **the only field that may differ between these designs is sample size (or,
for D87, an explicitly-labelled cost approximation).** `tests/unit/test_replication_design.py`
asserts exactly that, so a phase cannot quietly become a new experiment while still calling itself
a replication.

The gates are **not** restated here. They are imported from `objective_candidates`, which imports
them from D84's `decision_value_base`, so no phase in this lineage can adopt a friendlier bar.

The lineage
-----------
    D86  4 slots, 2021-2025, full board      -> target +52.9 primary; legacy +1.6
    D87  4 slots, 2021-2025, K=10 shortlist  -> a COST approximation, and it MEASURED A DIFFERENT
         POLICY: the shortlist is ranked by Y1, so it re-imports Y1's K/DST bias. 10.3% of
         decisions changed, 0% in rounds 1-7 and 18.3% in rounds 8-16. Recorded here as the
         reason `shortlist_k` must stay `None` in every later phase.
    D88  10 slots, 2021-2025, full board     -> target +50.5, CI [-5.5, +106.6]. The effect
         replicated at 2.5x the data, and the MDE was shown to ASYMPTOTE at ~56 points as slots
         -> infinity, because between-season variance is irreducible at 5 clusters.
    D89  10 slots, 2020-2025, full board     -> target +49.0, CI [+6.5, +91.5]. SIX seasons
         resolved the target-format effect: the CI excludes zero and all nine in-format gates
         pass. The blocker moved to G7 -- target +49.0 vs legacy -2.3, opposite signs.
    D90  10 slots, 2020-2025, full board, a THIRD LEAGUE FORMAT -> THIS PHASE. Nothing about O1
         or the gates changes; only the league config does.

Why D90 changes the format rather than the sample (Phase 1)
------------------------------------------------------------
D89 left exactly one ambiguity. O1's principal observed mechanism is reducing excessive K/DST
drafting and spending the picks on flex-eligible depth. The legacy format **cannot exercise that
mechanism at all**, and D90 measured that it fails for TWO independent reasons, not one:

  * its lineup has no K and no DEF slot (`positional_capacity` is literally 0 for both, and both
    arms drafted zero of each in all 100 D89 drafts); and
  * its market board has no K and no DST **players** -- `dsf` carries 0 kicker and 0 defense rows
    across 2021-2025, because FantasyPros' superflex ("OP") pages rank offensive players only.

So G7's failure is consistent with two very different worlds: O1 is a target-format artifact, or
legacy was never able to test it. A format in which the mechanism CAN operate separates them.

The candidate set is closed, not a matter of taste. `market/series.py` derives the board from
is_dynasty x is_superflex, giving exactly four series, two of which are already used:

    ro  redraft 1QB        <- target_league
    dsf dynasty superflex  <- legacy_2qb_dynasty
    rsf redraft superflex  <- candidate; 5 historical seasons; **0 K and 0 DST rows**
    do  dynasty 1QB        <- candidate; 6 historical seasons; 1,533 K and 1,494 DST rows

`do` wins criterion 1 (most complete historical seasons) outright and is the only candidate whose
board can express the mechanism at all. Selection was forced by data, before any result.

Why 2020 and not 2019 -- and why 2020 is TARGET-ONLY (Phase 1)
---------------------------------------------------------------
**A season's usability is a property of (format, season), not of the season.** The two shipped
formats resolve to different market series: the target format to `ro` (redraft overall) and the
legacy format to `dsf` (dynasty superflex). D89's first Phase 1 pass checked only `ro` and
concluded "2020 is comparable"; that conclusion is correct for the target format and **was wrong
for the legacy format**, which the run itself exposed by reporting `board=None`. The `dsf` series'
earliest scrape of ANY kind is **2020-10-16** -- 2020 has 3,246 `dynasty-op` rows, all of them
October-December, and **zero** in the July/August preseason window. There is no dynasty-superflex
preseason board in 2020 to resolve to, so `legacy_2qb_dynasty` runs on **2021-2025 (5 clusters)**
while `target_league` runs on **2020-2025 (6 clusters)**. See `EXCLUDED_SEASONS`.

`preseason_page_type` resolves the board each season actually published in July/August rather than
assuming one. Under that resolution, for the TARGET format's series:

  * **2020 is comparable.** 612 projected board players (2021-2025: 602-651), 74.8% market
    coverage (76.2-85.5%), 17,269 weekly rows (17,271-17,968), weeks 1-17, best kicker at overall
    market rank 175.4 (173.9-189.8), best DST at 146.2 (149.8-161.9), mean measured availability
    89.7% (88.3-89.7%), consumption demand QB 2.0 / RB 4.8 / WR 5.2 / TE 2.0 / K 1.0 / DST 1.0
    (all inside the 2021-2025 range). Every one of those numbers is produced by the SAME code
    path as every other season.
  * **2019 is not, and is excluded.** 174 projected board players and **0% market coverage** --
    there is no preseason board at all, so the fair-market opponent would have nothing to draft
    against, and the implied demand degenerates (K 3.3, DST 3.0). Excluded on the data, not on a
    preference.

THE ONE KNOWN ASYMMETRY, recorded in advance so it cannot be discovered afterwards
----------------------------------------------------------------------------------
2020 was a 16-game / 17-week regular season; 2021 onward are 17-game / 18-week. `FANTASY_WEEKS`
is 1-17 for **every** season and is not changed for 2020 -- so weeks 1-17 covers all of 2020 and
excludes 2021+'s final week. This is the pre-existing D86 definition applied unchanged, not a
2020-specific one. It is **paired**: both arms in a season see exactly the same weeks, so it
cannot bias the difference. It can only affect the season's level, which the paired design
differences out.

A defect this phase fixed before running (and which changes no production behaviour)
-------------------------------------------------------------------------------------
`market/series.py` maps the target format to `ecr_type='ro'`, and the harness previously assumed
`page_type='redraft-overall'`. 2020 published its preseason board under **`redraft-offense`**;
its `redraft-overall` rows exist (4,922) but are **all in-season**, i.e. future information
relative to a draft. Taking the default would have produced an EMPTY preseason board for 2020 and
a fair-market opponent drafting in alphabetical order. `preseason_page_type` resolves it from the
data instead. 2021-2025 and 2026 resolve to `redraft-overall` -- unchanged, and asserted so.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_squad.evaluation.objective_candidates import (
    MAX_SEASON_LONG_REGRESSION,
    MAX_WORSE_SEASONS,
    METRICS,
    MIN_STARTER_POINT_GAIN,
    PREREGISTERED_CONTROL,
    PREREGISTERED_FORMATS,
    PRIMARY_METRIC,
)


@dataclass(frozen=True)
class ReplicationDesign:
    """One replication of D86's O1. Everything except `seasons`, `slots` and `shortlist_k` is
    fixed across the lineage, and the test module asserts it."""

    phase: str
    seasons: tuple[int, ...]
    slots: tuple[int, ...]
    #: `None` means the FULL candidate board. Any integer is a cost approximation that D87 showed
    #: measures a different policy; it must never be set in a power/replication phase.
    shortlist_k: int | None
    formats: tuple[str, ...] = PREREGISTERED_FORMATS
    control: str = PREREGISTERED_CONTROL
    treatment: str = "O1"
    primary_metric: str = PRIMARY_METRIC
    metrics: tuple[str, ...] = METRICS
    opponent: str = "market_consensus_roster_aware"
    #: The estimator uses common random numbers keyed on a non-salted hash of `player_id`, so
    #: there is no seed to set and repeated runs are bit-identical.
    randomization: str = "common random numbers keyed on player_id; deterministic, no seed"

    def seasons_for(self, fmt: str) -> tuple[int, ...]:
        """The nominal seasons minus any excluded for THIS format on measured data grounds.

        A season is not excluded globally: 2020 has a usable preseason board in the target
        format's series and none at all in the legacy format's (see `EXCLUDED_SEASONS`), so the
        two formats legitimately run on different numbers of clusters."""
        return tuple(s for s in self.seasons if (fmt, s) not in EXCLUDED_SEASONS)

    def paired_observations(self, fmt: str) -> int:
        return len(self.seasons_for(fmt)) * len(self.slots)

    def clusters(self, fmt: str) -> int:
        return len(self.seasons_for(fmt))

    def drafts(self) -> int:
        """Both arms, every format."""
        return sum(self.paired_observations(f) for f in self.formats) * 2


D87_SHORTLIST = ReplicationDesign(
    phase="D87", seasons=(2021, 2022, 2023, 2024, 2025), slots=(1, 4, 7, 10), shortlist_k=10
)

D88_TEN_SLOTS = ReplicationDesign(
    phase="D88",
    seasons=(2021, 2022, 2023, 2024, 2025),
    slots=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    shortlist_k=None,
)

#: D89. The ONLY difference from D88 is the 2020 season. Asserted by test.
D89_SIX_SEASONS = ReplicationDesign(
    phase="D89",
    seasons=(2020, 2021, 2022, 2023, 2024, 2025),
    slots=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    shortlist_k=None,
)

#: D90. A CROSS-FORMAT generalisation test, not a new candidate and not a new gate. O1 is run
#: exactly as D89 ran it; the only thing that changes is which league config it drafts for.
#:
#: The format was selected by the pre-specified rule below, before any D90 result was examined.
#: `market/series.py` derives the board from is_dynasty x is_superflex, so the deployment has
#: exactly four possible series and two are already used -- the candidate set is CLOSED at
#: {redraft superflex (`rsf`), dynasty 1QB (`do`)}. Measured on the real snapshot:
#:
#:   criterion 1, most complete historical seasons:  do = 6 (2020-2025), rsf = 5 (2021-2025).
#:                                                   `rsf`'s earliest scrape is 2021-01-01.
#:   criterion 5, valid draft board:                 `do` carries 1,533 K and 1,494 DST rows
#:                                                   across 2021-2025. **`rsf` carries ZERO of
#:                                                   each** -- the superflex ("OP") pages rank
#:                                                   offensive players only. A lineup that must
#:                                                   start a K and a DEF cannot be drafted
#:                                                   against a board containing neither.
#:
#: `do` wins criterion 1 outright and is the only candidate with a board that can express the
#: mechanism at all. Selection was forced by data, not preference.
D90_THIRD_FORMAT = ReplicationDesign(
    phase="D90",
    seasons=(2020, 2021, 2022, 2023, 2024, 2025),
    slots=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    shortlist_k=None,
    formats=("dynasty_1qb",),
)

ACTIVE_DESIGN = D90_THIRD_FORMAT

#: Every league format any phase in this lineage has benchmarked. Used to validate that an
#: exclusion names a real format; not itself a design field.
KNOWN_FORMATS: tuple[str, ...] = (*PREREGISTERED_FORMATS, "dynasty_1qb")

#: (format, season) cells excluded from the benchmark universe, with the MEASURED reason.
#: Append-only. Exclusion is per-format because the two formats resolve to different market
#: series -- `ro` (redraft overall) and `dsf` (dynasty superflex) -- whose historical coverage
#: differs. A season usable in one is not automatically usable in the other, and D89 learned
#: that the hard way.
EXCLUDED_SEASONS: dict[tuple[str, int], str] = {
    ("target_league", 2019): (
        "no preseason market board: 174 projected board players and 0% market-rank coverage under "
        "the resolved preseason page_type, so the fair-market opponent has nothing to draft "
        "against and the implied consumption demand degenerates (K 3.3, DST 3.0)."
    ),
    ("legacy_2qb_dynasty", 2019): (
        "the `dsf` series does not exist in 2019 -- its earliest scrape of any kind is 2020-10-16."
    ),
    ("dynasty_1qb", 2019): (
        "no preseason board: the `do` series has no July/August rows in 2019 at all "
        "(`preseason_page_type` returns None), so there is nothing for the fair-market opponent "
        "to draft against. 2020 IS usable for this format -- its board is published under "
        "`dynasty-offense` (3,026 preseason rows, 68.5% coverage), the same page_type relabelling "
        "D89 found for the target format's 2020."
    ),
    ("legacy_2qb_dynasty", 2020): (
        "NO PRESEASON BOARD EXISTS. The legacy format resolves to ecr_type `dsf` (dynasty "
        "superflex), whose first scrape of any kind is 2020-10-16: 2020 holds 3,246 `dynasty-op` "
        "rows, ALL of them in October-December, and ZERO in the July/August preseason window. "
        "`preseason_page_type` therefore returns None and the board comes back empty, which would "
        "make the nine fair-market opponents draft ALPHABETICALLY. The October rows cannot be "
        "substituted: they are in-season and reading them would leak market movement that "
        "happened after the draft (the D54 defect). No page_type resolution can recover a board "
        "that was never published, so the legacy 2020 cell is dropped rather than manufactured. "
        "Recorded BEFORE any legacy 2020 outcome was examined. The target format is unaffected -- "
        "its `ro` series has 3,462 preseason rows in 2020 under `redraft-offense`."
    ),
}

#: D90's predictions, recorded before the third format was run. Same status as R1-R6: NOT gates,
#: and each states its own failure mode so the result cannot be reinterpreted afterwards.
D90_PREDICTIONS: dict[str, str] = {
    "T1": (
        "The `do` board differs enough from `ro` that Y1's own drafts differ materially between "
        "the two formats -- different opponent order, different market ranks. If Y1's dynasty_1qb "
        "rosters came out near-identical to its target_league rosters, this would not be an "
        "independent test and the phase would have to say so rather than count it as one."
    ),
    "T2": (
        "MECHANISM: O1 drafts FEWER kickers than Y1 in dynasty_1qb, as it does in target_league "
        "(3.45 -> 2.52). This is the thing the format was chosen to make testable. If the "
        "mechanism does NOT appear here -- on a board that carries 1,533 K and 1,494 DST rows "
        "and a lineup with K and DEF slots -- then D89's G7 failure is a genuine cross-format "
        "weakness and O1 should close, not ship."
    ),
    "T3": (
        "EFFECT: no specific magnitude is predicted, and none is required. The target format's "
        "+49.0 is not a target to hit. What matters is the SIGN and whether the pre-registered "
        "gates pass on their own terms. A dynasty board prices youth, so its K/DST ranks sit "
        "later (best K 184-251 vs 173-190), which could make Y1 hoard kickers either more or "
        "less than in the target format; both directions are consistent with the mechanism."
    ),
    "T4": (
        "POWER: with 6 clusters and a between-season SD in the target format's range (~40), the "
        "MDE will land near ~45. An effect materially smaller than that will NOT be resolvable, "
        "and the honest report in that case is 'mechanism present, effect unresolved' -- which "
        "is a different finding from 'mechanism absent'. These two must not be conflated."
    ),
    "T5": (
        "G7 IS NOT REDEFINED BY THIS PHASE. D86's rule is that a candidate must clear every "
        "gate. If dynasty_1qb reproduces the mechanism and the effect, that is evidence about "
        "WHY legacy is null -- it does not retroactively convert legacy's null into a pass. Any "
        "claim that G7 is satisfied must be argued against the gate's original text and flagged "
        "as a judgement, never asserted by arithmetic."
    ),
    "T6": (
        "SCOPE LIMIT, recorded so it cannot be quietly dropped: `is_dynasty` is consumed only by "
        "`market/series.py`, and dynasty_1qb's lineup is IDENTICAL to target_league's. So D90 "
        "varies the consensus board and everything downstream of it, and does NOT vary the "
        "lineup shape. A positive result is evidence that O1 survives a different board -- not "
        "yet that it survives a different roster structure."
    ),
}

#: Recorded before the run so the result cannot be reinterpreted afterwards. These are NOT gates;
#: the gates are D84's, imported unchanged via `objective_candidates`.
PREDICTIONS: dict[str, str] = {
    "R1": (
        "The 2021-2025 subset reproduces D88 BIT-IDENTICALLY, not merely 'within tolerance'. The "
        "harness is deterministic and `preseason_page_type` resolves those seasons to the same "
        "board the default assumed. Anything else is a defect, not stochastic variation, and "
        "Phase 4 stops the phase if it appears."
    ),
    "R2": (
        "MDE falls from ~56 to roughly 47 IF 2020's paired difference lands near the existing "
        "between-season spread. It does NOT fall if 2020 is an outlier: one extreme cluster can "
        "raise the between-season SD enough to cancel the gain from t(df=5) < t(df=4). Both "
        "outcomes are registered in advance as real possibilities."
    ),
    "R3": (
        "The point estimate moves by less than the between-season SD/sqrt(6) ~ 18 points. A "
        "replication that moves the estimate more than that is evidence of instability, not of a "
        "better measurement."
    ),
    "R4": (
        "The K/DST mechanism holds in 2020 (fewer kickers drafted under O1). 2020's board has 42 "
        "kickers at best rank 175.4, squarely in family, so there is no structural reason for it "
        "not to. If the mechanism reverses in 2020 specifically, that is a finding about the "
        "mechanism and must be reported as one, not averaged away."
    ),
    "R5": (
        "The most likely single outcome remains VERDICT B (promising but unresolved), because the "
        "effect (~50) and the six-season MDE (~47) are within a few points of each other and the "
        "sign of that gap is decided by 2020's cluster alone. A ~3-point margin either way is not "
        "a resolution; the economic and stability criteria must carry the decision, per the brief."
    ),
    "R6": (
        "Legacy 2QB remains an effective null. Its lineup has no K or DEF slot for O1's mechanism "
        "to act on, so a large legacy effect in EITHER direction would indicate a harness problem "
        "rather than a finding."
    ),
}

__all__ = [
    "ACTIVE_DESIGN",
    "D87_SHORTLIST",
    "D88_TEN_SLOTS",
    "D89_SIX_SEASONS",
    "D90_PREDICTIONS",
    "D90_THIRD_FORMAT",
    "EXCLUDED_SEASONS",
    "KNOWN_FORMATS",
    "MAX_SEASON_LONG_REGRESSION",
    "MAX_WORSE_SEASONS",
    "MIN_STARTER_POINT_GAIN",
    "PREDICTIONS",
    "ReplicationDesign",
]
