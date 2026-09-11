"""Pre-registered designs for the O1 REPLICATION / POWER phases (D87, D88, D89).

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
    D89  10 slots, 2020-2025, full board     -> THIS PHASE. Adds the one remaining usable season.

Why 2020 and not 2019 (Phase 1, decided on measured data before the run)
------------------------------------------------------------------------
`preseason_page_type` resolves the board each season actually published in July/August rather than
assuming one. Under that resolution:

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

    @property
    def paired_observations(self) -> int:
        return len(self.seasons) * len(self.slots)

    @property
    def clusters(self) -> int:
        return len(self.seasons)

    @property
    def drafts(self) -> int:
        """Both arms, both formats."""
        return self.paired_observations * 2 * len(self.formats)


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

ACTIVE_DESIGN = D89_SIX_SEASONS

#: Seasons excluded from the benchmark universe, with the measured reason. Append-only.
EXCLUDED_SEASONS: dict[int, str] = {
    2019: (
        "no preseason market board: 174 projected board players and 0% market-rank coverage under "
        "the resolved preseason page_type, so the fair-market opponent has nothing to draft "
        "against and the implied consumption demand degenerates (K 3.3, DST 3.0)."
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
    "EXCLUDED_SEASONS",
    "MAX_SEASON_LONG_REGRESSION",
    "MAX_WORSE_SEASONS",
    "MIN_STARTER_POINT_GAIN",
    "PREDICTIONS",
    "ReplicationDesign",
]
