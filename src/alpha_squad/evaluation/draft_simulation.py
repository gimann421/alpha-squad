"""Historical draft simulation (docs/DECISIONS.md D54) -- the empirical-validation phase's
answer to three related directive questions with one reusable engine, rather than three
one-off scripts:

1. Does Alpha make better draft decisions than reasonable alternatives (draft evaluation)?
2. Does adding real league context improve decisions over generic player rankings
   (league-aware vs. generic)?
3. Is "best decision for this roster" actually better than "best player available"
   (roster-aware evaluation)?

Design: fix nine of ten league slots to always draft by real historical market consensus
(the closest honest stand-in for "what real opponents do" -- see `_market_consensus_pick`),
then vary ONLY the tenth "team in question"'s strategy across trials. This isolates exactly
one variable -- the team-in-question's own drafting strategy -- against an identical,
realistic, fixed field, for every real draft slot (1..teams) and every season with real
walk-forward Alpha predictions. That is what makes "strategy X's roster outcome differs from
strategy Y's" a real comparison rather than two runs with different unmeasured opponents.

Every input is either a real, already-persisted, leakage-safe number (`load_season_projections`
draws on M6/M7's walk-forward predictions; market consensus draws on `market_snapshot`'s
real Jul/Aug preseason snapshot, both already used elsewhere in this codebase) or a real
end-of-season outcome (`player_season_stats`). No new scoring model is introduced here --
this module only sequences and scores decisions that other, already-tested modules make.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.league.context import LeagueContext
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.opportunity_cost import best_by_market_rank
from alpha_squad.league.replacement import compute_league_starters, load_season_projections
from alpha_squad.league.roster import unfilled_dedicated_slots
from alpha_squad.market.edge import _preseason_overall_market
from alpha_squad.market.series import resolve_market_series
from alpha_squad.models.baselines.simple import previous_year_baseline
from alpha_squad.sources.base import utcnow

MARKET_CONSENSUS = "market_consensus"
GENERIC_PRIOR_YEAR = "generic_prior_year"
ALPHA_BPA = "alpha_bpa"
ALPHA_LEAGUE_AWARE = "alpha_league_aware"
# D61 Stage 1.1: `market_consensus` never fills a mandatory dedicated starting slot it hasn't
# reached in real ECR order, so a league with slots (like K/DEF) that rank low on the overall
# board can finish the draft with those slots empty -- an artifact that was worth more starter
# points (+245.3, docs/DECISIONS.md D61) than any engine change ever measured. This strategy is
# identical to `market_consensus` EXCEPT that once a drafter's remaining picks equal its still
# -unfilled mandatory slots, it is restricted to filling one of them (still best-available by
# ECR within that restricted pool -- no hindsight, no projection access). Kept as a SEPARATE
# strategy/opponent rather than changing `market_consensus` in place, so every number published
# through D60 stays exactly reproducible under its original name (see docs/DECISIONS.md D56 for
# the precedent: label and supersede, never silently restate).
MARKET_CONSENSUS_ROSTER_AWARE = "market_consensus_roster_aware"

# The four strategies the directive's draft/league-aware/roster-aware questions require:
#   market_consensus    -- Strategy A/B (generic + market are the same real data source here;
#                           see docs/EVALUATION_LIMITATIONS.md -- no distinct ADP series exists
#                           in this environment, D17, so "market consensus" IS the closest real
#                           generic-ranking baseline available, not a stand-in for something else)
#   generic_prior_year   -- a genuinely distinct non-market generic ranking: real prior-season
#                           fantasy points, reusing the existing baseline_previous_year predictor
#   alpha_bpa            -- Alpha's own predicted points, ranked with NO league context at all
#                           (no VORP, no roster fit, no survival probability) -- best-player-
#                           available by Alpha's numbers
#   alpha_league_aware   -- Alpha's real recommend_draft_pick (VORP + roster fit + survival +
#                           confidence) -- the actual decision engine a user gets
#   market_consensus_roster_aware -- market_consensus, but forced to fill a still-empty
#                           mandatory dedicated slot once it is down to exactly enough picks
#                           to do so (D61). The fair reference point: what a consensus drafter
#                           that can at least field a legal lineup actually scores.
ALL_STRATEGIES = (
    MARKET_CONSENSUS,
    GENERIC_PRIOR_YEAR,
    ALPHA_BPA,
    ALPHA_LEAGUE_AWARE,
    MARKET_CONSENSUS_ROSTER_AWARE,
)

# The opponent-field choices `simulate_draft` accepts for its fixed 9-slot field. A subset of
# ALL_STRATEGIES (only strategies that make sense as a homogeneous fixed field belong here);
# kept as its own tuple so a future strategy that only makes sense as the team-in-question
# (e.g. one that reads Alpha's own predictions) is never accidentally offered as an opponent.
ALL_OPPONENT_STRATEGIES = (MARKET_CONSENSUS, MARKET_CONSENSUS_ROSTER_AWARE)


@dataclass
class DraftSimResult:
    season: int
    strategy: str
    draft_slot: int
    drafted_player_ids: list[str] = field(default_factory=list)
    total_roster_points: float = 0.0
    starter_points: float = 0.0
    # D61 Stage 1.1/1.4: which opponent field this strategy was measured against, and how
    # many of ITS OWN mandatory dedicated starting slots the team-in-question finished the
    # draft without filling (a forfeited slot must be visible, not silently score zero).
    opponent_strategy: str = MARKET_CONSENSUS
    n_unfilled_mandatory_slots: int = 0


def _snake_overall_pick(round_no: int, slot: int, teams: int) -> int:
    """1-indexed overall pick number for `slot` (1..teams) in `round_no` (1-indexed) of a
    standard snake draft: odd rounds go 1->teams, even rounds reverse teams->1."""
    if round_no % 2 == 1:
        return (round_no - 1) * teams + slot
    return (round_no - 1) * teams + (teams - slot + 1)


def _next_pick_overall(round_no: int, slot: int, teams: int, total_rounds: int) -> int | None:
    if round_no >= total_rounds:
        return None
    return _snake_overall_pick(round_no + 1, slot, teams)


def _market_consensus_pick(available: set[str], market_rank: dict[str, tuple[str, float]]) -> str:
    """Best remaining player by real preseason overall ECR rank (lower = better). A player
    Alpha's evaluable universe includes but this season's market snapshot doesn't cover
    (rare -- a deep sleeper with no real preseason consensus rank on record) sorts last
    rather than being silently excluded, since a real bot in a real draft still has to pick
    someone.

    `player_id` is a deterministic tie-break, not a ranking preference: real ECR ranks tie
    often (43 tied rank groups in the real 2025 'rsf' data alone), and `available` is a
    Python `set`, whose iteration order depends on hash randomization that differs across
    process runs (unset PYTHONHASHSEED, confirmed) -- without this, a re-run of the exact
    same historical draft could silently pick a different player among ties and produce a
    different (and unreproducible) result. See docs/DECISIONS.md D54.

    Delegates to `league/opportunity_cost.py::best_by_market_rank`, the single canonical
    implementation, so this strategy and the opponent replay used by the production draft
    engine's opportunity-cost term can never drift apart (D55)."""
    return best_by_market_rank(available, market_rank)


def _market_consensus_roster_aware_pick(
    available: set[str],
    market_rank: dict[str, tuple[str, float]],
    positions: dict[str, str],
    league: LeagueContext,
    roster_positions: list[str],
    picks_remaining: int,
) -> str:
    """`_market_consensus_pick`, except once this drafter has exactly as many picks left
    (`picks_remaining`, counting this one) as it has still-unfilled *mandatory* dedicated
    starting slots (`league/roster.py::unfilled_dedicated_slots`), the pick is restricted to
    filling one of them -- a real drafter does not let its final picks pass without being able
    to field a legal lineup. Still best-available by ECR *within* that restricted pool: no
    hindsight, no projection access, nothing else about the strategy changes (D61 Stage 1.1).

    The restriction, once triggered, stays triggered for every remaining pick this drafter
    makes: filling one slot reduces both `picks_remaining` and the deficit by exactly 1, so
    the equality that triggered it holds again next turn -- which is what guarantees every
    mandatory slot is filled by the last pick, not just the first one after the trigger.

    A league with no dedicated slots this format doesn't require (e.g. no `K`) has an empty
    deficit throughout, so this is byte-identical to `_market_consensus_pick` for it -- the
    correctness test the plan names explicitly."""
    deficits = unfilled_dedicated_slots(league, roster_positions)
    total_deficit = sum(deficits.values())
    if total_deficit > 0 and picks_remaining <= total_deficit:
        restricted = {p for p in available if positions.get(p) in deficits}
        if restricted:
            return best_by_market_rank(restricted, market_rank)
    return best_by_market_rank(available, market_rank)


def _generic_prior_year_pick(available: set[str], prior_year_points: dict[str, float]) -> str:
    """See `_market_consensus_pick`'s docstring: the `p` tie-break is for reproducibility
    across process runs, not a stated preference among tied real point totals (real ties are
    common here too -- e.g. two players both scoring exactly 0.0)."""
    return max(available, key=lambda p: (prior_year_points.get(p, float("-inf")), p))


def _alpha_bpa_pick(available: set[str], projections: dict[str, float]) -> str:
    """See `_market_consensus_pick`'s docstring for why `p` is included as a tie-break."""
    return max(available, key=lambda p: (projections.get(p, float("-inf")), p))


def simulate_draft(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    season: int,
    strategy: str,
    draft_slot: int,
    *,
    ecr_type: str | None = None,
    opponent_strategy: str = MARKET_CONSENSUS,
) -> DraftSimResult:
    """Simulate one full snake draft for `season`, with `draft_slot` (1..league.teams) drafting
    by `strategy` and every other slot drafting by `opponent_strategy` (D61 Stage 1.1: either
    the original `market_consensus`, kept byte-identical for reproducing every number published
    through D60, or the fair `market_consensus_roster_aware`). Returns the team-in-question's
    real-outcome-scored roster."""
    if strategy not in ALL_STRATEGIES:
        raise ValueError(f"unknown draft strategy '{strategy}'")
    if opponent_strategy not in ALL_OPPONENT_STRATEGIES:
        raise ValueError(f"unknown opponent strategy '{opponent_strategy}'")
    if not (1 <= draft_slot <= league.teams):
        raise ValueError(f"draft_slot must be in [1, {league.teams}], got {draft_slot}")
    # The consensus opponents ARE the benchmark, so the board they draft from has to be the
    # one that matches this league's format (D56). Resolved from the league rather than fixed:
    # scoring a 1-QB league against the superflex board measures a different game.
    if ecr_type is None:
        ecr_type = resolve_market_series(league).ecr_type

    projections, positions = load_season_projections(con, season)
    available = set(projections)
    market_rank = _preseason_overall_market(con, ecr_type, season)
    prior_year_points = (
        previous_year_baseline(con, season) if strategy == GENERIC_PRIOR_YEAR else {}
    )

    total_rounds = int(league.roster.get("roster_size", 0))
    if total_rounds <= 0:
        raise RuntimeError(f"league '{league.league_id}' has no positive roster_size to draft")

    drafted: list[str] = []
    my_roster_positions: list[str] = []
    # D61 Stage 1.1: {slot: [position, position, ...]} for every non-question slot's own
    # roster -- roster-awareness is per-team, not league-wide, so a fair opponent needs to
    # know only what IT has drafted, not what every opponent has.
    opponent_roster_positions: dict[int, list[str]] = {
        slot: [] for slot in range(1, league.teams + 1) if slot != draft_slot
    }

    for round_no in range(1, total_rounds + 1):
        order = range(1, league.teams + 1) if round_no % 2 == 1 else range(league.teams, 0, -1)
        # Every slot picks exactly once per round in a standard snake draft, so this is exact
        # for every slot, question or opponent, at this round.
        picks_remaining_this_round_on = total_rounds - round_no + 1
        for slot in order:
            if not available:
                break
            if slot == draft_slot:
                if strategy == MARKET_CONSENSUS:
                    pick = _market_consensus_pick(available, market_rank)
                elif strategy == MARKET_CONSENSUS_ROSTER_AWARE:
                    pick = _market_consensus_roster_aware_pick(
                        available,
                        market_rank,
                        positions,
                        league,
                        my_roster_positions,
                        picks_remaining_this_round_on,
                    )
                elif strategy == GENERIC_PRIOR_YEAR:
                    pick = _generic_prior_year_pick(available, prior_year_points)
                elif strategy == ALPHA_BPA:
                    pick = _alpha_bpa_pick(available, projections)
                else:  # ALPHA_LEAGUE_AWARE
                    next_pick = _next_pick_overall(round_no, slot, league.teams, total_rounds)
                    rec = recommend_draft_pick(
                        con,
                        league,
                        season,
                        my_roster_positions,
                        available,
                        next_pick_overall=next_pick,
                        ecr_type=ecr_type,
                        top_n=1,
                        # D55: the engine's positional opportunity-cost term needs to know how
                        # many picks other teams make before this team's next turn; the snake
                        # geometry is known exactly here.
                        current_pick_overall=_snake_overall_pick(round_no, slot, league.teams),
                        # D60: `drafted` IS this team's actual roster at this point (it only
                        # ever receives this team's own picks -- see the loop above), so the
                        # engine can score candidates by marginal starter value rather than
                        # falling back to VORP.
                        roster_player_ids=drafted,
                    )
                    pick = rec.recommendation
                drafted.append(pick)
                my_roster_positions.append(positions.get(pick, "UNKNOWN"))
            else:
                # Every non-question slot drafts by the same fixed opponent strategy, so the
                # only thing that varies across strategy trials is the team-in-question's own
                # decision -- see module docstring. Which opponent strategy varies across
                # *opponent_strategy* trials instead (D61 Stage 1.1).
                if opponent_strategy == MARKET_CONSENSUS_ROSTER_AWARE:
                    pick = _market_consensus_roster_aware_pick(
                        available,
                        market_rank,
                        positions,
                        league,
                        opponent_roster_positions[slot],
                        picks_remaining_this_round_on,
                    )
                else:
                    pick = _market_consensus_pick(available, market_rank)
                opponent_roster_positions[slot].append(positions.get(pick, "UNKNOWN"))
            available.discard(pick)

    actual_points = _actual_points_for(con, season, drafted)
    total_points = sum(actual_points.values())
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        actual_points,
        {p: positions.get(p, "UNKNOWN") for p in drafted},
    )
    starter_points = sum(actual_points.get(p, 0.0) for p in starters["starters"])
    n_unfilled = sum(unfilled_dedicated_slots(league, my_roster_positions).values())

    return DraftSimResult(
        season=season,
        strategy=strategy,
        draft_slot=draft_slot,
        drafted_player_ids=drafted,
        total_roster_points=total_points,
        starter_points=starter_points,
        opponent_strategy=opponent_strategy,
        n_unfilled_mandatory_slots=n_unfilled,
    )


def _actual_points_for(
    con: duckdb.DuckDBPyConnection, season: int, player_ids: list[str]
) -> dict[str, float]:
    if not player_ids:
        return {}
    rows = con.execute(
        "SELECT player_id, total_fantasy_points_ppr FROM player_season_stats "
        "WHERE season = ? AND player_id = ANY(?)",
        [season, player_ids],
    ).fetchall()
    found = dict(rows)
    # A drafted player with no real season row (e.g. a rookie who never played) really did
    # score 0 real fantasy points -- that is the honest outcome of that pick, not a gap to
    # paper over.
    return {p: found.get(p, 0.0) for p in player_ids}


def run_draft_simulation(
    con: duckdb.DuckDBPyConnection,
    league: LeagueContext,
    seasons: list[int],
    strategies: list[str] | None = None,
    *,
    ecr_type: str | None = None,
    opponent_strategies: list[str] | None = None,
) -> list[DraftSimResult]:
    """Every (season, strategy, opponent_strategy, draft_slot) combination -- every real draft
    slot drafts under every strategy once per season, so no single lucky/unlucky slot drives a
    strategy's apparent result.

    `opponent_strategies` defaults to `[MARKET_CONSENSUS]` alone -- the original, single fixed
    field every number published through D60 was measured against -- so an existing caller that
    doesn't pass this keeps getting exactly the same trials it always has. Pass
    `ALL_OPPONENT_STRATEGIES` for the fair side-by-side comparison D61 Stage 1.1 calls for."""
    strategies = strategies if strategies is not None else list(ALL_STRATEGIES)
    opponent_strategies = (
        opponent_strategies if opponent_strategies is not None else [MARKET_CONSENSUS]
    )
    results: list[DraftSimResult] = []
    for season in seasons:
        for strategy in strategies:
            for opponent_strategy in opponent_strategies:
                for slot in range(1, league.teams + 1):
                    results.append(
                        simulate_draft(
                            con,
                            league,
                            season,
                            strategy,
                            slot,
                            ecr_type=ecr_type,
                            opponent_strategy=opponent_strategy,
                        )
                    )
    return results


def persist_draft_sim_results(
    con: duckdb.DuckDBPyConnection, results: list[DraftSimResult]
) -> None:
    now = utcnow()
    for r in results:
        con.execute(
            """
            INSERT INTO draft_simulation_results
                (season, strategy, draft_slot, drafted_player_ids_json, total_roster_points,
                 starter_points, framework_version, evaluated_at, opponent_strategy,
                 n_unfilled_mandatory_slots)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (season, strategy, opponent_strategy, draft_slot, framework_version)
            DO UPDATE SET
                drafted_player_ids_json = excluded.drafted_player_ids_json,
                total_roster_points = excluded.total_roster_points,
                starter_points = excluded.starter_points,
                evaluated_at = excluded.evaluated_at,
                n_unfilled_mandatory_slots = excluded.n_unfilled_mandatory_slots
            """,
            [
                r.season,
                r.strategy,
                r.draft_slot,
                json.dumps(r.drafted_player_ids),
                r.total_roster_points,
                r.starter_points,
                EVALUATION_FRAMEWORK_VERSION,
                now,
                r.opponent_strategy,
                r.n_unfilled_mandatory_slots,
            ],
        )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def summarize_draft_sim(con: duckdb.DuckDBPyConnection, seasons: list[int]) -> list[dict]:
    """Per-(strategy, opponent_strategy) mean/stdev of total_roster_points and starter_points
    across every persisted (season, draft_slot) trial in `seasons`, plus n so a reader can
    judge whether the sample is large enough to trust a difference, and
    `mean_unfilled_mandatory_slots`/`n_trials_with_unfilled_slots` so a forfeited mandatory
    slot shows up as a visible number rather than silently scoring zero (D61 Stage 1.4)."""
    rows = con.execute(
        """
        SELECT strategy, opponent_strategy, total_roster_points, starter_points,
               n_unfilled_mandatory_slots
        FROM draft_simulation_results
        WHERE season = ANY(?) AND framework_version = ?
        """,
        [seasons, EVALUATION_FRAMEWORK_VERSION],
    ).fetchall()
    by_key: dict[tuple[str, str], list[tuple[float, float, int]]] = {}
    for strategy, opponent_strategy, total_pts, starter_pts, n_unfilled in rows:
        by_key.setdefault((strategy, opponent_strategy), []).append(
            (total_pts, starter_pts, n_unfilled)
        )

    summary = []
    for (strategy, opponent_strategy), triples in by_key.items():
        totals = [t[0] for t in triples]
        starters = [t[1] for t in triples]
        unfilled = [t[2] for t in triples]
        summary.append(
            {
                "strategy": strategy,
                "opponent_strategy": opponent_strategy,
                "n": len(triples),
                "mean_total_roster_points": _mean(totals),
                "stdev_total_roster_points": _stdev(totals),
                "mean_starter_points": _mean(starters),
                "stdev_starter_points": _stdev(starters),
                "mean_unfilled_mandatory_slots": _mean([float(u) for u in unfilled]),
                "n_trials_with_unfilled_slots": sum(1 for u in unfilled if u > 0),
            }
        )
    summary.sort(key=lambda r: (r["opponent_strategy"], -r["mean_starter_points"]))
    return summary


def write_draft_simulation_report(
    con: duckdb.DuckDBPyConnection, path: Path, seasons: list[int]
) -> list[dict]:
    """Writes a human-readable markdown report and returns the same summary rows (so a
    caller can also serialize them to JSON without re-querying).

    Reports every opponent-field strategy actually present in the persisted results
    side by side (D61 Stage 1.1/1.4) -- `market_consensus` (published through D60; its
    opponent field can finish a draft with a mandatory slot like K/DEF still empty) and, when
    present, the fair `market_consensus_roster_aware` (forced to fill one once it is down to
    exactly enough picks to do so). No published number is silently restated: a run that only
    persisted `market_consensus` trials (the pre-D61 default) renders exactly that, labeled."""
    summary = summarize_draft_sim(con, seasons)
    opponent_strategies_present = sorted({row["opponent_strategy"] for row in summary})
    per_season_rows = con.execute(
        """
        SELECT season, strategy, opponent_strategy, avg(total_roster_points),
               avg(starter_points), avg(n_unfilled_mandatory_slots), count(*)
        FROM draft_simulation_results
        WHERE season = ANY(?) AND framework_version = ?
        GROUP BY season, strategy, opponent_strategy
        ORDER BY season, opponent_strategy, strategy
        """,
        [seasons, EVALUATION_FRAMEWORK_VERSION],
    ).fetchall()

    if MARKET_CONSENSUS_ROSTER_AWARE in opponent_strategies_present:
        headline_banner = (
            f"> **Headline claim uses `{MARKET_CONSENSUS_ROSTER_AWARE}`.** `{MARKET_CONSENSUS}`'s "
            "opponent field can finish a draft with a mandatory dedicated slot (e.g. K/DEF) "
            "still unfilled -- worth more starter points than any measured engine change "
            "(docs/DECISIONS.md D61). It is kept and reported below only so every number "
            "published through D60 stays exactly reproducible under its original label."
        )
    else:
        headline_banner = (
            f"> **This run only measured `{MARKET_CONSENSUS}`**, the opponent field published "
            "through D60. Its consensus opponent can finish a draft with a mandatory dedicated "
            "slot (e.g. K/DEF) still unfilled -- see the `n_unfilled_mandatory_slots` columns "
            "below and docs/DECISIONS.md D61. Pass `opponent_strategies=ALL_OPPONENT_STRATEGIES` "
            f"to also measure the fair `{MARKET_CONSENSUS_ROSTER_AWARE}` opponent."
        )

    lines = [
        "# Draft simulation: does Alpha make better draft decisions?",
        "",
        headline_banner,
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. Seasons: {min(seasons)}-{max(seasons)} "
        f"(every season with a real walk-forward `uncertainty_predictions` row -- see "
        "docs/EVALUATION_LIMITATIONS.md for why this window can't be widened without fabricating "
        "predictions for seasons the model never actually ran on).",
        "",
        "## Methodology",
        "",
        'One team (the "team in question") drafts under a fixed strategy from every one of '
        "the league's 10 draft slots, once per season. The other 9 slots always draft by a "
        "fixed opponent field -- so the only thing that varies between trials is the "
        "team-in-question's own strategy. Rosters are scored on real end-of-season "
        "`player_season_stats` outcomes the strategy could not have seen at draft time.",
        "",
        f"Opponent fields: `{MARKET_CONSENSUS}` (best remaining player by real preseason ECR, "
        "unconditionally -- can finish with a mandatory slot unfilled if that position never "
        "ranks well enough by the last round it's reached) and "
        f"`{MARKET_CONSENSUS_ROSTER_AWARE}` (identical, except once it has exactly as many "
        "picks left as unfilled mandatory dedicated slots, it is restricted to filling one -- "
        "still best-available by ECR within that restriction; D61 Stage 1.1).",
        "",
        "Strategies: `market_consensus` (also stands in for a generic/ADP-style approach; no "
        "separate ADP series exists in this environment, see docs/EVALUATION_LIMITATIONS.md), "
        "`market_consensus_roster_aware` (the fair reference point), `generic_prior_year` (best "
        "remaining player by real prior-season fantasy points), `alpha_bpa` (Alpha's own "
        "predicted points, best-player-available, no league context), `alpha_league_aware` "
        "(Alpha's real `recommend_draft_pick` -- VORP/marginal starter value, roster fit, "
        "survival probability, confidence).",
    ]

    for opponent_strategy in opponent_strategies_present:
        lines += [
            "",
            f"## Overall vs `{opponent_strategy}` opponent field (all seasons, all draft slots pooled)",
            "",
            "| Strategy | n | Mean starter pts | Stdev | Mean total roster pts | Stdev | "
            "Mean unfilled mandatory slots | Trials w/ unfilled slot |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for row in summary:
            if row["opponent_strategy"] != opponent_strategy:
                continue
            lines.append(
                f"| {row['strategy']} | {row['n']} | {row['mean_starter_points']:.1f} | "
                f"{row['stdev_starter_points']:.1f} | {row['mean_total_roster_points']:.1f} | "
                f"{row['stdev_total_roster_points']:.1f} | "
                f"{row['mean_unfilled_mandatory_slots']:.2f} | "
                f"{row['n_trials_with_unfilled_slots']}/{row['n']} |"
            )

    lines += [
        "",
        "## Per season",
        "",
        "| Season | Opponent | Strategy | Mean total roster pts | Mean starter pts | "
        "Mean unfilled slots | n |",
        "|---|---|---|---|---|---|---|",
    ]
    for (
        season,
        strategy,
        opponent_strategy,
        mean_total,
        mean_starter,
        mean_unfilled,
        n,
    ) in per_season_rows:
        lines.append(
            f"| {season} | {opponent_strategy} | {strategy} | {mean_total:.1f} | "
            f"{mean_starter:.1f} | {mean_unfilled:.2f} | {n} |"
        )

    lines += [
        "",
        "## Reading this honestly",
        "",
        "This experiment answers three directive questions with one design: `alpha_league_aware` "
        "vs. `market_consensus`/`generic_prior_year` is the draft-evaluation question; "
        "`alpha_league_aware` vs. `alpha_bpa` (identical Alpha predictions, only roster "
        "context/VORP differ) is the league-aware-vs-generic and best-player-available-vs-"
        "best-for-this-roster question in one comparison. n is small by statistical standards "
        "(10 draft slots x up to 5 real seasons per strategy) -- a real effect should show up "
        "consistently across seasons in the per-season table above, not just in the pooled "
        "mean. Do not treat a single season's row as a claim on its own.",
        "",
        "A nonzero `n_unfilled_mandatory_slots`/`Mean unfilled mandatory slots` reading means "
        "the roster this strategy drafted, scored on real outcomes, was missing a player for a "
        "starting slot the league requires -- that slot scored 0, and the comparison against a "
        "strategy that filled it is not apples to apples. Compare `market_consensus` numbers "
        f"only against other `{MARKET_CONSENSUS}`-opponent rows, and "
        f"`{MARKET_CONSENSUS_ROSTER_AWARE}` rows only against each other.",
        "",
    ]
    path.write_text("\n".join(lines))
    return summary
