# W12 — Pre-registration: timestamped pre-Friday information and RB breakouts

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any W12 outcome, board or model
comparison was computed. The facts it relies on are in `docs/weekly/W12_DATA_AUDIT.md` (coverage
and timing only).

> **No change below after seeing results without a dated amendment here.**

Authority: W10/W11 results, the W12 data audit, `CLAUDE.md`. Decision record: D120.

---

## 0. What is already known

- **W11:** demoting sustained RB risers (W11 PRIMARY `ROLE_UP`) costs W10's model RB −0.053
  capture@10. Its demotions are usually right; the cost is the rare real breakout (top-5 finishers
  it ranks outside 24: 10 → 18). Adding current-role features did nothing.
- **The audit:**
  - the **only Class A source for the week's changing roles is the NFL injury report, 2021–2024**;
  - depth charts are Class A only in 2025;
  - news, coach and beat-reporter information has **no reconstructable timestamped source** here;
  - **a meaningful teammate vacancy is visible before Friday for 39 of 710 RB risers.**
- **The 2021–2025 weeks have shaped every hypothesis since W9, so W12 is retrospective.** There is
  no 2026 data.

---

## 1. The question, split in two

> **A. Does verified pre-Friday information exist that tells a real RB breakout from a blip?**
> **B. Can Alpha exploit it to improve the top of the board?**

They are reported separately. A source can be predictive yet too sparse to move rankings (A
without B). A model can also extract a signal a simple test misses (B decides actionability).

---

## 2. Cutoff, seasons, weeks

- **Cutoff instant:** 23:59:59 America/New_York on the **Friday before the week's first Sunday
  game**. That Friday equals the canonical snapshot date in 78 of 79 evaluated weeks. In the one
  Saturday-snapshot week, the Friday is used.
- **Strict sensitivity** (Question A only): 00:00:00 ET on that Friday.
- **Evaluated weeks:** W5–W11's 79 (2021–2025). **Primary window: 2021–2024 (63 weeks)**, where the
  Class A source exists. The secondary window is all 79; 2025 has no Class A injury feature.
- **Training:** walk-forward `[2015, S − 1]`, as W10/W11. Injury timestamps exist for 2015–2024.

---

## 3. Population and outcome

- **Candidates:** RB player-weeks in the evaluated universe whose **W11 PRIMARY class is
  `ROLE_UP`**. This is W11's exact implementation (`w11_mechanism.role_table`).
- **Horizon: the ranked week *w* only.**
- **Primary outcome, `BREAKOUT`:** the player's realized Full-PPR rank among the week's evaluated
  RBs is ≤ 10 (ties by `player_id`, W5's rule). It is future information, never a feature.
- **Secondary outcome, `ROLE_HELD`:** week-*w* touches − `prior_opp_pg` ≥ 3 (W11's τ). "The rise
  was real."
- Top-5 finishes are reported descriptively.

---

## 4. Features: Class A only (source: NFL injury report via nflverse, 2015–2024)

For player *i* on team *t* (the week-*w* team), position *P*, week *w* of season *S*, cutoff *K*:

**The report and its rows.**

- The report is `injuries` rows for (*S*, *w*, regular season), with 2015–2019 team codes mapped
  OAK→LV, SD→LAC, STL→LA.
- **Only rows whose `date_modified` (converted to ET) is ≤ K are used.**
- **The team's report is observable** if at least one of its rows is ≤ K. If it is not, all five
  features are **missing**.

**A teammate's touches per game:** the mean of carries + targets over the teammate's last ≤ 3
appearances in season *S* before week *w* (0 with none).

| category | feature | definition |
|---|---|---|
| **teammate availability** | `tm_out_opp` | Σ touches/game of teammates *j* ≠ *i* on team *t*, report position *P*, status **Out or Doubtful** |
| | `tm_q_opp` | the same for status **Questionable** |
| | `tm_ret_opp` | the same for teammates listed with a status other than Out/Doubtful who appeared in *S* before *w* but **not in the team's most recent game**: a likely return |
| **own injury / practice** | `own_status` | *i*'s status: 0 none, 1 Questionable, 2 Doubtful, 3 Out; missing if *i*'s row was modified after K |
| | `own_practice` | 0 full or not listed, 1 limited, 2 did not participate; missing if the row is after K |

**Missing data:**

- 2025 has no timestamps, so all five features are missing.
- A row modified after K is **unknown, never healthy**. As a teammate, it is not counted.
- An unobservable team report makes all five features missing.
- CatBoost handles missing values natively.

**`VACANCY`** (Question A): `tm_out_opp ≥ 8.0`, a teammate with a real role is out. One fixed
threshold; the model gets the continuous feature.

**Not features:**

- ECR or any expert ranking;
- news or text;
- the 2025 injury file;
- 2021–2024 current-week depth charts and weekly-roster status (Class B, arm E only);
- anything post-cutoff.

---

## 5. Question A — does the information exist and predict breakouts?

**Population:** 2021–2024 RB risers with an observable report. Full PPR. Week-cluster bootstrap
(`rolechange.ratio_diff_ci`: 10,000 resamples, seeds 0–9).

| | test | role |
|---|---|---|
| **QA1** | P(BREAKOUT \| VACANCY) − P(BREAKOUT \| no VACANCY) | **primary: INFORMATION EXISTS iff the CI excludes 0 above** |
| QA2 | the same, among risers **ranked outside C's top 10** (the breakouts the W11 model misses) | incremental |
| QA3 | the same for ROLE_HELD | persistence |
| QA4 | BREAKOUT, own status ≥ Questionable vs not | expected negative |
| QA5 | BREAKOUT, `tm_ret_opp` ≥ 8 vs not | expected negative |
| QA-S | QA1 under the strict cutoff | sensitivity |
| QA-U | QA1 over **all** RB universe player-weeks, not only risers | context |
| QA-D | **2025 depth, exploratory:** BREAKOUT for risers listed RB1 at the last capture ≤ K vs not; the promotion count is reported | 16 weeks |

---

## 6. Question B — can Alpha exploit it?

**Arms:**

| arm | definition |
|---|---|
| A | production's stored predictions |
| B | W10's model, exactly (G3) |
| C | W11's model, exactly: B + 3 role features (G3) |
| **D** | **C + the 5 Class A features.** Same CatBoost, hyperparameters, loss, target, walk-forward, universe and scoring |
| N | C + the 5 features **permuted across players within (season, week, position)**: the null |
| D−tm | C + the own-status features only (attribution) |
| D−own | C + the teammate features only (attribution) |
| E (**EXPLORATORY, Class B**) | D + the current-week nflverse `depth_team` (2015–2024; missing for 2025). **Never a verdict input** |

**ECR is a benchmark only.**

**Metrics:**

- **positional:** capture@5, @10, @20, @50, Spearman, Kendall, pairwise, precision@10;
- **FLEX:** capture@5, @10, @25, Spearman, pairwise, through the existing pooled path;
- **riser-specific, per week** (RB):
  - *missed breakouts*: risers who finish top-5 but are ranked outside 24;
  - *false top-10*: risers in the board's top 10 who finish outside 24;
  - *riser regret*: capture lost on realized-top-10 risers outside the board's top 10;
- **D vs C:** top-10 overlap, and D − C capture@10 attributed to movers by W11 class and by
  VACANCY.

**Statistics:** week-paired bootstrap (10,000 resamples, seeds 0–9), MDE, W–L–T, per season,
leave-one-season-out, Half-PPR.

---

## 7. The verdict: fixed now, evaluated in this order

**The coverage gate** is checked at run time before anything is interpreted. The 2021–2024 RB
risers with an observable report must have:

- ≥ 300 risers;
- ≥ 30 in VACANCY;
- ≥ 40 BREAKOUTs;
- VACANCY risers in ≥ 20 distinct weeks.

**Breach:** a D − C difference (63 weeks) with a CI excluding 0, negative, and |Δ| ≥ 0.005, in
any of:

- capture@5, @10, @20 or @50, Spearman or pairwise at RB, WR or TE;
- FLEX capture@10, @25, Spearman or pairwise.

**WR harm:** WR capture@10 D − C is a breach, or ≤ −0.010.

**The five conditions** (63 weeks, Full PPR):

- **B1:** RB capture@10 D − C ≥ **+0.02** (the program's bar, about 2× W11's RB MDE), with a CI
  excluding 0.
- **B2:** RB capture@10 D − N has a CI excluding 0 above 0.
- **B3:** RB capture@10 D − C is positive in ≥ 3 of 4 seasons, **and** its CI excludes 0 in ≥ 3
  of 4 leave-one-season-out folds.
- **B4:** no breach.
- **B5:** no WR harm, **and** WR capture@10 D − A has a CI excluding 0 above 0 (W10's gain
  retained).

| order | verdict | rule |
|---|---|---|
| 0 | **DATA INSUFFICIENT** | the coverage gate fails |
| 1 | **INFORMATION EXISTS + ACTIONABLE** | B1–B5 all hold |
| 2 | **TRADEOFF** | B1 holds, and B4 or B5 fails. Never averaged |
| 3 | **HARM** | B4 or B5 fails, and B1 fails |
| 4 | **INFORMATION EXISTS + NOT ACTIONABLE** | QA1 holds |
| 5 | **NO INCREMENTAL SIGNAL** | anything else |

**Multiplicity.**

- Exactly **two tests decide:** QA1, and the RB capture@10 cell of B1.
- B2–B5 are conditions on that same cell or guardrails.
- Everything else is secondary, unadjusted, flagged as such, and never selects.

**Stopping rules** (brief §16):

- DATA INSUFFICIENT, NO INCREMENTAL SIGNAL, NOT ACTIONABLE or HARM → **stop this direction**.
- ACTIONABLE → define one next experiment; **no implementation**.
- An effect that needs arm E (Class B) is never a stop-override. It can only say what data would
  be worth collecting forward.

---

## 8. Information-value decomposition

| category | how it is measured |
|---|---|
| teammate availability | D − (D−tm) |
| own injury / practice | D − (D−own) |
| depth chart | QA-D (2025, Class A, 16 weeks); arm E (Class B, exploratory) |
| coach / beat-reporter | **untestable**: no reconstructable source |
| other | none |

Ablations attribute; they never select.

---

## 9. Robustness

- Per season and leave-one-season-out (4 folds) for D − C at RB, WR, TE and FLEX: capture@5, @10,
  @20 and Spearman.
- Half-PPR.
- The 79-week window.
- The strict cutoff (QA).
- The null arm N.

---

## 10. Validity and leakage gates: all pass before anything is read

| gate | check |
|---|---|
| G1 | parity: the one-change trainer with no added feature reproduces production exactly |
| G2 | **pre-cutoff.** (a) every contributing injury row is ≤ its cutoff (asserted in the builder; 0 violations). (b) **Adversarial:** an injected Out row for a 20-touch teammate modified **1 second after** the cutoff changes no feature; the same row **1 second before** does (positive control). (c) Deleting every row modified after the cutoff changes no feature |
| G3 | B equals W10's committed cells; C equals W11's |
| G4 | no Class B/C in the primary features: 2025 features all missing; `depth_team` only in arm E; no forbidden tokens |
| G5 | ECR never a feature: exactly the declared training calls, with frames only from `durable_panel`, `role_panel` and the injury table |
| G6 | walk-forward |
| G7 | joins: 0 unmapped team codes after aliasing. `tm_out_opp` for 300 seeded player-weeks equals an independent SQL computation. The gsis → player map rate is reported |
| G8 | order-free: the injury feature table is identical with input reversed |
| G9 | the universe and arm A equal W10/W11's committed cells; 79 weeks |
| G10 | two runs byte-identical |
| G11 | W5–W11's 12 artifacts byte-identical |
| G12 | the null arm N − C has capture@5/@10 CIs including 0 at RB, WR and TE (63 weeks) |

---

## 11. Predictions

1. The coverage gate passes.
2. **QA1 holds:** a real vacancy raises the breakout rate.
3. QA2 is positive, but its CI includes 0.
4. QA4 is negative: a questionable riser breaks out less.
5. QA5 is negative: a returning teammate lowers it.
6. **RB capture@10 D − C is +0.000 to +0.008, below the bar.** The signal touches about 5% of
   risers.
7. WR is preserved.
8. **Verdict: INFORMATION EXISTS + NOT ACTIONABLE.**
9. Teammate availability carries most of any D effect.
10. Exploratory arm E moves RB more than D. That would hint that timestamped depth charts are worth
    collecting going forward.
11. QA-D: the 2025 depth-change count is too small to test.
12. Half-PPR agrees.

---

## 12. Amendments

*(None yet.)*
