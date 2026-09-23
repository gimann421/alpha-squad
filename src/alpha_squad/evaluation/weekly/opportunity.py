"""Pre-Friday opportunity: the panel, the feature sets and the forecasts (W7).

**Research only. Nothing here writes to the database and no production module imports it.**

The question this module serves
-------------------------------
W5 priced the ceiling: ranking by a week's *realized* usage-expected points beats ECR by +0.16 to
+0.21 on positional capture@10. W6 showed Alpha's ordering is set by its inputs, not its objective.
So W7 asks whether the usage that pays is **knowable on Friday** -- and in particular whether any of
it is knowable from information Alpha does not already hold.

The causality rule, and how it is enforced
------------------------------------------
Every predictor is computed from a player's **strictly prior appearances** with the same window
convention Alpha's own panel uses (`features/panel.py`): partition by player, order by
`game_date, season, week`, and never include the current row. Opponent context uses strictly
prior weeks of the same season. The previous week's depth chart is the only chart read.

That is a claim about SQL, and SQL claims are cheap. `scripts/research/w7_validity_gates.py`
therefore rebuilds this panel against a database with a week's outcome rows **physically
deleted** and requires every predictor for that week to be unchanged -- the same test W5's G2 used,
which caught two real defects there.

Timing classes (W7's scheme, from the pre-registration §2.4)
------------------------------------------------------------
Only **Class A** (demonstrably pre-Friday) enters the main feature sets. Lagged usage-expected
points are **Class B**: they are the output of a *fitted model* whose historical values may have been
produced by a model trained on later seasons, so they are isolated in `CLASS_B` and barred from the
verdict. The week's own realized usage is **Class D** and appears only as a target.
"""

from __future__ import annotations

import math

import duckdb
import pandas as pd

from alpha_squad.models.established.features import FULL_FEATURES

# ---------------------------------------------------------------------------------------
# Feature sets -- fixed in docs/weekly/W7_PREREGISTRATION.md §4, never edited after results.
# ---------------------------------------------------------------------------------------

#: Alpha's own information, exactly as production sees it (missing -> 0.0, as production does).
S0: tuple[str, ...] = tuple(FULL_FEATURES)

#: Class A signals Alpha does not hold. Nine, fixed.
NEW: tuple[str, ...] = (
    "opp_last1",
    "snap_pct_last1",
    "opp_trend",
    "opp_sd_last3",
    "air_yards_share_avg_last3",
    "carry_share_avg_last3",
    "weeks_since_last_game",
    "opponent_opp_allowed_prior",
    "depth_team_prior",
)

#: The double-counting control: re-expressions of what Alpha already has, over a longer window.
REDUNDANT: tuple[str, ...] = (
    "targets_avg_last5",
    "carries_avg_last5",
    "snap_pct_avg_last5",
    "target_share_avg_last5",
)

#: Class B -- exploratory only, never in the verdict.
CLASS_B: tuple[str, ...] = ("xfp_avg_last3",)

#: Minimum prior weeks before an opponent's allowed-opportunity figure is reported.
MIN_OPPONENT_WEEKS = 3

#: Weights for BL_WMEAN3, most recent first. Fixed in the pre-registration §6.1.
WMEAN3_WEIGHTS: tuple[float, float, float] = (0.5, 0.3, 0.2)

# ---------------------------------------------------------------------------------------
# Targets -- the week's REALIZED opportunity. Class D: outcomes, never predictors.
# ---------------------------------------------------------------------------------------

#: target id -> panel column holding the realized week-w value.
TARGETS: dict[str, str] = {
    "T_XFP": "y_xfp",
    "T_XFP_HALF": "y_xfp_half",
    "T_OPP": "y_opp",
    "T_TGT": "y_tgt",
    "T_CAR": "y_car",
    "T_TSH": "y_tsh",
    "T_SNP": "y_snp",
}
#: Which targets apply at which position (pre-registration §3). T_XFP_HALF is the Half-PPR
#: replication of T_XFP and is scored only in that replication.
TARGETS_BY_POSITION: dict[str, tuple[str, ...]] = {
    "RB": ("T_XFP", "T_OPP", "T_TGT", "T_CAR", "T_SNP"),
    "WR": ("T_XFP", "T_OPP", "T_TGT", "T_TSH", "T_SNP"),
    "TE": ("T_XFP", "T_OPP", "T_TGT", "T_TSH", "T_SNP"),
}
PRIMARY_TARGET = "T_XFP"

#: For each target, the Class A series its no-fitting baselines are built from.
#: **T_XFP's own lagged values are Class B** (the output of a fitted model -- see the module
#: docstring), so its baselines are built from lagged REALIZED fantasy points instead, which are
#: plain box-score arithmetic. The Class B version lives in the exploratory sensitivity only.
BASELINE_SOURCE: dict[str, str] = {
    "T_XFP": "fp",
    "T_XFP_HALF": "fp_half",
    "T_OPP": "opp",
    "T_TGT": "tgt",
    "T_CAR": "car",
    "T_TSH": "tsh",
    "T_SNP": "snp",
}


def _panel_sql() -> str:
    """One row per (player, season, week) appearance, every predictor strictly prior.

    `LAG` and `ROWS ... AND 1 PRECEDING` frames over `PARTITION BY player_id ORDER BY game_date,
    season, week` -- identical to Alpha's own panel -- so "last game" means the last game the
    player actually appeared in, and the window crosses seasons exactly as Alpha's does. Standard
    deviations and trend terms are NOT computed here: they are reduced in Python from explicitly
    ordered lag columns, because W5's G2 showed a SQL `stddev_samp` whose input order the planner
    may vary is not bit-reproducible."""
    lags = []
    for series in ("opp", "tgt", "car", "tsh", "snp", "fp", "fp_half", "xfp"):
        for k in (1, 2, 3, 4):
            lags.append(f"LAG({series}, {k}) OVER p AS {series}_l{k}")
    lag_sql = ",\n               ".join(lags)
    return f"""
    WITH base AS (
        SELECT s.player_id, s.season, s.week, s.game_date, s.team, s.position,
               COALESCE(s.targets, 0)                        AS tgt,
               COALESCE(s.carries, 0)                        AS car,
               COALESCE(s.targets, 0) + COALESCE(s.carries, 0) AS opp,
               s.target_share                                AS tsh,
               s.air_yards_share                             AS aysh,
               s.offense_snap_pct                            AS snp,
               s.fantasy_points_ppr                          AS fp,
               s.fantasy_points_ppr - 0.5 * COALESCE(s.receptions, 0) AS fp_half
        FROM player_week_stats s
    ),
    team_car AS (
        SELECT team, season, week, SUM(car) AS team_car FROM base GROUP BY 1, 2, 3
    ),
    usage AS (
        SELECT player_id, season, week,
               points_exp                                    AS xfp,
               points_exp - 0.5 * COALESCE(receptions_exp, 0) AS xfp_half
        FROM _usage
    ),
    joined AS (
        SELECT b.*,
               CASE WHEN tc.team_car > 0 THEN b.car * 1.0 / tc.team_car END AS carsh,
               u.xfp, u.xfp_half
        FROM base b
        LEFT JOIN team_car tc USING (team, season, week)
        LEFT JOIN usage u USING (player_id, season, week)
    )
    SELECT player_id, season, week, game_date, team, position,
           -- the week's REALIZED values: targets only, never predictors
           xfp AS y_xfp, xfp_half AS y_xfp_half, opp AS y_opp, tgt AS y_tgt, car AS y_car,
           tsh AS y_tsh, snp AS y_snp,
           {lag_sql},
           AVG(aysh)  OVER (p ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS air_yards_share_avg_last3,
           AVG(carsh) OVER (p ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS carry_share_avg_last3,
           AVG(tgt)   OVER (p ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS targets_avg_last5,
           AVG(car)   OVER (p ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS carries_avg_last5,
           AVG(snp)   OVER (p ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS snap_pct_avg_last5,
           AVG(tsh)   OVER (p ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS target_share_avg_last5,
           AVG(xfp)   OVER (p ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS xfp_avg_last3,
           LAG(season, 1) OVER p AS prev_season,
           LAG(week, 1)   OVER p AS prev_week
    FROM joined
    WINDOW p AS (PARTITION BY player_id ORDER BY game_date, season, week)
    """


def _opponent_sql() -> str:
    """The opponent's opportunity allowed to each position over strictly prior weeks of a season.

    Integer sums and counts accumulated with a `1 PRECEDING` frame, divided at the end -- exact, so
    reproducible. A defense with a bye simply has no row that week; the cumulative frame over the
    rows that exist is still strictly prior."""
    return """
    WITH og AS (
        SELECT season, week, home_team AS team, away_team AS opp FROM games WHERE game_type = 'REG'
        UNION ALL
        SELECT season, week, away_team AS team, home_team AS opp FROM games WHERE game_type = 'REG'
    ),
    per_week AS (
        SELECT og.opp AS defense, s.position, s.season, s.week,
               SUM(COALESCE(s.targets, 0) + COALESCE(s.carries, 0)) AS opp_sum,
               COUNT(*) AS n_players
        FROM player_week_stats s
        JOIN og ON og.season = s.season AND og.week = s.week AND og.team = s.team
        GROUP BY 1, 2, 3, 4
    )
    SELECT defense, position, season, week,
           SUM(opp_sum)   OVER d AS prior_opp_sum,
           SUM(n_players) OVER d AS prior_players,
           COUNT(*)       OVER d AS prior_weeks
    FROM per_week
    WINDOW d AS (PARTITION BY defense, position, season ORDER BY week
                 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
    """


def _missing(x) -> bool:
    """`None` or NaN. DuckDB's `fetchdf` turns a NULL in a numeric column into NaN, not `None`, so
    an `is None` test alone silently treats a missing lag as present."""
    return x is None or (isinstance(x, float) and math.isnan(x))


def _mean(xs: list) -> float | None:
    vals = [float(x) for x in xs if not _missing(x)]
    return sum(vals) / len(vals) if vals else None


def _sd(xs: list) -> float | None:
    vals = [float(x) for x in xs if not _missing(x)]
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _nan(x) -> float:
    return float("nan") if x is None else float(x)


def build_panel(con: duckdb.DuckDBPyConnection, positions: tuple[str, ...]) -> pd.DataFrame:
    """Every appearance at `positions`, with every pre-registered predictor and every target.

    Requires the `_usage` and `_depth` TEMP VIEWs from `context.wire_snapshot_views` to have been
    created over **2015-2025**, because the forecasts train walk-forward from 2015."""
    df = con.execute(_panel_sql()).fetchdf()
    df = df[df["position"].isin(positions)].copy()

    # --- reductions from explicitly ordered lag columns (deterministic by construction) ---
    rows = df.to_dict("records")
    for r in rows:
        opp = [r["opp_l1"], r["opp_l2"], r["opp_l3"], r["opp_l4"]]
        r["opp_last1"] = None if _missing(r["opp_l1"]) else float(r["opp_l1"])
        r["snap_pct_last1"] = None if _missing(r["snp_l1"]) else float(r["snp_l1"])
        prior_234 = _mean(opp[1:4])
        r["opp_trend"] = (
            None if _missing(r["opp_l1"]) or prior_234 is None else float(r["opp_l1"]) - prior_234
        )
        r["opp_sd_last3"] = _sd(opp[0:3])
        same_season = not _missing(r["prev_season"]) and int(r["prev_season"]) == int(r["season"])
        r["weeks_since_last_game"] = int(r["week"]) - int(r["prev_week"]) if same_season else None
    out = pd.DataFrame(rows)

    # --- opponent context, strictly prior weeks of the same season ---
    opp_rows = con.execute(_opponent_sql()).fetchdf()
    opp_rows["opponent_opp_allowed_prior"] = [
        (s / p) if (w is not None and w >= MIN_OPPONENT_WEEKS and p) else None
        for s, p, w in zip(
            opp_rows["prior_opp_sum"],
            opp_rows["prior_players"],
            opp_rows["prior_weeks"],
            strict=True,
        )
    ]
    # `opponent` is the opposing TEAM. Never `opp`, which throughout this module means opportunity
    # (targets + carries) -- the two were briefly the same name in a first draft.
    games = con.execute(
        "SELECT season, week, home_team AS team, away_team AS opponent FROM games "
        "WHERE game_type='REG' UNION ALL "
        "SELECT season, week, away_team, home_team FROM games WHERE game_type='REG'"
    ).fetchdf()
    out = out.merge(games, on=["season", "week", "team"], how="left")
    out = out.merge(
        opp_rows[["defense", "position", "season", "week", "opponent_opp_allowed_prior"]].rename(
            columns={"defense": "opponent"}
        ),
        on=["opponent", "position", "season", "week"],
        how="left",
    )

    # --- the PREVIOUS week's depth chart only; the current week's is Class B ---
    depth = con.execute(
        "SELECT player_id, season, week + 1 AS week, MIN(depth_team) AS depth_team_prior "
        "FROM _depth GROUP BY 1, 2, 3"
    ).fetchdf()
    out = out.merge(depth, on=["player_id", "season", "week"], how="left")

    # --- Alpha's own 11 features, exactly as production reads them ---
    s0 = con.execute(
        f"SELECT player_id, season, week, {', '.join(S0)} FROM player_week_features"
    ).fetchdf()
    s0[list(S0)] = s0[list(S0)].fillna(0.0)
    out = out.merge(s0, on=["player_id", "season", "week"], how="left")

    # --- the no-fitting baselines, per target, from Class A series only ---
    for target, source in BASELINE_SOURCE.items():
        l1, l2, l3 = out[f"{source}_l1"], out[f"{source}_l2"], out[f"{source}_l3"]
        out[f"{target}__BL_LAST"] = l1
        out[f"{target}__BL_MEAN3"] = pd.concat([l1, l2, l3], axis=1).mean(axis=1, skipna=True)
        out[f"{target}__BL_WMEAN3"] = _weighted(l1, l2, l3)
        prior_23 = pd.concat([l2, l3], axis=1).mean(axis=1, skipna=True)
        out[f"{target}__BL_TREND"] = out[f"{target}__BL_MEAN3"] + 0.5 * (l1 - prior_23)

    out = out.sort_values(["season", "week", "position", "player_id"], kind="mergesort")
    return out.reset_index(drop=True)


def _weighted(l1: pd.Series, l2: pd.Series, l3: pd.Series) -> pd.Series:
    """BL_WMEAN3: 0.5/0.3/0.2 on the last three appearances, renormalised over those present."""
    w1, w2, w3 = WMEAN3_WEIGHTS
    num = l1.fillna(0) * w1 + l2.fillna(0) * w2 + l3.fillna(0) * w3
    den = l1.notna() * w1 + l2.notna() * w2 + l3.notna() * w3
    return (num / den).where(den > 0)


def feature_columns(model: str) -> list[str]:
    """The exact predictor list for each pre-registered forecast (§6.2)."""
    if model == "M_S0":
        return list(S0)
    if model in ("M_NEW", "M_CB"):
        return list(S0) + list(NEW)
    if model == "M_RED":
        return list(S0) + list(REDUNDANT)
    if model == "M_B":
        return list(S0) + list(NEW) + list(CLASS_B)
    raise ValueError(f"unknown forecast model {model!r}")


FORECAST_MODELS: tuple[str, ...] = ("M_S0", "M_NEW", "M_RED", "M_CB", "M_B")
BASELINES: tuple[str, ...] = ("BL_LAST", "BL_MEAN3", "BL_WMEAN3", "BL_TREND", "BL_COMBO")
#: Columns BL_COMBO uses besides the four baselines of its own target (pre-registration §6.1).
COMBO_CONTEXT: tuple[str, ...] = ("snap_pct_last1", "weeks_since_last_game", "games_played_prior")
RIDGE_ALPHA = 1.0
CATBOOST_KWARGS: dict = {
    "iterations": 200,
    "depth": 4,
    "learning_rate": 0.05,
    "verbose": False,
    "random_seed": 42,
    "loss_function": "RMSE",
}


# ---------------------------------------------------------------------------------------
# Walk-forward forecasts. Refit once per season on [2015, S-1], exactly as Alpha trains.
# ---------------------------------------------------------------------------------------

MIN_TRAIN_SEASON = 2015


def _design(train: pd.DataFrame, pred: pd.DataFrame, cols: list[str]):
    """Median-impute non-S0 columns from the TRAINING fold, with a missing indicator each.

    S0 arrives already zero-filled, exactly as production reads it. Everything else is imputed
    from the training fold only -- never from the rows being predicted -- and each imputed column
    gets an indicator, so "missing" stays distinguishable from "typical". Zero-filling here would
    invent information: a missing prior-week depth chart is not depth 0."""
    x_tr = pd.DataFrame(index=train.index)
    x_pr = pd.DataFrame(index=pred.index)
    for c in cols:
        if c in S0:
            x_tr[c] = train[c].astype(float)
            x_pr[c] = pred[c].astype(float)
            continue
        med = train[c].median(skipna=True)
        med = 0.0 if pd.isna(med) else float(med)
        x_tr[c] = train[c].astype(float).fillna(med)
        x_pr[c] = pred[c].astype(float).fillna(med)
        if train[c].isna().any() or pred[c].isna().any():
            x_tr[f"{c}__missing"] = train[c].isna().astype(float)
            x_pr[f"{c}__missing"] = pred[c].isna().astype(float)
    return x_tr, x_pr


def _ridge(x_tr: pd.DataFrame, y: pd.Series, x_pr: pd.DataFrame):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(x_tr.to_numpy())
    model = Ridge(alpha=RIDGE_ALPHA).fit(scaler.transform(x_tr.to_numpy()), y.to_numpy())
    return model.predict(scaler.transform(x_pr.to_numpy()))


def walk_forward(
    panel: pd.DataFrame,
    position: str,
    target: str,
    method: str,
    seasons: tuple[int, ...],
) -> pd.Series:
    """Out-of-sample forecasts of `target` for every `position` row in `seasons`.

    `method` is a forecast model (`M_*`) or a baseline (`BL_*`). A baseline has no fitted part
    except `BL_COMBO`; a baseline that is undefined for a row (a player's debut has no "last game")
    falls back to the training window's median of the target, so every player can be ranked and no
    fallback ever reads the season being predicted."""
    ycol = TARGETS[target]
    pos = panel[panel["position"] == position]
    out = pd.Series(index=pos.index, dtype=float)

    for season in seasons:
        train = pos[(pos["season"] >= MIN_TRAIN_SEASON) & (pos["season"] < season)]
        train = train[train[ycol].notna()]
        pred = pos[pos["season"] == season]
        if pred.empty or train.empty:
            continue
        fallback = float(train[ycol].median())

        if method in ("BL_LAST", "BL_MEAN3", "BL_WMEAN3", "BL_TREND"):
            out.loc[pred.index] = pred[f"{target}__{method}"].astype(float).fillna(fallback)
            continue

        if method == "BL_COMBO":
            cols = [f"{target}__{b}" for b in ("BL_LAST", "BL_MEAN3", "BL_WMEAN3", "BL_TREND")]
            cols += list(COMBO_CONTEXT)
        else:
            cols = feature_columns(method)

        if method == "M_CB":
            from catboost import CatBoostRegressor

            model = CatBoostRegressor(**CATBOOST_KWARGS)
            model.fit(train[cols].astype(float).to_numpy(), train[ycol].to_numpy())
            out.loc[pred.index] = model.predict(pred[cols].astype(float).to_numpy())
            continue

        x_tr, x_pr = _design(train, pred, cols)
        out.loc[pred.index] = _ridge(x_tr, train[ycol].astype(float), x_pr)
    return out
