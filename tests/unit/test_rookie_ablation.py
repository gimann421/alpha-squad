"""Unit tests for the rookie college-production ablation's pairing and verdict logic
(models/rookie/ablation.py, docs/DECISIONS.md D39).

The pairing test is the important one: a mis-paired ablation does not crash and does not fail
any assertion -- it silently reports a wrong answer, which is the worst possible failure mode
for something whose entire job is deciding whether to keep a feature."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_squad.models.rookie.ablation import compare_arms, verdict


@dataclass
class FakeEval:
    model_name: str
    season: int
    position: str
    n: int
    mae: float
    spearman: float


@dataclass
class FakeClf:
    model_name: str
    cohort: int
    position: str
    n: int
    brier_score: float
    accuracy: float


@dataclass
class FakeReport:
    regression_metrics: list
    classification_metrics: list


def _arm(suffix: str, mae_by_pos: dict[str, float], brier: float = 0.10):
    """One arm's metrics for a single class. Mirrors the real shape: every regression model is
    reported at position='ALL' (the cross-position rollup), with the position living only in
    the model name."""
    return FakeReport(
        regression_metrics=[
            FakeEval(f"ml_rookie_regression_{pos}{suffix}", 2023, "ALL", 20, mae, 0.5)
            for pos, mae in mae_by_pos.items()
        ],
        classification_metrics=[
            FakeClf(f"ml_rookie_breakout_{pos}{suffix}", 2023, pos.upper(), 20, brier, 0.9)
            for pos in mae_by_pos
        ],
    )


class TestPairing:
    def test_regression_folds_pair_by_position_model_not_just_class(self):
        """Regression (D39): all four regression models report position='ALL', so keying on
        (class, position) alone collapses them to one key and pairs the candidate's QB against the baseline's TE.
        That produced a fabricated +13.69 MAE delta in this ablation's first real run."""
        baseline = _arm("", {"qb": 100.0, "rb": 10.0, "wr": 10.0, "te": 10.0})
        candidate = _arm("_college", {"qb": 100.0, "rb": 10.0, "wr": 10.0, "te": 10.0})

        comparisons, n_reg, _ = compare_arms(baseline, candidate)

        assert n_reg == 4, "every position model must pair, not collapse onto one key"
        mae = next(c for c in comparisons if c.label == "regression MAE")
        # Identical arms must produce exactly zero delta. Under the collapsing key this came
        # out non-zero because QB(100) was compared against TE(10).
        assert mae.delta == 0.0
        assert mae.winner == "tie"

    def test_a_real_improvement_is_detected(self):
        baseline = _arm("", {"qb": 20.0, "rb": 20.0, "wr": 20.0, "te": 20.0}, brier=0.20)
        candidate = _arm("_college", {"qb": 10.0, "rb": 10.0, "wr": 10.0, "te": 10.0}, brier=0.10)

        comparisons, _, _ = compare_arms(baseline, candidate)

        mae = next(c for c in comparisons if c.label == "regression MAE")
        brier = next(c for c in comparisons if c.label == "breakout Brier")
        assert mae.winner == "+college" and mae.delta == -10.0
        assert brier.winner == "+college"

    def test_unpaired_folds_are_excluded_rather_than_compared_against_nothing(self):
        baseline = _arm("", {"qb": 20.0, "rb": 20.0})
        candidate = _arm("_college", {"qb": 10.0, "rb": 10.0, "wr": 10.0, "te": 10.0})

        _, n_reg, n_clf = compare_arms(baseline, candidate)

        assert n_reg == 2
        assert n_clf == 2


class TestVerdict:
    def _comparisons(self, college_wins_brier: bool, college_wins_spearman: bool):
        baseline = _arm("", {"qb": 20.0, "rb": 20.0}, brier=0.20 if college_wins_brier else 0.10)
        candidate = _arm(
            "_college", {"qb": 20.0, "rb": 20.0}, brier=0.10 if college_wins_brier else 0.20
        )
        for m in candidate.regression_metrics:
            m.spearman = 0.6 if college_wins_spearman else 0.4
        for m in baseline.regression_metrics:
            m.spearman = 0.5
        return compare_arms(baseline, candidate)[0]

    def test_adopts_when_both_primaries_improve(self):
        assert verdict(self._comparisons(True, True)).startswith("ADOPT +college")

    def test_adopts_on_classifier_alone_and_discloses_the_tradeoff(self):
        result = verdict(self._comparisons(True, False))
        assert result.startswith("ADOPT +college")
        assert "disclosed" in result

    def test_keeps_baseline_when_the_classifier_does_not_improve(self):
        assert verdict(self._comparisons(False, True)).startswith("KEEP BASELINE")

    def test_keeps_baseline_when_neither_improves(self):
        assert verdict(self._comparisons(False, False)).startswith("KEEP BASELINE")
