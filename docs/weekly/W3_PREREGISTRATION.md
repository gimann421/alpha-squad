# W3 — Pre-registration: what can the existing Alpha weekly model already do?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any Alpha ranking metric has been
computed. At the time of writing, no Alpha weekly ranking result exists anywhere in this
repository — `weekly_projection_snapshot` is empty and `train established` has never been run
against this database.

Authority: `docs/weekly/W2_ECR_BENCHMARK_RESULTS.md` (the benchmark and the noise floor),
`docs/weekly/W2_PREREGISTRATION.md` (the frozen universe, scoring and metric suite),
`CLAUDE.md`. Decision record: `docs/DECISIONS.md` D111.

> **Nothing below may be changed after seeing a result without a dated amendment in this file
> stating what changed and why.** Same rule as W2's A1, D70 and D106.

---

## 1. The question

> **How much weekly ranking signal can Alpha recover from information available at the Friday
> cutoff, without ECR — and how does that compare with a simple season-to-date baseline and
> with FantasyPros ECR?**

W3 **evaluates the existing model**. It does not build, tune, retrain selectively, add
features to, or otherwise modify anything. If an improvement suggests itself, it is recorded
as a W4 candidate and **not tested here**.

---

## 2. The Alpha system under test — audited, frozen, unmodified

Audited against the repo at commit `12aa1f5` before this document was written. W1's description
was broadly right and incomplete; the corrections and additions are marked.

| | |
|---|---|
| module | `src/alpha_squad/models/established/` (M5) |
| entry point | `alpha-squad train established --season-start 2021 --season-end 2025 --min-train-season 2015` — **the unmodified CLI path** |
| model evaluated | **`ml_catboost`** = `CatBoostRegressor(iterations=200, depth=4, learning_rate=0.05, loss_function="MAE", random_seed=42)` |
| why that one | it is `WEEKLY_PROJECTION_BASE_MODEL` — the **only** model whose weekly predictions are persisted to `weekly_projection_snapshot`, and therefore the only one the product's `/rankings/weekly` endpoint can serve |
| other models fitted by the same run | `ml_ridge`, `ml_xgboost`, `ml_opportunity_only`, `ml_team_environment_only`, plus an averaging ensemble — all produce **season totals only**; none is persisted weekly, so none is a weekly ranking system |
| features | **11**, `FULL_FEATURES`: `games_played_prior`, `fp_ppr_avg_last3`, `fp_ppr_avg_season_to_date`, `targets_avg_last3`, `carries_avg_last3`, `receptions_avg_last3`, `target_share_avg_last3`, `snap_pct_avg_last3`, `team_plays_avg_last3`, `team_pass_rate_avg_last3`, `team_epa_avg_last3` |
| positions | **QB, RB, WR, TE only.** `POSITIONS` does not contain K or DST |
| target | `target_fantasy_points_ppr` — **Full PPR only** |
| training | per position, **walk-forward expanding window**: seasons `[2015, target_season − 1]`; a position-season with < 50 training rows is skipped |
| missing features | imputed to **0.0** (`load_position_week_data`) — existing behaviour, not changed |
| ranking construction | none exists in the model. W3 ranks by `predicted_points` descending, ties by `player_id` |
| FLEX construction | **none exists.** W3 pools the RB + WR + TE predictions into one board and ranks by predicted points — exactly as the brief specifies, with no separate FLEX model and no manual cross-position adjustment |
| ECR | **not reachable.** Verified two ways: no feature name is market-derived, and `player_week_features` physically contains only the 11 features + target + identity columns, so there is nothing else to read |

### 2.1 Two audit findings that change what W3 can measure

**(a) Alpha's prediction universe is defined by who played.** `player_week_features` is built
from `player_week_stats`, which has a row for `(player, season, week)` **only if the player
appeared in that game**. So the model can only emit a prediction for a player who played.

This does **not** contaminate the comparison — W2 already evaluates every system on the
*evaluable set* (ranked players who played), and all three systems are restricted to the same
players. But it is a **material product limitation** and is reported as a finding, not a
footnote: *the current Alpha weekly model cannot produce a real Friday board*, because on
Friday it does not yet know who will play. It can only score retrospectively. Building a
prediction row for every rostered player is infrastructure that does not exist.

**(b) The served product's evidence layer is excluded from W3, on leakage grounds.**
`GET /rankings/weekly` serves `weekly_projection_snapshot` adjusted by `projection_deltas`
(M9, bounded ±15%). That layer's `detect_injury_events` reads the nflverse injury file with
`WHERE i.week = ?` and **no `date_modified` filter**. nflverse stores one *final* row per
player-week, and measured across 2021–2024, **7.2%–9.8% of the `Out`/`Doubtful` rows it
consumes were last modified after Friday**; the 2025 file has **no `date_modified` column at
all**, so it cannot be filtered even in principle.

The W3 brief forbids post-cutoff injury information outright. W3 therefore evaluates
**`ml_catboost` alone**, and records the evidence layer's cutoff defect as a W4 candidate.
**This is a finding about the served product path, not a choice of convenience.**

---

## 3. The three systems

All three rank **the same players, in the same weeks, under the same scoring, with the same
cutoff**. Any player one system cannot rank is dropped from **all** systems for that cell, and
the loss is reported (§6).

### System A — season-to-date baseline (unchanged from W2)

`benchmark.py::rerank_board` over `_prior_ppg(mode="season_to_date")`: mean Full-PPR points per
game across **weeks < w of season S**. Inputs: `player_week_stats` only. Players with no prior
game in season *S* sort **last**; ties broken by `player_id`. No minimum-games rule, no
shrinkage, no position adjustment. Identical to W2's `B0_season_to_date_ppg` — **not** replaced
by a better baseline.

W2's second reference (`B1_prior_season_ppg`) is retained in the outputs for continuity but is
**not** a primary comparison here.

### System B — FantasyPros ECR (unchanged from W2)

The canonical **Friday** board: positional series for QB/RB/WR/TE, FLEX reconstructed from the
superflex board with QBs removed (validated in W1.1 at median top-10 overlap 0.80). Same
vintage, same exclusions, same identity resolution. **No methodology change.** W2's numbers are
re-run rather than quoted, so that every figure in W3 comes from one execution over one
universe.

### System C — Alpha without ECR

`ml_catboost` weekly predictions from the unmodified training path in §2. FLEX by pooling
RB/WR/TE predicted points.

---

## 4. Population, cutoff, scoring, universe

**Unchanged from W2.** 2021–2025; the **79** covered REG weeks; **Full PPR** primary
(`points(r) = fantasy_points_ppr − (1−r)·receptions`); **Friday** cutoff; already-played
(Thursday-night) players removed from the universe *before* ranking, keyed on nflverse `games`
and the player's real week-*w* team, never on a board's team column.

**K and DST are out of scope for the Alpha comparison** — the model does not produce them.
W2's K/DST ECR results stand; W3 does not retrofit an Alpha K/DST ranking, and does not report
a three-way comparison where only two systems exist.

**The universe is ECR-defined**, then intersected with "played" and "Alpha has a prediction".
Ranking the union instead would make the comparison unpaired and would ask a different
question. Coverage of that universe by each system is reported in §6.

**Boards evaluated:** FLEX, QB, RB, WR, TE. Depths **10, 25, 50** where the cell supports them
(a depth is `None`, not computed on a short list). Invalid-cell rule unchanged: fewer than
**10** evaluable players ⇒ the cell is excluded and counted.

---

## 5. Metrics — reused verbatim from W2, nothing added

`evaluation/weekly/metrics.py`, already frozen and unit-tested with hand-computed
expectations. **No new metric is introduced because Alpha is now in the comparison.**

**Primary** (declared before results):
- **M1 Spearman ρ** — overall rank-order quality
- **M6 `capture@k`, k ∈ {10, 25, 50}** — realized points captured by the predicted top-k

**Supporting ranking metrics:** M2 Kendall τ-b, M3 pairwise, M4 decisive-pair (≥3.0 pts),
M5 `precision@k`, M7 mean rank error.

**Secondary diagnostics, explicitly not success criteria:** MAE, RMSE, mean signed bias, and
decile calibration — **for Alpha only**. ECR publishes no point projection and none is invented
for it. W3 additionally reports whether point accuracy and ranking quality move together
across weeks, as a diagnostic observation.

**No composite score.**

---

## 6. Statistics

**Unit of replication is the week.** Never the player-week.

- All comparisons **paired within week** over the intersection of valid weeks.
- 95% **bootstrap CI over weeks**, 10,000 resamples, seeds 0–9 — `evaluation/weekly/noise.py`,
  unchanged, so W3's intervals are on the same scale as W2's MDEs.
- **MDE** = half-width of that interval; an effect below it is not distinguishable from weekly
  noise in either direction.
- **Newly declared for W3** (reporting additions, not metric changes): per comparison, the
  **number of weeks each system wins/loses/ties**, and a **two-sided Wilcoxon signed-rank
  test** on the per-week paired differences. Wilcoxon is chosen in advance as the standard
  paired non-parametric test; it is reported alongside the CI, and **the CI governs** where the
  two disagree, because the CI carries the effect size.
- Seasons reported separately as well as pooled.
- Coverage losses reported explicitly: how many ECR-universe players each system could not rank.

---

## 7. Primary comparisons

1. **Alpha vs season-to-date baseline** — does Alpha add signal over the obvious thing?
2. **ECR vs season-to-date baseline** — reproduced under the W3 common sample, **not quoted
   from W2**. W2 measured +0.066 Spearman on FLEX; if the W3 re-run differs, the difference is
   a sample/universe effect and is reported as such.
3. **Alpha vs ECR** — how close is Alpha to the external benchmark?

**+0.066 is not Alpha's pass mark.** It is ECR's measured edge over the same baseline, recomputed
here. A smaller Alpha edge can still be informative; a larger one is examined for a universe or
leakage explanation before being treated as a result.

---

## 8. Cross-position / FLEX calibration — measured, never corrected

Because FLEX is built by pooling three independently-trained per-position models, their absolute
point scales must be mutually comparable for the pooled ordering to be meaningful. W3 measures
whether they are:

- positional composition of Alpha's FLEX top-10/25/50 vs the **realized** top-10/25/50;
- mean signed bias (predicted − realized) per position;
- Spearman **within** each position on the FLEX board vs across the pooled board — a system
  well-calibrated within positions but badly calibrated across them shows the gap here;
- the same composition figures for ECR and the baseline, as references.

**No correction, reweighting or normalisation is applied in W3.** If a miscalibration exists it
is a finding and a W4 candidate.

---

## 9. Leakage protections

1. Features are lagged by SQL window frame (`ROWS BETWEEN n PRECEDING AND 1 PRECEDING`), so a
   row cannot see its own or a later game — pinned by
   `tests/leakage/test_player_week_features_leakage.py`.
2. Team features are the team's own prior-3-game averages, joined on the player's week-*w*
   team; same frame, same guarantee.
3. Training window is strictly `season < target_season`, enforced by the loader's date range.
4. Already-played players are removed from the universe before ranking
   (`tests/leakage/test_weekly_snapshot_cutoff.py`).
5. The evidence layer is **excluded** (§2.1b).
6. No Vegas, weather, closing line, post-cutoff injury or realized week-*w* statistic enters any
   feature — verified by the physical column list of `player_week_features`.
7. **A new W3 check:** every feature column is re-verified against the target row to confirm it
   is computed only from strictly-earlier `game_date`s, reported as a count of violations
   (expected: zero).

---

## 10. Reproducibility

| | |
|---|---|
| Alpha commit | `12aa1f5` (unmodified `models/`, `league/`, `api/`, `cli.py`) |
| training window | 2015–2024 (expanding, per target season) |
| data | nflverse ingest 2015–2025; ECR vintage `e270d790…5db9a5` |
| runner | `scripts/research/w3_alpha_benchmark.py` |
| determinism | CatBoost `random_seed=42`; bootstrap seeds 0–9; the benchmark is run **twice** and the outputs compared byte-for-byte |
| gates | `make test`, `make lint` (both halves) |

---

## 11. What W3 may NOT do

- Tune hyperparameters, add/remove features, change the target, the training window, the
  architecture or the ranking logic.
- Add ECR to Alpha in any form.
- Retrofit K/DST.
- Apply a cross-position FLEX correction.
- Select metrics after seeing results, or introduce a composite score.
- Change the population, the cutoff or the scoring rules.
- Declare Alpha "good" or "bad" — report where it has signal and where it does not.
- Change production code.

---

## 12. Amendments

*(None yet.)*
