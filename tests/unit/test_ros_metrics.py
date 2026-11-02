"""Decision metrics: pairs, ties, regret, calibration, bootstrap."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.ros import metrics as M

pytestmark = pytest.mark.unit


def snap(y, pred, n=10):
    k = len(y)
    return pd.DataFrame(
        {
            "ecr_rank": range(1, k + 1),
            "ecr": np.arange(1, k + 1, dtype=float),
            "y_total": y,
            "pred_total": pred,
            "n_remaining": [n] * k,
        }
    )


def test_pairwise_accuracy_perfect_and_inverted_and_ties():
    y = [200, 180, 160, 140, 120, 100]
    g = snap(y, [6, 5, 4, 3, 2, 1])
    assert M.pairwise_snapshot(g)["pw_top6"] == 1.0
    assert M.pairwise_snapshot(snap(y, [1, 2, 3, 4, 5, 6]))["pw_top6"] == 0.0
    tied = snap([100, 101, 102, 103, 103.5, 104], [6, 5, 4, 3, 2, 1])  # all |diff| < 0.5*10: ties
    assert M.pairwise_snapshot(tied)["pw_top6"] == 0.5
    assert M.pairwise_snapshot(tied)["pw_top6_tie_share"] == 1.0


def test_predicted_tie_scores_half():
    g = snap([200, 150, 100, 90, 80, 70], [5.0] * 6)
    assert M.pairwise_snapshot(g)["pw_top6"] == 0.5


def test_regret_zero_when_pick_is_best_and_positive_otherwise():
    y = np.arange(24, 0, -1) * 10.0
    good = M.regret_snapshot(snap(y, y))
    assert good["regret_top6"] == 0 and good["pick_is_best_top6"] == 1.0
    bad = M.regret_snapshot(snap(y, y[::-1]))
    assert bad["regret_top6"] == pytest.approx(y[0] - y[5])
    assert bad["vs_ecr_top6"] == pytest.approx(y[5] - y[0])


def test_regret_summary_when_wrong_and_large():
    per = pd.DataFrame({"regret_qb4_15": [0.0, 0.0, 20.0, 60.0]})
    s = M.regret_summary(per, "qb4_15")
    assert (
        s["mean_regret"] == 20.0 and s["share_wrong"] == 0.5 and s["mean_regret_when_wrong"] == 40.0
    )
    assert s["share_large"] == 0.25


def test_rank_metrics_perfect():
    y = np.arange(36, 0, -1) * 5.0
    out = M.rank_metrics_snapshot(snap(y, y))
    assert (
        out["spearman"] == pytest.approx(1.0)
        and out["top12_hit"] == 1.0
        and out["mean_abs_rank_err"] == 0
    )


def test_pairprob_is_antisymmetric_monotone_and_recovers_signal():
    rng = np.random.default_rng(0)
    d = rng.normal(0, 10, 4000)
    win = (rng.random(4000) < 1 / (1 + np.exp(-0.1 * d))).astype(float)
    cp = M.PairProb().fit(d, win)
    assert cp.b_ == pytest.approx(0.1, abs=0.02)
    assert cp.prob(np.array([5.0]))[0] + cp.prob(np.array([-5.0]))[0] == pytest.approx(1.0)
    assert cp.prob(np.array([1.0]))[0] < cp.prob(np.array([2.0]))[0]


def test_brier_logloss_known_values():
    p, y = np.array([0.5, 0.5]), np.array([1.0, 0.0])
    assert M.brier(p, y) == 0.25 and M.logloss(p, y) == pytest.approx(np.log(2))


def test_reliability_bins_fold_probabilities():
    r = M.reliability(np.array([0.9, 0.1, 0.55]), np.array([1.0, 0.0, 1.0]))
    assert r["n"].sum() == 3 and r.loc[r["bin"] == "0.9-1.0", "observed"].iloc[0] == 1.0


def test_block_bootstrap_is_deterministic_and_brackets_the_mean():
    per = pd.DataFrame(
        {
            "season": np.repeat([2022, 2023, 2024, 2025], 5),
            "snapshot_week": list(range(6, 11)) * 4,
            "m": np.r_[np.full(10, 0.6), np.full(10, 0.5)],
            "m2": np.full(20, 0.4),
        }
    )
    p1, d1 = M.block_bootstrap(per, ["m", "m2"], n_boot=500, seed=1)
    p2, d2 = M.block_bootstrap(per, ["m", "m2"], n_boot=500, seed=1)
    assert np.allclose(d1["m"], d2["m"]) and p1[0] == pytest.approx(0.55)
    lo, hi = M.ci(d1["m"])
    assert lo <= 0.55 <= hi and lo >= 0.5 and hi <= 0.6
    assert np.allclose(d1["m2"], 0.4)  # a constant has zero variance


def test_design_effect_reduces_effective_snapshots_when_seasons_differ():
    per = pd.DataFrame(
        {
            "season": np.repeat([1, 2, 3, 4], 5),
            "x": np.repeat([0.4, 0.5, 0.6, 0.7], 5) + np.tile([0, 0.001, -0.001, 0, 0.002], 4),
        }
    )
    de = M.design_effect(per, "x")
    assert de["n_snapshots"] == 20 and de["icc"] > 0.9 and de["n_eff"] < 6
