# W10 — Pre-registration: does historical player knowledge improve Alpha?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any W10 quantity was computed.

> **No change below after seeing results without a dated amendment here.**

Authority: `docs/weekly/W9_MECHANISMS_RESULTS.md` (the hypothesis), W5–W8 results, `CLAUDE.md`.
Decision record: `docs/DECISIONS.md` D118.

---

## 0. What is already known: read this first

**W10's main arm is exactly W9's `ALPHA_PLUS_DURABLE`.** Re-specifying the historical features
after W9 saw results would be the feature search the brief forbids, so the spec is frozen as W9
defined it.

This means **some of W10's primary numbers are already known**. W9 reported, and I read, the
arm's capture difference against current Alpha:

| B − A, point estimates | capture@5 | capture@10 | capture@20 |
|---|---:|---:|---:|
| RB | −0.004 | +0.000 | +0.000 |
| WR | +0.028 | **+0.022**, CI [+0.007, +0.038] | +0.009 |
| TE | +0.012 | +0.004 | +0.007 |
| FLEX | — | +0.019 | +0.013 (capture@25) |

The CIs for every cell except WR capture@10 were not read.

**What W10 tests without having seen it:**

- consistency across seasons, per season and leave-one-season-out;
- the early / mid / late split;
- every guardrail: capture@50, Spearman, pairwise accuracy, TE, FLEX, Half-PPR;
- the W5 cliff and the W5 misses;
- the ECR benchmark beyond capture@10;
- which historical information drives any effect;
- the redundancy analysis, the historical-only baseline, the null arm and the point diagnostics.

**Therefore W10 is retrospective research, not confirmation.** The 2021–2025 weeks shaped the
hypothesis.

**The repository holds no 2026 data at all**: no stats, games or production predictions (§9). The
genuinely out-of-sample check is the 2026 season, and §9 freezes that protocol now.

---

## 1. The question

> If Alpha is explicitly given the player's previous-season role and performance, does its weekly
> ranking, and above all its top of the board, actually improve?

---

## 2. The historical information — fixed (W9 §4.1, unchanged)

All seven features come from season **S − 1**, regular season (weeks ≤ 18). They are complete
before season S begins, so they are Class A for every week of S, including Week 1.

| category | feature | definition |
|---|---|---|
| **A. production** | `prior_ppg` | PPR points per game played |
| | `prior_rank` | positional rank by total PPR, `player_id` tiebreak (W5's definition) |
| **B. opportunity** | `prior_opp_pg` | (targets + carries) per game |
| | `prior_tsh` | mean target share |
| **C. role** | `prior_snap` | mean offensive snap share |
| | `prior_games` | games played |
| | `has_prior` | 1 if the player played in S − 1 |
| **D. efficiency** | *none* | W8 and W9 found no robust efficiency mechanism, so none is included. This is a pre-registered choice, not an omission |

**Not included:** receptions (inside `prior_opp_pg`'s role via targets), routes (absent from every
source), and anything from season S or later.

**Missing values:** CatBoost handles them natively. For 2015 training rows everything is missing
("unknown", not "no prior season").

**What Alpha already has.** Its 3-game lags cross season boundaries, so in Week 1 Alpha sees the
previous season's last 3 games. Its season-to-date features reset each season. The new information
is the **full-season level and role**, not "any prior-season data". §7 measures how much of it
duplicates what Alpha holds.

---

## 3. Arms

| arm | definition | role |
|---|---|---|
| **A: CURRENT ALPHA** | production's stored weekly predictions; the one-change trainer with no added feature reproduces them exactly (G1) | control |
| **B: ALPHA + HISTORICAL** | production's CatBoost, hyperparameters, MAE loss and walk-forward `[2015, S−1]`, plus the 7 features. **Identical to W9's `ALPHA_PLUS_DURABLE`** (G3 proves it) | **the test** |
| **C: HISTORICAL-ONLY** | rank by `prior_ppg`, descending; players with no prior season last, in `player_id` order. No model, no Alpha tiebreak | diagnostic: is there ranking information in history alone? |
| N: NULL | B with the 7 features permuted across players within each season (W9's shuffled arm) | adding 7 unrelated columns must do nothing |
| ablations B−prod, B−opp, B−role | B minus one category | **attribution only**, never selection |

**ECR is the independent benchmark only.** It is not a feature, target, tiebreak or selector
anywhere (G5).

---

## 4. Metrics

| | metrics |
|---|---|
| **positional** (RB, WR, TE) | capture@5, @10, @20, @50; Spearman; Kendall; pairwise accuracy; precision@10 |
| **FLEX** (existing pooled path, no FLEX model) | capture@10, @25; Spearman; pairwise |
| **point diagnostics** (secondary, never a verdict input) | MAE, RMSE and bias against realized points; calibration by predicted decile |

**Periods** (W9's, fixed by week number):

| period | weeks | evaluated weeks |
|---|---|---:|
| EARLY | 1–6 | 24 |
| MID | 7–12 | 30 |
| LATE | 13–17 | 25 |

**Statistics:** 79 weeks, paired within week, bootstrap over weeks (10,000 resamples, seeds 0–9).
MDE is the CI half-width. W–L–tie counts, and Wilcoxon.

---

## 5. Verdict criteria — fixed now, evaluated in this order

A **success cell** is capture@5 or capture@10 at **RB or WR**.

| order | verdict | criterion |
|---|---|---|
| 1 | **SUCCESS** | S1–S5 all hold for at least one success cell (below) |
| 2 | **HARM** | a guardrail breach, **and** no cell (any position, capture@5 or @10) meets S1 over the full season, **and** no EARLY-period capture@5 or @10 effect at any position is at least +0.02 with a CI excluding 0 |
| 3 | **PARTIAL** | any position's capture@5 or @10 meets S1 over the full season, **or** any position's EARLY-period capture@5 or @10 effect is at least +0.02 with a CI excluding 0. Any breach is reported as a tradeoff, never averaged away |
| 4 | **NO EFFECT** | anything else |

**The five SUCCESS conditions, at the success cell:**

- **S1:** B − A is at least **+0.02** (the program's practical bar, about the measured MDE), with a
  95% CI excluding 0.
- **S2 (consistent):** the per-season point estimate is positive in at least 4 of 5 seasons,
  **and** the CI excludes 0 in at least 4 of 5 leave-one-season-out folds.
- **S3 (narrows the ECR gap):** (B − A) / (ECR − A) ≥ ⅓ at that cell.
- **S4 (early):** the EARLY-period effect is positive and at least the LATE-period effect (point
  estimates).
- **S5:** no guardrail breach anywhere.

**A guardrail breach** is a B − A difference with a CI excluding zero, **negative**, and of
magnitude at least **0.005**, in any of:

- capture@5, @10, @20 or @50 at any position;
- Spearman or pairwise accuracy at any position;
- FLEX capture@10, capture@25, Spearman or pairwise accuracy.

**Known in advance:** WR capture@10 meets S1 (+0.022, CI excludes 0). S3 at WR capture@10 is about
0.70, using W8's ECR − A of +0.032. So SUCCESS at WR turns on S2, S4 and S5, which are unseen.

**Half-PPR is a replication only and never selects.**

---

## 6. Diagnostics tied to the W4–W9 problem

1. **The ECR gap.** ECR − A against ECR − B, at every metric. W8's decomposition of ECR − B,
   asking whether the usage-surprise piece `G_S` shrinks.
2. **The W5 cliff.** Capture@10 against a same-Spearman copula null (W5/W6's construction,
   unchanged), for A and B.
3. **The W5 misses.**
   - FALSE POSITIVE: predicted top-10, finished outside the realized top-24.
   - FALSE NEGATIVE: realized top-5, predicted outside the top-24.
   - Both are counted per week for A and B and paired.
4. **Quiet established players.** Player-weeks where the prior-season ELITE tier (rank ≤ 12) meets
   a last game below the player's `prior_ppg`. Among those that finished in the realized top 10:
   how many does each board put in its top 10? Pooled, with a week-cluster bootstrap.
5. **Movement attribution.** B − A capture@10 split exactly by the category of the players who
   enter or leave the top 10. Categories are mutually exclusive, first match wins:

   | category | definition |
   |---|---|
   | `QUIET_STAR` | ELITE, and last game < `prior_ppg` |
   | `SMALL_SAMPLE` | fewer than 3 games so far this season |
   | `ROLE_STRONGER_BEFORE` | `prior_opp_pg` − recent 3-game opportunity ≥ 3 |
   | `ROLE_STRONGER_NOW` | recent − prior ≥ 3 |
   | `OTHER` | none of the above |

   Also reported: the players most often rescued into the top 10 correctly, and most often
   promoted wrongly. The whole population comes first; examples only illustrate it.
6. **By period:** every B − A metric in EARLY, MID and LATE.

---

## 7. Is history new information? (brief §13)

1. The correlation of each historical feature with Alpha's closest current feature. For example,
   `prior_ppg` against `fp_ppr_avg_season_to_date` and against `fp_ppr_avg_last3`, by period.
2. **The R² of each historical feature linearly predicted from Alpha's 11 current features**, by
   period, over the evaluated player-weeks. A low EARLY R² and a high LATE R² means history is
   new information early and redundant late.
3. **The decisive test:** B − A itself. Does history improve rankings with current-season
   information already present?
4. **Ablations** (attribution only): which category's removal takes away B's effect.

---

## 8. Robustness

- Leave-one-season-out and per-season for every primary cell.
- Half-PPR.
- Dependence checks: by position, by season and by depth (capture@5, @10, @20, @50).
- **Null arm N:** its primary-cell effects must include 0 (gate G12).

---

## 9. 2026: the out-of-sample protocol, frozen now

**The repository contains no 2026 data.** `player_week_stats`, `player_week_features` and `games`
end at 2025, and production's weekly predictions end at 2025. W10 therefore cannot test 2026, and
does not claim confirmation.

**Frozen for later.** Once the 2026 regular season (weeks 1–17) and production's 2026 weekly
predictions are ingested:

- run `scripts/research/w10_historical.py --seasons 2026`, with the **same** 7 features, the same
  arm B trained through 2025, and the same metrics;
- **2026 confirms W10** if the WR capture@10 **and** capture@5 B − A point estimates are both
  positive **and** the WR capture@10 CI excludes 0;
- otherwise it does not confirm. A 16-week season has roughly 1.4× the 79-week MDE, so a null
  there is weak evidence and will be reported as such.

**No 2026 data may inform any W10 choice.**

---

## 10. Validity and leakage gates — all must pass before any result is read

| gate | check |
|---|---|
| **G1** | parity: the one-change trainer with no added feature reproduces production exactly |
| **G2** | prior-season is prior: deleting every season ≥ S moves 0 durable values for S; the features are constant within a season |
| **G3** | **arm B is W9's arm:** B's per-week W8-decomposition cells equal W9's committed `AD` cells exactly |
| **G4** | no future games, injuries or roles in any feature: no injury, depth, news, Vegas or realized token in the 7 features; scrambling season S's outcomes changes no feature for S |
| **G5** | ECR never a feature: every training call is a declared arm, and its frame is `durable_panel` only |
| **G6** | walk-forward: no training frame contains the predicted season |
| **G7** | joins and alignment: unique (player_id, season) durable keys; `prior_games` for 300 seeded player-seasons equals a direct count of season S − 1 rows |
| **G8** | no look-ahead through aggregates: the durable table is identical when its input rows arrive in reverse order |
| **G9** | the universe and cutoff equal W7–W9's; arm A's cells equal W8/W9's committed `CF_A` cells |
| **G10** | determinism: two runs byte-identical |
| **G11** | upstream: W5–W9 (8 artifacts) byte-identical |
| **G12** | null: arm N's capture@5 and @10 effects have CIs including 0 at every position |

**If a gate fails: stop, fix, re-run, document, then read.**

---

## 11. A priori predictions: unknown quantities only

1. **WR S2 holds:** positive in at least 4 of 5 seasons, with at least 4 of 5 LOSO folds
   significant.
2. **WR S4 holds:** the EARLY effect is larger than the LATE effect.
3. **No guardrail breach at WR or TE.** RB may show small negative top-end changes.
4. Spearman improves slightly at WR and TE.
5. **Verdict: SUCCESS**, carried by WR.
6. **The WR cliff shrinks** (−0.080 toward −0.06).
7. WR false positives decrease.
8. **The historical-only baseline C is much worse than Alpha** (capture@10 −0.03 to −0.06).
9. The **production** category drives most of the WR gain in the ablations.
10. The null arm does nothing.
11. The R² of `prior_ppg` from current features is below 0.3 EARLY and above 0.5 LATE.
12. RB shows no effect; the W9 RB null persists.

---

## 12. What W10 may NOT do

- Modify production or `models/`, `league/`, `api/`, `cli.py`, `market/`, `features/`,
  `identity/`, `ingest/` or `sources/`.
- Add ECR, expert rankings, news, injuries or Vegas.
- Tune after seeing results.
- Add feature variations or lookback searches.
- Select anything using an ablation or Half-PPR.
- Use 2026.
- Call the result confirmation.

---

## 13. Amendments

### A1 (2026-09-26): instrument clarifications, before any W10 result was computed

Written while building the runner and gates, before any W10 quantity existed. None of these
changes an arm, feature, metric, threshold or verdict rule. Each one pins down a definition the
text above left implicit.

1. **"Last game"** in §6.4–6.5 is the player's most recent appearance's realized PPR points,
   `T_XFP__BL_LAST` in the W7 panel (its `fp_l1` lag). This is exactly the input to W9's
   `quiet_last` flag. **"Recent 3-game opportunity"** is `targets_avg_last3 + carries_avg_last3`,
   Alpha's own features, on the same per-game scale as `prior_opp_pg`. **"Games so far this
   season"** is `games_played_prior`, which is season-partitioned.
2. **G9's comparison targets:**
   - W8's committed `CF_A` and `ECR` counterfactual cells (positional);
   - W7's committed `ranking` cells (positional and FLEX, `CF_A` and `ECR`) and its `CF_A` cliff;
   - W9's committed per-week ECR − A decomposition cells (`{pos}|ECR`, Full and Half-PPR).

   W6's FLEX cells are **not** a target. W6 pooled every control prediction into FLEX, while
   W7–W10 pool only the players on each positional board, so the two universes legitimately
   differ.
3. **§9 needs a 2026 durable table.** W9's `durable_table` hard-coded seasons up to 2025. It gains
   a `through` parameter whose default, 2025, reproduces W9 exactly. The W10 runner passes the
   last evaluated season and aborts if any evaluated season lacks durable rows. The W9 artifact
   is re-reproduced after this edit (G11).
4. **Point diagnostics are Full PPR only.** Every model predicts PPR points, so Half-PPR has no
   matching target.
5. **G5 is checked statically.** The runner has exactly three training call sites:
   - B, frame `dp`;
   - N, frame `w9.durable_panel(..., shuffle=True)`;
   - the ablation loop, frame `dp[keys + keep]`.

   `dp` is `w9.durable_panel(..., shuffle=False)`, and `durable_table` reads only
   `player_week_stats`.
6. **G4's scramble:** season S's points, targets, carries, target share and snap share are
   replaced by deterministic hash noise for S ∈ {2022, 2025}. Season S's durable rows must not
   move, and as a positive control season S + 1's must.
7. **G7** also checks that 300 seeded `has_prior = 0` rows have no season S − 1 game.
