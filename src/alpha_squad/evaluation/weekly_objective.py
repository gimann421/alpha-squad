"""The draft objective computed WEEKLY rather than season-long (D86 Phase 2/8).

Why this exists
---------------
Every draft number this project has published scores a roster the same way: take the 16 drafted
players, take each one's *season total*, and pick the best legal lineup once
(`compute_league_starters` on season totals). Call that the **season-long objective**.

That is not how fantasy football scores. A real manager sets a lineup **every week**, from
whoever is actually available that week. The correct quantity is

    U(roster) = SUM over weeks of ( best legal lineup among roster players who PLAYED that week )

and the difference between the two is not a detail. The season-long objective:

* **cannot see a bye week.** It starts the same eleven players in all 17 weeks, including the
  weeks they did not play. A real roster that week starts someone else or forfeits the slot.
* **cannot see an injury.** A player who tore an ACL in week 3 contributes his (small) season
  total to the lineup and never vacates the slot.
* **therefore gives the bench a value of exactly zero.** A backup can never enter the lineup,
  because the starter never leaves it. D84 recorded this as the reason a spot spent on a kicker
  who starts beats a spot spent on a receiver who does not, and named a better objective as "the
  single highest-value next step".

The weekly objective fixes all three **with no new data, no new parameter and no new term**. A
bye and an injury are both simply a *missing weekly row*: nflverse writes a `player_week_stats`
row when a player played, so "who is available in week w" is already recorded. Bench value is
not a bonus that has to be added and tuned -- it is what the objective produces on its own once
the lineup is set weekly, which is exactly the property D84 said was missing.

What it still does NOT model, stated so the remaining gap stays honest
----------------------------------------------------------------------
* **Waivers and trades.** The roster is fixed at its drafted 16 all season. Real managers churn
  the bottom of the roster constantly, and there is no transaction history in this database to
  model it from (checked: no transactions table; Sleeper's `trending_adds` is a live snapshot,
  not history). This makes the weekly objective a *lower* bound on the value of roster
  flexibility, not an upper one.
* **Lineup-setting skill.** `weekly_lineup_points` uses hindsight within the week -- it fields
  the best lineup the roster *could* have fielded. A real manager guesses. Use
  `weekly_lineup_points_no_foresight` for the opposite bound, which ranks that week's available
  players by preseason projection instead of by what they scored.

The two bracket the achievable range, and both are reported wherever this module is used, because
the hindsight version alone would overstate bench value and the no-foresight version alone would
understate it.
"""

from __future__ import annotations

import duckdb

from alpha_squad.league.context import LeagueContext
from alpha_squad.league.replacement import compute_league_starters

#: Weeks that count. A standard league plays a 14-week regular season and a 3-week playoff, so
#: 1-17; week 18 exists in the data from 2021 on but is not a fantasy week.
FANTASY_WEEKS: tuple[int, ...] = tuple(range(1, 18))


def load_weekly_points(
    con: duckdb.DuckDBPyConnection, season: int, weeks: tuple[int, ...] = FANTASY_WEEKS
) -> dict[tuple[str, int], float]:
    """{(player_id, week): PPR points} for every player who actually PLAYED that week.

    A missing key is the whole mechanism: it means bye, injury, inactive or not on a roster --
    all of which have the same consequence for a lineup, namely that the player cannot be
    started. Nothing is imputed."""
    rows = con.execute(
        "SELECT player_id, week, fantasy_points_ppr FROM player_week_stats "
        "WHERE season = ? AND week BETWEEN ? AND ?",
        [season, min(weeks), max(weeks)],
    ).fetchall()
    return {(r[0], int(r[1])): float(r[2] or 0.0) for r in rows if int(r[1]) in weeks}


def weekly_lineup_points(
    league: LeagueContext,
    roster: list[str],
    positions: dict[str, str],
    weekly: dict[tuple[str, int], float],
    weeks: tuple[int, ...] = FANTASY_WEEKS,
) -> float:
    """`U(roster)` -- the sum over weeks of the best legal lineup the roster could field.

    Uses `compute_league_starters` with `teams=1`, the same allocator the season-long benchmark
    uses, so the ONLY thing that differs between the two objectives is the weekly granularity.
    A slot the roster cannot fill in a given week simply scores zero for that week, which is what
    really happens."""
    total = 0.0
    single_team = league.model_copy(update={"teams": 1})
    for week in weeks:
        available = {p: weekly[(p, week)] for p in roster if (p, week) in weekly}
        if not available:
            continue
        starters = compute_league_starters(
            single_team, available, {p: positions.get(p, "UNKNOWN") for p in available}
        )
        total += sum(available.get(p, 0.0) for p in starters["starters"])
    return total


def weekly_lineup_points_no_foresight(
    league: LeagueContext,
    roster: list[str],
    positions: dict[str, str],
    weekly: dict[tuple[str, int], float],
    projections: dict[str, float],
    weeks: tuple[int, ...] = FANTASY_WEEKS,
) -> float:
    """The same quantity, but the lineup is chosen by PRESEASON PROJECTION rather than by what
    each player actually scored that week -- a manager who knows who is available but not who
    will do well.

    This is the pessimistic bracket. `weekly_lineup_points` is the optimistic one. The truth for
    a real manager sits between them, and quoting either alone would be a claim the data cannot
    support."""
    total = 0.0
    single_team = league.model_copy(update={"teams": 1})
    for week in weeks:
        available = [p for p in roster if (p, week) in weekly]
        if not available:
            continue
        starters = compute_league_starters(
            single_team,
            {p: projections.get(p, 0.0) for p in available},
            {p: positions.get(p, "UNKNOWN") for p in available},
        )
        total += sum(weekly.get((p, week), 0.0) for p in starters["starters"])
    return total


def season_long_lineup_points(
    league: LeagueContext,
    roster: list[str],
    positions: dict[str, str],
    season_totals: dict[str, float],
) -> float:
    """The INCUMBENT objective, reproduced here so the two can be compared on one roster with a
    single call each. Identical to what `draft_simulation`/`draft_forensics` score with."""
    starters = compute_league_starters(
        league.model_copy(update={"teams": 1}),
        {p: season_totals.get(p, 0.0) for p in roster},
        {p: positions.get(p, "UNKNOWN") for p in roster},
    )
    return sum(season_totals.get(p, 0.0) for p in starters["starters"])


def bench_contribution(
    league: LeagueContext,
    roster: list[str],
    positions: dict[str, str],
    weekly: dict[tuple[str, int], float],
    season_totals: dict[str, float],
    weeks: tuple[int, ...] = FANTASY_WEEKS,
) -> float:
    """How many weekly-objective points come from players the SEASON-LONG objective never starts.

    This is the number D84 said the benchmark could not see. It is computed, not assumed: field
    the weekly lineup, then subtract the weekly points contributed by the players the season-long
    allocator would have designated starters. What remains was contributed by the bench."""
    season_starters = set(
        compute_league_starters(
            league.model_copy(update={"teams": 1}),
            {p: season_totals.get(p, 0.0) for p in roster},
            {p: positions.get(p, "UNKNOWN") for p in roster},
        )["starters"]
    )
    total = 0.0
    single_team = league.model_copy(update={"teams": 1})
    for week in weeks:
        available = {p: weekly[(p, week)] for p in roster if (p, week) in weekly}
        if not available:
            continue
        fielded = compute_league_starters(
            single_team, available, {p: positions.get(p, "UNKNOWN") for p in available}
        )["starters"]
        total += sum(available.get(p, 0.0) for p in fielded if p not in season_starters)
    return total


# --------------------------------------------------------------------------------------------
# The forward-looking form: EXPECTED weekly lineup value (D86 Phase 11 candidate)
# --------------------------------------------------------------------------------------------
# Everything above scores a roster whose outcomes are already known. A DECISION needs the same
# quantity in expectation, computable on draft day from projections alone.
#
# The only new input is a per-position availability rate, and it is a MEASURED population
# statistic rather than a tuned constant: the fraction of fantasy weeks a draftable player at
# that position was actually available, over prior seasons. It is the same quantity D70's
# pre-registration already calls `avail_position_cohort_games` (feature F3), used here for the
# purpose it names.
#
# This is what makes bench depth priced WITHOUT a bench bonus. A backup enters the lineup exactly
# when a starter is unavailable, which happens at a rate the data reports; nothing is assumed.

#: How many availability draws `expected_weekly_starter_points` averages over. Not a tuning dial:
#: the estimator uses COMMON RANDOM NUMBERS (a player's availability sequence is a deterministic
#: function of his id), so the *difference* between two candidates is far more precise than the
#: absolute level, and a few hundred draws resolves it. Raising it cannot change a ranking
#: materially, only the shared constant both sides carry.
DEFAULT_AVAILABILITY_DRAWS = 200


def measure_availability_rates(
    con: duckdb.DuckDBPyConnection,
    seasons: tuple[int, ...],
    *,
    per_team_demand: dict[str, float] | None = None,
    teams: int = 10,
    weeks: tuple[int, ...] = FANTASY_WEEKS,
) -> dict[str, float]:
    """{position: fraction of fantasy weeks a DRAFTABLE player at that position was available}.

    Draftable is defined by the league's own consumption demand rather than by an arbitrary
    cutoff, so this measures the pool a draft actually consumes. Measured strictly on seasons the
    caller passes -- a walk-forward caller passes only seasons before the one being drafted.

    Returns rates in (0, 1]. A position with no data is omitted rather than defaulted, so a caller
    that silently expected one gets a KeyError instead of a fabricated rate."""
    demand = per_team_demand or {"QB": 2.2, "RB": 4.2, "WR": 5.8, "TE": 1.8, "K": 1.0, "DST": 1.0}
    out: dict[str, list[float]] = {}
    for season in seasons:
        for pos, per_team in demand.items():
            n = max(1, int(round(teams * per_team)))
            top = [
                r[0]
                for r in con.execute(
                    "SELECT player_id FROM player_season_stats WHERE season = ? AND position = ? "
                    "ORDER BY total_fantasy_points_ppr DESC LIMIT ?",
                    [season, pos, n],
                ).fetchall()
            ]
            if not top:
                continue
            counts = dict(
                con.execute(
                    "SELECT player_id, count(*) FROM player_week_stats WHERE season = ? "
                    "AND week BETWEEN ? AND ? AND player_id = ANY(?) GROUP BY 1",
                    [season, min(weeks), max(weeks), top],
                ).fetchall()
            )
            out.setdefault(pos, []).append(
                sum(counts.get(p, 0) for p in top) / (len(top) * len(weeks))
            )
    return {pos: sum(v) / len(v) for pos, v in out.items() if v}


def _available_in_draw(player_id: str, draw: int, rate: float) -> bool:
    """Deterministic COMMON RANDOM NUMBERS: a player's availability in draw `d` depends only on
    his id and `d`, never on which candidate is being evaluated or what else is on the roster.

    This is what makes the estimator usable for a DIFFERENCE. Two candidate rosters that share
    fifteen players see those fifteen players behave identically in every draw, so the difference
    between them is driven by the sixteenth rather than by sampling noise. Using a fresh RNG per
    evaluation instead would swamp a real ~5-point difference in ~50 points of Monte Carlo noise.
    """
    # splitmix-style avalanche on a stable hash of (id, draw); `hash()` is salted per process, so
    # it cannot be used -- reproducibility across runs is required (D54).
    h = 1469598103934665603
    for ch in player_id:
        h = ((h ^ ord(ch)) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    h = ((h ^ draw) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    h ^= h >> 33
    h = (h * 0xFF51AFD7ED558CCD) & 0xFFFFFFFFFFFFFFFF
    h ^= h >> 33
    return (h / 0xFFFFFFFFFFFFFFFF) < rate


def expected_weekly_starter_points(
    league: LeagueContext,
    roster: list[str],
    values: dict[str, float],
    positions: dict[str, str],
    rates: dict[str, float],
    *,
    n_draws: int = DEFAULT_AVAILABILITY_DRAWS,
) -> float:
    """`E[ weekly lineup value ]` for a roster, per week, under independent availability.

    `values` are per-week values (a season projection divided by the number of fantasy weeks, or
    any per-week quantity); the result is on the same per-week scale, so multiply by the number
    of weeks for a season figure.

    Independence across players is an approximation and is stated rather than hidden: real
    availability is correlated (a team's bye takes its whole stack out at once). Modelling the
    bye correlation properly needs a schedule join; the effect is to make depth slightly MORE
    valuable than this estimate, so the approximation is conservative in the direction that
    matters for the conclusion."""
    single_team = league.model_copy(update={"teams": 1})
    total = 0.0
    for draw in range(n_draws):
        available = {
            p: values.get(p, 0.0)
            for p in roster
            if _available_in_draw(p, draw, rates.get(positions.get(p, ""), 1.0))
        }
        if not available:
            continue
        starters = compute_league_starters(
            single_team, available, {p: positions.get(p, "UNKNOWN") for p in available}
        )
        total += sum(available.get(p, 0.0) for p in starters["starters"])
    return total / n_draws


def expected_weekly_marginal_value(
    league: LeagueContext,
    roster: list[str],
    candidate: str,
    values: dict[str, float],
    positions: dict[str, str],
    rates: dict[str, float],
    *,
    n_draws: int = DEFAULT_AVAILABILITY_DRAWS,
    base: float | None = None,
) -> float:
    """The availability-aware replacement for `marginal_starter_value`.

    `E[U(roster + candidate)] - E[U(roster)]`. Differs from the shipped MSV in exactly one way:
    the lineup is fielded from players who are *available*, at measured per-position rates,
    rather than from all sixteen every week.

    Two consequences follow with no extra machinery, and they are the whole point:

    * a player at a SATURATED position is worth more than zero, because the starters ahead of him
      are absent some of the time -- so the bench is priced without a bench bonus;
    * depth is worth more at positions that miss more time. Measured 2021-2025, a draftable RB is
      available 85.3% of weeks against a kicker's 93.6%, so RB depth is priced above K depth by
      the data rather than by a positional rule.
    """
    if base is None:
        base = expected_weekly_starter_points(
            league, roster, values, positions, rates, n_draws=n_draws
        )
    with_candidate = expected_weekly_starter_points(
        league, [*roster, candidate], values, positions, rates, n_draws=n_draws
    )
    return with_candidate - base
