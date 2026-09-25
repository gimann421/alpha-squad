# W9 — Pre-registration: durable knowledge, weekly information or efficiency?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any W9 quantity was computed.

§2 records coverage and timing facts only. No comparison between ECR and Alpha, and no durable,
weekly or efficiency statistic, was computed to write it.

**One disclosure up front.** The efficiency question (§7) re-uses W8's data, and W8's
efficiency result is already known: a fragile WR-only pass. So W9's efficiency verdict **is not a
blind test**. It is a re-application of W8's rule, with season periods added. It is labelled that
way everywhere it appears.

Authority: `docs/weekly/W8_ECR_ADVANTAGE_RESULTS.md`, `docs/weekly/W7_OPPORTUNITY_RESULTS.md`,
`docs/weekly/W5_TOPBOARD_FORENSICS.md`, `CLAUDE.md`. Decision record: `docs/DECISIONS.md` D117.

> **No change below after seeing results without a dated amendment here.**

---

## 1. The question

W8 split ECR's capture@10 lead over Alpha exactly into three pieces (RB / WR / TE):

| piece | RB | WR | TE |
|---|---:|---:|---:|
| forecastable usage `G_F` | −0.012 | −0.015 | −0.013 |
| **unforecast usage `G_S`** | **+0.029** | **+0.045** | **+0.035** |
| conversion `G_C` | +0.006 | +0.002 | +0.004 |

ECR's disagreements with Alpha anticipate the usage surprise: ρ(d, s) = +0.20.

> **Where does ECR's usage anticipation come from?**

There are three sources, each measured on its own. **None is assumed.**

| source | meaning | sub-kinds (§17 of the brief) |
|---|---|---|
| **DURABLE** | knowable before the season: established role, quality, prior-season usage and rank | **D_PUBLIC:** prior-season box-score facts, in the repository (acquirable data). **D_EXPERT:** the frozen preseason expert ranking, in the repository as a published ranking (expert judgment, acquirable as data) |
| **WEEKLY** | information that appears during the week: injuries, teammate injuries, practice, depth changes, news, Vegas | **A:** documented by a strictly pre-Friday-timestamped source. **B:** no documentation anywhere. **C:** documentation exists only in a timing-uncertain source |
| **EFFICIENCY** | points per unit of opportunity | W8's conversion `c = pts − x` and its close / matched pair tests. **No new metric** |

**The product meaning of the categories must never be collapsed:**

- **"Not in Alpha but acquirable":** D_PUBLIC, D_EXPERT and weekly class A.
- **"Only in expert judgment":** what ECR anticipates that no documented source explains.
- **"Not knowable before the game":** usage surprise that even ECR does not anticipate.

**ECR stays an instrument.** The weekly ECR and the preseason ECR appear only as comparison boards
and statistical controls. **Neither ever enters a trained model**, and gate G6 checks this.

---

## 2. Audit — facts established before any comparison

### 2.1 Reproduction first

W5 (post-D116 fix) and its E1, W6 and its agreement file, W7, W8 and W8's null check are re-run
from committed instruments. Each must be **byte-identical** to its committed result, or W9 stops.
The result is recorded in the results document §0.

### 2.2 Durable sources

| source | timing | coverage (top region, §4) |
|---|---|---|
| **prior-season box scores** (`player_week_stats`, season S−1, regular season only, weeks ≤ 18) | complete before season S begins: **Class A** | 89–92% of region player-weeks have a prior season; the rest are rookies or had no prior season |
| **preseason expert ranking** (DynastyProcess `rp` `redraft-rb/wr/te`, the latest scrape strictly before the season's first game) | scraped **6 days before the opener** every season 2021–2025: **Class A**, frozen all season | 111–300 players mapped per position-season |

### 2.3 Weekly sources, with their timing class

| source | strictly pre-Friday (A) | timing-uncertain (C) |
|---|---|---|
| injuries 2021–2024: own designation, or a same-position teammate Out/Doubtful | `modified_on < cutoff date`: **4.3% RB / 5.3% WR / 2.8% TE** of region player-weeks | `modified_on = cutoff date`: 35% / 44% / 26% |
| injuries 2025 | none (no timestamp column) | all 2025 injury rows |
| depth charts 2021–2024 (current week) | none (week-keyed, no timestamp) | current-week rank change vs prior week |
| **depth charts 2025** | **Thursday-morning (UTC) ESPN snapshot before every cutoff**: a rank change vs the previous Thursday is **documented pre-Friday** | — |
| news, practice notes, coaching announcements, Vegas | **not in the repository** | — |

**Weekly class A is therefore thin by construction.** §6.3 fixes the coverage bar the test must
clear, rather than letting a thin class produce a confident answer.

---

## 3. Scope — unchanged from W8

- 79 weeks, 2021–2025; Friday cutoff; the W3–W8 universe and ECR series.
- Full PPR primary; Half-PPR is a replication only.
- RB and WR primary, TE as comparison, FLEX through the existing boards.
- Top region = top 20 on either board.
- Primary depth capture@10; also @5 and @20.
- W8's decomposition `G = G_F + G_S + G_C`, the surprise `s = x − f` (W7's `M_NEW`) and W8's
  buckets are reused exactly. **G9 requires W9 to re-derive W8's per-week pieces exactly.**

### Season periods — fixed now

| period | weeks | evaluated weeks |
|---|---|---:|
| **EARLY** | 1–6 | 24 |
| **MID** | 7–12 | 30 |
| **LATE** | 13–17 | 25 |

Fixed from the week numbers alone.

---

## 4. The durable instruments

### 4.1 Durable public features (Class A), from season S−1

| feature | definition |
|---|---|
| `prior_ppg` | PPR points per game played |
| `prior_games` | games played |
| `prior_opp_pg` | (targets + carries) per game |
| `prior_tsh` | mean target share |
| `prior_snap` | mean offensive snap share |
| `prior_rank` | positional rank by total PPR points, `player_id` tiebreak (**W5's definition**) |
| `has_prior` | 1 if the player played in S−1 |

Floating-point sums are reduced in Python with `math.fsum` in a fixed order, never in SQL
(W8/D116's determinism lesson). The features are constant within a season (gate G2).

### 4.2 Durable instruments

**I-D1 — the durable counterfactual (the brief's §3).** `ALPHA_PLUS_DURABLE` is production's
CatBoost, hyperparameters, MAE loss and walk-forward `[2015, S−1]`, plus the 7 durable features.

- It is a diagnostic. It is never a candidate.
- For 2015 training rows the durable features are missing (no 2014 data); CatBoost handles
  missing values natively.

Since `G_S(ECR vs A) − G_S(ECR vs A+D) = G_S(A+D vs A)`, **the durable closure of ECR's surprise
edge** is

    closure_S = G_S(A+D vs A) / G_S(ECR vs A),   measured per week, CI on the numerator

and the same for `G`.

**I-D2 — residualized anticipation, public.** Within each week and position:

1. regress ECR's disagreement `d` on the durable public features (region players, OLS with
   intercept);
2. keep the residual `d⊥`;
3. compute

       durable share = 1 − ρ(d⊥, s) / ρ(d, s)    (per week: ρ(d, s) − ρ(d⊥, s))

This answers: once "ECR likes established players more" is removed, how much anticipation is
left?

**I-D3 — residualized anticipation, expert.** The same, with `d` residualized on the **preseason
expert disagreement** `d_PRE = rank_ALPHA − rank_PRE`.

- `PRE` is the frozen preseason positional ranking.
- Unranked players go after ranked ones, in Alpha's order.

This answers: how much of the weekly ECR's anticipation is already in the experts' August opinion?

**Durable comparison boards (descriptive):**

- **PRE:** the frozen preseason board.
- **PRIOR_PPG:** rank by `prior_ppg`; players with no prior season go last, in Alpha's order.

Both are decomposed against Alpha with W8's instrument. **They are boards, never models.**

**Stratification (brief §4).** Tiers by `prior_rank`:

- **ELITE:** ≤ 12 (W5's `ELITE_DEPTH`).
- **STARTER:** 13–36.
- **OTHER:** > 36, or no prior season.

For each tier, report:

- the exact capture@10 attribution of `G` and `G_S`;
- the tier's share of swapped players;
- tier-restricted anticipation (§5).

---

## 5. A decomposable anticipation statistic

W8's ρ(d, s) is a per-week correlation, so it cannot be split across subsets. W9 uses its
decomposable form. Let `rd_i` and `rs_i` be player i's ranks of `d` and `s` within the week's
region, centred and scaled to unit variance. Then

    a_i = rd_i · rs_i,   and   mean over the region of a_i = ρ(d, s) exactly.

For any subset, the anticipation is the mean of `a_i` over the subset's player-weeks. This
applies to weekly classes, tiers and periods. Inference resamples **weeks**, with every member of
the subset in a resampled week.

---

## 6. The weekly-information instrument

### 6.1 Classes, per region player-week

Classes are fixed in this order, so the first that applies wins.

| class | the player-week has … |
|---|---|
| **A — documented** | at least one event in a **strictly pre-Friday-timestamped** source: <br>• its own injury row with `modified_on < cutoff date`; <br>• a same-team, same-position teammate Out/Doubtful with `modified_on < cutoff date`; <br>• (2025) a change in its own ESPN depth rank between the latest snapshot strictly before the cutoff date and the latest snapshot strictly before the cutoff date minus 7 days (appearing or disappearing counts as a change) |
| **C — timing uncertain** | no A event, but an event in a timing-uncertain source: <br>• a same-day (`= cutoff date`) injury row or teammate Out/Doubtful (2021–2024); <br>• any 2025 injury row; <br>• (2021–2024) a current-week `depth_team` change vs the previous week |
| **B — undocumented** | neither |

The events are direction-agnostic. The question is whether *any* documented reason for a usage
change existed before Friday, not whether it pointed the right way.

### 6.2 What is measured

- **Exact attribution of ECR's `G_S` at capture@10 by class.** The three classes sum to `G_S`,
  shown against each class's share of swapped players.
- **Class anticipation:** the mean of `a_i` in A, in B and in C.
- **The A − B difference**, week-paired over weeks where both classes occur.

### 6.3 Measurability — fixed now

The weekly test is **MEASURABLE** at a position only if class A holds at least **100 region
player-weeks** spread over at least **20 evaluated weeks**.

Otherwise WEEKLY is **NOT MEASURABLE with the repository's data**. That is a distinct outcome from
"not supported", and it is reported as such.

**Class C never enters the main conclusion.** It is reported as an exploratory upper-bound view.

---

## 7. The efficiency instrument (not blind — see the disclosure above)

Efficiency uses W8's rules exactly:

- `G_C`;
- close-pair `Ω_close`;
- matched-pair `Ω_match`;
- routes E-1 and E-2;
- robustness per W8 §9.

W9 adds **period** breakdowns and **tier** breakdowns. No new efficiency metric is used.

---

## 8. The counterfactual (brief §10)

The boards are compared positionally and on FLEX:

- **A** = Alpha;
- **B** = W8's `ALPHA_ORACLE_OPP`, with the week's realized usage (Class D, never deployable);
- **C** = ECR.

Reported: B − A, C − A and C − B at capture@5, @10 and @20, and FLEX at @10 and @25.

**As in W8, B is reported and kept out of the verdict.** It closes the gap whether or not ECR's
lead is about opportunity.

The quantity the brief actually wants, "how much of ECR's advantage remains after perfect
opportunity", is W8's conversion share `G_C / G`, re-derived by period.

**The "not knowable" measure (brief §17C):**

    anticipated share = G_S(ECR vs A) / G_S(ORACLE_USAGE vs A)

This is the share of the top-of-board usage surprise that the experts actually anticipate. One
minus it is an **upper bound** on what is fundamentally unknowable on Friday. It is an upper bound
because a better-informed ranker than ECR could exist.

---

## 9. Verdict criteria — fixed now

Each is evaluated per position: RB and WR primary, TE comparison, FLEX. CIs are 95%, bootstrapped
over weeks.

### DURABLE is supported if D-1, D-2 and D-3 all hold for the same sub-kind (D_PUBLIC or D_EXPERT)

- **D-1 (explains a substantial part).** The durable share of ECR's usage anticipation is at
  least **⅓**, and its per-week reduction statistic has a CI excluding zero.
  - D_PUBLIC passes through either route: I-D1's closure of `G_S`, or I-D2.
  - D_EXPERT passes through I-D3.
- **D-2 (present before weekly information accumulates).** In the **EARLY** period, the same
  instrument's reduction statistic is positive with a CI excluding zero.
- **D-3 (consistent across seasons).** The reduction statistic's point estimate is positive in at
  least **4 of 5 seasons**.

### WEEKLY is supported if W-1, W-2 and W-3 all hold

- **W-1.** ECR's `G` is concentrated in large surprises: the LARGE-bucket share of `G` at
  capture@10 is at least 50% (W8's attribution, re-derived).
- **W-2.** The test is MEASURABLE (§6.3), **and** both:
  - class A carries at least **⅓** of ECR's `G_S` at capture@10, with a CI excluding zero, **and**
    at least **1.5×** its share of swapped players;
  - anticipation in A exceeds anticipation in B, with the A − B CI excluding zero.
- **W-3.** The W-2 A − B difference has a positive point estimate in at least 4 of 5
  leave-one-season-out folds.

If W-2 is not MEASURABLE, WEEKLY is **NOT MEASURABLE**, never "not supported".

### EFFICIENCY is supported if both hold

- W8's EFFICIENCY rule holds.
- W8's §9 robustness holds: at least 4 of 5 LOSO folds, Half-PPR, and at least 3 of 4 variants.

The route's CIs must exclude zero, so the effect exceeds its own noise floor.

### The position verdict

| supported | verdict |
|---|---|
| exactly one of DURABLE / WEEKLY / EFFICIENCY | that component |
| more than one | **MIXED** |
| none | **INCONCLUSIVE** |

WEEKLY being NOT MEASURABLE is annotated next to the verdict in every case.

### The overall verdict, from RB and WR

- They agree: that verdict.
- One is INCONCLUSIVE: the other's verdict, stated as position-specific.
- Otherwise: **MIXED**.

### The recommendation — one direction (brief §23)

| overall verdict | direction |
|---|---|
| DURABLE | **A:** improve Alpha's understanding of established player/role quality (naming D_PUBLIC or D_EXPERT) |
| WEEKLY | **B:** timestamped weekly-information acquisition |
| EFFICIENCY | **C** |
| MIXED | **D:** name the component with the largest measured share of ECR's usage anticipation as the one to research separately |
| INCONCLUSIVE, with the anticipated share (§8) below ⅓ | **E:** the bulk of the usage surprise is unanticipated even by experts; stop chasing it |
| INCONCLUSIVE, with WEEKLY NOT MEASURABLE and the anticipated share at least ⅓ | **B as a measurement**: the only untested explanation needs timestamped weekly data the repository lacks. The recommendation says so and is explicitly *not* "build a news pipeline" |

**Reported alongside, never replacing, the verdict** (the brief's §11 three-way decomposition,
labelled measured / estimated / inferred):

| label | quantity |
|---|---|
| **measured** | `G_F`, `G_S`, `G_C`; the class-A share of `G_S` |
| **estimated** | the durable shares (I-D1 to I-D3) |
| **inferred** | the undocumented remainder; the "not knowable" upper bound |

---

## 10. Robustness — fixed now

1. **Leave-one-season-out and per-season** for every verdict statistic.
2. **Periods:** EARLY / MID / LATE for `G` and its pieces, the durable reduction statistics and
   class anticipation. It is supporting evidence, not proof, to ask whether ECR's edge shrinks from
   EARLY to LATE. Durable knowledge predicts a shrink; weekly information predicts it persists.
3. **Half-PPR:** the decomposition, I-D1 to I-D3, and the weekly classes. It never selects.
4. **FLEX:** the decomposition by period and I-D1's closure on the FLEX board. No FLEX model is
   built.
5. **Region depth:** top-10 and top-30 on either board for I-D2, I-D3 and class anticipation.

---

## 11. Validity and leakage gates — all must pass before any result is read

| gate | check |
|---|---|
| **G1** | parity: the one-change trainer with no added feature reproduces production exactly |
| **G2** | **prior-season data is truly prior.** Physically deleting every `player_week_stats` row of season ≥ S leaves every durable feature for season S unchanged; the features are constant within a season; `PRE` uses only scrape dates strictly before the season's first game |
| **G3** | **early-season information precedes the evaluated week.** The W7 forecast's physical-redaction test re-runs; W9's `f` re-scores to W7's committed cells |
| **G4** | **weekly information predates the cutoff.** Every class-A event's timestamp is strictly before the cutoff date (0 violations); no same-day or untimestamped event is ever class A |
| **G5** | **no post-Friday or realized information in any predictor.** Exactly two models are trained, `ALPHA_PLUS_DURABLE` (durable features only) and the declared Class D `ALPHA_ORACLE_OPP`; no injury, depth, news or realized column is in the durable list; scrambling the evaluated season's outcomes changes no durable feature and no forecast |
| **G6** | **ECR is never a feature.** No ECR or preseason-ECR column in any training frame; ECR enters only boards and residualization |
| **G7** | walk-forward: no training frame contains the predicted season |
| **G8** | **joins and identity.** Unique keys. `G = G_F + G_S + G_C`. The A/B/C classes and the tiers partition the swapped players, and their attributions sum to `G_S` and `G`. The decomposable anticipation reproduces ρ(d, s) to 1e-12 |
| **G9** | **W8 re-derived exactly.** W9's per-week `G`, `G_F`, `G_S` and `G_C` equal W8's committed cells; the universe and cutoff are identical |
| **G10** | **determinism.** Two runs are byte-identical |
| **G11** | **upstream.** §2.1 |
| **G12** | **null construction.** Permuting the durable features across players within each season makes I-D1's `G_S` closure and I-D2's reduction indistinguishable from zero (CI includes 0); residualizing on pure noise leaves ρ(d, s) unchanged in expectation (unit-tested) |

**If a gate fails: stop, fix, re-run, document, and only then read results.**

---

## 12. A priori predictions, recorded before any result

1. **D_PUBLIC is modest.** I-D1 closes less than ⅓ of ECR's `G_S` (prior-season box scores are a
   weak signal, the W7 lesson again); I-D2's durable share is 15–35%.
2. **D_EXPERT is larger than D_PUBLIC.** The preseason expert ranking absorbs more of ECR's
   anticipation (I-D3 share 30–50%): the experts' durable opinion is richer than last season's box
   score.
3. **ECR's `G_S` edge is larger EARLY than LATE,** consistent with durable knowledge mattering
   most before the season reveals itself.
4. **WEEKLY is NOT MEASURABLE** at RB and WR: class A falls under 100 player-weeks or 20 weeks.
5. Where measurable or exploratory, class C (Friday-dated injury news) shows **higher** ECR
   anticipation than B.
6. **EFFICIENCY is not supported anywhere** (not blind: W8 already showed this).
7. **The anticipated share (§8) is below ⅓:** ECR anticipates only a minority of the
   top-of-board usage surprise, and most of it is unknowable on Friday.
8. The ELITE prior-season tier carries more than its share of ECR's `G`.
9. **Overall verdict: DURABLE** (via D_EXPERT) at RB and WR, with WEEKLY NOT MEASURABLE.
10. FLEX follows the positional pattern.

If the results contradict these, the results win and the contradiction is reported prominently.

---

## 13. What W9 may NOT do

- Add ECR, preseason ECR, news or injury data to Alpha, or use any of them as a model feature.
- Change production or any file under `models/`, `league/`, `api/`, `cli.py`, `market/`,
  `features/`, `identity/`, `ingest/`, `sources/`.
- Tune CatBoost.
- Build a news pipeline or the final solution.
- Change a threshold, period, tier, class rule or verdict rule after seeing results.
- Present `ALPHA_ORACLE_OPP` or `ALPHA_PLUS_DURABLE` as a candidate.

---

## 14. Amendments

### A1 — pre-results clarification (2026-09-25, before any W9 quantity was computed)

**G5 and G12 were inconsistent as written.** G5 says exactly two models are trained. G12's null
construction ("permuting the durable features … makes I-D1's `G_S` closure … indistinguishable from
zero") cannot be run without training I-D1's model on permuted features.

G5 therefore counts **three declared trainings**:

- `ALPHA_PLUS_DURABLE`;
- `ALPHA_ORACLE_OPP`;
- `ALPHA_PLUS_DURABLE_SHUFFLED` — the same 7 durable columns, permuted across players within each
  season with a fixed seed. This is the G12 null. It never enters a verdict except as that gate.

**The durable public residualization (I-D2) uses the 7 features of §4.1.** A missing value (a
player with no prior season) is set to 0, with `has_prior` = 0 carrying the missingness. This
matches the counterfactual's information exactly.

No threshold, class, period, tier or verdict rule changes.
