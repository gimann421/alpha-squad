# Midseason ROS QB trade model (D116)

**Status: implemented, backtested on every verified historical snapshot, and wired into the
CLI. Read §0 and §12 before acting on any number in this file.** Every figure below was produced by
`alpha-squad ros backtest` (full generated tables: `docs/ROS_QB_BACKTEST_RESULTS.md`, regenerated into `reports/ros/RESULTS.md` by that command)
or by `alpha-squad ros board` / `ros trade`; nothing was typed in by hand except where marked
*arithmetic*. Results correspond to the working tree on top of commit `e02fcf7`.

## 0. Bottom line

1. **Published research vs. this repository's own experiments are kept separate.** Nothing in the
   FantasyPros/nflverse/DynastyProcess documentation measures decision accuracy; every accuracy
   number here comes from the repo's own backtest on **four test seasons (2022-2025), 20 snapshots,
   720 QB-snapshots per model**. That is a small sample: the intervals are wide and several
   conclusions below are *directional*, not established.
2. **FantasyPros ROS ECR is a good rough sorter and a poor tie-breaker.** Over the top-36 QBs its
   rank correlation with realized ROS points is 0.61 [0.53, 0.67]; it ranks QBs 1-6 vs the rest
   well (top-6 pair accuracy 0.68) and is right 74% of the time when two QBs are 12+ ranks apart.
   Between QBs ranked 4-15 or 8-20 it is **a coin flip: 0.50 [0.46, 0.55] and 0.52 [0.47, 0.57]
   pairwise accuracy** — and a coin flip at ranks that differ by 3 or fewer (50-54%).
3. **A parameter-free statistic beat the published order for mid-tier QBs.** "Season-to-date
   points per team game x games left" (`S2D`, missed games count as zeros) picked the better of
   two QB4-15 / QB8-20 QBs 0.62 [0.56, 0.68] / 0.64 [0.62, 0.67] of the time: **+0.12 [+0.07, +0.17]
   and +0.13 [+0.07, +0.19] over the ECR order**, better in all four seasons in both bands. But it
   is badly calibrated in *magnitude* (over-predicts totals by 14.5 points, RMSE 58 vs ECR's 51),
   and a tiny truncated forward check on 2026 pointed the other way (§9). I rate this "likely real,
   not proven".
4. **The model that makes the best *trades* is not the one that wins pairwise comparisons.**
   On the primary criterion — realized lineup points from market-priced QB swaps in synthetic
   10-team leagues (§7) — the ridge `D_usage` model (two-part: points per game *played* x expected
   availability, built only from information available at the snapshot, no ECR input) gained
   **+25.9 [-2.0, +55.1] lineup points per team-snapshot (about +2.9/game)**, i.e. **+25.0 [+7.8,
   +45.7] over an ECR-valued manager and +26.2 [+8.1, +45.3] over the S2D manager** (paired
   intervals exclude zero; positive vs ECR in 4 of 4 seasons). Of the executed trades, 71% improved
   the realized lineup, and the model's predicted gain (23.9) matched the realized gain (26.9).
   Scored with hindsight-picked lineups instead (a flattering bracket) the same comparison is
   +10.0 [-7.2, +27.0] — still the best model, but not distinguishable from zero.
5. **I recommend `D_usage` for ranking and pricing a QB acquisition, ECR as a sanity check, and
   the Monte Carlo engine as a conservative risk read** (§10). The recommendation is for the
   *method*; the magnitude (+26) is almost certainly optimistic because the winner was picked from
   17 candidates on the same four seasons.
6. **Not testable with the data that exists:** FantasyPros ROS *point projections* (Model B), any
   independent historical ROS projections, expert-level ranks, real league rosters or trade logs,
   and real prices. See §1.

## 1. What was inspected, and what already existed

Repository audit (searched, not assumed). Reused as-is: `league/context.py` (`LeagueContext`,
`FLEX_ELIGIBILITY`, slot normalisation), `league/roster.py` (`positional_capacity`,
`startable_slots`, `unfilled_dedicated_slots`), `league/opportunity_cost.py`
(`roster_aware_market_pick` — the synthetic drafts), `league/replacement.py` (the lineup allocator
the new optimiser is tested against), `sources/{nflverse,dynastyprocess,file_release,base}.py`
(download + sha256 + timestamped layout), `market/series.py` (the D56 ECR-series discipline — the
ROS page is its own `(ecr_type='rp', page_type='redraft-qb')` series), `config/settings.py`.

| Needed | Found in repo | Action |
|---|---|---|
| fantasy scoring from raw stats | only nflverse's precomputed `fantasy_points(_ppr)` columns (`features/player.py`) | **added** `ros/scoring.py`; asserted bit-identical to nflverse on 2020/2023/2025 (tests) |
| weekly lineup optimiser, bye/injury aware | `evaluation/weekly_objective.py` (scalar, pools flex slots) | **added** vectorised `ros/lineup.py`; tested against an exact assignment solver and against `compute_league_starters` |
| ROS ranking / projection | `/rankings/weekly`, `models/established/train.py` (preseason-anchored); no ROS ECR consumer | **added** the panel; production paths untouched |
| trade valuation | `league/trade.py` / `evaluation/trade_evaluation.py` — **dynasty** market value, age curve, picks; explicitly no redraft lineup value | **added** `ros/trade.py`; dynasty code unchanged and kept separate (picks/dynasty assets are not valued here) |
| schedule / playoff simulation | `models/simulation/correlated.py` (team-season environment sim); no remaining-schedule or H2H playoff model | **added** `ros.trade.simulate_outcomes` (scenario-based, §10) |
| player identity | `identity/` (DuckDB-backed canonical ids) | used the DynastyProcess ID map directly (FantasyPros id -> GSIS id; ambiguous ids dropped, **never name-matched**); 100% of ROS-QB rows mapped |
| uncertainty / calibration | conformal intervals for preseason projections (`models/uncertainty/`) | not reusable for ROS; the ROS Monte Carlo is validated separately (§8) |
| tests | 1533 passing at `e02fcf7` before any change | now 1605 passing, 44 network tests deselected as before, lint + format clean |

No production model, table, API route, or draft logic was changed. Edits to existing files: two
lines in `cli.py` (register the `ros` command group), one `per-file-ignores` line in
`pyproject.toml` (typer's `Option()` defaults), and docs.

## 2. Data actually obtained (all re-downloaded 2026-11-02; sha256 in `data/ros/inputs_manifest.json`)

| Dataset | Source / retrieval | What it is | Limits |
|---|---|---|---|
| **ROS-QB consensus ECR** | DynastyProcess `db_fpecr.parquet` (what `nflreadr::load_ff_rankings` reads), page `/nfl/rankings/ros-qb.php` (`ecr_type=rp`, `page_type=redraft-qb`; pre-2020-10-16 label `ros-qb`) | **Genuinely ROS, weekly, preserved as scraped** — each `scrape_date` has its own full board; 2019-12-27, then weekly 2020-09-10 -> 2026-10-30 (2021-2025 complete) | rank/average-rank/sd/best/worst only. **No point projections, no per-expert ranks, no scrape time (date only).** Scrapes are Fridays from 2021 (Tuesday 5 PM is not available); 2020 scrapes are Thursdays = game days, so only one 2020 week-6 snapshot is usable. No ROS history before 2019-12. |
| All-position ROS board | same file, `/nfl/rankings/ros-ppr-overall.php` | one overall board incl. QB/RB/WR/TE (market *prices*) | same |
| Weekly stat lines | nflverse `stats_player_week` 2019-2026 | passing/rushing/receiving/fumbles, sacks, EPA, CPOE | scoring recomputed (`ros/scoring.py`) |
| Play-by-play | nflverse `pbp` 2020-2026 | red-zone/goal-line usage, scrambles vs designed runs, team plays/pass rate/EPA | as-of filtered per snapshot |
| Injuries | nflverse `injuries` | QB report status | `date_modified` missing in some seasons -> only prior-week reports used there |
| Schedule (incl. unplayed) | `nflverse/nfldata` `games.csv` via new `sources/nfldata.py` (not in `all_adapters`) | every game's date, bye weeks, remaining games | its closing betting lines are never read (would leak) |
| ID map | DynastyProcess `db_playerids.csv` | FantasyPros id -> GSIS id | |
| FantasyPros live API | existing `sources/fantasypros.py` key | **correction to D38:** `type=ROS` consensus IS now served (6 experts, last updated 10/28) and weekly point projections exist for future weeks — **but only the top 10 players per request, no pagination, free tier, no history** | shown for reference only; never in a backtest |

Not found anywhere reachable: historical FantasyPros ROS point projections, independent
historical ROS projections, expert-level ranks, KeepTradeCut/ESPN history. **Model B and the
"multiple independent projection sources" question are therefore untested — not failed.**
Nothing was substituted for them (no current or retrospective rankings were used as history).

Licensing: public GitHub-hosted community datasets (nflverse, DynastyProcess) plus FantasyPros'
free API under this account's key; nothing under `data/`, `reports/`, or `models/` is committed.

## 3. Experiment definition (fixed before inspecting outcomes)

* **Snapshot** = one archived ROS-QB scrape. One per (season, NFL week 3-13), chosen as the
  latest scrape after the previous week's last game and before this week's last game that does
  not fall on a game day. **Evaluation weeks 6-10** (the brief's Weeks 6-10); weeks 3-13 of
  *earlier* seasons are additionally used for training. 60 snapshots built (2020 week 6; 2021-2025
  all but 2023-w12, 2024-w3, 2025-w13; 2026 partial).
* **Timing contract** (`ros/snapshots.py`, leakage-tested): games with `gameday < scrape_date` are
  PAST (features), `> scrape_date` are FUTURE (target), a game *on* the scrape date is excluded from
  both. A Friday scrape therefore treats Thursday night as known and the weekend as unknown.
* **Target** = the QB's fantasy points in every future regular-season game through **week 17** (the
  standard championship week), a missed game = 0, byes respected (`n_remaining` = games the
  *team* still has). Per-game rate `y_rate = total / n_remaining`. Scoring: full PPR, 4-pt passing
  TD, -2 INT (`ScoringRules.nflverse_ppr()`, any other format via `ScoringRules.from_league`).
* **Population** = QBs inside the published top 36 of the consensus (identical for every model).
* **Splits** = chronological, season-level walk-forward: test season T is predicted by models fitted
  on seasons `< T` only (2022: 2 training seasons ... 2025: 5). Imputation medians, scaling, ridge
  penalty (leave-one-season-out inside the training seasons), the rank->points curve, blend weights
  and the pairwise-probability calibrator are all fitted without the test season
  (`tests/leakage/test_ros_leakage.py` proves it by corrupting the test season and the future).
* **Independent units**: seasons. Snapshots within a season share ~all remaining games; the
  design effect puts the 20 snapshots at an effective ~5-7 independent ones. Intervals are
  4000-draw **season-and-snapshot block bootstraps** (resample seasons, then snapshots within
  season); with four seasons they are rough.
* **Prespecified constants**: tie = realized totals within 0.5 points/game (~4.5 points); decision
  windows QB1-6 / QB4-15 / QB8-20; "similar" = ECR gap <= 2 ranks inside the top 24; large mistake =
  40+ points of regret.

Field definitions for every column of `data/ros/qb_ros_panel.parquet` are in the docstrings of
`ros/snapshots.py::build_snapshot_rows` and `ros/models.py` (feature groups). Provenance (source
file, capture date, sha256) is in `data/ros/inputs_manifest.json`; the scoring configuration is
hashed into `scoring_hash` on every row.

## 4. Models

| Name | What it uses | Notes |
|---|---|---|
| `ECR_order` | published order | ordinal metrics only |
| `A_ecr`, `A_iso` | ECR -> points/game curve fitted on earlier seasons (ridge on log-rank + rank / isotonic) | Model A |
| *(B)* | FantasyPros ROS projections | **not testable** |
| `S2D` | season-to-date points per team game x games left | parameter-free baseline |
| `C_prod`, `C_recent` | season-to-date + prior season + availability (+ last-1/3/5 games) | Model C; tests recency |
| `D_usage`, `D_gbm`, `D_usage_1p` | + passing/rushing/red-zone usage, team environment, remaining-opponent QB points allowed, injury history; two-part ridge (points/game played x availability), shallow GBM, single-part ridge | Model D; no ECR input |
| `E_stack`, `E_full`, `E_blend`, `E_avg` | ECR + production (+ usage); ridge; fitted vs equal blend of `A_ecr` and `D_usage` | Model E |
| `S2D_play`\*, `S2D_cal`\*, `E_ecr_s2d`\*, `E_ecr_s2d_w`\*, `E_ecr_s2d_cal`\* | added **after** seeing that S2D led the pairwise tables | exploratory; flagged `*` everywhere |
| Model F (`ros/lineup.py`, `ros/trade.py`, `ros/rosterbench.py`) | any of the above turned into weekly optimal-lineup value vs. replacement | §7 |

## 5. Point and rank accuracy

| model | MAE (pts, ~9-game total) | RMSE | mean error | Spearman | top-12 hit | top-24 hit |
|---|---|---|---|---|---|---|
| `A_ecr` | **41.1** [37.4, 45.0] | **51.2** [46.8, 55.7] | +0.7 | 0.605 [0.534, 0.674] | 0.575 | 0.825 |
| `S2D` | 45.8 | 58.4 | **+14.5** [4.2, 23.0] | 0.602 | **0.671** [0.633, 0.713] | 0.785 |
| `D_usage` | 45.7 | 55.2 | -3.3 | 0.522 | 0.567 | 0.777 |
| `E_full` | 42.9 | 52.7 | -1.3 | 0.578 | 0.588 | 0.783 |
| `E_avg` | 42.2 | 51.5 | -1.3 | 0.605 | 0.604 | 0.806 |

* ECR is the most *accurate in points* and well calibrated overall (pooled calibration slope
  ~1.0 for `A_ecr`); by tier its slope is 0.96 (QB1-6), **0.60 (QB7-12)**, 0.94, 1.32. Error shrinks
  through the season (RMSE 62.6 at week 6 -> 41.8 at week 10 as the horizon shortens) and is
  **larger for QBs who run (>=5 carries/game): RMSE 65 vs 47 for pocket passers**.
* `S2D` ranks the top 12 best (67% hit) but is not a points forecast.
* Rank metrics reward getting the *order of the whole list* right; a manager faces one comparison
  at a time, which is why §6 matters more.

## 6. Pairwise decisions, probabilities, and regret

Pairwise accuracy (ties = 0.5), mean over 20 snapshots, 95% block-bootstrap interval:

| model | top-6 pairs | QB4-15 | QB8-20 | ECR-similar |
|---|---|---|---|---|
| `ECR_order` | 0.683 [0.587, 0.772] | 0.498 [0.456, 0.545] | 0.516 [0.466, 0.568] | 0.503 |
| `A_ecr` | 0.563 | 0.519 | 0.540 | 0.538 |
| `S2D` | 0.678 | **0.618** [0.561, 0.681] | **0.643** [0.620, 0.670] | 0.634 |
| `D_usage` | 0.698 | 0.572 [0.480, 0.685] | 0.550 [0.487, 0.611] | 0.545 |
| `E_full` | 0.685 | 0.583 | 0.564 | 0.568 |
| `E_ecr_s2d`\* | 0.682 | 0.609 [0.521, 0.700] | 0.628 [0.591, 0.663] | 0.622 |

Paired differences (same resamples): `S2D` minus ECR order **+0.120 [+0.066, +0.171] (QB4-15)** and
**+0.127 [+0.071, +0.185] (QB8-20)**; `D_usage` minus ECR +0.074 [-0.007, +0.159] / +0.034 [-0.073,
+0.113]; `D_usage` minus `S2D` -0.046 [-0.113, +0.019] / **-0.093 [-0.165, -0.024]**. Per season,
QB8-20: ECR order 0.586/0.462/0.505/0.513 vs `S2D` 0.645/0.665/0.640/0.622 (2022-25). The top-6
band is the one place the published order does well.

*Does a model's stated gap mean anything?* Accuracy rises with the model's own predicted gap
(`A_ecr`: 46% for gaps <5 pts, 71% for 30+; `S2D`: 55% -> 75%), so large gaps are informative and
small ones are noise.

*Probabilities.* Converting score gaps to P(QB_i beats QB_j) with a per-season logistic map fitted
on out-of-fold training predictions gives Brier scores of 0.26-0.29 (coin flip = 0.25) and
unreliable high-confidence bins: for `D_usage`, predictions of 0.80-0.90 were right 58% of the
time; for `A_ecr`, 0.80-0.90 was right 42%. **Do not read any model's pairwise probability above
~0.6 as meaningful.**

*Decision regret* (pick one QB per window; regret = best realized in window minus the pick;
20 decisions per cell, hindsight diagnostic):

| model | QB1-6 mean / median / p90 | QB4-15 mean / median / p90 | QB8-20 mean / median / p90 |
|---|---|---|---|
| `ECR_order` | 16.6 / 5.8 / 49.8 | 47.6 / 21.6 / 122.3 | 69.0 / 64.7 / 97.7 |
| `S2D` | 43.5 / 23.3 / 113.4 | 57.0 / 52.3 / 108.7 | 41.7 / 24.5 / 82.5 |
| `D_usage` | 9.9 / 0.0 / 19.2 | 45.2 / 26.4 / 99.2 | 42.6 / 39.9 / 85.9 |
| `E_full` | 10.3 / 0.0 / 16.7 | 41.4 / 23.8 / 99.2 | 42.1 / 33.3 / 85.9 |

Versus simply taking the ECR-top QB in the QB8-20 window: `D_usage` +27.7 [-2.8, +58.1] points,
`E_full` +28.1 [-3.1, +59.1], `S2D` +28.5 [+2.9, +53.4]; in the QB4-15 window **no** model's advantage
over the ECR-top pick exceeds 7 points and every interval straddles zero. **In the two wider windows
the model's pick is not the hindsight-best QB in 70-95% of decisions, and when it misses the typical
miss is 40-90 points** — this is a hard prediction problem and no model solves it.

## 7. Roster-level decision utility (primary selection criterion)

`ros/rosterbench.py`: ten synthetic teams snake-draft the archived `ros-ppr-overall` board
(14 rounds, repo's roster-aware drafter, positional ceilings from the lineup, K/DEF removed since
a QB trade does not touch them). A candidate is a one-for-one swap of any of the manager's players
for a QB rostered by another team, **accepted only if the market would accept it** (the manager
gives up a player ranked at least as high on the consensus board as the QB received). A model
executes its single best predicted candidate if the predicted gain exceeds a threshold; otherwise
holds (score 0). Realized value = lineup points actually scored (starters picked weekly **by the
model's own forecasts among players who played**, then scored with what they scored). Every model
values everyone except QBs the same way, so the QB model is the only thing that varies. 200
decisions per model (10 teams x 20 snapshots), clustered in 4 seasons.

Realized lineup points per team-snapshot (~9-game horizon), execute if predicted gain > 0:

| model | mean [95%] | vs `A_ecr` | vs `S2D` | hindsight-lineup scoring | hindsight-best-trade gap |
|---|---|---|---|---|---|
| `A_ecr` | 1.0 [-13.5, 17.0] | | +1.2 | -2.2 [-11.4, 8.0] | 40.1 |
| `S2D` | -0.2 [-18.6, 18.2] | -1.2 | | -5.4 | 41.3 |
| `C_recent` | 15.3 [-5.6, 34.6] | +14.3 [+2.1, +27.1] | +15.5 [+0.1, +29.6] | 1.7 | 25.8 |
| **`D_usage`** | **25.9 [-2.0, 55.1]** | **+25.0 [+7.8, +45.7]** | **+26.2 [+8.1, +45.3]** | **10.0 [-7.2, 27.0]** | **15.1** |
| `E_full` | 19.6 [-14.2, 52.0] | +18.6 [-3.0, +42.4] | +19.8 [-4.1, +42.5] | 9.8 | 21.5 |
| `E_avg` | 20.5 [-9.5, 50.8] | +19.5 [+2.8, +39.6] | +20.7 [+3.7, +40.1] | 9.2 | 20.6 |
| `D_usage_1p`\* | 15.1 | +14.2 [-5.0, +40.9] | | 4.7 | 25.9 |
| `S2D_cal`\* | 2.2 | +1.2 | +2.4 | -1.5 | 38.9 |
| `E_ecr_s2d`\* | 4.3 | +3.3 | +4.5 | -1.6 | 36.8 |

By season (raw, `D_usage`): **+62.9 (2022), -4.3 (2023), +43.7 (2024), +1.4 (2025)**; `A_ecr`:
+8.4, -14.2, +21.1, -11.5. So `D_usage` beat the ECR-valued manager in all four seasons
(+54.5, +9.9, +22.6, +12.9), but its own absolute result is large in two seasons and about zero in
two. With execution thresholds of 10 and 20 predicted points the picture is the same
(`D_usage` 24.9 and 20.7; +22.0 [+4.1, +44.0] and +18.9 [+1.3, +44.5] vs ECR). Behaviour of
`D_usage` at threshold 0: trades in 91.5% of team-snapshots, 71% of executed trades improve the
lineup, mean predicted gain 23.9 vs realized 26.9. `A_ecr` predicted +17.5 and realized +0.8:
**the ECR-valued model's trades looked good to itself and were not**. `S2D` is mis-scaled
(predicts +34.8, realizes -0.6) — good ordering, bad magnitudes, ruinous when magnitudes set the
price.

**How much to believe it.** (1) Four seasons; (2) the model was chosen as the maximum of ~17 on
these same seasons (winner's curse); the three pre-specified Model D/E candidates were fixed
before any result existed, the `*` models and all ablations were not; (3) the leagues are
synthetic and prices are the consensus board, not real negotiation; (4) the departing player is
valued at market. The *direction* — production-based, availability-aware, calibrated forecasts
make better swap decisions than ECR-valued ones — is supported; the size is not.

## 8. Which information carries the signal (drop-one-group ablations, exploratory)

Walk-forward means over the 20 snapshots (`D_usage` base: RMSE 55.2, QB4-15 pairs 0.572):
dropping **PRIOR** (prior-season production) -> RMSE 54.7, pairs 0.628; dropping **USAGE** -> RMSE
54.0; dropping **CONTEXT** -> RMSE 55.7 / pairs 0.554 (the block helps); dropping **RECENT** -> RMSE 55.4;
dropping **SEASON** (season-to-date block) -> RMSE 55.4 / pairs 0.560; **TEAMENV** helps (removal
raises RMSE 55.2 -> 55.7), **SCHED** and **INJ** change almost nothing, **RZRUSH** removal costs 0.02
in QB4-15 pairs (and lowers RMSE slightly).
For `E_full` (adds ECR): removing **ECR** costs 2.5 RMSE (52.7 -> 55.2) and 0.056 in Spearman
(0.578 -> 0.522) — **ECR is the single most valuable *level* signal**; removing **USAGE** *improves*
RMSE (52.7 -> 51.4) and Spearman (0.578 -> 0.606). Reading: availability and season-to-date
production decide the order; ECR anchors the level; detailed usage features add parameters faster
than the four training seasons can pay for them. The recency question: last-1/3/5-game form
added nothing reliable (`C_recent` vs `C_prod`: QB4-15 pairs 0.544 vs 0.524, intervals overlap
completely).
Coefficients (standardized, `D_usage`): the largest availability driver is the share of team games
the QB has played (`apps_share`); the largest rate drivers are prior-season PPG, red-zone/rushing
usage, and team EPA/play. Treat as description, not causation.

## 9. When to trust ECR (pairs in ranks 1-24, ties removed; n = 5,277 decisive pairs)

| situation | ECR right | n |
|---|---|---|
| ECR gap <= 1 rank | 50.5% | 325 |
| gap 1-3 | 54.4% | 778 |
| gap 3-6 | 57.8% | 1,065 |
| gap 6-12 | 63.6% | 1,735 |
| gap 12+ | **74.2%** | 1,343 |
| better-ranked QB is QB1-6 / QB7-12 / QB13-24 | 67.8% / 58.1% / 59.7% | 2,366 / 1,645 / 1,266 |
| `S2D` agrees with ECR / disagrees | **71.8% / 36.7%** | 3,929 / 1,348 |
| `S2D` disagrees by >= 1.5 points/game | ECR right only **33%** (`S2D` 67%) | 919 |

**Trust ECR** for the top-6 vs the field, and whenever two QBs are 6+ ranks apart *and* production
agrees. **Discount ECR** within ~3 ranks, in the middle of the board, and — most importantly —
when season-to-date production (including games missed) disagrees by more than ~1.5 points/game.
These strata were defined from snapshot information only, but they were explored after seeing the
data: treat the percentages as descriptions of 4 seasons.

A **forward check on the season in progress (2026)** — models frozen on 2020-2025, horizon truncated
to the games already played, three overlapping snapshots, so roughly one small independent look —
went the other way for the pairwise question (`A_ecr` 0.68 / 0.66 on QB4-15 / QB8-20, `S2D` 0.63 /
0.61, `D_usage` 0.62 / 0.61). It is too small to overturn four seasons, and equally too small to
confirm them; it is a reason to keep S2D's pairwise edge in the "likely, not proven" column.

## 10. The trade decision engine

`alpha-squad ros board` (roster-independent) and `alpha-squad ros trade <config.yaml>` (a concrete
roster). Architecture: `ros/live.py` (fetch, forecast, packaging) -> `ros/trade.py` (simulation,
lineups, classification) -> `ros/lineup.py`. Inputs: league config (the repo's `LeagueContext`
YAML; default = the 10-team 1-QB PPR target league, which sets scoring, lineup slots, bench size,
replacement depth), roster / target / outgoing-package GSIS ids (`ros find "name"` looks ids up —
names are never used as keys), optional actual waiver QBs, optional standings. Example:
`docs/examples/ros_trade_example.yaml` (an **illustrative** roster, not yours).

For each (target QB, outgoing package) the engine reports: current ROS ECR rank + scrape date and
age; FantasyPros' own ROS projection **only where it exists** (top-10 free tier) else "unavailable"
with the reason; the model's ROS points with p10/p90; net lineup value = E[best weekly lineups
after] - E[before] over the remaining schedule (byes, injuries, correlated teammates, waiver
replacement at the league-derived rostered depth, lineups chosen by forecast not hindsight);
P(improves); p05-p95 of the gain; acquire-for-nothing value (the price ceiling) and a
conservative ceiling (its 25th percentile); playoff and championship deltas; sensitivity runs
(injury risk x1.5, target forecast -1/+1 residual SD); and a six-way label with explicit rules
(`ros.trade.classify`): *Strongly favorable* needs mean >= +20 points, P(improves) >= 0.85 and a
positive worst sensitivity; *Favorable* >= +8 and >= 0.65; mirrored for unfavorable; a label whose
sensitivity run flips sign is downgraded; stale (>8 days) ECR or missing inputs -> *Insufficient
evidence*.

**Validation of the simulation (§ backtest 9 of `RESULTS.md`).** Season totals: the model's nominal
50/80/90% intervals covered 41.7% / 73.5% / 84.7% of realized outcomes (too narrow; mean bias
-0.2 pts, left tail heavy — benched/injured QBs). Widening the model-uncertainty term by
kappa = 1.25 (rule fixed on 2022-23: smallest kappa reaching 80% coverage; judged on 2024-25) gives
78.9% overall (80.0% on 2022-23, 77.8% on 2024-25); the live engine uses kappa = 1.25. Trade
gains: see the next paragraph.

**Trade gains (183 trades `D_usage` executed in the roster backtest, re-simulated with the
production engine at kappa = 1.25).** The engine is **conservative, not calibrated**: stated mean
gain **+8.2** points vs **+28.3** realized; stated average P(improves) **0.53** vs **71.6%
observed** (Brier 0.235 vs 0.201 for a constant base rate); the realized gain fell inside the
stated central 50% / 80% interval 66.7% / 92.9% of the time (intervals a bit too wide). It tracked
the *season-to-season pattern* (stated +14.5/+9.2/+7.4/+0.9 vs realized +65.6/-4.7/+45.5/+1.6 for
2022-25) but not its size. It is lower than the deterministic backtest number (23.9) because the
engine prices things that number ignores — injury insurance (a displaced QB is still useful when
the new one is out), lineups chosen by forecast, and forecast error — and realized results sat above
both. **Practical reading: treat P(improves) as a floor and the label thresholds as demanding; no
backtest trade reached a stated P >= 0.7.** I did not "fix" this by rescaling to match the backtest:
the observed uplift rests on four seasons and is partly the winner's curse of §7.

**Playoff and championship probability.** These need standings, the matchup schedule and rivals'
strength, none of which the repository can know. Without them the engine reports scenario numbers
(rivals equal to your own average lineup, random pairings, 6-team bracket) flagged
`assumption_based=True`; with `standings:` supplied they are conditional on that input. **They are
not validated against history** — the backtest has no real league standings — and should be read
as "direction and rough size", never as a precise probability.

## 11. Live board and example evaluation (2026-11-02, before Week 9)

Data stamps (from `ros board`, written to `reports/ros/live_board_2026-11-02.json`): ECR archive
captured 2026-11-02, newest ROS-QB scrape **2026-10-30** (3 days old), nflverse 2026 stats through
Week 8 (all games played before today's Monday-night game; that game is treated as unplayed),
schedule from `nfldata` captured the same day; model `D_usage`, per-game forecast SD 6.0 points
(4.8 measured x kappa 1.25); FantasyPros live API reached (top-10-per-request tier) but **no QB had a
complete set of remaining-week projections, so its ROS projection is "unavailable" for all 36**.
The ECR here is the DynastyProcess mirror's Friday scrape, not necessarily FantasyPros'
fresher Wednesday update (the live API reports its ROS board last updated 10/28 with 6 experts).

Roster-independent board — model ROS points over the remaining **8-9 games** (Weeks 9-17), with
the 10th-90th percentile of the simulated total, beside what ECR alone implies and what
season-to-date production alone implies:

| ECR | QB | team | model ROS | p10-p90 | ECR-implied | S2D | `E_full` | avail. | games missed so far |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Josh Allen | BUF | 179.6 | 94-262 | 177.1 | 241.5 | 189.7 | 0.9 | 0 |
| 2 | Drake Maye | NE | 137.8 | 62-212 | 149.5 | 160.9 | 150.7 | 0.9 | 0 |
| 3 | Brock Purdy | SF | 156.2 | 72-241 | 165.6 | 187.7 | 175.7 | 0.9 | 0 |
| 4 | Lamar Jackson | BAL | **87.8** | 22-153 | 144.9 | 79.1 | 116.7 | **0.7** | **3** |
| 5 | Joe Burrow | CIN | 156.0 | 77-236 | 161.8 | 218.1 | 168.6 | 1.0 | 0 |
| 6 | Trevor Lawrence | JAX | 151.4 | 67-233 | 156.1 | 171.8 | 160.1 | 0.9 | 0 |
| 7 | Caleb Williams | CHI | 128.3 | 44-211 | 156.1 | 107.5 | 145.2 | 0.8 | 3 |
| 8 | Jared Goff | DET | 148.3 | 65-230 | 154.9 | 182.6 | 161.8 | 0.9 | 0 |
| 9 | Dak Prescott | DAL | 130.9 | 56-204 | 129.3 | 147.9 | 134.7 | 0.9 | 0 |
| 10 | Patrick Mahomes II | KC | 146.6 | 64-230 | 139.8 | 161.4 | 150.6 | 0.9 | 0 |
| 11 | Jordan Love | GB | 104.1 | 32-177 | 124.3 | 148.8 | 113.0 | 0.8 | 0 |
| 12 | Matthew Stafford | LA | 118.5 | 46-191 | 118.7 | 131.6 | 119.5 | 0.9 | 0 |
| 13 | Jayden Daniels | WAS | 100.3 | 27-173 | 132.3 | 129.4 | 104.2 | 0.7 | 2 |

How to read it: where the three views agree (Allen, Burrow, Lawrence, Goff, Prescott, Stafford)
the call is easy; where they split (Jackson at ECR #4 but 3 missed games, Williams, Daniels, Love,
Maye) the disagreement **is** the information — the model is discounting availability and
production that the Friday ECR has not (or not fully) priced. The spread inside a row (p10-p90
roughly +/-80 points) is larger than the gaps between most adjacent QBs, which is the honest
reason a mid-board QB-for-QB trade is a weak edge. Full 36-row board: `reports/ros/live_board_*.csv`.

**Example trade evaluation (an *illustrative* roster, `docs/examples/ros_trade_example.yaml`: Jordan
Love at QB; two to four RB/WR/TE at the ranks listed there. Not your roster — supply your own).**
Acquiring each target *for nothing* gives the price ceiling in lineup points:

| target | ECR | model ROS | net gain (acquire for nothing) | P(improves) | 5th-95th pct | label | scenario: playoff / title pp\* |
|---|---|---|---|---|---|---|---|
| Brock Purdy | 3 | 156 | +36.2 | 0.70 | -77 to +155 | Favorable | +7.3 / +5.4 |
| Trevor Lawrence | 6 | 151 | +32.7 | 0.67 | -83 to +152 | Favorable | +6.0 / +4.0 |
| Joe Burrow | 5 | 156 | +26.8 | 0.64 | -99 to +151 | Approximately neutral | +6.4 / +4.3 |
| Jared Goff | 8 | 148 | +25.9 | 0.62 | -90 to +142 | Approximately neutral | +6.2 / +4.0 |
| Dak Prescott | 9 | 131 | +23.8 | 0.60 | -76 to +133 | Approximately neutral | +5.2 / +4.4 |

and with an outgoing player the *same* target changes sign with the asset: for Purdy, giving the
bench-level RB (rank 30) is +20.7 (P 0.6), giving the WR4 (rank 35) +17.2, giving the starting
RB1 (Derrick Henry) **-22.4** (P 0.4). That asymmetry — bench assets are nearly free, starters
are not — is the main practical output of the replacement-aware calculation. Every one of those
packages falls to "Approximately neutral" or worse under the *forecast minus one residual SD*
sensitivity (-10 to -14 points for the bench packages), so none clears the "positive in every
sensitivity" bar; in this illustrative case the engine does not call any priced trade
*Favorable*. \*Playoff/title deltas use a 4-win/10-team scenario with the rivals' scoring set equal to this
roster's own average (`assumption_based=True`); they are placeholders for the shape of the
output, not estimates.

## 12. Limitations (read these)

* **Sample.** Four test seasons / 20 snapshots / ~5-7 effective independent snapshots. No result
  here is "statistically established" in the strong sense; the block-bootstrap intervals are an
  honest guide to season-to-season variation, not exact coverage.
* **Researcher degrees of freedom.** The first-cut model list and metrics were fixed before results.
  After seeing the first pairwise table I added the two-part structure's `S2D_play` baseline, the
  calibrated/blended S2D variants, the ablations and the "when to trust ECR" strata. All four
  evaluation seasons were therefore inspected before the final tables; there is **no untouched
  hold-out** apart from the tiny 2026 forward check (which disagreed on the pairwise question).
* **No real prices or leagues.** Swaps are market-priced by the consensus board in synthetic leagues.
  Real trade acceptance, FAAB, keeper/dynasty value, and draft picks are out of scope (the
  repository's dynasty trade code is unchanged and separate).
* **Model B untested** (no historical ROS projections). If FantasyPros point projections exist
  historically behind a paid tier, `ros/snapshots.py` is the place to add them; nothing is imputed.
* **Friday scrapes**, not Tuesday 5 PM; a game on the scrape date is excluded from both sides.
* **Non-QB assets are valued at market** (ECR curve) for every model; K/DEF are excluded from the
  roster experiments and not modelled.
* **Schedule effects** (remaining-opponent QB points allowed) were included as a feature, show no
  measurable value (ablation), and are never applied as an adjustment.
* Not claimed: that any of this changes championship odds by a specific amount.

## 13. Reproduce

```bash
uv sync --extra dev
uv run alpha-squad ros ingest                      # download/locate raw inputs, write provenance manifest
uv run alpha-squad ros build-panel                 # leak-safe panels -> data/ros/
uv run alpha-squad ros backtest --n-boot 4000      # ~15 minutes -> reports/ros/RESULTS.md (+CSVs)
uv run alpha-squad ros board                       # live QB board (timestamped)
uv run alpha-squad ros trade my_trade.yaml         # a concrete decision
uv run pytest tests/unit/test_ros_*.py tests/leakage/test_ros_leakage.py tests/integration/test_ros_*.py
```
Makefile shortcuts: `make ros-backtest`, `make ros-board`. Outputs: `data/ros/` (panels, manifest,
`mc_calibration.json`), `reports/ros/` (everything else) — both gitignored and reproducible.

## 14. Final recommendation

1. **Best method: `D_usage`** — a two-part ridge (points per game *played* x expected availability)
   on season-to-date and prior production, usage and team environment, no ECR input — for ranking and
   pricing QB trades, because it won the primary criterion (realized lineup value of market-priced
   swaps) against both baselines and was positive in every season against ECR. It also has the
   best top-6/QB1 regret (9.9 vs 16.6 for ECR order).
2. **Improvement over baseline, honestly sized.** +25 lineup points per decision over the ECR-valued
   manager (+7.8 to +45.7), about 2.8 points per game; arithmetic: at a 22-point weekly score SD
   that is ~3.6 percentage points of single-game win probability *if the full amount is real* (and
   about half that if only half is). Statistically supported only
   directionally (interval excludes zero vs both baselines; absolute interval includes zero;
   four seasons).
3. **Most predictive information:** availability and season-to-date production; ECR contributes the
   level (points accuracy) but little ordering inside the middle of the board; detailed usage,
   schedule and recency features contributed nothing reliable.
4. **Trust ECR** for the top 6 and for gaps of 6+ ranks when production agrees; **discount it** within
   3 ranks, mid-board, and when production disagrees by 1.5+ points/game (then ~2/3 of the time the
   production side wins).
5. **To make an actual QB acquisition:** (a) `ros board`; (b) list 3-5 targets whose model ROS
   (not ECR rank) exceeds your QB's; (c) `ros trade` with your real roster, the real package you
   would give, and your real waiver QBs; (d) require label *Favorable* or better *and* a positive
   result in the injury-x1.5 and forecast-minus-1-sigma sensitivities; (e) treat the
   acquire-for-nothing value as the most you should pay in lineup points, and the conservative ceiling
   as what you can pay without a worse-than-even chance of regret; (f) pay with **bench** assets first
   — a bench player costs ~0 lineup points, a starter costs his full replacement gap; (g) never
   price a trade off a single QB-vs-QB ECR gap smaller than ~6 ranks.

### Layman's terms

Think of the expert ranking as a decent map for telling the very best quarterbacks from everyone
else — and a coin flip for choosing between two similar quarterbacks. In four seasons of history,
simply asking "who has been scoring more per game this year, counting the games they missed?" picked the
better quarterback more often than the ranking did, for the middle of the pack. The best results
came from a model that combines that with how healthy the player has been and how his team
plays, and it did well at the thing that matters — whether a trade actually raised your weekly
lineup score — roughly +25 points over a half-season versus trusting the rankings. But "four
seasons" means we cannot be sure: the real-world gain is probably smaller than +25, and individual
trades still lose about three times out of ten. Use the tool to avoid paying for tiny ranking gaps,
to spend bench players instead of starters, and to see how much your lineup really changes — not
as a promise that any particular trade wins.

### Suggested next steps (highest value first)

1. **Hold-out the future:** log every live `ros board`/`ros trade` run (timestamped files already
   written) and score them at the end of 2026 — the only truly untouched evidence available.
2. Obtain **historical FantasyPros ROS point projections** (paid tier / archive) to test Model B and
   a real projection-based blend; the panel schema has the place for it.
3. Replace the synthetic leagues with **real league rosters and trade logs** (Sleeper history) to
   test prices, acceptance and positional-need effects.
4. Re-fit the rate model on a longer history (the ECR archive begins late 2019; production-only
   models could use 2015+) and re-check the mid-board pairwise result.
5. Wire a **standings/schedule import** (Sleeper) so playoff and championship probabilities stop
   being scenario numbers, then validate them.
6. Value outgoing assets with the same production-aware forecasts (currently market ECR).
