"""Unit tests for the two pieces of W4 logic that live in the runner rather than in
`src/alpha_squad/evaluation/weekly/` (`scripts/research/w4_flex_forensics.py`).

Both are small, both decide something reportable, and both are easy to get quietly wrong:

  * `flex_vs_positional` --- the difference of differences that answers the brief's "is the FLEX
    problem even real?". Its sign convention is the whole finding, so it is pinned against a
    hand-computed case rather than trusted.
  * the runner's **depth-5 wiring** --- `metrics.as_row()` used to key off the module-level
    `DEPTHS`, so W4's extra depth was computed and then thrown away. A test now holds the
    contract that a cell emits exactly the depths it was asked for.

Loaded the same way `test_d104_ecr_floor.py` loads its script.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from alpha_squad.evaluation.weekly.metrics import evaluate_cell


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "w4_flex_forensics.py"
    spec = importlib.util.spec_from_file_location("w4_flex_forensics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


class TestFlexVsPositional:
    """The sign convention: POSITIVE means the FLEX board carries a *smaller* deficit against
    ECR than the positional boards already do, i.e. the combination step is not adding one.

    Three weeks, because `noise.describe` refuses to summarise fewer (a CI over two weeks is
    not a CI). The weeks are identical so the expected mean is exact."""

    WEEKS = ("2024-1", "2024-2", "2024-3")

    def _cells(self, flex_alpha, flex_ecr, pos_alpha, pos_ecr):
        flex = {
            "CF_A": {w: {"spearman": flex_alpha, "n": 50} for w in self.WEEKS},
            "ECR": {w: {"spearman": flex_ecr, "n": 50} for w in self.WEEKS},
        }
        pos = {}
        for position in ("RB", "WR", "TE"):
            pos[f"{position}|ALPHA"] = {w: {"spearman": pos_alpha, "n": 50} for w in self.WEEKS}
            pos[f"{position}|ECR"] = {w: {"spearman": pos_ecr, "n": 50} for w in self.WEEKS}
        return flex, pos

    def test_equal_deficits_give_zero(self):
        out = MODULE.flex_vs_positional(*self._cells(0.60, 0.65, 0.60, 0.65))
        assert out["spearman"]["mean"] == pytest.approx(0.0)
        assert out["spearman"]["n_weeks"] == 3

    def test_worse_flex_is_negative(self):
        # FLEX is 0.10 behind ECR; each position only 0.02 behind. The combination step is
        # adding 0.08 of deficit of its own.
        out = MODULE.flex_vs_positional(*self._cells(0.55, 0.65, 0.63, 0.65))
        assert out["spearman"]["mean"] == pytest.approx(-0.08)

    def test_better_flex_is_positive(self):
        out = MODULE.flex_vs_positional(*self._cells(0.64, 0.65, 0.55, 0.65))
        assert out["spearman"]["mean"] == pytest.approx(0.09)

    def test_a_week_missing_any_position_is_dropped_not_partially_averaged(self):
        """A week where one positional board was invalid must not be averaged over the other
        two -- that would compare a 3-position FLEX deficit against a 2-position baseline."""
        flex, pos = self._cells(0.55, 0.65, 0.63, 0.65)
        pos["TE|ALPHA"]["2024-1"] = {"invalid": True}
        assert MODULE.flex_vs_positional(flex, pos) == {}

    def test_invalid_flex_week_is_dropped(self):
        flex, pos = self._cells(0.55, 0.65, 0.63, 0.65)
        flex["CF_A"]["2024-1"] = {"invalid": True}
        assert MODULE.flex_vs_positional(flex, pos) == {}


class TestDepthWiring:
    """Regression: depth 5 must survive `as_row()`. It did not before W4."""

    def test_requested_depths_are_all_emitted(self):
        pred = [float(i) for i in range(1, 21)]
        real = [float(20 - i) for i in range(20)]
        row = evaluate_cell(pred, real, depths=MODULE.W4_DEPTHS).as_row()
        for k in MODULE.W4_DEPTHS:
            assert f"precision@{k}" in row, f"depth {k} dropped by as_row()"
            assert f"capture@{k}" in row, f"depth {k} dropped by as_row()"

    def test_no_unrequested_depth_is_invented(self):
        pred = [float(i) for i in range(1, 21)]
        real = [float(20 - i) for i in range(20)]
        row = evaluate_cell(pred, real, depths=(5, 10)).as_row()
        assert "precision@25" not in row
        assert "capture@25" not in row

    def test_headline_covers_every_w4_depth(self):
        for k in MODULE.W4_DEPTHS:
            assert f"capture@{k}" in MODULE.HEADLINE
            assert f"precision@{k}" in MODULE.HEADLINE


def _load_w5():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "w5_topboard_forensics.py"
    spec = importlib.util.spec_from_file_location("w5_topboard_forensics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W5 = _load_w5()


class TestAggregationIsOrderInvariant:
    """W5's aggregation must not depend on the order its input rows arrive in.

    This is the defect gate G10 caught: `aggregate_cohorts` intersected two dicts' keys with a
    bare `dict.keys() & dict.keys()`, whose iteration order for string keys depends on
    `PYTHONHASHSEED` and so varies between processes. `noise._bootstrap_mean_ci` indexes its
    input **by position**, so the resulting confidence interval differed on every run -- and the
    cohort lift CIs are exactly the numbers the report's significance marks are read from.

    A full determinism gate catches this, but only after two complete runs. This catches it in
    milliseconds, which is the difference between finding it and shipping it."""

    def _rows(self):
        rows = []
        for season in (2023, 2024):
            for week in range(1, 12):
                for cohort, pop, miss in (("A", 0.2, 0.35), ("B", 0.5, 0.40)):
                    rows.append(
                        {
                            "season": season,
                            "week": week,
                            "position": "RB",
                            "depth": 10,
                            "cohort": cohort,
                            "n": 10.0,
                            "population_share": pop + 0.01 * week,
                            "missed_share": miss - 0.005 * week,
                            "false_positives": 1.0,
                            "false_negatives": 0.0,
                        }
                    )
        return rows

    def test_shuffling_the_input_rows_changes_nothing(self):
        import random

        rows = self._rows()
        base = W5.aggregate_cohorts(rows)
        for seed in (1, 7, 99):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            assert W5.aggregate_cohorts(shuffled) == base, f"aggregation moved under seed {seed}"

    def test_the_lift_interval_is_actually_populated(self):
        """Guards the test above from passing vacuously if `lift` ever stopped being computed."""
        out = W5.aggregate_cohorts(self._rows())
        cell = out["RB|10|A"]
        assert cell["lift"]["n_weeks"] == 22
        assert cell["lift"]["ci_low"] <= cell["lift"]["mean"] <= cell["lift"]["ci_high"]
