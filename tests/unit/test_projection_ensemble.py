"""Regression tests for the D83 seed-ensemble pre-registration.

These lock the PROTOCOL, not any result: the arms, the nesting, the estimator, the reuse of
D82's gates, and the smallest-clearing-arm selection rule.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.evaluation import projection_features as feat
from alpha_squad.evaluation.projection_ensemble import (
    ARM_DESCRIPTIONS,
    PREREGISTERED_CONTROL,
    PRODUCTION_SEED,
    S_ARM_SEEDS,
    S_ARMS,
    EnsembleReport,
    _fit_predict,
    _new_model,
    seeds_for,
)
from alpha_squad.models.established.season_level import FEATURES, TARGET_COLUMN


def test_arms_are_exactly_the_preregistered_four() -> None:
    assert S_ARMS == ("S0", "S1", "S2", "S3")
    assert PREREGISTERED_CONTROL == "S0"
    assert set(S_ARM_SEEDS) == set(S_ARMS)
    assert set(ARM_DESCRIPTIONS) == set(S_ARMS)


def test_control_is_the_single_production_seed() -> None:
    assert PRODUCTION_SEED == 42
    assert seeds_for("S0") == (42,)


def test_seed_sets_are_nested_supersets_of_production() -> None:
    """Each arm is 'production plus more seeds', not 'a different seed' -- otherwise a win
    could be seed-cherry-picking rather than variance reduction."""
    previous: set[int] = set()
    for arm in S_ARMS:
        seeds = set(seeds_for(arm))
        assert PRODUCTION_SEED in seeds, arm
        assert previous <= seeds, arm
        previous = seeds


def test_seed_counts_increase_monotonically() -> None:
    counts = [len(seeds_for(arm)) for arm in S_ARMS]
    assert counts == sorted(counts)
    assert counts == [1, 4, 12, 24]


def test_seeds_are_unique_within_each_arm() -> None:
    for arm in S_ARMS:
        assert len(set(seeds_for(arm))) == len(seeds_for(arm)), arm


def test_unknown_arm_raises() -> None:
    with pytest.raises(ValueError):
        seeds_for("S9")


def test_estimator_is_byte_identical_to_production_apart_from_the_seed() -> None:
    params = _new_model(7).get_params()
    assert params["iterations"] == 150
    assert params["depth"] == 3
    assert params["learning_rate"] == 0.08
    assert params["loss_function"] == "MAE"
    assert params["random_seed"] == 7
    assert "monotone_constraints" not in params


def test_gates_are_the_same_objects_as_d82() -> None:
    """The gates are imported rather than restated, so a threshold cannot silently diverge."""
    import alpha_squad.evaluation.projection_ensemble as ens

    assert ens.evaluate_gates is feat.evaluate_gates
    assert ens.PREREGISTERED_TIERS is feat.PREREGISTERED_TIERS
    assert ens.PREREGISTERED_TARGET_SEASONS is feat.PREREGISTERED_TARGET_SEASONS


def test_ensemble_uses_only_the_shipped_features() -> None:
    """D83 varies the seed and nothing else; the feature set must stay Y1's four."""
    train = pd.DataFrame(
        {
            **{f: np.linspace(1, 100, 60) + i for i, f in enumerate(FEATURES)},
            TARGET_COLUMN: np.linspace(50, 300, 60),
            "extra_column_that_must_be_ignored": np.random.default_rng(0).normal(size=60),
        }
    )
    target = train.head(5)
    members = _fit_predict(train, target, (42, 43))
    assert members.shape == (2, 5)


def test_prediction_is_the_mean_of_the_members() -> None:
    rng = np.random.default_rng(1)
    train = pd.DataFrame(
        {
            **{f: rng.normal(size=80) * 50 + 100 for f in FEATURES},
            TARGET_COLUMN: rng.normal(size=80) * 60 + 180,
        }
    )
    target = train.head(8)
    members = _fit_predict(train, target, (42, 43, 44))
    assert members.shape == (3, 8)
    assert np.allclose(members.mean(axis=0), np.mean([m for m in members], axis=0))


def test_a_single_seed_arm_reproduces_the_production_fit_exactly() -> None:
    """S0 must be Y1. If it drifts, every delta in the phase is measured against the wrong
    baseline."""
    rng = np.random.default_rng(2)
    train = pd.DataFrame(
        {
            **{f: rng.normal(size=80) * 50 + 100 for f in FEATURES},
            TARGET_COLUMN: rng.normal(size=80) * 60 + 180,
        }
    )
    target = train.head(6)
    ensemble = _fit_predict(train, target, seeds_for("S0"))[0]
    direct = (
        _new_model(PRODUCTION_SEED)
        .fit(train[list(FEATURES)].to_numpy(dtype=float), train[TARGET_COLUMN].to_numpy())
        .predict(target[list(FEATURES)].to_numpy(dtype=float))
    )
    assert np.allclose(ensemble, direct)


def test_averaging_reduces_member_spread() -> None:
    """The mechanism this phase is built on: the mean of k fits is less seed-sensitive than any
    single fit. Verified numerically rather than assumed."""
    rng = np.random.default_rng(3)
    train = pd.DataFrame(
        {
            **{f: rng.normal(size=120) * 50 + 100 for f in FEATURES},
            TARGET_COLUMN: rng.normal(size=120) * 60 + 180,
        }
    )
    target = train.head(20)
    members = _fit_predict(train, target, tuple(range(42, 54)))
    singles = members.std(axis=0, ddof=1).mean()
    halves = np.vstack([members[:6].mean(axis=0), members[6:].mean(axis=0)])
    assert halves.std(axis=0, ddof=1).mean() < singles


def test_selection_prefers_the_smallest_clearing_ensemble(monkeypatch) -> None:
    """Occam plus training cost: if S1 and S3 both cleared, S1 ships."""
    import alpha_squad.evaluation.projection_ensemble as ens

    monkeypatch.setattr(ens, "measure_arm_season", lambda con, arm, season: ([], {}))

    def _verdicts(tiers, extras, arm, control=PREREGISTERED_CONTROL):
        v = feat.ArmVerdict(arm=arm)
        v.gates.append(feat.GateResult("P1", arm in {"S1", "S3"}, ""))
        return v

    monkeypatch.setattr(ens, "evaluate_gates", _verdicts)
    report = ens.run_ensemble_experiment(con=None, seasons=(2022,))
    assert report.selected == "S1"


def test_selection_is_none_when_no_arm_clears(monkeypatch) -> None:
    import alpha_squad.evaluation.projection_ensemble as ens

    monkeypatch.setattr(ens, "measure_arm_season", lambda con, arm, season: ([], {}))
    monkeypatch.setattr(
        ens,
        "evaluate_gates",
        lambda tiers, extras, arm, control=PREREGISTERED_CONTROL: feat.ArmVerdict(
            arm=arm, gates=[feat.GateResult("P1", False, "")]
        ),
    )
    assert ens.run_ensemble_experiment(con=None, seasons=(2022,)).selected is None


def test_empty_report_frames_are_wellformed() -> None:
    report = EnsembleReport()
    assert report.tier_frame().empty
    assert report.extras_frame().empty
