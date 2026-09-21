"""D114 -- can matched-state pairing resolve decision-layer effects the free-running design could not?

Read-only research runner. Opens the database read-only, imports the shipped engine and the
already-committed instruments (`evaluation/draft_oracle.py`'s `rollout`, D103; D104's
`ecr_ordered_static`), and writes nothing but JSON artifacts under `--out`. **No file under
`src/alpha_squad/` is touched by D114 and this script is imported by no production path.**

    uv run python scripts/research/d114_matched_state.py --mode audit      --out <dir>
    uv run python scripts/research/d114_matched_state.py --mode freerun    --out <dir>
    uv run python scripts/research/d114_matched_state.py --mode onestep    --out <dir>
    uv run python scripts/research/d114_matched_state.py --mode report     --out <dir>

==========================================================================================
PRE-REGISTRATION -- written before any D114 estimator ran, committed WITH the results
==========================================================================================

Stated precisely, because the distinction matters and D113 did it the stronger way: this block
was written before `--mode freerun` or `--mode onestep` executed, but it was NOT committed before
them -- it lands in the same commit as the results. What HAD been seen when it was written is the
D104 replication (`--mode audit`, then D104's own unmodified runner re-run on this vintage). The
decision rule below is D114's brief's, not this runner's invention, `_classify` implements it
mechanically, and no rule was altered after any estimator result was seen.

THE QUESTION
------------
D113 measured a decision-layer contrast whose 95% CI half-width was 15.5-46.9 points, four to
sixteen times finer than the 172-250 floor D97 derived and D107 called unlowerable. **Was that
because of the pairing, or because the capacity treatment was nearly inert?** If the pairing did
it, previously-unresolved effects become measurable. If inertness did it, the floor stands for any
treatment that actually moves the draft.

D114 answers that with the one treatment the repository can reconstruct exactly: **D104's ECR
arm**, which changes 57-64% of picks -- the opposite of inert.

WHAT IS AND IS NOT RECONSTRUCTIBLE, established in `--mode audit` BEFORE any measurement
-------------------------------------------------------------------------------------------
* **D104's ECR arm: reconstructible.** `scripts/research/d104_ecr_floor.py::ecr_ordered_static` is
  committed, tested (`tests/unit/test_d104_ecr_floor.py`), and imported here rather than
  reimplemented. D114 does not re-specify it, re-weight it, or re-tune it -- **the arm has no
  weight to tune, by construction**: it is a within-position rank permutation of Y1's own value
  multiset, so replacement levels, scarcity and the positional value scale are all unchanged.
* **D97's NAIVE arm: NOT reconstructible.** See `--mode audit`. No file in any branch of this
  repository has ever contained a `NAIVE` arm; `git log --all -S NAIVE -- '*.py'` is empty, no
  `d97*` file was ever added, and no script was ever deleted. D97's own record says the phase ran
  "no experiment beyond the decomposition", and its runner was never committed. Rebuilding
  "projection over static replacement plus the endgame mandatory-slot rule" from D97's prose
  would be **inventing a naive system**, which D114's brief forbids. **Experiment 2 therefore
  STOPS and is reported as unreconstructible. No substitute is run.**
* **The data vintage is NOT the original.** D103/D104/D105 recorded board vintage
  `ca3e2d8a...`; this checkout is `0d525430...` (D113 §4d). Every D114 number is therefore
  labelled CURRENT-VINTAGE. The cross-design comparison that answers the question is run
  entirely WITHIN this vintage, so it is unaffected; only the comparison against D104's published
  magnitudes is cross-vintage, and is labelled as such everywhere it appears.

THE TWO ESTIMATORS, both on the same grid, same vintage, same opponents
-------------------------------------------------------------------------
Both arms are the shipped Y1 decision rule (`SHIPPED_TIER`, pinned to `recommend_draft_pick` by
`TestShippedTierIsProduction`). Only the projections the rule reads differ.

**(1) FREE-RUN** -- D104's design, re-run here on the full slot grid. Each arm plays its own
complete draft from the same start; the contrast is the difference in final realized roster value.
This is the effect of ADOPTING ECR.

**(2) ONE-STEP (matched state)** -- the new estimator, and what the brief specifies by "same
continuation policy after the treatment/control divergence". The control draft is played by the
shipped engine on Y1 projections. At each of our pick states `s`:

    y1_pick   = what production picks at s
    ecr_pick  = what the SAME rule picks at s when it reads the ECR-ordered board
    if they agree                 -> delta(s) = 0 exactly, no rollout needed
    else  V_T(s) = rollout(after ecr_pick, continuation = SHIPPED policy on Y1 projections)
          V_C(s) = rollout(after y1_pick,  continuation = SHIPPED policy on Y1 projections)
          delta(s) = V_T(s) - V_C(s)

Everything except one pick is shared between the two branches: same season, same league, same
slot, same starting roster, same available pool, same opponents, same continuation. `V_C(s)` is
computed through the identical `rollout` call as `V_T(s)` rather than reused from the control
draft, so the two branches cannot differ by how they were computed; the runner ASSERTS
`V_C(s) == V_control` at every state, which is a determinism check on the whole harness.

WHAT EACH ESTIMATOR ESTIMATES -- stated now, because conflating them is the headline risk
-------------------------------------------------------------------------------------------
FREE-RUN estimates "adopt ECR for the whole draft". ONE-STEP estimates "take ECR's advice at ONE
pick and otherwise play production". **The sum of one-step deltas across a draft is NOT the
free-run effect** and is nowhere reported as one: one-step deviations are not additive, because
each is measured against the same unchanged trajectory. Alpha's stated objective -- maximize
realized value from each individual draft pick -- is the ONE-STEP quantity; the roster-level
outcome the program has always reported is the FREE-RUN quantity. D114 reports both and reports
their relationship, and never substitutes one for the other.

POPULATION, fixed before any run
---------------------------------
  seasons  BACKTEST_SEASONS = 2021-2025 (2020 refused: D95/D96).
  slots    1-10 for BOTH estimators. D104's (1, 4, 7, 10) is retained as the pre-registered
           COMMON grid and is what the headline MDE comparison uses, so design -- not sample
           size -- is the only thing that differs between the two estimators; the full grid is
           reported alongside as a secondary figure. (The one-step grid was widened from the
           common grid to 1-10 after measuring that it costs ~9 s per draft, a COST decision
           taken before any estimator result existed, never an outcome-dependent one.)
  formats  target_league (primary) and dynasty_1qb -- exactly D104's FORMATS. The dynasty
           objective is reported separately and never pooled with the target objective.
  objectives  SEASON_LONG (primary) and WEEKLY_NO_FORESIGHT, via D103's `make_roster_scorer`.

The independent unit is the SEASON (k = 5); CIs use t_crit = 2.776, D104's convention.

DECISION RULE for ECR, fixed now
----------------------------------
  A. reproducible positive effect, interval narrow enough to exclude zero, AND a point estimate
     at or above the 25-point economic threshold -> "credible small improvement -- preserve for
     future combined-system testing".
  B. interval tight around zero (CI excludes an effect of economic size in both directions)
     -> CLOSE ECR.
  C. interval still wide relative to a plausible small improvement -> UNRESOLVED; document the
     remaining uncertainty and say what would resolve it.
  D. No ECR weight is tuned, searched or introduced in D114. The arm has none.

A positive point estimate is not sufficient. Statistical significance is not sufficient. Both the
interval and the practical magnitude are reported against the decision, every time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
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
from alpha_squad.evaluation.draft_simulation import (
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
)
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import load_weekly_points
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"

#: Exactly D104's formats. Reported separately; target and dynasty are never pooled.
FORMATS = ("target_league", "dynasty_1qb")
PRIMARY_FORMAT = "target_league"

#: D104's grid. The ONE-STEP estimator runs here, and the MDE comparison uses this COMMON grid so
#: that design -- not sample size -- is the only thing that differs between the two estimators.
COMMON_SLOTS = (1, 4, 7, 10)
#: The FREE-RUN estimator is cheap, so it also runs the full seat grid as a secondary figure.
FULL_SLOTS = tuple(range(1, 11))

CONTROL = "Y1"
TREATMENT = "FP_ECR_Y1"

#: D97's quoted floor for a draft-level contrast, and D107's economic threshold. Quoted, never
#: re-derived.
D97_DETECTION_FLOOR = (172.0, 250.0)
ECONOMIC_THRESHOLD = 25.0

#: The board vintage D103/D104/D105 recorded. D114 checks and RECORDS rather than asserting.
D103_TO_D105_VINTAGE = "ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99"

#: D104's published effects, quoted for the cross-vintage comparison and labelled as historical.
D104_PUBLISHED = {
    "target_league": {"effect": 77.3, "ci": "[-44.1, +198.6]", "t": 1.77, "seasons": "5W/0T/0L"},
    "dynasty_1qb": {"effect": -132.1, "ci": "[-371.1, +107.0]", "t": -1.53, "seasons": "1W/0T/4L"},
}

#: D103's phase convention, kept so the two records stay comparable, plus D113's.
PHASES: tuple[tuple[str, int, int], ...] = (
    ("EARLY 1-5", 1, 5),
    ("MIDDLE 6-10", 6, 10),
    ("LATE 11-16", 11, 16),
)


class UnreconstructibleError(RuntimeError):
    """Raised when an experiment cannot be rebuilt from the current checkout without inventing
    a component. D114 stops rather than substituting."""


def _load_d104():
    """D104's runner, imported rather than reimplemented -- `ecr_ordered_static` IS the arm under
    test and re-specifying it would make D114 a different experiment."""
    path = Path(__file__).resolve().parent / "d104_ecr_floor.py"
    spec = importlib.util.spec_from_file_location("d104_ecr_floor", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D104 = _load_d104()


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def _shell(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"<failed: {exc}>"


def _provenance(con: duckdb.DuckDBPyConnection, extra: dict) -> dict:
    vintage = compute_board_vintage(con)
    return {
        "git_head": _git_head(),
        "python": platform.python_version(),
        "argv": sys.argv,
        "board_vintage": vintage.as_dict(),
        "board_vintage_combined": vintage.combined_hash,
        "board_vintage_matches_d103_to_d105": vintage.combined_hash == D103_TO_D105_VINTAGE,
        "d103_to_d105_vintage": D103_TO_D105_VINTAGE,
        "opponent_strategy": MARKET_CONSENSUS_ROSTER_AWARE,
        "shipped_tier": SHIPPED_TIER,
        "seasons": list(BACKTEST_SEASONS),
        "d97_detection_floor": list(D97_DETECTION_FLOOR),
        "economic_threshold": ECONOMIC_THRESHOLD,
        **extra,
    }


def _write(out: Path, name: str, payload: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"wrote {path}")
    return path


def _static_for(con, league, season):
    series = resolve_market_series(league)
    return load_season_static(
        con, league, season, page_type=preseason_page_type(con, series.ecr_type, season)
    )


def _phase_of(round_no: int) -> str:
    for label, lo, hi in PHASES:
        if lo <= round_no <= hi:
            return label
    return "?"


# --------------------------------------------------------------------------------------------
# MODE: audit -- what can and cannot be reconstructed, BEFORE any measurement
# --------------------------------------------------------------------------------------------
def run_audit(con: duckdb.DuckDBPyConnection) -> dict:
    """The reconstructability audit D114's brief requires as step 1-6. Reports; does not measure.

    The D97 verdict is derived from the repository, not asserted: an arm that no commit in any
    branch has ever contained cannot be rebuilt without inventing it."""
    vintage = compute_board_vintage(con)
    naive_in_code = _shell(["git", "log", "--all", "--oneline", "-S", "NAIVE", "--", "*.py"])
    d97_files = _shell(
        ["git", "log", "--all", "--oneline", "--diff-filter=A", "--name-only", "--", "*d97*"]
    )
    deleted_scripts = _shell(
        ["git", "log", "--all", "--oneline", "--diff-filter=D", "--name-only", "--", "scripts/*"]
    )
    here = Path(__file__).resolve().parent

    ecr_ok = (here / "d104_ecr_floor.py").exists() and hasattr(D104, "ecr_ordered_static")
    audit = {
        "head": _git_head(),
        "head_subject": _shell(["git", "log", "-1", "--format=%s"]),
        "recent_commits": _shell(["git", "log", "--oneline", "-6"]).splitlines(),
        "board_vintage_combined": vintage.combined_hash,
        "board_vintage_per_season": {str(s): h for s, h in sorted(vintage.season_hashes.items())},
        "upstream_board_sha256": vintage.board_sha256,
        "upstream_idmap_sha256": vintage.idmap_sha256,
        "d103_to_d105_recorded_vintage": D103_TO_D105_VINTAGE,
        "vintage_matches_original": vintage.combined_hash == D103_TO_D105_VINTAGE,
        "experiment_1_ecr": {
            "runner_committed": str(here / "d104_ecr_floor.py"),
            "arm_function": "ecr_ordered_static",
            "arm_importable": ecr_ok,
            "test_committed": "tests/unit/test_d104_ecr_floor.py",
            "arms": list(D104.ARMS),
            "has_tunable_weight": False,
            "reconstructible": bool(ecr_ok),
            "note": "the arm is a within-position rank permutation of Y1's own value multiset; "
            "there is no weight to retune, by construction",
        },
        "experiment_2_prod_vs_naive": {
            "commits_ever_adding_a_NAIVE_arm_to_python": naive_in_code or "<none>",
            "files_ever_named_d97x": d97_files or "<none>",
            "scripts_ever_deleted": deleted_scripts or "<none>",
            "naive_arm_present_in_checkout": False,
            "reconstructible": False,
            "note": "D97's NAIVE ('projection over static replacement, classic VBD, with the "
            "endgame mandatory-slot rule') exists only as prose in docs/DECISIONS.md. Building "
            "it would be inventing a naive system, which D114's brief forbids. STOP.",
        },
    }
    return audit


# --------------------------------------------------------------------------------------------
# Shared: play the control draft, recording every state we reach
# --------------------------------------------------------------------------------------------
def _control_draft(con, league, season, static, slot):
    """One full draft played by the shipped engine on `static`, recording the exact state at each
    of OUR picks. Mirrors `draft_oracle.rollout`'s loop so the two are resumable into each other.
    """
    total_rounds = int(league.roster.get("roster_size", 0))
    my_picks = [snake_overall_pick(r, slot, league.teams) for r in range(1, total_rounds + 1)]
    avail = set(static.projections)
    mine: list[str] = []
    opps: dict[int, list[str]] = {s: [] for s in range(1, league.teams + 1) if s != slot}
    states: list[dict] = []

    for current, round_no, seat in draft_order(league):
        if not avail:
            break
        picks_remaining = total_rounds - round_no + 1
        if seat != slot:
            pick = roster_aware_market_pick(
                avail, static.market_rank, static.positions, league, opps[seat], picks_remaining
            )
            opps[seat].append(static.positions.get(pick, "UNKNOWN"))
            avail.discard(pick)
            continue
        nxt = next((p for p in my_picks if p > current), None)
        state = {
            "round": round_no,
            "overall_pick": current,
            "picks_remaining": picks_remaining,
            "next_pick": nxt,
            "available": set(avail),
            "drafted": list(mine),
            "opponents": {s: list(v) for s, v in opps.items()},
        }
        pick, _ = _pick_by_tier(
            static,
            con,
            league,
            season,
            set(avail),
            [static.positions.get(p, "UNKNOWN") for p in mine],
            SHIPPED_TIER,
            current,
            nxt,
            roster_player_ids=list(mine),
            picks_remaining=picks_remaining,
        )
        state["control_pick"] = pick
        states.append(state)
        mine.append(pick)
        avail.discard(pick)
    return mine, states


# --------------------------------------------------------------------------------------------
# MODE: freerun -- D104's design (each arm plays its own draft), on this vintage
# --------------------------------------------------------------------------------------------
def run_freerun(con, slots, formats, objectives) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            ecr_static, n_moved = D104.ecr_ordered_static(league, static)
            weekly = load_weekly_points(con, season)
            scorers = {obj: make_roster_scorer(obj, league, static, weekly) for obj in objectives}
            for slot in slots:
                rosters = {}
                for arm, arm_static in ((CONTROL, static), (TREATMENT, ecr_static)):
                    mine, _ = _control_draft(con, league, season, arm_static, slot)
                    rosters[arm] = mine
                actual = _actual_points_for(
                    con, season, sorted({p for r in rosters.values() for p in r})
                )
                row = {
                    "league": league_name,
                    "season": season,
                    "slot": slot,
                    "n_values_moved_by_ecr": n_moved,
                }
                for arm, mine in rosters.items():
                    row[f"{arm}_roster"] = mine
                    row[f"{arm}_positions"] = [static.positions.get(p, "UNKNOWN") for p in mine]
                    for obj, scorer in scorers.items():
                        value, total, unfilled = scorer(mine, actual)
                        row[f"{arm}_{obj}"] = value
                        row[f"{arm}_{obj}_total"] = total
                        row[f"{arm}_unfilled"] = unfilled
                a, b = rosters[CONTROL], rosters[TREATMENT]
                row["n_players_differing"] = len(set(b) - set(a))
                row["n_positions_differing"] = sum(1 for x, y in zip(a, b, strict=False) if x != y)
                row["first_divergence_round"] = next(
                    (i + 1 for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None
                )
                rows.append(row)
            print(f"  freerun {league_name} {season} ({time.time() - t0:.0f}s)", flush=True)
    return rows


# --------------------------------------------------------------------------------------------
# MODE: onestep -- the matched-state estimator
# --------------------------------------------------------------------------------------------
def run_onestep(con, slots, formats, objectives) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            ecr_static, _ = D104.ecr_ordered_static(league, static)
            weekly = load_weekly_points(con, season)
            scorers = {obj: make_roster_scorer(obj, league, static, weekly) for obj in objectives}
            for slot in slots:
                control_roster, states = _control_draft(con, league, season, static, slot)
                actual = _actual_points_for(con, season, control_roster)
                control_value = {
                    obj: scorer(control_roster, actual)[0] for obj, scorer in scorers.items()
                }
                for state in states:
                    ecr_pick, _ = _pick_by_tier(
                        ecr_static,
                        con,
                        league,
                        season,
                        set(state["available"]),
                        [static.positions.get(p, "UNKNOWN") for p in state["drafted"]],
                        SHIPPED_TIER,
                        state["overall_pick"],
                        state["next_pick"],
                        roster_player_ids=list(state["drafted"]),
                        picks_remaining=state["picks_remaining"],
                    )
                    y1_pick = state["control_pick"]
                    row = {
                        "league": league_name,
                        "season": season,
                        "slot": slot,
                        "round": state["round"],
                        "phase": _phase_of(state["round"]),
                        "overall_pick": state["overall_pick"],
                        "y1_pick": y1_pick,
                        "ecr_pick": ecr_pick,
                        "y1_position": static.positions.get(y1_pick, "UNKNOWN"),
                        "ecr_position": static.positions.get(ecr_pick, "UNKNOWN"),
                        "changed": ecr_pick != y1_pick,
                    }
                    if ecr_pick == y1_pick:
                        # Identical pick from an identical state under an identical continuation:
                        # the deviation is exactly zero. Rolling out would burn time to
                        # recompute a number that is zero by construction.
                        for obj in objectives:
                            row[f"delta_{obj}"] = 0.0
                            row[f"control_{obj}"] = control_value[obj]
                    else:
                        for obj, scorer in scorers.items():
                            v_t = rollout(
                                con,
                                league,
                                season,
                                static,
                                draft_slot=slot,
                                after_pick_overall=state["overall_pick"],
                                available={p for p in state["available"] if p != ecr_pick},
                                drafted=[*state["drafted"], ecr_pick],
                                opponent_rosters=state["opponents"],
                                actual=actual,
                                scorer=scorer,
                            )[0]
                            v_c = rollout(
                                con,
                                league,
                                season,
                                static,
                                draft_slot=slot,
                                after_pick_overall=state["overall_pick"],
                                available={p for p in state["available"] if p != y1_pick},
                                drafted=[*state["drafted"], y1_pick],
                                opponent_rosters=state["opponents"],
                                actual=actual,
                                scorer=scorer,
                            )[0]
                            # The control branch re-derives the control draft, so it MUST come
                            # back at the control's own value. If it does not, the harness is
                            # not resuming the same draft and every delta is noise.
                            if abs(v_c - control_value[obj]) > 1e-6:
                                raise UnreconstructibleError(
                                    f"control rollout {v_c} != control draft {control_value[obj]} "
                                    f"at {league_name}/{season}/slot {slot}/pick "
                                    f"{state['overall_pick']} ({obj}) -- the matched-state "
                                    "harness is not resuming production's own draft"
                                )
                            row[f"delta_{obj}"] = v_t - v_c
                            row[f"control_{obj}"] = v_c
                    rows.append(row)
                print(
                    f"  onestep {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    realized = _actual_points_for(
        con, 0, []
    )  # placeholder kept out of the hot loop; per-season realized added below
    del realized
    return rows


def attach_realized(con, rows: list[dict]) -> list[dict]:
    """Realized season points of each arm's chosen player, for the pick-level (NOT roster-level)
    metric. Kept separate from the rollout values so the two can never be confused."""
    by_season: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        by_season[r["season"]].update((r["y1_pick"], r["ecr_pick"]))
    points: dict[int, dict[str, float]] = {
        s: _actual_points_for(con, s, sorted(ids)) for s, ids in by_season.items()
    }
    for r in rows:
        r["y1_realized"] = round(points[r["season"]].get(r["y1_pick"], 0.0), 3)
        r["ecr_realized"] = round(points[r["season"]].get(r["ecr_pick"], 0.0), 3)
    return rows


# --------------------------------------------------------------------------------------------
# Statistics -- season-clustered paired differences, D104's convention
# --------------------------------------------------------------------------------------------
def _ci(values: list[float], t_crit: float = 2.776):
    k = len(values)
    if k == 0:
        return float("nan"), float("nan"), "n/a", float("nan")
    md = mean(values)
    if k < 2 or stdev(values) == 0:
        return md, float("nan"), "n/a", float("nan")
    se = stdev(values) / k**0.5
    return md, md / se, f"[{md - t_crit * se:+.1f}, {md + t_crit * se:+.1f}]", t_crit * se


def _by_season(pairs: list[tuple[int, float]]) -> dict[int, float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for season, value in pairs:
        grouped[season].append(value)
    return {s: mean(v) for s, v in sorted(grouped.items())}


def _classify(md: float, half: float) -> str:
    """The pre-registered ECR decision rule, applied mechanically.

    Order matters and is fixed here: whether the interval excludes zero is asked FIRST, and the
    economic magnitude second. An interval like [+5, +15] excludes zero but is economically
    negligible -- that is `A-`, a real-but-worthless effect, and it must not be reported as
    either a credible improvement or as an interval "tight around zero", which is a different
    statement about a different interval."""
    if md != md or half != half:
        return "n/a"
    lo, hi = md - half, md + half
    if lo > 0 or hi < 0:  # excludes zero
        if abs(md) >= ECONOMIC_THRESHOLD:
            return "A: credible effect at or above the economic threshold"
        return "A-: excludes zero but the point estimate is below the economic threshold"
    if abs(lo) < ECONOMIC_THRESHOLD and abs(hi) < ECONOMIC_THRESHOLD:
        return "B: TIGHT AROUND ZERO -- an economically meaningful effect is excluded"
    return "C: UNRESOLVED -- interval admits an economically meaningful effect"


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
def report(freerun: list[dict], onestep: list[dict], objectives: tuple[str, ...]) -> dict:
    bar = "=" * 100
    summary: dict = {"formats": {}}
    formats = [f for f in FORMATS if any(r["league"] == f for r in freerun)]

    print(f"\n{bar}\nESTIMATOR 1 -- FREE-RUN (D104's design): each arm plays its own draft\n{bar}")
    for league_name in formats:
        entry = summary["formats"].setdefault(league_name, {})
        for grid_name, grid in (("common_grid_1_4_7_10", COMMON_SLOTS), ("full_grid_1_10", None)):
            sub = [
                r
                for r in freerun
                if r["league"] == league_name and (grid is None or r["slot"] in grid)
            ]
            if not sub:
                continue
            print(f"\n  {league_name}  [{grid_name}]  ({len(sub)} paired drafts)")
            block: dict = {"n_drafts": len(sub)}
            for obj in objectives:
                per_season = _by_season(
                    [(r["season"], r[f"{TREATMENT}_{obj}"] - r[f"{CONTROL}_{obj}"]) for r in sub]
                )
                md, t, ci, half = _ci(list(per_season.values()))
                diffs = [r[f"{TREATMENT}_{obj}"] - r[f"{CONTROL}_{obj}"] for r in sub]
                block[obj] = {
                    "mean_per_draft": round(md, 1),
                    "ci": ci,
                    "t": None if t != t else round(t, 2),
                    "mde": None if half != half else round(half, 1),
                    "between_season_sd": (
                        round(stdev(list(per_season.values())), 1) if len(per_season) > 1 else None
                    ),
                    "seasons_won": sum(1 for v in per_season.values() if v > 0),
                    "seasons_lost": sum(1 for v in per_season.values() if v < 0),
                    "drafts_won": sum(1 for d in diffs if d > 0),
                    "drafts_tied": sum(1 for d in diffs if d == 0),
                    "drafts_lost": sum(1 for d in diffs if d < 0),
                    "per_season": {str(s): round(v, 1) for s, v in per_season.items()},
                    "classification": _classify(md, half),
                }
                print(
                    f"    {obj:<22} {md:>+9.1f}  95% CI {ci:<22} t={t:>6.2f}  MDE {half:>7.1f}  "
                    f"seasons {block[obj]['seasons_won']}W/{block[obj]['seasons_lost']}L  "
                    f"drafts {block[obj]['drafts_won']}W/{block[obj]['drafts_tied']}T/"
                    f"{block[obj]['drafts_lost']}L"
                )
                print(
                    "      by season: "
                    + "  ".join(f"{s}:{v:+.0f}" for s, v in per_season.items())
                    + f"   -> {block[obj]['classification']}"
                )
            block["mean_players_differing"] = round(mean(r["n_players_differing"] for r in sub), 2)
            block["identical_rosters"] = sum(1 for r in sub if r["n_players_differing"] == 0)
            fd = [r["first_divergence_round"] for r in sub if r["first_divergence_round"]]
            block["mean_first_divergence_round"] = round(mean(fd), 1) if fd else None
            block["min_first_divergence_round"] = min(fd) if fd else None
            print(
                f"    rosters: {block['mean_players_differing']} of "
                f"{len(sub[0][f'{CONTROL}_roster'])} players differ; "
                f"{block['identical_rosters']} identical; first divergence round "
                f"{block['mean_first_divergence_round']} (min {block['min_first_divergence_round']})"
            )
            entry[f"freerun_{grid_name}"] = block

    print(
        f"\n{bar}\nESTIMATOR 2 -- ONE-STEP (matched state): one pick swapped, shared "
        f"continuation\n{bar}"
    )
    for league_name in formats:
        sub = [r for r in onestep if r["league"] == league_name]
        if not sub:
            continue
        entry = summary["formats"].setdefault(league_name, {})
        changed = [r for r in sub if r["changed"]]
        block = {
            "n_pick_states": len(sub),
            "n_changed": len(changed),
            "pct_changed": round(100 * len(changed) / len(sub), 1),
            "n_drafts": len({(r["season"], r["slot"]) for r in sub}),
        }
        print(
            f"\n  {league_name}  ({block['n_drafts']} drafts, {len(sub)} matched pick states, "
            f"{len(changed)} changed = {block['pct_changed']}%)"
        )
        for obj in objectives:
            # Per pick state, clustered by season: the value of ONE ECR substitution.
            per_season = _by_season([(r["season"], r[f"delta_{obj}"]) for r in sub])
            md, t, ci, half = _ci(list(per_season.values()))
            block[obj] = {
                "mean_per_pick_state": round(md, 2),
                "ci": ci,
                "t": None if t != t else round(t, 2),
                "mde": None if half != half else round(half, 2),
                "between_season_sd": (
                    round(stdev(list(per_season.values())), 2) if len(per_season) > 1 else None
                ),
                "seasons_won": sum(1 for v in per_season.values() if v > 0),
                "seasons_lost": sum(1 for v in per_season.values() if v < 0),
                "per_season": {str(s): round(v, 2) for s, v in per_season.items()},
                "classification": _classify(md, half),
            }
            # Conditional on the pick actually changing.
            if changed:
                cper = _by_season([(r["season"], r[f"delta_{obj}"]) for r in changed])
                cmd, ct, cci, chalf = _ci(list(cper.values()))
                block[obj]["changed_only"] = {
                    "mean_per_changed_pick": round(cmd, 2),
                    "ci": cci,
                    "t": None if ct != ct else round(ct, 2),
                    "mde": None if chalf != chalf else round(chalf, 2),
                    "n_better": sum(1 for r in changed if r[f"delta_{obj}"] > 0),
                    "n_worse": sum(1 for r in changed if r[f"delta_{obj}"] < 0),
                    "n_equal": sum(1 for r in changed if r[f"delta_{obj}"] == 0),
                }
            print(
                f"    {obj:<22} per pick state {md:>+8.2f}  95% CI {ci:<20} t={t:>6.2f}  "
                f"MDE {half:>6.2f}  seasons {block[obj]['seasons_won']}W/"
                f"{block[obj]['seasons_lost']}L  -> {block[obj]['classification']}"
            )
            if changed:
                c = block[obj]["changed_only"]
                print(
                    f"      conditional on a changed pick: {c['mean_per_changed_pick']:>+8.2f}  "
                    f"95% CI {c['ci']:<20} MDE {c['mde']}  "
                    f"{c['n_better']} better / {c['n_worse']} worse / {c['n_equal']} equal"
                )
        # phase and position breakdowns on the primary objective
        obj = objectives[0]
        by_phase = {}
        for label, _lo, _hi in PHASES:
            ph = [r for r in sub if r["phase"] == label]
            if not ph:
                continue
            ch = [r for r in ph if r["changed"]]
            by_phase[label] = {
                "n_states": len(ph),
                "n_changed": len(ch),
                "pct_changed": round(100 * len(ch) / len(ph), 1),
                "mean_delta_all_states": round(mean(r[f"delta_{obj}"] for r in ph), 2),
                "mean_delta_changed": (
                    round(mean(r[f"delta_{obj}"] for r in ch), 2) if ch else None
                ),
            }
            print(
                f"    {label:<14} states {len(ph):>4}  changed {len(ch):>4} "
                f"({by_phase[label]['pct_changed']:>5.1f}%)  mean delta "
                f"{by_phase[label]['mean_delta_all_states']:>+8.2f}  "
                f"(changed only {by_phase[label]['mean_delta_changed']})"
            )
        block["by_phase"] = by_phase
        by_pos: dict[str, dict] = defaultdict(
            lambda: {"y1_gave_up": 0, "ecr_took": 0, "delta": 0.0, "realized_delta": 0.0}
        )
        for r in changed:
            by_pos[r["y1_position"]]["y1_gave_up"] += 1
            by_pos[r["ecr_position"]]["ecr_took"] += 1
            by_pos[r["ecr_position"]]["delta"] += r[f"delta_{obj}"]
            by_pos[r["ecr_position"]]["realized_delta"] += r["ecr_realized"] - r["y1_realized"]
        block["by_position"] = {
            k: {kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in v.items()}
            for k, v in by_pos.items()
        }
        print("    position flow at changed picks (Y1 gave up -> ECR took):")
        for pos in sorted(by_pos):
            v = by_pos[pos]
            print(
                f"      {pos:<5} Y1 {v['y1_gave_up']:>4}  ECR {v['ecr_took']:>4}  "
                f"roster-value delta {v['delta']:>+9.1f}  raw realized delta "
                f"{v['realized_delta']:>+9.1f}"
            )
        # The relationship the brief asks for, measured rather than asserted.
        if changed:
            raw = sum(r["ecr_realized"] - r["y1_realized"] for r in changed)
            roster = sum(r[f"delta_{obj}"] for r in changed)
            block["pick_vs_roster"] = {
                "sum_raw_realized_delta_at_changed_picks": round(raw, 1),
                "sum_roster_value_delta_one_step": round(roster, 1),
                "conversion_ratio": round(roster / raw, 4) if raw else None,
                "n_picks_raw_better_but_roster_worse": sum(
                    1
                    for r in changed
                    if r["ecr_realized"] > r["y1_realized"] and r[f"delta_{obj}"] < 0
                ),
                "n_picks_raw_worse_but_roster_better": sum(
                    1
                    for r in changed
                    if r["ecr_realized"] < r["y1_realized"] and r[f"delta_{obj}"] > 0
                ),
            }
            print(
                f"    PICK-LEVEL vs ROSTER-LEVEL: raw realized delta at changed picks "
                f"{raw:>+9.1f}; one-step roster-value delta {roster:>+9.1f}; "
                f"conversion {block['pick_vs_roster']['conversion_ratio']}"
            )
            print(
                f"      picks where the raw player scored MORE but the roster got WORSE: "
                f"{block['pick_vs_roster']['n_picks_raw_better_but_roster_worse']}; "
                f"the reverse: {block['pick_vs_roster']['n_picks_raw_worse_but_roster_better']}"
            )
        entry["onestep"] = block

    # The question D114 exists to answer.
    print(
        f"\n{bar}\nDOES MATCHED-STATE PAIRING LOWER THE DETECTION FLOOR?  (common grid only)\n{bar}"
    )
    floor: dict = {}
    for league_name in formats:
        entry = summary["formats"].get(league_name, {})
        fr = entry.get("freerun_common_grid_1_4_7_10", {}).get(objectives[0], {})
        os_ = entry.get("onestep", {}).get(objectives[0], {})
        floor[league_name] = {
            "freerun_effect": fr.get("mean_per_draft"),
            "freerun_mde": fr.get("mde"),
            "onestep_effect_per_pick_state": os_.get("mean_per_pick_state"),
            "onestep_mde_per_pick_state": os_.get("mde"),
            "d97_quoted_floor": list(D97_DETECTION_FLOOR),
            "d104_published_effect": D104_PUBLISHED.get(league_name),
        }
        print(f"\n  {league_name}")
        print(
            f"    FREE-RUN (adopt ECR)      effect {fr.get('mean_per_draft')}  "
            f"MDE {fr.get('mde')}   vs D97's quoted floor {D97_DETECTION_FLOOR}"
        )
        print(
            f"    ONE-STEP (one pick)       effect {os_.get('mean_per_pick_state')}  "
            f"MDE {os_.get('mde')}  (per pick state -- a DIFFERENT estimand, not comparable "
            f"as a magnitude)"
        )
        print(
            f"    D104 published (HISTORICAL vintage ca3e2d8a...): "
            f"{D104_PUBLISHED.get(league_name)}"
        )
    summary["floor_comparison"] = floor
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--mode", required=True, choices=("audit", "freerun", "onestep", "report"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default=None, help="comma list; defaults per mode")
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument("--objectives", default=f"{SEASON_LONG},{WEEKLY_NO_FORESIGHT}")
    a = ap.parse_args()

    out = Path(a.out)
    formats = tuple(x for x in a.leagues.split(",") if x)
    objectives = tuple(x for x in a.objectives.split(",") if x)
    con = duckdb.connect(a.db, read_only=True)

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise UnreconstructibleError(f"{season} must never enter the historical evaluation")

    if a.mode == "audit":
        payload = run_audit(con)
        payload["provenance"] = _provenance(con, {"mode": "audit"})
        _write(out, "d114_audit.json", payload)
        print(json.dumps({k: v for k, v in payload.items() if k != "provenance"}, indent=1))
        return

    slots = (
        tuple(int(s) for s in a.slots.split(","))
        if a.slots
        else (FULL_SLOTS if a.mode == "freerun" else COMMON_SLOTS)
    )

    if a.mode == "freerun":
        rows = run_freerun(con, slots, formats, objectives)
        _write(
            out,
            "d114_freerun.json",
            {
                "provenance": _provenance(
                    con,
                    {
                        "mode": "freerun",
                        "slots": list(slots),
                        "leagues": list(formats),
                        "objectives": list(objectives),
                    },
                ),
                "rows": rows,
            },
        )
        return

    if a.mode == "onestep":
        rows = attach_realized(con, run_onestep(con, slots, formats, objectives))
        _write(
            out,
            "d114_onestep.json",
            {
                "provenance": _provenance(
                    con,
                    {
                        "mode": "onestep",
                        "slots": list(slots),
                        "leagues": list(formats),
                        "objectives": list(objectives),
                    },
                ),
                "rows": rows,
            },
        )
        return

    freerun = json.loads((out / "d114_freerun.json").read_text())["rows"]
    onestep = json.loads((out / "d114_onestep.json").read_text())["rows"]
    summary = report(freerun, onestep, objectives)
    summary["provenance"] = _provenance(con, {"mode": "report"})
    _write(out, "d114_summary.json", summary)


if __name__ == "__main__":
    main()
