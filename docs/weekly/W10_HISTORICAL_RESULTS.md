# W10 — Does better historical player knowledge improve Alpha?

**Status: COMPLETE.**

**Pre-registered verdict: SUCCESS, carried by WR alone.** WR capture@5 and capture@10 meet all five
conditions. Half-PPR gives the same verdict. No guardrail is breached at any position.

**RB and TE's top of the board: no effect. The broad ordering improves slightly at every
position.**

Run as pre-registered in `docs/weekly/W10_PREREGISTRATION.md`:

- the pre-registration was committed at `77a1a93`, before any W10 quantity existed;
- the instruments (module, runner, gates, tests) were committed at `855abf7`, with amendment A1
  (clarifications only), **before any result was read**;
- amendment **A2** is the **one post-hoc check**, added after reading. It is labelled as such and
  is never a verdict input.

**Research only. Production diff EMPTY. ECR is a comparison board only, never a feature** (gate G5).

**Read this with §0 of the pre-registration in mind.** W10's main arm is W9's
`ALPHA_PLUS_DURABLE`, frozen, and its WR capture@10 number was known before W10 began. The
2021–2025 weeks shaped the hypothesis, so **this is retrospective research, not confirmation.**
The 2026 season is the only independent test, and its protocol is frozen (pre-registration §9).

---

## Does remembering who a player was last season make Alpha better at ranking players this week?

**Yes, for wide receivers, and modestly. Not for the top of the running-back or tight-end boards,
though it does not hurt them.**

**At WR, the gain is real and consistent.** Give Alpha seven numbers from each player's previous
season (points per game, positional rank, touches, target share, snap share, games, and whether they
played). Its weekly WR top 10:

- captures **66.3%** of the best possible points instead of **64.1%**;
- improves in **all five seasons**;
- is significantly better in **every leave-one-season-out fold**;
- improves **most in the first six weeks**;
- closes **70%** of the WR top-10 gap to the expert consensus (ECR). The remaining gap is no
  longer statistically distinguishable from zero.

**How it works.** Last season's numbers keep established stars in the top 10 through quiet weeks.
When a prior-season top-12 player has a disappointing game and then finishes in the top 10, Alpha
had him in its top 10 51% of the time (WR). With history it does 66% of the time; ECR does 75%.

**What it costs.** History makes Alpha slower to believe a genuine breakout. Players whose current
role is clearly bigger than last season's get pushed down.

**At RB the two effects cancel almost exactly.** History rescues quiet RB stars about as well as WR
stars, but pays a larger breakout penalty, so the net RB top-of-board effect is zero. At TE the net
effect is small and not significant.

**Nothing got worse.** Rank correlation and pairwise accuracy improve significantly at RB, WR, TE
and FLEX. Prediction error falls slightly at WR and TE.

**Two warnings:**

- **WR capture@5** passes the pre-registered rule, but it does not clearly beat a model given the
  same seven columns shuffled at random (post-hoc, below). Treat the top-5 gain as fragile and the
  top-10 gain as the finding.
- **FLEX top-5** leans negative (−0.013, not significant), even though FLEX top-10, top-25 and
  the whole order improve.

---

## 1. The headline table

B − A, Full PPR, 79 weeks, paired within week, 10,000 bootstrap resamples. \* marks a 95% CI that
excludes 0.

| | capture@5 | capture@10 | capture@20 | capture@50 | Spearman | pairwise |
|---|---:|---:|---:|---:|---:|---:|
| RB | −0.0038 | +0.0004 | +0.0003 | −0.0010 | **+0.0043\*** | **+0.0021\*** |
| **WR** | **+0.0275\*** | **+0.0223\*** | +0.0086 | +0.0009 | **+0.0065\*** | **+0.0031\*** |
| TE | +0.0115 | +0.0044 | +0.0065 | −0.0006 | **+0.0070\*** | **+0.0031\*** |
| FLEX | −0.0127 | **+0.0190\*** | **+0.0157\*** | **+0.0055\*** | **+0.0053\*** | **+0.0024\*** |

**WR CIs:**

| metric | B − A | 95% CI | MDE |
|---|---:|---|---:|
| capture@5 | +0.0275 | [+0.0057, +0.0502] | 0.022 |
| capture@10 | +0.0223 | [+0.0068, +0.0384] | 0.016 |

**FLEX capture@25:** +0.0132\*.

**capture@10 levels:**

| | A | B | ECR |
|---|---:|---:|---:|
| RB | 0.690 | 0.690 | 0.713 |
| WR | **0.641** | **0.663** | 0.673 |
| TE | 0.696 | 0.700 | 0.722 |
| FLEX | 0.598 | 0.617 | 0.637 |

**Weeks B wins–loses against A:**

| | capture@10 | Spearman |
|---|---|---|
| WR | 47–32 (Wilcoxon p 0.018) | 49–30 |
| RB | 41–32, median +0.001 | 50–29 |
| TE | 31–34 | 44–35 |
| FLEX | 50–29 | 61–18 |

### The pre-registered verdict (§5)

| success cell | S1 ≥ +0.02 and CI excludes 0 | S2 consistent | S3 ≥ ⅓ of ECR gap | S4 early ≥ late | S5 no breach |
|---|:-:|:-:|:-:|:-:|:-:|
| **WR capture@10** | ✔ +0.0223 | ✔ 5/5 seasons, 5/5 LOSO | ✔ 0.70 | ✔ +0.038 vs +0.017 | ✔ |
| **WR capture@5** | ✔ +0.0275 | ✔ 5/5, 5/5 | ✔ 0.49 | ✔ +0.063 vs +0.007 | ✔ |
| RB capture@10 | ✗ | ✗ | ✗ (0.02) | ✗ | ✔ |
| RB capture@5 | ✗ | ✗ | ✗ | ✗ | ✔ |

- **Guardrail breaches: none.** No B − A result in capture@5/10/20/50, Spearman or pairwise at any
  position, or in FLEX capture@10/25, Spearman or pairwise, is significantly negative.
- **Verdict: SUCCESS**, in Full PPR and in Half-PPR.

### Post-hoc qualifier: B against the shuffled-feature null (amendment A2)

The null arm N gets the same seven columns permuted across players. It passes gate G12: every
capture@5/@10 CI includes 0. But **its WR capture@5 is +0.014 over the season and +0.043\* in weeks
1–6**, so B's capture@5 gain might partly be "any model perturbation". Pairing B against N
directly:

| B − N | full season | EARLY | MID | LATE |
|---|---|---|---|---|
| **WR capture@10** | **+0.0290\*** (54–25) | **+0.0474\*** | **+0.0268\*** | +0.0140 |
| WR capture@5 | +0.0138 [−0.008, +0.036] | +0.0204 | +0.0145 | +0.0067 |
| FLEX capture@10 | **+0.0215\*** | +0.0207 | +0.0142 | **+0.0310\*** |
| RB capture@10 | −0.0009 | +0.0028 | +0.0010 | −0.0069 |
| TE capture@10 | −0.0020 | −0.0031 | +0.0012 | −0.0048 |

- **The WR top-10 gain is information:** B beats the shuffled null by more than it beats A.
- **The WR top-5 gain is not separable from the null.** The pre-registered verdict stands, but the
  honest reading is that **WR capture@10 is the finding and capture@5 is fragile.**
- Half-PPR gives the same pattern: WR capture@10 B − N +0.0283\*, capture@5 +0.0136.

---

## 2. The twelve questions

### 1. Did historical information improve RB?

**No, not at the top.**

| RB, B − A | value | 95% CI |
|---|---:|---|
| capture@5 | −0.004 | [−0.024, +0.015] |
| capture@10 | +0.000 | [−0.013, +0.014] |
| capture@20 | +0.000 | |
| Spearman | **+0.0043\*** | |
| pairwise | **+0.0021\*** | |

- No LOSO fold is significant at capture@5 or @10. B − N at capture@10 is −0.001.
- **The null is not because history is irrelevant at RB. Two real effects cancel** (movement
  attribution, §3.5):
  - rescuing quiet RB stars adds +0.041\*, and players whose role was stronger last season add
    +0.015\*;
  - demoting players whose role has grown this season costs −0.055\*.
- RB's ECR gap is untouched: capture@10 +0.0228 → +0.0224.

### 2. Did it improve WR?

**Yes.**

| WR, B − A | value | 95% CI |
|---|---:|---|
| capture@10 | **+0.0223** | [+0.0068, +0.0384] |
| capture@5 | +0.0275 | [+0.0057, +0.0502] |
| capture@25 | +0.0118\* | |
| Spearman | +0.0065\* | |
| pairwise | +0.0031\* | |

- The effect fades with depth: capture@20 +0.009 and capture@50 +0.001, neither significant.
- capture@10 is positive in every season (+0.018 to +0.028) and significant in every
  leave-one-season-out fold (+0.021 to +0.023).
- **The capture@10 gain survives the null comparison; capture@5 does not** (§1).

### 3. Did it improve TE?

**Not the top: capture@5 +0.012, capture@10 +0.004, both not significant.**

- The broad ordering improves: Spearman +0.0070\*, pairwise +0.0031\*.
- Point error falls: MAE 3.478 → 3.438\*.
- Quiet-star recall rises from 60% to 70%, matching ECR. The TE net at the top is still ≈ 0.

### 4. Did it improve FLEX?

**Yes, except the top 5.**

| FLEX, B − A | value |
|---|---:|
| capture@10 | **+0.019\*** (B − N +0.0215\*) |
| capture@20 | +0.016\* |
| capture@25 | +0.013\* |
| capture@50 | +0.0055\* |
| Spearman | +0.0053\* (61–18 weeks) |
| pairwise | +0.0024\* |
| capture@5 | −0.013 [−0.034, +0.008] |

- **FLEX capture@5 is negative in 4 of 5 LOSO folds, none significant.** It is significantly
  negative in 2021 (−0.064\*) and 2023 (−0.044\*).
- It is not a pre-registered guardrail, but it is reported here so a deeper gain does not hide a
  top-5 loss.
- **One hypothesis, not tested:** B raises its average WR prediction more than its RB prediction
  (bias shift +0.10 vs +0.03 points). That can move WRs above RBs at FLEX's very top, where RBs
  dominate.

### 5. Was the effect strongest early in the season?

**At WR, yes.**

| WR, B − A | EARLY (1–6) | MID (7–12) | LATE (13–17) |
|---|---:|---:|---:|
| capture@10 | **+0.038\*** | +0.015 | +0.017 |
| capture@5 | +0.063\* | +0.016 | +0.007 |
| Spearman | +0.014\* | +0.003 | +0.004 |

- Against the null, WR capture@10 is +0.047\* EARLY, +0.027\* MID and +0.014 LATE.
- **B closes 80% of ECR's EARLY WR top-10 gap** (+0.0475) **and 58% of its LATE gap**.
- FLEX: EARLY capture@10 +0.042\*.
- **RB and TE show no significant period effect at the top.**

**A caution on early-season measurement.** The null arm itself moved several EARLY cells: WR
capture@5 +0.043\*, TE capture@10 +0.023\*, FLEX capture@10 +0.021\*. The first six weeks are where
ECR's lead over Alpha is largest, and any perturbation of the model moves them. EARLY effects need the null
comparison, and only WR capture@10 survives it.

### 6. Did it specifically improve the top 10?

**At WR and FLEX, yes: capture@10 +0.022\* and +0.019\*, both beating the null.** WR precision@10 is
+0.019 [−0.002, +0.040].

**At RB and TE, no.**

The top-of-board gain is concentrated at depth 5–25. It is not a deep-board change leaking upward.

### 7. Did it reduce Alpha's ECR gap?

**At WR, substantially. At TE, somewhat. At RB, no.**

| ECR − A → ECR − B | capture@5 | capture@10 | Spearman | usage-surprise piece `G_S` @10 |
|---|---|---|---|---|
| RB | +0.013 → +0.017 | +0.0228\* → +0.0224\* (2%) | +0.0375 → +0.0332 | +0.0290 → +0.0237 (18%) |
| **WR** | +0.0567\* → +0.0291\* (49%) | **+0.0320\* → +0.0097 (70%; no longer significant)** | +0.0305 → +0.0240 (21%) | **+0.0453 → +0.0213 (53%)** |
| TE | +0.0365\* → +0.0250\* (31%) | +0.0258\* → +0.0214\* (17%) | +0.0343 → +0.0273 (20%) | +0.0350 → +0.0263 (25%) |
| FLEX | +0.022\* → +0.035\* | +0.0388\* → +0.0198\* (49%) | +0.0314 → +0.0260 | — |

- **W8's decomposition of B − A at WR** (capture@10): +0.0223 = `G_S` +0.0240\* + `G_F` −0.0069\*
  + `G_C` +0.0052.
- **B's gain is exactly the kind of edge ECR has:** its top 10 anticipates more of the usage that
  pre-Friday data does not forecast.
- It gives up a little forecastable usage and gains nothing significant in conversion.
- **ECR keeps its broad-ordering lead everywhere:** Spearman gaps of +0.024 to +0.033 remain.

### 8. Did it fix the W5 top-of-board problem?

**It shrinks it at WR. It does not fix it, and RB is unchanged.**

**The cliff** (capture@10 against a same-Spearman copula null, W5's construction; A's cliff
reproduces W7 exactly):

| | A | B |
|---|---:|---:|
| WR | −0.080\* | **−0.062\*** (23% smaller) |
| RB | −0.071\* | −0.073\* |
| TE | −0.010 | −0.010 |

**The W5 misses, per week:**

| | A | B | ECR | B − A |
|---|---:|---:|---:|---:|
| WR false negatives (top-5 finishers ranked outside the top 24) | 1.63 | **1.47** | 1.46 | −0.165\* |
| WR false positives (top-10 picks finishing outside the top 24) | 4.29 | 4.06 | 3.87 | −0.23, CI [−0.46, +0.003] |
| RB false negatives | 1.09 | 1.06 | | −0.03 |
| RB false positives | 2.65 | 2.62 | | −0.03 |
| TE false negatives | 0.68 | 0.61 | | −0.08 |
| TE false positives | 2.25 | 2.30 | | +0.05 |

B's WR false negatives match ECR's rate. None of the RB or TE changes is significant.

**Quiet established players.** These are prior-season top-12 players, coming off a game below their
prior-season PPG, who then finish in the top 10. The table shows how often each board has them in
its top 10:

| | A | B | ECR | B − A |
|---|---:|---:|---:|---:|
| RB (140 cases) | 52% | **65%** | 64% | +0.13\* |
| WR (118) | 51% | **66%** | 75% | +0.15\* |
| TE (164) | 60% | **70%** | 70% | +0.10\* |

**This is the pattern W8 and W9 found ECR exploiting.** History matches ECR's quiet-star recall at
RB and TE, and closes two-thirds of the gap at WR.

### 9. Did it hurt the deeper board or another position?

**No.**

- **No guardrail breach.**
- **Every position's Spearman, Kendall and pairwise accuracy improves significantly.**
- capture@50 is flat at RB, WR and TE (−0.001 to +0.001) and up at FLEX (+0.0055\*).
- **Point error:** MAE falls at WR (4.424 → 4.386\*) and TE (3.478 → 3.438\*), and is unchanged
  at RB (4.506 → 4.490).
- **Calibration by predicted decile** is essentially unchanged. Both models under-predict every
  decile by about 1 point, as MAE-trained median predictors do.

**The watch items:**

- FLEX capture@5 (−0.013, not significant);
- RB, where history's rescues are paid for by breakout demotions (§3.5), so the net is zero.

### 10. How much of the historical information is new versus duplicated?

**About 60% of it is linearly implied by Alpha's current features, in every period. The other ~40%
is what helps.**

**R² of each historical feature from Alpha's 11 current features** (evaluated player-weeks with a
prior season):

| | `prior_ppg` | `prior_opp_pg` | `prior_tsh` | `prior_snap` | `prior_rank` | `prior_games` |
|---|---:|---:|---:|---:|---:|---:|
| WR EARLY / LATE | 0.66 / 0.61 | 0.69 / 0.59 | 0.70 / 0.60 | 0.67 / 0.51 | 0.61 / 0.54 | 0.20 / 0.21 |
| RB EARLY / LATE | 0.65 / 0.59 | 0.67 / 0.60 | 0.56 / 0.49 | 0.64 / 0.53 | 0.52 / 0.46 | 0.16 / 0.17 |
| TE EARLY / LATE | 0.65 / 0.63 | 0.67 / 0.64 | 0.67 / 0.62 | 0.63 / 0.55 | 0.56 / 0.52 | 0.31 / 0.30 |

**The prediction that history is "new early, redundant late" was wrong.**

- Early-season R² is slightly *higher*. Alpha's 3-game lags cross season boundaries, so in weeks
  1–6 its "recent form" partly *is* last season's final games.
- Correlations of `prior_ppg`:
  - with `fp_ppr_avg_last3`: 0.74 EARLY, 0.63–0.66 LATE;
  - with `fp_ppr_avg_season_to_date`: 0.57–0.64 EARLY, rising to 0.75–0.77 LATE.

**The decisive test is B − A itself.** With every current feature present, the historical columns
still lift the WR top 10, and they beat the same columns shuffled.

**The full-season level is the new information**: a stable baseline that recent games only
partly reveal.

**Which category drives it?** Removing one category at a time (attribution only, never selection):

| WR, B − A | capture@10 | capture@5 |
|---|---:|---:|
| B (all seven) | +0.0223\* | +0.0275\* |
| B − production | +0.0155\* (−30%) | +0.0114 (−59%) |
| B − opportunity | +0.0127 (−43%) | +0.0174 |
| B − role | +0.0166\* (−26%) | +0.0364\* |

**No single category is necessary; they substitute for one another.** Last season's production,
touches and role all encode "who this player is".

**The historical-only board C** ranks by last season's PPG alone:

- **It is far worse over the full board:** Spearman −0.18 to −0.22\*, capture@50 −0.06 to −0.09\*.
- **But at the WR top it is statistically indistinguishable from Alpha:** capture@5 +0.011,
  capture@10 −0.007. The RB top 10 is −0.023, also not significant. TE is worse: −0.034\*.

**At the very top of WR, last season's PPG alone already matches Alpha.**

### 11. How robust is the result?

**For WR capture@10, very.**

- **Every season is positive:** 2021 +0.028, 2022 +0.019, 2023 +0.023, 2024 +0.024, 2025 +0.018.
- **Every LOSO fold is significant:** +0.021 to +0.023.
- **Half-PPR:** +0.0215\*, with all seasons positive and all folds significant.
- **It beats the null:** +0.029\*.
- No single season carries it.

**WR capture@5 is weaker.** It meets S2 (5/5 seasons positive, 5/5 folds significant), but not the
null comparison.

**It depends on position and depth:**

- **position:** WR only at the top;
- **depth:** the top 5–25, fading by 50.

**Two structural caveats:**

- **The 2021–2025 weeks informed the hypothesis** (W9 read WR capture@10 on these same weeks).
- **2026 is unavailable.** The repository holds no 2026 stats, games or production predictions,
  so no independent confirmation exists yet.

### 12. What is the single best next research question?

> **Can Alpha tell a quiet week from a real role change before kickoff?** Can it keep history's
> quiet-star rescue without paying its breakout penalty?

The evidence points straight at it:

- history's whole WR gain, and its RB gain, comes from keeping established players up after quiet
  games (+0.050 WR, +0.041 RB);
- its whole cost is demoting players whose current role has outgrown last season (−0.050 WR,
  −0.055 RB);
- at RB the two cancel, and that is the entire RB null.

**A pre-registered test of whether pre-Friday information separates the two would:**

- decide whether the RB gap is reachable at all;
- say whether the WR gain can grow.

The candidate information is the current-season role trend already in the repository, and
timestamped weekly news when it can be measured.

**The 2026 run (§9) remains the only independent confirmation of W10 itself.**

---

## 3. Supporting detail

### 3.1 Per season and leave-one-season-out, B − A, Full PPR

| cell | 2021 | 2022 | 2023 | 2024 | 2025 | LOSO folds significant |
|---|---:|---:|---:|---:|---:|---:|
| **WR capture@10** | +0.028 | +0.019 | +0.023 | +0.024 | +0.018 | **5/5** |
| **WR capture@5** | +0.026 | +0.038 | +0.030 | +0.041 | +0.005 | **5/5** |
| WR capture@20 | +0.015 | +0.022\* | +0.010 | −0.012 | +0.007 | 0/5 |
| WR Spearman | +0.004 | +0.012\* | +0.007\* | +0.004 | +0.006\* | 5/5 |
| RB capture@10 | +0.009 | +0.008 | −0.028 | +0.001 | +0.011 | 0/5 |
| RB capture@5 | −0.022 | +0.008 | −0.018 | +0.032\* | −0.014 | 0/5 |
| TE capture@10 | +0.005 | +0.019 | −0.002 | +0.014 | −0.013 | 0/5 |
| TE capture@5 | +0.004 | −0.010 | +0.002 | +0.029 | +0.035 | 0/5 |
| FLEX capture@10 | −0.008 | +0.026 | +0.028 | +0.046\* | +0.009 | 4/5 |
| FLEX capture@5 | −0.064\* | +0.019 | −0.044\* | +0.014 | +0.017 | 0/5 (4 negative) |

### 3.2 Half-PPR (replication only; never selects)

**Verdict: SUCCESS**, with the same two cells and no breach.

| B − A | value |
|---|---:|
| WR capture@10 | +0.0215\* |
| WR capture@5 | +0.0282\* |
| WR capture@25 | +0.0120\* |
| RB capture@10 | +0.0005 |
| TE capture@10 | +0.0047 |
| FLEX capture@10 | +0.0172\* |
| FLEX capture@5 | −0.0133 |

Spearman improves at every position.

### 3.3 The null arm (G12)

| | capture@5 | capture@10 |
|---|---:|---:|
| RB | +0.007 | +0.001 |
| WR | +0.014 | −0.007 |
| TE | −0.003 | +0.007 |

All six CIs include 0, so **G12 passes.**

**Seven shuffled columns are not free.** They cost small but significant amounts:

- WR Spearman −0.0014\*;
- FLEX Spearman −0.0011\*, Kendall −0.0010\* and pairwise −0.0005\*;
- RB capture@50 −0.0026\*.

Several EARLY cells move (§2, Q5). B's real columns overcome that cost.

### 3.4 Periods: B − A capture@10, with ECR − A for scale

| | EARLY B | EARLY ECR | MID B | MID ECR | LATE B | LATE ECR |
|---|---:|---:|---:|---:|---:|---:|
| RB | −0.003 | +0.043\* | +0.000 | +0.015 | +0.004 | +0.013 |
| WR | **+0.038\*** | +0.048\* | +0.015 | +0.022 | +0.017 | +0.029 |
| TE | +0.020 | +0.041\* | −0.009 | +0.036\* | +0.005 | −0.002 |
| FLEX | **+0.042\*** | +0.070\* | +0.007 | +0.030\* | +0.011 | +0.020 |

### 3.5 Movement attribution: who enters and leaves the top 10

B − A capture@10 is split exactly by the category of each player entering or leaving the top 10.
Categories are first-match, fixed in pre-registration §6.5. The split sums to G; the runner aborts
otherwise.

| | QUIET_STAR | ROLE_STRONGER_BEFORE | ROLE_STRONGER_NOW | SMALL_SAMPLE | OTHER | total |
|---|---:|---:|---:|---:|---:|---:|
| RB | **+0.041\*** | +0.015\* | **−0.055\*** | −0.007\* | +0.007 | +0.000 |
| WR | **+0.050\*** | +0.008\* | **−0.050\*** | −0.000 | +0.014 | **+0.022\*** |
| TE | **+0.026\*** | +0.001 | −0.009\* | −0.001 | −0.013 | +0.004 |

**Counts of movers:**

| | entering B's top 10 | leaving it |
|---|---|---|
| RB | 59 QUIET_STAR | 71 ROLE_STRONGER_NOW |
| WR | 70 QUIET_STAR | 72 ROLE_STRONGER_NOW |
| TE | 40 QUIET_STAR | 17 ROLE_STRONGER_NOW |

**This split is descriptive.** It says where the capture changed, not why the model moved each
player.

**Players.** These examples only illustrate the population result above:

- **Most often promoted correctly:** A.J. Brown (8 of 10 promotions hit), Derrick Henry (7 of 15),
  T.J. Hockenson (4 of 7).
- **Most often promoted wrongly:** Tyreek Hill (5 of 19 hit), Davante Adams (6 of 17) and Josh
  Jacobs (2 of 12). All are mostly QUIET_STAR promotions.

**The rescue is a population effect, not a guarantee for any one star.**

### 3.6 Point diagnostics (secondary; Full PPR only)

| | MAE A → B | RMSE B − A | bias A → B |
|---|---|---:|---|
| RB | 4.506 → 4.490 | −0.023 | −1.27 → −1.24 |
| WR | 4.424 → 4.386\* | −0.072\* | −1.21 → −1.11 |
| TE | 3.478 → 3.438\* | −0.070\* | −1.17 → −1.12 |

Calibration by predicted decile is unchanged in shape.

---

## 4. Decision tree (brief §26)

**Historical Alpha clearly improves the top, at WR.**

→ **Identify which historical information drives it.** The mechanism is the quiet-star rescue
(§3.5). No one category is necessary: production, opportunity and role substitute for one another
(Q10).

→ **Design a focused follow-up rather than shipping.** The breakout penalty is what stops the same
mechanism from helping RB (Q12).

**It is not the full solution:**

- RB's and TE's top-of-board ECR gaps are essentially unchanged;
- the WR top-5 gain is fragile;
- 2026 is untested.

**Nothing was shipped.** The "helps one position, hurts another" branch does not apply: no
position is hurt. The FLEX top-5 lean and the RB cancellation are documented above, not averaged
away.

---

## 5. A priori predictions (pre-registration §11)

| # | prediction | outcome |
|---|---|---|
| 1 | WR S2 holds | ✔ 5/5 seasons, 5/5 LOSO (both cells) |
| 2 | WR EARLY > LATE | ✔ +0.038 vs +0.017 (capture@10) |
| 3 | no breach at WR/TE; RB may dip slightly | ✔ no breach anywhere; RB capture@5 −0.004 |
| 4 | Spearman improves slightly at WR and TE | ✔ +0.0065\*, +0.0070\* (and RB +0.0043\*) |
| 5 | verdict SUCCESS, carried by WR | ✔ |
| 6 | WR cliff shrinks −0.080 toward −0.06 | ✔ −0.080 → −0.062 |
| 7 | WR false positives decrease | ~ −0.23/week, CI just includes 0; false negatives fall significantly |
| 8 | historical-only much worse than Alpha (capture@10 −0.03 to −0.06) | ✗ only TE (−0.034\*); WR −0.007 and RB −0.023, both not significant; far worse deeper |
| 9 | the production category drives most of the WR gain | ✗ no single category is necessary |
| 10 | the null arm does nothing | ~ G12 passes; small Spearman costs and EARLY excursions |
| 11 | `prior_ppg` R² < 0.3 EARLY and > 0.5 LATE | ✗ 0.65 EARLY, 0.59–0.63 LATE |
| 12 | RB shows no effect | ✔ |

**Seven right, two partly right, three wrong.**

---

## 6. Validity

**Reproduction first.** Eight artifacts reproduced **byte-for-byte**: W5, W5-E1, W6, the W6
agreement file, W7, W8, the W8 null check and W9.

- W9 was reproduced again after the `through` edit to `durable_table` (A1).
- Production parity holds: 26,097 of 26,097 predictions are exact.

**All twelve gates pass** (`scripts/research/w10_validity_gates.py`):

| gate | result |
|---|---|
| G1 parity | 26,097/26,097 exact |
| G2 prior is prior | deleting seasons ≥ S moves 0 values over 10,168 player-seasons; 0 within-season variation |
| G3 B is W9's arm | 1,896 per-week decomposition values equal W9's `AD` cells, 0 mismatches |
| G4 no future information | no forbidden tokens; scrambling S's outcomes moves 0 of S's rows; the positive control (S + 1 moves) passes |
| G5 ECR never a feature | exactly 3 declared training calls, frames from `durable_panel` only; `durable_table` reads only `player_week_stats` |
| G6 walk-forward | 0 training frames contain the predicted season |
| G7 joins | 0 duplicate keys; `prior_games` correct for 300/300 seeded player-seasons; 0/300 `has_prior = 0` rows with an S − 1 game |
| G8 order-free | durable table identical with its input reversed |
| G9 universe / arm A | 0 mismatches against W8 positional (8,532 values), W7 positional (8,532), W7 FLEX (2,844), W9's ECR − A decomposition (1,896) and W7's A cliff; 79/79 weeks |
| G10 determinism | two full runs byte-identical (sha256 `7963324aea45af21…`) |
| G11 upstream | 8/8 artifacts byte-identical |
| G12 null arm | all six capture@5/@10 CIs include 0 |

**Process notes.**

- The runner was crash-tested on 2021 alone before the real run. Its output went to scratch, and
  only its structure was inspected.
- The gate comparisons were checked on that subset before the full run: 0 mismatches over 408 +
  4,284 values.
- A shell-scoping slip wrote the W9 re-run's output to `/` instead of scratch. It was moved; no
  result changed.

---

## 7. Files

| file | role |
|---|---|
| `docs/weekly/W10_PREREGISTRATION.md` | pre-registration with A1 (pre-results) and A2 (post-hoc) |
| `src/alpha_squad/evaluation/weekly/historical.py` | the historical-only ordering, W5 miss counts, movement categories, §5 verdict (18 tests in `tests/unit/test_weekly_historical.py`) |
| `scripts/research/w10_historical.py` | the runner |
| `scripts/research/w10_validity_gates.py` | G1–G12 |
| `scripts/research/w10_posthoc.py` | the A2 check |
| `reports/weekly/w10_results.json` | every per-week cell, summary, verdict, decomposition, cliff, calibration, redundancy and player list |
| `reports/weekly/w10_posthoc.json` | B − N |
| `scripts/research/w9_mechanisms.py` | `durable_table(con, through=2025)`: default = W9 exactly |

**Reproduce:**

```
uv run python scripts/research/w10_historical.py --out reports/weekly/w10_results.json
uv run python scripts/research/w10_validity_gates.py --repro-summary <W5-W9 reproduction record>
uv run python scripts/research/w10_posthoc.py
```
