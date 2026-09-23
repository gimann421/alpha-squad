# W6 — Pre-registration: does training for higher-end outcomes fix the top of the board?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any arm was trained beyond the control
and before any comparative result existed. The two gates in §2 *were* run first, because a
comparison built on an unverified baseline is not worth pre-registering.

Authority: `docs/weekly/W5_TOPBOARD_FORENSICS.md` (especially §18 and §25),
`docs/weekly/W4_FLEX_FORENSICS_RESULTS.md`, `CLAUDE.md`. Decision record: `docs/DECISIONS.md` D114.

> **No change below after seeing results without a dated amendment here.** Same rule as W2's A1,
> W3, W4, W5's A1, D70, D106.

---

## 1. The hypothesis

W5 established that Alpha's RB/WR top-of-board failure is a **selection** problem, not a detection
problem: it finds the right pool and cannot order inside it, the cohorts carrying the excess missed
regret are defined by features it already holds, and `P(realized ≥ 2 × predicted)` falls from 41.5%
to 5.6% across RB's predicted deciles. Its one-line summary was:

> **Alpha ranks by expected floor; points-captured@10 is won by ceiling.**

W6 tests the single-variable consequence:

> **If the model is trained to predict a higher part of the outcome distribution instead of its
> middle, do the players who actually finish at the top of the RB and WR boards move to the top of
> Alpha's board?**

**The question is not whether predicted points rise.** A monotone rescaling of every prediction
changes no ranking at all — W3 established that and W4's four failed calibrations confirmed it. The
question is whether the *right players* move up.

---

## 2. Gates already passed, before this document was written

Both were run first because the experiment is meaningless without them.

**Baseline reproduction.** W3, W4 and W5 re-run from their committed instruments and diffed against
their tracked results:

| | numeric leaves | max abs difference | key sets identical |
|---|---:|---:|---|
| W3 | 46,756 | **0** | yes |
| W4 | 126,844 | **0** | yes |
| W5 | 568,947 | **0** | yes |

**The control arm reproduces production exactly.** `evaluation/weekly/arms.py` re-implements the
narrow slice of `models/established/train.py::run_established_ml` that produces weekly predictions.
A re-implementation can drift silently from the thing it mirrors, so retraining with production's
own loss must reproduce production's own stored predictions:

| | |
|---|---|
| predictions trained | 29,376 |
| predictions stored (`weekly_projection_snapshot`, `ml_catboost`) | 29,376 |
| keys only in one side | **0** |
| **exact matches** | **29,376 (100.0%)** |
| max absolute difference | **0.0** |

Positions QB 3,279 · RB 7,687 · WR 12,298 · TE 6,112. **Every arm below therefore differs from
production in exactly one argument and nothing else.**

---

## 3. The arms — fixed now

| id | `loss_function` | what it targets | role |
|---|---|---|---|
| **A_MAE** | `MAE` | the conditional **median** | **the control** — production, byte-identical |
| **B0_RMSE** | `RMSE` | the conditional **mean** | **discriminating control**, not a candidate |
| **B1_Q60** | `Quantile:alpha=0.6` | the 60th percentile | dose-response |
| **B2_Q70** | `Quantile:alpha=0.7` | the 70th percentile | **PRIMARY** |
| **B3_Q80** | `Quantile:alpha=0.8` | the 80th percentile | dose-response |
| **C** | — | — | the W5 **copula null**, unchanged |

**Everything else is frozen and asserted by test**: the same 11 `FULL_FEATURES`, the same
`target_fantasy_points_ppr`, `iterations=200`, `depth=4`, `learning_rate=0.05`, `random_seed=42`,
the same per-position split, the same walk-forward window `[2015, S−1]`, the same `fillna(0.0)`,
the same prediction frame. `BASE_KWARGS` is asserted equal to production's `MODEL_SPECS` entry
minus `loss_function`.

### 3.1 Why these levels, chosen before any result

**Why a quantile at all.** MAE minimises absolute error, whose minimiser is the conditional
*median*. "Train it to care about higher-end outcomes" has a direct, single-argument
implementation: move the quantile up. Nothing else about the model changes, so any effect is
attributable.

**Why 0.7 is primary.** It is the midpoint of the pre-registered range and was named as such in
`W5_TOPBOARD_FORENSICS.md` §25 before any of these models existed. 0.6 is close enough to the
median that a null result would be uninformative about the hypothesis; 0.8 is far enough up that a
null result could be attributed to the target being too sparse to fit. 0.7 is the level at which
the hypothesis is most fairly tested, and it is fixed here so it cannot be re-chosen later.

**Why RMSE is included, and why it is not a candidate.** Ranking by *expected* points means ranking
by the conditional **mean**, which is what RMSE targets. Without this arm, a win for `B2_Q70` could
not be distinguished from "anything other than MAE helps" — the upper-quantile hypothesis and the
mean-versus-median hypothesis would be confounded. `B0_RMSE` separates them. It is a control for
interpretation, not a thing W6 is trying to promote.

W5's amendment A1 already tested the mean-versus-median story descriptively and found the
mean−median gap **flat** across the predicted range (+1.0 to +1.9 at every decile), which predicts
`B0_RMSE` should be close to a no-op. That prediction is recorded in §9.

### 3.2 Target construction

There is **no new target column**. `target_fantasy_points_ppr` is unchanged; only the loss that is
minimised against it changes. Quantile regression is fitted **separately by position**, exactly as
production fits separately by position — the quantile is of each position's own conditional outcome
distribution, not of a pooled one.

---

## 4. Population, universe, metrics, statistics

**Unchanged from W3/W4/W5 in every respect** — 79 weeks, 2021–2025, Full PPR primary with a
Half-PPR replication, Friday cutoff, ECR-defined positional universe intersected with played and
with Alpha's coverage, W2's frozen metric suite, invalid-cell rule at 10 evaluable players.

**All arms predict the identical rows** (they share `predict_df`), so the evaluated universe is
identical across arms by construction — asserted as a gate, not assumed.

**Unit of replication is the week (n = 79).** Every comparison is paired within week; 95% bootstrap
CI over weeks (10,000 resamples, seeds 0–9, `evaluation/weekly/noise.py`); Wilcoxon signed-rank and
win/loss counts reported alongside so an average driven by a handful of weeks is visible. The
distribution of weekly differences is reported, not only its mean.

**Measured MDE on positional capture@10 at n = 79** (from W5, not assumed): RB **0.0206**, WR
**0.0196**, TE **0.0193**.

---

## 5. Primary evaluation

**`B2_Q70` versus `A_MAE`**, on four pre-registered cells:

| position | metric |
|---|---|
| RB | capture@5, capture@10 |
| WR | capture@5, capture@10 |

Points captured, not precision, is primary for the same reason it was in W4 and W5: it prices a
miss by what the miss cost. **Precision@5 and precision@10 are reported alongside as part of the
genuineness test in §7**, not as primary outcomes.

---

## 6. Guardrails

The change must not buy the top of the RB/WR board by damaging the rest. Every guardrail is
evaluated as `B2_Q70 − A_MAE`, paired over weeks, and a **breach** is a degradation whose 95% CI
excludes zero:

* **RB and WR depth**: capture@20, capture@50.
* **TE**: capture@5, capture@10, capture@20, capture@50 — W5 found TE has *no* cliff, so it is the
  position most at risk from a change aimed at RB/WR.
* **Overall ranking quality**: Spearman and pairwise accuracy, per position.
* **FLEX**: capture@10, capture@25, Spearman — built by pooling the treated RB/WR/TE predictions
  through the **existing** FLEX path, with **no separate FLEX model** and no cross-position
  adjustment (W4/D112 settled that calibration is not the lever).
* **QB**: reported for contrast, excluded from the decision rules, as in W5.

**Breach set, fixed now.** A guardrail breach is a significant degradation in any of:
TE capture@10 · any position's capture@50 · FLEX capture@25 · any position's Spearman.

---

## 7. Is it genuinely better, or merely more extreme?

A quantile loss shifts predictions upward. A *uniform* shift changes no ranking, so any measured
movement is a genuine reordering — but a reordering that merely chases variance is not an
improvement. Three pre-registered checks, all required for an improvement to count as **genuine**:

1. **Consistency** — `B2_Q70` wins ≥ **60%** of the weeks in which the primary effect is measured.
   A mean driven by a handful of weeks is not a product improvement.
2. **Agreement between capture and precision** — the effect on precision@10 has the **same sign**
   as the effect on capture@10 at the position claimed. Capture rising while precision does not
   means a few large scores were caught, not that better players were selected.
3. **The mechanism moved** — the W5 copula-null cliff at that position **shrinks** (its point
   estimate moves toward zero). A metric that improves while the cliff is unchanged means something
   other than the hypothesised mechanism produced it, and must be reported as such.

**Movement diagnostics, reported whatever the outcome**: mean and distribution of |Δ predicted
rank|; share of players moving more than 5 and more than 10 places; which players move up, measured
as the correlation of Δrank with `snap_pct_avg_last3` and `fp_ppr_avg_last3` (does it simply
promote players who already had high recent usage?); the standard deviation of predictions per arm;
and the top-10 false-positive rate (predicted top-10, finished outside the realized top-24) per
arm — the direct test of whether it creates more busts.

---

## 8. Decision rules — fixed now

Evaluated on the **primary arm only**. `Δ` is `B2_Q70 − A_MAE`.

| verdict | criterion |
|---|---|
| **SUCCESS** | Δ capture@10 ≥ **+0.02** at RB **or** WR with a 95% CI excluding zero, **and** all three genuineness checks in §7 pass at that position, **and** no guardrail breach |
| **PARTIAL** | a positive effect with a CI excluding zero that falls short of +0.02, **or** a qualifying effect at one position accompanied by a guardrail breach, **or** a qualifying effect that fails one genuineness check |
| **NO EFFECT** | every primary CI contains zero |
| **HARM** | any primary CI excludes zero in the **negative** direction, **or** a guardrail breach with no qualifying primary gain |

**+0.02** is roughly the measured MDE and roughly half the W5 cliff; it is fixed here and is not a
number chosen after seeing an effect size.

### 8.1 Multiplicity — how three quantiles are read without becoming a search

**`B2_Q70` alone decides the verdict.** `B1_Q60` and `B3_Q80` are reported as a **dose-response
pattern**: if the hypothesis is right, the effect should vary monotonically with how far up the
distribution the target sits. They may **corroborate** a primary result and they may **not rescue
one**. If `B2_Q70` returns NO EFFECT and another arm shows a positive effect, the phase reports
**NO EFFECT on the pre-registered hypothesis**, with the other arm noted as an exploratory
observation requiring its own experiment.

**`B0_RMSE` is interpretive, not competitive.** It tells us whether any effect belongs to the
*upper-ness* of the target or merely to *not being MAE*. If `B0_RMSE` and `B2_Q70` move together,
the finding is "MAE was the problem", not "the upper tail was the answer".

### 8.2 No optimisation after results

If the primary arm fails, W6 does **not** try a fourth quantile, a different depth, more
iterations, a blended target, or a per-position quantile. It reports the failure and names the next
question. This is the rule W4 honoured when all four of its calibrations failed.

---

## 9. A priori predictions, recorded before any arm result

Stated so they can be wrong in public, as in W4 and W5 — where three of eight were wrong and the
errors changed the recommendation.

1. **`B0_RMSE` will be close to a no-op**, because W5's amendment A1 found the mean−median gap flat
   at +1.0 to +1.9 across all ten predicted deciles, and a flat additive offset cannot reorder.
2. **The quantile arms will move rankings substantially** — this is not a monotone rescaling,
   because a quantile fit re-weights *which* training rows drive each split, so tree structure
   changes and players genuinely reorder.
3. **The primary arm will produce a positive but sub-threshold effect on capture@10** — I expect
   something in the range +0.005 to +0.015, short of the +0.02 bar, giving **PARTIAL** or
   **NO EFFECT** rather than SUCCESS.
4. **Precision@10 will move less than capture@10**, because W5 showed even a perfect *usage* oracle
   recovers 56–63% of the capture ceiling but only 35–40% of the precision ceiling — the exact
   names at the top are decided by conversion, which no target change can reach.
5. **The effect will be larger at WR than at RB**, because WR has the larger cliff (−0.0800 vs
   −0.0710) and the deeper tail of missed finishers (30.0% beyond predicted rank 40 vs 10.2%).
6. **TE will degrade slightly**, because it has no cliff to fix and the change is not aimed at it.
7. **Dose-response will not be monotone to 0.8** — I expect 0.8 to be worse than 0.7, because an
   80th-percentile target on a heavily zero-inflated outcome fits mostly noise.
8. **The copula-null cliff will shrink less than the raw capture@10 gain suggests**, because part
   of any gain will come from the board becoming better overall rather than better *at the top*.

---

## 10. Robustness — fixed now

1. **Leave-one-season-out** on the primary effect (5 recomputations per primary cell).
2. **Per-season** reporting of the primary effect, so a result driven by one unusual season is
   visible rather than averaged away.
3. **Per-depth** consistency across 5 / 10 / 20 / 25 / 50.
4. **Half-PPR replication** of the primary effect and the cliff re-test. **Half-PPR is a
   replication, never a selection instrument** — no arm may be chosen or promoted on it.

No further slicing.

---

## 11. Validity gates — all must pass before any result is interpreted

1. **Control fidelity** — `A_MAE` reproduces `weekly_projection_snapshot` exactly (§2).
2. **Single-variable** — `BASE_KWARGS` equals production's spec minus `loss_function`; features,
   target and window identical (asserted by unit test).
3. **Identical universe** — every arm predicts exactly the same keys, and every board scores
   exactly the same players.
4. **Causality** — no arm's training window includes the season it predicts.
5. **No ECR** — no arm reads the benchmark; each board's order is reproducible from its own
   predictions alone.
6. **Already-played** — zero evaluated players whose team had kicked off.
7. **Null calibration** — the copula null achieves the Spearman it is asked for.
8. **Determinism** — the runner produces byte-identical output on two runs.
9. **Upstream reproduction** — W3, W4 and W5 still reproduce exactly.

**If any gate fails, stop and fix the instrument before reading results.** W5's G10 is the
precedent: it failed, it was real, and the fix had to precede interpretation.

---

## 12. What W6 may NOT do

Change production behaviour or any file under `models/`, `league/`, `api/`, `cli.py`, `market/`,
`features/`, `identity/`, `ingest/`, `sources/`; add ECR; add features; tune any hyperparameter;
change more than the loss; build a separate FLEX model; run a sweep; choose a quantile after seeing
results; or present a sub-threshold or inconsistent effect as success.

---

## 13. Amendments

### A1 — the HARM rule had no practical floor, and fires on a negligible effect (dated: W6 results run)

**What happened.** §8's four verdicts are not mutually exclusive, and on the actual result two of
them fire at once. Every primary CI contains zero, which is **NO EFFECT** exactly as written. But
HARM's second clause — *"a guardrail breach with no qualifying primary gain"* — also fires,
because §6 defines a **breach** as any degradation whose 95% CI excludes zero, with no lower bound
on its size. The two breaches are **RB capture@50 = −0.0029** (on a metric averaging 0.92) and
**FLEX Spearman = −0.0014** (on a metric averaging 0.65).

**Why the literal reading is rejected.** Calling a 0.3% change in a deep-board metric "damage"
would misdescribe the experiment to the product decision this report exists to serve. W4's §7.2
identified precisely this hazard and guarded against it — *"a self-calibrated MDE shrinks as two
systems become similar and would otherwise make trivial effects significant"* — and added a
**practical** bar alongside the statistical one. **I applied that guard to the success side and
not to the breach side.** That asymmetry is an error in this pre-registration, not a finding about
the model.

**What is reported.** The verdict is **NO EFFECT**, and §5 of the results document states the
literal HARM trigger, its two component effects and their sizes, so a reader can apply either
reading. **Nothing material hinges on the choice**: both readings recommend discontinuing the
direction, for the same reason.

**The rule that should have been written**, recorded so a later phase inherits it rather than the
defect: *a guardrail breach requires a CI excluding zero **and** a magnitude of at least 25% of the
primary success threshold* — here 0.005 — which neither of these two clears.

No other rule, threshold, metric or arm was changed, and the primary verdict was not affected by
this amendment.
