# W9 — Why does ECR beat Alpha? Durable knowledge, weekly information or efficiency

**Status: COMPLETE.**

**Pre-registered verdict: DURABLE (WR only)**, with RB INCONCLUSIVE and TE DURABLE as the
comparison position. That maps to recommendation **A: improve Alpha's understanding of established
player/role quality**. **WEEKLY information is NOT MEASURABLE with the repository's data. EFFICIENCY
is not supported** (not a blind test).

Run as pre-registered in `docs/weekly/W9_PREREGISTRATION.md`:

- the pre-registration was committed at `ea56000`, before any W9 quantity existed;
- amendments A1 and A2 were made **before any result**; A2 corrected a statistic that a unit test
  showed was biased by construction;
- the instruments were committed at `249741d` (module) and `1fa29a1` (runner and gates) before any
  result was read.

**Research only. Production diff EMPTY. ECR — weekly or preseason — appears only as a comparison
board or a statistical control, never in a trained model** (gate G6).

---

## Why does ECR beat Alpha at the top?

**Mostly because ECR remembers who a player is, and Alpha does not.**

W8 found ECR's lead is ECR anticipating *usage*: its top 10 gets more targets and carries than
Alpha's pre-Friday data forecasts. W9 asked where that anticipation comes from. The clearest
answer, at WR and TE, is **durable knowledge**: an established player's role and quality, knowable
before the season.

**The evidence:**

- **A board frozen in August does it.** The preseason expert ranking, never updated all season,
  anticipates as much of this week's unexpected usage as the weekly ECR does. Its usage-surprise
  edge over Alpha is **115–132%** of ECR's at every position.
- **So does last season's box score.** Ranking by last season's points per game reaches
  **84–116%** of ECR's usage edge.
- **Neither board beats Alpha overall.** Both throw away the in-season volume signal (their
  forecastable-usage piece is hugely negative), so their total gap is about zero. What ECR does is
  **combine** durable knowledge with the current season. Alpha has only the current season.
- **Controlling for the August opinion removes much of ECR's anticipation.** Once ECR's weekly
  disagreement with Alpha is purged of the preseason experts' disagreement, **48% (WR) and 40%
  (TE)** of its anticipation disappears; at RB only 20%. That durable share is **largest early in
  the season** (WR 69%, TE 66% in weeks 1–6) and fades late (10–15% in weeks 13–17).
- **ECR's own lead fades the same way.** Early to late in the season, it falls from +0.043 to
  +0.013 at RB, from +0.048 to +0.029 at WR, and from +0.041 to −0.002 at TE.
- **Giving Alpha the same durable information closes most of the WR gap.** Last season's box-score
  numbers, with no ECR, close **53%** of ECR's WR usage edge and **70%** of its WR capture@10 lead:
  +0.022 capture@10 out of +0.032, CI [+0.007, +0.038], significant in every leave-one-season-out
  fold. They close 25% at TE and 18% at RB, neither significant.
- **ECR's advantage sits on established stars.** Prior-season top-12 players carry 120% (RB),
  294% (WR) and 72% (TE) of ECR's capture lead, while making up 30–39% of the players the two
  boards disagree on. ECR keeps last year's elite players in its top 10 when Alpha has demoted
  them after a quiet stretch. At WR, 65% of ECR-only top-10 hits came the week after a game below
  the player's prior-season average.

**What is not the answer:**

- **Efficiency.** Conversion is 6–25% of the lead and never robust.
- **Documented weekly news.** Only 3–5% of top-of-board player-weeks have a provably pre-Friday
  injury or depth event, below the pre-registered bar to measure anything.

**Most of the week-to-week usage surprise is knowable by nobody.** ECR itself anticipates only
**10–15%** of the top-of-board usage surprise that a perfect-usage oracle exploits.

---

## 0. Reproduction and validity — before any result was read

### 0.1 The foundation reproduces byte-for-byte

W5 (the corrected post-D116 version), its E1, W6, the W6 agreement file, W7, W8 and W8's null check
were each re-run from their committed instruments. **All seven are byte-identical** to their
committed results.

That confirms:

- the corrected W5;
- W8's decomposition, exactly;
- the 79 weeks, the Friday cutoff, the universe, the ECR series and Full-PPR primary scoring.

### 0.2 Two instrument problems found and fixed before any result existed

1. **Amendment A1.** G5 ("exactly two models trained") contradicted G12's null construction, which
   needs a third training on permuted durable features. G5 now counts three declared trainings.
2. **Amendment A2: a biased pre-registered statistic.** A unit test showed that regressing ECR's
   disagreement on 7 unrelated columns within a ~25-player region shrinks the anticipation
   correlation by **0.058 from noise alone**. As written, I-D2 would have reported roughly a 15%
   "durable share" out of nothing.

   The reduction is now measured against the same regression on within-week permuted feature
   rows (20 fixed seeds). Tests show:
   - the raw statistic is biased (> 0.03);
   - the adjusted statistic is centred on zero (< 0.01);
   - a real control is still detected (share > 0.6).

   **The real data confirm the problem was real.** The raw reduction for D_PUBLIC is +0.050 to
   +0.062 and significant. The adjusted reduction is +0.010 to +0.014 and not significant.

### 0.3 The twelve gates — all pass

| gate | result |
|---|---|
| G1 parity | 26,097/26,097 exact |
| **G2 prior-season is prior** | physically deleting every season ≥ S moved **0** durable values over 10,168 player-seasons; 0 within-season variation; every preseason scrape precedes its season's opener |
| G3 forecast is prior | W7's forecast re-scores exactly (1,422 metrics); redaction moves 0 inputs over 2,861 player-weeks |
| **G4 weekly is pre-Friday** | 5,354 class-A events, **0** timestamp violations; a timing-uncertain event is never promoted to A |
| G5 declared trainings | exactly 3; no injury, depth, news, Vegas or realized token in the durable features; scrambled outcomes move 0 forecasts |
| **G6 ECR never a feature** | no ECR/market/preseason column in any of the three training frames |
| G7 walk-forward | 0 leaks |
| G8 joins and identity | 0 duplicate keys; identity residual 2.6e-16; every attribution sums and every decomposable ρ matches Spearman to 1e-12 (the runner aborts otherwise) |
| **G9 W8 re-derived** | 6,952 per-week decomposition values identical to W8's committed cells |
| **G10 determinism** | two runs byte-identical (`929501e9…`) |
| G11 upstream | 7 artifacts byte-identical (§0.1) |
| **G12 null construction** | shuffled durable features close **0** of ECR's usage edge at every position (+0.0002 / −0.0042 / +0.0001, all CIs include 0); the permutation-null reduction's CI includes 0 at every position |

One G12 caveat: RB's null reduction is +0.032, with a CI of [−0.002, +0.066]. The residualized
statistic is noisy at RB, which is one reason RB's durable evidence is read cautiously below.

---

## 1. The starting point, re-derived exactly: W8's decomposition

ECR minus Alpha, capture@10, identical to W8:

| | RB | WR | TE |
|---|---|---|---|
| lead `G` | +0.0228\* | +0.0320\* | +0.0258\* |
| forecastable usage `G_F` | −0.0120\* | −0.0154\* | −0.0133\* |
| **unforecast usage `G_S`** | **+0.0290\*** | **+0.0453\*** | **+0.0350\*** |
| conversion `G_C` | +0.0057 | +0.0021 | +0.0041 |
| ECR's anticipation ρ(d, s) | +0.203\* | +0.203\* | +0.190\* |

---

## 2. Q1 — how much comes from durable player and role knowledge?

### 2.1 Durable boards: how far can durable information alone go?

Each board is decomposed against Alpha at capture@10.

| board | | RB | WR | TE |
|---|---|---|---|---|
| **PRE**: preseason expert ranking, frozen all season | `G_S` | **+0.0333\*** | **+0.0534\*** | **+0.0461\*** |
| | `G_F` | −0.0436\* | −0.0415\* | −0.0531\* |
| | total `G` | +0.0005 | +0.0052 | +0.0079 |
| | `G_S` as a share of ECR's | **115%** | **118%** | **132%** |
| **PPG**: last season's points per game | `G_S` | +0.0253\* | +0.0523\* | +0.0294\* |
| | total `G` | −0.0226 | −0.0066 | −0.0340\* |
| | `G_S` as a share of ECR's | 87% | 116% | 84% |

**Durable information carries the usage anticipation, at every position.** This is the opposite of
W8's `LAST3_POINTS` board, whose `G_S` was ≤ 0. Recent box scores do not anticipate the surprise;
an established level does.

**But durable information alone is not enough.** These boards discard in-season forecastable
volume. ECR does not, and its `G_F` is only −0.012 to −0.015.

### 2.2 The three pre-registered durable instruments

| instrument | RB | WR | TE |
|---|---|---|---|
| **I-D1**: Alpha + 7 prior-season box-score features (no ECR). Closure of ECR's `G_S` | +18% [−17, +48] | **+53% [+32, +75]** | +25% [−4, +54] |
| I-D1: closure of ECR's capture@10 lead `G` | +2% | **+70% [+29, +146]** (AD − Alpha +0.0223\*) | +17% |
| **I-D2**: ECR's anticipation, residualized on the same features (A2-adjusted) | +6% (n.s.) | +5% (n.s.) | +7% (n.s.) |
| **I-D3**: ECR's anticipation, residualized on the preseason expert disagreement | **+20% [+8, +33]** | **+48% [+31, +66]** | **+40% [+25, +56]** |
| I-D3 in weeks 1–6 | +15% | **+69%** | **+66%** |
| I-D3 in weeks 13–17 | +19% | +10% | +15% |
| G12 null: shuffled I-D1 closure | +1% | −9% | 0% |

**Pre-registered route outcomes (D-1 substantial, D-2 present early, D-3 ≥ 4/5 seasons):**

| | I-D1 (D_PUBLIC) | I-D2 (D_PUBLIC) | I-D3 (D_EXPERT) | DURABLE |
|---|---|---|---|---|
| **RB** | ✗ ✗ ✗ | ✗ ✗ ✓ | ✗ (20% < ⅓) ✗ ✓ | **not supported** |
| **WR** | **✓ ✓ ✓** | ✗ ✗ ✗ | **✓ ✓ ✓** | **SUPPORTED — D_PUBLIC and D_EXPERT** |
| **TE** | ✗ ✗ ✓ | ✗ ✗ ✓ | **✓ ✓ ✓** | **SUPPORTED — D_EXPERT** |

**Two readings matter.**

**The public durable signal is nonlinear.** I-D2's linear residualization finds nothing, yet I-D1's
CatBoost finds 53% at WR. Durable box-score information matters as an interaction ("this is an
established WR1 whose recent usage dipped"), not as a linear shift.

**At WR the effect holds everywhere it was tested.** I-D1's closure is significant in all five
leave-one-season-out folds (+0.020 to +0.027) and positive in all five seasons. I-D3 is significant
in all five folds. Half-PPR replicates it: I-D1 closure 51%, I-D3 48%.

### 2.3 Tiers — is ECR's edge concentrated among established players? (brief §4)

Exact capture@10 attribution of ECR's lead by prior-season positional rank:

| | ELITE (≤ 12) | STARTER (13–36) | OTHER / rookie | ELITE share of swapped players |
|---|---:|---:|---:|---:|
| RB | **+0.0273\*** (120% of `G`) | −0.0057 | +0.0012 | 39% |
| WR | **+0.0940\*** (294%) | −0.0313\* | −0.0308\* | 36% |
| TE | **+0.0186\*** (72%) | +0.0057 | +0.0015 | 30% |

**ECR's lead is concentrated in keeping prior-season elite players in its top 10.** At WR the
effect is extreme. ECR's exclusive picks are last season's top-12 WRs. Alpha's are lesser-established
players, and they lose.

After tiering, ECR's anticipation *within* each tier is still +0.13 to +0.27. **Tier alone does not
explain it**; what does is the interaction with recent form (§6).

---

## 3. Q2 — how much comes from weekly information?

**It cannot be measured with this repository's data.** That is the pre-registered outcome, and
it is different from "no".

| | RB | WR | TE |
|---|---:|---:|---:|
| class A (documented by a strictly pre-Friday-timestamped source) region player-weeks | **79** | **91** | **62** |
| … in how many weeks | 43 | 52 | 37 |
| pre-registered bar | 100 player-weeks over 20 weeks | same | same |
| **status** | **NOT MEASURABLE** | **NOT MEASURABLE** | **NOT MEASURABLE** |

What exists in the repository:

- strictly pre-Friday injury rows (2021–2024);
- the 2025 Thursday ESPN depth-chart snapshots.

What does not exist anywhere:

- news, practice notes, coaching announcements and Vegas lines;
- any timestamp for 2021–2024 depth charts or 2025 injuries.

**Descriptively (not a conclusion), share of ECR's `G_S` at capture@10 and the anticipation in
each class:**

| | A (documented) | C (timing uncertain) | B (undocumented) |
|---|---|---|---|
| RB | 6% · 0.24 | 21% · 0.21 | **73%** · 0.20 |
| WR | 11% · **0.39** | **46%** · 0.21 | 43% · 0.18 |
| TE | 3% · 0.23 | 30% · 0.22 | **66%** · 0.18 |

Two observations, neither a conclusion:

1. **At WR, ECR's anticipation is roughly twice as strong** in the few documented-news weeks: A−B
   is +0.25, CI [+0.02, +0.48]. Nearly half of ECR's WR usage edge sits in weeks with a Friday-dated
   (timing-uncertain) injury or depth event. So WR may have a real weekly-information component,
   and this repository cannot establish it.
2. **At RB and TE, two-thirds or more** of ECR's usage edge sits in player-weeks with **no
   documented event of any kind**.

---

## 4. Q3 — how much comes from efficiency? (not blind; re-applies W8's rule)

| | RB | WR | TE |
|---|---|---|---|
| W8 efficiency rule holds | no | yes (E-1, E-2b) | no |
| LOSO folds with it | 0/5 | **1/5** | 0/5 |
| Half-PPR | no | **no** | no |
| variants | 0/4 | **2/4** | 0/4 |
| **EFFICIENCY supported** | **no** | **no** | **no** |
| conversion share of `G` | 25% (n.s.) | 6% (n.s.) | 16% (n.s.) |

**By period.** At WR, the close-pair edge appears only LATE: +0.102\* in weeks 13–17, against
+0.000 EARLY and +0.023 MID (n.s.). At TE, Alpha is significantly better on close pairs in EARLY
and MID. **There is no robust efficiency advantage anywhere.**

---

## 5. Q4–Q6 — what is explainable, what is missing, and what is unknowable

The brief's §17 categories, kept separate:

| category | what it means | RB | WR | TE | how known |
|---|---|---|---|---|---|
| **Durable, public, in the repo** | Alpha + last season's box scores (I-D1) closes this share of ECR's usage edge | 18% (n.s.) | **53%** | 25% (n.s.) | **estimated** (diagnostic counterfactual) |
| **Durable, expert, in the repo** | the frozen preseason ranking absorbs this share of ECR's anticipation (I-D3) | **20%** | **48%** | **40%** | **estimated** |
| **Weekly, documented** | class A share of ECR's `G_S` | 6% | 11% | 3% | **measured**, under the measurability bar |
| **Weekly, timing uncertain** | class C share of ECR's `G_S` | 21% | 46% | 30% | measured, exploratory |
| **Efficiency** | conversion share of ECR's lead | 25% | 6% | 16% | **measured**, none significant |
| **Undocumented, expert-only** | ECR's anticipation not absorbed by any durable or documented source: roughly 80% (RB), 50% (WR), 60% (TE) | | | | **inferred**; the durable shares overlap, so this is approximate |
| **Unknowable on Friday (upper bound)** | top-of-board usage surprise that even ECR does not anticipate. ECR anticipates only 10% / 15% / 12% of it | **90%** | **85%** | **88%** | **inferred** upper bound |

**The components are not additive.** D_PUBLIC and D_EXPERT overlap: preseason experts know last
season's box scores. Class C overlaps with durable knowledge. The table therefore shows what each
instrument can explain on its own, not a sum.

**Q4 — genuinely explainable with pre-Friday information.**

- **WR:** about half of ECR's usage edge, through durable information already in the repository.
- **TE:** about 40%, through the expert's durable view.
- **RB:** about 20%.

**Q5 — from information not in the repository.** Roughly the remainder of ECR's anticipation:

- about half at WR;
- about 60% at TE;
- about 80% at RB.

At RB it is concentrated in player-weeks with no documented event at all.

**Q6 — fundamentally unpredictable.** About **85–90%** of the week-to-week usage surprise at the
top of the board, as an upper bound. The perfect-opportunity counterfactual shows its size:
"Alpha + the week's real usage" beats ECR by +0.16 to +0.18 capture@10 at every position, and by
+0.18 on FLEX. That is information nobody has on Friday.

---

## 6. Q7 — does it differ by position?

**Yes.**

| | verdict | the mechanism in one line |
|---|---|---|
| **WR** | **DURABLE** (public and expert) | ECR keeps last season's elite WRs in its top 10 through quiet weeks; last season's box scores, added to Alpha, recover 70% of the gap. A weekly component may exist but is unmeasurable here |
| **TE** | **DURABLE** (expert) | the expert's August view absorbs 40% of ECR's anticipation (66% early); ECR's edge **vanishes late** (−0.002 in weeks 13–17) |
| **RB** | **INCONCLUSIVE** | durable boards anticipate RB usage (PRE `G_S` 115% of ECR's), but they explain only 20% of *ECR's specific* disagreements; 73% of ECR's RB usage edge sits in undocumented weeks |

**The recent-form interaction, at WR.** Among ECR-only WR top-10 hits:

- **65%** came in the week after a below-prior-season-average game (41% base rate);
- **60%** were prior-season ELITE (31% base rate);
- the Alpha-favoured WR player-seasons contain **0%** ELITE players.

---

## 7. Q8 — FLEX

| FLEX capture@10 | ECR − Alpha | Alpha + durable − Alpha |
|---|---|---|
| `G` | +0.0388\* | **+0.0190\*** (49% of ECR's lead) |
| `G_S` | +0.0377\* | +0.0187\* (**closure 50%** [23, 77]) |
| `G_C` | +0.0158\* | +0.0069 |

**Same explanation.** Durable information closes about half of ECR's FLEX usage edge.

**Same seasonal pattern:**

| weeks | ECR lead | durable closure |
|---|---:|---:|
| EARLY | +0.070 | +0.042 |
| LATE | +0.020 (n.s.) | +0.011 |

---

## 8. Q9 — early vs late season

ECR − Alpha by period (weeks 1–6 / 7–12 / 13–17):

| | lead `G` | usage surprise `G_S` | anticipation ρ | expert-durable share (I-D3) |
|---|---|---|---|---|
| RB | **+0.043\*** / +0.015 / +0.013 | +0.045\* / +0.027\* / +0.016 | 0.26 / 0.21 / 0.15 | 15% / 26% / 19% |
| WR | **+0.048\*** / +0.022 / +0.029 | +0.067\* / +0.035\* / +0.037\* | 0.27 / 0.18 / 0.17 | **69%** / 54% / 10% |
| TE | **+0.041\*** / +0.036\* / **−0.002** | +0.047\* / +0.051\* / +0.004 | 0.26 / 0.18 / 0.14 | **66%** / 25% / 15% |

**ECR's advantage is largest early and shrinks as the season reveals itself.** At TE it disappears
entirely by weeks 13–17. The durable share falls with it. That is the durable-knowledge signature
the brief described: the gap is largest when Alpha has the least in-season evidence and ECR is
leaning on what it knew in August.

At WR a residual edge (+0.029) persists late, and the late close-pair edge (§4) is the one place a
non-durable component shows. That fits "WR may also have a weekly or other component" (§3).

---

## 9. The a priori predictions, scored

| # | prediction | outcome |
|---|---|---|
| 1 | D_PUBLIC modest: I-D1 < ⅓, I-D2 15–35% | **wrong at WR**, which is the headline: I-D1 closes 53%. I-D2 is only 5–7%, below the predicted range |
| 2 | D_EXPERT > D_PUBLIC; I-D3 30–50% | **mostly right**: 48% (WR) and 40% (TE) in range; RB 20% below; larger than I-D2 everywhere, but not than I-D1 at WR |
| 3 | ECR's `G_S` edge larger EARLY than LATE | **right** at every position |
| 4 | WEEKLY NOT MEASURABLE at RB and WR | **right** (TE too) |
| 5 | class C anticipation > class B | **weakly right**: 0.21–0.22 vs 0.18–0.20, overlapping CIs |
| 6 | EFFICIENCY not supported (not blind) | **right** |
| 7 | anticipated share < ⅓ | **right** (10–15%) |
| 8 | the ELITE tier carries more than its share of ECR's lead | **right**: 120% / 294% / 72% of `G` from 30–39% of swaps |
| 9 | DURABLE (via D_EXPERT) at RB and WR | **partly**: WR yes, and through D_PUBLIC as well; RB INCONCLUSIVE |
| 10 | FLEX follows the positional pattern | **right** (durable closure 50%) |

**Six right, three partly right, one wrong.** The one wrong prediction is the most useful finding.
I expected last season's box scores to be a weak signal for Alpha, as W7's in-season features
were. At WR they close most of the gap.

---

## 10. Q10 — what should Alpha investigate next?

**By the pre-registered mapping: A — improve Alpha's understanding of established player/role
quality.**

- **WR:** both D_PUBLIC and D_EXPERT are supported.
- **TE:** D_EXPERT is supported.
- **RB:** no mechanism is supported.

**The single highest-value next direction: A, via durable *public* information, in a pre-registered
controlled test.** Give Alpha last season's role and production, and test whether it holds up.
**Do not build it yet**, and read the next test in light of three facts:

1. **The W9 number is a diagnostic, not a result to ship.**
   - `ALPHA_PLUS_DURABLE` added +0.022 capture@10 at WR, CI [+0.007, +0.038], positive in every
     season and significant in every leave-one-season-out fold.
   - It added nothing measurable at RB (+0.000) or TE (+0.004).
   - It was run on the same 79 weeks everyone has now looked at, so re-testing the same
     specification on those weeks is not independent confirmation.
   - A W10 should pre-register that exact specification with W6/W7's harm guardrails (Spearman,
     capture@50, TE, FLEX, Half-PPR), and treat the **2026 season** as the only truly
     out-of-sample confirmation.
2. **D_EXPERT (the preseason ranking) is ECR.** Using it as a feature would add ECR to Alpha. That
   is a product decision for you, not a research default, and W9 does not recommend it. The public
   route reaches the same WR gap without it.
3. **Weekly information remains untested, not refuted.** WR shows a suggestive documented-news
   signal (A−B +0.25). The only way to test it is timestamped injury, practice and depth data this
   repository does not have.
   - If the durable test succeeds, the weekly question is second priority.
   - If it fails, acquiring timestamped weekly data is the next thing to measure.

**What to stop chasing: the ~85–90% of top-of-board usage surprise that even experts don't
anticipate.** No pre-game information source in reach will recover it.

---

## Appendix — scope and reproducibility

**Instruments:**

- `src/alpha_squad/evaluation/weekly/mechanisms.py`, with 78 tests;
- `scripts/research/w9_mechanisms.py`;
- `scripts/research/w9_validity_gates.py`.

**Result:** `reports/weekly/w9_results.json`, byte-identical on re-run.

**Statistics:** 79 weeks, paired within week, bootstrap over weeks (10,000 resamples, seeds 0–9).
Players are never treated as independent. Period and season subsets resample only their own weeks.

**Scope:** research only. Production diff empty. ECR trained, calibrated, tuned and selected
nothing. No external data was acquired. Alpha was not changed. The three trained models are
declared diagnostics, and none is a candidate.
