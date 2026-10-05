# W14 — Out-of-sample 2026 validation of W10: interim look 1 (weeks 1–3)

**Status: INTERIM LOOK COMPLETE. The holdout continues.**

**Pre-registered verdict at this look: INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT**
(category D, a valid test with too few weeks). It is not a failure, and not a success.

**What that means:**

- **In the first three 2026 weeks, W10 points the way it did in 2021–2025.**
  - WR capture@10 B − A **+0.078** (weeks −0.052, +0.157, +0.128).
  - WR capture@5 **+0.088**.
  - FLEX capture@10 **+0.064**.
  - All sit inside the range W10's own history predicts for 3 weeks (90th, 86th and 88th
    percentile).
- **Three weeks cannot confirm or refute anything.**
  - The exact sign-flip p is **0.50** for WR capture@10. With 3 weeks the smallest possible p is
    0.25.
  - The 3-week bootstrap intervals are roughly the range of the three weekly values, not 95%
    intervals.
  - The pre-registered rule reads no direction before 8 weeks.
- **A caution from the null arm.** W10 with its 7 features shuffled also gained +0.037 WR
  capture@10 over these weeks, about half of B's gain. Historically it did nothing (−0.007).
  Some of the early 2026 gain may be the model reshuffling itself (W13's lesson).

**W10 §9's confirmation rule is not yet evaluable.** It is applied once, after week 17.

**Provenance** (every amendment came before any 2026 result was read):

| step | commit |
|---|---|
| pre-registration | `de5efe0` |
| A1: the weekly production command | `eb031bd` |
| runner and gates | `f33aba6` |
| A2: restore the canonical row order | `cd3c63e` |
| A3: G6 at W10's positions | `225353b` |
| A4: G3's enumerated crosswalk revision | `a620389` |
| results artifact, committed unread | `956b4d2` |

**All 12 gates pass. Research only. Production diff EMPTY. ECR is a benchmark only.** No PR, no
merge.

---

## 1. Research question

> Does the W10 historical-player-knowledge improvement generalize to completely untouched 2026
> weekly rankings?

This is an **out-of-sample validation, not an experiment.**

- W10 found its gain on 2021–2025, the same weeks that shaped the hypothesis (W10 §0).
- This project had never seen 2026.
- **Primary cell: WR capture@10, B − A, Full PPR.** It is the cell W10's frozen §9 rule turns on.
- FLEX capture@10 is the key secondary cell.

## 2. W10 frozen specification

| | |
|---|---|
| **A: current Alpha** | production's weekly CatBoost predictions for 2026, written by production's own `alpha-squad train established` (A1) |
| **B: W10** | `ALPHA_PLUS_HISTORICAL`: production's CatBoost (200 iterations, depth 4, lr 0.05, MAE, seed 42) on its 11 weekly features **plus W10's 7 prior-season features** (`prior_ppg`, `prior_games`, `prior_opp_pg`, `prior_tsh`, `prior_snap`, `prior_rank`, `has_prior`, all from 2025 games) |
| training | walk-forward by season: **[2015, 2025] for every 2026 week**, per position RB/WR/TE. No 2026 outcome in any training set (G5) |
| universe, boards, scoring | W10's and W2's, unchanged: canonical Friday ECR board ∩ played ∩ Alpha-covered; A's rank as tiebreak; Full PPR (primary) and Half-PPR |
| code | **every W10 code-path file is byte-identical to W10's commit `5de17c1`** (G2). The W14 runner calls W10's own `trainings`, `analyse`, `summaries`, `cliffs` and `calibration`; it fits no model of its own |
| the frozen protocol, verbatim | `w10_historical.py --seasons 2026` was also run as written. Its cells equal W14's for every eligible week (G10: 3,690 values, 0 mismatches) |

**Nothing was added or changed:**

- no ECR, injury, news or depth chart;
- no 2026-specific information;
- no tuning.

**QB, K and DST** are not part of W10's model, so they are not evaluated.

## 3. 2026 frozen protocol

**Pre-registered:** `docs/weekly/W14_PREREGISTRATION.md`, committed before any 2026 outcome was
ingested. **Four amendments**, each before any 2026 result was read:

| # | what was found | correction |
|---|---|---|
| **A1** | the pre-registration named production's season-level command; W10's arm A is written by the weekly `train established` | the isolated database was deleted and rebuilt with the right command |
| **A2** | production's `features build` rewrites the physical row order of every feature row. Its loader has no `ORDER BY`, and CatBoost is order-sensitive. Identical 2015–2025 data trained a different model: G1 history parity fell to 0 / 26,097, max 2.69 points | the ≤ 2025 rows were restored to the canonical physical order (verified against production's own loader), and production's 2026 run was redone. G1 history parity is then 26,097 / 26,097 exact |
| **A3** | G6's rebuild differed from the stored features only in K/DST rows, because production builds those after the feature step | G6 compares features at W10's positions (RB/WR/TE) |
| **A4** | DynastyProcess's newer crosswalk dropped two 2025 depth players' FantasyPros ids (5 mappings lost, 4 gained, 0 changed out of about 4,776) | G3 accepts only differences explained by that enumerated revision. W10's headline numbers are unchanged under it (WR capture@10 +0.0223 [+0.0068, +0.0384]) |

**Data path.** Production's CLI, unchanged, in an isolated copy of the database
(`data/w14/alpha_squad_2026.duckdb`):

1. `sources ingest` 2026;
2. `identity build`;
3. `features build` 2026;
4. A2's row-order restore;
5. `train established` 2026.

**The canonical database was never written** (G4: sha256 unchanged).

**Cutoff and cadence.**

- Each week is scored against its **canonical Friday ECR board** (W2): the latest weekly scrape at
  most 7 days before the first Sunday game.
- Model inputs for week *w* use only games before week *w*, plus 2025.
- No other snapshot was used or reconstructed.

## 4. Anti-peek audit

| | |
|---|---|
| 2026 rows in the repository's outcome tables before W14 | **none** (canonical `player_week_stats`, `games`, `player_week_features`, `weekly_projection_snapshot`, `team_week_stats`; G4) |
| **2026 outcome-derived artifact found** | **nflverse Next Gen Stats snapshots** (captured 2026-09-19/20) held 66 / 70 / 157 rows of 2026 weekly NGS. **No module on the W14 runner's path reads NGS** (G4: all 43 repository modules it loads were scanned). Excluded |
| other 2026 content already present | ECR history through 2026-09-18 (benchmark only); pre-season dynasty values, the draft class and combine (unused) |
| read before freezing | the 2026 schedule columns and the ECR scrape dates only, to find which weeks have a Friday board |
| console output | every production command wrote to logs that were not read for results. Production's own season-evaluation printout was never looked at |
| frozen before scoring | model, features, transformations, training window, eligibility, scoring, ranking, cutoff, metrics and the decision rule (pre-registration §2–§7) |

## 5. Eligible 2026 weeks

| week | Friday board | games in data | status |
|---:|---|---:|---|
| 1 | 2026-09-11 | 16 / 16 | **evaluated** |
| 2 | 2026-09-18 | 16 / 16 | **evaluated** |
| 3 | 2026-09-25 | 16 / 16 | **evaluated** |

**Eligible means:** every scheduled game is in the data, every scheduled team has stats, and the
last kickoff is at least 6 hours before the data capture (2026-10-05 13:10 UTC).

**Universe per week:**

| week | WR | RB | TE | FLEX |
|---:|---:|---:|---:|---:|
| 1 | 129 | 74 | 67 | 269 |
| 2 | 140 | 88 | 68 | 296 |
| 3 | 133 | 78 | 75 | 286 |

## 6. Missing and unavailable weeks

| week | status | why |
|---|---|---|
| **4** | **pending data** | its Friday board exists (2026-10-02), but NO–ATL kicks off Monday 5 October at 20:15 ET, after the data capture. It is **not** scored "minus the Monday game", which would silently drop that game's players. It joins the next look once nflverse publishes the game |
| 5–17 | not yet played | they join later looks as each completes |
| 18 | never | no weekly board; W10 evaluates weeks 1–17 |

## 7. Primary FLEX results

**Full PPR, 3 weeks, B − A.**

- "interval" is the 3-week bootstrap, roughly the range of the weekly values (see §13).
- p is the exact sign-flip test.

| metric | B − A | weeks 1 / 2 / 3 | W–L–T | interval | p |
|---|---:|---|---|---|---:|
| **capture@10** | **+0.064** | +0.050 / +0.028 / +0.114 | 3–0–0 | [+0.028, +0.110] | 0.25 |
| capture@5 | −0.041 | −0.075 / 0.000 / −0.048 | 0–2–1 | [−0.075, 0.000] | 0.50 |
| capture@20 | +0.052 | +0.026 / +0.052 / +0.077 | 3–0–0 | [+0.026, +0.075] | 0.25 |
| Spearman | +0.030 | +0.042 / +0.029 / +0.017 | 3–0–0 | — | 0.25 |
| pairwise | +0.013 | — | 3–0–0 | — | 0.25 |
| precision@10 | 0.000 | — | 1–1–1 | — | 1.00 |
| regret@10 (points; lower is better) | **−18.8** | −16.3 / −8.2 / −31.8 | B better in 3 | — | 0.25 |
| top-10 overlap, B with A | — | 0.9 / 0.8 / 0.8 | — | — | — |

**FLEX capture@10 levels:**

| board | capture@10 |
|---|---:|
| ECR | 0.721 |
| **B** | **0.700** |
| A | 0.636 |

B closes about three quarters of A's FLEX gap to ECR in these weeks. The FLEX top 5 leans the
other way (−0.041), as it did in 2021–2025 (−0.013).

## 8. RB results

| B − A | capture@5 | capture@10 | capture@20 | Spearman |
|---|---:|---:|---:|---:|
| 2026, weeks 1–3 | −0.004 | +0.007 (1–1–1, p 1.00) | +0.023 | +0.026 (3–0, p 0.25) |
| W10, 2021–2025 | −0.004 | +0.000 | +0.000 | +0.004\* |

**RB's top of the board is unchanged, as in W10.** Whole-board ordering is better.

## 9. WR results: the primary cell

| B − A | value | weeks 1 / 2 / 3 | W–L–T | interval | p |
|---|---:|---|---|---|---:|
| **capture@10** | **+0.078** | −0.052 / +0.157 / +0.128 | 2–1–0 | [−0.052, +0.157] | **0.50** |
| capture@5 | +0.088 | 0.000 / +0.106 / +0.157 | 2–0–1 | [0.000, +0.154] | 0.50 |
| capture@20 | +0.031 | +0.035 / +0.012 / +0.046 | 3–0–0 | — | 0.25 |
| Spearman | +0.020 | +0.018 / +0.026 / +0.017 | 3–0–0 | — | 0.25 |
| precision@10 | +0.100 | — | 2–1–0 | — | 0.50 |
| regret@10 (points) | −20.3 | +13.5 / −44.2 / −30.2 | B better in 2 | — | 0.50 |

**WR capture@10 per week:**

| week | A | B | ECR |
|---:|---:|---:|---:|
| 1 | 0.664 | 0.612 | 0.662 |
| 2 | 0.496 | 0.653 | 0.726 |
| 3 | 0.631 | 0.759 | 0.784 |

**Means:**

| board | WR capture@10 |
|---|---:|
| ECR | 0.724 |
| **B** | **0.675** |
| A | 0.597 |

Against A, ECR is ahead by +0.127 and B by +0.078: **B covers about 61% of the gap.**

## 10. TE results

| B − A | capture@5 | capture@10 | capture@20 | Spearman |
|---|---:|---:|---:|---:|
| 2026, weeks 1–3 | +0.114 | +0.082 (2–1, p 0.50) | +0.026 | +0.049 (3–0, p 0.25) |
| W10, 2021–2025 | +0.012 | +0.004 | +0.007 | +0.007\* |

**Larger than W10's TE history, on three weeks.** TE was never part of W10's claim.

## 11. Half-PPR results

**Robustness only; nothing was tuned on it.**

| B − A | 2026 Half-PPR | 2026 Full PPR |
|---|---:|---:|
| WR capture@10 | **+0.082** (2–1, p 0.50; band 92nd percentile) | +0.078 |
| WR capture@5 | +0.091 | +0.088 |
| FLEX capture@10 | +0.067 (3–0, p 0.25) | +0.064 |
| RB capture@10 | +0.004 | +0.007 |
| TE capture@10 | +0.087 | +0.082 |

**Same direction everywhere.** The same rule gives the same verdict: INCONCLUSIVE — CONTINUE.

## 12. Week-by-week paired results (B − A, Full PPR)

| week | WR c@10 | WR c@5 | FLEX c@10 | FLEX c@5 | RB c@10 | TE c@10 | WR overlap | FLEX regret@10 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | −0.052 | 0.000 | +0.050 | −0.075 | +0.049 | −0.001 | 0.9 | −16.3 |
| 2 | +0.157 | +0.106 | +0.028 | 0.000 | −0.028 | +0.066 | 0.7 | −8.2 |
| 3 | +0.128 | +0.157 | +0.114 | −0.048 | 0.000 | +0.182 | 0.8 | −31.8 |

Overlap is the share of B's top 10 that is also in A's top 10. For regret, negative means B left
fewer points on the table.

## 13. Confidence intervals

**With 3 weeks a bootstrap over weeks is not a 95% interval.** Resampling 3 values gives about
the range of those values: WR capture@10's "interval" [−0.052, +0.157] is exactly its worst and
best week.

**The honest uncertainty comes from W10's own history.** The weekly SD of WR capture@10 B − A is
0.0725, so a 3-week mean carries about **±0.082** at 95%. Pre-registration §6 stated this in
advance.

| | weeks needed for a ±0.034 interval | P(CI excludes 0) if W10's +0.022 is true |
|---|---:|---:|
| WR capture@10 | 17 | 0.24 |

**Even a full season will most likely not confirm W10 under §9.**

**Guardrails.** No guardrail difference is negative with an interval excluding 0. Given the
above, that is unsurprising and not informative.

## 14. Sign-flip / permutation results

**Exact two-sided tests**, enumerating all 2³ = 8 sign patterns:

| cell | p | note |
|---|---:|---|
| **WR capture@10** | **0.50** | 2 weeks up, 1 down |
| WR capture@5 | 0.50 | |
| FLEX capture@10 | 0.25 | 3 of 3 weeks positive, the smallest p 3 weeks can produce |
| WR / FLEX / RB / TE Spearman | 0.25 | |
| FLEX regret@10 | 0.25 | |

**Nothing can be significant at 3 weeks.**

## 15. Historical vs 2026 comparison

**Question: does 2026 look like a plausible draw from W10's effect?**

| WR capture@10, B − A | value |
|---|---:|
| **2026, weeks 1–3** | **+0.078** |
| W10, 2021–2025 (79 weeks) | +0.022 [+0.007, +0.038] |
| W10 leave-one-season-out folds | +0.021 / +0.023 / +0.022 / +0.022 / +0.023 |
| W10 per season, 2021 / 2022 / 2023 / 2024 / 2025 | +0.028 / +0.019 / +0.023 / +0.023 / +0.018 |
| **each season's first 3 evaluated weeks**, 2021 / 2022 / 2023 / 2024 / 2025 | **+0.110 / +0.012 / +0.111 / +0.073 / +0.012** |
| W10's EARLY period (weeks 1–6, 24 weeks) | +0.038 |
| **predictive band for a 3-week mean** (from W10's 79 weeks) | 2.5–97.5%: [−0.055, +0.107]; **2026 at the 91st percentile** |

**Answer: yes.**

- 2026's first three weeks fall **inside the spread of W10's own early-season windows**, three of
  which were larger or about as large. They are well inside the 3-week predictive band.
- History said early weeks are where W10 helps most: when the current season has almost no games,
  last season is most of what there is to know.
- **The same holds at WR capture@5** (+0.088; 86th percentile) and **FLEX capture@10** (+0.064;
  88th percentile).
- **Nothing in 2026 is reversed or degraded.**

## 16. W5/W10 WR cliff comparison

**The W5 "cliff":** how far a board's WR capture@10 falls short of a same-Spearman random-order
null (W5/W6 copula construction, unchanged).

| | A (current Alpha) | B (W10) |
|---|---:|---:|
| 2021–2025 | −0.080 [−0.100, −0.061] | −0.062 [−0.080, −0.043] |
| **2026, weeks 1–3** | **−0.074** | **−0.009** |

- **Current Alpha's cliff is still there in 2026,** the same size as before.
- **W10's board shows almost none in these three weeks.** Directionally this is W10's cliff
  reduction, larger than historically, but on 3 weeks; it is not called replicated.

**WR misses, per week:**

| | false positives (predicted top 10, finished outside the top 24) | false negatives (finished top 5, predicted outside the top 24) |
|---|---:|---:|
| 2026: A / B / ECR | 5.3 / 4.7 / 3.7 | 1.7 / 1.7 / 1.0 |
| 2021–2025: A / B | 4.3 / 4.1 | 1.6 / 1.5 |

**Quiet stars** (prior-season top-12 WRs coming off a quiet game who finished top 10):

| | hits | A | B | ECR |
|---|---:|---:|---:|---:|
| 2026 | 4 | 0 | 1 | 2 |
| 2021–2025 | 118 | 0.51 | 0.66 | 0.75 |

## 17. Limited mechanism analysis

**From W10's own outputs, after the primary result was written down.** No new feature.

**WR movement attribution of B − A capture@10 (+0.078):**

| category | 2026 | 2021–2025 |
|---|---:|---:|
| QUIET_STAR | +0.039 | +0.050 |
| SMALL_SAMPLE | +0.039 | 0.000 |
| ROLE_STRONGER_NOW | 0 | −0.050 |
| ROLE_STRONGER_BEFORE | 0 | +0.008 |
| OTHER | 0 | +0.014 |

**Movers: 6 into B's top 10** (2 quiet stars, 4 small-sample), **6 out** (all small-sample).

**Why the categories look different:**

- In weeks 1–3 every player has fewer than 3 games, so nearly everyone is SMALL_SAMPLE by
  definition. That is the early-season situation history pointed to.
- The role-change category that cost W10 over 2021–2025 (players whose role grew this season) is
  empty this early.
- **Expect it to reappear as 2026 goes on.**

**Who moved:**

- **Rescued into the top 10 correctly:** CeeDee Lamb (2 weeks), Davante Adams, Ja'Marr Chase (a
  quiet star).
- **Dropped correctly:** Jalen Coker (2), Devaughn Vele (2), Caleb Douglas. B pushed them out and
  they did not finish top 10.
- **Promoted wrongly:** George Pickens (quiet star), Rashee Rice.
- **Dropped wrongly:** Parker Washington (finished top 10 after B pushed him out).

**W8 decomposition** of +0.078: usage surprise +0.044, conversion +0.043, forecastable usage
−0.009. Historically almost all of it was usage surprise (+0.024 of +0.022).

**RB:** quiet stars +0.016, small sample −0.010; quiet-star recall A = B = 0.89 (9 hits). **TE:**
quiet stars +0.060; recall 0.5 → 0.6.

**The null arm (reported, not gated).** W10 with its 7 features shuffled within the season:

| N − A | 2026 | 2021–2025 |
|---|---:|---:|
| WR capture@10 | **+0.037** (+0.036 / +0.016 / +0.059) | −0.007 |
| FLEX capture@10 | +0.021 | −0.003 |

- So over these 3 weeks, **half of B's WR gain is matched by adding uninformative columns.**
- B − N is +0.041.
- This is the refit noise W13 measured, at a sample size where it is as large as the effect. It is
  the strongest reason not to read 3 weeks.

## 18. Leakage audit

| check (brief §20) | how | result |
|---|---|---|
| 2026 outcomes never a feature | B's frame is exactly keys + W10's 7 prior-season columns (G7). Production's 11 are lagged window features | pass |
| later weeks cannot influence earlier predictions | **G6, end to end.** For each week *w*, every 2026 row after *w* was deleted, features rebuilt with production's builders and A and B retrained: **bit-identical** RB/WR/TE features and A/B predictions (320, 320 and 326 player-weeks) | pass |
| no post-Friday or post-kickoff information | features end one game before week *w* (window frames; G6). The board is the Friday scrape. Week 4 is withheld until complete | pass |
| no future injury information | no injury, news or depth input anywhere (G2, G7) | pass |
| no future identity | 0 / 1,464 evaluated 2026 players without a canonical record; no team code outside `games` (G9). Crosswalk revisions enumerated (A4) | pass |
| historical features as W10 allows | 2026's prior-season features come from 2025 only. Training frames ≤ 2025 are identical to W10's environment (G3) | pass |
| training | no 2026 row in any training frame (G5) | pass |
| no peeking | canonical database unmodified; no NGS on the path (G4). Results artifact committed before being read | pass |

**Automated, committed assertions:**

- `scripts/research/w14_validity_gates.py`;
- the eligibility rule in `evaluation/weekly/holdout.py` (11 tests);
- the row-order restore (2 tests);
- in-runner gates: recomputed boards match W10's capture@10 (72 boards); evaluated weeks equal
  eligible weeks.

## 19. Reproducibility results

| check | result |
|---|---|
| **W5–W13 re-run on the canonical database** | **14 / 14 artifacts byte-identical** (G12) |
| **W10's committed cells** | byte-identical in that re-run. On the 2026 database every 2021–2024 cell and every prediction reproduces. The 2025 differences are fully explained by the enumerated crosswalk revision (G3, A4) |
| **G1 parity** | 1,270 / 1,270 production 2026 predictions and 26,097 / 26,097 for 2021–2025 reproduced exactly |
| **W14 twice** | byte-identical (sha256 `3dbb7f1276986e8e…`). A third run, inside G11, also identical |
| **frozen W10 protocol, verbatim** | equals W14's cells (G10) |

**Gate passes:**

- pass 3: G1–G11;
- final pass: G1–G5, G7–G10, G12. G6 and G11 were skipped there because they had already passed
  in pass 3 on the same artifact.

**Suite:** 1,907 tests pass. Lint clean. **Production diff EMPTY.**

## 20. Limitations

- **Three weeks.** Nothing is significant, or could be. The early weeks are also W10's historically
  strongest period, so they over-represent the effect a full season would show.
- **The null arm matched half the WR gain** in these weeks (§17). Refit noise is as large as the
  effect at this sample size.
- **One training order.**
  - Row order alone moves single-seed CatBoost predictions by up to 2.69 points (A2).
  - The 2026 estimate, like every W5–W13 estimate, is conditional on one order and one seed.
  - Seed or order averaging was not pre-registered and was not done.
- **Bootstrap intervals are degenerate at n = 3** (§13). The exact sign-flip test is the valid one.
- **Data vintage.**
  - The newer crosswalk dropped 5 and added 4 FantasyPros mappings (A4).
  - 2026 boards use it, so a handful of players may be unjoinable for both arms alike.
- **Production observation, not a W14 input.** Production's `features build` writes feature rows
  before computing K/DST points, so 2026 K/DST feature rows are incomplete (A3). W10's positions
  are unaffected.
- **The universe is players who played** (W2). Avoiding inactive players is not measured.
- **Repeated looks.** Interim looks can only end the holdout early by finding a contradiction
  (§7, C). REPLICATED is decided once, at the final look.

## 21. Verdict

> **D. INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT.** The test is valid: all 12 gates
> pass. Interim look, 3 eligible weeks.

**Pre-registered §7, in order:**

1. **Valid:** yes.
2. **NOT REPLICATED?** No.
   - The WR capture@10 interval is not below 0.
   - The 2026 mean (+0.078) is not below the predictive band's 2.5th percentile (−0.055).
3. **REPLICATED** is a final-look verdict only.
4. **PARTIAL** at an interim look needs at least 8 weeks.
5. **Result: INCONCLUSIVE — CONTINUE.**

**Not chosen, and why:**

- **B (PARTIAL REPLICATION):** every WR and FLEX point estimate does point W10's way. But a
  3-week sign comes out positive about 70% of the time even if W10 is real, and 50% if it is not.
  The rule fixed before the data refuses to read it.
- **C (NOT REPLICATED):** nothing contradicts W10.

**W10 §9:** not yet evaluable; it is applied once, after week 17.

## 22. Exact next research question

> **Does W10's WR top-10 gain over current Alpha hold through the rest of 2026, under this
> unchanged protocol?**

**How:**

1. **Next look:** as soon as week 4's Monday game is published, re-run the committed pipeline
   (§3, including A2's restore) and the committed runner and gates.
2. **The first informative look** is the first with **≥ 8 eligible weeks**, expected after
   week 8. There, PARTIAL REPLICATION becomes possible.
3. **The decisive look** comes after week 17: W10 §9 and REPLICATED / PARTIAL / NOT REPLICATED,
   once.
4. **Watch the null arm.** If N − A stays near B − A, the early gain was refit noise.

**No model, feature, threshold or rule changes in between.**

---

## Predictions (pre-registration §11)

| # | prediction | outcome |
|---|---|---|
| 1 | 3 eligible weeks; week 4 unavailable | **right** |
| 2 | verdict INCONCLUSIVE — CONTINUE | **right** |
| 3 | WR capture@10 positive, inside the band, CI including 0 | **right:** +0.078, 91st percentile, [−0.052, +0.157] |
| 4 | WR capture@5 positive | **right:** +0.088 |
| 5 | FLEX capture@10 positive with a CI including 0 | **partly right:** positive (+0.064), but the 3-week bootstrap interval excludes 0 (3 of 3 weeks positive); exact p 0.25 |
| 6 | exact sign-flip p ≥ 0.25 | **right** (necessarily) |
| 7 | no guardrail difference with a CI excluding 0 | **partly right:** no negative one, but several *positive* differences have 3-week intervals excluding 0 |
| 8 | Half-PPR agrees in sign at WR capture@10 | **right:** +0.082 |
| 9 | WR movement mostly SMALL_SAMPLE and QUIET_STAR | **right:** +0.039 each, nothing else |
| 10 | G1 holds for 2026 | **right:** 1,270 / 1,270 |

**Score:** 8 right, 2 partly right, 0 wrong.

## Validity

All twelve gates pass (`scripts/research/w14_validity_gates.py`):

| gate | result |
|---|---|
| G1 parity | 2026 1,270/1,270; 2021–2025 26,097/26,097 exact |
| G2 W10 frozen | 0 files changed since `5de17c1`; one `w10.trainings` call; no own model fit; 7 features as frozen |
| G3 history intact | training frames and durable table identical. W10 re-run: 4,898 cells, differing only in seven 2025 weeks, every difference explained by the 9 revised crosswalk mappings (A4) |
| G4 anti-peek | canonical database unmodified; no 2026 outcome rows in it; no NGS reader among the runner's 43 repository modules |
| G5 walk-forward | 0 training frames with 2026 rows |
| G6 later weeks | bit-identical RB/WR/TE features and A/B predictions with all later weeks deleted, for weeks 1, 2 and 3 |
| G7 inputs | B adds exactly W10's 7 columns |
| G8 eligibility | evaluated = eligible = weeks 1–3; schedule sha256 matches; week 4 PENDING_DATA (NO–ATL) |
| G9 identity | 0/1,464 unresolved players; no stray team codes |
| G10 W10's own numbers | 3,690 values equal to the verbatim W10 run; 72 recomputed boards match W10's capture@10 |
| G11 determinism | byte-identical |
| G12 upstream | W5–W13 14/14 byte-identical |

## Files

| file | role |
|---|---|
| `docs/weekly/W14_PREREGISTRATION.md` | the frozen protocol and amendments A1–A4 |
| `src/alpha_squad/evaluation/weekly/holdout.py` | eligibility, exact sign-flip p, predictive band, W10 §9, the decision rule |
| `tests/unit/test_weekly_holdout.py` | 11 tests |
| `scripts/research/w14_2026_validation.py` | the runner: W10's own functions, eligible weeks, statistics, history, decision |
| `scripts/research/w14_row_order.py` + `tests/unit/test_w14_row_order.py` | A2's restore (2 tests) |
| `scripts/research/w14_validity_gates.py` | G1–G12 |
| `reports/weekly/w14_results.json` | every eligible-week cell, paired statistics, weekly table, history, mechanism, decision and provenance (snapshot sha256s, schedule manifest) |

**Data, gitignored and reproducible:**

- `data/w14/`: the isolated 2026 database, raw 2026 snapshots, and the schedule snapshot (sha256
  `9823779f…`).
- Production's pipeline logs are under `data/w14/logs/`.

---

## LAYMAN'S TERMS

**What Claude did:**

- Wrote down exactly how to test W10 on the new 2026 season, and what would count as a pass,
  before looking at any 2026 result.
- Built 2026 rankings for weeks 1–3 with today's Alpha and with W10, unchanged.
- Checked twelve ways that nothing leaked from later weeks or broke along the way.

**What it means:**

- So far W10 does what it did before: it picks better wide receivers. But three weeks is far too
  little to be sure, and some of the edge may just be the model reshuffling.

**Next step:**

- Keep scoring each 2026 week the same way, and decide only once the season has enough weeks.
