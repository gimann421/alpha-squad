# W4 — Pre-registration: is cross-position calibration the FLEX bottleneck?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any counterfactual, oracle or
calibration result existed. The forensic audit in §2 *was* run first — it describes the
data-generating process, which is what Part 1 of the brief asks for — and its a priori
predictions are recorded in §3 **before** anything is evaluated, so they can be scored against
the outcome rather than rationalised after it.

Authority: `docs/weekly/W3_ALPHA_BENCHMARK_RESULTS.md`, `docs/weekly/W2_ECR_BENCHMARK_RESULTS.md`,
`CLAUDE.md`. Decision record: `docs/DECISIONS.md` D112.

> **No change below after seeing results without a dated amendment here.** Same rule as W2's A1,
> W3, D70, D106.

---

## 1. The question — framed forensically, not as a fix

> **How much of Alpha's top-of-FLEX deficit is caused by the RB/WR/TE combination step, versus
> deficiencies already present inside the individual positional rankings?**
>
> And only then: **can pre-registered, causal cross-position calibration recover a meaningful
> part of it, without new information and without changing the positional models?**

The phase must return one of four verdicts, defined in §7:

| | verdict |
|---|---|
| **A** | cross-position calibration is the **primary** bottleneck |
| **B** | **meaningful but secondary** |
| **C** | **minor contributor** |
| **D** | **essentially irrelevant** |

**A finding of C or D is a successful outcome**, because it stops a phase of work that would
not have paid.

---

## 2. Forensic audit of the current pipeline (run first, reported as fact)

Traced through the actual code, not the docs.

**The combination step is one line.** `evaluation/weekly/alpha.py:94` —
`sorted(ranked, key=lambda r: (-predictions[r.player_id], r.player_id))`. There is **no
normalisation, no positional weighting, no rescaling** anywhere in the FLEX path (verified by
search). Three separately-trained per-position CatBoost models emit raw predicted points into
one `sorted()`.

**The three models are genuinely separate but structurally identical**: same 11 features, same
`target_fantasy_points_ppr`, same MAE loss, same hyperparameters, same walk-forward window,
same `fillna(0.0)`. They differ only in their training rows (RB 14,807 / WR 23,302 / TE 11,611
panel rows, 2015–2024).

**Missing-data handling does not advantage a position**: NULL rates are near-identical
(lag-3 features ~2.05–2.16%, season-to-date ~9.7–10.6% for all three).

**Predictions are badly compressed — and unequally so:**

| pos | mean pred | mean real | mean ratio | sd pred | sd real | **sd ratio** |
|---|---:|---:|---:|---:|---:|---:|
| RB | 6.506 | 7.800 | 0.834 | 4.938 | 8.020 | **0.616** |
| WR | 6.074 | 7.299 | 0.832 | 4.532 | 7.713 | **0.588** |
| TE | 4.344 | 5.499 | 0.790 | 3.246 | 5.969 | **0.544** |

Maximum predicted value ever emitted: RB **22.79**, WR **17.82**, TE **15.85** — against
realized maxima of 55.4 / 55.6 / 45.6. A TE can essentially never outrank a top RB on this
board.

**But the regression is nearly calibrated.** OLS of realized on predicted:

| pos | slope | intercept | corr |
|---|---:|---:|---:|
| RB | **1.0144** | +1.200 | 0.625 |
| WR | **1.0129** | +1.147 | 0.595 |
| TE | **1.0250** | +1.047 | 0.557 |

Slope ≈ 1 because the correlation exactly offsets the compression (`slope = corr · sd_r/sd_p`).
So the predictions are **conditionally** well-calibrated while being **marginally** compressed —
two different properties, and only the first one matters for ranking by expected points.

**Conditional cross-position calibration, by predicted bin** (`E[realized] − predicted`):

| bin | RB | TE | WR |
|---|---:|---:|---:|
| 08–10 | +1.48 | +1.49 | +1.34 |
| 10–12 | +1.52 | +0.95 | +1.09 |
| 12–14 | +1.58 | +0.72 | +1.11 |
| 14–16 | +1.52 | +0.35 (n=37) | +1.61 |

Restricted to predicted ≥ 10 — where the FLEX top-10 lives — the gap is **RB +1.47, WR +1.26,
TE +0.83**. Median signed error is ≈ 0 for all three positions (RB +0.08, WR +0.01, TE +0.01).

**Within the top group, Alpha's ordering is nearly uninformative**: corr(pred, real) for
predicted ≥ 10 is **RB 0.251, WR 0.222, TE 0.141**, against 0.625/0.595/0.557 over the full
range.

---

## 3. A priori predictions, recorded before any counterfactual runs

Stated so they can be **wrong** in public.

1. **The TE under-representation W3 flagged is mostly NOT a calibration error.** At a given
   predicted value, top TEs realize *fewer* points than top RBs (+0.83 vs +1.47), so an
   expected-points ranking that demotes them is behaving correctly. The realized top-10's TE
   share is driven by variance, which an E[points] ranking cannot and should not chase.
2. **Consequently, a correctly-fitted cross-position calibration will move the board in the
   OPPOSITE direction from the composition table** — pushing RB *up*, not TE up. If it improves
   ranking, composition will look *worse* against realized, not better.
3. **`CAL_AFFINE` will be close to a no-op**, because the three positional OLS fits are nearly
   identical (slopes within 0.012, intercepts within 0.153).
4. **The marginal-matching methods (`CAL_QUANTILE`, `CAL_RANKPCT`) will be neutral-to-harmful**,
   because un-shrinking a conditionally-calibrated prediction adds variance without adding
   information. CLAUDE.md records the same result for the draft program ("the un-shrunk
   prior-season total … is the worst projection in the comparison").
5. **The dominant term will be within-position ordering**, given corr ≈ 0.14–0.25 at the top of
   each position.
6. **Expected verdict: C or D.**

If the results contradict these, the results win and the contradiction is reported prominently.

---

## 4. The identifiable decomposition

Total pairwise ordering accuracy on a FLEX board is **exactly** a weighted average over
position-pair buckets:

    pairwise_total = Σ_b (n_b / N) · accuracy_b ,  b ∈ {RB-RB, WR-WR, TE-TE, RB-WR, RB-TE, WR-TE}

The first three buckets are **within-position** — untouchable by any monotone per-position
transform. The last three are **cross-position** — the only pairs calibration can move. This
is mathematically exact, needs no modelling assumption, and is the primary decomposition.

It is reported alongside the oracle decomposition (§5), which is **not** additive and is
labelled as such.

---

## 5. Counterfactual and oracle boards

All are diagnostics. **None is a production candidate.** All are evaluated on the identical
universe, week, scoring and cutoff as W3.

| id | board | what it isolates |
|---|---|---|
| **CF_A** | current Alpha — pooled raw predicted points | the W3 control |
| **ORACLE_BOTH** | pool realized points | sanity: must give ρ = 1 |
| **ORACLE_XPOS** | **Alpha's within-position order, perfect cross-position scale** | ceiling on fixing the combination step alone |
| **ORACLE_WITHIN** | **perfect within-position order, Alpha's cross-position scale** | ceiling on fixing the positional models alone |
| **CF_SWAP_{RB,WR,TE}** | one position's scale replaced by its oracle scale, others left as Alpha | which position's scale carries the effect |

**Construction of `ORACLE_XPOS`** — the key object. For each position *P* in a week: let
`A_P` be Alpha's ordering of *P*'s players and `V_P` the same week's realized values for *P*
sorted descending. Assign the player at Alpha-rank *i* within *P* the score `V_P[i]`. Alpha's
within-position ordering is preserved exactly; the cross-position scale becomes the true one.

**Construction of `ORACLE_WITHIN`**: assign the player at *realized*-rank *i* within *P* the
score `S_P[i]`, where `S_P` is Alpha's predicted values for *P* sorted descending. Within-position
order becomes perfect; the pooled scale stays Alpha's.

These use realized outcomes **by design** and are never candidates for anything.

---

## 6. Calibration methods — four, fixed now

Every method is **per-position**, **monotone non-decreasing within position** (so within-position
order is provably unchanged — asserted by test), and **causal**.

| id | transform | fitted on |
|---|---|---|
| **CAL_MEANVAR** | `g_P(x) = μ^real_P + (x − μ^pred_P)·(σ^real_P / σ^pred_P)` | prior predicted/realized moments for *P* |
| **CAL_AFFINE** | `g_P(x) = a_P + b_P·x`, OLS of realized on predicted; applied only if `b_P > 0`, else identity | prior (pred, real) pairs for *P* |
| **CAL_QUANTILE** | `g_P(x) = Q^real_P( F^pred_P(x) )` — empirical CDF of prior predictions mapped to the empirical quantile of prior realizations | prior predicted and realized *values* for *P* |
| **CAL_RANKPCT** | `g_P(player) = Q^real_P( 1 − (rank_P − 0.5)/n_P )` — discards magnitudes entirely, uses only within-position rank | prior realized values for *P* |

**Fitting window (causal).** For week *w* of season *S*, every method is fitted **only** on
completed player-weeks with `(season < S) OR (season = S AND week < w)`. Current-week outcomes
are never used. Enforced structurally and asserted by test.

**Minimum sample.** A position needs **≥ 200** prior (pred, real) pairs to fit; below that the
transform is the identity. 200 is fixed here, chosen as ~2 weeks' worth of the smallest position.

**Extrapolation.** `CAL_QUANTILE` and `CAL_RANKPCT` clamp to the fitted empirical range;
`CAL_MEANVAR` and `CAL_AFFINE` extrapolate linearly. **Ties** are broken by `player_id`
throughout, as everywhere else. **Missing predictions** are dropped and counted, never imputed.

**No sweep.** Four methods, no hyperparameters, no variants. This is a diagnosis, not a contest.

**ECR is never a calibration target.** Calibration is fitted against realized fantasy points
only. Fitting toward ECR would teach Alpha to imitate the benchmark, which is a different
question and an invalid one here.

---

## 7. Decision rules, fixed now

### 7.1 The bottleneck verdict (primary)

On **FLEX capture@10**, using the oracle gaps `X = ORACLE_XPOS − CF_A` and
`W = ORACLE_WITHIN − CF_A`:

| verdict | criterion |
|---|---|
| **A — primary** | `X > W` **and** the best causal calibration recovers ≥ 50% of `X` with a CI excluding zero |
| **B — meaningful but secondary** | `X ≥ 0.25·W` **and** the best causal calibration has a CI excluding zero |
| **C — minor** | `X < 0.25·W`, **or** every calibration's CI includes zero while `X` itself is positive |
| **D — irrelevant** | `X` is not distinguishable from zero — even a *perfect* cross-position fix changes nothing measurable |

### 7.2 Calibration success (secondary, reported separately)

Two bars, both required for a success, because a self-calibrated MDE shrinks as two systems
become similar and would otherwise make trivial effects "significant":

- **statistical** — the 95% bootstrap CI over weeks excludes zero;
- **practical** — the effect is ≥ **25% of the W3 Alpha-vs-ECR gap** on that metric. FLEX
  capture@10 gap = −0.0388 ⇒ bar **+0.0097**. FLEX Spearman gap = −0.0313 ⇒ bar **+0.0078**.

| outcome | criterion |
|---|---|
| **CLEAR SUCCESS** | both bars met on FLEX capture@10, and nothing deeper (Spearman, capture@25, capture@50) degrades with a CI excluding zero |
| **PARTIAL** | CI excludes zero but the practical bar is not met, **or** capture@10 improves while a deeper metric significantly degrades (reported as a **tradeoff**, never as success) |
| **NULL** | CI includes zero |
| **NEGATIVE** | CI excludes zero in the wrong direction |

**No composite score.** A method that wins on one depth and loses on another is reported as
exactly that.

---

## 8. Population, universe, metrics, statistics

**Unchanged from W3 in every respect** — 79 weeks, 2021–2025, Full PPR, Friday cutoff,
ECR-defined universe intersected with played and with Alpha coverage, W2's frozen metric suite
(`evaluation/weekly/metrics.py`), invalid-cell rule at 10 evaluable players.

**Unit of replication is the week.** All comparisons paired within week; 95% bootstrap CI over
weeks (10,000 resamples, seeds 0–9, `evaluation/weekly/noise.py`); Wilcoxon signed-rank and
win/loss counts as in W3. **A calibration that moves 90% of players does not have 90%
independent evidence** — n stays 79.

Reported for FLEX **and** for RB, WR, TE separately, at depths **5, 10, 25, 50** (depth 5 added
for the positional top-of-board forensics the brief requests; it is a depth of the *existing*
`topk_precision`/`topk_points_capture` metrics, not a new metric).

---

## 9. Robustness — three checks, fixed now

1. **Leave-one-season-out** on the headline calibration effect (5 recomputations of the summary).
2. **Per-position-pair** attribution: is any effect carried by a single cross-position bucket?
3. **Per-depth** consistency across 5/10/25/50.

No further slicing.

---

## 10. Leakage and validity gates

Before any result is interpreted: zero ECR inputs to Alpha or to any calibration; zero
current-week realized outcomes in any calibration fit; zero future weeks; zero already-played
players; identical universe across every counterfactual; identical scoring, cutoff and ground
truth; the benchmark run twice with byte-identical output. **If any gate fails, stop and fix the
methodology before reading results.**

---

## 11. What W4 may NOT do

Change production ranking logic, model predictions, the weekly API, the Friday-board eligibility
architecture or the injury evidence layer; add calibration to production; add ECR; add features;
retrain or tune the positional models; select a calibration method after seeing results; run a
hyperparameter sweep; or present a method as successful on one metric while hiding another.

The two W3 engineering prerequisites (injury-cutoff leakage; true Friday board) remain **out of
scope** — implementation plans may be documented, nothing implemented.

---

## 12. Amendments

*(None yet.)*
