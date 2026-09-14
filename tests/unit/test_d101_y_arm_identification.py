"""Unit tests for D101's research harness (`scripts/research/d101_y_arm_identification.py`).

The harness is diagnostic, not production, but its published verdict depends on three properties
that must not be allowed to drift silently:

  * exact cancellation is classified as a TIE, not a win (a real defect this phase hit and fixed
    -- see `test_exact_cancellation_is_a_tie`);
  * it measures D101's registered population, not some later reinterpretation of it; and
  * it refuses, loudly, to score arms on pools that are not identical.

Loaded the same way `test_board_vintage.py` loads `scripts/d92_paired_grid.py`."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation.board_vintage import BACKTEST_SEASONS
from alpha_squad.evaluation.projection_specification import (
    PREREGISTERED_CONTROL,
    PREREGISTERED_TARGET_SEASONS,
    Y_ARMS,
)


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research"
    spec = importlib.util.spec_from_file_location(
        "d101_y_arm_identification", path / "d101_y_arm_identification.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def test_exact_cancellation_is_a_tie_not_a_win():
    """Regression test, built from the real cell counts that produced the defect.

    2024's Y1-vs-Y0 top-6 hit counts were QB 3v3, RB 3v3, WR 1v2, TE 3v2 -- one position lost a
    player and one gained one, so the season is a tie. But the deltas are differences of sixths
    (1/6 - 2/6 and 3/6 - 2/6), which do not cancel in IEEE-754: their mean is 6.9e-18. The first
    run of this harness counted that as a WIN, reporting Y1's season record as 3W/1L when it is
    2W/1T/1L. Note the naive literal `mean([1/6, -1/6, 1/6, -1/6])` is exactly 0.0 and does NOT
    reproduce it -- the artifact needs the subtraction, which is why this test carries the counts
    rather than the deltas."""
    counts = [(3, 3), (3, 3), (1, 2), (3, 2)]
    deltas = [arm / 6 - control / 6 for arm, control in counts]
    season_mean = float(np.mean(deltas))
    assert season_mean != 0.0, "the artifact this guards against has to exist to be worth guarding"
    assert season_mean == pytest.approx(0.0, abs=1e-15)
    assert MODULE._sign_counts([season_mean]) == (0, 1, 0)


def test_sign_counts_still_sees_the_smallest_real_difference():
    """The tolerance must not swallow a genuine result: one cell of four differing by one
    player is 1/24, five orders of magnitude above the floor."""
    smallest_real = 1 / 24
    assert smallest_real > MODULE.SIGN_TOLERANCE * 1e6
    assert MODULE._sign_counts([smallest_real, -smallest_real, 0.0]) == (1, 1, 1)


def test_sign_counts_partitions_every_value():
    values = [0.5, -0.5, 0.0, 1e-15, 0.25]
    wins, ties, losses = MODULE._sign_counts(values)
    assert wins + ties + losses == len(values)


def test_registered_population_is_the_y_arm_registration_not_a_reinterpretation():
    """D101 measures D78's registered window. If a later phase widens it, this fails rather than
    the harness quietly reporting a different experiment under the same name."""
    assert PREREGISTERED_TARGET_SEASONS == (2022, 2023, 2024, 2025)
    assert set(PREREGISTERED_TARGET_SEASONS) <= set(BACKTEST_SEASONS)
    assert 2020 not in PREREGISTERED_TARGET_SEASONS
    assert 2026 not in PREREGISTERED_TARGET_SEASONS


def test_transparency_season_is_outside_the_decision_window():
    assert MODULE.TRANSPARENCY_SEASON not in PREREGISTERED_TARGET_SEASONS
    assert MODULE.TRANSPARENCY_SEASON in BACKTEST_SEASONS


def test_arms_and_control_are_the_registered_ones():
    assert Y_ARMS == ("Y0", "Y1", "Y2", "Y3")
    assert PREREGISTERED_CONTROL == "Y0"


def test_identification_uses_d100s_definition():
    """Not 'the same as D100' by comment -- the harness imports D100's own functions."""
    d100_path = Path(__file__).resolve().parents[2] / "scripts" / "research"
    assert MODULE.D100.__file__ == str(d100_path / "d100_feature_signal.py")
    assert MODULE.TOP_N == 6


def test_identification_row_scores_a_perfect_and_an_inverted_ranking():
    target = pd.DataFrame(
        {
            "player_id": [f"p{i}" for i in range(12)],
            "target_points": [float(100 - i) for i in range(12)],
        }
    )
    perfect = MODULE.identification_row(target, target["target_points"].to_numpy())
    assert perfect["top6_hits"] == 6
    assert perfect["top6_hit_rate"] == 1.0
    assert perfect["auc"] == pytest.approx(1.0)

    inverted = MODULE.identification_row(target, -target["target_points"].to_numpy())
    assert inverted["top6_hits"] == 0
    assert inverted["auc"] == pytest.approx(0.0)


def test_identification_row_breaks_ties_deterministically():
    """All-equal projections must not let row order decide the projected top 6 -- D54's
    convention, applied here through D100's `top_set`."""
    target = pd.DataFrame(
        {
            "player_id": ["z", "y", "x", "w", "v", "u", "t", "s"],
            "target_points": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )
    flat = np.ones(len(target))
    first = MODULE.identification_row(target, flat)
    shuffled = target.iloc[::-1].reset_index(drop=True)
    second = MODULE.identification_row(shuffled, np.ones(len(shuffled)))
    assert first["top6_hits"] == second["top6_hits"]


def test_universe_mismatch_is_an_error_type_not_a_warning():
    assert issubclass(MODULE.UniverseMismatchError, RuntimeError)
