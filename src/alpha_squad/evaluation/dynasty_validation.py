"""Validates the two documented dynasty heuristics (docs/DECISIONS.md D54) that were never
checked against real outcomes when they were built:

- `league/trade.py::pick_value` (D45) assumes real fantasy value declines by round the way
  `PICK_ROUND_BASE_VALUE` (2200/300/60/15 for rounds 1-4, halving each round after) shapes it,
  and declines within a round from the first pick to the last.
- `league/trade.py::age_curve_multiplier` (D25) assumes real production is flat until a
  position-specific `decline_start` age, then linearly decays to 0.5x at a `cliff` age.

Both are explicitly documented as heuristics, not trained models, because no ground-truth
dataset existed to fit one against. This module doesn't replace them with a trained model --
it checks whether the *shape* they assume (declining by round/pick, declining after a
position-specific age) actually matches real, already-ingested history: real NFL draft
capital (`players.draft_year/draft_round/draft_pick`, COALESCEd from nflverse's real
`draft_picks` file) and real career fantasy production (`player_season_stats`, 2012-2025).

Known confound, stated plainly rather than hidden: this is an observational, not causal,
check. Real survivorship bias applies to the age-curve check in particular -- a player who
declined sharply usually stops appearing in the league (and therefore in this dataset)
altogether, so the "still active at age 33" cohort is a selected group of unusually durable
players, not a random sample of every player who was ever 33. A flatter-than-expected
empirical decline at older ages is consistent with the heuristic being wrong, but it is
equally consistent with this selection effect -- this module reports the real numbers and
names the confound, not adjudicates between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.league.trade import AGE_CURVE_PARAMS
from alpha_squad.models.evaluate import SKILL_POSITIONS

MIN_GAMES_FOR_AGE_CURVE = 4  # excludes injury-shortened/late-signing seasons too small to be
# representative of that player-age's real week-to-week production, without requiring a full
# season (a real, meaningfully-played partial season is still real evidence).


@dataclass
class PickRoundOutcome:
    round: int
    n_players: int
    mean_rookie_season_points: float
    mean_best_of_first3_points: float


def build_pick_value_validation(
    con: duckdb.DuckDBPyConnection, draft_year_start: int = 2012, draft_year_end: int = 2023
) -> list[PickRoundOutcome]:
    """`draft_year_end` defaults to 2023 (not the latest draft class) so every included class
    has had at least 3 real NFL seasons to establish "best of first 3 seasons" -- including a
    2025 draftee here would compare a 1-season-old player's ceiling against a 2015 draftee's
    3-season ceiling, which isn't a fair round-vs-round comparison."""
    rows = con.execute(
        """
        SELECT p.draft_round, p.player_id, p.draft_year, p.rookie_season
        FROM players p
        WHERE p.draft_year BETWEEN ? AND ? AND p.draft_round IS NOT NULL
          AND p.position = ANY(?)
        """,
        [draft_year_start, draft_year_end, list(SKILL_POSITIONS)],
    ).fetchall()

    by_round: dict[int, list[tuple[float, float]]] = {}
    for draft_round, player_id, _draft_year, rookie_season in rows:
        if rookie_season is None:
            continue
        seasons = con.execute(
            "SELECT season, total_fantasy_points_ppr FROM player_season_stats "
            "WHERE player_id = ? AND season BETWEEN ? AND ?",
            [player_id, rookie_season, rookie_season + 2],
        ).fetchall()
        if not seasons:
            continue
        by_season = dict(seasons)
        rookie_points = by_season.get(rookie_season, 0.0)
        best3 = max(by_season.values())
        by_round.setdefault(draft_round, []).append((rookie_points, best3))

    results = []
    for round_no in sorted(by_round):
        pairs = by_round[round_no]
        n = len(pairs)
        results.append(
            PickRoundOutcome(
                round=round_no,
                n_players=n,
                mean_rookie_season_points=sum(p[0] for p in pairs) / n,
                mean_best_of_first3_points=sum(p[1] for p in pairs) / n,
            )
        )
    return results


@dataclass
class AgeCurvePoint:
    position: str
    age: int
    n: int
    mean_ppr_points_per_game: float


def build_age_curve_validation(
    con: duckdb.DuckDBPyConnection, season_start: int = 2012, season_end: int = 2025
) -> list[AgeCurvePoint]:
    rows = con.execute(
        """
        SELECT
            s.position,
            date_diff('year', p.birth_date, make_date(s.season, 9, 1)) AS age,
            s.ppr_points_per_game
        FROM player_season_stats s
        JOIN players p ON p.player_id = s.player_id
        WHERE s.season BETWEEN ? AND ? AND s.games_played >= ?
          AND s.position = ANY(?) AND p.birth_date IS NOT NULL
        """,
        [season_start, season_end, MIN_GAMES_FOR_AGE_CURVE, list(AGE_CURVE_PARAMS)],
    ).fetchall()

    by_key: dict[tuple[str, int], list[float]] = {}
    for position, age, ppg in rows:
        if age is None or age < 18 or age > 45:
            continue  # a birth_date/season pairing outside any plausible NFL age is a data
            # error, not a real observation -- exclude rather than let it distort a bucket mean
        by_key.setdefault((position, int(age)), []).append(ppg)

    points = []
    for (position, age), values in sorted(by_key.items()):
        points.append(
            AgeCurvePoint(
                position=position,
                age=age,
                n=len(values),
                mean_ppr_points_per_game=sum(values) / len(values),
            )
        )
    return points


def write_dynasty_validation_report(
    con: duckdb.DuckDBPyConnection, path: Path, draft_year_end: int = 2023
) -> dict:
    pick_outcomes = build_pick_value_validation(con, draft_year_end=draft_year_end)
    age_points = build_age_curve_validation(con)

    lines = [
        "# Dynasty heuristic validation: pick value and age curves against real outcomes",
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. Both `pick_value` (D45) and "
        "`age_curve_multiplier` (D25) are documented heuristics, never fit to data. This "
        "checks whether the *shape* they assume matches real history -- see this module's "
        "docstring for the real survivorship-bias confound in the age-curve check.",
        "",
        "## Pick value: does real production decline the way the heuristic assumes?",
        "",
        f"Real skill-position ({'/'.join(SKILL_POSITIONS)}) draftees, {draft_year_end - 11}-"
        f"{draft_year_end} classes (needs 3 real seasons of data, so recent classes are "
        "excluded -- see module docstring).",
        "",
        "| Round | n | Mean rookie-season pts | Mean best-of-first-3-seasons pts |",
        "|---|---|---|---|",
    ]
    for o in pick_outcomes:
        lines.append(
            f"| {o.round} | {o.n_players} | {o.mean_rookie_season_points:.1f} | {o.mean_best_of_first3_points:.1f} |"
        )

    # `strict=True` is wrong here: comparing a list against its own one-shifted tail means
    # the two sides are *always* one element apart by construction, and strict mode raises
    # ValueError as soon as the shorter side is exhausted -- which happens precisely when
    # every single comparison is True (the "cleanly monotonic" case), since `all()` only
    # short-circuits before then if it finds a False first. Found live: a real, perfectly
    # monotonic 7-round pick-value result crashed this exact line.
    monotonic_rookie = all(
        a.mean_rookie_season_points >= b.mean_rookie_season_points
        for a, b in zip(pick_outcomes, pick_outcomes[1:], strict=False)
    )
    monotonic_best3 = all(
        a.mean_best_of_first3_points >= b.mean_best_of_first3_points
        for a, b in zip(pick_outcomes, pick_outcomes[1:], strict=False)
    )
    lines += [
        "",
        f"**Monotonically decreasing by round (rookie-season points): {monotonic_rookie}.** "
        f"**(best-of-first-3-seasons points): {monotonic_best3}.**",
        "",
        "The heuristic's exact ratios (round 1 valued ~7.3x round 2, ~36.7x round 3) are not "
        "expected to match real point ratios -- `pick_value` prices draft *assets* under "
        "uncertainty (most picks bust; the value reflects the right tail an early pick still "
        "has access to), not the expected mean outcome measured here. What this table can "
        "actually validate is the *direction*: does real production really fall monotonically "
        "by round, or does the heuristic assume a decline that isn't really there.",
        "",
        "## Age curve: does real production actually decline the way the heuristic assumes?",
        "",
        "Mean PPR points/game by exact age (players with >= "
        f"{MIN_GAMES_FOR_AGE_CURVE} games that season, 2012-2025). Compare each position's "
        "empirical peak/decline against its assumed params below.",
        "",
    ]
    for position, params in AGE_CURVE_PARAMS.items():
        lines.append(
            f"**{position}** -- assumed: flat through age {params['decline_start']}, "
            f"declining to 0.5x by age {params['cliff']}."
        )
        pos_points = [p for p in age_points if p.position == position]
        if pos_points:
            peak = max(pos_points, key=lambda p: p.mean_ppr_points_per_game)
            lines.append(
                f"Real peak age observed: {peak.age} ({peak.mean_ppr_points_per_game:.1f} ppg, n={peak.n})."
            )
        lines.append("")
        lines.append("| Age | n | Mean PPR pts/game |")
        lines.append("|---|---|---|")
        for p in pos_points:
            lines.append(f"| {p.age} | {p.n} | {p.mean_ppr_points_per_game:.1f} |")
        lines.append("")

    lines += [
        "## Reading this honestly",
        "",
        "Real survivorship bias applies to the age table above: a player who declined sharply "
        "in their late 20s / early 30s typically leaves the league (and this dataset) rather "
        "than posting a bad season in it, so older-age rows are a durable, selected subset, "
        "not what an *individual* player's real decline curve looks like. This module reports "
        "the real aggregate numbers and names that confound; it does not resolve it.",
        "",
    ]
    path.write_text("\n".join(lines))
    return {
        "pick_outcomes": [o.__dict__ for o in pick_outcomes],
        "age_points": [p.__dict__ for p in age_points],
    }
