"""D113 -- does the shipped positional-capacity mechanism cost realized draft value?

Read-only research runner. It opens the database read-only, imports the shipped decision engine
and the already-committed counterfactual harness (`evaluation/decision_counterfactuals.py`), and
writes nothing but JSON artifacts under `--out`. **No file under `src/alpha_squad/league/` or
`src/alpha_squad/models/` is touched by D113, and this script is imported by no production path.**

    uv run python scripts/research/d113_capacity_audit.py --mode mechanism --out <dir>
    uv run python scripts/research/d113_capacity_audit.py --mode matched   --out <dir>
    uv run python scripts/research/d113_capacity_audit.py --mode paired    --out <dir>
    uv run python scripts/research/d113_capacity_audit.py --mode report    --out <dir>

==========================================================================================
PRE-REGISTRATION -- written and committed BEFORE any D113 comparison was run
==========================================================================================

THE QUESTION
------------
Does Alpha's current positional-capacity logic cause a meaningful loss of realized draft value,
particularly late in the draft?

D112 established LEVERAGE: capacity changes a meaningful fraction of late picks, fires frequently
in rounds 12-16, and holds Alpha at ~2.00-2.06 kickers against a capacity of 2. Leverage is not
value. D113 measures value, and nothing here treats "many picks changed" as evidence either way.

THE MECHANISM UNDER TEST, as it exists in production today
----------------------------------------------------------
Exactly one multiplicative penalty in `league/draft.py::recommend_draft_pick`:

    cap  = positional_feasibility_cap(league, pos)          # = league/roster.py::positional_capacity
    if cap > 0 and have_at_position[pos] >= cap:
        score *= OVER_CAP_VALUE_MULTIPLIER                  # = 0.1

applied AFTER `fit_mult * risk_mult * survival_mult`, on the finished score. `positional_capacity`
is `startable_slots(pos) + max(1, round(bench_size * startable_share(pos)))`, derived from the
league config alone. That is the whole hard-capacity mechanism; there is no other.

A SECOND, softer mechanism shares capacity's depth target and is deliberately NOT the primary
arm: `roster_need`'s `depth_target = startable_slots(pos)`, past which `need = -3.0 * excess` and
`roster_fit_multiplier` floors at 0.7. It is measured separately, as a bound, so the primary
contrast stays one mechanism wide.

THE ARMS -- one boolean each, no new rule invented
---------------------------------------------------
  C   control   `ScoringVariant.control()`, asserted equal to the real `recommend_draft_pick`
                by `assert_control_reproduces_production` at sampled pick states, and asserted
                here to produce the same draft as the production-pinned forensic tier.
  T1  PRIMARY   `use_cap_multiplier=False` -- the capacity penalty neutralized (forced to 1.0).
                Nothing else changes. This is removal, not replacement: no substitute cap, no
                new legality rule, no re-weighting.
  T2  SECONDARY `use_cap_multiplier=False, use_fit_multiplier=False` -- capacity plus its soft
                sibling. Reported as an upper bound on the whole saturation family, never as the
                headline.

Both booleans already exist in the committed harness (D83/D86); D113 adds no scoring code.

POPULATION -- fixed before any run
-----------------------------------
  seasons  BACKTEST_SEASONS = 2021, 2022, 2023, 2024, 2025. 2020 is excluded because no shipped
           market series has a preseason board before 2021 (D95/D96); the runner refuses it.
  slots    1-10, every seat in the snake. 50 paired drafts per format per arm.
  formats  target_league  -- the D58 target format. PRIMARY.
           dynasty_1qb    -- identical lineup, different consensus board (`do`), K/DST present.
           legacy_2qb_dynasty -- STRUCTURAL NEGATIVE CONTROL: its lineup has no K and no DEF
                            slot and its board (`dsf`) carries no kickers or defenses at all, so
                            capacity there can only ever bind on QB/RB/WR/TE. If the effect is a
                            K/DST effect it must vanish here.

PAIRING.  Every (format, season, slot) cell runs every arm from the identical board, the identical
fair opponent field (`market_consensus_roster_aware`), and the identical snake geometry. The
opponent is a deterministic function of the board, so the pairing is exact rather than stochastic.
The independent unit is the SEASON (k = 5): slots within a season share one board and one set of
realized outcomes, so they are not independent, exactly as D88/D97 established.

METRICS
-------
  PRIMARY    realized season-long starter points per draft -- `compute_league_starters` over real
             realized totals, the shipped primary metric for every draft number in this project.
  SECONDARY  weekly-no-foresight and weekly-hindsight lineup points (D86's objective), total
             roster points, bench contribution.
  FEASIBILITY unfilled mandatory slots, per-position roster counts, cap breaches.
  PICK-LEVEL (matched state, control's draft never forks): how many candidates carry the penalty
             at each state, whether the argmax changes, and the realized points of the control's
             player versus the treatment's player at each changed pick.

DECISION RULE, fixed now, before any number exists
---------------------------------------------------
D97's measured detection floor for a draft-level contrast is **172-250 points**; it is quoted, not
re-derived. The economic threshold is 25 points (D107 section 810's blind band).

  * |T1 - C| on the PRIMARY metric below 172 points in a format  ->  UNRESOLVED in that format,
    whatever the sign, whatever the t statistic. Capacity closes as a current research priority.
  * T1 - C >= +172 with a 95% CI excluding zero in `target_league`, AND no increase in unfilled
    mandatory slots  ->  capacity is costing realized value. Name the mechanism and recommend a
    follow-up controlled experiment. Still no production change in D113.
  * T1 - C <= -172 with a 95% CI excluding zero  ->  capacity is load-bearing; document and close
    the hypothesis.
  * T1 producing MORE unfilled mandatory slots than C  ->  the counterfactual is invalid. Report
    that and stop; do not invent a replacement legality rule to rescue it.

No weight is tuned after seeing a result -- T1 has no weight to tune, by construction. No season,
round, slot or position is dropped after the fact; every table below is over the full grid. The
target (redraft) and dynasty formats are never pooled.

ANALYSIS.  Season-clustered paired differences, k = 5, t_crit = 2.776 (df = 4) -- the same `_ci`
convention D104/D105 used, reproduced here rather than imported so this runner stands alone.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

import duckdb

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS, compute_board_vintage
from alpha_squad.evaluation.decision_counterfactuals import (
    BoardConstants,
    PickState,
    ScoringVariant,
    assert_control_reproduces_production,
    load_board_constants,
    score_board,
    simulate_variant_draft,
)
from alpha_squad.evaluation.draft_simulation import (
    MARKET_CONSENSUS_ROSTER_AWARE,
    _actual_points_for,
)
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.evaluation.weekly_objective import (
    bench_contribution,
    load_weekly_points,
    season_long_lineup_points,
    weekly_lineup_points,
    weekly_lineup_points_no_foresight,
)
from alpha_squad.league.context import resolve_league
from alpha_squad.league.roster import (
    OVER_CAP_VALUE_MULTIPLIER,
    positional_capacity,
    positional_feasibility_cap,
    startable_slots,
)
from alpha_squad.market.series import resolve_market_series

DB = "data/alpha_squad.duckdb"

#: PRIMARY format first. `legacy_2qb_dynasty` is the structural negative control -- see the
#: pre-registration.
FORMATS = ("target_league", "dynasty_1qb", "legacy_2qb_dynasty")
PRIMARY_FORMAT = "target_league"
DEFAULT_SLOTS = tuple(range(1, 11))

#: D97's measured floor for a draft-level contrast, quoted not re-derived.
DETECTION_FLOOR = (172.0, 250.0)
#: D107's economic threshold -- the bottom of the "blind band".
ECONOMIC_THRESHOLD = 25.0

CONTROL = "C"
PRIMARY_TREATMENT = "T1_no_cap"
SECONDARY_TREATMENT = "T2_no_cap_no_fit"
ARMS = (CONTROL, PRIMARY_TREATMENT, SECONDARY_TREATMENT)

VARIANTS: dict[str, ScoringVariant] = {
    CONTROL: ScoringVariant(name=CONTROL),
    PRIMARY_TREATMENT: ScoringVariant(name=PRIMARY_TREATMENT, use_cap_multiplier=False),
    SECONDARY_TREATMENT: ScoringVariant(
        name=SECONDARY_TREATMENT, use_cap_multiplier=False, use_fit_multiplier=False
    ),
}

#: The user-specified draft phases for D113. D103's own convention (1-5 / 6-10 / 11-16) is
#: reported alongside so the two records stay comparable.
PHASES: tuple[tuple[str, int, int], ...] = (("R1-6", 1, 6), ("R7-11", 7, 11), ("R12-16", 12, 16))
D103_PHASES: tuple[tuple[str, int, int], ...] = (
    ("EARLY 1-5", 1, 5),
    ("MIDDLE 6-10", 6, 10),
    ("LATE 11-16", 11, 16),
)


class CounterfactualInvalidError(RuntimeError):
    """Raised when the treatment arm stops being an interpretable counterfactual."""


def _git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def _phase_of(round_no: int, phases=PHASES) -> str:
    for label, lo, hi in phases:
        if lo <= round_no <= hi:
            return label
    return "?"


#: The combined board vintage every phase from D97 to D108 recorded (D107 section 9). D113 checks
#: against it and RECORDS the answer rather than asserting it: a fresh from-source rebuild is
#: allowed to land on a different projection layer, and a phase whose conclusion is a within-run
#: paired contrast is not invalidated by that -- but a cross-phase magnitude comparison is
#: weakened by it, and that has to be visible rather than assumed away.
D97_TO_D108_COMBINED_VINTAGE = "ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99"


def _market_board_hashes(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Per-(series, season) hash of the PRESEASON (player, position, rank) map the draft engine
    consumes, for each format in the grid.

    `compute_board_vintage`'s season hash covers `load_season_projections` -- the MODEL layer.
    The consensus board is a separate input and D92's append-only claim is about that one, so a
    rebuild that moves the model layer while leaving the market board fixed is distinguishable
    from one that moves both. Recorded here so the distinction is checkable later.
    """
    import hashlib

    from alpha_squad.league.opportunity_cost import load_market_ranks

    out: dict[str, str] = {}
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        ecr_type = resolve_market_series(league).ecr_type
        for season in BACKTEST_SEASONS:
            ranks = load_market_ranks(con, ecr_type, season)
            items = sorted((pid, pos, round(float(rank), 6)) for pid, (pos, rank) in ranks.items())
            digest = hashlib.sha256(json.dumps(items).encode()).hexdigest()
            out[f"{ecr_type}:{season}"] = f"{digest[:32]} n={len(items)}"
    return out


def _provenance(con: duckdb.DuckDBPyConnection, extra: dict) -> dict:
    vintage = compute_board_vintage(con)
    return {
        "git_head": _git_head(),
        "python": platform.python_version(),
        "argv": sys.argv,
        "board_vintage": vintage.as_dict(),
        "board_vintage_combined": vintage.combined_hash,
        "board_vintage_matches_d97_to_d108": vintage.combined_hash == D97_TO_D108_COMBINED_VINTAGE,
        "d97_to_d108_combined_vintage": D97_TO_D108_COMBINED_VINTAGE,
        "market_board_hashes": _market_board_hashes(con),
        "opponent_strategy": MARKET_CONSENSUS_ROSTER_AWARE,
        "over_cap_value_multiplier": OVER_CAP_VALUE_MULTIPLIER,
        "seasons": list(BACKTEST_SEASONS),
        "detection_floor": list(DETECTION_FLOOR),
        "economic_threshold": ECONOMIC_THRESHOLD,
        **extra,
    }


def _write(out: Path, name: str, payload: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"wrote {path}")
    return path


# --------------------------------------------------------------------------------------------
# MODE: mechanism -- what capacity IS, before any counterfactual
# --------------------------------------------------------------------------------------------
def run_mechanism(con: duckdb.DuckDBPyConnection, slots: tuple[int, ...]) -> dict:
    """Questions 1-3 and 7's precondition: which positions have a cap, what the cap is, when the
    penalty activates, how large it is -- read off the shipped functions, not restated.

    Also measures the SIGN PROPERTY of the penalty, which is a property of the arithmetic rather
    than an opinion: the multiplier is applied to a finished score that can be negative, and
    multiplying a negative score by 0.1 moves it UP. So for a candidate whose score is already
    negative, the "penalty" is a promotion relative to other negative-scored candidates. Whether
    that ever happens on a real board is measured in `matched`, not assumed here.
    """
    out: dict = {"formats": {}}
    for league_name in FORMATS:
        league = resolve_league(league_name, con=con)
        series = resolve_market_series(league)
        startable = startable_slots(league)
        caps = {pos: positional_capacity(league, pos) for pos in sorted(startable)}
        assert all(positional_feasibility_cap(league, pos) == caps[pos] for pos in caps), (
            "positional_feasibility_cap must be positional_capacity"
        )
        out["formats"][league_name] = {
            "lineup": dict(league.lineup),
            "dedicated_slots": league.dedicated_slots(),
            "bench_size": league.bench_size,
            "roster_size": int(league.roster.get("roster_size", 0)),
            "startable_slots": startable,
            "positional_capacity": caps,
            "sum_capacity": sum(caps.values()),
            "ecr_type": series.ecr_type,
            "page_type": series.page_type,
            "slots": list(slots),
        }
    out["penalty"] = {
        "constant": OVER_CAP_VALUE_MULTIPLIER,
        "applied_at": "league/draft.py::recommend_draft_pick, after fit*risk*survival",
        "form": "score *= 0.1 when have_at_position[pos] >= positional_feasibility_cap(pos)",
        "activation": "count-based and hard: the 0th over-cap body is unpenalised, the 1st is "
        "penalised in full; there is no taper",
        "sign_property": "multiplicative on a signed score; a negative score is moved TOWARD "
        "ZERO by the penalty, i.e. promoted relative to other negative-scored candidates",
    }
    return out


# --------------------------------------------------------------------------------------------
# MODE: matched -- counterfactual scoring at production's own pick states, no forking
# --------------------------------------------------------------------------------------------
def _matched_draft(
    con: duckdb.DuckDBPyConnection,
    league,
    season: int,
    ecr_type: str,
    board: BoardConstants,
    slot: int,
    *,
    verify_control_every: int,
) -> list[dict]:
    """Play ONE draft under the control, and at every one of our pick states additionally score
    the board under each treatment.

    The draft never forks: it always continues on the CONTROL's pick, so every state compared is
    a state production itself reaches, and every comparison is from an identical starting state.
    That is what isolates "capacity changed this pick" from "the two arms drifted apart".
    """
    from alpha_squad.league.opportunity_cost import roster_aware_market_pick

    total_rounds = int(league.roster.get("roster_size", 0))
    my_picks = [snake_overall_pick(r, slot, league.teams) for r in range(1, total_rounds + 1)]
    available = set(board.projections)
    drafted: list[str] = []
    my_positions: list[str] = []
    opponents: dict[int, list[str]] = {s: [] for s in range(1, league.teams + 1) if s != slot}
    rows: list[dict] = []

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        picks_remaining = total_rounds - round_no + 1
        for seat in order:
            if not available:
                break
            if seat != slot:
                pick = roster_aware_market_pick(
                    available,
                    board.market_ranks,
                    board.positions,
                    league,
                    opponents[seat],
                    picks_remaining,
                )
                opponents[seat].append(board.positions.get(pick, "UNKNOWN"))
                available.discard(pick)
                continue

            current = snake_overall_pick(round_no, slot, league.teams)
            nxt = (
                snake_overall_pick(round_no + 1, slot, league.teams)
                if round_no < total_rounds
                else None
            )
            state = PickState(
                season=season,
                ecr_type=ecr_type,
                roster_player_ids=list(drafted),
                roster_positions=list(my_positions),
                available=available,
                current_pick_overall=current,
                next_pick_overall=nxt,
                next_changed_board_pick=next((p for p in my_picks if p > current + 1), None),
            )
            if verify_control_every and round_no % verify_control_every == 1:
                assert_control_reproduces_production(con, league, board, state)

            scored = {arm: score_board(con, league, board, state, VARIANTS[arm]) for arm in ARMS}
            have = Counter(my_positions)

            # How the penalty is distributed over the board AT THIS STATE, from the control's own
            # numbers. `over_cap` is the set of candidates the penalty actually fires on.
            over_cap_positions = {
                pos
                for pos in {s.position for s in scored[CONTROL]}
                if (cap := positional_feasibility_cap(league, pos)) > 0 and have[pos] >= cap
            }
            control_scores = {s.player_id: s for s in scored[CONTROL]}
            over_cap_ids = [
                s.player_id for s in scored[CONTROL] if s.position in over_cap_positions
            ]
            # The sign property, measured rather than asserted: over-cap candidates whose control
            # score is negative were moved UP by the penalty.
            n_over_cap_negative = sum(1 for pid in over_cap_ids if control_scores[pid].score < 0)
            n_negative_total = sum(1 for s in scored[CONTROL] if s.score < 0)

            row = {
                "season": season,
                "slot": slot,
                "round": round_no,
                "overall_pick": current,
                "phase": _phase_of(round_no),
                "phase_d103": _phase_of(round_no, D103_PHASES),
                "roster_before": dict(have),
                "n_candidates": len(scored[CONTROL]),
                "n_over_cap_candidates": len(over_cap_ids),
                "over_cap_positions": sorted(over_cap_positions),
                "n_over_cap_negative_score": n_over_cap_negative,
                "n_negative_score_candidates": n_negative_total,
                "penalty_fires": bool(over_cap_ids),
            }
            for arm in ARMS:
                top = scored[arm][0]
                row[f"{arm}_pick"] = top.player_id
                row[f"{arm}_position"] = top.position
                row[f"{arm}_score"] = round(top.score, 4)
                row[f"{arm}_projection"] = round(top.projection, 3)
            # Was the CONTROL's own selection an over-cap body? (i.e. the penalty fired on the
            # player production picked anyway)
            row["control_pick_was_over_cap"] = row[f"{CONTROL}_pick"] in set(over_cap_ids)
            for arm in ARMS[1:]:
                row[f"{arm}_changed"] = row[f"{arm}_pick"] != row[f"{CONTROL}_pick"]
            rows.append(row)

            pick = row[f"{CONTROL}_pick"]
            drafted.append(pick)
            my_positions.append(board.positions.get(pick, "UNKNOWN"))
            available.discard(pick)

    realized = _actual_points_for(
        con,
        season,
        sorted({r[f"{arm}_pick"] for r in rows for arm in ARMS}),
    )
    for r in rows:
        for arm in ARMS:
            r[f"{arm}_realized"] = round(realized.get(r[f"{arm}_pick"], 0.0), 3)
    return rows


def run_matched(
    con: duckdb.DuckDBPyConnection,
    slots: tuple[int, ...],
    formats: tuple[str, ...],
    verify_control_every: int,
) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        ecr_type = resolve_market_series(league).ecr_type
        for season in BACKTEST_SEASONS:
            board = load_board_constants(con, league, season, ecr_type)
            for slot in slots:
                for row in _matched_draft(
                    con,
                    league,
                    season,
                    ecr_type,
                    board,
                    slot,
                    verify_control_every=verify_control_every,
                ):
                    row["league"] = league_name
                    rows.append(row)
            print(f"  matched {league_name} {season} ({time.time() - t0:.0f}s)", flush=True)
    return rows


# --------------------------------------------------------------------------------------------
# MODE: parity -- the control IS the production decision path, end to end
# --------------------------------------------------------------------------------------------
def run_parity(
    con: duckdb.DuckDBPyConnection, slots: tuple[int, ...], formats: tuple[str, ...]
) -> list[dict]:
    """Play each draft twice: once with every one of our picks made by the real
    `recommend_draft_pick`, once by the control arm of the counterfactual harness. The two
    rosters must be identical, player for player, in draft order.

    `assert_control_reproduces_production` already checks single states; this checks the whole
    trajectory, which is what the value contrast is actually computed over. If this fails, every
    D113 margin is a measurement of the harness and nothing in the phase is usable.
    """
    from alpha_squad.league.draft import recommend_draft_pick
    from alpha_squad.league.opportunity_cost import roster_aware_market_pick

    rows: list[dict] = []
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        ecr_type = resolve_market_series(league).ecr_type
        total_rounds = int(league.roster.get("roster_size", 0))
        for season in BACKTEST_SEASONS:
            board = load_board_constants(con, league, season, ecr_type)
            for slot in slots:
                available = set(board.projections)
                drafted: list[str] = []
                my_positions: list[str] = []
                opponents = {s: [] for s in range(1, league.teams + 1) if s != slot}
                for round_no in range(1, total_rounds + 1):
                    order = (
                        range(1, league.teams + 1)
                        if round_no % 2 == 1
                        else range(league.teams, 0, -1)
                    )
                    picks_remaining = total_rounds - round_no + 1
                    for seat in order:
                        if not available:
                            break
                        if seat != slot:
                            pick = roster_aware_market_pick(
                                available,
                                board.market_ranks,
                                board.positions,
                                league,
                                opponents[seat],
                                picks_remaining,
                            )
                            opponents[seat].append(board.positions.get(pick, "UNKNOWN"))
                        else:
                            current = snake_overall_pick(round_no, slot, league.teams)
                            nxt = (
                                snake_overall_pick(round_no + 1, slot, league.teams)
                                if round_no < total_rounds
                                else None
                            )
                            pick = recommend_draft_pick(
                                con,
                                league,
                                season,
                                list(my_positions),
                                available,
                                next_pick_overall=nxt,
                                ecr_type=ecr_type,
                                current_pick_overall=current,
                                roster_player_ids=list(drafted),
                            ).recommendation
                            drafted.append(pick)
                            my_positions.append(board.positions.get(pick, "UNKNOWN"))
                        available.discard(pick)
                harness = simulate_variant_draft(
                    con,
                    league,
                    season,
                    slot,
                    VARIANTS[CONTROL],
                    ecr_type=ecr_type,
                    board=board,
                )
                identical = list(harness.drafted_player_ids) == drafted
                rows.append(
                    {
                        "league": league_name,
                        "season": season,
                        "slot": slot,
                        "n_picks": len(drafted),
                        "identical": identical,
                    }
                )
                if not identical:
                    raise CounterfactualInvalidError(
                        f"the control arm is NOT the production decision path for "
                        f"{league_name}/{season}/slot {slot}: harness "
                        f"{harness.drafted_player_ids} vs recommend_draft_pick {drafted}"
                    )
            print(f"  parity {league_name} {season} OK", flush=True)
    return rows


# --------------------------------------------------------------------------------------------
# MODE: paired -- whole free-running drafts per arm, scored on realized outcomes
# --------------------------------------------------------------------------------------------
def run_paired(
    con: duckdb.DuckDBPyConnection, slots: tuple[int, ...], formats: tuple[str, ...]
) -> list[dict]:
    rows: list[dict] = []
    t0 = time.time()
    for league_name in formats:
        league = resolve_league(league_name, con=con)
        ecr_type = resolve_market_series(league).ecr_type
        for season in BACKTEST_SEASONS:
            board = load_board_constants(con, league, season, ecr_type)
            weekly = load_weekly_points(con, season)
            season_totals = {
                r[0]: float(r[1])
                for r in con.execute(
                    "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
                    "WHERE season = ?",
                    [season],
                ).fetchall()
            }
            for slot in slots:
                for arm in ARMS:
                    result = simulate_variant_draft(
                        con,
                        league,
                        season,
                        slot,
                        VARIANTS[arm],
                        ecr_type=ecr_type,
                        board=board,
                    )
                    roster = list(result.drafted_player_ids)
                    positions = {p: board.positions.get(p, "UNKNOWN") for p in roster}
                    rows.append(
                        {
                            "league": league_name,
                            "season": season,
                            "slot": slot,
                            "arm": arm,
                            "roster": roster,
                            "positions": [positions[p] for p in roster],
                            "position_counts": dict(Counter(positions[p] for p in roster)),
                            "season_long": season_long_lineup_points(
                                league, roster, positions, season_totals
                            ),
                            "starter_points": result.starter_points,
                            "total_roster_points": result.total_roster_points,
                            "weekly_no_foresight": weekly_lineup_points_no_foresight(
                                league, roster, positions, weekly, board.projections
                            ),
                            "weekly_hindsight": weekly_lineup_points(
                                league, roster, positions, weekly
                            ),
                            "bench": bench_contribution(
                                league, roster, positions, weekly, season_totals
                            ),
                            "n_unfilled_mandatory_slots": result.n_unfilled_mandatory_slots,
                            "cap_breaches": {
                                pos: n - positional_feasibility_cap(league, pos)
                                for pos, n in Counter(positions[p] for p in roster).items()
                                if positional_feasibility_cap(league, pos) > 0
                                and n > positional_feasibility_cap(league, pos)
                            },
                        }
                    )
            print(f"  paired {league_name} {season} ({time.time() - t0:.0f}s)", flush=True)
    return rows


# --------------------------------------------------------------------------------------------
# Statistics -- season-clustered paired differences, D104's convention
# --------------------------------------------------------------------------------------------
def _paired_by_season(rows: list[dict], league_name: str, metric: str, a: str, b: str):
    """Per-season mean of (arm a - arm b) on `metric`, over the slots in that season."""
    by_cell: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r["league"] == league_name:
            by_cell[(r["season"], r["slot"])][r["arm"]] = r[metric]
    by_season: dict[int, list[float]] = defaultdict(list)
    for (season, _slot), arms in by_cell.items():
        if a in arms and b in arms:
            by_season[season].append(arms[a] - arms[b])
    return {s: mean(v) for s, v in sorted(by_season.items())}


def _ci(values: list[float], t_crit: float = 2.776):
    k = len(values)
    if k == 0:
        return float("nan"), float("nan"), "n/a", float("nan")
    md = mean(values)
    if k < 2 or stdev(values) == 0:
        return md, float("nan"), "n/a", float("nan")
    se = stdev(values) / k**0.5
    return md, md / se, f"[{md - t_crit * se:+.1f}, {md + t_crit * se:+.1f}]", t_crit * se


def _draft_level_wins(rows: list[dict], league_name: str, metric: str, a: str, b: str):
    by_cell: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for r in rows:
        if r["league"] == league_name:
            by_cell[(r["season"], r["slot"])][r["arm"]] = r[metric]
    diffs = [v[a] - v[b] for v in by_cell.values() if a in v and b in v]
    return (
        sum(1 for d in diffs if d > 0),
        sum(1 for d in diffs if d == 0),
        sum(1 for d in diffs if d < 0),
        diffs,
    )


# --------------------------------------------------------------------------------------------
# MODE: report
# --------------------------------------------------------------------------------------------
METRICS = (
    ("season_long", "D. target season-long objective (PRIMARY)"),
    ("weekly_no_foresight", "E. weekly objective, no foresight"),
    ("weekly_hindsight", "E. weekly objective, hindsight"),
    ("total_roster_points", "total roster points"),
    ("bench", "bench contribution"),
)


def report(matched: list[dict], paired: list[dict], formats: tuple[str, ...]) -> dict:
    summary: dict = {"formats": {}}
    bar = "=" * 98

    # ---- A. pick-level changes caused by capacity (matched state, no forking) ----------------
    print(
        f"\n{bar}\nA. PICK-LEVEL CHANGES CAUSED BY CAPACITY  (matched states, draft never "
        f"forks)\n{bar}"
    )
    for league_name in formats:
        sub = [r for r in matched if r["league"] == league_name]
        if not sub:
            continue
        n = len(sub)
        fires = sum(1 for r in sub if r["penalty_fires"])
        entry: dict = {
            "n_pick_states": n,
            "n_states_penalty_fires": fires,
            "pct_states_penalty_fires": round(100 * fires / n, 1),
        }
        print(f"\n  {league_name}   ({n} pick states)")
        print(f"    penalty fires on >=1 candidate : {fires:>5} / {n}  ({100 * fires / n:.1f}%)")
        for arm in ARMS[1:]:
            changed = sum(1 for r in sub if r[f"{arm}_changed"])
            changed_when_fires = sum(1 for r in sub if r["penalty_fires"] and r[f"{arm}_changed"])
            changed_when_quiet = changed - changed_when_fires
            entry[arm] = {
                "n_changed": changed,
                "pct_changed": round(100 * changed / n, 2),
                "n_changed_while_penalty_fires": changed_when_fires,
                "n_changed_while_penalty_quiet": changed_when_quiet,
            }
            print(
                f"    {arm}: picks changed          : {changed:>5} / {n}  "
                f"({100 * changed / n:.2f}%)   of which {changed_when_fires} at a state where "
                f"the penalty fires"
            )
        # Question 6: fires but does NOT change the pick == "merely a lower score".
        merely = fires - entry[PRIMARY_TREATMENT]["n_changed_while_penalty_fires"]
        entry["n_states_penalty_fires_but_pick_unchanged"] = merely
        print(f"    penalty fires, pick UNCHANGED  : {merely:>5}  (leverage without consequence)")
        # sign property
        neg = sum(r["n_over_cap_negative_score"] for r in sub)
        tot_over = sum(r["n_over_cap_candidates"] for r in sub)
        entry["over_cap_candidate_scorings"] = tot_over
        entry["over_cap_candidate_scorings_with_negative_score"] = neg
        entry["pct_over_cap_scorings_promoted_by_penalty"] = (
            round(100 * neg / tot_over, 1) if tot_over else None
        )
        print(
            f"    over-cap candidate scorings    : {tot_over:>5}, of which {neg} had a "
            f"NEGATIVE control score (the penalty moved those UP)"
        )
        n_ctrl_over = sum(1 for r in sub if r["control_pick_was_over_cap"])
        entry["n_control_picks_that_were_over_cap"] = n_ctrl_over
        print(f"    production picked an over-cap body anyway: {n_ctrl_over} states")
        summary["formats"].setdefault(league_name, {})["A_pick_level"] = entry

    # ---- G/H. by phase and by position -------------------------------------------------------
    print(f"\n{bar}\nG. EFFECTS BY DRAFT PHASE   H. EFFECTS BY POSITION  (matched states)\n{bar}")
    for league_name in formats:
        sub = [r for r in matched if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}")
        by_phase: dict[str, dict] = {}
        for label, _lo, _hi in PHASES:
            ph = [r for r in sub if r["phase"] == label]
            if not ph:
                continue
            fires = sum(1 for r in ph if r["penalty_fires"])
            changed = sum(1 for r in ph if r[f"{PRIMARY_TREATMENT}_changed"])
            delta = [
                r[f"{PRIMARY_TREATMENT}_realized"] - r[f"{CONTROL}_realized"]
                for r in ph
                if r[f"{PRIMARY_TREATMENT}_changed"]
            ]
            by_phase[label] = {
                "n_states": len(ph),
                "n_penalty_fires": fires,
                "pct_penalty_fires": round(100 * fires / len(ph), 1),
                "n_changed": changed,
                "pct_changed": round(100 * changed / len(ph), 2),
                "sum_realized_delta_at_changed_picks": round(sum(delta), 1),
                "mean_realized_delta_at_changed_picks": (round(mean(delta), 2) if delta else None),
            }
            print(
                f"    {label:<8} states {len(ph):>5}  penalty fires {fires:>5} "
                f"({100 * fires / len(ph):>5.1f}%)  picks changed {changed:>4} "
                f"({100 * changed / len(ph):>5.2f}%)  sum realized delta at changed picks "
                f"{sum(delta):>+9.1f}"
            )
        summary["formats"].setdefault(league_name, {})["G_by_phase"] = by_phase

        by_pos: dict[str, dict] = defaultdict(lambda: {"control": 0, "treatment": 0, "delta": 0.0})
        for r in sub:
            if not r[f"{PRIMARY_TREATMENT}_changed"]:
                continue
            by_pos[r[f"{CONTROL}_position"]]["control"] += 1
            by_pos[r[f"{PRIMARY_TREATMENT}_position"]]["treatment"] += 1
            by_pos[r[f"{CONTROL}_position"]]["delta"] -= r[f"{CONTROL}_realized"]
            by_pos[r[f"{PRIMARY_TREATMENT}_position"]]["delta"] += r[
                f"{PRIMARY_TREATMENT}_realized"
            ]
        print("    position flow at changed picks (control gave up -> treatment took):")
        for pos in sorted(by_pos):
            v = by_pos[pos]
            print(
                f"      {pos:<5} control picked {v['control']:>4}   treatment picked "
                f"{v['treatment']:>4}   net realized {v['delta']:>+9.1f}"
            )
        summary["formats"][league_name]["H_by_position"] = {
            k: {kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in v.items()}
            for k, v in by_pos.items()
        }

    # ---- B. realized value of changed picks ---------------------------------------------------
    print(
        f"\n{bar}\nB. REALIZED VALUE OF CHANGED PICKS  (matched states; pick-level, NOT a "
        f"roster contrast)\n{bar}"
    )
    for league_name in formats:
        sub = [
            r for r in matched if r["league"] == league_name and r[f"{PRIMARY_TREATMENT}_changed"]
        ]
        if not sub:
            print(f"\n  {league_name}: no changed picks")
            continue
        delta = [r[f"{PRIMARY_TREATMENT}_realized"] - r[f"{CONTROL}_realized"] for r in sub]
        per_season = {
            s: sum(
                r[f"{PRIMARY_TREATMENT}_realized"] - r[f"{CONTROL}_realized"]
                for r in sub
                if r["season"] == s
            )
            / len({(r["season"], r["slot"]) for r in sub if r["season"] == s})
            for s in sorted({r["season"] for r in sub})
        }
        md, t, ci, _ = _ci(list(per_season.values()))
        print(
            f"\n  {league_name}: {len(sub)} changed picks, mean realized delta "
            f"{mean(delta):+.1f} pts/pick, total {sum(delta):+.1f}"
        )
        print(
            f"    per-DRAFT sum of changed-pick deltas, season-clustered: {md:+.1f}  "
            f"95% CI {ci}  t={t:.2f}"
        )
        print("    by season: " + "  ".join(f"{s}:{v:+.0f}" for s, v in per_season.items()))
        summary["formats"].setdefault(league_name, {})["B_changed_pick_value"] = {
            "n_changed_picks": len(sub),
            "mean_delta_per_pick": round(mean(delta), 2),
            "total_delta": round(sum(delta), 1),
            "per_draft_mean": round(md, 1),
            "per_draft_ci": ci,
            "per_season": {str(s): round(v, 1) for s, v in per_season.items()},
        }

    # ---- C/D/E/F/I/J/K. roster-level realized value -------------------------------------------
    print(f"\n{bar}\nC/D/E/F. FINAL ROSTER REALIZED VALUE  (paired free-running drafts)\n{bar}")
    for league_name in formats:
        sub = [r for r in paired if r["league"] == league_name]
        if not sub:
            continue
        print(f"\n  {league_name}   ({len(sub)} draft-arms)")
        fmt_entry = summary["formats"].setdefault(league_name, {})
        levels = {
            arm: {m: round(mean(r[m] for r in sub if r["arm"] == arm), 1) for m, _ in METRICS}
            for arm in ARMS
        }
        fmt_entry["levels"] = levels
        for arm in ARMS:
            print(f"    {arm:<18} " + "  ".join(f"{m}={levels[arm][m]:>8.1f}" for m, _ in METRICS))
        contrasts: dict = {}
        for treatment in ARMS[1:]:
            contrasts[treatment] = {}
            print(f"\n    {treatment} - {CONTROL}:")
            for metric, label in METRICS:
                per_season = _paired_by_season(sub, league_name, metric, treatment, CONTROL)
                md, t, ci, half = _ci(list(per_season.values()))
                w, tie, loss, diffs = _draft_level_wins(
                    sub, league_name, metric, treatment, CONTROL
                )
                verdict = _verdict(md, half)
                contrasts[treatment][metric] = {
                    "mean_per_draft": round(md, 1),
                    "ci": ci,
                    "t": None if t != t else round(t, 2),
                    "seasons_won": sum(1 for v in per_season.values() if v > 0),
                    "seasons_lost": sum(1 for v in per_season.values() if v < 0),
                    "drafts_won": w,
                    "drafts_tied": tie,
                    "drafts_lost": loss,
                    "per_season": {str(s): round(v, 1) for s, v in per_season.items()},
                    # The CI half-width IS this contrast's own minimum detectable effect at
                    # k = 5 season clusters -- D97 derived its 172-250 band the same way, from
                    # the between-season SD. Reported so the floor is measured here as well as
                    # quoted.
                    "own_mde": None if half != half else round(half, 1),
                    "between_season_sd": (
                        round(stdev(list(per_season.values())), 1) if len(per_season) > 1 else None
                    ),
                    "verdict_vs_detection_floor": verdict,
                }
                print(
                    f"      {label:<42} {md:>+9.1f}  95% CI {ci:<22} t={t:>6.2f}  "
                    f"MDE {half:>7.1f}  "
                    f"seasons {sum(1 for v in per_season.values() if v > 0)}W/"
                    f"{sum(1 for v in per_season.values() if v < 0)}L  "
                    f"drafts {w}W/{tie}T/{loss}L  -> {verdict}"
                )
                if metric == "season_long":
                    print(
                        "        by season: "
                        + "  ".join(f"{s}:{v:+.0f}" for s, v in per_season.items())
                    )
        fmt_entry["CDEF_contrasts"] = contrasts

        # feasibility -- the validity gate
        feas = {
            arm: {
                "mean_unfilled_mandatory_slots": round(
                    mean(r["n_unfilled_mandatory_slots"] for r in sub if r["arm"] == arm), 3
                ),
                "n_drafts_with_unfilled": sum(
                    1 for r in sub if r["arm"] == arm and r["n_unfilled_mandatory_slots"] > 0
                ),
                "mean_position_counts": {
                    pos: round(
                        mean(r["position_counts"].get(pos, 0) for r in sub if r["arm"] == arm),
                        2,
                    )
                    for pos in sorted({p for r in sub for p in r["position_counts"]})
                },
                "n_drafts_with_cap_breach": sum(
                    1 for r in sub if r["arm"] == arm and r["cap_breaches"]
                ),
                "max_breach": max(
                    (
                        max(r["cap_breaches"].values())
                        for r in sub
                        if r["arm"] == arm and r["cap_breaches"]
                    ),
                    default=0,
                ),
            }
            for arm in ARMS
        }
        fmt_entry["feasibility"] = feas
        print("\n    ROSTER FEASIBILITY (the counterfactual-validity gate)")
        for arm in ARMS:
            f = feas[arm]
            print(
                f"      {arm:<18} unfilled mandatory slots mean "
                f"{f['mean_unfilled_mandatory_slots']:.3f} "
                f"({f['n_drafts_with_unfilled']} drafts >0)   cap breaches in "
                f"{f['n_drafts_with_cap_breach']} drafts (max {f['max_breach']})   "
                f"counts {f['mean_position_counts']}"
            )
        if (
            feas[PRIMARY_TREATMENT]["mean_unfilled_mandatory_slots"]
            > feas[CONTROL]["mean_unfilled_mandatory_slots"] + 1e-9
        ):
            print(
                "      *** T1 leaves MORE mandatory slots unfilled than production: by the "
                "pre-registered rule this counterfactual is INVALID in this format ***"
            )
            fmt_entry["counterfactual_valid"] = False
        else:
            fmt_entry["counterfactual_valid"] = True

    return summary


def _verdict(md: float, half_width: float) -> str:
    """The pre-registered classification, applied mechanically."""
    if md != md:
        return "n/a"
    lo, hi = DETECTION_FLOOR
    resolved = half_width == half_width and abs(md) > half_width
    if abs(md) < lo:
        return f"BELOW DETECTION FLOOR ({lo:.0f}) -> UNRESOLVED"
    if not resolved:
        return "above floor but CI SPANS ZERO -> UNRESOLVED"
    if abs(md) < hi:
        return f"inside the {lo:.0f}-{hi:.0f} floor BAND, CI excludes zero -> WEAK"
    return "ABOVE the floor band and CI excludes zero -> RESOLVED"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument(
        "--mode", required=True, choices=("mechanism", "parity", "matched", "paired", "report")
    )
    ap.add_argument("--out", required=True)
    ap.add_argument("--slots", default="1-10")
    ap.add_argument("--leagues", default=",".join(FORMATS))
    ap.add_argument(
        "--verify-control-every",
        type=int,
        default=8,
        help="assert the control reproduces recommend_draft_pick every Nth round; "
        "0 disables (it is slow)",
    )
    a = ap.parse_args()

    lo, _, hi = a.slots.partition("-")
    slots = tuple(range(int(lo), int(hi or lo) + 1))
    formats = tuple(x for x in a.leagues.split(",") if x)
    out = Path(a.out)
    con = duckdb.connect(a.db, read_only=True)

    if a.mode == "mechanism":
        payload = run_mechanism(con, slots)
        payload["provenance"] = _provenance(con, {"mode": "mechanism"})
        _write(out, "d113_mechanism.json", payload)
        print(json.dumps(payload["formats"], indent=1, sort_keys=True))
        return

    if a.mode == "parity":
        rows = run_parity(con, slots, formats)
        _write(
            out,
            "d113_parity.json",
            {
                "provenance": _provenance(
                    con, {"mode": "parity", "slots": list(slots), "leagues": list(formats)}
                ),
                "n_drafts": len(rows),
                "all_identical": all(r["identical"] for r in rows),
                "rows": rows,
            },
        )
        print(f"parity: {len(rows)} drafts, all identical = {all(r['identical'] for r in rows)}")
        return

    if a.mode == "matched":
        rows = run_matched(con, slots, formats, a.verify_control_every)
        _write(
            out,
            "d113_matched.json",
            {
                "provenance": _provenance(
                    con, {"mode": "matched", "slots": list(slots), "leagues": list(formats)}
                ),
                "rows": rows,
            },
        )
        return

    if a.mode == "paired":
        rows = run_paired(con, slots, formats)
        _write(
            out,
            "d113_paired.json",
            {
                "provenance": _provenance(
                    con, {"mode": "paired", "slots": list(slots), "leagues": list(formats)}
                ),
                "rows": rows,
            },
        )
        return

    matched = json.loads((out / "d113_matched.json").read_text())["rows"]
    paired = json.loads((out / "d113_paired.json").read_text())["rows"]
    present = tuple(f for f in formats if any(r["league"] == f for r in paired))
    summary = report(matched, paired, present)
    summary["provenance"] = _provenance(con, {"mode": "report"})
    _write(out, "d113_summary.json", summary)


if __name__ == "__main__":
    main()
