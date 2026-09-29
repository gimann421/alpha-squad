# W13 — Pre-registration: a player's own Friday injury designation and the FLEX top 10

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any W13 quantity comparing boards or
models was computed.

> **No change below after seeing results without a dated amendment here.**

Authority:

- `docs/weekly/W12_TIMESTAMPED_RESULTS.md` (where the hypothesis came from);
- `docs/weekly/W12_DATA_AUDIT.md` (the source and its timing);
- W10 (the base model);
- `CLAUDE.md`.

Decision record: D121.

---

## 0. What is already known: read this first

- **In W12, adding the player's own injury-report entry to W12's arm D** (W11's model + teammate
  features) raised FLEX capture@10 by **+0.016** (CI excluding 0) over the same model without it.
  The full timestamped arm beat W11's model by +0.018. But **against a permuted-feature null the
  gain was +0.009, not significant**.
- W13 tests the same two features **on the W10 base**, with no role or teammate features. **That
  B − A number is unseen.**
- **The 2021–2024 weeks produced this hypothesis. W13 is a cleaner re-test on the same weeks, not
  independent confirmation.** The independent test is 2026 (§9), and it is frozen now.

---

## 1. Hypothesis

> **H1:** adding a player's own Friday injury-report entry to W10's model raises weekly **FLEX
> capture@10**.

The test is ranking quality among players who played. It is not whether the player plays: the
program's universe (W2) is players who played, so avoiding inactive players is not something this
test can reward.

---

## 2. The exact feature: frozen, W12's "own" category with the A1 fix

**Source.** The NFL injury report via nflverse `injuries`, regular season, 2015–2024. It is loaded
by `w12_timestamped.injury_rows` and built by `injury_table`.

- **Timestamp field:** `date_modified` (UTC, the row's last modification), converted to
  America/New_York.
- **Cutoff:** **23:59:59 ET on the Friday before the week's first Sunday game.** This equals the
  canonical snapshot date in 62 of the 63 W13 weeks. The exception is 2021 week 14, whose board
  is a Saturday; there the Friday is used, which is stricter.
- **Rows used:** only the player's own team-week rows with `date_modified` ≤ cutoff. **Rows
  modified after the cutoff are treated as nonexistent** (W12 A1), and the W12 regression test
  `test_deleting_post_cutoff_rows_never_changes_a_feature` stays in the suite.

| feature | values |
|---|---|
| `own_status` | 0 = no designation (also Probable, Note, or not on the report); **1 = Questionable; 2 = Doubtful; 3 = Out** |
| `own_practice` | 0 = full or not listed; 1 = limited; 2 = did not participate (incl. "Out (Definitely Will Not Play)") |

**Rules:**

- **Multiple rows** for the same player-week (4 in all of 2015–2024): the most severe value.
- **No injury designation:** 0 on both.
- **No observable team report** (no row of the team is ≤ cutoff): both **missing**. CatBoost
  handles missing values natively.
- **Nothing else enters:** no teammate, depth-chart, news, ECR or other feature.

---

## 3. Weeks

**Primary: 2021–2024, 63 evaluated weeks** (the W5–W12 universe and Friday cutoff):

| season | weeks | count |
|---|---|---:|
| 2021 | 1–17 | 17 |
| 2022 | 2–17 | 16 |
| 2023 | 2–17 | 16 |
| 2024 | 4–17 | 14 |

- **2025 is excluded:** its injury file has no timestamp (W12 audit, Class B).
- **2026 is not used** (§9).
- **Training:** walk-forward `[2015, S − 1]`, as W10. Injury timestamps exist for all of
  2015–2024.

---

## 4. Arms

| arm | definition |
|---|---|
| CF_A | production's stored predictions (current Alpha), used for the WR guardrail |
| **A: W10** | `ALPHA_PLUS_HISTORICAL`, exactly W10's model. Gate G3 proves it |
| **B: W10 + own** | A + `own_status` + `own_practice`. Same CatBoost, hyperparameters, loss, target, walk-forward, universe and scoring |
| N: null | A + the two features **permuted jointly across players within (season, week, position)**, with W12's seeds |
| S: exploratory | A + `own_status` only (designation without practice). **Never a verdict input** |

**ECR is a benchmark only.**

---

## 5. Metrics

- **Primary:** FLEX capture@10, B − A, Full PPR, 63 weeks, through the existing pooled FLEX path.
  No FLEX model.
- **Secondary:**
  - FLEX capture@5, @20, Spearman, pairwise, precision@10, and **regret@10** (best top-10 points −
    the board's top-10 points, per week);
  - positional RB/WR/TE capture@10, @5 and Spearman.
- **Mechanism** (Full PPR, FLEX):
  - B − A capture@10 attributed exactly to the players entering or leaving the top 10, grouped by
    own status (NONE, Q, D, O, NO_REPORT) and by position;
  - movers' counts and realized points;
  - A's and B's bias (prediction − realized) by status group.

---

## 6. Statistics and the MDE

- **Unit: the week.** 63 paired weekly differences.
- Bootstrap over weeks: 10,000 resamples, seeds 0–9. MDE = CI half-width.
- W–L–T counts, Wilcoxon.
- **Sign-flip permutation p-value** on the weekly differences: 100,000 seeded draws, two-sided.
  Exact enumeration of 2⁶³ sign patterns is infeasible, so this is a Monte Carlo p with its draw
  count stated.
- Per season, and leave-one-season-out (4 folds).
- **The pre-registered bar: +0.011 FLEX capture@10.** This is W12's measured MDE for FLEX
  capture@10 between adjacent models in this exact 63-week window.

---

## 7. Decision rule: fixed now

**Guardrail breach:** a B − A difference with a CI excluding 0, negative, of magnitude ≥ 0.005, in
any of:

- RB/WR/TE capture@10, @5 or Spearman;
- FLEX capture@5, @20 or Spearman.

The result is **CONFIRMED INCREMENTAL SIGNAL** only if **all six** hold:

| # | condition |
|---|---|
| C1 | FLEX capture@10, B − A ≥ **+0.011** |
| C2 | its bootstrap CI excludes 0 (the effect is non-trivial and supported) |
| C3 | leave-one-season-out: **all 4 folds positive, and ≥ 3 of 4 with a CI excluding 0** |
| C4 | FLEX capture@10, **B − N** has a CI excluding 0 above 0 |
| C5 | Half-PPR FLEX capture@10, B − A is positive (directional compatibility) |
| C6 | **WR guardrail:** WR capture@10 B − A is not a breach and is > −0.010, **and** WR capture@10 B − CF_A has a CI excluding 0 above 0 (W10's WR gain retained). **No other breach** |

**Labels:**

- C1–C5 hold but C6 fails → **TRADEOFF**, reported explicitly and never averaged.
- Otherwise → **NO CONFIRMED INCREMENTAL SIGNAL**.

**Multiplicity:** one decision. The FLEX capture@10 cell carries C1–C5; C6 is a guardrail.
Everything else is secondary, unadjusted and flagged.

**Stopping rule:** NO CONFIRMED INCREMENTAL SIGNAL → **stop this injury-feature direction**. There
will be no thresholds, transformations, interactions, tuning, alternate cutoffs, ECR, news or
teammate features, unless a separately pre-registered experiment justifies them.

**Exploratory breakdown** (brief §11): the mechanism attribution by status group, and arm S. Both
are labelled exploratory and never select.

---

## 8. Missing data

| case | treatment |
|---|---|
| unobservable team report | missing |
| player not on an observable report | 0 |
| a row edited after the cutoff | nonexistent |
| 2025 | not evaluated |

No imputation beyond these rules.

---

## 9. 2026: the independent confirmation, frozen now

**The repository holds no 2026 data** (stats, games and production predictions end in 2025). The
following is frozen **before any 2026 data exists**:

- the two features (§2);
- the cutoff rule;
- the A/B/N arms;
- W10's durable features;
- the CatBoost configuration;
- the decision rule C1–C6 (with LOSO replaced by per-month halves, since 2026 is one season).

**What must be collected**, because the nflverse 2025 injury file has no `date_modified` and 2026
may not either:

- **Each Friday before 23:59:59 ET, snapshot the week's official NFL injury report.** Record the
  retrieval time (UTC), source URL or identifier and sha256, and store the raw file under `data/`,
  registered in `snapshot_registry`. This retrieval time is the Class A timestamp.
- Production's weekly predictions and the canonical Friday ECR board, as in 2021–2025.
- After the season: weekly stats and games through week 17.

**Run** `w13_injury_flex.py --seasons 2026`, with arms trained through 2025. Note that 2025
training rows have missing injury features.

**2026 confirms W13** only if FLEX capture@10 B − A is positive with a CI excluding 0 over 2026
weeks 1–17. A 17-week CI is roughly twice as wide, so a null is weak evidence and will be called
that.

**No 2026 value may inform any W13 choice.**

---

## 10. Leakage and validity gates: all pass before any result is read

| gate | check |
|---|---|
| G1 | parity: the one-change trainer with no added feature reproduces production exactly |
| G2 | **pre-cutoff:** an injected own **Out** row 1 second after the cutoff changes neither feature; 1 second before sets `own_status` = 3. Deleting every post-cutoff row changes no value |
| G3 | arm A equals W10's committed cells (2021–2024 weeks, positional and FLEX, Full and Half-PPR) |
| G4 | **only the two own features:** B's training frame columns are exactly W10's 7 durable + `own_status`, `own_practice`; no teammate, depth, news or ECR token; 2025 is never evaluated |
| G5 | ECR never a feature: exactly the declared training calls (B, N, S, and A via W10's function) |
| G6 | walk-forward |
| G7 | identity: `own_status` for 300 seeded player-weeks equals an independent SQL computation (the player's own gsis-mapped rows ≤ cutoff); 100% gsis mapping; 0 unmapped team codes |
| G8 | order-free: the feature table is identical with all inputs reversed |
| G9 | universe and cutoff: CF_A and ECR cells equal W10's committed cells on the 63 weeks |
| G10 | two runs byte-identical |
| G11 | W5–W12's 13 artifacts byte-identical |
| G12 | null construction: N − A capture@5/@10 CIs include 0 at RB, WR and TE |

**No target information:** the features come from injury rows only. Outcomes enter only as
evaluation targets.

---

## 11. Predictions

1. FLEX capture@10 B − A is positive: +0.005 to +0.015.
2. C1 fails (below +0.011) or C4 fails (does not beat the null).
3. **Verdict: NO CONFIRMED INCREMENTAL SIGNAL.**
4. Half-PPR is positive.
5. WR is preserved.
6. **Mechanism:** B demotes Questionable players out of the FLEX top 10, and they score less than
   their replacements. Most movers are RB and WR.
7. A over-predicts designated players (Q/D) more than undesignated ones.
8. Arm S (status only) gives most of B's effect.
9. The null does nothing at the positional level (G12).

---

## 12. Amendments

*(None yet.)*
