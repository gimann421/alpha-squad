"""Models A-E: comparable ROS QB forecasters behind one interface (D116).

Every model predicts ``y_rate`` -- fantasy points per scheduled team game over the remainder of
the season, with a missed game counting as 0 -- and ``predict_total`` multiplies by the QB's
``n_remaining`` so byes are respected. All fitting (imputation medians, standardization, ridge
penalty, rank->points map, ensemble weights) happens inside ``fit`` on TRAINING rows only; the
walk-forward driver never passes a test-season row to ``fit``.

| name        | paper model | information used                                              |
|-------------|-------------|---------------------------------------------------------------|
| ``S2D``     | baseline    | season-to-date points per team game (parameter free)          |
| ``A_ecr``   | A           | ECR only, rank->points map fitted on training seasons         |
| ``A_iso``   | A (sens.)   | same, isotonic map                                            |
| ``C_prod``  | C           | season-to-date + prior-season production + availability      |
| ``C_recent``| C           | ``C_prod`` + last-1/3/5 game form (tests recency)             |
| ``D_usage`` | D           | ``C_recent`` + passing/rushing/red-zone usage + team + sched  |
| ``D_gbm``   | D (sens.)   | same features, shallow gradient-boosted trees                 |
| ``E_stack`` | E           | ECR + ``C_recent`` features in one ridge                      |
| ``E_full``  | E           | ECR + every feature in one ridge                              |
| ``E_blend`` | E           | convex blend of ``A_ecr`` and ``D_usage``; weight fitted on   |
|             |             | out-of-fold training predictions                              |
| ``E_avg``   | E (no fit)  | 50/50 average of ``A_ecr`` and ``D_usage``                    |

Model B (FantasyPros ROS point projections) is deliberately absent: the archive holds no ROS point
projections (see ``snapshots`` and the report). Nothing is substituted for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import Ridge

ALPHA_GRID = (0.1, 1.0, 10.0, 30.0, 100.0, 300.0, 1000.0)

ECR_FEATS = ["log_ecr", "ecr", "ecr_range", "ecr_sd"]
PROD_MIN = ["ppg_tg", "ppg_app", "ppg_prev", "apps_share", "apps_prev"]
RECENT = ["last1", "last3", "last5"]
USAGE = [
    "att_pg",
    "rush_att_pg",
    "rush_pts_pg",
    "rz20_pass_pg",
    "gl_rush_pg",
    "rz10_rush_pg",
    "scramble_pg",
    "designed_rush_pg",
    "epa_db",
    "cpoe",
    "sack_rate",
    "ypa",
    "pass_td_pg",
    "int_pg",
    "air_per_att",
    "cmp_pct",
    "started_share",
    "pts_sd",
]
CONTEXT = [
    "team_plays_pg",
    "team_pass_rate",
    "team_epa_play",
    "team_ppg",
    "sched_adj",
    "inj_prev_flag",
    "inj_prev_any",
    "inj_weeks_listed",
    "inj_cur_flag",
    "team_changed",
    "games_missed",
    "att_pg_prev",
    "rush_att_pg_prev",
]
MODEL_FEATURES: dict[str, list[str]] = {
    "C_prod": PROD_MIN,
    "C_recent": PROD_MIN + RECENT,
    "D_usage": PROD_MIN + RECENT + USAGE + CONTEXT,
    "D_gbm": PROD_MIN + RECENT + USAGE + CONTEXT,
    "E_stack": ECR_FEATS + PROD_MIN + RECENT,
    "E_full": ECR_FEATS + PROD_MIN + RECENT + USAGE + CONTEXT,
}


PRIOR = ["ppg_prev", "apps_prev", "att_pg_prev", "rush_att_pg_prev"]
SEASON = ["ppg_tg", "ppg_app", "apps_share", "pts_sd", "started_share"]
#: feature groups used by the drop-one-group ablation (`<base>-<GROUP>` model names)
GROUPS: dict[str, list[str]] = {
    "ECR": ECR_FEATS,
    "RECENT": RECENT,
    "USAGE": USAGE,
    "CONTEXT": CONTEXT,
    "PRIOR": PRIOR,
    "SEASON": SEASON,
    "SCHED": ["sched_adj"],
    "INJ": ["inj_prev_flag", "inj_prev_any", "inj_weeks_listed", "inj_cur_flag", "games_missed"],
    "RZRUSH": [
        "rush_att_pg",
        "rush_pts_pg",
        "rz20_pass_pg",
        "gl_rush_pg",
        "rz10_rush_pg",
        "scramble_pg",
        "designed_rush_pg",
    ],
    "TEAMENV": ["team_plays_pg", "team_pass_rate", "team_epa_play", "team_ppg"],
}


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Columns every model reads. Pure row-wise functions of as-of columns (no cross-row stats)."""
    d = df.copy()
    tg = d["team_games_played"].replace(0, np.nan)
    d["ppg_tg"] = d["pts_total"] / tg
    d["apps_share"] = d["apps"] / tg
    d["log_ecr"] = np.log(d["ecr"])
    d["ecr_range"] = d["ecr_worst"] - d["ecr_best"]
    return d


@dataclass
class Prep:
    """Median imputation + missing indicators + standardization, fitted on training rows only."""

    cols: list[str]
    med: dict[str, float] | None = None
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None
    miss_cols: list[str] | None = None

    def fit(self, df: pd.DataFrame) -> Prep:
        X = df[self.cols].astype(float)
        self.med = {c: float(np.nanmedian(X[c])) if X[c].notna().any() else 0.0 for c in self.cols}
        self.miss_cols = [c for c in self.cols if X[c].isna().any()]
        Z = self._raw(df)
        self.mu = Z.mean(axis=0)
        self.sd = Z.std(axis=0)
        self.sd[self.sd < 1e-9] = 1.0
        return self

    def _raw(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.cols].astype(float)
        miss = (
            X[self.miss_cols].isna().astype(float).to_numpy()
            if self.miss_cols
            else np.zeros((len(X), 0))
        )
        Xf = X.fillna(pd.Series(self.med)).to_numpy()
        return np.hstack([Xf, miss])

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        return (self._raw(df) - self.mu) / self.sd


class ROSModel:
    """Base: ``fit(train_df)`` then ``predict_rate(df)``; ``predict_total`` applies n_remaining."""

    name = "base"

    def fit(self, train: pd.DataFrame) -> ROSModel:  # pragma: no cover - interface
        raise NotImplementedError

    def predict_rate(self, df: pd.DataFrame) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    def predict_total(self, df: pd.DataFrame) -> np.ndarray:
        return self.predict_rate(df) * df["n_remaining"].to_numpy()


class S2D(ROSModel):
    """Season-to-date points per team game; falls back to the prior-season rate, then to the
    training mean. No fitted parameters except that mean (a fallback only)."""

    name = "S2D"

    def fit(self, train):
        self.mean_ = float(train["y_rate"].mean())
        return self

    def predict_rate(self, df):
        r = df["ppg_tg"].copy()
        r = r.where(r.notna(), df["ppg_prev"])
        return r.fillna(self.mean_).to_numpy()


class S2DPlay(ROSModel):
    """Season-to-date points per game PLAYED (assumes full health): isolates the availability
    component of ``S2D``."""

    name = "S2D_play"

    def fit(self, train):
        self.mean_ = float(train["y_total"].sum() / max(train["y_apps"].sum(), 1.0))
        return self

    def predict_rate(self, df):
        r = df["ppg_app"].where(df["ppg_app"].notna(), df["ppg_prev"])
        return r.fillna(self.mean_).to_numpy()


def _loso_alpha(
    train: pd.DataFrame, cols: list[str], target: str, mask: np.ndarray, weight: str | None
) -> float:
    """Ridge penalty by leave-one-season-out CV inside the TRAINING seasons only."""
    d = train[mask]
    seasons = d["season"].to_numpy()
    uniq = np.unique(seasons)
    if len(uniq) < 2:
        return 100.0
    y = d[target].to_numpy()
    w = d[weight].to_numpy() if weight else np.ones(len(d))
    best, best_err = ALPHA_GRID[-1], np.inf
    for a in ALPHA_GRID:
        err = 0.0
        for s in uniq:
            tr, te = seasons != s, seasons == s
            p = Prep(cols).fit(d[tr])
            m = Ridge(alpha=a).fit(p.transform(d[tr]), y[tr], sample_weight=w[tr])
            err += float(np.sum(w[te] * (m.predict(p.transform(d[te])) - y[te]) ** 2))
        if err < best_err:
            best, best_err = a, err
    return best


class RidgeModel(ROSModel):
    """Ridge on standardized, median-imputed features.

    ``two_part=False``: one regression of ``y_rate`` (points per scheduled team game, missed games
    = 0). ``two_part=True``: (i) points per game *played* for rows that played at least once
    (weighted by games played), times (ii) the fraction of remaining scheduled games played
    (``avail``), each with its own LOSO-selected penalty. The split matters because a QB who is
    lost for the season (y_rate = 0) is mostly unpredictable noise for the *skill* regression;
    modelling availability separately also makes "expected availability" an explicit,
    inspectable output rather than something smeared into the coefficients."""

    def __init__(
        self, name: str, cols: list[str], alpha: float | None = None, two_part: bool = False
    ):
        self.name, self.cols, self.alpha, self.two_part = name, cols, alpha, two_part

    def fit(self, train):
        train = train.copy()
        if self.two_part:
            train["y_play"] = np.where(
                train["y_apps"] > 0, train["y_total"] / train["y_apps"].clip(lower=1), np.nan
            )
            train["y_avail"] = (train["y_apps"] / train["n_remaining"].clip(lower=1)).clip(0, 1)
            played = (train["y_apps"] > 0).to_numpy()
            self.prep_ = Prep(self.cols).fit(train)
            self.play_prep_ = Prep(self.cols).fit(train[played])
            a1 = (
                self.alpha
                if self.alpha is not None
                else _loso_alpha(train, self.cols, "y_play", played, "y_apps")
            )
            a2 = (
                self.alpha
                if self.alpha is not None
                else _loso_alpha(train, self.cols, "y_avail", np.ones(len(train), bool), None)
            )
            self.alpha_ = (a1, a2)
            self.play_ = Ridge(alpha=a1).fit(
                self.play_prep_.transform(train[played]),
                train.loc[played, "y_play"].to_numpy(),
                sample_weight=train.loc[played, "y_apps"].to_numpy(),
            )
            self.avail_ = Ridge(alpha=a2).fit(
                self.prep_.transform(train), train["y_avail"].to_numpy()
            )
            return self
        y = train["y_rate"].to_numpy()
        self.prep_ = Prep(self.cols).fit(train)
        alpha = (
            self.alpha
            if self.alpha is not None
            else _loso_alpha(train, self.cols, "y_rate", np.ones(len(train), bool), None)
        )
        self.alpha_ = alpha
        self.m_ = Ridge(alpha=alpha).fit(self.prep_.transform(train), y)
        return self

    def predict_parts(self, df) -> tuple[np.ndarray, np.ndarray]:
        """(points per game played, expected availability) -- two-part models only."""
        rate = self.play_.predict(self.play_prep_.transform(df))
        avail = np.clip(self.avail_.predict(self.prep_.transform(df)), 0.0, 1.0)
        return rate, avail

    def predict_rate(self, df):
        if self.two_part:
            rate, avail = self.predict_parts(df)
            return rate * avail
        return self.m_.predict(self.prep_.transform(df))

    def coefficients(self) -> pd.Series:
        m, prep = (self.play_, self.play_prep_) if self.two_part else (self.m_, self.prep_)
        names = self.cols + [f"{c}__missing" for c in (prep.miss_cols or [])]
        return pd.Series(m.coef_ / prep.sd, index=names)


class IsoECR(ROSModel):
    name = "A_iso"

    def fit(self, train):
        self.m_ = IsotonicRegression(increasing=False, out_of_bounds="clip").fit(
            train["ecr"].to_numpy(), train["y_rate"].to_numpy()
        )
        return self

    def predict_rate(self, df):
        return self.m_.predict(df["ecr"].to_numpy())


class GBM(ROSModel):
    """One fixed, deliberately shallow configuration -- not tuned (no tuning data to spare).
    Two-part like the ridge models: points per game played x availability."""

    name = "D_gbm"

    def __init__(self, cols: list[str]):
        self.cols = cols

    @staticmethod
    def _gbm() -> HistGradientBoostingRegressor:
        return HistGradientBoostingRegressor(
            max_depth=2,
            learning_rate=0.05,
            max_iter=120,
            min_samples_leaf=30,
            l2_regularization=5.0,
            random_state=0,
        )

    def fit(self, train):
        played = (train["y_apps"] > 0).to_numpy()
        self.prep_ = Prep(self.cols).fit(train)
        X = self.prep_.transform(train)
        y_play = (train["y_total"] / train["y_apps"].clip(lower=1)).to_numpy()
        self.play_ = self._gbm().fit(
            X[played], y_play[played], sample_weight=train.loc[played, "y_apps"].to_numpy()
        )
        self.avail_ = self._gbm().fit(
            X, (train["y_apps"] / train["n_remaining"].clip(lower=1)).clip(0, 1).to_numpy()
        )
        return self

    def predict_rate(self, df):
        X = self.prep_.transform(df)
        return self.play_.predict(X) * np.clip(self.avail_.predict(X), 0, 1)


class Blend(ROSModel):
    """Convex blend ``w*A + (1-w)*B`` with ``w`` chosen on out-of-fold TRAINING predictions
    (leave-one-season-out), never on the evaluation season."""

    def __init__(
        self,
        name: str,
        make_a: Callable[[], ROSModel],
        make_b: Callable[[], ROSModel],
        w: float | None,
    ):
        self.name, self.make_a, self.make_b, self.w = name, make_a, make_b, w

    def fit(self, train):
        self.a_, self.b_ = self.make_a().fit(train), self.make_b().fit(train)
        if self.w is not None:
            self.w_ = self.w
            return self
        seasons = train["season"].to_numpy()
        uniq = np.unique(seasons)
        if len(uniq) < 2:
            self.w_ = 0.5
            return self
        pa, pb = np.zeros(len(train)), np.zeros(len(train))
        for s in uniq:
            tr, te = seasons != s, seasons == s
            pa[te] = self.make_a().fit(train[tr]).predict_rate(train[te])
            pb[te] = self.make_b().fit(train[tr]).predict_rate(train[te])
        grid = np.linspace(0, 1, 21)
        y = train["y_rate"].to_numpy()
        errs = [np.mean((w * pa + (1 - w) * pb - y) ** 2) for w in grid]
        self.w_ = float(grid[int(np.argmin(errs))])
        return self

    def predict_rate(self, df):
        return self.w_ * self.a_.predict_rate(df) + (1 - self.w_) * self.b_.predict_rate(df)


def make_model(name: str) -> ROSModel:
    if (
        "-" in name
        and name.split("-", 1)[0] in ("D_usage", "E_full")
        and name.split("-", 1)[1] in GROUPS
    ):
        base, grp = name.split("-", 1)
        cols = [c for c in MODEL_FEATURES[base] if c not in GROUPS[grp]]
        return RidgeModel(name, cols, two_part=True)
    if name == "S2D":
        return S2D()
    if name == "S2D_play":
        return S2DPlay()
    if name == "A_ecr":
        return RidgeModel("A_ecr", ["log_ecr", "ecr"])
    if name == "A_iso":
        return IsoECR()
    if name == "D_gbm":
        return GBM(MODEL_FEATURES["D_gbm"])
    if name == "D_usage_1p":
        return RidgeModel("D_usage_1p", MODEL_FEATURES["D_usage"], two_part=False)
    if name in MODEL_FEATURES:
        return RidgeModel(name, MODEL_FEATURES[name], two_part=True)
    if name == "E_blend":
        return Blend("E_blend", lambda: make_model("A_ecr"), lambda: make_model("D_usage"), None)
    if name == "E_avg":
        return Blend("E_avg", lambda: make_model("A_ecr"), lambda: make_model("D_usage"), 0.5)
    if name == "S2D_cal":  # exploratory: S2D's ordering with fitted (shrunk) magnitude
        return RidgeModel("S2D_cal", ["ppg_tg"], two_part=False)
    if name == "E_ecr_s2d_cal":  # exploratory: 3-parameter ECR + season-to-date regression
        return RidgeModel("E_ecr_s2d_cal", ["log_ecr", "ecr", "ppg_tg"], two_part=False)
    if name == "E_ecr_s2d":  # exploratory, added after seeing S2D's pairwise results
        return Blend("E_ecr_s2d", lambda: make_model("A_ecr"), lambda: make_model("S2D"), 0.5)
    if name == "E_ecr_s2d_w":
        return Blend("E_ecr_s2d_w", lambda: make_model("A_ecr"), lambda: make_model("S2D"), None)
    if name == "ECR_order":
        return ECROrder()
    raise KeyError(name)


class ECROrder(ROSModel):
    """Pure published order (no calibration): predicted rate = -ecr. Only ordinal metrics
    (pairwise, rank, regret) are meaningful for it; point metrics are skipped."""

    name = "ECR_order"

    def fit(self, train):
        return self

    def predict_rate(self, df):
        return -df["ecr"].to_numpy()


ALL_MODELS = (
    "S2D",
    "S2D_play",
    "A_ecr",
    "A_iso",
    "C_prod",
    "C_recent",
    "D_usage",
    "D_usage_1p",
    "D_gbm",
    "E_stack",
    "E_full",
    "E_blend",
    "E_avg",
    "E_ecr_s2d",
    "E_ecr_s2d_w",
    "S2D_cal",
    "E_ecr_s2d_cal",
)
#: Models added after the first look at results; reported, but flagged as exploratory.
EXPLORATORY = ("S2D_play", "E_ecr_s2d", "E_ecr_s2d_w", "D_usage_1p", "S2D_cal", "E_ecr_s2d_cal")
