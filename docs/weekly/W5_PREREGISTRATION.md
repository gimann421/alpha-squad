# W5 — Pre-registration: why does within-position ranking collapse at the top?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any cohort, oracle, copula-null or
residual result existed. The forensic audit in §2 *was* run first — it describes the
data-generating process and the data inventory, which is what the brief asks for — and the a
priori predictions in §3 are recorded **before** anything is evaluated, so they can be scored
against the outcome rather than rationalised after it.

Authority: `docs/weekly/W4_FLEX_FORENSICS_RESULTS.md`, `docs/weekly/W3_ALPHA_BENCHMARK_RESULTS.md`,
`docs/weekly/W2_ECR_BENCHMARK_RESULTS.md`, `CLAUDE.md`. Decision record: `docs/DECISIONS.md` D113.

> **No change below after seeing results without a dated amendment here.** Same rule as W2's A1,
> W3, W4, D70, D106.

---

## 1. The question

> **Why does Alpha's within-position ranking quality collapse at the top of the RB, WR and TE
> boards, and what information or model behaviour is responsible?**

W4 established that the FLEX combination step is not the bottleneck (verdict D) and that
`corr(pred, real)` restricted to predicted ≥ 10 falls to RB **0.251**, WR **0.222**, TE **0.141**,
against 0.625 / 0.595 / 0.557 over the full range. W5 asks why.

**W5 must not assume the collapse is a model defect.** §2.6 and §2.7 record two properties of the
*outcome* that were measured before any model comparison, and either could produce the same
appearance. The phase therefore splits into three questions, in order:

| | question | answered by |
|---|---|---|
| **P1** | Is there a top-of-board cliff **beyond what Alpha's overall ordering quality already implies**? | §5 copula null |
| **P2** | How much of the remaining headroom is **reachable at all** from pre-game information? | §6 oracles |
| **P3** | Does any **pre-cutoff information class** explain a material share of top-board regret? | §7–§9 |

**A finding that the cliff is largely a statistical artefact, or that the headroom is mostly
irreducible, is a successful outcome** — it stops a phase of feature engineering that would not
have paid, exactly as W4's verdict D did for calibration.

---

## 2. Forensic audit (run first, reported as fact)

Traced through the code and the stored snapshots, not the docs.

### 2.1 The model, verified against source

`models/established/train.py::MODEL_SPECS["ml_catboost"]` — `CatBoostRegressor(iterations=200,
depth=4, learning_rate=0.05, loss_function="MAE", verbose=False, random_seed=42)`, trained on
`FULL_FEATURES` (11 columns), **per position**, target `target_fantasy_points_ppr`.
`load_position_week_data` applies `fillna(0.0)` to every feature. `MIN_TRAINING_ROWS = 50`.
Every W3/W4 claim about the model reproduces exactly.

**Training window:** `run_established_ml` loops `for target_season ... for position ...` and
fits on `[min_train_season, target_season − 1]`. **The model is refit once per season and never
sees a single week of the season it is predicting.** Week 18 of 2024 is predicted by a model
whose newest training row is from 2023. In-season information reaches the prediction only
through the features, never through the fit.

**Training rows (2015–2024) / 2025 prediction rows:**
QB 6,220 / 664 · RB 14,807 / 1,575 · WR 23,302 / 2,511 · TE 11,611 / 1,287.

### 2.2 What the model actually weights (CatBoost gain %, fit on 2015–2024)

| feature | QB | RB | WR | TE |
|---|---:|---:|---:|---:|
| `fp_ppr_avg_season_to_date` | 21.1 | **26.6** | **28.4** | **23.6** |
| `snap_pct_avg_last3` | **28.1** | **30.2** | 16.7 | 14.5 |
| `fp_ppr_avg_last3` | 23.2 | 14.4 | 9.5 | 4.8 |
| `target_share_avg_last3` | 0.8 | 2.5 | 13.9 | **16.5** |
| `receptions_avg_last3` | 0.7 | 2.7 | 12.9 | 13.1 |
| `targets_avg_last3` | 0.4 | 2.5 | 11.7 | 12.1 |
| `carries_avg_last3` | 4.2 | 13.6 | 0.8 | 3.9 |
| `games_played_prior` | 2.4 | 2.2 | 2.5 | 4.0 |
| `team_epa_avg_last3` | 9.6 | 1.7 | 1.4 | 2.3 |
| `team_plays_avg_last3` | 5.6 | 1.8 | 1.3 | 2.5 |
| `team_pass_rate_avg_last3` | 3.8 | 1.9 | 1.0 | 2.5 |

Two "how good has he been lately" features carry **40–57%** of the gain at every position. Team
environment carries **1.3–9.6%**, and only for QB is it non-trivial. **There is no opponent
feature, no injury feature, no depth-chart feature, no rest/travel feature and no market feature
of any kind.**

### 2.3 Two structural properties of the feature panel

`features/panel.py` computes every lag-3 column as
`AVG(x) OVER (PARTITION BY player_id ORDER BY game_date, season, week ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)`.

* **The window is partitioned by `player_id` only, not by `(player_id, season)`.** Week 1 of
  2024 is therefore described by the last three games of 2023. A player who changed team, role
  or offence over an offseason looks exactly like his old self.
* **`player_week_stats` has a row only when a player appeared.** "Last 3 games" means the last
  three games *played*, which for an injured player can span two months. Recency is measured in
  appearances, never in calendar weeks.

Missing-data handling disadvantages no position: NULL rates are 1.89–2.18% for the lag-3
columns and 9.73–12.32% for season-to-date, near-identical across QB/RB/WR/TE.

### 2.4 Data inventory: what this repository actually holds

Every source below is already ingested as an immutable snapshot. The **cutoff feasibility**
column is the only thing that decides whether a signal can legitimately reach a Friday board.

| source | grain | pre-Friday timestamp? | class (current week) |
|---|---|---|---|
| `player_week_stats`, `player_week_features` | player-week | derived from prior games only | **A** (in use) |
| `games` (schedule, opponent) | game | fixed months ahead | **B** — opponent identity is free and unused |
| `nflverse/injuries` 2021–2024 | one **final** row per player-week | `date_modified`, 100% non-null | **B/C** — see §2.5 |
| `nflverse/injuries` 2025 | same | **no `date_modified` column at all** | **C** — excluded |
| `nflverse/depth_charts` 2015–2024 | player-week, `depth_team` 1/2/3 | **none** | **C** current week · **B** prior week |
| `nflverse/depth_charts` 2025 | **daily snapshots**, `dt` timestamped, 219 dates from 2025-08-03 | yes | **B** — but 2025 only, and no `week` key |
| `nflverse/snap_counts` | player-game realized | post-game | **B** prior weeks · **D** current |
| `ffopportunity/ep_weekly` | player-game expected points from realized usage | post-game | **B** prior weeks · **D** current |
| `nflverse/weekly_rosters` | player-week `status` (ACT/INA/RES) | none; gameday status | **C/D** |
| Vegas lines, weather | — | **absent from every ingested source** | **C** — not researchable here |

`player_id_map` maps every `gsis_id` to the canonical `asq_*` id, so injuries, depth charts and
expected points all join to the evaluated universe.

### 2.5 The injury report is one final row, not a history

`nflverse/injuries` holds **exactly one row per (season, week, player)** — verified, 5,599 of
5,599 groups have n=1 in 2023. `date_modified` is the timestamp of that row's **last** edit, so
filtering on it *deletes* a row rather than rewinding it to its Wednesday state. Day-of-week of
`date_modified` in 2023: Friday 4,227 (75.5%), Wednesday 588, Thursday 331, Saturday 421.

W5 therefore uses two pre-registered variants and reports both:

* **STRICT** — `date_modified < snapshot_date`. Unambiguously available on Friday morning.
* **FRIDAY** — `date_modified <= snapshot_date`. Same vintage rule ECR itself is published under,
  but a row edited at 23:00 Friday is included.

2025 carries no `date_modified` and is **excluded from every injury analysis**, never imputed.

### 2.6 The outcome itself is barely persistent at the top

`corr(points_w, points_{w−1})`, REG 2021–2025, computed before any model result was examined:

| | all players | prior week's positional **top 24** | prior week's **top 12** |
|---|---:|---:|---:|
| QB | 0.283 | 0.152 | 0.124 |
| RB | 0.491 | **0.195** | **0.145** |
| WR | 0.434 | **0.142** | **0.113** |
| TE | 0.376 | **0.209** | **0.176** |

**Alpha's measured top-of-board correlations (RB 0.251 / WR 0.222 / TE 0.141) sit at or above the
raw week-to-week persistence of the outcome itself.** Whatever the collapse is, the outcome
collapses the same way, and conditioning on a high value truncates the predictor's variance in
both cases. §5 is designed to separate those two explanations rather than assume either.

### 2.7 Even perfect knowledge of this week's usage is far from perfect

`ffopportunity` computes expected fantasy points from a game's *realized* opportunity — a
post-game quantity. Correlating it against realized points bounds what **perfect opportunity
foresight** could ever deliver:

| | r (all) | r² | r among the week's realized **top 12** |
|---|---:|---:|---:|
| QB | 0.792 | 0.627 | 0.398 |
| RB | 0.842 | 0.709 | 0.379 |
| WR | 0.805 | 0.649 | 0.499 |
| TE | 0.816 | 0.665 | 0.605 |

Knowing exactly how many targets and carries a player would get leaves **29–37%** of weekly point
variance unexplained overall and **63–86%** unexplained among the players who actually finished at
the top. Touchdowns carry 37–44% of the weekly standard deviation (RB sd 3.57 of 8.02, WR 2.84 of
7.71, TE 2.57 of 5.97) and are close to Bernoulli.

**W4's `ORACLE_WITHIN` (+0.3613) is therefore not an achievable target**; it assumed perfect
outcome knowledge. §6 replaces it with a ceiling that can actually be reasoned about.

---

## 3. A priori predictions, recorded before any result

Stated so they can be **wrong** in public. Scored in the results document whatever happens.

1. **Most of the measured "top-of-board collapse" is range restriction, not a model defect.** A
   synthetic ranker with Alpha's *overall* Spearman and no top-specific defect will reproduce
   most of the conditional-correlation drop. **P1 will return NO CLIFF** on capture@10.
2. **The reachable headroom is much smaller than W4's `W = +0.3613`.** `ORACLE_USAGE` will land
   far below `ORACLE_OUTCOME` — I predict it recovers **less than half** of the outcome oracle's
   gain on capture@10.
3. **Role change is a real but modest contributor.** Because lag-3 crosses seasons and counts
   appearances rather than weeks, players whose current opportunity departs from their lagged
   opportunity will be over-represented in regret — but by a factor closer to 1.5× than 3×.
4. **Injury/practice status will explain less top-board regret than expected.** The top of a
   positional board is mostly healthy starters; the injury signal is predominantly an
   *availability* signal, which W1 required be kept as a separate concept from expected points.
5. **Opponent/matchup will explain very little.** Weekly opponent effects on individual scoring
   are small next to TD variance; I predict the opponent term fails the materiality bar at every
   position.
6. **TE is not a distinct failure mode.** Its lower correlation follows from its lower scoring
   scale and higher relative TD share, not a separate mechanism. TE's `ORACLE_USAGE` share will
   look like RB's and WR's.
7. **Misses will be only weakly predictable from pre-cutoff information** — I predict the
   exploratory miss model reaches AUC below 0.62.
8. **Expected decision: not "add features".** The strongest candidate will be an opportunity- or
   architecture-targeted experiment, and a substantial share of the gap will be irreducible.

If the results contradict these, the results win and the contradiction is reported prominently.

---

## 4. Population, universe, metrics, statistics

**Unchanged from W3/W4 in every respect** — 79 weeks, 2021–2025, Full PPR, Friday cutoff,
ECR-defined positional universe intersected with played and with Alpha coverage, W2's frozen
metric suite, invalid-cell rule at 10 evaluable players.

**Depths: 5, 10, 20, 25, 50.** Depth 20 is added because the brief asks for it; it is a new
*depth* of existing metrics, not a new metric. A depth is skipped for a cell too small to
support it. **No depth is chosen after seeing which is most interesting.**

**Positions: RB, WR, TE confirmatory; QB reported for contrast only** and excluded from every
decision rule (the product's FLEX is RB+WR+TE, and W3 measured QB as the weakest board).

**Unit of replication is the week (n = 79).** All comparisons paired within week; 95% bootstrap
CI over weeks (10,000 resamples, seeds 0–9, `evaluation/weekly/noise.py`); Wilcoxon signed-rank
and win/loss counts. A cohort containing 4,000 player-weeks does not have 4,000 independent
observations.

---

## 5. P1 — the cliff test (confirmatory)

**The problem.** "Correlation among the predicted top-K" is computed on a subgroup selected by
the predictor, so it is attenuated by range restriction whether or not the model has a
top-specific defect. Comparing it to the full-board correlation therefore cannot answer P1.

**The instrument — a copula null.** For each (week, position) cell, take Alpha's realized values
and its observed full-board Spearman ρ. Draw a synthetic score for every player from a Gaussian
copula with the realized values at exactly correlation ρ, rank by it, and compute the frozen
metric suite. This is a ranker with **Alpha's overall ordering quality and no top-specific
structure whatsoever**. Repeat `N_SIM = 200` times per cell with seeds fixed by
`hash(season, week, position)` so the run is deterministic.

The null answers: *given only how well Alpha orders the board overall, how good should its top-10
be?*

**Decision rule, fixed now.** On positional **capture@10**, per position, using the per-week
difference `d = capture@10_actual − mean(capture@10_simulated)`:

| verdict | criterion |
|---|---|
| **CLIFF** | the 95% bootstrap CI over weeks excludes zero, `d` is negative, **and** \|mean d\| ≥ **0.02** |
| **NO CLIFF** | the CI contains zero, **or** \|mean d\| < 0.02 |

0.02 is roughly half the W3 FLEX Alpha-vs-ECR capture@10 gap (0.0388) and is fixed here, not
chosen after seeing an effect size. The same statistic is reported at depths 5/20/25/50 and for
precision, as supporting evidence only.

**The conditional-correlation statistic** (`corr(pred, real)` among predicted ≥ the position's
top-24 cutoff) is computed for Alpha **and for the copula null**, so the range-restriction share
of the reported collapse is quantified rather than asserted.

---

## 6. P2 — the reachable ceiling (confirmatory)

Three positional boards, all on the identical universe. **All use realized outcomes by design
and none is a production candidate.**

| id | board | what it bounds |
|---|---|---|
| **CF_A** | current Alpha, ranked by predicted points | the control |
| **ORACLE_USAGE** | ranked by the week's **realized usage-expected points** (`ffopportunity total_fantasy_points_exp`) | perfect opportunity foresight, **zero** conversion foresight |
| **ORACLE_OUTCOME** | ranked by realized points | perfect foresight — W4's `ORACLE_WITHIN` restricted to one position |

Reported quantities, fixed now:

    U = ORACLE_USAGE   − CF_A        reachable-at-most by better opportunity forecasting
    O = ORACLE_OUTCOME − CF_A        the unattainable ceiling
    U / O                            the share of the ceiling that opportunity foresight reaches
    O − U                            conversion / touchdown variance -- unreachable from any
                                     pre-game information

**Invariants, asserted by test before any result is read** (W4's lesson): `ORACLE_OUTCOME` must
score pairwise accuracy exactly 1.0; `ORACLE_USAGE` must be invariant to any strictly monotone
transform of the usage score; both must rank exactly the same player set as `CF_A`; ties in
either score resolve in Alpha's favour with `player_id` as the deterministic backstop.

`ORACLE_USAGE` is evaluated only on player-weeks where the expected-points join succeeds; the
join rate is reported per position and per season, and unmatched players are **dropped and
counted, never imputed**.

---

## 7. Player-level regret — the exact additive decomposition

For depth *K*, a week's top-K points-capture shortfall is **exactly** additive over players:

    shortfall_K = Σ_{i ∈ realized top-K} pts_i  −  Σ_{i ∈ predicted top-K} pts_i
                = Σ_i pts_i · ( 1[i ∈ realized top-K] − 1[i ∈ predicted top-K] )

Each player contributes `regret_i = pts_i · (1[real top-K] − 1[pred top-K])`, positive for a
player the board **missed** and negative for one it **wrongly included**. Summing `regret_i` over
any cohort gives that cohort's exact contribution to the week's shortfall, with no modelling
assumption and no residual term. This is the attribution instrument for §8 and §9.

**Frozen "big miss" definitions**, for the categorical analyses:

* **FALSE POSITIVE** — predicted positional top-10, finished outside the realized top-24.
* **FALSE NEGATIVE** — predicted outside the positional top-24, finished in the realized top-5.

---

## 8. Cohorts — thresholds fixed now

Every cohort is computed from **strictly prior** information only (`season < S`, or `season = S`
and `week < w`), except where the table says otherwise. Cohorts are not mutually exclusive; each
is reported against the complement of itself.

| cohort | definition | class |
|---|---|---|
| `ELITE_PRIOR_SEASON` | top 12 at the position by **prior season** total PPR points | B |
| `HOT_L3` | `fp_ppr_avg_last3` in the top quintile of the position-week | A |
| `HIGH_SNAP` | `snap_pct_avg_last3` ≥ 0.75 | A |
| `LOW_SAMPLE` | `games_played_prior` ≤ 2 | A |
| `ROOKIE` | `players.rookie_season = season` | B |
| `TEAM_CHANGE` | current-week team ≠ team of the player's most recent prior appearance | B* |
| `RETURNING` | ≥ 2 calendar weeks since the player's last appearance | B |
| `VOLATILE_ROLE` | sd of `offense_snap_pct` over the prior 3 appearances above the position-week median | A |
| `OPPORTUNITY_UP` | `(targets+carries)_last1 − (targets+carries)_avg_prior3` in the top quintile | A |
| `OPPORTUNITY_DOWN` | the same measure in the bottom quintile | A |

`TEAM_CHANGE` is marked **B\*** because a trade or signing is public long before Friday in
reality, but this repository cannot *timestamp* it; the cohort is reported and the caveat is
carried with it wherever it appears.

**Quintiles are computed within (position, season, week)** on the evaluated universe, so a
cohort is always ~20% of that cell and cannot be inflated by a league-wide trend.

---

## 9. Information classes — the roadmap instrument

Each candidate is classified once, and the classification is what decides whether it may be
recommended:

* **CLASS A** — information Alpha already has.
* **CLASS B** — existed historically, available before Friday, **not used by Alpha**.
* **CLASS C** — exists historically but cannot be timestamped to Friday in this repository.
* **CLASS D** — knowable only after the game.

**Only Class B may be elevated to a W6 experiment.** Class D cannot legitimately improve a Friday
prediction and is used only to bound headroom. Class C becomes a data-acquisition item, never a
modelling recommendation.

**Materiality bar, fixed now.** A class is MATERIAL only if **all three** hold:

1. its cohort's share of total positional top-10 regret exceeds its share of the evaluated
   population by **≥ 50% relative**;
2. the corresponding week-level paired difference has a 95% CI excluding zero;
3. its estimated recoverable value on positional capture@10 is **≥ +0.0097** — the same practical
   bar W4 used, one quarter of the W3 FLEX Alpha-vs-ECR gap.

A class that is statistically significant but fails (1) or (3) is reported as **significant and
immaterial**, and is explicitly *not* elevated. W4's `CAL_AFFINE` is the precedent.

---

## 10. Exploratory analyses — labelled, and excluded from every decision rule

The following may generate hypotheses and **may not** be presented as confirmed findings, nor
used to satisfy §9's materiality bar:

* **E1 — miss predictability.** A walk-forward CatBoost classifier on pre-cutoff features only,
  predicting FALSE POSITIVE / FALSE NEGATIVE status. Reported as AUC with a permutation baseline.
  A model trained to predict its own errors is a diagnostic, never a feature.
* **E2 — opponent residual association.** Correlation of the top-board residual with a
  strictly-prior opponent points-allowed measure.
* **E3 — mid-season staleness.** Association between week-within-season and Alpha's deficit,
  motivated by §2.1's once-per-season refit.
* **E4 — team-environment change.** Association between top-board residual and the change in the
  team's lagged environment.

---

## 11. Robustness — fixed now

1. **Leave-one-season-out** on every headline effect (5 recomputations each).
2. **Per-depth consistency** across 5 / 10 / 20 / 25 / 50.
3. **Half-PPR replication** of P1 and P2 — the product ships both formats and W2–W4 measured only
   Full PPR.

No further slicing.

---

## 12. Validity gates — all must pass before any result is interpreted

Zero ECR input to Alpha or to any cohort, oracle or classifier; zero current-week realized
outcomes in any *pre-cutoff* quantity; zero future weeks; zero already-played players; identical
universe across every board; positions correct; oracle invariants hold; cohort definitions match
their stated SQL; the runner produces byte-identical output on two runs; W3 and W4 reproduce
exactly. **If any gate fails, stop and fix the instrument before reading results** — W4's G4
failure is the precedent and it changed a reportable number.

---

## 13. What W5 may NOT do

Change production behaviour, model predictions, features, the weekly API, the Friday-board
eligibility architecture or the injury evidence layer; add ECR anywhere; retrain or tune the
production model; run a hyperparameter sweep; select a cohort or depth after seeing results;
recommend an information class that fails §9's bar; or present an exploratory result as
confirmatory.

The two W3 engineering prerequisites (injury-cutoff leakage; true Friday board) remain **out of
scope** — W5 may document whether they constrain a future experiment, and implement nothing.

---

## 14. Decision rules for the phase (Part 23 of the brief)

| if | then |
|---|---|
| P1 returns **CLIFF** and a Class B cohort is MATERIAL | recommend a focused W6 testing that information class |
| P1 returns **NO CLIFF** and `U/O` is small | the top-of-board result is implied by overall ordering quality; recommend an **overall-quality** experiment, not a top-of-board one |
| errors are largely unpredictable from pre-cutoff information (E1 near chance, no MATERIAL class) | treat as substantially irreducible; **do not** add complexity |
| positions differ in their strongest mechanism | recommend **position-specific** work, not a universal fix |
| a mechanism is significant but explains little | report it as significant and immaterial; **do not** elevate it |

**The phase must end with either** a single named, falsifiable W6 experiment (treatment, control,
scope, cutoff, leakage rules, primary metric, MDE, success **and** failure criteria) **or** a
named uncertainty that must be resolved before any experiment is worth running.

---

## 15. Amendments

*(None yet.)*
