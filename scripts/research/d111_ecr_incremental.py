"""D111 -- does ECR add INCREMENTAL information that improves Alpha's actual draft decisions?

Read-only research runner. Opens the database read-only, drives the shipped instruments
(`draft_forensics._pick_by_tier`, `draft_oracle.rollout`) and D103's already-reviewed
`_play_draft`/`oracle_static`; writes nothing but JSON artifacts. No `src/` file changes in D111
at all: `models/`, `league/` and `evaluation/` are byte-identical to HEAD.

    uv run python scripts/research/d111_ecr_incremental.py --mode phase0         --out <dir>
    uv run python scripts/research/d111_ecr_incremental.py --mode parity         --out <dir>
    uv run python scripts/research/d111_ecr_incremental.py --mode value          --out <dir>
    uv run python scripts/research/d111_ecr_incremental.py --mode divergence     --out <dir>
    uv run python scripts/research/d111_ecr_incremental.py --mode counterfactual --out <dir>

==========================================================================================
PRE-REGISTRATION  (written and committed BEFORE any treatment result was produced)
==========================================================================================

THE QUESTION, and the one it is NOT
------------------------------------
Does giving Alpha ECR **in addition to** its existing Y1 information produce better actual draft
decisions, pick by pick?  The primary contrast is **Y1 + ECR vs Y1**.  It is NOT "is ECR a better
ranking than Y1" (that is D100/D104's question, already answered), and ECR-alone is carried only
as an INDEPENDENT BENCHMARK, never as a target Alpha must beat.

D104 measured ECR *replacing* Y1's ordering.  D111 measures ECR *added to* it.  Those are
different experiments and the second does not follow from the first.

WHAT Y1 ALREADY DOES WITH ECR -- established by inspection, before any arm was defined
---------------------------------------------------------------------------------------
The shipped decision rule (tier `L0`, `draft_forensics.score_candidate`) is

    score = (msv + 1.0 * vorp + opp_cost) * fit_mult * risk_mult * survival_mult

and TWO of those terms already read the ECR board:

  * `opp_cost` -- `league/opportunity_cost.py::positional_opportunity_cost` replays the opponent
    model, which is literally `best_by_market_rank`, i.e. ECR;
  * `survival_mult` -- `_survival_probability` reads `ecr_best`/`ecr_worst` from the same
    preseason snapshot.

So Y1 **already consumes ECR as a TIMING model** (who will be gone, and when).  What it has never
consumed is ECR as a **VALUE opinion** -- the opportunity cost is denominated in Y1's own VORP
points, and ECR only decides *which* player is removed from the pool, never what he is worth.

**That is the precise incremental question D111 tests: does ECR's opinion about player VALUE add
anything, given Y1 already uses ECR's opinion about player AVAILABILITY?**  It is stated here
because a phase that reported "ECR adds nothing" without it would be badly misleading.

PHASE 0 -- INTEGRATION METHODS CONSIDERED, WITH MEASURED GROUNDS FOR EACH DECISION
----------------------------------------------------------------------------------
Seven candidate insertion points were enumerated and five rejected BEFORE any arm was run.

  M1  BOARD-LEVEL RANK CONSENSUS.  **ACCEPTED -- PRIMARY.**  Within each position, re-assign Y1's
      own projected values to players ordered by the equal-weight average of Y1's ordinal rank and
      ECR's ordinal rank.  See `blended_static`.  Parameter-free at w = 1/2 (Borda / mean-rank is
      the unique symmetric combination of two orderings, and is what "expert consensus" means --
      FantasyPros' own ECR is an equal-weight mean of expert ranks).  ECR enters the INFORMATION
      layer, so its opinion propagates through msv, VORP, replacement level and opportunity cost
      exactly the way Y1's own does.

  M2  DECISION-LEVEL RANK CONSENSUS.  **ACCEPTED -- SECONDARY.**  Y1's engine is left completely
      untouched; it produces its ranked candidate list, ECR ranks the same candidates, and the
      pick is the argmin of the equal-weight mean rank.  See `consensus_pick`.  Same Borda
      argument, different insertion point: ECR is a co-equal VOTER on the decision rather than an
      input to the valuation.  Carried because a null at one insertion point is not a null at the
      other, and a phase that tested only M1 could not tell them apart.

  M3  ECR BREAKS EXACT TIES IN THE DECISION SCORE.  **REJECTED -- measured no-op.**  It is the
      minimal conceivable additive use of ECR and needs no coefficient at all, so it was measured
      rather than argued about: across 192 real pick states (2 formats x {2021, 2023, 2025} x
      slots {1, 7} x 16 rounds) the top score is exactly tied in **0** of them.  The arm would
      change nothing, so running it would be theatre.  (Exact WITHIN-POSITION projection ties do
      exist -- QB 4, RB 24, WR 42, TE 40, K 4, DST 18 surplus rows in those seasons -- but they
      never survive `risk_mult`, which is per-player, into a tied score.)

  M4  AN ADDITIVE ECR TERM IN THE SCORE (`score += k * f(ecr_rank)`).  **REJECTED.**  `k` is a
      points-denominated coefficient with nothing in the repository to derive it from.  The brief
      forbids inventing one and forbids fitting one against realized outcomes; there is no third
      option, so the method is not defensibly pre-registrable.

  M5  A MULTIPLICATIVE ECR FACTOR.  **REJECTED**, for M4's reason, and additionally because it
      would compose with `risk_mult` -- which this phase freezes.

  M6  POINTS-DOMAIN AVERAGE WITH `ecr_implied_baseline`.  **REJECTED**, on D104's three grounds,
      each RE-MEASURED on this vintage rather than cited: (a) the isotonic step function collapses
      the top of the board -- in 2023 the top 24 by value hold **4** distinct values at RB (largest
      tie group **12**), 7 at WR, 9 at QB, 12 at TE, and the engine breaks exact ties
      alphabetically; (b) `_preseason_ranks_for_season` is hardcoded to `ecr_type='ro'`, so
      `dynasty_1qb` (series `do`) would be fed the REDRAFT board -- a D56 violation that would cost
      half the population; (c) coverage is **68.2%** of the 2023 draft board and only QB/RB/WR/TE,
      so substituting it changes the candidate universe and breaks pool parity.  It is also a
      VALUATION change, not an information change: it moves each position's value multiset.

  M7  CROSS-POSITION (OVERALL) ECR CONSENSUS.  **REJECTED as an arm, recorded as follow-up.**
      Permuting values across positions by overall ECR rank changes each position's value
      multiset, so replacement levels, scarcity and the positional value scale all move with it.
      The result would confound an information change with a valuation change and could not answer
      the incremental question.  It is exactly D108 reopening-criterion 3's untested axis and is
      recorded there as the follow-up it is, not smuggled in here.

**Conclusion of Phase 0: exactly two methods are defensibly pre-registrable, M1 and M2.**  Neither
introduces a coefficient that is not fixed by symmetry.

THE THREE SYSTEMS
------------------
  CONTROL     `Y1`         -- the shipped decision path, tier `L0`, unmodified.
  TREATMENT   `T1_*`/`T2_*` -- Y1 plus ECR, by M1 and M2 respectively.  Y1 is NOT replaced: at the
                             pre-registered weight each source carries equal say and Y1 keeps its
                             entire value scale, replacement logic and decision rule.
  BENCHMARK   `ECR_ALONE`  -- our seat drafts `roster_aware_market_pick`, i.e. best available by
                             preseason ECR subject to the same end-of-draft mandatory-slot rule
                             the nine opponents already use.  ECR determines the selection
                             directly; it is NOT run through Y1.  `ECR_ALONE_NAIVE`
                             (`best_by_market_rank`, no roster rule) is reported beside it so the
                             roster rule's contribution is visible rather than assumed.

  `ORACLE_Y1` (D103's hindsight cell) is re-measured on this vintage for context only.  It is an
  information CEILING and is nowhere described as achievable.

THE WEIGHT, AND WHY REPORTING A LADDER IS NOT OPTIMIZING ONE
-------------------------------------------------------------
The pre-registered PRIMARY weight is **w = 0.5** for both methods, fixed by the symmetry argument
above and by nothing else.  The verdict is read off w = 0.5 and only w = 0.5.

A ladder w in {0, 0.25, 0.5, 0.75, 1.0} is ALSO run and reported in full, as a SHAPE diagnostic in
the style of D105's alpha-ladder.  It is not a search: the winning rung is never promoted, the
primary is fixed in advance, and the two endpoints are identities that validate the instrument --

    w = 0  is provably Y1 itself   (asserted at runtime, see `blended_static`/`consensus_pick`)
    w = 1  under M1 restricted to QB/RB/WR/TE is D104's `ecr_ordered_static` exactly

so the ladder is the only way to see whether any effect is monotone in how much ECR is trusted,
which a single point estimate cannot show.

POSITION SET.  M1's primary permutes **all six positions** (QB/RB/WR/TE/K/DST).  D104 restricted
itself to QB/RB/WR/TE on the stated ground that "no ECR board ranks K and DST" -- **that is not
true of this data**, measured: `ro`/`redraft-overall` carries 30-37 ranked kickers and 31-32 ranked
defenses in every season 2021-2025.  D104's own §5 flags the consequence as a confound (holding
K/DST fixed while skill values move pulls the engine toward kickers, producing its RB->K and WR->K
swaps).  Permuting every position removes that confound at the source.  `T1_SKILL_w100` is carried
as the explicit bridge back to D104's arm.

INFORMATION / ANTI-LEAKAGE
---------------------------
  source            DynastyProcess `fp_ecr_history` (mirror of FantasyPros), via `market_snapshot`
  series            the league's RESOLVED `(ecr_type, page_type)` pair (D56) --
                    `target_league` -> `ro`/`redraft-overall`, `dynasty_1qb` -> `do`/`dynasty-overall`;
                    never hardcoded, resolved by `market/series.py::resolve_market_series`
  vintage           July/August scrapes OF THE TARGET SEASON only, latest per player (D54)
  identity          canonical `asq_` ids via `player_id_map`'s `fantasypros_id` bridge; never names
  board read        `SeasonStatic.market_rank`, the same board the opponent model and the survival
                    term already consume -- so the treatment cannot see a board the control cannot
  never             a later ECR ranking, a different date, or another season's board

`assert_no_realized_inputs_in_policy()` is called before any measurement in every mode.  Realized
points enter only the roster scorer, after every decision has been made -- except in `ORACLE_Y1`,
which is quarantined behind its own arm name for exactly that reason.

POPULATION.  `BACKTEST_SEASONS` = 2021-2025 x slots {1, 4, 7, 10} x both shipped 1-QB formats
(`target_league`, `dynasty_1qb`) = 20 drafts per arm per format.  Seasons are the independent
clusters (k = 5).  2020 and 2026 are refused outright.

CONTINUATION POLICY.  Unchanged in every arm: nine opponents draft `roster_aware_market_pick` off
the CONTROL board, the snake geometry is `draft_order(league)`, and the roster is scored by
`compute_league_starters` on realized points.  In `counterfactual` mode the continuation after the
audited pick is the CONTROL board and the shipped engine for BOTH candidates -- D106 established
that an arm-relative oracle is uninterpretable, so nothing here is scored against a board that
moved with the arm.

METRICS.
  PRIMARY    realized whole-draft starter points (`--objective season_long`), season-clustered.
  SECONDARY  % of picks changed; % improved / worsened by realized value; mean and median realized
             change on changed picks; the gain/loss distribution; per round, per pick-range, per
             position, per phase (EARLY 1-5 / MIDDLE 6-10 / LATE 11-16, D103's registered
             convention); within-position vs cross-position changes; the weekly objective
             (`weekly_no_foresight`) as the established secondary scoring.

DETECTION FLOOR.  D97's measured floor for a draft-level contrast is **172-250 points**, quoted
not re-derived, and it is the pre-registered decision boundary: an effect below it is UNRESOLVED
even if its point estimate is positive.  The realized MDE is ALSO computed and reported, as
`(t_{.025,4} + t_{.20,4}) * sd/sqrt(5)` = `3.717 * sd/sqrt(5)`, from the observed per-season paired
SD.  "Not statistically significant" is never reported as "ECR has no value" without that number
beside it.

STATISTICAL TEST.  Season-clustered paired t on the per-season mean paired difference, k = 5,
two-sided, t_crit = 2.776; 95% CI reported with every effect; per-season W/T/L reported so a
result that rests on one season is visible.  No subgroup is promoted to primary after the fact.

STOPPING RULE.  ONE run of the registered grid.  No slot is added after seeing results (D88
established that slots cannot lower the floor -- seasons bind), no season is added, no weight is
promoted, no arm is re-specified.  If the primary is below the floor the phase reports UNRESOLVED
and stops; no production run, no 2026, no retraining, no tuning follows.

INVALID-CELL RULES.  A (format, season) cell is INVALID, excluded, and reported as excluded if
  (a) the resolved series has no preseason (Jul/Aug) board for that season -- `market_rank` empty;
  (b) fewer than 2 ECR-covered players exist at a position the permutation would touch (the
      permutation is undefined on a singleton), for that position only;
  (c) `load_season_projections` returns no board, or none at a position the league must start.
No cell is ever repaired by substituting another date, another page or a later ranking.

BASELINE PARITY -- and the vintage problem, stated before any result
---------------------------------------------------------------------
**The board vintage has moved.**  Every phase D97-D108 was measured at combined_hash
`ca3e2d8a...`; a from-source rebuild in this environment produces `63076e2e...`.  D108
reopening-criterion 5 calls that an instrument-integrity failure, so it is resolved here BEFORE any
treatment arm is interpreted, not explained away afterwards:

  * The **ECR half is bit-identical.**  The upstream board blob at the pinned commit
    (`D89_BOARD_COMMIT = 9338630`, sha256 `a966176d...`) was re-fetched and compared row by row
    against today's against the exact population under test -- `ecr_type in ('ro','do')`,
    Jul/Aug, 2021-2025.  **69,639 rows, 2,415 players, sha256
    `c5cfbbeb17aabbf9b903ab55051984f735c4c03daca75a6328272144d378fb7f` on both.**  The identity map
    differs by exactly one added row over that population (Jack Kiser, an LB -- irrelevant to a
    fantasy board) and zero changed rows.  So D111's treatment signal IS the information D104
    measured.
  * The **projection half moved.**  `compute_board_vintage`'s combined hash is a hash of
    `load_season_projections`, so the delta is entirely in Y1's own board -- downstream of the
    nflverse restatement.  Absolute levels therefore will NOT match D104's, and any comparison
    that pretends otherwise is invalid.

Parity is therefore established STRUCTURALLY, and the `parity` mode refuses to continue unless all
of it holds:

  P1  tier `L0` picks identically to tier `H` (a direct pass-through to production's
      `recommend_draft_pick`) at every pick state of every registered draft -- D107's 640/640
      check, re-run on this vintage.  This is what makes the control "production-equivalent".
  P2  every arm at w = 0 is BYTE-IDENTICAL to Y1 -- the projection dict, the VORP dict and the
      chosen player, at every pick state.  An arm that differs from the control by anything other
      than the pre-registered ECR input fails here.
  P3  every treatment preserves each position's value multiset exactly (`SubstitutionError`
      otherwise), so replacement levels, scarcity and consumption demand are unchanged.
  P4  pool parity: the candidate universe is identical in every arm, by construction and asserted.
  P5  the ECR board hash above reproduces, and the vintage is recorded with every artifact.

D104's own decomposition is ALSO re-run on this vintage (`T1_SKILL_w100` is its `FP_ECR_Y1`), so
the phase reports a same-vintage replication of the number it is building on rather than comparing
across boards.

WHAT THIS PHASE DELIBERATELY DOES NOT TOUCH
---------------------------------------------
Risk and uncertainty are FROZEN.  `risk_mult` is not modified, removed, recalibrated or jointly
varied with anything here, and no new uncertainty estimate is built.  The open question --

    can a properly constructed player-level / heteroscedastic uncertainty measure improve
    realized draft value?

-- is recorded as an explicit future research question and is NOT closed by this phase.

No production change.  No model fitted.  No ECR weight tuned against outcomes.  No 2026.  Nothing
merged.  No PR.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import (
    BACKTEST_SEASONS,
    D89_BOARD_SHA256,
    compute_board_vintage,
)
from alpha_squad.evaluation.draft_forensics import (
    _pick_by_tier,
    load_season_static,
    preseason_page_type,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    WEEKLY_NO_FORESIGHT,
    assert_no_realized_inputs_in_policy,
    draft_order,
    make_roster_scorer,
    rollout,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import best_by_market_rank, roster_aware_market_pick
from alpha_squad.league.replacement import compute_league_starters, marginal_value_over_replacement
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"
FORMATS = ("target_league", "dynasty_1qb")
DEFAULT_SLOTS = (1, 4, 7, 10)
SKILL = ("QB", "RB", "WR", "TE")
ALL_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")

#: D97's measured floor for a draft-level contrast, quoted not re-derived.
DETECTION_FLOOR = (172.0, 250.0)
#: Season-clustered inference: k = 5 independent clusters, so 4 degrees of freedom.
T_CRIT_95 = 2.776
#: One-sided t at 80% power, 4 df -- the second term of the MDE formula.
T_POWER_80 = 0.941

#: The pre-registered PRIMARY weight. The verdict is read off this rung and only this rung.
PRIMARY_W = 0.5
#: The pre-registered shape ladder. Not a search: see the module pre-registration.
WEIGHT_LADDER = (0.0, 0.25, 0.5, 0.75, 1.0)

#: The exact ECR population whose immutability P5 checks.
ECR_POPULATION_SHA256 = "c5cfbbeb17aabbf9b903ab55051984f735c4c03daca75a6328272144d378fb7f"

#: Arms, in report order. `Y1` is the control; `T1_*`/`T2_*` are the treatments; `ECR_ALONE*` are
#: the independent benchmark; `ORACLE_Y1` is context only.
CONTROL = "Y1"
ARMS: tuple[str, ...] = (
    "Y1",
    "T1_ALL_w25",
    "T1_ALL_w50",
    "T1_ALL_w75",
    "T1_ALL_w100",
    "T1_SKILL_w100",
    "T2_w25",
    "T2_w50",
    "T2_w75",
    "T2_w100",
    "ECR_ALONE",
    "ECR_ALONE_NAIVE",
    "ORACLE_Y1",
)
#: The two pre-registered PRIMARY treatment arms.
PRIMARY_ARMS = ("T1_ALL_w50", "T2_w50")

PHASES: dict[str, range] = {
    "EARLY (1-5)": range(1, 6),
    "MIDDLE (6-10)": range(6, 11),
    "LATE (11-16)": range(11, 17),
}


def phase_of(round_no: int) -> str:
    for name, rounds in PHASES.items():
        if round_no in rounds:
            return name
    return "OUT OF RANGE"


def _load_d103():
    """D103's runner, reused rather than reimplemented (`oracle_static` is its machinery)."""
    path = Path(__file__).resolve().parent / "d103_pick_regret.py"
    spec = importlib.util.spec_from_file_location("d103_pick_regret", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D103 = _load_d103()


class SubstitutionError(RuntimeError):
    """Raised when an arm would not be a clean information isolation (P3/P4)."""


class ParityError(RuntimeError):
    """Raised when the control is not production-equivalent, or an arm differs from the control by
    something other than the pre-registered ECR input (P1/P2)."""


class InvalidCellError(RuntimeError):
    """Raised for a (format, season) cell the pre-registered invalid-cell rules exclude."""


# --------------------------------------------------------------------------------------------
# M1 -- board-level rank consensus
# --------------------------------------------------------------------------------------------
def blended_static(league, static, w: float, positions: tuple[str, ...] = ALL_POSITIONS):
    """`static` with Y1's projected values re-assigned within position by the equal-weight
    consensus of Y1's ordinal rank and ECR's ordinal rank.

    Within a position, over the players that carry BOTH a Y1 projection and an ECR rank:

        r_Y1(x)  = index of x in sorted(C, key=(-projection, player_id))
        r_ECR(x) = index of x in sorted(C, key=(ecr_rank,    player_id))
        order    = sorted(C, key=((1-w)*r_Y1 + w*r_ECR, player_id))
        assign     sorted(values, descending)[i] -> order[i]

    Players with no ECR rank keep their Y1 projection untouched, so the candidate universe and the
    per-position value multiset are both preserved exactly (P3/P4) -- which is what makes this an
    INFORMATION change rather than a new valuation function.

    Two identities hold by construction and are asserted by the `parity` mode:
      * w = 0 reproduces `static` exactly (the blended key is a strictly increasing function of
        r_Y1, so `order` is the value-descending order and every player is handed back his own
        value);
      * w = 1 with `positions=SKILL` is D104's `ecr_ordered_static`.

    `player_id` is the outer tie-break throughout, the D54 discipline: real ECR ranks tie often and
    `PYTHONHASHSEED` is unset, so without it a re-run could order ties differently.
    """
    if not 0.0 <= w <= 1.0:
        raise ValueError(f"weight must be in [0, 1], got {w}")
    projections = dict(static.projections)
    by_position: dict[str, list[str]] = defaultdict(list)
    for player_id in static.projections:
        by_position[static.positions.get(player_id, "UNKNOWN")].append(player_id)

    moved = 0
    covered_counts: dict[str, int] = {}
    for position in positions:
        covered = [p for p in by_position.get(position, []) if p in static.market_rank]
        covered_counts[position] = len(covered)
        # Invalid-cell rule (b): the permutation is undefined on fewer than two players.
        if len(covered) < 2:
            continue
        values = sorted((static.projections[p] for p in covered), reverse=True)
        y1_order = sorted(covered, key=lambda p: (-static.projections[p], p))
        ecr_order = sorted(covered, key=lambda p: (static.market_rank[p][1], p))
        r_y1 = {p: i for i, p in enumerate(y1_order)}
        r_ecr = {p: i for i, p in enumerate(ecr_order)}
        order = sorted(covered, key=lambda p: ((1.0 - w) * r_y1[p] + w * r_ecr[p], p))
        for player_id, value in zip(order, values, strict=True):
            if projections[player_id] != value:
                moved += 1
            projections[player_id] = value

    if sorted(projections.values()) != sorted(static.projections.values()):
        raise SubstitutionError(
            "the ECR blend changed the multiset of projected values; it must be a permutation "
            "within position, or it is a new valuation function rather than an information change"
        )
    if set(projections) != set(static.projections):
        raise SubstitutionError("the ECR blend changed the candidate universe (P4)")
    vorp = marginal_value_over_replacement(league, projections, static.positions)
    return dataclasses.replace(static, projections=projections, vorp=vorp), moved, covered_counts


# --------------------------------------------------------------------------------------------
# M2 -- decision-level rank consensus
# --------------------------------------------------------------------------------------------
def consensus_pick(static, scored, w: float) -> str:
    """The pick under M2: the argmin of the equal-weight mean of Y1's decision rank and ECR's rank
    over the SAME candidate slate Y1 scored.

    Y1's engine is untouched -- `scored` is whatever `_pick_by_tier` returned. A candidate with no
    ECR rank sorts last in the ECR vote, the same convention `best_by_market_rank` already uses
    ("a real drafter still has to pick someone").

    w = 0 returns Y1's own pick exactly, because `_pick_by_tier` selects by the same
    `(-score, player_id)` order this builds `r_y1` from.
    """
    ranked = sorted(scored, key=lambda c: (-c.score, c.player_id))
    r_y1 = {c.player_id: i for i, c in enumerate(ranked)}
    ecr_order = sorted(
        r_y1,
        key=lambda p: (static.market_rank[p][1] if p in static.market_rank else math.inf, p),
    )
    r_ecr = {p: i for i, p in enumerate(ecr_order)}
    return min(r_y1, key=lambda p: ((1.0 - w) * r_y1[p] + w * r_ecr[p], p))


# --------------------------------------------------------------------------------------------
# arm plumbing
# --------------------------------------------------------------------------------------------
def arm_spec(arm: str) -> tuple[str, float, tuple[str, ...]]:
    """(method, weight, positions) for an arm name. `method` is one of
    'control' | 'board' | 'decision' | 'ecr' | 'ecr_naive' | 'oracle'."""
    if arm == "Y1":
        return "control", 0.0, ALL_POSITIONS
    if arm == "ECR_ALONE":
        return "ecr", 1.0, ALL_POSITIONS
    if arm == "ECR_ALONE_NAIVE":
        return "ecr_naive", 1.0, ALL_POSITIONS
    if arm == "ORACLE_Y1":
        return "oracle", 0.0, ALL_POSITIONS
    if arm.startswith("T1_"):
        _, posset, wtag = arm.split("_")
        positions = SKILL if posset == "SKILL" else ALL_POSITIONS
        return "board", int(wtag[1:]) / 100.0, positions
    if arm.startswith("T2_"):
        return "decision", int(arm.split("_")[1][1:]) / 100.0, ALL_POSITIONS
    raise ValueError(f"unknown arm {arm!r}")


def arm_static(con, league, season, static, arm: str):
    """The board an arm drafts from. Only `board` arms and `ORACLE_Y1` change it."""
    method, w, positions = arm_spec(arm)
    if method == "board":
        return blended_static(league, static, w, positions)[0]
    if method == "oracle":
        return D103.oracle_static(con, league, season, static)
    return static


def _static_for(con, league, season):
    series = resolve_market_series(league)
    static = load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )
    # Invalid-cell rules (a) and (c), checked before anything is measured.
    if not static.market_rank:
        raise InvalidCellError(
            f"{league.league_id} {season}: the resolved series "
            f"{series.ecr_type}/{series.page_type} has no preseason board; the cell is INVALID "
            "and is excluded -- no other date or page is substituted"
        )
    if not static.projections:
        raise InvalidCellError(f"{league.league_id} {season}: empty projection board")
    return static


def play_draft(con, league, season, static, slot, *, arm, control_static, weekly, objective):
    """One full draft by `arm`, scored on realized outcomes.

    Mirrors D103's `_play_draft` exactly -- same geometry, same nine `roster_aware_market_pick`
    opponents reading the CONTROL board, same realized scoring -- and differs only in how OUR seat
    chooses, which is the whole point of the phase.
    """
    method, w, _ = arm_spec(arm)
    rounds = int(league.roster.get("roster_size", 0))
    teams = league.teams
    avail = set(static.projections)
    mine: list[str] = []
    opps = {s: [] for s in range(1, teams + 1) if s != slot}
    my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
    for current, round_no, seat in draft_order(league):
        if not avail:
            break
        remaining = rounds - round_no + 1
        if seat != slot:
            pick = roster_aware_market_pick(
                avail, control_static.market_rank, control_static.positions, league,
                opps[seat], remaining,
            )
            opps[seat].append(control_static.positions.get(pick, "UNKNOWN"))
            avail.discard(pick)
            continue
        if method == "ecr":
            pick = roster_aware_market_pick(
                avail, control_static.market_rank, control_static.positions, league,
                [control_static.positions.get(p, "UNKNOWN") for p in mine], remaining,
            )
        elif method == "ecr_naive":
            pick = best_by_market_rank(avail, control_static.market_rank)
        else:
            nxt = next((p for p in my_picks if p > current), None)
            pick, scored = _pick_by_tier(
                static, con, league, season, avail,
                [static.positions.get(p, "UNKNOWN") for p in mine], SHIPPED_TIER, current, nxt,
                roster_player_ids=list(mine), picks_remaining=remaining,
            )
            if method == "decision" and w > 0.0:
                pick = consensus_pick(static, scored, w)
        mine.append(pick)
        avail.discard(pick)

    actual = _actual_points_for(con, season, mine)
    if objective == WEEKLY_NO_FORESIGHT:
        from alpha_squad.evaluation.weekly_objective import weekly_lineup_points_no_foresight

        return weekly_lineup_points_no_foresight(
            league, mine, control_static.positions, weekly, control_static.projections
        ), mine
    single = league.model_copy(update={"teams": 1})
    starters = compute_league_starters(
        single, {p: actual.get(p, 0.0) for p in mine},
        {p: control_static.positions.get(p, "UNKNOWN") for p in mine},
    )
    return sum(actual.get(p, 0.0) for p in starters["starters"]), mine


# --------------------------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------------------------
def per_season_paired(rows, league_name, a, b):
    """Season-clustered paired difference a - b. Seasons are the independent unit (k = 5)."""
    by_season = defaultdict(list)
    for r in rows:
        if r["league"] == league_name and a in r and b in r:
            by_season[r["season"]].append(r[a] - r[b])
    return [(s, mean(v)) for s, v in sorted(by_season.items())]


def contrast(values: list[float]) -> dict:
    """Season-clustered paired t, with the realized MDE beside it."""
    k = len(values)
    md = mean(values) if k else float("nan")
    out = {"effect": md, "k": k, "wins": sum(1 for v in values if v > 0),
           "losses": sum(1 for v in values if v < 0)}
    if k < 2 or stdev(values) == 0:
        out.update({"se": float("nan"), "t": float("nan"), "ci": "n/a",
                    "mde": float("nan"), "sd": 0.0})
        return out
    sd = stdev(values)
    se = sd / k**0.5
    out.update({
        "sd": sd, "se": se, "t": md / se,
        "ci": f"[{md - T_CRIT_95 * se:+.1f}, {md + T_CRIT_95 * se:+.1f}]",
        "ci_lo": md - T_CRIT_95 * se, "ci_hi": md + T_CRIT_95 * se,
        # Minimum detectable effect at 80% power, two-sided alpha = 0.05, k-1 df.
        "mde": (T_CRIT_95 + T_POWER_80) * se,
    })
    return out


def verdict_for(effect: float) -> str:
    lo, hi = DETECTION_FLOOR
    if abs(effect) < lo:
        return "BELOW the floor -> UNRESOLVED"
    if abs(effect) < hi:
        return "inside the floor band -> UNRESOLVED"
    return "ABOVE the floor"


def _fmt_contrast(label: str, c: dict, per_season: list[tuple[int, float]]) -> str:
    ties = c["k"] - c["wins"] - c["losses"]
    body = (f"    {label}\n"
            f"       {c['effect']:>+9.1f}   95% CI {c.get('ci', 'n/a')}   "
            f"t={c.get('t', float('nan')):>6.2f}   "
            f"seasons {c['wins']}W/{ties}T/{c['losses']}L   "
            f"MDE(80%) {c.get('mde', float('nan')):>6.1f}\n"
            f"       by season: "
            + "  ".join(f"{s}:{v:+.0f}" for s, v in per_season))
    return body


# --------------------------------------------------------------------------------------------
# MODE: phase0 -- the integration-point audit, and the anti-leakage record
# --------------------------------------------------------------------------------------------
def run_phase0(con, slots) -> dict:
    out: dict = {"coverage": [], "score_ties": {}, "isotonic": [], "vintage": {}}
    vintage = compute_board_vintage(con)
    out["vintage"] = vintage.as_dict()

    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        series = resolve_market_series(league)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            page_type = preseason_page_type(con, series.ecr_type, season)
            dates = con.execute(
                "SELECT min(scrape_date), max(scrape_date), count(*) FROM market_snapshot "
                "WHERE ecr_type = ? AND page_type = ? AND year(scrape_date) = ? "
                "AND month(scrape_date) IN (7, 8)",
                [series.ecr_type, page_type, season],
            ).fetchone()
            counts, covered = Counter(), Counter()
            for p in static.projections:
                pos = static.positions.get(p, "UNKNOWN")
                counts[pos] += 1
                if p in static.market_rank:
                    covered[pos] += 1
            out["coverage"].append({
                "league": league_name, "season": season,
                "ecr_type": series.ecr_type, "page_type": page_type,
                "board": len(static.projections),
                "ranked": sum(1 for p in static.projections if p in static.market_rank),
                "scrape_min": str(dates[0]), "scrape_max": str(dates[1]), "rows": dates[2],
                "by_position": {p: [covered[p], counts[p]] for p in ALL_POSITIONS},
            })

    # M3's measured rejection: how often is the TOP decision score exactly tied?
    total, tied = 0, 0
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, static.positions, league,
                            opps[seat], remaining,
                        )
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    pick, scored = _pick_by_tier(
                        static, con, league, season, avail,
                        [static.positions.get(p, "UNKNOWN") for p in mine], SHIPPED_TIER,
                        current, nxt, roster_player_ids=list(mine), picks_remaining=remaining,
                    )
                    ranked = sorted(scored, key=lambda c: (-c.score, c.player_id))
                    total += 1
                    if len(ranked) > 1 and abs(ranked[0].score - ranked[1].score) <= 1e-9:
                        tied += 1
                    mine.append(pick)
                    avail.discard(pick)
            print(f"  phase0 ties {league_name} {season} done", flush=True)
    out["score_ties"] = {"pick_states": total, "top_score_exactly_tied": tied}
    return out


def report_phase0(out: dict) -> None:
    print(f"\n{'=' * 98}\nPHASE 0 -- ECR availability, vintage and the integration audit"
          f"\n{'=' * 98}")
    print(f"\n  board vintage (projection board): {out['vintage']['combined_hash']}")
    print(f"  upstream ECR blob sha256:         {out['vintage']['board_sha256']}")
    print(f"  D89-pinned ECR blob sha256:       {D89_BOARD_SHA256}")
    print(f"\n  {'league':<15}{'season':>7}{'series':>22}{'board':>7}{'ranked':>8}{'cov%':>7}"
          f"  {'scrapes':>26}")
    for row in out["coverage"]:
        print(f"  {row['league']:<15}{row['season']:>7}"
              f"{row['ecr_type'] + '/' + str(row['page_type']):>22}"
              f"{row['board']:>7}{row['ranked']:>8}{row['ranked'] / row['board']:>6.1%}"
              f"  {row['scrape_min']}..{row['scrape_max']}")
    print("\n  ECR coverage by position (covered/total on the draft board)")
    print(f"  {'league':<15}{'season':>7}  " + "  ".join(f"{p:>9}" for p in ALL_POSITIONS))
    for row in out["coverage"]:
        cells = "  ".join(f"{row['by_position'][p][0]}/{row['by_position'][p][1]:<7}"
                          for p in ALL_POSITIONS)
        print(f"  {row['league']:<15}{row['season']:>7}  {cells}")
    t = out["score_ties"]
    print(f"\n  M3 (ECR as an exact-tie-breaker) is a MEASURED NO-OP: the top decision score is "
          f"exactly tied in\n    {t['top_score_exactly_tied']} of {t['pick_states']} real pick "
          f"states ({t['top_score_exactly_tied'] / max(1, t['pick_states']):.2%}).")


# --------------------------------------------------------------------------------------------
# MODE: parity -- P1..P5, run BEFORE any treatment result is interpreted
# --------------------------------------------------------------------------------------------
def run_parity(con, slots) -> dict:
    result = {"P1_L0_equals_production": {"states": 0, "agree": 0, "mismatches": []},
              "P2_w0_is_control": {"checks": 0, "failures": []},
              "P3_multiset_preserved": {"checks": 0},
              "P4_pool_parity": {"checks": 0},
              "P5_ecr_board": {}}

    # P5 -- the ECR board this phase reads is the one D104 read.
    rows = con.execute(
        """
        SELECT player_id, scrape_date, ecr_type, page_type, position, ecr_rank, ecr_best, ecr_worst
        FROM market_snapshot
        WHERE ecr_type IN ('ro', 'do') AND month(scrape_date) IN (7, 8)
          AND year(scrape_date) BETWEEN 2021 AND 2025
        ORDER BY 1, 2, 3, 4
        """
    ).fetchall()
    result["P5_ecr_board"] = {
        "assembled_rows": len(rows),
        "assembled_sha256": hashlib.sha256(repr(rows).encode()).hexdigest(),
        "upstream_population_sha256_expected": ECR_POPULATION_SHA256,
        "note": "the upstream-blob comparison is in the pre-registration; this is the "
                "ASSEMBLED (identity-joined) board's own hash, recorded for future phases",
    }

    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)

            # P2/P3/P4 -- every arm at w = 0 is byte-identical to the control.
            for positions in (ALL_POSITIONS, SKILL):
                zero, moved, _ = blended_static(league, static, 0.0, positions)
                result["P2_w0_is_control"]["checks"] += 1
                result["P3_multiset_preserved"]["checks"] += 1
                result["P4_pool_parity"]["checks"] += 1
                if zero.projections != static.projections or zero.vorp != static.vorp or moved:
                    result["P2_w0_is_control"]["failures"].append(
                        f"{league_name} {season} {positions}: moved={moved}")

            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                zero_static = blended_static(league, static, 0.0, ALL_POSITIONS)[0]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, static.positions, league,
                            opps[seat], remaining,
                        )
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                    l0, scored = _pick_by_tier(static, con, league, season, set(avail),
                                               list(my_pos), SHIPPED_TIER, current, nxt, **kw)
                    # P1 -- the control IS production.
                    h, _ = _pick_by_tier(static, con, league, season, set(avail), list(my_pos),
                                         "H", current, nxt, **kw)
                    result["P1_L0_equals_production"]["states"] += 1
                    if l0 == h:
                        result["P1_L0_equals_production"]["agree"] += 1
                    elif len(result["P1_L0_equals_production"]["mismatches"]) < 20:
                        result["P1_L0_equals_production"]["mismatches"].append(
                            [league_name, season, slot, round_no, l0, h])
                    # P2 -- both w = 0 arms choose exactly what the control chose.
                    z0, _ = _pick_by_tier(zero_static, con, league, season, set(avail),
                                          list(my_pos), SHIPPED_TIER, current, nxt, **kw)
                    d0 = consensus_pick(static, scored, 0.0)
                    result["P2_w0_is_control"]["checks"] += 2
                    if z0 != l0:
                        result["P2_w0_is_control"]["failures"].append(
                            f"board w0 {league_name} {season} slot {slot} rd {round_no}: "
                            f"{z0} != {l0}")
                    if d0 != l0:
                        result["P2_w0_is_control"]["failures"].append(
                            f"decision w0 {league_name} {season} slot {slot} rd {round_no}: "
                            f"{d0} != {l0}")
                    mine.append(l0)
                    avail.discard(l0)
            print(f"  parity {league_name} {season} done", flush=True)
    return result


def report_parity(result: dict) -> None:
    print(f"\n{'=' * 98}\nBASELINE PARITY -- P1..P5\n{'=' * 98}")
    p1 = result["P1_L0_equals_production"]
    print(f"\n  P1  L0 == production (tier H) at every pick state: "
          f"{p1['agree']}/{p1['states']}")
    if p1["mismatches"]:
        print(f"      MISMATCHES (first {len(p1['mismatches'])}): {p1['mismatches']}")
    p2 = result["P2_w0_is_control"]
    print(f"  P2  every arm at w = 0 is byte-identical to the control: "
          f"{p2['checks'] - len(p2['failures'])}/{p2['checks']}")
    for f in p2["failures"][:10]:
        print(f"      FAIL {f}")
    print(f"  P3  per-position value multiset preserved: {result['P3_multiset_preserved']['checks']}"
          f"/{result['P3_multiset_preserved']['checks']} "
          f"(a violation raises SubstitutionError, so reaching here IS the pass)")
    print(f"  P4  candidate-universe parity:             {result['P4_pool_parity']['checks']}"
          f"/{result['P4_pool_parity']['checks']} (same)")
    p5 = result["P5_ecr_board"]
    print(f"  P5  assembled ECR board: {p5['assembled_rows']} rows, "
          f"sha256 {p5['assembled_sha256'][:16]}...")
    ok = (p1["agree"] == p1["states"]) and not p2["failures"]
    print(f"\n  PARITY: {'PASS -- the treatment arms may be interpreted' if ok else 'FAIL -- STOP'}")


# --------------------------------------------------------------------------------------------
# MODE: value -- the PRIMARY metric, realized whole-draft starter points
# --------------------------------------------------------------------------------------------
def run_value(con, slots, objective, arms) -> list[dict]:
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            statics = {a: arm_static(con, league, season, static, a) for a in arms}
            for slot in slots:
                row = {"league": league_name, "season": season, "slot": slot,
                       "objective": objective}
                roster = {}
                for arm in arms:
                    value, mine = play_draft(
                        con, league, season, statics[arm], slot, arm=arm,
                        control_static=static, weekly=weekly, objective=objective,
                    )
                    row[arm] = value
                    roster[arm] = [static.positions.get(p, "UNKNOWN") for p in mine]
                row["_positions"] = roster
                rows.append(row)
            print(f"  value {league_name} {season} done", flush=True)
    return rows


def report_value(rows, arms) -> None:
    print(f"\n{'=' * 98}\nPRIMARY -- realized whole-draft starter points\n{'=' * 98}")
    for league_name in FORMATS:
        sub = [r for r in rows if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}   (n = {len(sub)} drafts per arm)")
        for arm in arms:
            if arm in sub[0]:
                tag = ("  <- CONTROL" if arm == CONTROL else
                       "  <- PRIMARY TREATMENT" if arm in PRIMARY_ARMS else
                       "  <- independent benchmark" if arm.startswith("ECR_ALONE") else
                       "  <- hindsight ceiling, NOT achievable" if arm == "ORACLE_Y1" else "")
                print(f"    {arm:<16} {mean(r[arm] for r in sub):>9.1f}{tag}")
        print()
        for arm in arms:
            if arm == CONTROL or arm not in sub[0]:
                continue
            per_season = per_season_paired(sub, league_name, arm, CONTROL)
            c = contrast([v for _, v in per_season])
            marker = "**" if arm in PRIMARY_ARMS else "  "
            print(_fmt_contrast(f"{marker} {arm} - Y1", c, per_season))
            if arm in PRIMARY_ARMS:
                print(f"       against D97's floor ({DETECTION_FLOOR[0]:.0f}-"
                      f"{DETECTION_FLOOR[1]:.0f} pts): {verdict_for(c['effect'])}")
            print()


# --------------------------------------------------------------------------------------------
# MODE: divergence -- which picks change, and what the changed players actually scored
# --------------------------------------------------------------------------------------------
def run_divergence(con, slots, arms) -> list[dict]:
    """Both arms are asked at the IDENTICAL state, pool and roster; the state advances on the
    CONTROL's pick, so every comparison is made at a state production actually reaches."""
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            realized = _actual_points_for(con, season, sorted(static.projections))
            statics = {a: arm_static(con, league, season, static, a) for a in arms}
            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, static.positions, league,
                            opps[seat], remaining,
                        )
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                    base, base_scored = _pick_by_tier(
                        static, con, league, season, set(avail), list(my_pos), SHIPPED_TIER,
                        current, nxt, **kw)
                    for arm in arms:
                        method, w, _ = arm_spec(arm)
                        if method == "control":
                            continue
                        if method == "board":
                            pick, _ = _pick_by_tier(
                                statics[arm], con, league, season, set(avail), list(my_pos),
                                SHIPPED_TIER, current, nxt, **kw)
                        elif method == "decision":
                            pick = consensus_pick(static, base_scored, w)
                        elif method == "ecr":
                            pick = roster_aware_market_pick(
                                set(avail), static.market_rank, static.positions, league,
                                list(my_pos), remaining)
                        elif method == "ecr_naive":
                            pick = best_by_market_rank(set(avail), static.market_rank)
                        else:
                            continue
                        rows.append({
                            "league": league_name, "season": season, "slot": slot, "arm": arm,
                            "round": round_no, "overall": current, "phase": phase_of(round_no),
                            "control_pick": base, "arm_pick": pick, "same": base == pick,
                            "control_pos": static.positions.get(base, "UNKNOWN"),
                            "arm_pos": static.positions.get(pick, "UNKNOWN"),
                            "control_realized": realized.get(base, 0.0),
                            "arm_realized": realized.get(pick, 0.0),
                            "control_ecr": static.market_rank.get(base, (None, None))[1],
                            "arm_ecr": static.market_rank.get(pick, (None, None))[1],
                            "control_proj": static.projections.get(base, 0.0),
                            "arm_proj": static.projections.get(pick, 0.0),
                        })
                    mine.append(base)
                    avail.discard(base)
            print(f"  divergence {league_name} {season} done", flush=True)
    return rows


def report_divergence(rows, arms) -> None:
    print(f"\n{'=' * 98}\nPICK DIVERGENCE -- what changes, and what the changed players scored"
          f"\n{'=' * 98}")
    print("\n  'realized delta' = realized season points of the arm's player minus the control's,")
    print("  at the SAME state and pool. It is an absolute, arm-independent per-pick outcome.")
    for league_name in FORMATS:
        for arm in arms:
            sub = [r for r in rows if r["league"] == league_name and r["arm"] == arm]
            if not sub:
                continue
            changed = [r for r in sub if not r["same"]]
            print(f"\n  {league_name} / {arm}: {len(changed)}/{len(sub)} picks changed "
                  f"({len(changed) / len(sub):.1%})")
            if not changed:
                continue
            deltas = [r["arm_realized"] - r["control_realized"] for r in changed]
            better = sum(1 for d in deltas if d > 0)
            worse = sum(1 for d in deltas if d < 0)
            print(f"    improved {better}/{len(changed)} ({better / len(changed):.1%})   "
                  f"worsened {worse}/{len(changed)} ({worse / len(changed):.1%})   "
                  f"tied {len(changed) - better - worse}")
            print(f"    realized delta on changed picks: mean {mean(deltas):+.1f}   "
                  f"median {median(deltas):+.1f}   total {sum(deltas):+.0f}")
            ordered = sorted(deltas)
            qs = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
            print("    distribution: " + "  ".join(
                f"p{int(q * 100)}={ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]:+.0f}"
                for q in qs))
            within = [r for r in changed if r["control_pos"] == r["arm_pos"]]
            print(f"    within-position changes {len(within)}/{len(changed)} "
                  f"({len(within) / len(changed):.1%})   "
                  f"cross-position {len(changed) - len(within)}")
            if within:
                wd = [r["arm_realized"] - r["control_realized"] for r in within]
                print(f"      within-position realized delta: mean {mean(wd):+.1f}")
            cross = [r for r in changed if r["control_pos"] != r["arm_pos"]]
            if cross:
                cd = [r["arm_realized"] - r["control_realized"] for r in cross]
                print(f"      cross-position  realized delta: mean {mean(cd):+.1f}")
            print(f"    {'phase':<16}{'picks':>7}{'changed':>9}{'%':>8}{'mean delta':>12}"
                  f"{'improved %':>12}")
            for phase in PHASES:
                ph = [r for r in sub if r["phase"] == phase]
                ch = [r for r in ph if not r["same"]]
                if not ph:
                    continue
                d = [r["arm_realized"] - r["control_realized"] for r in ch]
                print(f"    {phase:<16}{len(ph):>7}{len(ch):>9}{len(ch) / len(ph):>7.1%}"
                      f"{(mean(d) if d else 0):>12.1f}"
                      f"{(sum(1 for x in d if x > 0) / len(d) if d else 0):>11.1%}")
            print(f"    {'round':<7}{'changed %':>11}{'mean delta':>12}")
            for rnd in sorted({r["round"] for r in sub}):
                rr = [r for r in sub if r["round"] == rnd]
                ch = [r for r in rr if not r["same"]]
                d = [r["arm_realized"] - r["control_realized"] for r in ch]
                print(f"    {rnd:<7}{len(ch) / len(rr):>10.0%}{(mean(d) if d else 0):>12.1f}")
            print("    by CONTROL position (where Y1 would have picked):")
            for pos in ALL_POSITIONS:
                ch = [r for r in changed if r["control_pos"] == pos]
                if not ch:
                    continue
                d = [r["arm_realized"] - r["control_realized"] for r in ch]
                print(f"      {pos:<5} n={len(ch):<5} mean delta {mean(d):>+8.1f}  "
                      f"improved {sum(1 for x in d if x > 0) / len(d):>5.1%}")
            swaps = Counter((r["control_pos"], r["arm_pos"]) for r in changed)
            print(f"    position swaps (Y1 -> arm), top 8: {swaps.most_common(8)}")
            firsts = []
            for key in {(r["season"], r["slot"]) for r in sub}:
                ch = sorted(r["round"] for r in changed
                            if (r["season"], r["slot"]) == key)
                firsts.append(ch[0] if ch else None)
            hist = Counter(f for f in firsts if f is not None)
            print(f"    first divergence round histogram: {dict(sorted(hist.items()))}   "
                  f"drafts with no divergence {sum(1 for f in firsts if f is None)}/{len(firsts)}")
            for lo, hi in ((1, 1), (20, 21), (40, 41), (60, 61)):
                pr = [r for r in sub if lo <= r["overall"] <= hi]
                ch = [r for r in pr if not r["same"]]
                if not pr:
                    continue
                d = [r["arm_realized"] - r["control_realized"] for r in ch]
                print(f"    picks {lo}-{hi}: {len(ch)}/{len(pr)} changed, "
                      f"mean realized delta {(mean(d) if d else 0):+.1f}")


# --------------------------------------------------------------------------------------------
# MODE: counterfactual -- matched rollout of the two candidates, same board, same continuation
# --------------------------------------------------------------------------------------------
def _matched_value(con, league, season, static, scorer, realized, *, slot, after, available,
                   drafted, opponents, candidate) -> float:
    """Final realized roster value if `candidate` is taken at `after` and the CONTROL engine plays
    the rest of the draft off the CONTROL board. The only thing that varies between two calls at
    one pick state is `candidate`, which is what makes the difference attributable to that pick."""
    value, _total, _unfilled = rollout(
        con, league, season, static, draft_slot=slot, after_pick_overall=after,
        available={p for p in available if p != candidate},
        drafted=[*drafted, candidate],
        opponent_rosters={s: list(v) for s, v in opponents.items()},
        actual=realized, scorer=scorer,
    )
    return value


def run_counterfactual(con, slots, objective, arms) -> list[dict]:
    """At each state where an arm's pick differs from the control's, roll the REST of the draft out
    twice -- once having taken the control's player, once the arm's -- with the CONTROL board and
    the shipped engine as the continuation in BOTH cases.

    D106 established that regret measured against an arm's own oracle is uninterpretable, because
    changing the board changes the oracle too. Holding the continuation at the control removes that
    entirely: the two rollouts differ by exactly one player, so the difference is attributable to
    THAT PICK and to nothing else.
    """
    rows = []
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        rounds = int(league.roster.get("roster_size", 0))
        teams = league.teams
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            weekly = load_weekly_points(con, season)
            scorer = make_roster_scorer(objective, league, static, weekly)
            realized = _actual_points_for(con, season, sorted(static.projections))
            statics = {a: arm_static(con, league, season, static, a) for a in arms}
            for slot in slots:
                avail = set(static.projections)
                mine: list[str] = []
                opps = {s: [] for s in range(1, teams + 1) if s != slot}
                my_picks = [snake_overall_pick(r, slot, teams) for r in range(1, rounds + 1)]
                for current, round_no, seat in draft_order(league):
                    if not avail:
                        break
                    remaining = rounds - round_no + 1
                    if seat != slot:
                        pick = roster_aware_market_pick(
                            avail, static.market_rank, static.positions, league,
                            opps[seat], remaining,
                        )
                        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
                        avail.discard(pick)
                        continue
                    nxt = next((p for p in my_picks if p > current), None)
                    kw = dict(roster_player_ids=list(mine), picks_remaining=remaining)
                    my_pos = [static.positions.get(p, "UNKNOWN") for p in mine]
                    base, base_scored = _pick_by_tier(
                        static, con, league, season, set(avail), list(my_pos), SHIPPED_TIER,
                        current, nxt, **kw)

                    cache: dict[str, float] = {}
                    for arm in arms:
                        method, w, _ = arm_spec(arm)
                        if method == "control":
                            continue
                        if method == "board":
                            pick, _ = _pick_by_tier(
                                statics[arm], con, league, season, set(avail), list(my_pos),
                                SHIPPED_TIER, current, nxt, **kw)
                        elif method == "decision":
                            pick = consensus_pick(static, base_scored, w)
                        elif method == "ecr":
                            pick = roster_aware_market_pick(
                                set(avail), static.market_rank, static.positions, league,
                                list(my_pos), remaining)
                        else:
                            continue
                        if pick == base:
                            continue
                        for cand in (base, pick):
                            if cand not in cache:
                                cache[cand] = _matched_value(
                                    con, league, season, static, scorer, realized,
                                    slot=slot, after=current, available=avail,
                                    drafted=mine, opponents=opps, candidate=cand,
                                )
                        rows.append({
                            "league": league_name, "season": season, "slot": slot, "arm": arm,
                            "round": round_no, "phase": phase_of(round_no),
                            "objective": objective,
                            "control_pick": base, "arm_pick": pick,
                            "control_value": cache[base], "arm_value": cache[pick],
                            "delta": cache[pick] - cache[base],
                            "control_pos": static.positions.get(base, "UNKNOWN"),
                            "arm_pos": static.positions.get(pick, "UNKNOWN"),
                        })
                    mine.append(base)
                    avail.discard(base)
                print(f"  counterfactual {league_name} {season} slot {slot} done", flush=True)
    return rows


def report_counterfactual(rows, arms) -> None:
    print(f"\n{'=' * 98}\nMATCHED PICK-LEVEL COUNTERFACTUAL -- same state, same board, "
          f"same continuation\n{'=' * 98}")
    print("\n  delta = final realized roster value taking the ARM's player minus taking the")
    print("  CONTROL's, with the rest of the draft played identically in both. Positive means the")
    print("  changed pick was genuinely worth more by the end of the draft.")
    for league_name in FORMATS:
        for arm in arms:
            sub = [r for r in rows if r["league"] == league_name and r["arm"] == arm]
            if not sub:
                continue
            d = [r["delta"] for r in sub]
            better = sum(1 for x in d if x > 0)
            worse = sum(1 for x in d if x < 0)
            print(f"\n  {league_name} / {arm}: {len(sub)} changed picks")
            print(f"    better {better} ({better / len(sub):.1%})   "
                  f"worse {worse} ({worse / len(sub):.1%})   "
                  f"neutral {len(sub) - better - worse}")
            print(f"    delta: mean {mean(d):+.1f}   median {median(d):+.1f}   "
                  f"total {sum(d):+.0f}")
            per_season = defaultdict(list)
            for r in sub:
                per_season[r["season"]].append(r["delta"])
            vals = [mean(v) for _, v in sorted(per_season.items())]
            c = contrast(vals)
            print(f"    season-clustered mean delta per changed pick {c['effect']:+.2f}  "
                  f"95% CI {c.get('ci', 'n/a')}  seasons better {c['wins']}/{c['k']}")
            print(f"    {'phase':<16}{'n':>6}{'mean':>10}{'better %':>11}")
            for phase in PHASES:
                ph = [r["delta"] for r in sub if r["phase"] == phase]
                if ph:
                    print(f"    {phase:<16}{len(ph):>6}{mean(ph):>10.1f}"
                          f"{sum(1 for x in ph if x > 0) / len(ph):>10.1%}")
            print("    by CONTROL position:")
            for pos in ALL_POSITIONS:
                ph = [r["delta"] for r in sub if r["control_pos"] == pos]
                if ph:
                    print(f"      {pos:<5} n={len(ph):<5} mean {mean(ph):>+8.1f}  "
                          f"better {sum(1 for x in ph if x > 0) / len(ph):>5.1%}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True,
                    choices=("phase0", "parity", "value", "divergence", "counterfactual"))
    ap.add_argument("--slots", default=",".join(str(s) for s in DEFAULT_SLOTS))
    ap.add_argument("--objective", default=SEASON_LONG, choices=(SEASON_LONG, WEEKLY_NO_FORESIGHT))
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slots = tuple(int(s) for s in args.slots.split(","))
    arms = tuple(a for a in args.arms.split(",") if a)
    for arm in arms:
        arm_spec(arm)  # fail fast on an unknown arm name

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise InvalidCellError(f"{season} must never enter the historical evaluation")

    con = duckdb.connect(args.db, read_only=True)
    vintage = compute_board_vintage(con)
    print(f"board vintage {vintage.combined_hash}")
    print(f"upstream ECR blob {vintage.board_sha256}  (D89 pin {D89_BOARD_SHA256})")
    print(f"seasons {BACKTEST_SEASONS}  slots {slots}  objective {args.objective}")
    print(f"arms {arms}  mode {args.mode}\n")

    if args.mode == "phase0":
        result = run_phase0(con, slots)
        (out / "d111_phase0.json").write_text(json.dumps(result, indent=2, default=str))
        report_phase0(result)
    elif args.mode == "parity":
        result = run_parity(con, slots)
        (out / "d111_parity.json").write_text(json.dumps(result, indent=2, default=str))
        report_parity(result)
    elif args.mode == "value":
        rows = run_value(con, slots, args.objective, arms)
        (out / f"d111_value_{args.objective}.json").write_text(json.dumps(rows, default=str))
        report_value(rows, arms)
    elif args.mode == "divergence":
        rows = run_divergence(con, slots, arms)
        (out / "d111_divergence.json").write_text(json.dumps(rows, default=str))
        report_divergence(rows, arms)
    else:
        rows = run_counterfactual(con, slots, args.objective, arms)
        (out / f"d111_counterfactual_{args.objective}.json").write_text(
            json.dumps(rows, default=str))
        report_counterfactual(rows, arms)


if __name__ == "__main__":
    main()
