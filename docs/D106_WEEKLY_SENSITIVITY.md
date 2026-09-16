# D106 — Does the D105 plateau survive the weekly no-foresight objective?

*(Results in §4 onward; §1–§3 were written before the weekly ladder produced a number.)*

---

## 1. The pre-registered question and decision rule

> **Does the threshold/plateau relationship observed in D105 persist when realized pick value is
> scored with the weekly no-foresight lineup objective?**

    H0  the plateau is OBJECTIVE-SPECIFIC — weekly scoring produces materially more separation
        in realized value as ranking quality degrades.
    H1  the plateau PERSISTS — large changes in ranking and in picks produce little change in
        realized value until ranking quality is substantially degraded.

**The decision rule, fixed before measuring**, using D105's own empirical scale rather than an
invented threshold:

| outcome | criterion |
|---|---|
| **H1 — plateau persists** | at α = 0.50 the weekly value delta stays **below the D97 detection floor (172–250)** *and* **below that level's own seed-to-seed SD**; and the *plateau ratio* stays of the same order as D105's |
| **H0 — plateau resolved** | at α = 0.50 the weekly delta clears **both** the seed SD **and** the detection floor |
| **weakened (intermediate)** | the plateau ratio rises materially but α = 0.50 still sits inside the noise band — detectable in shape, not practically meaningful |

**Plateau ratio** = |Δvalue at α = 0.50| / |Δvalue at α = 1.00|. It is scale-free, which matters
because weekly and season-long totals are not the same units. D105's values:

| format | Δ at α=0.50 | Δ at α=1.00 | **plateau ratio** | seed SD at α=0.50 |
|---|---|---|---|---|
| target_league | −46.5 | −565.8 | **8.2%** | 160 |
| dynasty_1qb | −60.0 | −631.9 | **9.5%** | 127 |

**"Statistically detectable" is not "practically meaningful."** The floor (172–250 points) is the
smallest *draft-level* effect this instrument can resolve at five season clusters; an effect below
it is not actionable regardless of where its interval sits.

## 2. Challenging the premise first

**The brief is right to warn against assuming the weekly objective is better, and the existing
evidence actively predicts H1.** D103 measured that switching from season-long to weekly *reduces*
regret at **every** draft phase (−27.4 target, −38.7 dynasty; late −30.6, −36.8), because a weekly
lineup **adapts** — swapping one player changes the summed weekly total less than it changes a
single season-long allocation. D102's original theory that weekly scoring would expose hidden
late-pick value was refuted by that same measurement.

So the prior from this project's own instruments is that weekly scoring **compresses** differences
between rosters. If that holds, weekly should show **less** separation along the ladder, not more —
which would strengthen rather than resolve the plateau. **A finding of H0 would therefore be
genuinely surprising, and that is what makes the test worth running.**

The north-star is unchanged: pick quality and realized value. The weekly objective is a
*measurement choice* under test here, not a better yardstick by assumption.

## 3. What is held identical to D105, and the one thing that changes

Everything in the D105 ladder is reused **unmodified** — same runner, same functions, same
constants:

- Y1 production decision rule (tier `L0`, pinned to production by D103's
  `TestShippedTierIsProduction`);
- seasons 2021–2025 (`BACKTEST_SEASONS`; **no 2020, no 2026**);
- slots {1, 4, 7, 10}, both shipped 1-QB formats;
- the α ladder **0.00 / 0.25 / 0.50 / 0.75 / 1.00** with D105's exact interpolation
  `key = (1−α)·rank_Y1 + α·rank_random`;
- pre-registered seeds **(0, 1, 2, 3, 4)**, string-seeded, identical at every level;
- the same candidate pools, the same value-multiset preservation, the same information boundary.

**The only intended change is the realized-value objective**, from season-long to
`weekly_lineup_points_no_foresight` — used exactly as D103 established, with no modification to its
implementation.

### Two harness properties that make this a clean isolation

**(a) The weekly lineup is set from UNPERTURBED Y1 projections for every arm.** `_play_draft`
scores with `scoring_static`, and the ladder passes the perturbed board as the *draft* board while
the untouched `static` goes in as the *scorer*. So each arm drafts differently but sets its weekly
lineup the same way. Without this, a scrambled arm would also set worse lineups and the experiment
would confound **draft** quality with **lineup** quality. Pinned by test.

**(b) Pick divergence is objective-independent, so it is NOT re-run.** Picks come from
`_pick_by_tier`, which takes no objective parameter at all — the scoring objective cannot reach a
draft decision. D105's picks-changed table (66.2% / 88.4% / 90.6% / 98.4%) therefore carries over
to D106 **exactly and by construction**, not by re-measurement. Pinned by test.

### One harness hardening, made before the run

`--objective` was an unconstrained string, and `_play_draft` silently falls through to the
season-long branch for any objective it does not recognise — so a typo would have produced a
season-long run reported as a weekly one. The flag now uses `choices=OBJECTIVES` and argparse
refuses. This is the only change D106 makes to any file, and it is in the research layer.

## 4. Results — the weekly ladder

### target_league (L0 = Y1 = 1964.2 weekly points)

| arm | α | value | vs L0 | 95% CI | seasons worse | vs floor | seed SD |
|---|---|---|---|---|---|---|---|
| L0 | 0.00 | 1964.2 | +0.0 | — | 0/5 | — | — |
| L1 | 0.25 | 1920.4 | −43.7 | [−120.9, +33.4] | 3/5 | below | 174.4 |
| **L2** | **0.50** | 1933.5 | **−30.6** | [−147.8, +86.5] | 3/5 | **below** | **151.1** |
| L3 | 0.75 | 1838.7 | −125.5 | [−325.9, +74.8] | 4/5 | below | 197.5 |
| **L4** | **1.00** | 1343.2 | **−621.0** | **[−831.8, −410.1]** | **5/5** | **ABOVE** | 169.6 |
| FP_ECR_Y1 | — | 2012.6 | +48.4 | [−70.7, +167.6] | 2/5 | below | — |
| *ORACLE_Y1* | — | *2731.6* | *+767.5* | *[+606.4, +928.5]* | *0/5* | *ABOVE* | — |

### dynasty_1qb (L0 = Y1 = 2112.1)

| arm | α | value | vs L0 | 95% CI | seasons worse | vs floor | seed SD |
|---|---|---|---|---|---|---|---|
| L1 | 0.25 | 2042.4 | −69.6 | [−233.8, +94.6] | 3/5 | below | 146.7 |
| **L2** | **0.50** | 2027.7 | **−84.3** | [−328.9, +160.2] | 3/5 | **below** | **124.9** |
| L3 | 0.75 | 1859.5 | −252.5 | [−560.7, +55.6] | 4/5 | ABOVE | 190.3 |
| **L4** | **1.00** | 1390.8 | **−721.3** | **[−990.1, −452.5]** | **5/5** | **ABOVE** | 177.4 |
| FP_ECR_Y1 | — | 1909.7 | **−202.4** | [−440.5, +35.8] | **5/5** | in band | — |
| *ORACLE_Y1* | — | *2783.5* | *+671.4* | *[+399.9, +943.0]* | *0/5* | *ABOVE* | — |

## 5. D105 versus D106 — the direct comparison

**The scales are effectively identical**, so raw deltas are comparable: the L0 baseline moves by
**−1.0%** (target, 1983.6 → 1964.2) and **+0.8%** (dynasty, 2094.9 → 2112.1). No units artifact.

| α | **target** D105 season-long | **target** D106 weekly | **dynasty** D105 | **dynasty** D106 |
|---|---|---|---|---|
| 0.25 | −41.1 | −43.7 | −39.5 | −69.6 |
| **0.50** | **−46.5** | **−30.6** | **−60.0** | **−84.3** |
| 0.75 | −115.0 | −125.5 | −217.7 | −252.5 |
| **1.00** | **−565.8** | **−621.0** | **−631.9** | **−721.3** |
| FP_ECR_Y1 | +77.3 | +48.4 | −132.1 | −202.4 |
| ORACLE_Y1 | +795.3 | +767.5 | +717.0 | +671.4 |

**Plateau ratio** = |Δ at α=0.50| / |Δ at α=1.00|:

| format | D105 season-long | D106 weekly | change |
|---|---|---|---|
| target_league | 8.2% | **4.9%** | **−3.3 pp** |
| dynasty_1qb | 9.5% | **11.7%** | +2.2 pp |

### Applying the pre-registered decision rule

| test | target D105 | target D106 | dynasty D105 | dynasty D106 |
|---|---|---|---|---|
| α=0.50 delta below its seed SD? | BELOW (46.5 < 160) | **BELOW (30.6 < 151)** | BELOW (60.0 < 127) | **BELOW (84.3 < 125)** |
| α=0.50 delta clears the 172–250 floor? | no | **no** | no | **no** |

**Both criteria for H0 fail in both formats. The registered answer is H1 — the plateau persists.**

### The nuance, and where my stated prior was wrong

§2 predicted, from D103, that weekly scoring would **compress** the whole ladder. **That prior was
half right and I am recording the half that was wrong.** Weekly compresses the *intermediate*
region in the target format (ratio 8.2% → 4.9%) but **amplifies the endpoint in both formats**:
α=1.00 grows **+9.8%** in magnitude at target (−565.8 → −621.0) and **+14.1%** at dynasty
(−631.9 → −721.3).

So the weekly objective does not flatten the curve — **it makes the threshold sharper.** The
plateau is, if anything, more pronounced under the more faithful objective: flatter for longer,
then a steeper collapse.

### ECR under the weekly objective

**D104's negative result strengthens.** Target's gain shrinks from +77.3 to **+48.4** and becomes
inconsistent (0/5 seasons worse → **2/5**). Dynasty's loss deepens from −132.1 to **−202.4**, now
worse in **5 of 5 seasons** and reaching the floor band. Under the objective that better reflects
what fantasy actually scores, the best available preseason ranking is **not** an improvement in
either format and is mildly harmful in one.

## 6. Where the change is concentrated

**By season.** The pattern is the same under both objectives and is driven by the same seasons:
2023 and 2025 are negative for the intermediate rungs in both formats, while 2021 and 2022 are
often positive. **L4 is negative in every season of both formats under both objectives** — that is
the only row with no sign flips. The intermediate rungs flip sign season to season, which is
exactly what "inside the noise band" looks like and why their intervals span zero.

**By draft phase.** See §6.1 — the matched regret ladder. *(The whole-draft value metric is a
single number per draft and cannot be decomposed by phase; regret can.)*

**By position.** Not separately measurable on this experiment without changing it. The value metric
is whole-roster, and the pick-divergence positional mix is objective-independent (§3b), so D105's
finding stands unchanged: divergence is WR-dominated at every level, with K appearing only at L1.
**No position-specific claim is made, and none is warranted.**

### 6.1 Matched regret ladder

*(Filled in on completion — same reduced scope D105 used, so the two are like-for-like.)*

## 7. Verdict and direction

### Verdict: H1 — the plateau persists, and it is objective-independent

The robustness D105 measured is **not** an artifact of season-long scoring. Under the weekly
no-foresight objective the intermediate ladder stays inside the noise band in both formats, while
the severe end separates *more* strongly than before.

### What this closes, and what it does not

**Closes:** the projection/ranking direction as an explanation for the absence of measurable
improvement. Two different value objectives, one ladder, the same answer. Per the brief's stopping
rule, **the projection/decision-objective sensitivity branch stops here.** Searching for a third
scoring objective because the first two produced nulls is precisely the error to avoid.

**Does NOT close, and must not be misread:** this is **not** evidence that the draft objective is
defective. An objective that is insensitive to small ranking changes is not broken — it is
reporting something true about the problem. The evidence supports a **thresholded decision
environment**: only information improvements large enough to move within-position predictive
Spearman by roughly ±0.5 (D105's measurement) can produce a draft-level effect this instrument can
resolve. ECR moves it by 0.024.

### Does this change the project's decision direction?

**Yes, and toward stopping rather than toward a new search.** Across D97–D106 the project has now
established, with two objectives and three instruments:

- the decision-shaped residual is ~86–113 pts/draft, below the detection floor (D103, replicating D86);
- perfect information is worth ~+670 to +795, but the best *available* preseason ranking recovers
  ≤10% of it and is negative in dynasty (D104, strengthened here);
- the value surface is a plateau in ranking quality, under **both** scoring objectives (D105, D106);
- the decision surface is steep — 88% of picks change for ~30–85 points (D105, objective-independent).

**Y1 is operating in a regime where neither better rankings nor a better decision rule can produce
a measurable gain.** That is a conclusion about the problem, not a failure of the search, and it is
now supported rather than assumed.

## 8. Reproduction

```
uv run python scripts/research/d105_objective_sensitivity.py --mode value \
    --objective weekly_no_foresight --out <dir>      # D106
uv run python scripts/research/d105_objective_sensitivity.py --mode value --out <dir>   # D105
uv run pytest tests/unit/test_d105_objective_sensitivity.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```
