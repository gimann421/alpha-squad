"""Rookie evaluation vs. baselines (docs/DECISIONS.md D54): PRODUCT_SPEC.md requires every
model be compared against baselines, and M7's rookie models (`ml_rookie_regression_*`,
`ml_rookie_breakout_*`, already walk-forward evaluated in `evaluation_results`/
`classification_results`) have so far only ever been compared against each other (the D38/D39
college-production ablation) -- never against a real *external* baseline. This module adds two:

- `draft_capital_baseline`: real draft pick number -> rookie-season points, an isotonic curve
  fit walk-forward (strictly prior draft classes only, exactly `market_implied.py`'s pattern
  with pick number standing in for ECR rank) -- "a scout with nothing but the draft card."
- `rookie_market_ecr_baseline`: the same walk-forward isotonic-curve pattern, but using each
  rookie's real dynasty ECR rank ('do') from their own rookie-season summer -- the closest real
  market consensus signal for rookies this environment has (no separate "rookie-specific ECR"
  product was ingested; this is that same real dynasty market applied to just the rookie
  subset, not a fabricated rookie-only series).

Both write through the exact same shared harness (`models/evaluate.py::evaluate_and_record`)
Alpha's own rookie models already use, so every number lands in the same `evaluation_results`
table and is directly comparable -- no separate scoring path for "baselines" vs. "Alpha".
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from sklearn.isotonic import IsotonicRegression

from alpha_squad.evaluation.config import EVALUATION_FRAMEWORK_VERSION
from alpha_squad.models.evaluate import SKILL_POSITIONS, evaluate_and_record
from alpha_squad.models.rookie.features import FEATURE_VERSION

DRAFT_CAPITAL_BASELINE = "baseline_rookie_draft_capital"
MARKET_ECR_BASELINE = "baseline_rookie_market_ecr"
EARLY_ROUNDS = (1, 2)
MID_ROUNDS = (3, 4)
LATE_ROUNDS = (5, 6, 7)


def _rookie_classes(
    con: duckdb.DuckDBPyConnection, position: str, before_class: int
) -> list[tuple]:
    return con.execute(
        """
        SELECT p.draft_pick, s.total_fantasy_points_ppr
        FROM players p
        JOIN player_season_stats s ON s.player_id = p.player_id AND s.season = p.rookie_season
        WHERE p.position = ? AND p.draft_year < ? AND p.draft_pick IS NOT NULL
        """,
        [position, before_class],
    ).fetchall()


def draft_capital_baseline(con: duckdb.DuckDBPyConnection, draft_class: int) -> dict[str, float]:
    predictions: dict[str, float] = {}
    for position in SKILL_POSITIONS:
        training = _rookie_classes(con, position, draft_class)
        if len(training) < 15:
            continue
        picks_train = [t[0] for t in training]
        points_train = [t[1] for t in training]
        curve = IsotonicRegression(increasing=False, out_of_bounds="clip")
        curve.fit(picks_train, points_train)

        rookies = con.execute(
            "SELECT player_id, draft_pick FROM players "
            "WHERE position = ? AND draft_year = ? AND draft_pick IS NOT NULL",
            [position, draft_class],
        ).fetchall()
        for player_id, pick in rookies:
            predictions[player_id] = float(curve.predict([pick])[0])
    return predictions


def _rookie_market_ecr_classes(
    con: duckdb.DuckDBPyConnection, position: str, before_class: int, ecr_type: str
) -> list[tuple]:
    return con.execute(
        """
        WITH rookie_ecr AS (
            SELECT m.player_id, m.ecr_rank,
                   row_number() OVER (PARTITION BY m.player_id ORDER BY m.scrape_date DESC) AS rn
            FROM market_snapshot m
            JOIN players p ON p.player_id = m.player_id
            WHERE m.ecr_type = ? AND p.position = ? AND p.draft_year < ?
              AND year(m.scrape_date) = p.rookie_season AND month(m.scrape_date) IN (7, 8)
        )
        SELECT e.ecr_rank, s.total_fantasy_points_ppr
        FROM rookie_ecr e
        JOIN players p ON p.player_id = e.player_id
        JOIN player_season_stats s ON s.player_id = e.player_id AND s.season = p.rookie_season
        WHERE e.rn = 1
        """,
        [ecr_type, position, before_class],
    ).fetchall()


def rookie_market_ecr_baseline(
    con: duckdb.DuckDBPyConnection, draft_class: int, ecr_type: str = "do"
) -> dict[str, float]:
    predictions: dict[str, float] = {}
    for position in SKILL_POSITIONS:
        training = _rookie_market_ecr_classes(con, position, draft_class, ecr_type)
        if len(training) < 15:
            continue
        ranks_train = [t[0] for t in training]
        points_train = [t[1] for t in training]
        curve = IsotonicRegression(increasing=False, out_of_bounds="clip")
        curve.fit(ranks_train, points_train)

        rows = con.execute(
            """
            SELECT m.player_id, m.ecr_rank FROM (
                SELECT m.player_id, m.ecr_rank,
                       row_number() OVER (PARTITION BY m.player_id ORDER BY m.scrape_date DESC) AS rn
                FROM market_snapshot m
                JOIN players p ON p.player_id = m.player_id
                WHERE m.ecr_type = ? AND p.position = ? AND p.draft_year = ?
                  AND year(m.scrape_date) = p.rookie_season AND month(m.scrape_date) IN (7, 8)
            ) m WHERE rn = 1
            """,
            [ecr_type, position, draft_class],
        ).fetchall()
        for player_id, rank in rows:
            predictions[player_id] = float(curve.predict([rank])[0])
    return predictions


def run_rookie_baselines(con: duckdb.DuckDBPyConnection, draft_classes: list[int]) -> None:
    """Walk-forward, exactly like `models/baselines/run.py::run_baselines` -- each class
    predicted only from strictly-prior classes' real outcomes."""
    for draft_class in draft_classes:
        dc_pred = draft_capital_baseline(con, draft_class)
        if dc_pred:
            evaluate_and_record(con, DRAFT_CAPITAL_BASELINE, draft_class, dc_pred)
        ecr_pred = rookie_market_ecr_baseline(con, draft_class)
        if ecr_pred:
            evaluate_and_record(con, MARKET_ECR_BASELINE, draft_class, ecr_pred)


def _round_tier(round_no: int | None) -> str | None:
    if round_no in EARLY_ROUNDS:
        return "early (rounds 1-2)"
    if round_no in MID_ROUNDS:
        return "mid (rounds 3-4)"
    if round_no in LATE_ROUNDS:
        return "late (rounds 5-7)"
    return None


def _round_and_outcome(
    con: duckdb.DuckDBPyConnection, player_ids: list[str]
) -> dict[str, tuple[int | None, float]]:
    """{player_id: (draft_round, real_rookie_season_points)} -- real outcome only, used to
    join whichever predictions dict a caller already has against real draft round + result."""
    if not player_ids:
        return {}
    rows = con.execute(
        """
        SELECT p.player_id, p.draft_round, s.total_fantasy_points_ppr
        FROM players p
        JOIN player_season_stats s ON s.player_id = p.player_id AND s.season = p.rookie_season
        WHERE p.player_id = ANY(?)
        """,
        [player_ids],
    ).fetchall()
    return {player_id: (draft_round, points) for player_id, draft_round, points in rows}


def _tier_mae(
    predicted: dict[str, float], outcomes: dict[str, tuple[int | None, float]]
) -> dict[str, list[float]]:
    by_tier: dict[str, list[float]] = {}
    for player_id, pred in predicted.items():
        if player_id not in outcomes:
            continue
        draft_round, actual = outcomes[player_id]
        tier = _round_tier(draft_round)
        if tier is None:
            continue
        by_tier.setdefault(tier, []).append(abs(pred - actual))
    return by_tier


def build_round_tier_breakdown(
    con: duckdb.DuckDBPyConnection, draft_class_start: int, draft_class_end: int
) -> list[dict]:
    """For each real draft class in range, recomputes both new baselines fresh (the exact same
    walk-forward calls `run_rookie_baselines` uses -- their per-player predictions are not
    separately persisted anywhere, so this is the correct way to re-slice them, not a shortcut)
    and reads Alpha's real production rookie model's persisted predictions
    (`rookie_predictions` keyed by the real production `FEATURE_VERSION`), then buckets every
    model's absolute error by real draft-round tier."""
    totals: dict[str, dict[str, list[float]]] = {}

    for draft_class in range(draft_class_start, draft_class_end + 1):
        dc_pred = draft_capital_baseline(con, draft_class)
        ecr_pred = rookie_market_ecr_baseline(con, draft_class)
        alpha_rows = con.execute(
            "SELECT player_id, predicted_rookie_points FROM rookie_predictions "
            "WHERE model_version = ? AND draft_class = ? AND predicted_rookie_points IS NOT NULL",
            [FEATURE_VERSION, draft_class],
        ).fetchall()
        alpha_pred = dict(alpha_rows)

        all_ids = set(dc_pred) | set(ecr_pred) | set(alpha_pred)
        outcomes = _round_and_outcome(con, list(all_ids))

        for model_name, predicted in (
            (DRAFT_CAPITAL_BASELINE, dc_pred),
            (MARKET_ECR_BASELINE, ecr_pred),
            ("ml_rookie_regression (production)", alpha_pred),
        ):
            by_tier = _tier_mae(predicted, outcomes)
            model_totals = totals.setdefault(model_name, {})
            for tier, errors in by_tier.items():
                model_totals.setdefault(tier, []).extend(errors)

    breakdown = []
    for model_name, by_tier in totals.items():
        for tier, errors in by_tier.items():
            if not errors:
                continue
            breakdown.append(
                {
                    "model": model_name,
                    "tier": tier,
                    "n": len(errors),
                    "mae": sum(errors) / len(errors),
                }
            )
    return breakdown


def write_rookie_benchmark_report(
    con: duckdb.DuckDBPyConnection, path: Path, draft_class_start: int, draft_class_end: int
) -> list[dict]:
    breakdown = build_round_tier_breakdown(con, draft_class_start, draft_class_end)

    lines = [
        "# Rookie evaluation vs. baselines, by real draft-round tier",
        "",
        f"Framework version: `{EVALUATION_FRAMEWORK_VERSION}`. Draft classes {draft_class_start}-"
        f"{draft_class_end}. `{DRAFT_CAPITAL_BASELINE}`/`{MARKET_ECR_BASELINE}` are new walk-forward "
        "baselines added this phase (see module docstring); Alpha's rookie regression is the real "
        "production model (`rookie_predictions`, keyed by the live `FEATURE_VERSION`), already "
        "walk-forward evaluated by M7 -- pooled across QB/RB/WR/TE here, not the "
        "pre-aggregated `evaluation_results` row, which has no round-tier dimension.",
        "",
        "| Tier | Model | n | MAE |",
        "|---|---|---|---|",
    ]
    for row in sorted(breakdown, key=lambda r: (r["tier"], r["mae"])):
        lines.append(f"| {row['tier']} | {row['model']} | {row['n']} | {row['mae']:.1f} |")

    lines += [
        "",
        "## Sample size warning",
        "",
        "Rookie classes are small by construction -- a real NFL draft class has roughly "
        "10-25 skill-position players who see meaningful rookie-season usage, and a round "
        "tier within one position within one class can be single digits. Do not treat any "
        "single tier's MAE as a confident claim; look for a difference that holds up across "
        "the pooled multi-class n above.",
        "",
    ]
    path.write_text("\n".join(lines))
    return breakdown
