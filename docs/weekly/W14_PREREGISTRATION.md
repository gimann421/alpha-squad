# W14 — Pre-registration: does W10's historical-player-knowledge gain hold on untouched 2026 weeks?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any 2026 outcome was ingested into
this project, before any 2026 board was scored, and before any 2026 model was trained.

> **No change below after seeing results without a dated amendment here.**

Authority:

- `docs/weekly/W10_PREREGISTRATION.md` §9, the frozen 2026 protocol, which this document executes;
- `docs/weekly/W10_HISTORICAL_RESULTS.md` and `reports/weekly/w10_results.json`, the effect being
  validated;
- `docs/weekly/W13_INJURY_FLEX_RESULTS.md` §21, which set this question;
- `CLAUDE.md`.

Decision record: D122.

---

## 0. What is known, and the date

- **W10's result is retrospective.** In 2021–2025, W10's model beat current Alpha at WR:
  - WR capture@10 +0.0223 [+0.0068, +0.0384];
  - WR capture@5 +0.0275 [+0.0057, +0.0502];
  - FLEX capture@10 +0.0190 [+0.0040, +0.0343];
  - all five leave-one-season-out folds significant at WR capture@10.

  Those weeks also shaped the hypothesis (W10 §0). **2026 is the first genuinely
  out-of-sample test.**
- **Today is 2026-10-05; the 2026 season is in progress.**
  - The nflverse 2026 files were last modified today at about 12:30 UTC (HTTP headers only).
  - Week 4's last game, Monday 5 October, kicks off tonight, after that capture.
- **Nothing about 2026 outcomes has been read.**
  - The 2026 schedule and the DynastyProcess ECR history were downloaded to establish which weeks
    have a Friday board. Only schedule columns and ECR scrape dates were read: no score, result,
    stat or ranking value.
  - W10's committed 2021–2025 cells were read, to fix the comparison rules below.

---

## 1. Hypothesis

> **H:** W10's historical-player-knowledge model (B) ranks 2026 weekly boards better than current
> Alpha (A), above all at the WR top of the board.

**Primary cell: WR capture@10, B − A, Full PPR, eligible 2026 weeks.** It is the cell W10's own
§9 rule turns on.

---

## 2. W10, frozen: nothing about the model changes

| item | frozen value |
|---|---|
| **A: current Alpha** | production's weekly CatBoost predictions for 2026, written by production's own weekly command `alpha-squad train established` (amendment A1). The research control trainer must reproduce them exactly (G1) |
| **B: W10** | `ALPHA_PLUS_HISTORICAL` = production's CatBoost (200 iterations, depth 4, lr 0.05, MAE, seed 42) on production's 11 weekly features **plus W10's 7 prior-season features** (`prior_ppg`, `prior_rank`, `prior_opp_pg`, `prior_tsh`, `prior_snap`, `prior_games`, `has_prior`) |
| how B is built | by W10's own `trainings()`, i.e. `w9.durable_table` → `w9.durable_panel` → `arms.train_with_extra_features` |
| training window | walk-forward by season: **`[2015, 2025]` for every 2026 week**, per position RB/WR/TE. No 2026 outcome ever enters training |
| 2026's prior-season features | from 2025 regular-season games only |
| universe | W2's: the week's canonical ECR positional board ∩ players who played ∩ Alpha-covered |
| FLEX | the existing pooled path (`w6.flex_cell`); no FLEX model |
| boards, tiebreaks, scoring | W10's: `alpha_board` with A's rank as tiebreak; Full PPR (primary) and Half-PPR |
| other boards | W10's null (N), its three ablations and HIST_ONLY are produced as W10 produces them. **They are not W14 verdict inputs** |
| ECR | the independent benchmark only, never a feature |

**Not added:**

- injury, news or depth-chart information;
- ECR;
- any 2026-specific information;
- any tuning or new transformation.

**The code is W10's, not a re-implementation.**

- Every file on W10's code path is byte-identical to W10's results commit `5de17c1` (G2):
  - the W6–W10 runners;
  - `evaluation/weekly/`;
  - production's `models/`, `features/`, `identity/`, `sources/` and `storage/`.
- The W14 runner imports and calls W10's own functions: `trainings`, `analyse`, `summaries`,
  `cliffs`, `calibration`. It adds only:
  - the week-eligibility filter (§4);
  - regret@10 and top-10 overlap, recomputed with W10's exact board calls (G10 checks them
    against W10's cells);
  - the statistics of §6.
- **The frozen protocol is also run verbatim** (`w10_historical.py --seasons 2026`). Its per-week
  cells must equal W14's for every eligible week (G10).

**If W10 cannot run as specified, W14 stops and documents the incompatibility.** It does not
modify W10.

---

## 3. 2026 data path: production's own pipeline, in an isolated database

The canonical database (`data/alpha_squad.duckdb`, sha256 `fa8e32db…`) is **never written**. The
W5–W13 reproduction runs against it, and G4 re-checks its hash at the end.

**Steps:**

1. Copy it to `data/w14/alpha_squad_2026.duckdb`, with `ALPHA_SQUAD_DATA_DIR=data/w14`. Raw 2026
   files land under `data/w14/raw`; both paths are gitignored.
2. Run production's CLI unchanged, with all console output to log files that are not read for
   results:
   1. `alpha-squad sources ingest --season-start 2026 --season-end 2026`
   2. `alpha-squad identity build`
   3. `alpha-squad features build --season-start 2026 --season-end 2026`
   4. `alpha-squad train established --season-start 2026 --season-end 2026` (the weekly
      walk-forward; amendment A1. The pre-amendment text named the season-level
      `train established-season`)
3. Save the nflverse 2026 schedule (`schedules/games.parquet`) under `data/w14/` with sha256 and
   capture time. Only its schedule columns are read: season, game_type, week, gameday, gametime,
   home_team, away_team.

**This is operation of the application, not a production change.** No file under `src/` is
modified (G2), and nothing outside `data/w14/` is written except W14's committed research files.

---

## 4. Cutoff, cadence and eligible weeks

**Cutoff:** W10's. Each week is scored against its **canonical Friday ECR board**: the latest
weekly scrape at most 7 days before the week's first Sunday game (W1/W2, `audit.week_coverage`).

- **No other snapshot is used, invented or reconstructed.**
- Model inputs for week *w* use only games before week *w* (production's window frames), plus
  2025 for the prior-season features.

**A 2026 week is eligible if and only if:**

1. it has a canonical Friday board;
2. every REG game of the week on the nflverse schedule is present in the pbp-derived `games`
   table;
3. every scheduled team has player-week stats for the week;
4. the week's last scheduled kickoff (ET) is at least 6 hours before the capture time of the 2026
   stats snapshot.

**Weeks 1–17 only.** Week 18 has no weekly board (W1), and W10 evaluates 1–17.

**Known now, from the schedule and ECR scrape dates only:**

| weeks | Friday board | status at this look |
|---|---|---|
| 1, 2, 3 | 2026-09-11, 09-18, 09-25 | candidates, subject to the completeness check |
| 4 | 2026-10-02 | **unavailable at this look:** its Monday game (5 Oct) kicks off after the data capture. It becomes eligible once nflverse publishes it |
| 5–17 | — | not yet played |

**Not substituted:** week 4 is not evaluated "minus the Monday game". The universe would then
silently drop that game's players.

---

## 5. Anti-peek audit: what 2026 information the repository already held

**Found by scanning every registered snapshot, before any 2026 ingestion:**

| snapshot (captured 2026-09-19/20) | 2026 content | used by W10's path? | treatment |
|---|---|---|---|
| nflverse `ngs_passing` / `ngs_rushing` / `ngs_receiving` | **66 / 70 / 157 rows of 2026 weekly Next Gen Stats: 2026 outcomes** | **no**: no module outside `sources/`, `cli.py`, `storage/schema.py` and `agents/state.py` references NGS | excluded; G4 asserts no NGS reference on W14's import path |
| DynastyProcess `fp_ecr_history` | weekly ECR boards through 2026-09-18 | the benchmark board only | superseded by the 2026 ingest; benchmark only |
| DynastyProcess values (scrape 2026-09-18), nflverse `draft_picks` / `combine` (2026 class) | pre-season | no | not used |
| every season-parameterised snapshot (stats, pbp, snaps, injuries, rosters, depth charts, ep) | none: they end in 2025 | — | — |

**The canonical database's outcome tables end in 2025.** This covers `player_week_stats`, `games`,
`player_week_features` and `weekly_projection_snapshot` (G4 re-asserts it).

**No committed artifact contains 2026 data.**

---

## 6. Metrics and statistics

**Metrics:**

- **Primary:** WR capture@10, B − A.
- **W10 §9's second element:** WR capture@5, B − A.
- **Key secondary:** FLEX capture@10.
- **Profile, all reported:**
  - RB, WR and TE capture@5, @10, @20 and Spearman;
  - FLEX capture@5, @10, @20, @25 and Spearman;
  - precision@10 and pairwise accuracy;
  - **top-10 overlap** (B vs A);
  - **regret@10**: best possible top-10 points minus the board's top-10 points, per week, as W13
    defined it.
- **Guardrails:** W10's breach definition (a CI excluding 0, negative, magnitude ≥ 0.005) over
  W10's guardrail set.

**Statistics:**

- **Unit: the week.**
- Paired bootstrap over weeks: 10,000 resamples, seeds 0–9. MDE is the CI half-width.
- W–L–T and Wilcoxon.
- **Exact sign-flip permutation p** for up to 20 weeks, enumerating all 2ⁿ sign patterns.
  - **With 3 weeks, the smallest attainable two-sided p is 0.25.**
  - Above 20 weeks: 100,000 seeded draws.
- **Season stage:** W10's periods (EARLY 1–6, MID 7–12, LATE 13–17).

**How much 2026 can say.** From W10's own 79 weeks, the weekly SD of WR capture@10 B − A is
0.0725.

| weeks | CI half-width | P(CI excludes 0) if W10's +0.022 is true | P(point estimate > 0) if true |
|---:|---:|---:|---:|
| 3 | ±0.082 | 0.08 | 0.70 |
| 8 | ±0.050 | 0.14 | 0.81 |
| 17 | ±0.034 | 0.24 | 0.90 |

- **A complete 2026 season will most likely not confirm W10 under §9, even if W10 is real.** This
  is stated now so it cannot be used as an excuse later.
- **Correction of fact, no rule change:** W10 §9 says a 16-week season has "roughly 1.4×" the
  79-week MDE. W10's own per-season WR capture@10 MDEs are 0.028–0.043 against 0.0155 over 79
  weeks, i.e. **1.8–2.8×**.

**Comparison with W10's history** (brief §15). The 2026 mean is set against:

1. W10's 2021–2025 effect;
2. each of W10's five leave-one-season-out folds;
3. each historical season's mean;
4. **each historical season's first *n* evaluated weeks**. For n = 3:

   | season | first 3 weeks, WR capture@10 B − A |
   |---|---:|
   | 2021 | +0.110 |
   | 2022 | +0.012 |
   | 2023 | +0.111 |
   | 2024 | +0.073 |
   | 2025 | +0.012 |

5. **the predictive band**: the distribution of an *n*-week mean resampled from W10's 79 weekly
   differences (100,000 draws, seed 14).

   | weeks | 2.5% | 97.5% | share ≤ 0 |
   |---:|---:|---:|---:|
   | 3 | −0.056 | +0.107 | 31% |
   | 17 | −0.011 | +0.057 | 10% |

---

## 7. Decision rule: fixed now

**Looks:**

- **INTERIM** while any of weeks 1–17 is still unplayed or pending complete data.
- **FINAL** when every week 1–17 is evaluated or permanently unavailable (no Friday board, or a
  documented data defect).

`classify()` in `evaluation/weekly/holdout.py` applies these rules in order:

| order | verdict | condition |
|---|---|---|
| 1 | **D. INCONCLUSIVE** (invalid) | any validity gate fails, or W10 cannot run as specified, or fewer than **3** eligible weeks |
| 2 | **C. NOT REPLICATED** | any look: the WR capture@10 CI is entirely below 0, **or** the 2026 mean is below the **2.5th percentile of W10's predictive band** for that many weeks. Final look only: also a WR capture@10 point estimate ≤ 0 |
| 3 | **A. REPLICATED** | **final look only:** W10 §9 holds (WR capture@10 and @5 point estimates both positive, and the WR capture@10 CI excludes 0) **and** no guardrail breach |
| 4 | **B. PARTIAL REPLICATION** | final look: WR capture@10 positive but not A (§9 not met, or met with a breach, reported as a tradeoff). Interim look with **≥ 8** eligible weeks: WR capture@10 and @5 point estimates both positive |
| 5 | **INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT** | everything else, which includes **any interim look with fewer than 8 weeks** |

**Why 8:** half the season. Before it, a 3-to-7-week sign is too close to a coin flip to call
"directionally present" (table in §6).

**W10 §9's own verdict** ("2026 confirms W10") is evaluated verbatim, and **only at the final
look**. At interim looks it is reported as "not yet evaluable".

**One decision, one primary cell.** FLEX capture@10 and the full guardrail profile are reported
and flagged; they change the verdict only through the breach condition at the final look.

**Half-PPR** gets the same rule as robustness. It is reported and never changes the verdict.

**No mid-season changes.** Whatever 2026 shows, the model, features, training, eligibility,
metrics and these rules stay as written. Any idea 2026 suggests becomes a separate,
separately pre-registered question.

---

## 8. Mechanism (only after the primary result is written down)

From W10's own outputs, on 2026, reusing W10's categories with no new features:

- **movement attribution** of B − A capture@10 by category: QUIET_STAR, SMALL_SAMPLE,
  ROLE_STRONGER_BEFORE, ROLE_STRONGER_NOW, OTHER;
- **quiet-star recall** for A, B and ECR;
- **the WR cliff:** capture@10 against W5's same-Spearman copula null, for A and B;
- **the W5 misses**, per week:
  - false positives: predicted top-10, finished outside the top 24;
  - false negatives: finished top-5, predicted outside the top 24;
- the players most often rescued, or wrongly promoted;
- the W8 decomposition of B − A;
- **the early-season reading:** every 2026 week so far is in EARLY. W10's EARLY effect was the
  largest of its periods: WR capture@10 +0.038, capture@5 +0.063, 24 weeks.

**All exploratory.** A mechanism is called "replicated" only if the 2026 numbers support it at a
stated level, not by narrative.

---

## 9. Validity and leakage gates: all pass before any 2026 result is read

| gate | check |
|---|---|
| G1 | **parity:** the research control (no added feature) reproduces production's stored predictions exactly, for 2026 and for 2021–2025, on the 2026 database |
| G2 | **W10 frozen:** every W10 code-path file is byte-identical to `5de17c1`. B's 7 features equal W10's list. The W14 runner fits no model of its own: it calls `w10.trainings` once and makes no `train_with_extra_features` or CatBoost call |
| G3 | **history intact:** production's training frames 2015–2025 (RB/WR/TE) and the durable table ≤ 2025 are identical between the canonical and 2026 databases (content hashes). W10 re-run on the 2026 database for 2021–2025 is byte-identical to `reports/weekly/w10_results.json` |
| G4 | **anti-peek:** the canonical database is unmodified (sha256 `fa8e32db…` at the end). Its outcome tables hold no 2026 row. No module loaded by the W14 runner references NGS |
| G5 | **walk-forward:** every 2026 training frame ends in 2025; no 2026 row in any training set |
| G6 | **later weeks cannot move earlier predictions:** for each eligible week *w*, a copy of the 2026 database with **every 2026 row after week *w* deleted**, its features rebuilt by production's own builders and A and B retrained, gives **bit-identical** week-*w* A and B predictions and features. This covers post-Friday, post-kickoff, final-usage and future-game information. Week *w*'s own games never enter its features (window frames end one row before) |
| G7 | **no forbidden inputs:** B's training frame columns are exactly W10's 7 plus keys; no injury, depth, news, ECR or 2026-only token |
| G8 | **eligibility:** the evaluated weeks are exactly those passing §4; each excluded week has its reason; the schedule sha256 is recorded |
| G9 | **identity:** every 2026 universe player resolves to a canonical id; 2026 team codes ⊂ `games` teams; the gsis map rate for 2026 stats rows is reported |
| G10 | **W10's own numbers:** for every eligible week, W14's cells equal the verbatim `w10_historical.py --seasons 2026` cells exactly; recomputed boards reproduce W10's capture@10 |
| G11 | **determinism:** two W14 runs byte-identical |
| G12 | **upstream:** W5–W13's 14 artifacts re-run byte-identical on the canonical database |

**Reported, not gated** (3 weeks are too few to gate on): W10's null arm N − A at WR
capture@5/@10.

---

## 10. Future looks: what is added, and how

- **Each later look runs the same committed runner and gates, unchanged**, on a fresh 2026
  ingest (§3). It adds every week that has become eligible under §4:
  - week 4 once its Monday game is published;
  - then weeks 5–17 as each completes.
- **The final look** comes after week 17's data is complete, with §9 evaluated once.
- Each look is a new commit. It records its eligible weeks and its gate results.
- **No look may change §2–§7.**

---

## 11. Predictions (before any 2026 result)

1. This look has **3 eligible weeks** (1–3); week 4 is unavailable.
2. **Verdict at this look: INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT.**
3. WR capture@10 B − A is **positive**, inside W10's predictive band, with a CI including 0.
4. WR capture@5 B − A is positive.
5. FLEX capture@10 B − A is positive, with a CI including 0.
6. The exact sign-flip p is ≥ 0.25, as it must be with 3 weeks.
7. No guardrail difference has a CI excluding 0.
8. Half-PPR agrees in sign at WR capture@10.
9. Mechanism: most of B's WR movement is attributed to SMALL_SAMPLE and QUIET_STAR. Early-season
   history matters most when the current season has almost no games.
10. G1 parity holds for 2026: production's 2026 predictions are reproduced exactly.

---

## 12. Amendments

### A1 (2026-10-05, before any 2026 result): the weekly production command

**§3 step 4 named the wrong production command.**

- `alpha-squad train established-season` is production's **season-level** model (`ml_season_*`).
  It writes no weekly predictions.
- **W10's arm A** (`weekly_projection_snapshot`, `ml_catboost`) is written by
  `alpha-squad train established`. That is the weekly walk-forward command
  (`models/established/train.py::run_established_ml`), the one that produced the stored 2021–2025
  predictions (DECISIONS: "`train established` (the weekly command, distinct from `train
  established-season`)").

**How it was found:** a structural check after the first build. `weekly_projection_snapshot` had
no 2026 rows. Only row counts and the log's non-table lines were looked at.

**Correction:**

- §3 step 4 reads `alpha-squad train established --season-start 2026 --season-end 2026`.
- The first isolated database, which also held the season-level command's output, was
  **deleted**. It was rebuilt from a fresh copy of the canonical database with the corrected
  sequence.

**Nothing else changes:** the hypothesis, arms, features, cutoff, eligibility, metrics, decision
rule, gates and predictions are as written.

### A2 (2026-10-05, before any 2026 result): restore the canonical row order

**Caught by gates G1 and G3 on their first pass,** before any result was read.

- **G1 failed:** the research control trained on the 2026 database reproduced **0 of 26,097**
  stored 2021–2025 predictions (max difference 2.69 points). It still reproduced all 1,270 of
  production's 2026 predictions exactly.
- **But G3's content check passed:** the 2015–2025 training frames held identical rows and values.

**Cause.**

- Production's `features build` re-upserts **every** `player_week_features` (and
  `team_week_features`) row, which rewrites their physical order. Every position's frame differs
  from the canonical one from row 0.
- Production's loader (`load_position_week_data`) reads without `ORDER BY`, so it returns rows in
  physical order, and CatBoost's fit depends on row order.
- **The same data in a new order therefore trains a different model.** This is a property of the
  production stack, not of W10: every W5–W13 number is likewise conditional on the canonical
  database's order.

**Correction.** This keeps W10's exact environment; production code is untouched.

1. After production's `features build`, the isolated database's ≤ 2025 rows of those two tables
   are put back in the **canonical database's physical (rowid) order**. The 2026 rows follow in
   production's own order. This is done by `scripts/research/w14_row_order.py`, which verifies
   afterwards that production's loader returns the canonical sequence for 2015–2025 exactly.
2. Production's `alpha-squad train established --season-start 2026 --season-end 2026` is then
   **re-run**, so arm A is production's prediction in that environment.
3. **G1 and G3 are unchanged and must pass as written.**
4. **G6's redacted copies get the same restore** after their features are rebuilt. G6 then tests
   leakage, not row order.

**Reported as a finding.** Row order alone moves single-seed predictions by up to 2.69 points.
The 2026 estimate, like W10's, is conditional on one training order.

**Nothing else changes.**

### A3 (2026-10-05, before any 2026 result): G6 compares features at W10's positions

**Found on G6's second pass,** before any result was read.

- **What passed:** with every later 2026 week deleted, A's and B's week-*w* predictions were
  bit-identical for all three weeks (320 / 320 / 326 player-weeks).
- **What differed:** the stored week-*w* feature rows. Every difference is a K or DST row, caused
  by production's build order, not by later weeks:
  - `features build` writes the feature rows **before** its K/DST step adds team-defense rows to
    `player_week_stats` and computes kicker points (nflverse scores only passing, rushing and
    receiving). The 2026 database therefore has no 2026 DST feature rows, and its 2026 kicker
    features were built from zero points.
  - The gate's rebuild runs after that step, so it creates 32 DST rows a week and gives kickers
    their computed points.
- **No RB, WR or TE row differs.**

**Correction:** G6's feature comparison is restricted to **RB, WR and TE**, the positions W10
ranks. It requires identical row sets and bit-identical values there, alongside the unchanged A
and B prediction checks.

**Reported as a production observation, not a W14 input:** the K/DST build-order quirk. Nothing
else changes.

### A4 (2026-10-05, before any 2026 result): G3's re-run allows only an enumerated crosswalk revision

**Found by G3,** before any result was read.

- **What did not match:** W10 re-run for 2021–2025 on the 2026 database is **not** byte-identical
  to `reports/weekly/w10_results.json`.
- **What did match:**
  - every 2021–2024 cell;
  - every model prediction (G1: 26,097 / 26,097);
  - the training frames and the durable table.

**Cause: an upstream data revision.**

- The newer DynastyProcess `player_ids` crosswalk (captured 2026-10-05) dropped the FantasyPros id
  of two 2025 depth players, a WR and a TE. Their ECR rows no longer join, so each leaves seven
  2025 boards (2025 weeks 5, 9, 10, 11, 15, 16, 17), and the FLEX board with them.
- Across the whole crosswalk, 5 FantasyPros mappings were lost, 4 gained and 0 changed, out of
  about 4,776.
- **W10's headline effects are unchanged** under the new crosswalk:
  - WR capture@10 +0.0223 [+0.0068, +0.0384];
  - WR capture@5 +0.0275;
  - FLEX capture@10 +0.0190;
  - the verdict is SUCCESS either way.
- **2026 must use the current crosswalk.** The old one has no 2026 rookies.

**Correction: G3's third check becomes an *explained-difference* check.**

- Every W10 cell must reproduce exactly, except in a week whose evaluation universe differs.
- Every universe difference must be a player whose FantasyPros mapping differs between the two
  crosswalk vintages.
- **Any other difference fails G3.**

The canonical database's byte-identical W10 reproduction (G12) is unchanged.

### A5 (2026-10-10, look 2, before any new 2026 data was ingested): tooling only

**Why it was needed:**

- Look 2 (W15) runs on a **fresh** isolated database, `data/w15/`, so that look 1's database,
  and with it the W14 artifact, stays reproducible.
- The committed runner already takes `--db`, `--schedule` and `--out`.
- The gate script read look 1's schedule manifest from a hard-coded path (G8), and its G11
  determinism re-run did not pass a schedule through.

**What changed:** the gates gained a `--schedule` argument, defaulting to look 1's manifest. G8
reads it, and G11's re-run passes it on.

**No check's logic, threshold or rule changes.** §2–§7 are untouched.

**Look 2 data path:** §3 steps 1–5 exactly (A1, A2) in `data/w15/alpha_squad_2026.duckdb`, with
`ALPHA_SQUAD_DATA_DIR=data/w15`, and a fresh schedule snapshot under `data/w15/schedule/`.
