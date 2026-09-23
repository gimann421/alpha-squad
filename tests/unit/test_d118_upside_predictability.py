"""Unit tests for D118's upside-predictability diagnostic
(`scripts/research/d118_upside_predictability.py`).

D118's conclusions rest on these properties, pinned here rather than asserted in prose:

  * walk-forward separation: a season's predictions come only from strictly earlier seasons, and
    the first season of the window has no out-of-sample prediction at all;
  * features are z-scored WITHIN (season, position), so no feature can order players across
    positions (the D117 artifact);
  * the ridge has an unpenalised per-position intercept and a FIXED penalty -- nothing is tuned;
  * the decision test counts a flip only when proj + e_hat reverses proj's order, scores it
    against the realized order, and books the realized points gained;
  * no outcome column is ever a feature, and the future-dated `dynasty_values` table is excluded.

Loaded the same way the D115-D117 tests load their runners.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("d118_upside_predictability")
RUNNER_SOURCE = (ROOT / "scripts" / "research" / "d118_upside_predictability.py").read_text()


def _row(pid, season, pos, cohort="established", e=0.0, **feats):
    base = dict.fromkeys(M.ESTABLISHED_FEATURES + M.ROOKIE_FEATURES, 0.0)
    base.update(feats)
    return {
        "player_id": pid,
        "season": season,
        "position": pos,
        "cohort": cohort,
        "e": e,
        "abs_e": abs(e),
        **base,
    }


class TestWalkForward:
    def test_oos_seasons_exclude_the_first_season_of_the_window(self):
        assert min(M.BACKTEST_SEASONS) not in M.OOS_SEASONS
        assert set(M.OOS_SEASONS) == set(M.BACKTEST_SEASONS) - {min(M.BACKTEST_SEASONS)}

    def test_a_season_is_predicted_only_from_earlier_seasons(self):
        """Plant a relationship that exists ONLY in the evaluation season. A walk-forward model
        cannot have learned it, so its predictions in that season must be flat in the feature."""
        rows = []
        for season in M.BACKTEST_SEASONS:
            for i in range(20):
                x = float(i)
                e = 10.0 * x if season == max(M.BACKTEST_SEASONS) else 0.0
                rows.append(_row(f"p{i}", season, "WR", e=e, age=x))
        preds = M.walk_forward(rows, "established", "e")
        last = max(M.BACKTEST_SEASONS)
        vals = [preds["age"][(f"p{i}", last)] for i in range(20)]
        assert max(vals) - min(vals) == pytest.approx(0.0, abs=1e-9)
        assert all((f"p{i}", min(M.BACKTEST_SEASONS)) not in preds["age"] for i in range(20))

    def test_a_stable_relationship_is_learned(self):
        rows = []
        for season in M.BACKTEST_SEASONS:
            for i in range(20):
                rows.append(_row(f"p{i}", season, "WR", e=5.0 * i, age=float(i)))
        preds = M.walk_forward(rows, "established", "e")
        s = M.OOS_SEASONS[-1]
        assert preds["age"][("p19", s)] > preds["age"][("p0", s)]


class TestStandardisation:
    def test_zscore_is_within_group(self):
        rows = [_row("a", 2022, "QB", age=10.0), _row("b", 2022, "QB", age=20.0)]
        rows += [_row("c", 2022, "RB", age=100.0), _row("d", 2022, "RB", age=200.0)]
        M.zscore_within(rows, "age", lambda r: (r["season"], r["position"]))
        z = {r["player_id"]: r["z_age"] for r in rows}
        assert z["a"] == pytest.approx(z["c"])
        assert z["b"] == pytest.approx(z["d"])

    def test_missing_is_imputed_to_the_group_median(self):
        rows = [_row("a", 2022, "QB", age=1.0), _row("b", 2022, "QB", age=3.0)]
        rows.append(_row("c", 2022, "QB", age=None))
        M.zscore_within(rows, "age", lambda r: (r["season"], r["position"]))
        assert {r["player_id"]: r["z_age"] for r in rows}["c"] == pytest.approx(0.0)

    def test_a_constant_group_scores_zero(self):
        rows = [_row("a", 2022, "QB", age=5.0), _row("b", 2022, "QB", age=5.0)]
        M.zscore_within(rows, "age", lambda r: (r["season"], r["position"]))
        assert all(r["z_age"] == 0.0 for r in rows)


class TestRidge:
    def test_intercepts_are_per_position_and_unpenalised(self):
        x = np.zeros((4, 1))
        y = np.array([10.0, 10.0, -5.0, -5.0])
        coef, b0 = M.fit_ridge(x, y, ["QB", "QB", "RB", "RB"])
        assert b0["QB"] == pytest.approx(10.0)
        assert b0["RB"] == pytest.approx(-5.0)
        assert coef[0] == pytest.approx(0.0)

    def test_the_penalty_is_fixed_not_searched(self):
        assert M.RIDGE_ALPHA == 1.0
        for forbidden in ("GridSearch", "cross_val", "optimize", "for alpha in"):
            assert forbidden not in RUNNER_SOURCE

    def test_unknown_position_falls_back_to_the_mean_intercept(self):
        coef, b0 = M.fit_ridge(np.zeros((2, 1)), np.array([2.0, 4.0]), ["QB", "RB"])
        pred = M.predict_ridge(coef, b0, np.zeros((1, 1)), ["TE"])
        assert pred[0] == pytest.approx(3.0)


class TestMetrics:
    def test_auc(self):
        assert M.auc([1, 2, 3, 4], [False, False, True, True]) == 1.0
        assert M.auc([4, 3, 2, 1], [False, False, True, True]) == 0.0
        assert M.auc([1, 2], [True, True]) is None

    def test_pairwise_concordance_skips_ties(self):
        c, d = M.pairwise_concordance([1.0, 2.0, 2.0], [1.0, 2.0, 3.0])
        assert d == 2 and c == 2

    def test_decision_flips_scores_against_the_realized_order(self):
        proj = [100.0, 90.0]
        adj = [100.0, 120.0]  # the adjustment reverses the order
        res = M.decision_flips(proj, adj, [50.0, 80.0])
        assert res == {
            "pairs": 1,
            "flipped": 1,
            "flips_correct": 1,
            "base_correct": 0,
            "gain": 30.0,
        }
        wrong = M.decision_flips(proj, adj, [80.0, 50.0])
        assert wrong["flips_correct"] == 0 and wrong["gain"] == -30.0

    def test_close_pairs_are_filtered_by_projection_gap(self):
        res = M.decision_flips([100.0, 50.0], [0.0, 60.0], [1.0, 2.0], close_gap=30.0)
        assert res["pairs"] == 0

    def test_season_ci_uses_the_k_specific_t(self):
        res = M.season_ci({2022: 0.1, 2023: 0.2, 2024: 0.3, 2025: 0.4})
        assert res["k"] == 4
        assert res["mde"] == pytest.approx(3.182 * np.std([0.1, 0.2, 0.3, 0.4], ddof=1) / 2)

    def test_age_is_measured_at_september_first(self):
        assert M.age_on(date(2000, 9, 1), 2022) == pytest.approx(22.0, abs=0.01)
        assert M.age_on(None, 2022) is None


class TestSequencingPairs:
    def test_flip_requires_the_adjustment_to_overcome_the_projection_gap(self):
        idx = {("a", 2023): {"proj": 200.0}, ("o", 2023): {"proj": 150.0}}
        pair = {
            "alpha": "a",
            "oracle": "o",
            "season": 2023,
            "same_position": True,
            "regret_roster": 100.0,
            "A": {"proj_vorp": 0.0},
            "O": {"proj_vorp": 0.0},
        }
        small = M.sequencing_pairs([pair], {"s": {("a", 2023): 0.0, ("o", 2023): 20.0}}, idx)
        assert small["s"]["same"]["favors_O"] == 1
        assert small["s"]["same"]["flips_to_O"] == 0
        big = M.sequencing_pairs([pair], {"s": {("a", 2023): 0.0, ("o", 2023): 60.0}}, idx)
        assert big["s"]["same"]["flips_to_O"] == 1
        assert big["s"]["same"]["regret_flipped"] == 100.0

    def test_a_missing_prediction_is_undefined_not_a_loss(self):
        pair = {
            "alpha": "k",
            "oracle": "o",
            "season": 2021,
            "same_position": False,
            "regret_roster": 5.0,
            "A": {"proj_vorp": 1.0},
            "O": {"proj_vorp": 0.0},
        }
        res = M.sequencing_pairs([pair], {"s": {}}, {})
        assert res["s"]["cross"]["n"] == 1 and res["s"]["cross"]["defined"] == 0


class TestDataDiscipline:
    def test_no_outcome_is_a_feature(self):
        for outcome in ("e", "abs_e", "e_pos", "realized", "beat50", "beat100"):
            assert outcome not in M.ESTABLISHED_FEATURES
            assert outcome not in M.ROOKIE_FEATURES

    def test_future_dated_dynasty_values_are_excluded(self):
        assert "FROM dynasty_values" not in RUNNER_SOURCE
        assert "dynasty_values" in RUNNER_SOURCE  # the exclusion is documented

    def test_prior_season_inputs_are_s_minus_1(self):
        assert "[season - 1]" in RUNNER_SOURCE

    def test_the_market_board_is_page_scoped(self):
        assert '"redraft-overall"' in RUNNER_SOURCE
        assert "page_type = ?" in RUNNER_SOURCE

    def test_the_verdict_rule_is_pre_registered(self):
        assert "VERDICT RULE (fixed now)" in RUNNER_SOURCE
        assert M.MIN_FLIP_SHARE == 0.05

    def test_the_retired_arm_name_is_absent(self):
        name = "N" + "AIVE"
        assert name not in RUNNER_SOURCE
        assert name not in Path(__file__).read_text()
