"""Unit tests for the D78 training-specification experiment.

These cover the parts that must be right *before* the experiment is run against real data:
the arm definitions, the ECR-coverage eligibility rule, the leakage guard, the fallbacks, and
every gate's logic. Nothing here touches the real database.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.projection_specification import (
    ECR_COVERAGE_FLOOR,
    ECR_MISSING_SENTINEL,
    MIN_TRAIN_ROWS,
    MIN_TRAIN_SEASONS,
    PREREGISTERED_CONTROL,
    PREREGISTERED_TARGET_SEASONS,
    Y_ARMS,
    ArmMeasurement,
    _assert_no_leakage,
    ecr_coverage_by_season,
    eligible_ecr_seasons,
    evaluate_gates,
    render_specification_report,
    select_training_rows,
)


def _rows(target_season: int, n: int, *, ecr_real: bool) -> pd.DataFrame:
    rng = np.random.default_rng(target_season)
    return pd.DataFrame(
        {
            "player_id": [f"p{target_season}_{i}" for i in range(n)],
            "target_season": target_season,
            "prior_ppg": rng.uniform(2, 20, n),
            "prior_games": rng.integers(4, 18, n),
            "prior_weighted_total": rng.uniform(20, 300, n),
            "preseason_ecr_rank": (
                rng.uniform(1, 200, n) if ecr_real else np.full(n, ECR_MISSING_SENTINEL)
            ),
            "target_points": rng.uniform(10, 320, n),
        }
    )


def _panel() -> pd.DataFrame:
    """Mirrors the real shape: no preseason board before 2020, a real one from 2020 on."""
    frames = [_rows(s, 40, ecr_real=False) for s in range(2016, 2020)]
    frames += [_rows(s, 40, ecr_real=True) for s in range(2020, 2025)]
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------- eligibility rule


def test_ecr_coverage_separates_board_and_no_board_seasons():
    coverage = ecr_coverage_by_season(_panel())
    assert all(coverage[s] == 0.0 for s in range(2016, 2020))
    assert all(coverage[s] == 1.0 for s in range(2020, 2025))


def test_eligible_seasons_are_the_board_seasons():
    assert eligible_ecr_seasons(_panel()) == [2020, 2021, 2022, 2023, 2024]


@pytest.mark.parametrize("floor", [0.05, 0.2, 0.4, ECR_COVERAGE_FLOOR, 0.6, 0.7])
def test_eligibility_is_invariant_to_the_floor_across_a_wide_range(floor):
    """The floor is not a tuned parameter: real per-season coverage is 0.00 or 0.71-0.95, so
    every threshold in that gap gives the same partition. This asserts the invariance instead
    of trusting the docstring."""
    panel = pd.concat(
        [
            *[_rows(s, 40, ecr_real=False) for s in range(2016, 2020)],
            # a realistically PARTIAL board: 71% coverage, the real 2020 WR figure
            _rows(2020, 100, ecr_real=True).assign(
                preseason_ecr_rank=lambda d: np.where(
                    np.arange(len(d)) < 71, d.preseason_ecr_rank, ECR_MISSING_SENTINEL
                )
            ),
        ],
        ignore_index=True,
    )
    assert eligible_ecr_seasons(panel, floor) == [2020]


# ------------------------------------------------------------------------ arm definitions


def test_control_stops_at_s_minus_2_and_keeps_every_season():
    train = select_training_rows("Y0", _panel(), 2025)
    assert train.target_season.max() == 2023
    assert set(train.target_season) == set(range(2016, 2024))


def test_y1_adds_the_most_recent_completed_season():
    control = select_training_rows("Y0", _panel(), 2025)
    y1 = select_training_rows("Y1", _panel(), 2025)
    assert y1.target_season.max() == 2024
    assert set(y1.target_season) - set(control.target_season) == {2024}


def test_y2_drops_the_board_less_seasons_only():
    y2 = select_training_rows("Y2", _panel(), 2025)
    assert set(y2.target_season) == {2020, 2021, 2022, 2023}


def test_y3_is_the_union_of_both_changes():
    y3 = select_training_rows("Y3", _panel(), 2025)
    assert set(y3.target_season) == {2020, 2021, 2022, 2023, 2024}


def test_unknown_arm_raises():
    with pytest.raises(ValueError, match="unknown arm"):
        select_training_rows("Y9", _panel(), 2025)


# ------------------------------------------------------------------------------- fallbacks


def test_y2_falls_back_to_control_when_too_few_board_seasons():
    """Target 2022 draws training rows from target seasons <= 2020, which is one board season
    -- below MIN_TRAIN_SEASONS -- so the arm must not starve the model."""
    y2 = select_training_rows("Y2", _panel(), 2022)
    control = select_training_rows("Y0", _panel(), 2022)
    assert set(y2.target_season) == set(control.target_season)
    assert len({2020}) < MIN_TRAIN_SEASONS


def test_y2_falls_back_when_the_filter_would_leave_too_few_rows():
    panel = pd.concat(
        [
            *[_rows(s, 60, ecr_real=False) for s in range(2016, 2022)],
            _rows(2022, 5, ecr_real=True),
            _rows(2023, 5, ecr_real=True),
        ],
        ignore_index=True,
    )
    train = select_training_rows("Y2", panel, 2025)
    assert len(train) >= MIN_TRAIN_ROWS
    assert set(train.target_season) == set(range(2016, 2024))


# ---------------------------------------------------------------------------- leakage guard


def test_leakage_guard_raises_on_a_target_season_training_row():
    with pytest.raises(ValueError, match="leakage"):
        _assert_no_leakage(_rows(2025, 10, ecr_real=True), 2025)


def test_leakage_guard_raises_on_a_future_training_row():
    with pytest.raises(ValueError, match="leakage"):
        _assert_no_leakage(_rows(2026, 10, ecr_real=True), 2025)


def test_no_arm_ever_selects_a_row_at_or_after_the_target_season():
    panel = _panel()
    for arm in Y_ARMS:
        for season in PREREGISTERED_TARGET_SEASONS:
            train = select_training_rows(arm, panel, season)
            assert train.empty or train.target_season.max() < season


# ------------------------------------------------------------------------------------ gates


def _frame(overrides: dict | None = None) -> pd.DataFrame:
    """Control + one arm over 4 seasons x 4 positions, arm uniformly better unless overridden."""
    overrides = overrides or {}
    rows = []
    for season in PREREGISTERED_TARGET_SEASONS:
        for pos in ("QB", "RB", "WR", "TE"):
            for arm, delta in (("Y0", 0.0), ("Y1", -2.0)):
                d = overrides.get((arm, season, pos), {})
                rows.append(
                    ArmMeasurement(
                        arm=arm,
                        season=season,
                        position=pos,
                        n=100,
                        n_train=400,
                        n_train_seasons=5,
                        mae=d.get("mae", 40.0 + delta),
                        rmse=d.get("rmse", 60.0 + delta),
                        spearman=d.get("spearman", 0.75 - delta / 100.0),
                        bias=0.0,
                        top_decile_bias=d.get("top_decile_bias", 20.0 + delta),
                        max_projection=250.0,
                        fell_back=False,
                    ).__dict__
                )
    return pd.DataFrame(rows)


def test_all_gates_pass_for_a_uniformly_better_arm():
    verdict = evaluate_gates(_frame(), "Y1")
    assert verdict.passed, [(g.name, g.detail) for g in verdict.gates if not g.passed]


def test_g3_rejects_an_arm_that_buys_one_position_with_another():
    """The gate that makes a disguised positional bonus impossible: RB improves a lot, WR
    degrades, pooled MAE still improves -- and the arm must still be rejected."""
    over = {("Y1", s, "RB"): {"mae": 20.0} for s in PREREGISTERED_TARGET_SEASONS}
    over |= {("Y1", s, "WR"): {"mae": 41.0} for s in PREREGISTERED_TARGET_SEASONS}
    verdict = evaluate_gates(_frame(over), "Y1")
    g3 = next(g for g in verdict.gates if g.name.startswith("G3"))
    assert not g3.passed
    assert "WR" in g3.detail
    assert not verdict.passed


def test_g2_rejects_an_arm_that_only_wins_in_one_season():
    over = {
        ("Y1", s, p): {"mae": 41.0} for s in (2022, 2023, 2024) for p in ("QB", "RB", "WR", "TE")
    }
    over |= {("Y1", 2025, p): {"mae": 5.0} for p in ("QB", "RB", "WR", "TE")}
    verdict = evaluate_gates(_frame(over), "Y1")
    assert not next(g for g in verdict.gates if g.name.startswith("G2")).passed


def test_g4_rejects_an_arm_that_damages_ordering():
    over = {("Y1", s, "TE"): {"spearman": 0.70} for s in PREREGISTERED_TARGET_SEASONS}
    verdict = evaluate_gates(_frame(over), "Y1")
    assert not next(g for g in verdict.gates if g.name.startswith("G4")).passed


def test_g5_rejects_an_arm_whose_gain_is_indistinguishable_from_noise():
    rng = np.random.default_rng(0)
    over = {
        ("Y1", s, p): {"mae": 40.0 + rng.normal(0, 8)}
        for s in PREREGISTERED_TARGET_SEASONS
        for p in ("QB", "RB", "WR", "TE")
    }
    verdict = evaluate_gates(_frame(over), "Y1")
    assert not next(g for g in verdict.gates if g.name.startswith("G5")).passed


def test_g6_rejects_an_arm_that_worsens_top_of_board_calibration():
    over = {("Y1", s, "RB"): {"top_decile_bias": 45.0} for s in PREREGISTERED_TARGET_SEASONS}
    verdict = evaluate_gates(_frame(over), "Y1")
    g6 = next(g for g in verdict.gates if g.name.startswith("G6"))
    assert not g6.passed
    assert "RB" in g6.detail


def test_g7_rejects_an_arm_that_depends_on_one_season():
    """Pooled mean still negative, but removing 2025 flips it -- exactly the failure mode a
    2025-tuned change would show."""
    over = {
        ("Y1", s, p): {"mae": 40.5} for s in (2022, 2023, 2024) for p in ("QB", "RB", "WR", "TE")
    }
    over |= {("Y1", 2025, p): {"mae": 30.0} for p in ("QB", "RB", "WR", "TE")}
    verdict = evaluate_gates(_frame(over), "Y1")
    assert not next(g for g in verdict.gates if g.name.startswith("G7")).passed


def test_control_arm_has_no_gates_and_does_not_pass():
    verdict = evaluate_gates(_frame(), PREREGISTERED_CONTROL)
    assert verdict.gates == []
    assert not verdict.passed


def test_report_renders_without_measurements():
    from alpha_squad.evaluation.projection_specification import SpecificationReport

    text = render_specification_report(SpecificationReport())
    assert "D78" in text
    assert "No measurements" in text
