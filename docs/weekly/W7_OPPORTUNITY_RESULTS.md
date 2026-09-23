# W7 — Can we predict a player's opportunity before Friday?

**Status: COMPLETE. Pre-registered verdict: HARM** (by §9's first clause, triggered at WR). In the
brief's three-way scheme this is **NO EFFECT**: opportunity is only somewhat predictable, and
using the prediction does not help the ranking.

Run exactly as pre-registered in `docs/weekly/W7_PREREGISTRATION.md` (commit `0c46c30`, written
before any forecast was fitted). The instruments and all eleven gates were committed at `968b191`
before any result existed. **Research only. Production diff EMPTY. No ECR feature. Alpha's
ranking model is unchanged. No new production model.** No amendments.

---

## Can we actually predict future player opportunity before Friday?

**Partly, and the part we can predict is mostly already known to Alpha.**

Using only information that provably existed before Friday, the best forecast of a player's
week-*w* opportunity has these per-week rank correlations with the real thing:

- RB: about **0.71**
- WR: about **0.67**
- TE: about **0.63**

Across all player-weeks it explains about **40–48%** of the variation. That is better than
Alpha's ranking of *fantasy points* (0.67 / 0.64 / 0.58). So opportunity is somewhat easier to
predict than points. It is still far from knowable.

**Most of that predictability is already in Alpha.** Alpha's own 11 features, fed into a
simple linear model, reach 0.70 / 0.66 / 0.61. Every other pre-Friday signal we could find adds
only **+0.010 to +0.013** of rank correlation. That is statistically real but below the
pre-registered +0.02 bar at every position. A nonlinear model adds nothing (ridge ≈ CatBoost). A
fitted-model opportunity estimate we could not prove was point-in-time also adds nothing.

**The predictable part doesn't reach the top of the board, where it would matter.** Among the 5
players Alpha already ranks highest at a position, the forecast's rank correlation with realized
opportunity is only **0.12–0.30**. The new information doesn't lift it at RB (0.124 → 0.124). At
WR it makes it worse (0.195 → 0.165).

**Giving Alpha the new information does not improve its top 10, and at WR it slightly hurts it.**

- **RB capture@10:** +0.005, CI contains zero.
- **WR capture@10:** **−0.013**, CI [−0.025, −0.001]. It is negative in all five
  leave-one-season-out folds and in Half-PPR.
- **Whole board:** Spearman improves a little everywhere (RB +0.011, WR +0.006, FLEX +0.007, all
  significant). The added information helps the middle of the board, not the top.

**Most of W5's perfect-opportunity prize is not available on Friday.** Knowing each player's
realized usage would add about +0.18 to +0.20 capture@10. Realistic pre-Friday forecasting
recovers **+2.6% of that at RB, −6.3% at WR and −1.7% at TE**. In practice that is none of it.
The value of the usage oracle lies in week-specific usage surprises that nothing available before
Friday can see.

---

## 0. Reproduction and validity — checked before any result was read

| | result |
|---|---|
| **W5 re-run** | **exact** — 568,947 numeric leaves, max abs diff 0, identical key sets |
| **W6 re-run** | **exact** — `w6_results.json` 92,038 leaves and `w6_agreement.json` 11,162 leaves, max abs diff 0 |
| **W6 production-control parity** | retraining with production's loss reproduces the stored weekly predictions exactly (W6's arm A, part of the exact re-run above: 29,376/29,376) |
| **W7 G1 — `ALPHA_PLUS_OPP` fidelity** | with no added features, the extended trainer reproduces production's stored RB/WR/TE predictions **26,097 / 26,097 exactly**, max abs diff **0.0** |
| **production files** | `git diff ec9e3c2^..HEAD` over `models/ league/ api/ cli.py market/ features/ identity/ ingest/ sources/` is **empty** |

**The eleven pre-registered gates:**

| gate | check | result |
|---|---|---|
| G1 | production parity | **PASS** — 26,097/26,097 exact |
| G2 | no future usage | **PASS** — nulling every `player_week_stats` row at/after the ranked week and deleting that week's usage and depth rows moved **0** predictor values across 2,861 audited player-weeks; the check is proven non-vacuous (the outcome columns *do* change) |
| G3 | no post-Friday injury | **PASS** — no injury-like field in any main feature |
| G4 | no post-Friday depth chart | **PASS** — covered by G2 (the week's chart is deleted there) |
| G5 | no Vegas / market / ECR | **PASS** — no forbidden source referenced by the feature SQL |
| G6 | no realized game info in context | **PASS** — the opponent measure is recomputed under G2's redaction and unchanged |
| G7 | walk-forward | **PASS** — 0 training frames contain the season they predict |
| G8 | Friday cutoff | **PASS** — 0 evaluated players whose team had already kicked off |
| G9 | identical universe | **PASS** — enforced inside the runner, which aborts on any mismatch |
| G10 | determinism | **PENDING** — running |
| G11 | upstream W3–W6 reproduce | **PENDING** — running |

---

## 1. What "opportunity" means here

All targets are realized in week *w*, for players who played. That is the same "given that the
player plays" universe every prior phase used.

| id | target | role |
|---|---|---|
| **T_XFP** | `total_fantasy_points_exp`: fantasy points expected from the player's usage (ffopportunity) | **primary**. It is exactly what W5's `ORACLE_USAGE` ranked by |
| T_OPP | targets + carries | secondary |
| T_TGT | targets | secondary |
| T_CAR | carries (RB) | secondary |
| T_TSH | target share (WR, TE) | secondary |
| T_SNP | snap share | secondary |

`T_XFP` exists for **91.2% (RB) / 90.1% (WR) / 90.5% (TE)** of evaluated player-weeks. The
other targets exist for 100%. **Routes run are absent from every ingested source.** They are
recorded as a data-acquisition item, not approximated (§2.2 of the pre-registration).

## 2. What was allowed in

| class | meaning | used |
|---|---|---|
| **A** | provably existed before the Friday cutoff | **the only class in the main test** |
| B | probably pre-Friday, but its historical timing cannot be proven | one labelled sensitivity (lagged usage-expected points), never in the verdict |
| C | knowable only after the cutoff | not used |
| D | contains the game's outcome | only as the `ORACLE_USAGE` ceiling |

**What Alpha already has (S0):** its 11 production features. These already include 3-game
averages of targets, carries, receptions, target share and snap share.

**Genuinely new Class A information (NEW, 9 features):**

- last-game opportunity
- last-game snap share
- opportunity trend
- opportunity volatility
- air-yards share
- carry share
- weeks since last game
- the opponent's opportunity allowed to the position so far this season
- last week's depth-chart slot

**A double-counting control (REDUNDANT, 4 features):** 5-game versions of what Alpha already
holds. This control is what separates new information from more of the same.

Injury status is **not** in the main test. Its only provably-pre-Friday form covers 0.2% of
player-weeks (W5 §9).

---

## 3. RB — how predictable is opportunity?

Primary target `T_XFP`: per-week Spearman and top-10 capture of the realized target, pooled R²,
and mean weekly MAE (in expected fantasy points). All forecasts are walk-forward, trained on
`[2015, S−1]`.

| forecast | Spearman | capture@10 | R² | MAE |
|---|---:|---:|---:|---:|
| last game | 0.579 | 0.721 | −0.205 | 5.30 |
| 3-game mean | 0.648 | 0.760 | 0.259 | 4.25 |
| weighted 3-game | 0.653 | 0.758 | 0.246 | — |
| trend | 0.607 | 0.739 | 0.012 | — |
| simple combination | 0.690 | 0.780 | 0.450 | 3.78 |
| **M_S0** (Alpha's features, ridge) | 0.699 | 0.782 | 0.463 | 3.75 |
| **M_NEW** (+ Class A new) | **0.709** | 0.793 | 0.479 | 3.67 |
| M_RED (+ more of the same) | 0.700 | 0.786 | 0.469 | 3.70 |
| M_CB (M_NEW as CatBoost) | 0.709 | 0.795 | 0.480 | 3.66 |
| M_B (+ Class B xFP) | 0.709 | 0.798 | 0.479 | 3.67 |

Alpha's own *points* board ranks realized points at **0.668**.

**Secondary targets (M_NEW Spearman):**

| targets + carries | targets | carries | snap share |
|---:|---:|---:|---:|
| 0.778 | **0.590** | 0.762 | 0.804 |

RB receiving work is the least predictable opportunity measure in the study.

**RB is the one position where the new information is genuinely new.**

- `Δ_NEW` = **+0.0105** [+0.0056, +0.0155].
- More of the same adds nothing: `Δ_RED` = +0.0009 [−0.0013, +0.0031].
- The difference, `Δ_NEW − Δ_RED` = +0.0096, is significant.

It is still half the +0.02 bar. **C1 not met.**

## 4. WR

| forecast | Spearman | capture@10 | R² | MAE |
|---|---:|---:|---:|---:|
| last game | 0.492 | 0.646 | −0.439 | 5.43 |
| 3-game mean | 0.597 | 0.700 | 0.180 | 4.17 |
| simple combination | 0.643 | 0.706 | 0.379 | 3.73 |
| **M_S0** | 0.660 | 0.726 | 0.402 | 3.68 |
| **M_NEW** | **0.672** | 0.737 | 0.418 | 3.62 |
| M_RED | 0.667 | 0.743 | 0.418 | 3.62 |
| M_CB | 0.670 | 0.736 | 0.424 | 3.59 |
| M_B | 0.672 | 0.745 | 0.420 | 3.61 |

Alpha's points board: **0.636**.

**Secondary targets (M_NEW Spearman):**

| targets + carries | targets | target share | snap share |
|---:|---:|---:|---:|
| 0.736 | 0.738 | 0.754 | 0.810 |

- `Δ_NEW` = **+0.0118** [+0.0080, +0.0155].
- `Δ_RED` = +0.0066, also significant. **About 55% of the apparent gain is re-expression.**
- `Δ_NEW − Δ_RED` = +0.0052 [+0.0010, +0.0093].

**C1 not met.** On capture@10 and MAE, the redundant control matches or beats the new information:
capture@10 +0.0166 (RED) vs +0.0113 (NEW); MAE −0.0648 vs −0.0642.

## 5. TE — the comparison position

| forecast | Spearman | capture@10 | R² | MAE |
|---|---:|---:|---:|---:|
| last game | 0.421 | 0.680 | −0.492 | 4.31 |
| 3-game mean | 0.534 | 0.732 | 0.128 | 3.34 |
| simple combination | 0.586 | 0.751 | 0.341 | 2.99 |
| **M_S0** | 0.612 | 0.776 | 0.379 | 2.92 |
| **M_NEW** | **0.625** | 0.781 | 0.393 | 2.86 |
| M_RED | 0.621 | 0.789 | 0.398 | 2.86 |
| M_CB | 0.617 | 0.774 | 0.392 | 2.85 |
| M_B | 0.625 | 0.783 | 0.396 | 2.86 |

Alpha's points board: **0.576**. TE opportunity is the least forecastable of the three positions.

- `Δ_NEW` = +0.0127, significant.
- `Δ_RED` = +0.0083, significant.
- **`Δ_NEW − Δ_RED` = +0.0044 [−0.0011, +0.0101], which contains zero.** At TE the "new"
  information cannot be told apart from more of the same.
- CatBoost is significantly *worse* than ridge (−0.0080).

**C1 not met.**

### Calibration

M_NEW's forecast of `T_XFP` is well calibrated where it matters. The top predicted decile gets
exactly what it is forecast to get:

| position | top decile: predicted | top decile: realized |
|---|---:|---:|
| RB | 16.9 | 16.8 |
| WR | 15.6 | 15.6 |
| TE | 12.2 | 12.2 |

Mid-deciles are over-forecast by roughly 0.5–1.1 expected points, most at WR. The limit is
resolution (telling players apart), not bias.

### Snap share is the most forecastable quantity — and it is not the point

Snap share forecasts at 0.79–0.81, and it is where the new features add the most (`Δ_NEW`
+0.015–0.016). The largest `Δ_NEW` anywhere in the study is WR snap share, +0.0163, which is still
under the bar. But snap share is the opportunity measure least connected to fantasy points. The
week-to-week variation that separates a top-10 week from a top-25 week is in targets and carries,
and there the forecasts sit at 0.59–0.78.

---

## 6. Q4 — what Alpha already captures, and Q5 — what is genuinely new

| | RB | WR | TE |
|---|---:|---:|---:|
| naive 3-game mean | 0.648 | 0.597 | 0.534 |
| simple combination of baselines | 0.690 | 0.643 | 0.586 |
| **Alpha's features alone (M_S0)** | **0.699** | **0.660** | **0.612** |
| + all genuinely new Class A info (M_NEW) | 0.709 | 0.672 | 0.625 |
| **share of the achievable forecast Alpha already holds**¹ | **84%** | **84%** | **86%** |
| new-information gain, net of the redundancy control | **+0.0096** ✱ | +0.0052 ✱ | +0.0044 (n.s.) |
| + Class B lagged xFP (M_B − M_NEW) | −0.0004 | +0.0001 | −0.0004 |
| nonlinear form (M_CB − M_NEW) | −0.0005 | −0.0024 | **−0.0080** ✱ |

¹ `(M_S0 − 3-game mean) / (M_NEW − 3-game mean)`: the share of the fitted forecasts' improvement
over the naive baseline that Alpha's own information already delivers.

**The ceiling is set by the information, not the model form or the feature count.** More of the
same saturates, a nonlinear learner adds nothing, and the one out-of-class source we could test
adds nothing either. It is lagged usage-expected points from a fitted model, which is exactly the
kind of quantity one would expect to help.

**Where the new information helps, by Alpha's predicted rank band.** The table shows forecast
Spearman within the band, pooled across weeks, M_S0 → M_NEW.

| band | RB | WR | TE |
|---|---|---|---|
| **top 5** | 0.124 → **0.124** | 0.195 → **0.165** | 0.284 → 0.300 |
| 6–10 | 0.154 → 0.196 | 0.049 → 0.109 | 0.128 → 0.158 |
| 11–20 | 0.140 → 0.191 | 0.036 → 0.139 | 0.169 → 0.201 |
| 21–50 | 0.445 → 0.485 | 0.261 → 0.308 | 0.315 → 0.355 |
| 51+ | 0.201 → 0.230 | 0.391 → 0.415 | 0.088 → 0.114 |

**This table is the core finding.** Among players Alpha already puts in its top 5, whose
opportunity will be largest this week is close to unpredictable from pre-Friday information. The
new information helps bands 6–50 and does nothing for the top 5 at RB. At WR it makes the top 5
worse.

---

## 7. Q6 — how much of W5's perfect-opportunity ceiling does realistic forecasting recover?

W5's `ORACLE_USAGE` ranks by the week's realized usage-expected points, which is Class D. Its
positional capture@10 advantage over current Alpha:

| | RB | WR | TE |
|---|---:|---:|---:|
| **L2 − L0** — perfect usage knowledge | +0.1816 | +0.2020 | +0.1916 |
| **L1 − L0** — Alpha + pre-Friday opportunity (`ALPHA_PLUS_OPP`) | +0.0047 | −0.0127 | −0.0033 |
| `FORECAST_USAGE − L0` — rank by the forecast alone | +0.0029 | −0.0017 | −0.0017 |
| **ladder share `R_L1`** | **+2.6%** | **−6.3%** | **−1.7%** |
| **forecast share `R_F`** | **+1.6%** | **−0.9%** | **−0.9%** |
| Half-PPR `R_L1` / `R_F` | +2.8% / +2.0% | −7.0% / +1.2% | −1.8% / −2.4% |

The picture is the same on the whole-board metric. Perfect usage knowledge adds +0.22 / +0.20 /
+0.24 Spearman, and `ALPHA_PLUS_OPP` recovers 4.8% / 2.7% / 1.7% of it.

**Realistic forecasting recovers essentially none of the perfect-opportunity ceiling.** The
ceiling W5 priced is the value of knowing this week's usage *surprise*, and a surprise is, by
construction, what a pre-Friday forecast cannot see.

---

## 8. Q7 — does forecasted opportunity improve the top of the board?

`ALPHA_PLUS_OPP` is production's CatBoost with production's hyperparameters, MAE loss and
walk-forward, plus the 9 NEW features and nothing else. It is compared against production
(`CF_A`), paired over 79 weeks.

| | effect | 95% CI | W–L–tied | Wilcoxon p |
|---|---:|---|---|---:|
| **RB capture@5** | +0.0018 | [−0.0126, +0.0165] | 27–25–27 | 0.84 |
| **RB capture@10** | +0.0047 | [−0.0058, +0.0152] | 35–30–14 | 0.44 |
| **WR capture@5** | −0.0147 | [−0.0332, +0.0031] | 31–32–16 | 0.23 |
| **WR capture@10** | **−0.0127** | **[−0.0250, −0.0006]** | 28–40–11 | 0.055 |
| TE capture@10 | −0.0033 | [−0.0175, +0.0108] | 29–32–18 | 0.73 |
| FLEX capture@10 | +0.0016 | [−0.0106, +0.0135] | 40–34–5 | 0.65 |
| RB capture@25 | +0.0097 | [+0.0021, +0.0176] ✱ | 45–28 | 0.023 |
| RB Spearman | +0.0107 | [+0.0069, +0.0147] ✱ | 54–25 | <0.001 |
| WR Spearman | +0.0055 | [+0.0033, +0.0078] ✱ | 55–23 | <0.001 |
| TE Spearman | +0.0041 | [−0.0007, +0.0087] | 46–33 | 0.075 |
| FLEX Spearman | +0.0071 | [+0.0053, +0.0090] ✱ | 63–16 | <0.001 |

**No.** The top-10 effect is null at RB and negative at WR, and the median weekly difference is
0.0000 at RB and −0.0015 at WR. What the new information improves is the ordering of the middle
and lower board: Spearman, pairwise accuracy and RB capture@25. That matches the rank-band table
in §6 exactly.

Ranking by the opportunity forecast alone (`FORECAST_USAGE`) is no better. It is significantly
worse at RB capture@5 (−0.0269 [−0.0498, −0.0039]) because it throws away efficiency, and null
at capture@10 everywhere.

**The W5 cliff did not shrink.** This was the mechanism check. The copula-null capture@10 cliff
goes:

| | before | after |
|---|---:|---:|
| RB | −0.0710 | −0.0729 |
| WR | −0.0800 | **−0.0963** |
| TE | −0.0096 | −0.0164 |

Half-PPR agrees (WR −0.0873 → −0.1050).

**The benchmark gap is untouched.** ECR still beats `ALPHA_PLUS_OPP` at capture@10 at every
position (RB −0.018, WR −0.045, TE −0.029, all significant). ECR is used here only as a
comparator, never as a feature.

### Guardrails

No practical breach: no degradation with a CI excluding zero **and** magnitude ≥ 0.005 in TE
capture@10, any capture@50, FLEX capture@25 or any Spearman. The degradations are all at the top
of the WR board, which is the primary cell itself.

---

## 9. Robustness

### Leave-one-season-out

| | drop 2021 | drop 2022 | drop 2023 | drop 2024 | drop 2025 |
|---|---:|---:|---:|---:|---:|
| RB `ALPHA_PLUS_OPP` c@10 | −0.0005 | +0.0066 | +0.0026 | +0.0089 | +0.0057 |
| **WR `ALPHA_PLUS_OPP` c@10** | **−0.0137 ✱** | −0.0091 | **−0.0148 ✱** | −0.0111 | **−0.0147 ✱** |
| RB `Δ_NEW` (forecast) | +0.0089 ✱ | +0.0111 ✱ | +0.0098 ✱ | +0.0121 ✱ | +0.0105 ✱ |
| WR `Δ_NEW` | +0.0125 ✱ | +0.0083 ✱ | +0.0121 ✱ | +0.0145 ✱ | +0.0114 ✱ |
| TE `Δ_NEW` | +0.0133 ✱ | +0.0121 ✱ | +0.0142 ✱ | +0.0109 ✱ | +0.0130 ✱ |

### Per season

| | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| RB `ALPHA_PLUS_OPP` c@10 | +0.0236 ✱ | −0.0027 | +0.0130 | −0.0149 | +0.0008 |
| WR `ALPHA_PLUS_OPP` c@10 | −0.0089 | **−0.0267 ✱** | −0.0043 | −0.0200 | −0.0046 |
| RB `Δ_NEW` | +0.0162 ✱ | +0.0080 | +0.0134 ✱ | +0.0030 | +0.0106 ✱ |
| WR `Δ_NEW` | +0.0091 ✱ | +0.0256 ✱ | +0.0105 ✱ | −0.0011 | +0.0133 ✱ |
| TE `Δ_NEW` | +0.0105 | +0.0149 ✱ | +0.0066 | +0.0210 ✱ | +0.0116 ✱ |

**Both findings are stable.**

- The forecast gain is small, real and never large. Every LOSO fold is significant. One season
  (WR 2022, +0.0256) clears +0.02, and it is not the rule.
- The WR harm is **negative in every fold and every season**. It is significant in three of five
  LOSO folds and in Half-PPR (−0.0139 [−0.0268, −0.0014]).
- RB is noise around a small positive, with one significant season (2021) and one negative
  (2024).

### Half-PPR (replication only, never selects)

| | RB | WR | TE | FLEX |
|---|---:|---:|---:|---:|
| `ALPHA_PLUS_OPP` c@10 | +0.0052 | **−0.0139 ✱** | −0.0033 | +0.0015 |
| Spearman | +0.0104 ✱ | +0.0053 ✱ | +0.0040 | +0.0067 ✱ |

This is the same result in both scoring formats.

---

## 10. The verdict, by the pre-registered order

| order | verdict | condition | holds? |
|---|---|---|---|
| 1 | **HARM** | `ALPHA_PLUS_OPP` capture@10 at RB or WR has a CI excluding zero in the negative direction, or a practical breach with no C2 gain | **YES** — WR capture@10 −0.0127 [−0.0250, −0.0006] |
| 2 | SUCCESS | C1 and C2 at the same position | no — C1 fails everywhere; C2 fails everywhere |
| 3 | PARTIAL | C1 at RB or WR and a positive significant capture@10 effect | no — C1 fails |
| 4 | NO EFFECT | anything else | — |

**The verdict is HARM.**

**It is not a technicality of the kind W6's amendment A1 fixed.** The magnitude (−0.0127) is 2.5×
the 0.005 practical floor and 63% of the success threshold. It is negative in every
leave-one-season-out fold and every season, and it replicates in Half-PPR.

**It is also a small, marginal harm.** The CI's upper end is −0.0006. The Wilcoxon test is
p = 0.055. 11 of 79 weeks are tied, and 40 of the remaining 68 are losses.

It maps to **NO EFFECT** in the brief's scheme ("somewhat predictable but no ranking gain"). In
practical terms the conclusion is the same: **do not add these features to Alpha, and do not
build an opportunity-forecast model for ranking.**

**A pattern worth recording, not a finding.** W6's quantile arm also moved WR capture@10 down
(−0.0051, every LOSO fold negative), through a completely different intervention. Two unrelated
changes to Alpha's model have both lowered its WR top 10 while raising its whole-board order.
That is consistent with production's WR top 10 already being at a local optimum that
volume-weighted changes push away from. It is a hypothesis, untested here.

---

## 11. The a priori predictions, scored

| # | prediction | outcome |
|---|---|---|
| 1 | `T_XFP` forecast Spearman ≈ 0.70–0.80, above Alpha's 0.58–0.67 for points | **partly right** — above Alpha's points board at every position (+0.04–0.05), but lower than predicted: 0.71 / 0.67 / 0.63 |
| 2 | `Δ_NEW` below +0.02 everywhere; C1 fails | **right** |
| 3 | `Δ_RED` ≈ `Δ_NEW` | **wrong at RB** (0.0009 vs 0.0105, the new info is genuinely new there); roughly right at WR (55%) and TE (65%, indistinguishable) |
| 4 | ridge ≈ CatBoost | **right** (CatBoost significantly worse at TE) |
| 5 | `FORECAST_USAGE` worse than Alpha; `R_F` negative | **partly** — significantly worse at RB capture@5; `R_F` is ≈ 0 (+1.6 / −0.9 / −0.9%), not clearly negative |
| 6 | `ALPHA_PLUS_OPP` null on capture@10 at RB and WR | **wrong at WR** — significantly negative |
| 7 | `R_L1` under 10% | **right** (+2.6 / −6.3 / −1.7%) |
| 8 | TE least forecastable | **right** |
| 9 | Class B adds a small but measurable amount | **wrong** — zero at every position |
| 10 | NO EFFECT | **wrong** — HARM by the stated order (NO EFFECT in the brief's scheme) |

**Four right, three partly right, three wrong.** The most consequential error is #6. The
intervention did not merely fail to help the top of the WR board; it hurt it.

---

## 12. Answers

1. **How predictable is RB opportunity?** Moderately. The per-week rank correlation is 0.71 for
   usage-expected points and 0.78 for targets + carries. Carries are well forecast (0.76). RB
   *targets* are the least predictable opportunity in the study (0.59). Pooled R² is 0.48.
2. **WR?** Less: 0.67 for usage-expected points, 0.74 for targets and target share, R² 0.42.
3. **TE?** Least: 0.63 for usage-expected points, 0.69–0.70 for targets and target share, R² 0.39.
   Snap share is well forecast at every position (0.79–0.81) but is the measure least tied to
   points.
4. **What Alpha already captures:** about **84–86%** of the improvement any pre-Friday forecast
   achieves over a naive 3-game mean. Alpha's own features alone reach 0.70 / 0.66 / 0.61.
5. **What genuinely new pre-Friday information adds:** +0.010 to +0.013 of rank correlation, all
   significant and all below the +0.02 bar. Net of the redundancy control, it is +0.0096 at RB
   (genuinely new), +0.0052 at WR (about half is re-expression), and +0.0044 at TE
   (indistinguishable from re-expression). None of it lands in the top 5.
6. **How much of W5's perfect-opportunity ceiling does realistic forecasting recover?**
   **Essentially none**: +2.6% (RB), −6.3% (WR), −1.7% (TE) of the capture@10 prize, and 2–5% of
   the whole-board prize.
7. **Does forecasted opportunity improve top-of-board ranking?** **No.** RB +0.005 (null), WR
   **−0.013 (significant harm)**, TE −0.003 (null). It improves the middle and whole board by
   +0.004–0.011 Spearman.
8. **Is it large enough to matter?** **No.** The top-of-board effects are null or harmful. The
   whole-board gains are between an eighth and a third of ECR's existing Spearman lead over Alpha
   (+0.031 to +0.038).
9. **Is it worth pursuing?** **Not with Class A data.** This line should stop here: no more
   opportunity features, no opportunity-forecast model, no retry with more lags or another
   learner. W7 shows those choices do not matter. What remains unmeasured is information this
   repository does not have with a provable timestamp (injury and practice reports, news, Vegas
   lines, routes). That is a data-acquisition question, not a modelling one.
10. **The single best next research question:**

    > **Is ECR's top-of-board advantage over Alpha concentrated in the player-weeks whose
    > opportunity departs from its pre-Friday forecast — i.e., is the expert edge news about this
    > week's usage, or judgement about efficiency?**

    Use W7's M_NEW residual (realized minus forecast `T_XFP`) as the instrument. ECR is only a
    diagnostic here, never a feature. Measure whether ECR's capture@10 lead over Alpha (+0.023 RB,
    +0.032 WR, +0.026 TE) lives in the player-weeks with large opportunity surprises.

    - **If it does,** the experts' edge is week-specific news that Alpha cannot see. The only way
      forward is acquiring timestamped injury, news and Vegas data, and that should be decided
      explicitly.
    - **If it does not,** the edge is judgement about efficiency and talent. Opportunity work is
      finished and the next phase should study efficiency.

    It is a measurement, not a model. It reuses instruments that already exist, it has no leakage
    surface, and either answer eliminates one of the two remaining directions.

---

## Appendix — scope and reproducibility

- **Instruments:**
  - `src/alpha_squad/evaluation/weekly/opportunity.py`: the Class A panel, feature sets,
    baselines and walk-forward forecasts.
  - `src/alpha_squad/evaluation/weekly/arms.py`: `train_with_extra_features`, the one-change
    trainer.
  - `scripts/research/w7_opportunity.py`: the runner.
  - `scripts/research/w7_validity_gates.py`: G1–G11.
  - `tests/unit/test_weekly_opportunity.py`: 29 tests.
- **Result file:** `reports/weekly/w7_results.json`.
- **Rerun:** `uv run python scripts/research/w7_opportunity.py` rebuilds the file byte-for-byte
  (G10).
- **Model settings:**
  - ridge `alpha = 1.0` on standardised features, median imputation from the training fold, plus
    missing indicators
  - CatBoost with production's hyperparameters
  - `ALPHA_PLUS_OPP`: production's CatBoost MAE, seed 42, walk-forward `[2015, S−1]`
- **Statistics:** 79 weeks, 2021–2025. Paired bootstrap over weeks (10,000 resamples, seeds 0–9).
  Wilcoxon. Win/loss counts.
- **Nothing tuned, nothing selected after results, no amendment.** Production diff empty.
