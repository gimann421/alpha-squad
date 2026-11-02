"""Temporal leakage tests for the ROS pipeline (alpha_squad.ros).

Adversarial posture: corrupt EVERYTHING that happens after the snapshot and assert the features do
not move; corrupt the held-out season and assert the fitted models do not move.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_squad.ros import backtest as BT
from alpha_squad.ros import models as MD
from alpha_squad.ros import snapshots as sn
from tests.unit.ros_fixtures import gameday, make_inputs

pytestmark = pytest.mark.leakage

TARGET_COLS = (
    "y_total",
    "y_apps",
    "y_total_w14",
    "y_apps_w14",
    "y_rate",
    "y_rate_w14",
    "target_complete",
    "n_future_played",
)


def features_only(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.drop(columns=[c for c in df.columns if c in TARGET_COLS])
        .sort_values("gsis_id")
        .reset_index(drop=True)
    )


def test_post_snapshot_results_cannot_change_any_feature():
    inp, spec = make_inputs(scrape_week=8)
    clean = features_only(sn.build_snapshot_rows(inp, spec))
    future = inp.stats["gameday"] >= spec.scrape_date
    for col in ("pts", "passing_yards", "attempts", "carries", "passing_tds"):
        inp.stats.loc[future, col] = 9999.0
    inp.schedule.loc[inp.schedule["gameday"] >= spec.scrape_date, "pts_for"] = 999.0
    dirty_full = sn.build_snapshot_rows(inp, spec)
    pd.testing.assert_frame_equal(clean, features_only(dirty_full), check_exact=False, rtol=1e-12)
    assert dirty_full["y_total"].max() > 1000  # and the corruption really did reach the target


def test_other_dates_ecr_rows_cannot_change_the_snapshot():
    inp, spec = make_inputs(scrape_week=8)
    clean = sn.build_snapshot_rows(inp, spec)
    later = inp.ecr.copy()
    later["scrape_date"] = gameday(12)
    later["ecr"] = later["ecr"][::-1].to_numpy()
    inp.ecr = pd.concat([inp.ecr, later], ignore_index=True)
    pd.testing.assert_frame_equal(clean, sn.build_snapshot_rows(inp, spec))


def test_prior_season_features_use_only_the_prior_season():
    inp, spec = make_inputs(scrape_week=8)
    prior = inp.stats.copy()
    prior["season"] = 2023
    prior["pts"] = 123.0
    inp.stats = pd.concat([inp.stats, prior], ignore_index=True)
    r = sn.build_snapshot_rows(inp, spec).set_index("gsis_id")
    assert r["ppg_prev"].eq(123.0).all()
    assert r.loc["00-QA", "apps"] == 6  # current-season counts unaffected by the prior season


def synthetic_panel(seed: int = 0, seasons=(2020, 2021, 2022, 2023, 2024)) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    feats = sorted(
        set(MD.USAGE + MD.CONTEXT + MD.PROD_MIN + MD.RECENT) - {"ppg_tg", "apps_share", "log_ecr"}
    )
    for s in seasons:
        for w in (6, 7, 8, 9, 10):
            for k in range(36):
                n = int(rng.integers(8, 12))
                ecr = k + 1 + rng.normal(0, 0.2)
                rate = max(24 - 0.4 * k + rng.normal(0, 3), 0)
                r = dict(
                    season=s,
                    snapshot_week=w,
                    scrape_date=f"{s}-10-1{w % 10}",
                    gsis_id=f"p{s}_{k}",
                    player=f"p{k}",
                    ecr=ecr,
                    ecr_rank=k + 1,
                    ecr_sd=1.0,
                    ecr_best=ecr - 1,
                    ecr_worst=ecr + 1,
                    n_remaining=n,
                    team_games_played=w - 1,
                    pts_total=rate * (w - 1),
                    apps=w - 1,
                    rush_att_pg=float(rng.uniform(0, 8)),
                    y_rate=rate,
                    y_total=rate * n,
                    y_apps=float(n),
                    target_complete=True,
                    eval_week=True,
                )
                r.update({f: float(rng.normal(10, 3)) for f in feats})
                r["ppg_app"] = rate + rng.normal(0, 2)
                rows.append(r)
    return pd.DataFrame(rows)


class Recorder:
    def __init__(self, inner, log):
        self.inner, self.log = inner, log
        self.name = inner.name

    def fit(self, train):
        self.log.append(sorted(train["season"].unique().tolist()))
        self.inner.fit(train)
        return self

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def predict_rate(self, df):
        return self.inner.predict_rate(df)


def test_walk_forward_never_fits_on_the_test_season_or_later(monkeypatch):
    log: list[list[int]] = []
    real = BT.make_model
    monkeypatch.setattr(BT, "make_model", lambda name: Recorder(real(name), log))
    panel = synthetic_panel()
    BT.run_backtest(panel, models=("A_ecr", "S2D", "D_usage"), test_seasons=(2022, 2023, 2024))
    assert log, "recorder never invoked"
    # every fit call the driver makes sees a strictly earlier set of seasons than the test season
    for seasons in log:
        assert max(seasons) < 2024
    assert any(max(s) == 2023 for s in log)  # the real test-season-2024 fit used 2023 and earlier


def test_corrupting_the_test_season_does_not_change_its_own_predictions():
    panel = synthetic_panel()
    a = BT.run_backtest(
        panel, models=("A_ecr", "D_usage", "E_blend"), test_seasons=(2023,), compute_oof=False
    ).preds
    bad = panel.copy()
    m = bad["season"] == 2023
    for c in ("y_rate", "y_total", "y_apps"):
        bad.loc[m, c] = 0.0 if c != "y_apps" else 1.0
    b = BT.run_backtest(
        bad, models=("A_ecr", "D_usage", "E_blend"), test_seasons=(2023,), compute_oof=False
    ).preds
    pd.testing.assert_series_equal(
        a["pred_total"], b["pred_total"]
    )  # predictions blind to test outcomes
    assert not np.allclose(a["y_total"], b["y_total"])


def test_future_seasons_cannot_influence_a_past_test_season():
    panel = synthetic_panel()
    a = BT.run_backtest(
        panel, models=("D_usage", "E_blend"), test_seasons=(2022,), compute_oof=False
    ).preds
    bad = panel.copy()
    bad.loc[bad["season"] > 2022, "y_rate"] = 99.0
    b = BT.run_backtest(
        bad, models=("D_usage", "E_blend"), test_seasons=(2022,), compute_oof=False
    ).preds
    pd.testing.assert_series_equal(a["pred_total"], b["pred_total"])


def test_oof_calibration_predictions_exclude_the_test_season():
    panel = synthetic_panel()
    res = BT.run_backtest(panel, models=("A_ecr",), test_seasons=(2023,))
    assert res.oof["season"].max() < 2023 and (res.oof["test_season"] == 2023).all()
