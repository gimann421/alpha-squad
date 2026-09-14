"""Unit tests for D100's committed research script (`scripts/research/d100_feature_signal.py`).

The script is diagnostic, not production, but its published numbers rest on three claims that
would silently become false if production drifted underneath it, so those are pinned here:

  * its rebuilt estimator really is M6's estimator, which is what makes `D_gbm` a same-functional-
    form control rather than an unrelated model;
  * it knows the direction of every production feature, so a feature added to
    `season_level.FEATURES` breaks the script instead of being ranked backwards; and
  * the pre-registered primary universe is actually enforced, not merely described.

Loaded the same way `test_board_vintage.py` loads `scripts/d92_paired_grid.py`."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alpha_squad.models.established.season_level import FEATURES
from alpha_squad.models.uncertainty.run import _new_model


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "research" / "d100_feature_signal.py"
    spec = importlib.util.spec_from_file_location("d100_feature_signal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def test_diagnostic_estimator_is_m6s_estimator():
    """`D_gbm` is only a meaningful control if it is M6's own functional form. If M6's
    hyperparameters change, this fails rather than the script quietly measuring something else."""
    production = _new_model().get_params()
    diagnostic = MODULE._new_m6_estimator().get_params()
    assert diagnostic == production


def test_every_production_feature_has_a_declared_direction():
    assert set(MODULE.HIGHER_IS_BETTER) == set(FEATURES)


def test_ecr_is_the_only_feature_where_smaller_is_better():
    inverted = [f for f, higher in MODULE.HIGHER_IS_BETTER.items() if not higher]
    assert inverted == ["preseason_ecr_rank"]


def test_rank_aggregations_only_reference_production_features():
    for name, features in MODULE.RANK_AGGREGATIONS.items():
        assert set(features) <= set(FEATURES), name


def test_pct_rank_puts_the_best_value_at_one_in_both_directions():
    values = np.array([10.0, 20.0, 30.0])
    assert MODULE.pct_rank(values, True).tolist() == [0.0, 0.5, 1.0]
    assert MODULE.pct_rank(values, False).tolist() == [1.0, 0.5, 0.0]


def test_pct_rank_is_defined_for_a_single_row():
    assert MODULE.pct_rank(np.array([7.0]), True).tolist() == [0.5]


def test_auc_separates_and_ties_as_expected():
    scores = np.array([9.0, 8.0, 1.0, 0.0])
    labels = np.array([1, 1, 0, 0])
    assert MODULE.auc(scores, labels) == pytest.approx(1.0)
    assert MODULE.auc(-scores, labels) == pytest.approx(0.0)
    assert MODULE.auc(np.ones(4), labels) == pytest.approx(0.5)


def test_auc_is_nan_without_both_classes():
    assert np.isnan(MODULE.auc(np.array([1.0, 2.0]), np.array([1, 1])))


def test_top_set_breaks_ties_on_player_id_not_row_order():
    """Every ordering in the script must be deterministic under exact ties -- the same property
    D54 pinned for the draft engine, for the same reason."""
    frame = pd.DataFrame({"player_id": ["b", "a", "c"], "score": [1.0, 1.0, 1.0]})
    assert MODULE.top_set(frame, "score", ascending=False, n=2) == {"a", "b"}


def test_unknown_universe_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown universe"):
        MODULE.load_universe(None, "whatever")
