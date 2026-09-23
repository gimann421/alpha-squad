# W6 — Did training for higher-end outcomes fix the top of the rankings?

**Status: COMPLETE. Verdict — NO EFFECT.**

Run exactly as pre-registered in `docs/weekly/W6_PREREGISTRATION.md` (commit `87ad0a1`, written
before any comparative result existed). **Research only. Production diff EMPTY. No feature added,
no hyperparameter tuned, no ECR used, one argument changed.**

---

## 1. One-sentence answer

**No.** Training the model on the 70th percentile of the outcome instead of its median left the
top of the RB and WR boards statistically unchanged — and the reason is mechanical rather than
subtle: the change moves *how many points Alpha predicts* a great deal and *the order it ranks
players in* almost not at all.

---

## 2. What changed

Exactly one argument. Everything else is production's, and that is verified rather than asserted.

| | |
|---|---|
| **changed** | the CatBoost `loss_function` |
| **unchanged** | the same 11 features, the same target column, `iterations=200`, `depth=4`, `learning_rate=0.05`, `random_seed=42`, the per-position split, the walk-forward window `[2015, S−1]`, `fillna(0.0)`, the prediction frame, the evaluation universe, the cutoff, the metric suite |

| arm | loss | targets | role |
|---|---|---|---|
| **A_MAE** | `MAE` | the conditional **median** | the control — **reproduces production byte-for-byte** |
| **B0_RMSE** | `RMSE` | the conditional **mean** | discriminating control, not a candidate |
| **B1_Q60** | `Quantile:alpha=0.6` | 60th percentile | dose-response |
| **B2_Q70** | `Quantile:alpha=0.7` | 70th percentile | **PRIMARY** |
| **B3_Q80** | `Quantile:alpha=0.8` | 80th percentile | dose-response |

**The control reproduces production exactly**: all **29,376** stored weekly predictions, **100.0%
exact matches**, maximum absolute difference **0.0**, zero unmatched keys. Every number below is
therefore a difference between production and production-with-one-argument-changed.

**The target change did what it was supposed to do at the level of predicted points.** RB's mean
prediction rises 6.86 → 8.36 → 10.18 → 12.63 across MAE / Q60 / Q70 / Q80, and its spread rises
4.98 → 5.58 → 6.16 → 6.77. The arms are genuinely different models.

---

## 3. What happened

### Primary result — `B2_Q70` versus the control, paired over 79 weeks

| | effect | 95% CI | W–L–tied | win rate | verdict |
|---|---:|---|---:|---:|---|
| **RB capture@5** | +0.0023 | [−0.0124, +0.0173] | 28–19–32 | 59.6% | contains zero |
| **RB capture@10** | +0.0052 | [−0.0022, +0.0135] | 28–19–32 | 59.6% | contains zero |
| **WR capture@5** | −0.0008 | [−0.0149, +0.0139] | 24–29–26 | 45.3% | contains zero |
| **WR capture@10** | −0.0051 | [−0.0157, +0.0053] | 28–32–19 | 46.7% | contains zero |

**Every primary confidence interval contains zero.** The pre-registered rule for that outcome is
**NO EFFECT**, and the success threshold was +0.02 — the largest primary effect is a quarter of it
and is not distinguishable from noise.

The weekly distributions say the same thing more bluntly. **The median weekly difference is exactly
0.0000 at both positions**, and the two boards produce an *identical* capture@10 in **32 of 79 RB
weeks** and 19 of 79 WR weeks.

### RB

The only position where the sign is consistently favourable, and it is small: capture@10 +0.0052,
positive in all five leave-one-season-out folds (+0.0009 to +0.0072), never significant. Precision@10
moves slightly more than capture@10 (+0.0101), which is the right direction but also not
significant. Its one significant change is a **degradation** deep in the board: capture@50 −0.0029.

### WR

The position with the largest W5 cliff, and the target change makes it slightly **worse**:
capture@10 −0.0051, negative in all five LOSO folds, and the only significant WR effect anywhere in
the experiment is `B3_Q80`'s Spearman (−0.0019) and pairwise accuracy (−0.0008) — both degradations.
Per-season, WR capture@5 is significantly *negative* in 2022 (−0.0293) and 2024 (−0.0252) and
positive in 2021 (+0.0270): noise, not signal.

### TE — the one genuine positive, and it is off-target

**TE capture@5 improves by +0.0208, CI [+0.0068, +0.0367], 25–14 weeks, p = 0.015**, and it is the
only effect in the experiment that passes all three pre-registered genuineness checks (§5). It
repeats at every quantile (Q60 +0.0134, Q80 +0.0206) and in Half-PPR (+0.0211).

**It is not a primary cell and cannot produce SUCCESS**, and it does not propagate: TE capture@10 is
−0.0083 and TE Spearman −0.0030, both null. W5 found TE was the position *without* a top-of-board
cliff; the target change helps a little exactly where the problem was not.

### FLEX

Pooled through the existing path, with no separate FLEX model. capture@10 **−0.0022**
[−0.0129, +0.0084], capture@25 **+0.0049** [−0.0000, +0.0101], Spearman **−0.0014**
[−0.0025, −0.0003]. **The positional changes do not reach the product's board.** Against ECR the
control is −0.0388 on FLEX capture@10 and the primary arm is −0.0410: no progress toward the
benchmark.

### The other arms

| | RB c@10 | WR c@10 | TE c@5 | FLEX c@10 |
|---|---:|---:|---:|---:|
| B0_RMSE | +0.0052 | −0.0034 | +0.0127 | −0.0047 |
| B1_Q60 | −0.0007 | −0.0081 | **+0.0134\*** | −0.0027 |
| **B2_Q70** | +0.0052 | −0.0051 | **+0.0208\*** | −0.0022 |
| B3_Q80 | +0.0009 | −0.0114 | **+0.0206\*** | −0.0043 |

**There is no dose-response.** The effect does not grow, shrink or order itself with the quantile
level at either primary position. Under the pre-registered reading, a hypothesis that predicts
"further up the distribution should help more" is not supported by a pattern that looks like this.

**`B0_RMSE` is indistinguishable from the quantile arms** (RB +0.0052, identical to Q70). So there
is no separate "upper-tail" effect to find: moving off MAE in *any* direction does the same amount
of nothing. That is exactly what the discriminating control was included to determine.

---

## 4. Did the W5 cliff shrink?

**No.** This is the mechanism check, and it is the most decisive result in the phase.

W5 measured the gap between Alpha's actual top-10 and what a ranker with its *own* overall ordering
quality would achieve. If the upper-outcome target fixed the mechanism W5 identified, that gap would
close. Re-running the identical test on each treated board:

| capture@10 cliff | A_MAE | B0_RMSE | B1_Q60 | **B2_Q70** | B3_Q80 |
|---|---:|---:|---:|---:|---:|
| **RB** | −0.0710 | −0.0645 | −0.0716 | **−0.0650** | −0.0684 |
| **WR** | −0.0800 | −0.0823 | −0.0869 | **−0.0836** | −0.0898 |
| **TE** | −0.0096 | −0.0108 | −0.0059 | −0.0171 | −0.0053 |

In plain English: **Alpha still leaves the same amount of value on the table at the top of the RB
board, and slightly more at WR.** The RB cliff narrows by 8% — well inside noise, and Q60 widens it
— while the WR cliff *widens* and does so monotonically with the quantile level. Half-PPR agrees
(RB −0.0794 → −0.0733; WR −0.0873 → −0.0907).

The one place a cliff genuinely closes is TE at depth 5 (−0.0292, significant, → −0.0083, not
significant), which is the same off-target improvement as §3.

---

## 5. Did the model actually get better, or just more extreme?

**Neither.** It became more *aggressive in its numbers* and almost identical in its *rankings*.

`scripts/research/w6_board_agreement.py` compares each treated board against the control board,
week by week:

| | rank correlation with the control board | top-10 overlap | weeks the top 10 is **identical** |
|---|---:|---:|---:|
| RB `B2_Q70` | **0.9958** | 93.2% | **40.5%** |
| WR `B2_Q70` | **0.9963** | 89.6% | **24.1%** |
| TE `B2_Q70` | **0.9912** | 91.8% | 34.2% |

Players move a mean of **1.4 (RB) / 2.1 (WR) places**, and only 1.9% / 7.1% move more than five.
Meanwhile the mean prediction rises by **48%** at RB (6.86 → 10.18). **Changing the quantile is,
on these eleven features, very nearly a monotone rescaling — and a monotone rescaling cannot change
any ranking at all** (W3's finding, and the reason W4's four calibrations failed).

That is the whole explanation for the null result, and it is a structural fact about the feature
set rather than about the quantile: with only lagged volume and form as inputs, the model's ordering
of players is nearly the same whichever part of the outcome distribution it is asked to hit.

**It did not become more bust-prone either.** The top-10 false-positive rate (predicted top-10,
finished outside the realized top-24) is essentially unmoved: RB 26.5% → 26.1%, WR 42.9% → 43.2%,
TE 22.5% → 22.8%. The change is neither better nor recklessly more extreme. It is inert.

---

## 6. Tradeoffs

**Better** — TE capture@5 **+0.0208** (significant, replicated at every quantile and in Half-PPR);
RB precision@10 +0.0101 and capture@10 +0.0052 (both null); FLEX capture@25 +0.0049 (null).

**Worse** — RB capture@50 **−0.0029** (significant); FLEX Spearman **−0.0014** and pairwise
**−0.0006** (significant); QB capture@20 −0.0072 (significant, and at every arm); WR capture@10
−0.0051 (null).

### 6.1 A rule defect, disclosed rather than resolved quietly

**The letter of the pre-registration triggers two verdicts at once.** Every primary CI contains
zero, which is NO EFFECT as written. But HARM's second clause — *"a guardrail breach with no
qualifying primary gain"* — also fires, because §6 defined a **breach** as any degradation whose CI
excludes zero, with **no lower bound on its size**. The two breaches are the RB capture@50 of
−0.0029 (on a metric averaging 0.92) and the FLEX Spearman of −0.0014 (on a metric averaging 0.65).

**The verdict reported is NO EFFECT**, because calling a 0.3% deep-board change "damage" would
misdescribe the experiment to the decision it exists to serve. The reason the rule misfires is
known and was already solved once: W4's §7.2 warned that *"a self-calibrated MDE shrinks as two
systems become similar and would otherwise make trivial effects significant"* and added a
**practical** bar next to the statistical one. **I applied that guard to the success side and not
to the breach side** — an error in the pre-registration, recorded as amendment A1 with the rule
that should have been written.

**Nothing material hinges on the choice.** Both readings say the same thing: do not continue this
direction.

---

## 7. Confidence

**High that the answer is "no", for this intervention.**

* **n = 79 weeks**, week as the unit of replication, paired throughout. Measured MDE on capture@10
  is 0.0206 (RB) / 0.0196 (WR); the largest primary effect is **+0.0052**, a quarter of it.
* **Leave-one-season-out**: RB positive in all five folds, WR negative in all five, none
  significant. No fold rescues the result and none drives it.
* **Per-season**: the sign flips season to season (WR capture@5 significantly negative in 2022 and
  2024, positive in 2021) — the signature of noise.
* **Half-PPR replicates the null exactly** — RB capture@10 +0.0053, WR −0.0048, TE capture@5
  +0.0211, RB capture@50 −0.0028. The second shipped format reaches the same conclusion.
* **Four arms, one direction, no pattern.** RMSE behaves like Q70; Q60, Q70 and Q80 do not order
  themselves. A real mechanism would leave a trace across four models; this leaves none.
* **All nine validity gates pass**, including a control that reproduces production exactly and
  byte-identical output on a repeat run.

The confidence is about *this* intervention. It does **not** say the W5 diagnosis was wrong — §4
shows the cliff is still there, unchanged, waiting.

---

## 8. Recommendation

**Do not continue this research direction.** Changing the training target is settled: MAE, RMSE and
three upper quantiles all produce the same board to within a rank correlation of 0.99, and none of
them touches the top-of-board gap. Per the pre-registered rule, W6 does **not** try a fourth
quantile, a blended target, a per-position quantile, or the same idea with different
hyperparameters.

**What W6 adds to the program is a constraint, and it is a useful one.** The failure is not that
the upper quantile was the wrong level — it is that *the target barely controls the ordering at
all*. On eleven lagged volume-and-form features, the model's ranking of players is nearly invariant
to which part of the outcome distribution it is asked to predict. **The ordering is determined by
the features, not by the objective.** Any future intervention that only changes what the model
predicts, and not what it can see or how it combines it, should be expected to fail the same way —
and that now includes the obvious next candidates: a different loss, a different link, a
classification reformulation of the same inputs.

This is the second consecutive phase to rule out a reshaping of the existing signal (W4 ruled out
cross-position calibration; W6 rules out target reshaping). W5's oracle already said where the
remaining value is, and it is not in either place.

---

## 9. The single best next question

> **How much of a player's week-*w* opportunity — his targets and carries — is actually
> forecastable from information available on the Friday before the game?**

W5 measured that perfect opportunity foresight is worth **53–63%** of the entire perfect-foresight
ceiling and would beat ECR by **+0.16 to +0.21** on positional capture@10, four to eight times the
current gap to the benchmark. That is by far the largest identified prize in the program, and its
decisive unknown has never been measured.

**It is a measurement, not a model.** Regress realized week-*w* opportunity on strictly-prior
opportunity features and report the achievable R², exactly the way W5 §2.6 measured the persistence
of *points*. It is cheap, it fits no production model, it carries no leakage risk, and it converts
the largest oracle in the program into either a target worth building for or a second ceiling that
cannot be reached.

**Ask it before building anything.** W6 is the evidence for that ordering: this phase spent a full
cycle discovering that an intervention could not move the board, when a one-day measurement of
where the movable signal lives would have said so in advance.

---

## 10. A priori predictions, scored

Recorded in the pre-registration §9 before any arm was compared. **Three held, four were wrong, one
split** — and the wrong ones are the informative part.

| # | prediction | outcome |
|---|---|---|
| 1 | `B0_RMSE` near a no-op | **RIGHT** — RB +0.0052, WR −0.0034, both null; board rank correlation 0.995 |
| 2 | The quantile arms will **move rankings substantially** | **WRONG, decisively.** Board rank correlation 0.9958/0.9963/0.9912; the top 10 is *identical* in 24–41% of weeks. This is the finding of the phase, and I predicted its opposite |
| 3 | Primary effect positive but sub-threshold (+0.005 to +0.015) → PARTIAL or NO EFFECT | **SPLIT** — RB capture@10 landed at +0.0052, inside the predicted band; WR was negative; the verdict is NO EFFECT, which was allowed |
| 4 | Precision@10 will move **less** than capture@10 | **WRONG at RB** — precision@10 +0.0101 against capture@10 +0.0052 |
| 5 | The effect will be **larger at WR** than RB | **WRONG** — RB is the only position with a positive sign; WR is negative at every quantile |
| 6 | TE will **degrade slightly** | **WRONG** — TE capture@5 is the only significant improvement in the experiment (+0.0208) |
| 7 | Dose-response not monotone to 0.8 | **RIGHT in outcome, wrong in reasoning** — I expected 0.8 to be worse for fitting a sparse target; in fact there is no dose-response at all |
| 8 | The cliff will shrink less than the raw gain suggests | **RIGHT, and understated** — it did not shrink at all, and widened at WR |

Prediction 2 being wrong is what turns a null result into a useful constraint: the experiment did
not fail because 0.7 was the wrong number, it failed because the objective barely controls the
ordering.

---

## 11. Test / lint / reproducibility status

### Validity gates — all nine pass

| gate | check | result |
|---|---|---|
| **G1** control fidelity | retraining with production's loss reproduces production's stored predictions | **29,376/29,376 exact, max abs diff 0.0** |
| **G2** single-variable | only `loss_function` differs from production's `MODEL_SPECS` entry | **True** |
| **G3** universe | identical prediction keys across arms; boards scoring a different player set | **True; 0** |
| **G4** causality | training frames containing the predicted season | **0** |
| **G5** no-ECR | boards needing more than their own predictions | **0** |
| **G6** already-played | evaluated players whose team had kicked off | **0** |
| **G7** null-calibration | worst \|achieved − target\| Spearman over 24 real cells | **1.35 × 10⁻⁵** |
| **G8** determinism | SHA-256 of the output, repeat run | **identical** |
| **G9** upstream | W3 / W4 / W5 re-run and diffed against their tracked results | **0 / 0 / 0** over 46,756 / 126,844 / 568,947 numeric leaves |

**G1 is the load-bearing one.** Everything W6 claims is a difference between a re-implementation and
itself with one argument changed; had the re-implementation not been production, the difference
would have been measuring something else.

### Repository

* **1,611 → 1,625 tests pass**, 44 deselected (W6 adds 14 in `tests/unit/test_weekly_arms.py`).
* `make lint` clean, **both** halves.
* **Production diff EMPTY** — everything new is under `src/alpha_squad/evaluation/weekly/`
  (research-only by its own contract), `scripts/research/`, `tests/unit/` and `docs/`.

**Reproduce:**

```
uv run python scripts/research/w6_upper_outcome.py   --out reports/weekly/w6_results.json
uv run python scripts/research/w6_board_agreement.py --out reports/weekly/w6_agreement.json
uv run python scripts/research/w6_validity_gates.py        # non-zero if any gate fails
```
