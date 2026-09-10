"""RETROSPECTIVE DIAGNOSTIC ORACLE for the draft objective (D86). **Not a production model.**

The question D86 exists to answer is *what should Alpha optimize*, and the only way to answer it
empirically is to find out where the current objective's ranking disagrees with what would
actually have produced the best final roster. That requires knowing the outcomes — so this module
uses realized season points, and it is therefore **a diagnostic instrument that can never inform a
pick**.

The leakage rule, stated precisely because everything here depends on it
--------------------------------------------------------------------------
Realized outcomes enter in exactly ONE place: **scoring a finished roster**. They never enter:

* the rollout policy (which is the shipped Y1 engine, reading Y1 projections),
* the opponent model (the fair `roster_aware_market_pick`, reading only preseason ECR),
* the candidate generation (see `candidate_slate` — the realized-points slate is included so the
  oracle is not evaluated only on players Alpha already liked, which would bias the measured
  regret toward zero; it is a diagnostic input, never a policy input).

`assert_no_realized_inputs_in_policy` pins the first two by construction: the rollout is
`draft_forensics.score_candidate`, which has no access to a realized-points table at all.

What "the best pick" means here, and why this definition
---------------------------------------------------------
There is no tractable full oracle. The exact answer — the pick maximising final realized starter
points after *optimal* play by every remaining decision — is a dynamic program over a 160-pick
game with a ~840-player board. It is not computable, and it is also not the right question,
because Alpha will never play optimally afterwards.

So this measures the **one-step oracle under a fixed continuation policy**:

    V(c) = realized starter points of the final roster, if I take `c` now and then play the
           REST of the draft exactly the way the shipped engine plays it

and the oracle pick is `argmax_c V(c)`. This is the right diagnostic because it isolates the one
decision under test while holding everything downstream constant: a difference between `V(alpha's
pick)` and `max_c V(c)` is attributable to *this pick* and to nothing else. It is a lower bound on
the value of a better objective (a better objective would also improve the continuation), and that
is the conservative direction.

Two derived quantities, both reported:

* **regret** = `max_c V(c) − V(alpha's pick)` — points left on the table at this pick.
* **rank correlation** between Alpha's score and `V(c)` across the slate — whether the current
  objective *orders* candidates the way outcomes do, independent of scale.

Why the continuation is the SHIPPED engine and not a greedy realized-points policy
-----------------------------------------------------------------------------------
A realized-points continuation would make every rollout a hindsight draft, and the resulting
"regret" would measure the projection model's error rather than the objective's. Holding the
continuation at the shipped policy is what makes the residual attributable to the OBJECTIVE.
`rollout_policy` is nonetheless a parameter, so the alternative can be measured deliberately
(D86 Phase 4 uses it to separate objective error from projection error).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from alpha_squad.evaluation.draft_forensics import (
    SeasonStatic,
    _pick_by_tier,
)
from alpha_squad.evaluation.draft_simulation import _actual_points_for
from alpha_squad.evaluation.opening_audit import snake_overall_pick
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.opportunity_cost import roster_aware_market_pick
from alpha_squad.league.replacement import compute_league_starters
from alpha_squad.league.roster import unfilled_dedicated_slots

#: The shipped engine, as a `draft_forensics` tier. `L0`/`Q0`/`Z0` are asserted byte-identical to
#: `recommend_draft_pick` by existing tests, so a rollout under this tier is the production policy.
SHIPPED_TIER = "L0"


@dataclass
class OracleCandidate:
    player_id: str
    position: str
    projection: float
    alpha_score: float
    alpha_rank: int
    realized_points: float
    #: Final realized STARTER points of the whole roster if this candidate is taken now and the
    #: rest of the draft is played by `rollout_policy`.
    rollout_starter_points: float
    rollout_total_points: float
    unfilled_mandatory: int
    #: True for the candidate the shipped engine actually picked at this state.
    is_alpha_pick: bool = False


@dataclass
class OraclePick:
    season: int
    draft_slot: int
    round_no: int
    pick_overall: int
    roster_positions: list[str]
    candidates: list[OracleCandidate] = field(default_factory=list)

    @property
    def alpha(self) -> OracleCandidate | None:
        return next((c for c in self.candidates if c.is_alpha_pick), None)

    @property
    def oracle(self) -> OracleCandidate | None:
        return max(self.candidates, key=lambda c: c.rollout_starter_points, default=None)

    @property
    def regret(self) -> float:
        """Realized starter points left on the table by the shipped engine at this pick."""
        a, o = self.alpha, self.oracle
        if a is None or o is None:
            return 0.0
        return o.rollout_starter_points - a.rollout_starter_points

    @property
    def alpha_is_oracle(self) -> bool:
        a, o = self.alpha, self.oracle
        return a is not None and o is not None and a.player_id == o.player_id


def candidate_slate(
    static: SeasonStatic,
    available: set[str],
    alpha_ranked: list[str],
    realized: dict[str, float],
    *,
    top_alpha: int = 10,
    top_realized: int = 10,
    top_projection: int = 5,
) -> list[str]:
    """The candidates the oracle evaluates at one pick.

    Deliberately a UNION of three slates, because each alone biases the measured regret:

    * **Alpha's own top-N** — without it the oracle never evaluates the pick Alpha made.
    * **the realized-points top-N** — without it the oracle can only ever choose among players
      Alpha already rated, which drives measured regret artificially toward zero. This is the
      slate that makes the diagnostic honest, and it is also the reason this module can never be
      used in production.
    * **the projection top-N** — catches players both of the above miss (high projection, low
      Alpha score because of a multiplier, ordinary outcome).

    Order is deterministic (`player_id` tie-break throughout) so a re-run reproduces exactly.
    """
    slate: list[str] = []
    seen: set[str] = set()

    def add(ids: list[str], n: int) -> None:
        for pid in ids[:n]:
            if pid not in seen and pid in available:
                seen.add(pid)
                slate.append(pid)

    add([p for p in alpha_ranked if p in available], top_alpha)
    add(
        sorted(available, key=lambda p: (-realized.get(p, 0.0), p)),
        top_realized,
    )
    add(
        sorted(
            (p for p in available if p in static.projections),
            key=lambda p: (-static.projections[p], p),
        ),
        top_projection,
    )
    return slate


def _score_roster(
    league: LeagueContext,
    drafted: list[str],
    positions: dict[str, str],
    actual: dict[str, float],
) -> tuple[float, float, int]:
    """(realized starter points, realized total points, unfilled mandatory slots).

    Uses `compute_league_starters` with `teams=1` -- the same allocator the shipped benchmark
    scores rosters with, so an oracle number is directly comparable to a benchmark number."""
    drafted_positions = [positions.get(p, "UNKNOWN") for p in drafted]
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        {p: actual.get(p, 0.0) for p in drafted},
        {p: positions.get(p, "UNKNOWN") for p in drafted},
    )
    return (
        sum(actual.get(p, 0.0) for p in starters["starters"]),
        sum(actual.get(p, 0.0) for p in drafted),
        sum(unfilled_dedicated_slots(league, drafted_positions).values()),
    )


def draft_order(league: LeagueContext) -> list[tuple[int, int, int]]:
    """Every (overall pick, round, slot) of a full snake draft, in overall-pick order.

    Enumerated once rather than re-derived inside the rollout loop: resuming a draft from the
    middle is exactly a filter on this list, which is far less error-prone than reconstructing
    the snake geometry from a starting round and then trying to skip the picks already made."""
    total_rounds = int(league.roster.get("roster_size", 0))
    out: list[tuple[int, int, int]] = []
    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        for slot in order:
            out.append((snake_overall_pick(round_no, slot, league.teams), round_no, slot))
    out.sort()
    return out


def rollout(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    static: SeasonStatic,
    *,
    draft_slot: int,
    after_pick_overall: int,
    available: set[str],
    drafted: list[str],
    opponent_rosters: dict[int, list[str]],
    actual: dict[str, float],
    rollout_tier: str = SHIPPED_TIER,
) -> tuple[float, float, int]:
    """Finish the draft from a mid-draft state and score the result on REALIZED points.

    `after_pick_overall` is the overall number of the pick that has just been made (the candidate
    under test); the rollout resumes at the next pick in the snake and plays to the end. Mirrors
    `draft_forensics.simulate_forensic_draft`'s loop (same geometry, same fair opponent, same
    outcome scoring) so a rollout is the benchmark's own draft, started from the middle.

    The policy reads projections only. Realized points are used solely by `_score_roster`, after
    every decision has been made.
    """
    total_rounds = int(league.roster.get("roster_size", 0))
    my_picks = [snake_overall_pick(r, draft_slot, league.teams) for r in range(1, total_rounds + 1)]
    avail = set(available)
    mine = list(drafted)
    opps = {s: list(v) for s, v in opponent_rosters.items()}

    for current, round_no, slot in draft_order(league):
        if current <= after_pick_overall:
            continue
        if not avail:
            break
        picks_remaining = total_rounds - round_no + 1
        if slot == draft_slot:
            nxt = next((p for p in my_picks if p > current), None)
            pick, _ = _pick_by_tier(
                static,
                con,
                league,
                season,
                avail,
                [static.positions.get(p, "UNKNOWN") for p in mine],
                rollout_tier,
                current,
                nxt,
                roster_player_ids=mine,
                picks_remaining=picks_remaining,
            )
            mine.append(pick)
        else:
            pick = roster_aware_market_pick(
                avail,
                static.market_rank,
                static.positions,
                league,
                opps[slot],
                picks_remaining,
            )
            opps[slot].append(static.positions.get(pick, "UNKNOWN"))
        avail.discard(pick)

    missing = [p for p in mine if p not in actual]
    if missing:
        actual = {**actual, **_actual_points_for(con, season, missing)}
    return _score_roster(league, mine, static.positions, actual)


def audit_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    draft_slot: int,
    static: SeasonStatic,
    *,
    rounds: tuple[int, ...] | None = None,
    top_alpha: int = 10,
    top_realized: int = 10,
    top_projection: int = 5,
    rollout_tier: str = SHIPPED_TIER,
) -> list[OraclePick]:
    """Walk ONE real production-path draft and, at each audited pick, measure what every
    candidate on the slate would have been worth by the end.

    The draft itself is played by the shipped engine, so the states audited are the states
    production actually reaches. At each audited pick the slate is evaluated by rollout, then the
    draft continues with the ENGINE's pick (not the oracle's) -- so this measures per-pick regret
    against the real trajectory rather than compounding oracle picks into a hindsight draft.

    `rounds` limits which rounds are audited (rollout cost is the whole remaining draft per
    candidate); `None` audits every round.
    """
    total_rounds = int(league.roster.get("roster_size", 0))
    my_picks = [snake_overall_pick(r, draft_slot, league.teams) for r in range(1, total_rounds + 1)]
    avail = set(static.projections)
    mine: list[str] = []
    opps: dict[int, list[str]] = {s: [] for s in range(1, league.teams + 1) if s != draft_slot}
    realized = _actual_points_for(con, season, sorted(static.projections))
    audited: list[OraclePick] = []

    for current, round_no, slot in draft_order(league):
        if not avail:
            break
        picks_remaining = total_rounds - round_no + 1
        if slot != draft_slot:
            pick = roster_aware_market_pick(
                avail, static.market_rank, static.positions, league, opps[slot], picks_remaining
            )
            opps[slot].append(static.positions.get(pick, "UNKNOWN"))
            avail.discard(pick)
            continue

        nxt = next((p for p in my_picks if p > current), None)
        my_positions = [static.positions.get(p, "UNKNOWN") for p in mine]
        alpha_pick, scored = _pick_by_tier(
            static,
            con,
            league,
            season,
            avail,
            my_positions,
            rollout_tier,
            current,
            nxt,
            roster_player_ids=mine,
            picks_remaining=picks_remaining,
        )

        if rounds is None or round_no in rounds:
            alpha_ranked = [s.player_id for s in scored]
            alpha_score = {s.player_id: s.score for s in scored}
            alpha_rank = {p: i + 1 for i, p in enumerate(alpha_ranked)}
            slate = candidate_slate(
                static,
                avail,
                alpha_ranked,
                realized,
                top_alpha=top_alpha,
                top_realized=top_realized,
                top_projection=top_projection,
            )
            if alpha_pick not in slate:
                slate.append(alpha_pick)
            record = OraclePick(
                season=season,
                draft_slot=draft_slot,
                round_no=round_no,
                pick_overall=current,
                roster_positions=list(my_positions),
            )
            for cand in slate:
                starter, total, unfilled = rollout(
                    con,
                    league,
                    season,
                    static,
                    draft_slot=draft_slot,
                    after_pick_overall=current,
                    available=avail - {cand},
                    drafted=[*mine, cand],
                    opponent_rosters=opps,
                    actual=realized,
                    rollout_tier=rollout_tier,
                )
                record.candidates.append(
                    OracleCandidate(
                        player_id=cand,
                        position=static.positions.get(cand, "UNKNOWN"),
                        projection=static.projections.get(cand, 0.0),
                        alpha_score=alpha_score.get(cand, float("nan")),
                        alpha_rank=alpha_rank.get(cand, 10**6),
                        realized_points=realized.get(cand, 0.0),
                        rollout_starter_points=starter,
                        rollout_total_points=total,
                        unfilled_mandatory=unfilled,
                        is_alpha_pick=(cand == alpha_pick),
                    )
                )
            audited.append(record)

        mine.append(alpha_pick)
        avail.discard(alpha_pick)

    return audited


def assert_no_realized_inputs_in_policy() -> None:
    """The leakage guard, as an executable check rather than a comment.

    `_pick_by_tier` is the rollout policy and `roster_aware_market_pick` is the opponent. Neither
    takes a realized-outcome argument, so no realized point total can reach a decision. If a
    future change adds one, this fails loudly instead of silently turning the oracle into a
    hindsight drafter."""
    import inspect

    banned = ("actual", "realized", "outcome", "realised")
    for fn in (_pick_by_tier, roster_aware_market_pick):
        params = set(inspect.signature(fn).parameters)
        leaked = {p for p in params if any(b in p.lower() for b in banned)}
        if leaked:
            raise AssertionError(
                f"{fn.__name__} accepts realized-outcome parameters {sorted(leaked)}; the oracle's "
                "rollout policy must never see an outcome"
            )
