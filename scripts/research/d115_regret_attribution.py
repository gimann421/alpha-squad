"""D115 -- where does Alpha's ~135 points of per-pick oracle regret actually go?

Read-only research runner. Opens the database read-only, calls the COMMITTED instruments
(`evaluation/draft_oracle.audit_draft` for regret, D104's `ecr_ordered_static`, D105's
`perturbed_static`, D103's `oracle_static`, `draft_forensics._calibrated_static` for the D99
X-arms), and writes nothing but JSON artifacts under `--out`. **No file under `src/alpha_squad/`
is touched by D115 and this script is imported by no production path.**

    uv run python scripts/research/d115_regret_attribution.py --mode audit  --out <dir>
    uv run python scripts/research/d115_regret_attribution.py --mode regret --out <dir>
    uv run python scripts/research/d115_regret_attribution.py --mode arms   --out <dir>
    uv run python scripts/research/d115_regret_attribution.py --mode report --out <dir>

==========================================================================================
PRE-REGISTRATION -- written before any D115 attribution number existed
==========================================================================================

THE QUESTION.  D103 measured ~135 realized starter points of regret at the average Alpha pick.
D114 showed the one-step matched-state estimator resolves ~13 points, i.e. about a tenth of it.
D115 spends that resolution on ATTRIBUTION: which positions, rounds, phases and decision shapes
that 135 is made of. **Attribution only. No model is built, fitted or tuned; nothing ships.**

WHICH "REGRET" -- a definitional correction, stated up front
-------------------------------------------------------------
D115's brief defines regret as `oracle player realized value - Alpha player realized value`.
**That is not the quantity the ~135 figure measures, and the two disagree by roughly an order of
magnitude** (D114 measured a 10.9% conversion from raw player points to roster value). D103's
regret -- the one that equals ~135 -- is a ROSTER-VALUE quantity:

    regret(s) = V(rollout after the oracle's pick) - V(rollout after Alpha's pick)

with a common continuation policy, which is exactly `OraclePick.regret` in the committed
instrument. D115 therefore reports:

  * PRIMARY   `regret_roster`  -- D103's definition, verbatim from `audit_draft`. This is the
              ~135 and every attribution table below is built on it.
  * SECONDARY `regret_raw`     -- the brief's formula, `oracle.realized_points -
              alpha.realized_points`, reported alongside so the relationship is visible rather
              than assumed.

Substituting the raw form for the primary would re-make the exact error D113 and D114 both
measured. Both are reported; neither is presented as the other.

WHICH ORACLE.  "The oracle-best available player at that exact draft state" is
`audit_draft`'s slate maximiser (`OraclePick.oracle`), which is what produced the ~135.
`ORACLE_Y1` -- the Y1 *rule* reading realized points as its projections -- is a whole-draft ARM,
and it appears in D115 only in the arm-recovery section, where the brief lists it. The two are
different objects and are never interchanged.

THE ATTRIBUTION, fixed before any run
---------------------------------------
Disjoint and exhaustive over picks with a measured regret:

  A  WRONG PLAYER, RIGHT POSITION   oracle.position == alpha.position
  B  WRONG POSITION                 oracle.position != alpha.position
  D  UNCLASSIFIED                   alpha or oracle missing, position UNKNOWN, or regret < 0

C  TIMING / AVAILABILITY is **an overlay, not a fourth bucket**, because it genuinely overlaps A
and B and the brief forbids forcing ambiguous cases. It is measured, on the same picks, as two
mechanical facts about the next pick Alpha actually owns:

  C1  the ORACLE's player is still on the board at Alpha's next pick  -> the value was
      available later, so this pick's regret was recoverable by SEQUENCING rather than lost;
  C2  ALPHA's own player is still on the board at Alpha's next pick   -> Alpha reached for
      someone who would have survived.

Every table reports A/B/D as the partition and C1/C2 as overlays with their overlap stated.

POPULATION.  D103's own grid, unchanged: seasons 2021-2025 (2020 refused, D95/D96), slots
(1, 4, 7, 10), all 16 rounds, formats `target_league` and `dynasty_1qb`. Target and dynasty are
reported separately and never pooled. Independent unit = SEASON (k = 5), t_crit = 2.776.

PHASES.  The brief's EARLY 1-6 / MIDDLE 7-11 / LATE 12-16, with D103's own 1-5 / 6-10 / 11-16
reported alongside so the two records stay comparable.

THE ARMS.  Each existing arm is asked, at every Alpha pick state, what it would pick; the
one-step value of that substitution is measured against Alpha's own rollout with a COMMON
continuation (the shipped policy on Y1's board), exactly as D114 did. Recovery is
`mean(delta_arm) / mean(regret_roster)`.

  Y1        the control; must recover exactly 0 by construction (a null check)
  FP_ECR_Y1 D104's ECR arm, imported
  X2, X3    D99/D68's walk-forward calibration arms, via `_calibrated_static`
  L1..L4    D105's perturbation ladder (seed `SEEDS[0]`). These DEGRADE Y1's ordering by
            construction, so they bound the DOWNSIDE slope; a negative recovery is the expected
            result and is not a failure.
  ORACLE_Y1 D103's realized-points arm

An arm's board is used ONLY to choose the pick, never to score it -- which is what keeps a
perturbed or calibrated board from moving the audited states or the oracle (the confound D105
section 68 names explicitly).

WHAT D115 MAY NOT DO.  No NAIVE arm is recreated (D114 established it has never existed). No new
arm, feature, weight or model is introduced. No component is tuned. Correlations between regret
and Alpha's own score components are reported as ASSOCIATIONS only; the runner prints a
causality disclaimer next to every one of them.
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
    X_TIER_SPEC,
    _calibrated_static,
    _pick_by_tier,
    load_residual_rows,
    load_season_static,
    preseason_page_type,
)
from alpha_squad.evaluation.draft_oracle import (
    SEASON_LONG,
    SHIPPED_TIER,
    assert_no_realized_inputs_in_policy,
    audit_draft,
    draft_order,
    make_roster_scorer,
    rollout,
)
from alpha_squad.evaluation.draft_simulation import (
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
)
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.league.context import resolve_league
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"

#: D103's grid, unchanged.
FORMATS = ("target_league", "dynasty_1qb")
PRIMARY_FORMAT = "target_league"
DEFAULT_SLOTS = (1, 4, 7, 10)

#: The brief's phases, plus D103's own for comparability.
PHASES: tuple[tuple[str, int, int], ...] = (("R1-6", 1, 6), ("R7-11", 7, 11), ("R12-16", 12, 16))
D103_PHASES: tuple[tuple[str, int, int], ...] = (
    ("EARLY 1-5", 1, 5),
    ("MIDDLE 6-10", 6, 10),
    ("LATE 11-16", 11, 16),
)

#: Quoted, never re-derived.
D97_DETECTION_FLOOR = (172.0, 250.0)
ECONOMIC_THRESHOLD = 25.0
D103_MEAN_REGRET_TARGET = 134.8  # HISTORICAL vintage ca3e2d8a...
D103_TO_D105_VINTAGE = "ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99"
#: D114's measured one-step resolution, quoted as the yardstick for "is this attributable".
D114_ONESTEP_MDE = (12.75, 13.37)

ARM_ORDER = ("Y1", "FP_ECR_Y1", "X2", "X3", "L1", "L2", "L3", "L4", "ORACLE_Y1")

#: Files whose PURPOSE is to record that D97's NAIVE arm does not exist; they necessarily mention
#: the string, so a bare history search over `*.py` matches the guard itself. D114's first version
#: of this check did exactly that and started failing the moment D114 was committed -- fixed in
#: D115 and kept in step with `tests/unit/test_d114_matched_state.py::GUARD_FILES`.
NAIVE_GUARD_EXCLUSIONS = (
    "scripts/research/d114_matched_state.py",
    "tests/unit/test_d114_matched_state.py",
    "scripts/research/d115_regret_attribution.py",
    "tests/unit/test_d115_regret_attribution.py",
)


class UnreconstructibleError(RuntimeError):
    """Raised when an input cannot be rebuilt from the current checkout without inventing it,
    or when a harness invariant fails. D115 stops rather than substituting."""


def _load(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D103 = _load("d103_pick_regret")
D104 = _load("d104_ecr_floor")
D105 = _load("d105_objective_sensitivity")


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
        "objective": SEASON_LONG,
        "seasons": list(BACKTEST_SEASONS),
        "d97_detection_floor": list(D97_DETECTION_FLOOR),
        "d114_onestep_mde": list(D114_ONESTEP_MDE),
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


def _phase_of(round_no: int, phases=PHASES) -> str:
    for label, lo, hi in phases:
        if lo <= round_no <= hi:
            return label
    return "?"


# --------------------------------------------------------------------------------------------
# MODE: audit -- what is reconstructible, before any measurement
# --------------------------------------------------------------------------------------------
def run_audit(con: duckdb.DuckDBPyConnection) -> dict:
    vintage = compute_board_vintage(con)
    naive_in_code = _shell(
        [
            "git",
            "log",
            "--all",
            "--oneline",
            "-S",
            "NAIVE",
            "--",
            "*.py",
            *(f":(exclude){rel}" for rel in NAIVE_GUARD_EXCLUSIONS),
        ]
    )
    return {
        "head": _git_head(),
        "head_subject": _shell(["git", "log", "-1", "--format=%s"]),
        "board_vintage_combined": vintage.combined_hash,
        "board_vintage_per_season": {str(s): h for s, h in sorted(vintage.season_hashes.items())},
        "upstream_board_sha256": vintage.board_sha256,
        "upstream_idmap_sha256": vintage.idmap_sha256,
        "vintage_matches_d103_to_d105": vintage.combined_hash == D103_TO_D105_VINTAGE,
        "regret_instrument": {
            "function": "alpha_squad.evaluation.draft_oracle.audit_draft",
            "committed": True,
            "primary_definition": "OraclePick.regret = oracle.rollout_starter_points - "
            "alpha.rollout_starter_points (D103; this is the ~135)",
            "secondary_definition": "oracle.realized_points - alpha.realized_points "
            "(the brief's formula; a DIFFERENT quantity, reported alongside)",
            "d103_published_mean_regret_target": D103_MEAN_REGRET_TARGET,
        },
        "arms": {
            "Y1": {"source": "SHIPPED_TIER control", "reconstructible": True},
            "FP_ECR_Y1": {
                "source": "d104_ecr_floor.ecr_ordered_static",
                "reconstructible": hasattr(D104, "ecr_ordered_static"),
            },
            "X2": {
                "source": f"draft_forensics._calibrated_static, arm={X_TIER_SPEC.get('X2')}",
                "reconstructible": "X2" in X_TIER_SPEC,
            },
            "X3": {
                "source": f"draft_forensics._calibrated_static, arm={X_TIER_SPEC.get('X3')}",
                "reconstructible": "X3" in X_TIER_SPEC,
            },
            "L1..L4": {
                "source": f"d105_objective_sensitivity.perturbed_static, levels={D105.LEVELS}, "
                f"seed={D105.SEEDS[0]}",
                "reconstructible": hasattr(D105, "perturbed_static"),
                "note": "these DEGRADE Y1's ordering by construction -- they bound the downside "
                "slope, they are not improvement candidates",
            },
            "ORACLE_Y1": {
                "source": "d103_pick_regret.oracle_static",
                "reconstructible": hasattr(D103, "oracle_static"),
            },
            "NAIVE": {
                "source": "does not exist",
                "reconstructible": False,
                "git_log_all_S_NAIVE": naive_in_code or "<none>",
                "note": "D114 established this; D115 does not recreate it",
            },
        },
    }


# --------------------------------------------------------------------------------------------
# The cheap deterministic replay -- availability and score components at Alpha's own pick states
# --------------------------------------------------------------------------------------------
def replay_states(con, league, season, static, slot) -> list[dict]:
    """Replay the SAME draft `audit_draft` walks, without any rollouts, recording at each of our
    picks: the available pool, the pick, and the shipped engine's own score components for it.

    `audit_draft` returns neither the availability at the NEXT pick (needed for the C overlay)
    nor the score components (needed for the association section), and D115 will not modify a
    committed instrument to get them. Determinism makes this safe: the opponents and the engine
    are both functions of `static`, so replaying produces the identical trajectory -- which
    `attach_replay` then ASSERTS pick-for-pick against `audit_draft`'s own record rather than
    assuming.
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
        alpha_pick, scored = _pick_by_tier(
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
        chosen = next((c for c in scored if c.player_id == alpha_pick), None)
        states.append(
            {
                "round": round_no,
                "overall_pick": current,
                "next_pick": nxt,
                "picks_remaining": picks_remaining,
                "available": set(avail),
                "drafted": list(mine),
                "opponents": {s: list(v) for s, v in opps.items()},
                "alpha_pick": alpha_pick,
                "components": None
                if chosen is None
                else {
                    "projection": chosen.projection,
                    "vorp": chosen.vorp,
                    "roster_need": chosen.roster_need,
                    "fit_multiplier": chosen.fit_multiplier,
                    "confidence": chosen.confidence,
                    "survival_probability": chosen.survival_probability,
                    "opportunity_cost_pts": chosen.opportunity_cost_pts,
                    "marginal_starter_value": chosen.marginal_starter_value,
                    "score": chosen.score,
                },
            }
        )
        mine.append(alpha_pick)
        avail.discard(alpha_pick)
    return states


def attach_replay(audited, states) -> list[dict]:
    """Join `audit_draft`'s records to the replay, asserting the two walked the same draft."""
    by_pick = {s["overall_pick"]: s for s in states}
    if len(audited) != len(states):
        raise UnreconstructibleError(
            f"replay saw {len(states)} picks, audit_draft saw {len(audited)}"
        )
    joined = []
    for record in audited:
        state = by_pick.get(record.pick_overall)
        if state is None:
            raise UnreconstructibleError(f"replay has no state at pick {record.pick_overall}")
        alpha = record.alpha
        if alpha is None or alpha.player_id != state["alpha_pick"]:
            raise UnreconstructibleError(
                f"replay chose {state['alpha_pick']!r} but audit_draft chose "
                f"{None if alpha is None else alpha.player_id!r} at pick {record.pick_overall} "
                "-- the two are not walking the same draft, so no D115 number is usable"
            )
        joined.append((record, state))
    return joined


# --------------------------------------------------------------------------------------------
# MODE: regret -- audit every pick and attribute it
# --------------------------------------------------------------------------------------------
def classify(alpha_position: str | None, oracle_position: str | None, regret: float) -> str:
    """The pre-registered A/B/D partition, as a function so it can be tested rather than trusted.

    Disjoint and exhaustive by construction. `C` is deliberately NOT here: timing/availability
    overlaps both A and B, so forcing it into this partition would mean assigning picks to a
    category they only partly belong to -- which the brief forbids. It is recorded separately as
    the C1/C2 flags on the same rows.
    """
    if alpha_position is None or oracle_position is None:
        return "D_unclassified"
    if "UNKNOWN" in (alpha_position, oracle_position):
        return "D_unclassified"
    if regret < 0:
        # The oracle maximises over a slate that always contains Alpha's own pick, so this
        # cannot happen; if it ever does, the instrument is wrong and the pick must not be
        # silently attributed to A or B.
        return "D_unclassified"
    if alpha_position == oracle_position:
        return "A_wrong_player_right_position"
    return "B_wrong_position"


def _availability_at_next_pick(states, index) -> set[str] | None:
    """The pool Alpha faces at its NEXT pick, or None if this was the last one."""
    if index + 1 >= len(states):
        return None
    return states[index + 1]["available"]


def run_regret(con, slots, formats) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            for slot in slots:
                audited = audit_draft(con, league, season, slot, static)
                states = replay_states(con, league, season, static, slot)
                joined = attach_replay(audited, states)
                for index, (record, state) in enumerate(joined):
                    alpha, oracle = record.alpha, record.oracle
                    next_pool = _availability_at_next_pick(states, index)
                    regret = record.regret
                    category = classify(
                        None if alpha is None else alpha.position,
                        None if oracle is None else oracle.position,
                        regret,
                    )
                    rows.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "round": record.round_no,
                            "overall_pick": record.pick_overall,
                            "phase": _phase_of(record.round_no),
                            "phase_d103": _phase_of(record.round_no, D103_PHASES),
                            "n_candidates": len(record.candidates),
                            "alpha_player": alpha.player_id,
                            "alpha_position": alpha.position,
                            "alpha_realized": alpha.realized_points,
                            "alpha_projection": alpha.projection,
                            "alpha_rollout": alpha.rollout_starter_points,
                            "oracle_player": oracle.player_id,
                            "oracle_position": oracle.position,
                            "oracle_realized": oracle.realized_points,
                            "oracle_projection": oracle.projection,
                            "oracle_rollout": oracle.rollout_starter_points,
                            "oracle_alpha_rank": oracle.alpha_rank,
                            # PRIMARY: D103's roster-value regret -- this is the ~135.
                            "regret_roster": regret,
                            # SECONDARY: the brief's raw-player formula. A different quantity.
                            "regret_raw": oracle.realized_points - alpha.realized_points,
                            "category": category,
                            # C overlays -- never a bucket, always a flag.
                            "C1_oracle_survives_to_next_pick": (
                                None if next_pool is None else oracle.player_id in next_pool
                            ),
                            "is_last_pick": next_pool is None,
                            "components": state["components"],
                        }
                    )
                print(
                    f"  regret {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows


# --------------------------------------------------------------------------------------------
# MODE: arms -- one-step recovery of the measured regret, per existing arm
# --------------------------------------------------------------------------------------------
def _arm_statics(con, league, season, static, residual_rows):
    """{arm: the board that arm CHOOSES with}. Every one is a committed construction, imported.

    The arm's board is used only to pick; scoring always happens on Y1's board, so a perturbed
    or calibrated board can never move the audited states or the oracle.
    """
    arms = {"Y1": static, "FP_ECR_Y1": D104.ecr_ordered_static(league, static)[0]}
    for tier in ("X2", "X3"):
        arms[tier] = _calibrated_static(
            con, league, season, X_TIER_SPEC[tier], residual_rows, static
        )
    for name, alpha in D105.LEVELS.items():
        if name == "L0":
            continue
        arms[name] = D105.perturbed_static(league, static, alpha, D105.SEEDS[0])
    arms["ORACLE_Y1"] = D103.oracle_static(con, league, season, static)
    return arms


def survives_counterfactual(
    con, league, season, static, slot, state, taken_instead: str, subject: str
) -> bool | None:
    """Had Alpha taken `taken_instead` at this state, would `subject` still be on the board at
    Alpha's next pick?

    This is the ONLY honest way to ask "did Alpha pick too early". The naive form -- is Alpha's
    own player in the pool at the next pick -- is vacuously False for every pick in every draft,
    because Alpha removed him by drafting him. D115 shipped that naive form in its first regret
    run, measured 0 of 300 picks, and replaced it here; the report documents the correction.

    The opponents are stepped forward with `roster_aware_market_pick`, the same deterministic
    field the real draft uses, from the same rosters, so the only thing that differs from the
    observed draft is which player Alpha removed.
    """
    next_pick = state["next_pick"]
    if next_pick is None:
        return None
    total_rounds = int(league.roster.get("roster_size", 0))
    avail = set(state["available"]) - {taken_instead}
    opps = {s: list(v) for s, v in state["opponents"].items()}
    for current, round_no, seat in draft_order(league):
        if current <= state["overall_pick"] or current >= next_pick:
            continue
        if not avail:
            break
        if seat == slot:
            continue
        pick = roster_aware_market_pick(
            avail,
            static.market_rank,
            static.positions,
            league,
            opps[seat],
            total_rounds - round_no + 1,
        )
        opps[seat].append(static.positions.get(pick, "UNKNOWN"))
        avail.discard(pick)
    return subject in avail


def run_timing(con, slots, formats, regret_rows: list[dict]) -> list[dict]:
    """The C overlays, computed cheaply from the regret run's own picks -- no rollouts needed.

    C1 is observational (the real draft already shows whether the oracle's man survived). C2 is
    the counterfactual above. Both are recorded per pick so the report can state their overlap
    with A and B instead of forcing timing into the disjoint partition.
    """
    by_key = {(r["league"], r["season"], r["slot"], r["overall_pick"]): r for r in regret_rows}
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            for slot in slots:
                states = replay_states(con, league, season, static, slot)
                for index, state in enumerate(states):
                    key = (league_name, season, slot, state["overall_pick"])
                    row = by_key.get(key)
                    if row is None:
                        raise UnreconstructibleError(
                            f"no regret row for {key}; run --mode regret on the same grid first"
                        )
                    if row["alpha_player"] != state["alpha_pick"]:
                        raise UnreconstructibleError(
                            f"regret table has {row['alpha_player']!r} at {key} but the replay "
                            f"picked {state['alpha_pick']!r} -- not the same draft"
                        )
                    next_pool = _availability_at_next_pick(states, index)
                    oracle = row["oracle_player"]
                    rows.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "overall_pick": state["overall_pick"],
                            "round": state["round"],
                            "is_last_pick": next_pool is None,
                            # Observational: Alpha took its own man; did the oracle's survive?
                            "C1_oracle_survives_to_next_pick": (
                                None if next_pool is None else oracle in next_pool
                            ),
                            # Counterfactual: had Alpha taken the oracle's man, would Alpha's
                            # own choice have survived?
                            "C2_alpha_survives_if_oracle_taken": (
                                None
                                if next_pool is None or oracle == state["alpha_pick"]
                                else survives_counterfactual(
                                    con,
                                    league,
                                    season,
                                    static,
                                    slot,
                                    state,
                                    oracle,
                                    state["alpha_pick"],
                                )
                            ),
                        }
                    )
                print(
                    f"  timing {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows


def roll_from_state(con, league, season, static, slot, state, pick, realized, scorer) -> float:
    """Finish the draft from `state` having taken `pick`, and return its realized starter points.

    Module level and fully parameterised rather than a closure inside the grid loop: a closure
    over loop variables is the classic late-binding bug, and every arm-recovery number runs
    through this call. Its arguments mirror `audit_draft`'s own rollout exactly -- same shipped
    continuation, same opponents, same realized table, same scorer -- which is what lets an arm's
    value be differenced against a rollout that instrument produced.
    """
    return rollout(
        con,
        league,
        season,
        static,
        draft_slot=slot,
        after_pick_overall=state["overall_pick"],
        available=state["available"] - {pick},
        drafted=[*state["drafted"], pick],
        opponent_rosters=state["opponents"],
        actual=realized,
        scorer=scorer,
    )[0]


def run_arms(con, slots, formats, regret_rows: list[dict]) -> list[dict]:
    """One-step recovery per arm, reusing the regret run's own numbers.

    Alpha's rollout value at each state is READ from the regret table rather than recomputed, so
    the denominator of every recovery figure is literally the same number the attribution tables
    are built on. `audit_draft` is therefore not re-run here -- it costs ~80 s per draft and would
    only reproduce values already on disk. The reuse is verified rather than trusted: at the first
    state of every draft the runner recomputes Alpha's own rollout through `rollout` and raises if
    it disagrees with the stored value.
    """
    alpha_rollout = {
        (r["league"], r["season"], r["slot"], r["overall_pick"]): (
            r["alpha_rollout"],
            r["alpha_player"],
        )
        for r in regret_rows
    }
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        residual_rows = load_residual_rows(con, league, list(BACKTEST_SEASONS))
        for season in BACKTEST_SEASONS:
            static = _static_for(con, league, season)
            scorer = make_roster_scorer(SEASON_LONG, league, static)
            arms = _arm_statics(con, league, season, static, residual_rows)
            realized = _actual_points_for(con, season, sorted(static.projections))
            for slot in slots:
                states = replay_states(con, league, season, static, slot)
                for index, state in enumerate(states):
                    key = (league_name, season, slot, state["overall_pick"])
                    if key not in alpha_rollout:
                        raise UnreconstructibleError(
                            f"no regret row for {key}; run --mode regret on the same grid first"
                        )
                    base, stored_pick = alpha_rollout[key]
                    if stored_pick != state["alpha_pick"]:
                        raise UnreconstructibleError(
                            f"regret table has {stored_pick!r} at {key} but the replay picked "
                            f"{state['alpha_pick']!r} -- the two runs are not the same draft"
                        )

                    if index == 0:
                        check = roll_from_state(
                            con,
                            league,
                            season,
                            static,
                            slot,
                            state,
                            state["alpha_pick"],
                            realized,
                            scorer,
                        )
                        if abs(check - base) > 1e-6:
                            raise UnreconstructibleError(
                                f"recomputed Alpha rollout {check} != stored {base} at {key} -- "
                                "the arm harness and audit_draft are not scoring the same draft"
                            )
                    for arm_name in ARM_ORDER:
                        pick, _ = _pick_by_tier(
                            arms[arm_name],
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
                        changed = pick != state["alpha_pick"]
                        delta = (
                            (
                                roll_from_state(
                                    con,
                                    league,
                                    season,
                                    static,
                                    slot,
                                    state,
                                    pick,
                                    realized,
                                    scorer,
                                )
                                - base
                            )
                            if changed
                            else 0.0
                        )
                        rows.append(
                            {
                                "league": league_name,
                                "season": season,
                                "slot": slot,
                                "round": state["round"],
                                "phase": _phase_of(state["round"]),
                                "arm": arm_name,
                                "arm_pick": pick,
                                "arm_position": static.positions.get(pick, "UNKNOWN"),
                                "changed": changed,
                                "delta": delta,
                                "alpha_rollout": base,
                            }
                        )
                print(
                    f"  arms {league_name} {season} slot {slot} ({time.time() - t0:.0f}s)",
                    flush=True,
                )
    return rows


# --------------------------------------------------------------------------------------------
# Statistics
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


def _season_ci(rows: list[dict], field: str):
    """Per-season mean of `field`, then a season-clustered interval over k=5."""
    per_season = _by_season([(r["season"], r[field]) for r in rows])
    return per_season, _ci(list(per_season.values()))


def _gini(values: list[float]) -> float:
    """Concentration of a non-negative quantity. 0 = perfectly even, 1 = all in one pick."""
    vals = sorted(max(0.0, v) for v in values)
    n = len(vals)
    total = sum(vals)
    if n == 0 or total == 0:
        return float("nan")
    cum = sum((i + 1) * v for i, v in enumerate(vals))
    return (2 * cum) / (n * total) - (n + 1) / n


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


CATEGORIES = ("A_wrong_player_right_position", "B_wrong_position", "D_unclassified")


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
def group_regret(rows: list[dict], total: float, field: str, label: str, order=None) -> dict:
    """Total / per-pick / share of regret for each value of `field`, with the A and B split.

    Module level and fully parameterised rather than nested in `report`: a closure over the
    enclosing loop's `rows` is the classic late-binding bug, and this table is the phase's
    primary output.
    """
    groups: dict = {}
    keys = order or sorted({r[field] for r in rows})
    print(f"\n  BY {label.upper()}")
    print(
        f"    {label:<14}{'picks':>7}{'total':>12}{'per pick':>10}{'% regret':>10}"
        f"{'A%':>7}{'B%':>7}"
    )
    for key in keys:
        rows_k = [r for r in rows if r[field] == key]
        if not rows_k:
            continue
        tot = sum(r["regret_roster"] for r in rows_k)
        a = sum(
            r["regret_roster"] for r in rows_k if r["category"] == "A_wrong_player_right_position"
        )
        b = sum(r["regret_roster"] for r in rows_k if r["category"] == "B_wrong_position")
        groups[str(key)] = {
            "n_picks": len(rows_k),
            "total_regret": round(tot, 1),
            "per_pick": round(tot / len(rows_k), 1),
            "pct_of_regret": round(100 * tot / total, 1) if total else None,
            "pct_A": round(100 * a / tot, 1) if tot else None,
            "pct_B": round(100 * b / tot, 1) if tot else None,
        }
        g = groups[str(key)]
        print(
            f"    {str(key):<14}{len(rows_k):>7}{tot:>12,.0f}{g['per_pick']:>10.1f}"
            f"{g['pct_of_regret']:>9.1f}%{g['pct_A']:>6.0f}%{g['pct_B']:>6.0f}%"
        )
    return groups


def report(regret_rows: list[dict], arm_rows: list[dict], timing_rows: list[dict]) -> dict:
    bar = "=" * 100
    summary: dict = {"formats": {}}
    formats = [f for f in FORMATS if any(r["league"] == f for r in regret_rows)]

    for league_name in formats:
        sub = [r for r in regret_rows if r["league"] == league_name]
        entry = summary["formats"].setdefault(league_name, {})
        total = sum(r["regret_roster"] for r in sub)
        total_raw = sum(r["regret_raw"] for r in sub)
        n_drafts = len({(r["season"], r["slot"]) for r in sub})
        print(f"\n{bar}\nWHERE THE ~135 POINTS/PICK GOES -- {league_name}\n{bar}")
        print(
            f"  {len(sub)} audited picks over {n_drafts} drafts; mean slate "
            f"{mean(r['n_candidates'] for r in sub):.1f} candidates"
        )
        per_season, (md, t, ci, half) = _season_ci(sub, "regret_roster")
        print(
            f"  PRIMARY  regret_roster (D103's definition): mean {md:.1f}/pick  95% CI {ci}  "
            f"MDE {half:.1f}   total {total:,.0f}"
        )
        print("           by season: " + "  ".join(f"{s}:{v:.0f}" for s, v in per_season.items()))
        praw, (mdraw, _t, ciraw, _h) = _season_ci(sub, "regret_raw")
        print(
            f"  SECONDARY regret_raw (the brief's formula): mean {mdraw:.1f}/pick  95% CI "
            f"{ciraw}   total {total_raw:,.0f}   -- a DIFFERENT quantity; conversion "
            f"{total / total_raw:.3f}"
            if total_raw
            else ""
        )
        entry["overall"] = {
            "n_picks": len(sub),
            "n_drafts": n_drafts,
            "mean_regret_roster": round(md, 1),
            "ci": ci,
            "mde": None if half != half else round(half, 1),
            "total_regret_roster": round(total, 1),
            "mean_regret_raw": round(mdraw, 1),
            "total_regret_raw": round(total_raw, 1),
            "raw_to_roster_conversion": round(total / total_raw, 4) if total_raw else None,
            "per_season": {str(s): round(v, 1) for s, v in per_season.items()},
            "d103_published_mean_regret": D103_MEAN_REGRET_TARGET,
        }

        # ---- the ranked attribution table -------------------------------------------------
        print("\n  RANKED ATTRIBUTION (A/B/D are disjoint and exhaustive)")
        print(
            f"    {'category':<32}{'picks':>7}{'% picks':>9}{'total':>12}{'per pick':>10}"
            f"{'% regret':>10}{'95% CI':>22}"
        )
        cats: dict = {}
        for cat in CATEGORIES:
            rows_c = [r for r in sub if r["category"] == cat]
            if not rows_c:
                cats[cat] = {"n_picks": 0, "total_regret": 0.0, "pct_of_regret": 0.0}
                continue
            tot = sum(r["regret_roster"] for r in rows_c)
            # Per-season SHARE of the draft's total regret, so the interval is on the
            # attribution rather than on the conditional mean.
            share_by_season = _by_season(
                [
                    (
                        s,
                        sum(
                            r["regret_roster"]
                            for r in sub
                            if r["season"] == s and r["category"] == cat
                        )
                        / max(1e-9, sum(r["regret_roster"] for r in sub if r["season"] == s)),
                    )
                    for s in sorted({r["season"] for r in sub})
                ]
            )
            _mdsh, _tsh, cish, halfsh = _ci([v * 100 for v in share_by_season.values()])
            cats[cat] = {
                "n_picks": len(rows_c),
                "pct_picks": round(100 * len(rows_c) / len(sub), 1),
                "total_regret": round(tot, 1),
                "per_pick": round(tot / len(rows_c), 1),
                "pct_of_regret": round(100 * tot / total, 1) if total else None,
                "share_ci_pct": cish,
                "share_mde_pct": None if halfsh != halfsh else round(halfsh, 1),
                "per_season_share_pct": {
                    str(s): round(100 * v, 1) for s, v in share_by_season.items()
                },
            }
            print(
                f"    {cat:<32}{len(rows_c):>7}{cats[cat]['pct_picks']:>8.1f}%"
                f"{tot:>12,.0f}{cats[cat]['per_pick']:>10.1f}"
                f"{cats[cat]['pct_of_regret']:>9.1f}%{cish:>22}"
            )
        entry["attribution"] = cats

        # ---- C overlays --------------------------------------------------------------------
        timing_by_key = {
            (r["league"], r["season"], r["slot"], r["overall_pick"]): r for r in timing_rows
        }
        for r in sub:
            tim = timing_by_key.get((r["league"], r["season"], r["slot"], r["overall_pick"]))
            if tim is not None:
                r["C1_oracle_survives_to_next_pick"] = tim["C1_oracle_survives_to_next_pick"]
                r["C2_alpha_survives_if_oracle_taken"] = tim["C2_alpha_survives_if_oracle_taken"]
        scored = [r for r in sub if not r["is_last_pick"]]
        print(
            f"\n  C OVERLAYS (not a bucket -- these OVERLAP A and B; {len(scored)} non-final picks)"
        )
        overlays: dict = {}
        for flag, label in (
            ("C1_oracle_survives_to_next_pick", "C1 oracle's player survives to my next pick"),
            (
                "C2_alpha_survives_if_oracle_taken",
                "C2 Alpha's man survives IF the oracle's is taken",
            ),
        ):
            hit = [r for r in scored if r[flag]]
            tot = sum(r["regret_roster"] for r in hit)
            overlays[flag] = {
                "n_picks": len(hit),
                "pct_picks": round(100 * len(hit) / len(scored), 1) if scored else None,
                "total_regret": round(tot, 1),
                "pct_of_regret": round(100 * tot / total, 1) if total else None,
                "per_pick": round(tot / len(hit), 1) if hit else None,
                "overlap_with_A": sum(
                    1 for r in hit if r["category"] == "A_wrong_player_right_position"
                ),
                "overlap_with_B": sum(1 for r in hit if r["category"] == "B_wrong_position"),
            }
            o = overlays[flag]
            print(
                f"    {label:<48}{o['n_picks']:>6} picks ({o['pct_picks']:>5.1f}%)  "
                f"{o['pct_of_regret']:>5.1f}% of regret   A:{o['overlap_with_A']} B:{o['overlap_with_B']}"
            )
        both = [
            r
            for r in scored
            if r["C1_oracle_survives_to_next_pick"] and r.get("C2_alpha_survives_if_oracle_taken")
        ]
        overlays["C1_and_C2"] = {
            "n_picks": len(both),
            "pct_of_regret": round(100 * sum(r["regret_roster"] for r in both) / total, 1)
            if total
            else None,
        }
        print(
            f"    {'C1 AND C2 both (pure sequencing, nothing contested)':<48}"
            f"{len(both):>6} picks           "
            f"{overlays['C1_and_C2']['pct_of_regret']:>5.1f}% of regret"
        )
        entry["C_overlays"] = overlays

        # ---- by position, round, phase, season ---------------------------------------------
        entry["by_alpha_position"] = group_regret(sub, total, "alpha_position", "alpha position")
        entry["by_round"] = group_regret(
            sub, total, "round", "round", order=sorted({r["round"] for r in sub})
        )
        entry["by_phase"] = group_regret(sub, total, "phase", "phase", order=[p[0] for p in PHASES])
        entry["by_phase_d103"] = group_regret(
            sub, total, "phase_d103", "phase_d103", order=[p[0] for p in D103_PHASES]
        )
        entry["by_season"] = group_regret(
            sub, total, "season", "season", order=sorted({r["season"] for r in sub})
        )

        # ---- concentration ------------------------------------------------------------------
        vals = sorted((r["regret_roster"] for r in sub), reverse=True)
        n = len(vals)
        conc = {
            "gini": round(_gini(vals), 3),
            "top_1pct_share": round(100 * sum(vals[: max(1, n // 100)]) / total, 1),
            "top_5pct_share": round(100 * sum(vals[: max(1, n // 20)]) / total, 1),
            "top_10pct_share": round(100 * sum(vals[: max(1, n // 10)]) / total, 1),
            "top_25pct_share": round(100 * sum(vals[: max(1, n // 4)]) / total, 1),
            "median_regret": round(vals[n // 2], 1),
            "mean_regret": round(total / n, 1),
            "max_regret": round(vals[0], 1),
            "n_picks_above_2x_mean": sum(1 for v in vals if v > 2 * total / n),
            "n_picks_below_d114_mde": sum(1 for v in vals if v < D114_ONESTEP_MDE[1]),
        }
        entry["concentration"] = conc
        print(
            f"\n  CONCENTRATION  gini {conc['gini']}   median {conc['median_regret']} vs mean "
            f"{conc['mean_regret']}"
        )
        print(
            f"    top 1% of picks hold {conc['top_1pct_share']}% of regret; top 5% "
            f"{conc['top_5pct_share']}%; top 10% {conc['top_10pct_share']}%; top 25% "
            f"{conc['top_25pct_share']}%"
        )
        print(
            f"    {conc['n_picks_above_2x_mean']} picks above 2x mean; "
            f"{conc['n_picks_below_d114_mde']} of {n} picks carry less regret than D114's "
            f"{D114_ONESTEP_MDE[1]}-point resolution"
        )

        # ---- rounds 1-3 ----------------------------------------------------------------------
        early3 = [r for r in sub if r["round"] <= 3]
        if early3:
            tot3 = sum(r["regret_roster"] for r in early3)
            _ps3, (md3, _t3, ci3, half3) = _season_ci(early3, "regret_roster")
            entry["rounds_1_3"] = {
                "n_picks": len(early3),
                "total_regret": round(tot3, 1),
                "per_pick": round(tot3 / len(early3), 1),
                "pct_of_regret": round(100 * tot3 / total, 1) if total else None,
                "ci": ci3,
                "mde": None if half3 != half3 else round(half3, 1),
                "pct_A": round(
                    100
                    * sum(
                        r["regret_roster"]
                        for r in early3
                        if r["category"] == "A_wrong_player_right_position"
                    )
                    / tot3,
                    1,
                )
                if tot3
                else None,
            }
            e3 = entry["rounds_1_3"]
            print(
                f"\n  ROUNDS 1-3 (highest leverage): {len(early3)} picks, {e3['per_pick']} "
                f"per pick, {e3['pct_of_regret']}% of all regret, 95% CI {ci3}, "
                f"{e3['pct_A']}% category A"
            )

        # ---- RB/WR/TE cross-position ----------------------------------------------------------
        flex = ("RB", "WR", "TE")
        cross = [
            r
            for r in sub
            if r["category"] == "B_wrong_position"
            and r["alpha_position"] in flex
            and r["oracle_position"] in flex
        ]
        flow: dict = defaultdict(lambda: {"n": 0, "regret": 0.0})
        for r in cross:
            flow[f"{r['alpha_position']}->{r['oracle_position']}"]["n"] += 1
            flow[f"{r['alpha_position']}->{r['oracle_position']}"]["regret"] += r["regret_roster"]
        entry["rb_wr_te_cross"] = {
            "n_picks": len(cross),
            "total_regret": round(sum(r["regret_roster"] for r in cross), 1),
            "pct_of_regret": round(100 * sum(r["regret_roster"] for r in cross) / total, 1)
            if total
            else None,
            "flows": {
                k: {"n": v["n"], "regret": round(v["regret"], 1)}
                for k, v in sorted(flow.items(), key=lambda kv: -kv[1]["regret"])
            },
        }
        print(
            f"\n  RB/WR/TE CROSS-POSITION: {len(cross)} picks, "
            f"{entry['rb_wr_te_cross']['pct_of_regret']}% of all regret"
        )
        for k, v in list(entry["rb_wr_te_cross"]["flows"].items())[:8]:
            print(f"    Alpha took {k:<12} n={v['n']:>4}  regret {v['regret']:>10,.0f}")

        # ---- component associations (ASSOCIATION ONLY) -----------------------------------------
        with_comp = [r for r in sub if r["components"]]
        assoc: dict = {}
        print(
            f"\n  COMPONENT ASSOCIATIONS ({len(with_comp)} picks) -- CORRELATION ONLY. A component "
            f"that\n    correlates with regret is NOT thereby a cause of it: every component also "
            f"correlates\n    with round, and regret varies strongly by round."
        )
        for field in (
            "projection",
            "vorp",
            "marginal_starter_value",
            "roster_need",
            "fit_multiplier",
            "confidence",
            "survival_probability",
            "opportunity_cost_pts",
            "score",
        ):
            pairs = [
                (r["components"][field], r["regret_roster"])
                for r in with_comp
                if r["components"].get(field) is not None
            ]
            if len(pairs) < 3:
                continue
            raw = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
            # Within-round correlation: removes the round confound that drives every raw number.
            within: list[float] = []
            for rnd in sorted({r["round"] for r in with_comp}):
                p_r = [
                    (r["components"][field], r["regret_roster"])
                    for r in with_comp
                    if r["round"] == rnd and r["components"].get(field) is not None
                ]
                if len(p_r) >= 5:
                    c = _pearson([p[0] for p in p_r], [p[1] for p in p_r])
                    if c == c:
                        within.append(c)
            assoc[field] = {
                "pearson_r_raw": round(raw, 3) if raw == raw else None,
                "pearson_r_within_round_mean": round(mean(within), 3) if within else None,
                "n": len(pairs),
                "n_rounds_in_within": len(within),
            }
            print(
                f"    {field:<26} r={assoc[field]['pearson_r_raw']!s:>7}   "
                f"within-round mean r={assoc[field]['pearson_r_within_round_mean']!s:>7}"
            )
        entry["component_associations"] = assoc

    # ---- arm recovery -------------------------------------------------------------------------
    if arm_rows:
        print(f"\n{bar}\nEXISTING-ARM RECOVERY OF THE MEASURED PER-PICK REGRET\n{bar}")
        for league_name in formats:
            arms_sub = [r for r in arm_rows if r["league"] == league_name]
            if not arms_sub:
                continue
            denom = summary["formats"][league_name]["overall"]["mean_regret_roster"]
            print(
                f"\n  {league_name}   (regret denominator = {denom:.1f} points/pick)"
                f"\n    {'arm':<12}{'changed':>9}{'delta/pick':>12}{'95% CI':>22}{'MDE':>8}"
                f"{'recovery':>10}  seasons"
            )
            arm_entry: dict = {}
            for arm_name in ARM_ORDER:
                rows_a = [r for r in arms_sub if r["arm"] == arm_name]
                if not rows_a:
                    continue
                per_season, (md, t, ci, half) = _season_ci(rows_a, "delta")
                changed = sum(1 for r in rows_a if r["changed"])
                arm_entry[arm_name] = {
                    "n_pick_states": len(rows_a),
                    "n_changed": changed,
                    "pct_changed": round(100 * changed / len(rows_a), 1),
                    "delta_per_pick": round(md, 2),
                    "ci": ci,
                    "t": None if t != t else round(t, 2),
                    "mde": None if half != half else round(half, 2),
                    "recovery_pct_of_regret": round(100 * md / denom, 1) if denom else None,
                    "seasons_positive": sum(1 for v in per_season.values() if v > 0),
                    "seasons_negative": sum(1 for v in per_season.values() if v < 0),
                    "per_season": {str(s): round(v, 2) for s, v in per_season.items()},
                }
                a = arm_entry[arm_name]
                print(
                    f"    {arm_name:<12}{a['pct_changed']:>8.1f}%{md:>12.2f}{ci:>22}"
                    f"{half:>8.2f}{a['recovery_pct_of_regret']:>9.1f}%"
                    f"  {a['seasons_positive']}+/{a['seasons_negative']}-"
                )
            summary["formats"][league_name]["arm_recovery"] = arm_entry
            null = arm_entry.get("Y1", {})
            if null and abs(null.get("delta_per_pick", 1.0)) > 1e-9:
                raise UnreconstructibleError(
                    f"the Y1 null arm recovered {null['delta_per_pick']} rather than exactly 0 -- "
                    "the arm harness is not reproducing the control, so no recovery number is usable"
                )
            print("    Y1 is the null check and must be exactly 0.00 (it picks what Alpha picked).")
            print(
                "    L1-L4 DEGRADE Y1's ordering by construction: a negative number there is the "
                "expected\n    downside slope, not a failed improvement."
            )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument(
        "--mode", required=True, choices=("audit", "regret", "timing", "arms", "report")
    )
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default=",".join(str(s) for s in DEFAULT_SLOTS))
    ap.add_argument("--leagues", default=",".join(FORMATS))
    a = ap.parse_args()

    out = Path(a.out)
    slots = tuple(int(s) for s in a.slots.split(","))
    formats = tuple(x for x in a.leagues.split(",") if x)
    con = duckdb.connect(a.db, read_only=True)

    assert_no_realized_inputs_in_policy()
    for season in BACKTEST_SEASONS:
        if season in (2020, 2026):
            raise UnreconstructibleError(f"{season} must never enter the historical evaluation")

    if a.mode == "audit":
        payload = run_audit(con)
        payload["provenance"] = _provenance(con, {"mode": "audit"})
        _write(out, "d115_audit.json", payload)
        print(json.dumps({k: v for k, v in payload.items() if k != "provenance"}, indent=1))
        return

    if a.mode == "regret":
        rows = run_regret(con, slots, formats)
        _write(
            out,
            "d115_regret.json",
            {
                "provenance": _provenance(
                    con, {"mode": "regret", "slots": list(slots), "leagues": list(formats)}
                ),
                "rows": [{k: v for k, v in r.items()} for r in rows],
            },
        )
        return

    if a.mode == "timing":
        regret_path = out / "d115_regret.json"
        if not regret_path.exists():
            raise UnreconstructibleError(
                f"{regret_path} is missing; --mode timing reads the regret run's own picks"
            )
        rows = run_timing(con, slots, formats, json.loads(regret_path.read_text())["rows"])
        _write(
            out,
            "d115_timing.json",
            {
                "provenance": _provenance(
                    con, {"mode": "timing", "slots": list(slots), "leagues": list(formats)}
                ),
                "rows": rows,
            },
        )
        return

    if a.mode == "arms":
        regret_path = out / "d115_regret.json"
        if not regret_path.exists():
            raise UnreconstructibleError(
                f"{regret_path} is missing; --mode arms reuses the regret run's own Alpha "
                "rollout values and will not recompute them"
            )
        rows = run_arms(con, slots, formats, json.loads(regret_path.read_text())["rows"])
        _write(
            out,
            "d115_arms.json",
            {
                "provenance": _provenance(
                    con, {"mode": "arms", "slots": list(slots), "leagues": list(formats)}
                ),
                "rows": rows,
            },
        )
        return

    regret_rows = json.loads((out / "d115_regret.json").read_text())["rows"]
    arms_path = out / "d115_arms.json"
    arm_rows = json.loads(arms_path.read_text())["rows"] if arms_path.exists() else []
    timing_path = out / "d115_timing.json"
    if not timing_path.exists():
        raise UnreconstructibleError(
            f"{timing_path} is missing; the C overlays come from --mode timing. The naive "
            "in-regret version of C2 was vacuous and has been removed rather than reported."
        )
    timing_rows = json.loads(timing_path.read_text())["rows"]
    summary = report(regret_rows, arm_rows, timing_rows)
    summary["provenance"] = _provenance(con, {"mode": "report"})
    _write(out, "d115_summary.json", summary)


if __name__ == "__main__":
    main()
