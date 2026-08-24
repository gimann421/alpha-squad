"""Ablation of the D38 college-production features against the baseline (D20) rookie feature
set, over identical walk-forward folds.

Why this exists rather than "train with the new features and look at the numbers": `evaluation_results` and
`classification_results` are keyed on (model_name, season|cohort, position), so training a
second feature set under the same model names silently overwrites the first arm and leaves
nothing to compare against. Both arms therefore run under distinct model names/feature
versions (see `train.py::run_rookie_models`'s `model_suffix`/`feature_version`), and this
module pairs them fold-by-fold.

The comparison is only meaningful where both arms scored the same players, so `compare_arms`
pairs strictly on (class, position) and reports the paired count; and it is only *interesting*
where the college features are actually populated, so the report carries per-class coverage —
`models/rookie/data.py` imputes missing college usage to 0.0, which is indistinguishable
downstream from a real zero-usage player, and a class with no coverage is a guaranteed tie."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class MetricComparison:
    label: str
    baseline: float
    candidate: float
    higher_is_better: bool

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline

    @property
    def winner(self) -> str:
        if self.delta == 0 or self.delta != self.delta:  # tie or NaN
            return "tie"
        improved = self.delta > 0 if self.higher_is_better else self.delta < 0
        return "+college" if improved else "baseline"


def _mean(values: list[float]) -> float:
    real = [v for v in values if v == v]  # drop NaN
    return sum(real) / len(real) if real else float("nan")


def _fold_key(m, suffix: str = "") -> tuple:
    """Identifies one walk-forward fold across both arms.

    `model_name` is load-bearing here, not decorative: `run_rookie_models` trains one model
    per position but `evaluate_and_record` reports each one's headline row as
    position='ALL' (the cross-position rollup). Keying on (class, position) alone therefore
    collapses all four position models of a class onto one key and pairs, say, v2's QB model
    against v1's TE model. That produced a fake +13.69 MAE regression in the first run of this
    ablation -- caught because the number was implausible next to a ~0.004 Spearman delta, not
    because anything failed."""
    name = m.model_name
    if suffix and name.endswith(suffix):
        name = name[: -len(suffix)]
    # EvaluationMetrics uses `season`; ClassificationMetrics uses `cohort`.
    return (getattr(m, "season", None) or getattr(m, "cohort", None), m.position, name)


def compare_arms(
    baseline_report, candidate_report, *, candidate_suffix: str = "_college"
) -> tuple[list[MetricComparison], int, int]:
    """Returns (comparisons, n_paired_regression_folds, n_paired_classification_folds)."""
    base_reg = {_fold_key(m): m for m in baseline_report.regression_metrics}
    base_clf = {_fold_key(m): m for m in baseline_report.classification_metrics}

    paired_reg = [
        (m, base_reg[_fold_key(m, candidate_suffix)])
        for m in candidate_report.regression_metrics
        if _fold_key(m, candidate_suffix) in base_reg
    ]
    paired_clf = [
        (m, base_clf[_fold_key(m, candidate_suffix)])
        for m in candidate_report.classification_metrics
        if _fold_key(m, candidate_suffix) in base_clf and m.n > 0
    ]

    comparisons = [
        MetricComparison(
            "regression MAE",
            _mean([b.mae for _, b in paired_reg]),
            _mean([a.mae for a, _ in paired_reg]),
            higher_is_better=False,
        ),
        MetricComparison(
            "regression Spearman",
            _mean([b.spearman for _, b in paired_reg]),
            _mean([a.spearman for a, _ in paired_reg]),
            higher_is_better=True,
        ),
        MetricComparison(
            "breakout Brier",
            _mean([b.brier_score for _, b in paired_clf]),
            _mean([a.brier_score for a, _ in paired_clf]),
            higher_is_better=False,
        ),
        MetricComparison(
            "breakout accuracy",
            _mean([b.accuracy for _, b in paired_clf]),
            _mean([a.accuracy for a, _ in paired_clf]),
            higher_is_better=True,
        ),
    ]
    return comparisons, len(paired_reg), len(paired_clf)


def college_usage_coverage(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Per draft class: how many rookie_features rows actually carry a college-usage value.
    A class at 0% cannot produce any baseline/+college difference — the features are all-zero there."""
    return con.execute(
        """
        SELECT draft_class,
               count(*) AS rookies,
               count(college_usage_overall) AS with_college,
               round(100.0 * count(college_usage_overall) / count(*), 1) AS pct
        FROM rookie_features
        GROUP BY draft_class
        ORDER BY draft_class
        """
    ).fetchall()


ADOPT = "+college"


def verdict(comparisons: list[MetricComparison]) -> str:
    """Pre-registered decision rule (docs/DECISIONS.md D39), fixed before any results were
    seen: the breakout classifier is the decision-relevant output, so Brier governs; regression
    Spearman is secondary. Adopt the college features only if the classifier improves."""
    by_label = {c.label: c for c in comparisons}
    brier = by_label["breakout Brier"].winner
    spearman = by_label["regression Spearman"].winner
    if brier == ADOPT and spearman == ADOPT:
        return "ADOPT +college — it improves both the classifier and the regression."
    if brier == ADOPT:
        return (
            "ADOPT +college — it improves the decision-relevant classifier (Brier); regression "
            "is neutral-to-worse and that tradeoff is disclosed."
        )
    if spearman == ADOPT:
        return (
            "KEEP BASELINE — the classifier (the decision-relevant output) does not improve. "
            "The regression gain alone does not meet the pre-registered bar."
        )
    return "KEEP BASELINE — college production improves neither primary metric."


def write_ablation_report(
    con: duckdb.DuckDBPyConnection,
    baseline_report,
    candidate_report,
    path: Path,
    *,
    class_start: int,
    class_end: int,
    min_train_class: int | None = None,
) -> str:
    comparisons, n_reg, n_clf = compare_arms(baseline_report, candidate_report)
    result = verdict(comparisons)

    scope = f"Walk-forward by draft class, {class_start}–{class_end}"
    if min_train_class is not None:
        scope += f" (training classes from {min_train_class})"

    lines = [
        "# Rookie model: does CFBD college production actually help?",
        "",
        f"{scope}. Both arms trained on identical folds, identical CatBoost hyperparameters "
        "and seed; the only difference is the three `college_usage_*` features added in D38.",
        "",
        "- **baseline** = draft capital + combine + landing spot (D20) — 12 features",
        "- **+college** = baseline + `college_usage_overall/pass/rush` (CFBD, espn_id-bridged, "
        "D38) — 15 features",
        "",
        "## Result",
        "",
        "| metric | baseline | +college | delta | better |",
        "|---|---|---|---|---|",
    ]
    for c in comparisons:
        arrow = "lower better" if not c.higher_is_better else "higher better"
        lines.append(
            f"| {c.label} ({arrow}) | {c.baseline:.4f} | {c.candidate:.4f} | "
            f"{c.delta:+.4f} | **{c.winner}** |"
        )
    lines += [
        "",
        f"Paired folds: {n_reg} regression, {n_clf} classification.",
        "",
        f"**Verdict:** {result}",
        "",
        "## College-usage coverage by draft class",
        "",
        "Coverage matters for reading the result above: `models/rookie/data.py` imputes a missing "
        "college-usage value to 0.0, which is indistinguishable from a genuine zero-usage player. "
        "A draft class at 0% coverage contributes a guaranteed tie and dilutes the measured effect. "
        "CFBD's `player/usage` endpoint returns nothing before 2013 (verified), so the earliest "
        "draft class that can carry this signal at all is 2014.",
        "",
        "| draft class | rookies | with college usage | % |",
        "|---|---|---|---|",
    ]
    for draft_class, rookies, with_college, pct in college_usage_coverage(con):
        lines.append(f"| {draft_class} | {rookies} | {with_college} | {pct}% |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return result
