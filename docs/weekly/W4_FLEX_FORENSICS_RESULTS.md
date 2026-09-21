# W4 — Is cross-position calibration the FLEX bottleneck?

**Status: COMPLETE. Verdict D — essentially irrelevant.**

Run exactly as pre-registered in `docs/weekly/W4_PREREGISTRATION.md`, committed before any
counterfactual, oracle or calibration result existed. **No model was built, fitted, tuned or
retrained. No calibration was added to production. No ECR entered Alpha or any calibration fit.
No production file changed.**

Provenance: Alpha `ml_catboost` (`WEEKLY_PROJECTION_BASE_MODEL`) as trained by the unmodified
`alpha-squad train established`; ECR vintage `e270d790…5db9a5` and crosswalk `36016b92…6b19ca4`,
both identical to W1/W2/W3; 79 weeks (2021–2025: 17/16/16/14/16), Full PPR, Friday cutoff,
`MIN_FIT_SAMPLE = 200`. Instruments: `scripts/research/w4_flex_forensics.py`,
`scripts/research/w4_validity_gates.py`. Results: `reports/weekly/w4_results.json`.

---

## 1. Verdict

> **D — essentially irrelevant.** On the pre-registered primary metric (FLEX points-captured@10),
> the gain from a **perfect** cross-position scale is **+0.0075, 95% CI [−0.0055, +0.0205]** —
> indistinguishable from zero, 37 weeks better and 38 worse. The gain from a **perfect
> within-position ordering**, leaving Alpha's cross-position scale exactly as it is, is
> **+0.3613, CI [+0.3426, +0.3796], 79 weeks to 0**. The combination step accounts for **2.1%**
> of what is available; the positional rankings account for the rest.

Pre-registration §7.1 defines D as *"`X` is not distinguishable from zero."* That criterion is
met. C's criterion (`X < 0.25·W`, and every calibration CI includes zero) is also met; D is
reported because it is the stronger and more specific of the two, and both point the same way.

**The single most decisive number is not `X` itself.** Give Alpha a perfect cross-position scale
and it is *still* significantly behind ECR on FLEX capture@10 — **−0.0313, CI [−0.0495, −0.0136]**
— which is 81% of the original −0.0388 deficit, surviving intact. Give Alpha a perfect
within-position ordering and leave the allegedly-broken scale untouched, and it beats ECR by
**+0.3225**. Whatever is wrong with Alpha's FLEX board is inside the positional rankings.

**One honest complication, reported here and not buried.** The verdict rests on the
pre-registered metric, which is *points captured*. On **name overlap** (`precision`) the
cross-position ceiling is real: ORACLE_XPOS improves precision@5 by **+0.0456, CI [+0.0144,
+0.0782]** and precision@10 by **+0.0241, CI [+0.0097, +0.0386]**. So a perfect cross-position
scale *does* put more of the right names in the top 5–10 — those names are simply worth almost
nothing in points. §6.3 works this through. The gloss attached to verdict D in the
pre-registration ("changes nothing measurable") is therefore too strong as written, and is
corrected here rather than quietly restated.

**Practical consequence:** *do not build cross-position calibration.* Four causal methods were
pre-registered, fitted walk-forward and applied; **not one met either success bar**, and three of
four are **significantly worse** than current Alpha on the overall ordering. This is a successful
research outcome in the sense the brief intends — it closes a line of work that would not have
paid, and it redirects W5 at the positional models.

---

## 2. What was measured, and what this is not

| | |
|---|---|
| question | how much of Alpha's top-of-FLEX deficit comes from the **RB/WR/TE combination step**, versus deficiencies already inside the **positional rankings** |
| population | 79 weeks, 2021–2025, Full PPR, Friday cutoff — **identical to W3 in every respect** |
| universe | ECR's FLEX board → intersected with players who played → intersected with Alpha's coverage. Identical for every one of the 14 systems, every week (gate G3) |
| metrics | W2's frozen suite, unchanged, at depths **5 / 10 / 25 / 50** |
| unit of replication | **the week (n = 79)**, never the player-week. A calibration that moves 900 players does not have 900 independent observations |
| statistics | paired within week; 95% bootstrap CI over weeks (10,000 resamples, seeds 0–9); Wilcoxon signed-rank; win–loss counts. MDE = CI half-width |

**This is not** a search for the best calibration, a hyperparameter sweep, a model change, or a
production candidate. Four methods were fixed in advance; all four are reported whatever they
did. The oracle boards use realized outcomes **by design** and are diagnostics only.

---

## 3. Forensic audit of the combination step

Traced through the code before any result existed; reported in full as
`docs/weekly/W4_PREREGISTRATION.md` §2 and summarised here because the results only make sense
against it.

**The combination step is one line.** `evaluation/weekly/alpha.py` sorts the pooled RB/WR/TE
predictions by predicted points. There is **no normalisation, no positional weighting, no
rescaling** anywhere in the FLEX path. Three separately-trained, structurally identical CatBoost
models (same 11 features, same target, same MAE loss, same hyperparameters, same walk-forward
window, same `fillna(0.0)`) emit raw predicted points into one `sorted()`.

**Predictions are compressed, and unequally so** — sd(real)/sd(pred) is RB 0.616, WR 0.588,
TE 0.544. Maximum predicted value ever emitted: RB 22.79, WR 17.82, TE 15.85, against realized
maxima of 55.4 / 55.6 / 45.6. On this board a TE essentially cannot outrank a top RB.

**But the predictions are conditionally well-calibrated.** OLS of realized on predicted gives
slopes of 1.0144 / 1.0129 / 1.0250 for RB / WR / TE, because `slope = corr · sd_r/sd_p` and the
correlation exactly offsets the compression. Conditional and marginal calibration are different
properties and **only the conditional one matters for ranking by expected points** — this is the
hinge of the whole phase.

**Restricted to predicted ≥ 10, where the FLEX top-10 lives**, `E[realized] − predicted` is
RB **+1.47**, WR **+1.26**, TE **+0.83**. At equal predicted value a top TE realizes *fewer*
points than a top RB, so a ranking that demotes them is behaving correctly.

**Within the top group Alpha's ordering is nearly uninformative**: `corr(pred, real)` for
predicted ≥ 10 is RB **0.251**, WR **0.222**, TE **0.141**, against 0.625 / 0.595 / 0.557 over
the full range. That number, not the scale, is what §6 confirms is the bottleneck.

---

## 4. W3 reproduced exactly

Before anything new was interpreted, the W3 control was rebuilt from scratch by this phase's
runner and compared value-by-value against `reports/weekly/w3_results.json`.

**2,607 metric values across 79 weeks × 3 systems (Alpha, ECR, season-to-date baseline), maximum
absolute difference `0`, zero one-sided-missing cells.** Not "to six decimals" — exactly zero.
The instrument is the same instrument.

FLEX means, 79 weeks:

| | Spearman | capture@5 | capture@10 | capture@25 | capture@50 | precision@10 |
|---|---:|---:|---:|---:|---:|---:|
| **ECR** | 0.6792 | 0.5945 | 0.6369 | 0.6889 | 0.7599 | 0.2595 |
| **Alpha (CF_A)** | 0.6479 | 0.5726 | 0.5981 | 0.6616 | 0.7373 | 0.2190 |
| **B0 season-to-date** | 0.6132 | 0.5601 | 0.5954 | 0.6498 | 0.7187 | 0.2215 |
| **B1 prior-season** | 0.4420 | 0.5339 | 0.5738 | 0.6482 | 0.6912 | 0.2063 |

---

## 5. Positional top-of-board forensics

Alpha versus ECR **inside each position**, where no combination step exists at all:

| | Spearman | capture@5 | capture@10 | capture@25 | precision@5 | precision@10 |
|---|---:|---:|---:|---:|---:|---:|
| **RB** Alpha − ECR | **−0.0375*** | −0.0133 | **−0.0228*** | **−0.0251*** | −0.0203 | **−0.0405*** |
| **WR** Alpha − ECR | **−0.0305*** | **−0.0567*** | **−0.0320*** | **−0.0273*** | **−0.0608*** | **−0.0367*** |
| **TE** Alpha − ECR | **−0.0343*** | **−0.0365*** | **−0.0258*** | **−0.0148*** | −0.0278 | **−0.0278*** |
| **FLEX** Alpha − ECR | **−0.0313*** | **−0.0219*** | **−0.0388*** | **−0.0273*** | **−0.0380*** | **−0.0405*** |

`*` = 95% CI excludes zero. **Alpha loses to ECR in every position, at every depth, on almost
every metric — and the FLEX deficit is the same size as the deficits Alpha already carries inside
the positions.** A combination step cannot be blamed for a deficit that is fully present before
combination happens.

**Where Alpha is worst: WR at the very top.** precision@5 of **0.2000** against ECR's 0.2608, and
— the only place in the whole phase where Alpha loses to the *trivial* baseline — **−0.0304
versus season-to-date PPG, CI [−0.0603, −0.0003], 9 weeks better and 20 worse.** Alpha's WR top-5
is worse than "rank them by their average so far". That is a positional-model finding and it is
where W5 should start.

Against the trivial baseline, Alpha's within-position ordering advantage is real and large
everywhere (Spearman RB +0.0269, WR +0.0351, TE +0.0509, all CIs excluding zero) — it is the
**top** of each positional board that is empty, exactly as W3 found for FLEX.

---

## 6. Counterfactuals and oracles

All evaluated on the identical universe, week, scoring and cutoff. **None is a production
candidate.** `ORACLE_BOTH` is a sanity check and scores pairwise accuracy **1.0000** exactly, as
it must.

### 6.1 The two that decide the phase

| | FLEX capture@10 | vs CF_A | 95% CI | weeks W–L |
|---|---:|---:|---|---:|
| **CF_A** (current Alpha) | 0.5981 | — | — | — |
| **ORACLE_XPOS** — Alpha's within-position order, **perfect** cross-position scale | 0.6057 | **+0.0075** | [−0.0055, +0.0205] | 37–38 |
| **ORACLE_WITHIN** — **perfect** within-position order, Alpha's cross-position scale | 0.9594 | **+0.3613** | [+0.3426, +0.3796] | **79–0** |
| **ORACLE_BOTH** | 1.0000 | +0.4019 | [+0.3829, +0.4207] | 79–0 |
| **ECR** | 0.6369 | +0.0388 | [+0.0226, +0.0550] | 58–21 |

`X / W` across the frozen metrics — the share of the available headroom that lives in the
combination step:

| metric | `X` (cross) | `W` (within) | `X/W` |
|---|---:|---:|---:|
| Spearman | +0.0004 | +0.3360 | **0.1%** |
| Kendall τ-b | +0.0009 | +0.4415 | 0.2% |
| pairwise accuracy | +0.0005 | +0.2243 | 0.2% |
| decisive-pair accuracy | +0.0002 | +0.1987 | 0.1% |
| capture@5 | +0.0044 | +0.3575 | 1.2% |
| **capture@10 (primary)** | **+0.0075** | **+0.3613** | **2.1%** |
| capture@25 | +0.0039 | +0.3139 | 1.3% |
| capture@50 | **−0.0035** | +0.2473 | −1.4% |

**At depth 50 a perfect cross-position scale makes the board *worse*.** Not significantly, but
the sign is consistent with everything else here.

### 6.2 The ceiling, priced against the benchmark

`X` being small could still matter if Alpha were otherwise near ECR. It is not:

| | vs ECR, FLEX capture@10 | 95% CI |
|---|---:|---|
| CF_A | −0.0388 | [−0.0550, −0.0226] |
| **ORACLE_XPOS** (perfect cross-position scale) | **−0.0313** | [−0.0495, −0.0136] |
| **ORACLE_WITHIN** (perfect positional order) | **+0.3225** | [+0.3040, +0.3410] |

Spending a *perfect* fix on the combination step closes at most 19% of the gap to ECR in point
estimate, and the residual remains statistically significant. Spending it on the positional
rankings overshoots the benchmark by an order of magnitude.

### 6.3 The precision exception, stated plainly

On top-k **membership**, the cross-position ceiling is real:

| | precision@5 | precision@10 | precision@25 | precision@50 |
|---|---:|---:|---:|---:|
| ORACLE_XPOS − CF_A | **+0.0456*** | **+0.0241*** | **+0.0106*** | −0.0051 |
| as a share of the Alpha−ECR gap | 120% | 59% | 25% | — |

So a perfect cross-position scale puts materially more of the *right names* in the top 5 and
top 10 — and buys **no** additional points (capture@5 +0.0044, capture@10 +0.0075, both CIs
containing zero). The two metrics disagree because the names it swaps in are marginal: the scale
fix moves the board's positional composition toward the realized one (§9), and the extra TEs and
WRs it promotes are ones that finished *just* inside the true top-10, displacing RBs that
finished just outside. Name overlap improves; points do not.

The pre-registration named **capture@10** the primary metric precisely because it prices a miss by
what the miss cost. The verdict follows that rule. But "cross-position scale is irrelevant" is the
wrong summary of the precision column, and is not the claim made here: the correct claim is that
**cross-position scale changes which names appear at the top without changing what the top is
worth.**

### 6.4 Single-position scale swaps

Every `CF_SWAP_*` — giving exactly one position the oracle scale and leaving the others as Alpha's
— is **significantly worse** than current Alpha on the overall ordering (Spearman: RB −0.0032,
WR −0.0057, TE −0.0043; all CIs exclude zero) and on capture@10 (−0.0311, −0.0350, −0.0449).

This is informative rather than surprising: a board scored on a mixture of two incompatible
scales is worse than one scored consistently on either. It is also a direct warning about partial
fixes — "recalibrate TE only" is measurably harmful.

---

## 7. The exact additive decomposition

Total pairwise ordering accuracy on a FLEX board is **exactly** a weighted average over
position-pair buckets. No modelling assumption; the weights are pair counts.

**Pair mix over 79 weeks: 917,415 within-position pairs (36.0%), 1,630,665 cross-position
pairs (64.0%).**

| system | within | **cross** | RB-RB | WR-WR | TE-TE | RB-WR | RB-TE | WR-TE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **CF_A** | 0.7365 | **0.7385** | 0.7462 | 0.7378 | 0.7159 | 0.7410 | 0.7409 | 0.7338 |
| ECR | 0.7514 | 0.7515 | 0.7643 | 0.7514 | 0.7307 | 0.7555 | 0.7541 | 0.7448 |
| ORACLE_XPOS | 0.7365 | **0.7392** | 0.7462 | 0.7378 | 0.7159 | 0.7419 | 0.7409 | 0.7347 |
| ORACLE_WITHIN | 1.0000 | **0.9411** | 1.0000 | 1.0000 | 1.0000 | 0.9529 | 0.9271 | 0.9349 |
| CAL_MEANVAR | 0.7365 | 0.7377 | — | — | — | 0.7405 | 0.7394 | 0.7330 |
| CAL_AFFINE | 0.7365 | 0.7379 | — | — | — | 0.7404 | 0.7398 | 0.7335 |
| CAL_QUANTILE | 0.7365 | 0.7377 | — | — | — | 0.7406 | 0.7399 | 0.7325 |
| CAL_RANKPCT | 0.7365 | 0.7364 | — | — | — | 0.7392 | 0.7381 | 0.7318 |

Three things fall out of this table and each is load-bearing.

**(a) Alpha already orders cross-position pairs slightly *better* than within-position pairs**
(0.7385 vs 0.7365). There is no cross-position penalty to recover. The premise the phase was sent
to test is not merely small — it has the wrong sign.

**(b) A perfect cross-position scale moves cross-pair accuracy from 0.7385 to 0.7392** — seven
ten-thousandths, against a within-position headroom of 0.7365 → 1.0000. The oracle's within-pair
accuracy is **identical to CF_A's to six decimals**, as it must be by construction; that identity
is asserted by test (`TestOracleInvariants`) and is what caught a defect in the oracle itself
(§16).

**(c) Fixing the positional models fixes the cross-position pairs too** — ORACLE_WITHIN lifts
cross-pair accuracy to **0.9411** without touching the scale at all. Cross-position ordering is
mostly downstream of within-position ordering: if you know who the best RBs are, you place them
correctly against WRs almost for free. This is why the oracle decomposition is **not additive**
and is labelled as such everywhere it appears.

**Per-bucket attribution (robustness check 2):** no single cross-position bucket carries an
effect. The three cross buckets move by +0.0009 (RB-WR), +0.0000 (RB-TE) and +0.0009 (WR-TE)
under the oracle scale.

---

## 8. Cross-position directional bias

Symmetric accuracy cannot distinguish "wrong in both directions" from "systematically over-rates
a position", and only the second is something a transform could fix. Net bias, positive = the
first position is systematically ranked above the second when it should not be:

| system | RB-WR | RB-TE | WR-TE |
|---|---:|---:|---:|
| **CF_A** | +0.0008 | **+0.0454** | **+0.0532** |
| **ECR** | −0.0034 | **+0.0621** | **+0.0674** |
| B0 season-to-date | −0.0127 | +0.0223 | +0.0435 |
| CAL_MEANVAR | −0.0021 | −0.0042 | +0.0034 |
| CAL_QUANTILE | +0.0028 | −0.0003 | −0.0002 |
| CAL_RANKPCT | −0.0041 | +0.0009 | +0.0068 |
| ORACLE_XPOS | −0.0005 | −0.0021 | −0.0010 |

**Alpha has a genuine, measurable anti-TE bias, and it is not a defect.** Three findings, in
order:

1. The bias is **real** — Alpha over-ranks RBs against TEs on 15.23% of decidable pairs and
   under-ranks them on 10.69%.
2. The bias is **removable** — `CAL_QUANTILE` drives it to −0.0003 / −0.0002, and the oracle
   scale drives it to −0.0021 / −0.0010. These transforms do exactly what they were designed to
   do.
3. Removing it **does not help** (§10), and **the better system has more of it**: ECR's anti-TE
   bias is *stronger* than Alpha's (+0.0621 / +0.0674 against +0.0454 / +0.0532), while ECR beats
   Alpha on every metric at every depth.

A directional bias that the superior system exhibits more strongly is not an error to correct. It
reflects the fact established in §3: at equal predicted value, top TEs realize fewer points.
Ranking by expected points *should* demote them.

---

## 9. Composition — and why composition is not ranking quality

FLEX top-10 positional shares, means over 79 weeks (pool shares: RB 0.295, WR 0.469, TE 0.236):

| system | RB pred | RB real | **RB over** | WR pred | **WR over** | TE pred | TE real | **TE over** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **CF_A** | 0.534 | 0.381 | **+0.153** | 0.452 | −0.059 | 0.014 | 0.108 | **−0.094** |
| ECR | 0.458 | 0.381 | +0.077 | 0.496 | −0.015 | 0.046 | 0.108 | −0.062 |
| CAL_MEANVAR | 0.459 | 0.381 | +0.078 | 0.452 | −0.059 | 0.089 | 0.108 | −0.019 |
| CAL_AFFINE | 0.529 | 0.381 | +0.148 | 0.452 | −0.059 | 0.019 | 0.108 | −0.089 |
| **CAL_QUANTILE** | 0.399 | 0.381 | **+0.018** | 0.499 | −0.013 | 0.103 | 0.108 | **−0.005** |
| **CAL_RANKPCT** | 0.387 | 0.381 | **+0.006** | 0.515 | +0.004 | 0.097 | 0.108 | **−0.010** |
| ORACLE_XPOS | 0.381 | 0.381 | +0.000 | 0.511 | +0.000 | 0.108 | 0.108 | +0.000 |
| **ORACLE_WITHIN** | 0.534 | 0.381 | **+0.153** | 0.452 | −0.059 | 0.014 | 0.108 | **−0.094** |

The last two rows are the entire argument:

* **`CAL_QUANTILE` and `CAL_RANKPCT` match the realized composition almost exactly** — RB
  over-representation from +0.153 down to +0.018 and +0.006, TE under-representation from −0.094
  to −0.005 and −0.010 — and their capture@10 effects are **+0.0019** and **−0.0015**, both null,
  while both significantly degrade capture@50 and precision@50.
* **`ORACLE_WITHIN` has exactly CF_A's composition** — identical +0.153 / −0.094, because it keeps
  Alpha's scale by construction — and gains **+0.3613** on capture@10.

Matching composition perfectly buys nothing; fixing ordering while leaving composition maximally
"wrong" buys everything. **W3's composition table was a correct description and an incorrect
diagnosis**, and this is the direct experimental demonstration.

---

## 10. Causal calibration — four methods, all pre-registered, all reported

Every method is per-position, monotone non-decreasing within position (so its effect is *purely*
cross-position — proved, not assumed: gate G4), and fitted **only** on completed player-weeks with
`(season < S) OR (season = S AND week < w)`. Current-week outcomes are never seen. **ECR was never
a calibration target** — every fit is against realized fantasy points.

FLEX, versus CF_A, 79 weeks:

| method | Spearman | capture@5 | **capture@10** | capture@25 | capture@50 | precision@50 |
|---|---:|---:|---:|---:|---:|---:|
| **CAL_AFFINE** | **−0.0008*** | −0.0036 | −0.0043 | −0.0020 | −0.0001 | +0.0005 |
| **CAL_MEANVAR** | **−0.0011*** | −0.0132 | −0.0048 | **−0.0066*** | −0.0036 | **−0.0056*** |
| **CAL_QUANTILE** | **−0.0011*** | −0.0177 | +0.0019 | −0.0032 | **−0.0064*** | **−0.0086*** |
| **CAL_RANKPCT** | **−0.0033*** | −0.0147 | −0.0015 | −0.0029 | **−0.0071*** | **−0.0094*** |

`*` = 95% CI excludes zero.

**Pre-registered success bars (§7.2), both required:** CI excluding zero **and** an effect ≥ 25%
of the W3 Alpha-vs-ECR gap — **+0.0097** on capture@10, **+0.0078** on Spearman.

**No method met either bar on either metric.** The best capture@10 effect of the four is
`CAL_QUANTILE`'s **+0.0019**, a fifth of the practical bar, with a CI spanning zero. Classified
under §7.2: all four **NULL** on the primary metric, and all four **NEGATIVE** on the overall
ordering — every one degrades Spearman with a CI excluding zero, and the two marginal-matching
methods additionally degrade capture@50 and precision@50 significantly.

*One of those four significance calls is borderline and is flagged rather than rounded:*
`CAL_QUANTILE`'s Spearman CI is [−0.002215, **−0.000007**]. It excludes zero by seven millionths.
Nothing in the verdict rests on it — its point estimate is 14% of the practical bar and in the
wrong direction either way — but "significantly negative" is doing very little work in that one
cell.

**A dose–response in the wrong direction.** Ordering the methods by how aggressively they rescale:

    CAL_AFFINE (−0.0008)  <  CAL_MEANVAR (−0.0011)  ≈  CAL_QUANTILE (−0.0011)  <  CAL_RANKPCT (−0.0033)

The more of the prediction's magnitude a method throws away, the worse the ranking gets.
`CAL_RANKPCT`, which discards magnitudes entirely and keeps only within-position rank, is the
worst of the four — and it is also, by §9, the one that matches realized composition best.

This reproduces the draft program's result recorded in `CLAUDE.md`: un-shrinking a
conditionally-calibrated prediction adds variance without adding information. §3 explains why —
the positional OLS slopes are 1.0144 / 1.0129 / 1.0250, so there is no conditional miscalibration
to correct, and the marginal-matching methods are inflating an estimate that was already right on
average.

**`CAL_AFFINE` is a near no-op**, as predicted: the three positional fits differ by at most 0.012
in slope and 0.153 in intercept, so the transform is nearly the same map for all three positions,
and applying the same monotone map to all three leaves a pooled sort unchanged.

---

## 11. Rank preservation versus cross-position scaling — kept separate, and proved separate

The brief requires these two be distinguished rather than confounded. Three mechanisms enforce it:

1. **Construction.** Every calibration is monotone non-decreasing within a position, so it
   *cannot* reorder players inside a position. Its entire effect is the difference between the
   three positional maps.
2. **Proof, not assertion.** Gate G4 re-derives each position's ordering from every calibrated
   board and compares it to Alpha's, week by week: **0 within-position reorderings across 948
   (week × method × position) cells.**
3. **The oracles hold one side fixed by construction**, and the identities that must follow are
   asserted by test: `ORACLE_XPOS`'s within-position pair accuracy equals CF_A's exactly
   (0.7365), and `ORACLE_WITHIN`'s equals 1.0000.

G4 **failed on the first run** — 458 of 948 cells. That failure was real and is what produced the
tie defect in §16. It is not a formality.

---

## 12. Is the FLEX problem even real?

The brief asks this directly, and the answer changes what W5 should do. A difference of
differences, paired within week: the FLEX deficit against ECR, minus the mean positional deficit
against ECR. Negative = the combination step adds a problem of its own; zero = FLEX merely
inherits the positional deficit.

| metric | FLEX deficit − mean positional deficit | 95% CI |
|---|---:|---|
| Spearman | **+0.0028** | [+0.0001, +0.0054] |
| Kendall τ-b | **+0.0032** | [+0.0009, +0.0054] |
| pairwise accuracy | **+0.0016** | [+0.0004, +0.0027] |
| capture@5 | +0.0136 | [−0.0091, +0.0369] |
| **capture@10** | −0.0119 | [−0.0279, +0.0044] |
| capture@25 | −0.0049 | [−0.0175, +0.0076] |
| capture@50 | **−0.0139** | [−0.0213, −0.0068] |
| precision@5 | −0.0017 | [−0.0349, +0.0297] |
| precision@10 | −0.0055 | [−0.0273, +0.0168] |
| precision@25 | **−0.0214** | [−0.0394, −0.0036] |
| precision@50 | **−0.0125** | [−0.0220, −0.0035] |

**At the top of the board — the depths this phase exists to explain — the FLEX deficit is
statistically indistinguishable from the deficit Alpha already carries inside the positions.** On
the overall ordering metrics FLEX is very slightly *better* than its positions. There is a small,
significant excess deficit **deep** in the board (capture@50, precision@25/@50) — and §6.1 shows
the cross-position oracle makes depth 50 *worse*, so that excess is not a scale problem either.

**W3's "pooling destroys 84% of Alpha's positional top-10 signal" does not survive as a causal
claim.** It was arithmetic on point estimates whose individual CIs all contained zero, and the
oracle that removes every pooling effect recovers 2.1% of the headroom rather than 84%. The
finding is superseded here.

*Methodological note: this analysis answers a question the brief posed before any result existed,
but it is not one of the three numbered robustness checks in pre-registration §9. It is reported
as a separate, clearly-labelled analysis and does **not** feed the §7.1 verdict, which is decided
by `X` and `W` on FLEX capture@10 alone.*

---

## 13. A priori predictions, scored

Recorded in `docs/weekly/W4_PREREGISTRATION.md` §3 **before** any counterfactual ran, explicitly
so they could be wrong in public. Five of six held; one was wrong.

| # | prediction | outcome |
|---|---|---|
| 1 | The TE under-representation is **mostly not a calibration error** — at equal predicted value top TEs realize fewer points, so demoting them is correct | **Supported, with a correction.** The diagnosis holds: removing the anti-TE bias entirely (§8) buys nothing, and ECR — which beats Alpha everywhere — has a *stronger* anti-TE bias. But the under-representation **is** mechanically removable by calibration, which the prediction's wording understated |
| 2 | Calibration will move the board in the **opposite** direction from the composition table — pushing **RB up**, not TE up | **WRONG.** Calibration moved RB **down** (top-10 share 0.534 → 0.399 for `CAL_QUANTILE`, → 0.387 for `CAL_RANKPCT`) and TE **up** (0.014 → 0.103 / 0.097). The prediction conflated the *conditional* relationship (§3) with what marginal-matching transforms actually target, which is the marginal distribution. Reported here rather than quietly dropped |
| 3 | `CAL_AFFINE` will be close to a no-op | **Correct.** capture@10 −0.0043 (null); Spearman −0.0008, 0.08% of the Alpha-vs-ECR gap; top-10 RB share 0.534 → 0.529 |
| 4 | `CAL_QUANTILE` / `CAL_RANKPCT` will be neutral-to-harmful | **Correct.** Both null on capture@10, both significantly negative on Spearman, capture@50 and precision@50 |
| 5 | The dominant term will be within-position ordering | **Correct, and by a wider margin than expected.** `W / X` = 48× on capture@10 |
| 6 | Expected verdict **C or D** | **Correct** — D |

Prediction 2 being wrong does not change the verdict; if anything it strengthens it. The
calibrations moved composition to almost exactly where the composition table said it should go,
and ranking quality did not improve.

---

## 14. Statistical treatment and power

**The unit of replication is the week, n = 79**, for every comparison in this document. A
calibration that alters 900 players' scores in a week produces one observation, not 900. Paired
within week throughout; 95% bootstrap CI over weeks with 10,000 resamples averaged over seeds
0–9; Wilcoxon signed-rank and win–loss counts reported alongside so a significant mean driven by
a handful of weeks is visible.

**MDE on the primary metric is 0.0130** (half-width of the `X` CI on FLEX capture@10). `X` itself
is +0.0075 — **0.58× MDE**. So the honest statement is not "cross-position calibration does
nothing" but "**any cross-position effect is smaller than 79 weeks of paired data can resolve, and
smaller than 0.0130 in absolute terms**", against a `W` of +0.3613 that the same data resolves at
28× MDE with a 79–0 week split.

**Self-calibrated MDE is a trap and the pre-registration anticipated it.** Two systems that differ
in 3% of their rows have a tiny paired variance, which makes a trivial effect "significant" —
which is exactly why §7.2 required a *practical* bar (25% of the W3 gap) as well as a statistical
one. `CAL_AFFINE`'s Spearman effect illustrates it: −0.0008 with a CI excluding zero, and 0.08% of
the gap it would need to close. Significant and meaningless simultaneously.

---

## 15. Robustness

**1. Leave-one-season-out** on the headline calibration effect (20 recomputations):

| method | Spearman, dropping each of 2021 / 2022 / 2023 / 2024 / 2025 |
|---|---|
| CAL_MEANVAR | −0.0008, −0.0013*, −0.0015*, −0.0011, −0.0011 |
| CAL_AFFINE | −0.0005*, −0.0007*, −0.0009*, −0.0009*, −0.0010* |
| CAL_QUANTILE | −0.0007, −0.0011, −0.0014*, −0.0013*, −0.0010 |
| CAL_RANKPCT | −0.0032*, −0.0030*, −0.0036*, −0.0034*, −0.0034* |

**Every one of the 20 Spearman folds is negative.** On capture@10, `CAL_QUANTILE` and
`CAL_RANKPCT` flip sign in a few folds (largest +0.0073, dropping 2024) but no fold is
significantly positive and none reaches the +0.0097 practical bar. No season is carrying the
result.

**2. Per-position-pair attribution** — §7: no single cross-position bucket carries an effect; the
oracle scale moves all three by ≤ +0.0009.

**3. Per-depth consistency** — §6.1: `X` is small and positive at depths 5/10/25 and **negative**
at depth 50 on both capture and precision. The conclusion does not depend on the depth chosen,
and the one depth where it is largest (precision@5) is discussed on its own terms in §6.3.

No further slicing was performed, as pre-registered.

---

## 16. Validity gates — including one that failed

`scripts/research/w4_validity_gates.py` is a committed instrument (D92: a finding whose runner was
never committed is not a finding), exiting non-zero if any gate fails. Final state:

| gate | check | result |
|---|---|---|
| **G1** causality | fit rows at or after the evaluated week, running the predicate the fitter actually emits against the real table | **0** |
| **G2** already-played | evaluated players whose team had kicked off at the Friday cutoff, re-derived from the schedule and the player's real week-*w* team | **0** |
| **G3** universe | (week × system) cells with a different player set from CF_A's | **0** |
| **G4** monotonicity | within-position reorderings across 948 (week × method × position) cells | **0** |
| **G5** no-ECR | weeks where Alpha's ordering is not reproducible from its predictions alone | **0** |
| **G6** determinism | benchmark run twice, SHA-256 of the output JSON | **identical** |

### 16.1 G4 failed first, and fixing it changed a reported number

The first execution failed G4 with **458 violations of 948**. Per the pre-registration's own rule
— *"If any gate fails, stop and fix the methodology before reading results"* — results were not
read until it was diagnosed.

**Root cause.** `CAL_QUANTILE` and `CAL_RANKPCT` are step functions on an empirical distribution,
so they map *distinct* predictions onto *equal* calibrated values — **362 and 355 manufactured
same-position ties per week** respectively, against **0** for `CAL_MEANVAR` and `CAL_AFFINE`,
which are strictly increasing (counted by the gate script, which prints the figure on every run). The dense re-rank then fell back to `player_id`,
reshuffling players the transform was meant to leave alone — turning a pure cross-position effect
into a mixture of that and arbitrary within-position noise. `CAL_MEANVAR` and `CAL_AFFINE` are
strictly increasing and never violated.

**Fix.** `alpha_board` gained an optional `tiebreak` argument (default `None`, which reproduces W3
byte-for-byte) so manufactured ties resolve in favour of Alpha's own order, with `player_id` as
the deterministic backstop. G4 now reports 0/948.

**This fix strictly helped the calibration methods**, which is the direction that cannot be
accused of engineering the null. The defective construction is still runnable —
`w4_flex_forensics.py --legacy-ties`, which fails G4 by construction and exists precisely so
this comparison is reproducible rather than quoted from a run nobody can repeat:

| FLEX, vs CF_A | defective tie handling | corrected |
|---|---|---|
| `CAL_QUANTILE` Spearman | −0.0052 [−0.0067, −0.0038] | **−0.0011** [−0.0022, −0.0000] |
| `CAL_RANKPCT` Spearman | −0.0085 [−0.0105, −0.0066] | **−0.0033** [−0.0049, −0.0017] |
| `CAL_MEANVAR` / `CAL_AFFINE` | unchanged | unchanged (strictly increasing) |

They still fail both bars.

### 16.2 A defect in the oracle itself, caught by an invariant

Separately, `ORACLE_XPOS`'s within-bucket pair accuracy came back as 0.7335 when it must equal
CF_A's 0.7368 exactly by construction. **42.5% of realized player-week values tie inside a
position-week** over the evaluated universe (8,657 of 20,364 across RB/WR/TE 2021–2025; 3,393 of
them exactly 0.0), so the oracle's equal scores fell back to `player_id` and scrambled the very ordering the oracle exists
to hold fixed.

This mattered to a reportable conclusion. Before the fix, `ORACLE_XPOS` scored Spearman
**−0.0047, CI [−0.0069, −0.0025]** — which would have been reported as *"perfect cross-position
calibration makes the ordering significantly worse"*. After it, **+0.0004, CI [−0.0013, +0.0023]**
— indistinguishable from zero. The verdict is unchanged; the claim underneath it is not.

The invariant itself, which is what surfaced it, also reproduces under `--legacy-ties`:

| within-position pair accuracy | defective | corrected | must be |
|---|---:|---:|---|
| CF_A | 0.736539 | 0.736539 | — |
| `ORACLE_XPOS` | **0.733306** | **0.736539** | identical to CF_A's |
| `ORACLE_WITHIN` | 0.999999 | **1.000000** | exactly 1 |

`TestOracleInvariants` now asserts both identities on real-shaped data, and
`TestLegacyTieDiagnostic` pins that the diagnostic flag genuinely reproduces the defect and is
never the default.

---

## 17. What we know versus what we do not yet know

### Known, with the evidence

* **The combination step is not the bottleneck.** `X/W` = 2.1% on capture@10; `X`'s CI contains
  zero; a perfect cross-position scale leaves Alpha significantly behind ECR (§6.1, §6.2).
* **Alpha already orders cross-position pairs better than within-position pairs** (0.7385 vs
  0.7365) — the premise has the wrong sign (§7).
* **No causal cross-position calibration helps.** Four pre-registered methods; zero met either
  bar; three of four significantly harm the overall ordering; the harm increases with
  aggressiveness (§10).
* **Composition-matching is not ranking quality.** Methods that match realized composition almost
  exactly gain nothing; an oracle with maximally "wrong" composition gains +0.3613 (§9).
* **Alpha's anti-TE bias is real, removable, and not an error** — the superior benchmark has more
  of it (§8).
* **Alpha's deficit is inside the positional models and concentrated at the top of each board.**
  It loses to ECR in all three positions at every depth, and its WR top-5 loses to the trivial
  baseline (§5).
* **The methodology is clean**: W3 reproduced exactly (max abs diff 0 over 2,607 values), six
  validity gates pass, two runs byte-identical (§4, §16).

### Not known, and honestly out of reach here

* **Why `corr(pred, real)` collapses to 0.14–0.25 at the top of each position.** W4 measured that
  it does; it did not diagnose it. Candidate causes — missing opponent/matchup/usage-change
  information, MAE loss flattening the tail, the 11-feature set being mostly lagged
  volume — were **not** tested, because testing them means changing the model, which W4 may not do.
* **Whether a *non-monotone* or *conditional* cross-position adjustment could do better.** Every
  method here was deliberately monotone-within-position so its effect would be identifiable. A
  transform conditioned on something other than the prediction itself is a different object and
  is untested.
* **Whether any of this transfers to Half-PPR.** Everything here is Full PPR, as W2/W3 were.
* **Whether it holds for a board Alpha could actually produce on a Friday.** Alpha's universe is
  still defined by who played (W3 §2.1). This is a *shared* limitation of every system compared
  here — the universe is identical for all 14 — but it bounds what the numbers mean for a live
  product.
* **K and DST remain outside the model entirely** (D57), and were not retrofitted.
* **The live injury-cutoff leak in the served evidence layer** (W3 §3b) is untouched and still
  open.

---

## 18. Implications for W5

**Do not build cross-position calibration.** That is the phase's product. It would have been a
plausible next sprint; four methods and two oracles say it is worth at most 2.1% of the available
headroom and is measurably harmful in three of four implementations.

**Do not "fix" the composition table either** — §9 shows composition-matching is orthogonal to
ranking quality, and §8 shows the anti-TE bias is shared, more strongly, by the better system.

**The target is within-position ordering at the top of each board**, where `corr(pred, real)`
falls to 0.14–0.25 and where Alpha's WR top-5 loses to season-to-date PPG. That is where all 97.9%
of the measured headroom sits. The two engineering prerequisites carried forward from W3 — the
injury-cutoff leak and the Friday-board eligibility architecture — remain open and remain out of
research scope.

**One narrow, honest caveat to carry forward:** §6.3's precision result means a cross-position
scale fix *would* change which names appear in a top-10. If a future product decision ever values
name overlap independently of points captured, that finding is on the record. The current product
goal is expected points, so it does not change what W5 should do.

---

## 19. Scope, provenance and reproducibility

**Production diff: EMPTY.** Everything added by W4 lives under `src/alpha_squad/evaluation/weekly/`
(research-only, per `evaluation/weekly/__init__.py`'s contract), `scripts/research/`, `tests/unit/`
and `docs/`. No model, no `league/`, no `api/`, no feature, no CLI behaviour changed. The one edit
to a file W3 shipped — `alpha_board`'s optional `tiebreak` argument — defaults to `None` and
reproduces W3 byte-for-byte, which §4 verifies numerically rather than asserting.

**Reproduce:**

```
uv run python scripts/research/w4_flex_forensics.py --out reports/weekly/w4_results.json
uv run python scripts/research/w4_validity_gates.py          # exits non-zero if any gate fails

# the §16 corrected-vs-defective comparison (DIAGNOSTIC ONLY; fails gate G4 by construction)
uv run python scripts/research/w4_flex_forensics.py --legacy-ties --out /tmp/w4_legacy.json
```

**Provenance:** Alpha `ml_catboost`; ECR snapshot `e270d790165a6c304e5854145332fe9da3caacab3a61e1efea280b57cc5db9a5`;
crosswalk `36016b9239e3e7dab9a21d9a855692e374d3b7b98ba000af06a8555886b19ca4`; both identical to
W1/W2/W3. 79 weeks; `MIN_FIT_SAMPLE = 200`; bootstrap seeds 0–9.

**Repository:** 1,521 → **1,567 tests pass**, 44 deselected (W4 adds 46: 38 in
`tests/unit/test_weekly_calibration.py`, 8 in `tests/unit/test_w4_flex_forensics.py`). `make lint`
clean, **both** halves (`ruff check` and `ruff format --check`). Two independent benchmark runs
byte-identical.

New research-only modules: `evaluation/weekly/calibration.py`, `evaluation/weekly/counterfactual.py`,
`evaluation/weekly/crosspos.py`. Runners: `scripts/research/w4_flex_forensics.py`,
`scripts/research/w4_validity_gates.py`.

Decision record: `docs/DECISIONS.md` **D112**.
