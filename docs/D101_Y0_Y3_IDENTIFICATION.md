# D101 — Do D78's Y0–Y3 arms differ in top-6 identification?

**Verdict: DO NOT SHIP.** Nothing is promoted and nothing changes. The phase answers its question
decisively and in the negative — **Y3 should not be preferred over Y1** — but the decisive finding
arrived before identification did: **D78's recorded verdict that Y3 passes all seven gates does not
reproduce on the current data snapshot. Y3 fails G6 at WR.** On the identification axis Y3 is then
also *worse* than Y1 on the primary metric. Y1, the arm already shipped, is the best arm on both
axes. **No production code, no model, no retraining, no draft run, no PR.**

---

## 1. Repository state

| check | result |
|---|---|
| working tree at start | clean |
| branch / HEAD at start | `d100-feature-signal-diagnostic`, `7c9d022` (D100) |
| `origin/main` | `277204f`; PR #23 (D98) and PR #19 open, **not merged** |
| `models/` tree | `73b408e9bd12daecdd6a2a875e48735319b66aef` — Y1 baseline, **unchanged** |
| `league/` tree | `d4cfd00e31b949c79eda397824a7952bd31f8f9f` — Y1 baseline, **unchanged** |
| board vintage | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` |
| CatBoost | 1.2.10 |

## 2. Exact Y0–Y3 definitions used, and whether they have changed

Taken verbatim from `evaluation/projection_specification.py`; no arm was modified, reimplemented,
or re-parameterised. Each arm's training frame comes from the shipped `select_training_rows` and
each fit from the shipped `_fit_predict` — the same two calls `measure_arm` makes.

| arm | definition (module docstring) |
|---|---|
| Y0 | control — production: train on every season ≤ S−2, ECR sentinel 999 kept |
| Y1 | train through S−1 (the most recent completed season reaches the point model) |
| Y2 | drop training seasons whose preseason board does not exist (ECR coverage < 0.5) |
| Y3 | both Y1 and Y2 |

**Has the code changed since registration?** `projection_specification.py` has exactly two commits:
`d976622` (D78, introducing it) and `2fea3d2` (D79). D79's diff is **22 insertions / 19 deletions
and is a pure refactor**: it adds a `control: Arm = PREREGISTERED_CONTROL` parameter to `_paired`
and `evaluate_gates` and threads it through, so every D78 call site is behaviourally identical.
No arm definition, threshold, gate formula, or estimator changed. Verified by reading the diff, not
inferred from the commit message.

## 3. Exact identification metric definition

`top6_hit_rate = |realized top 6 ∩ projected top 6| / 6`, per (arm, season, position).

Identical to D100's definition, and identical **by construction rather than by comment**: the
harness imports D100's committed `top_set` and `auc` from `scripts/research/d100_feature_signal.py`
rather than reimplementing them, and a unit test pins that the imported module is that file. The
realized top 6 is the six highest `target_points` in the position pool; the projected top 6 is the
six highest by that arm's prediction over the **same** pool; both break exact ties on `player_id`
ascending (D54's determinism convention). The realized set is computed once per (season, position)
and is independent of every arm's ranking.

Supporting metrics: Mann-Whitney AUC for realized-top-6 membership, and Spearman against the
realized total — the latter being literally G4's own quantity, so the two axes can be read against
each other.

## 4. Pre-registered decision rule

Written into the harness docstring before any arm's identification result was inspected. Arms are
classified A/B/C/D exactly as the phase brief specifies; no numeric economic threshold for hit rate
was invented, and no threshold was chosen after seeing a result. For Y3 specifically, a positive
answer requires **both** that the existing D78 gates remain satisfied **and** that the
identification improvement is directionally consistent and not confined to a single cell or season.
The identification metric is never fed back into training, arm selection, or the gates.

Multiplicity was declared exploratory **in advance**: three arms are compared against control on a
new metric with no existing project registration correcting for it, so no identification result may
be called significant on an uncorrected interval. Bonferroni context is printed for reference
(t(3) ≈ 4.86 at 4 season clusters; t(15) ≈ 2.69 at 16 cells), never applied as a gate.

## 5. Universe and parity checks — and four discrepancies

All twelve self-checks were run. Nine passed as specified. **Four discrepancies were found**, three
in the registered experiment and one in this phase's own harness.

### 5.1 The population conflict — the phase brief says 2021–2025, the registration says 2022–2025

`PREREGISTERED_TARGET_SEASONS = (2022, 2023, 2024, 2025)`. Adding 2021 is not a neutral widening:
at target season 2021 **both treatment arms collapse onto their controls, exactly.**

Measured ECR coverage by training target-season is **0.000 for 2016–2019** and 0.878–0.947 for
2020–2024, so:

- Y2 at 2021 trains on target seasons ≤ 2019 → **zero** eligible seasons → falls back → training
  rows identical to Y0 (435 rows, seasons {2016…2019}).
- Y3 at 2021 trains on ≤ 2020 → **one** eligible season {2020} → below `MIN_TRAIN_SEASONS = 2` →
  falls back → training rows identical to Y1 (549 rows).

Confirmed on outputs, not on prose — the 2021 transparency panel gives Y2 metrics byte-identical to
Y0 and Y3 byte-identical to Y1 (MAE, hit rate, AUC alike). **Every 2021 cell is a structural tie**,
so including it would dilute the contrast by 20% with guaranteed-zero rows.

**Resolution:** the registered window is primary — changing an experiment's population after the
fact is the protocol violation these phases exist to avoid — and 2021 is reported as a separate,
clearly-labelled panel that enters no decision. Both are in §9.

### 5.2 Y2 is degenerate inside its own registered window as well

The module justifies starting at 2022 as "the earliest target season at which Y2 has at least one
eligible training season." **One is not enough:** its own `MIN_TRAIN_SEASONS = 2` rule then forces a
fallback. The harness reports the shipped `fell_back` flag directly:

> ARM FALLBACKS: 4 — **Y2: [2022] (4 of 16 cells)**. Y3: none.

So **Y2 carries a real treatment in only 3 of its 4 registered seasons**, and its G2 detail line
shows exactly that (`2022:+0.00`). The registered window's stated rationale is off by one against
the registration's own eligibility rule. Y3 is unaffected.

### 5.3 D78's recorded Y3 verdict does not reproduce — this is the phase's decisive finding

| arm | MAE now | D78's table | Δ | RMSE now | D78 | Spearman now | D78 |
|---|---|---|---|---|---|---|---|
| Y0 | 41.983 | 41.879 | +0.104 | 58.327 | 58.288 | 0.7659 | 0.7656 |
| Y1 | 40.638 | 40.725 | −0.087 | 56.616 | 56.723 | 0.7773 | 0.7749 |
| Y2 | 40.694 | 40.495 | +0.199 | 57.289 | 56.946 | 0.7721 | 0.7713 |
| Y3 | 39.411 | 39.687 | −0.276 | 55.616 | 55.892 | 0.7823 | 0.7804 |

The drift is small — 0.2% to 0.7% — but it is not zero, and **it is enough to flip G6 for Y3.**
Three candidate causes were tested:

- **Code drift — ruled out.** §2: the only post-D78 edit is a default-preserving refactor.
- **Run-to-run nondeterminism — ruled out.** `measure_arm` was called three times on each of three
  cells; MAE, top-decile bias and Spearman were identical to nine decimals every time.
- **Data or library drift — the remaining explanation.** The pre-D78 database is not recoverable
  (D91 recorded the artifacts are gone) and there is no ingestion log, so this cannot be attributed
  further than "the snapshot changed between D78's run and this one." It is recorded as unresolved
  rather than guessed at.

**Consequence: any future citation of "Y3 passed all seven gates" must be re-derived, not quoted.**
D100's recommendation to re-run Y0–Y3 rested on that claim; D101 is the phase that checked it, and
it does not hold on current data.

### 5.4 G6's prose and its implementation are different statistics

The pre-registration says "the 4-season mean **|top-decile signed bias|**" — mean(|x|). The code
computes `pivot_table(...).abs()`, which means the *absolute value of the mean* — |mean(x)|. These
differ whenever the signed bias changes sign across seasons, which it does at WR (+15.97, −2.01,
−38.31, −61.35 for Y0) and at TE.

| arm | G6 as coded → \|mean(signed)\| | G6 as written in the prose → mean(\|signed\|) |
|---|---|---|
| Y1 | PASS | PASS |
| Y2 | FAIL at [RB] | FAIL at [**RB, WR**] |
| Y3 | **FAIL at [WR]** | **FAIL at [WR]** |

Two things follow. First, **Y3 fails under both readings**, so the ambiguity does not change this
phase's answer. Second, D78's own narrative records Y2 as "top-of-board worse at RB **and WR**" —
which matches the *prose* reading, not the code. The gates were evaluated **as coded and unchanged**,
per the brief; the prose reading is reported here only as a labelled sensitivity, and resolving
which one G6 is meant to be is left to a future phase (§16).

### 5.5 A defect in this phase's own harness, found and fixed

Self-check 6 (deterministic tie handling) **failed in my harness**, not in the arms. Season-level
win/loss counts were classified with a bare `> 0`. The per-cell deltas are differences of sixths,
so a season where one position gains a player and another loses one — 2024's Y1-vs-Y0 counts are
QB 3v3, RB 3v3, WR 1v2, TE 3v2 — averages to `6.938893903907228e-18` rather than `0.0` and was
counted as a **win**. That overstated Y1's season record as 3W/1L when it is 2W/1T/1L.

Fixed with an explicit `SIGN_TOLERANCE = 1e-12` (the smallest genuinely non-zero season delta is
1/24 ≈ 0.042, five orders of magnitude clear), every sign count routed through one `_sign_counts`
helper, and a regression test carrying the real cell counts — the naive literal
`mean([1/6, −1/6, 1/6, −1/6])` is exactly 0.0 and does *not* reproduce the artifact, so the test
carries the counts and performs the subtraction. **Every number in this report is post-fix.**

### 5.6 The checks that passed

- **Pool parity: 16 of 16 cells, identical pool size for all four arms.** Structural — the target
  slice depends only on (position, season), never on the arm — and asserted anyway, with a loud
  `UniverseMismatchError` rather than a warning.
- **D100 universe cross-check: zero differing cells.** The Y-arm target pool matches
  `uncertainty_predictions` exactly in every (season, position), so D100's definition is reproduced
  on the identical population rather than on a lookalike.
- **Gate parity: verified, not assumed.** For every cell the harness re-derives `measure_arm`'s own
  MAE, RMSE, Spearman and top-decile bias from the retained per-player predictions and fails the run
  if any differs by more than 1e-9. It never did. The predictions scored for identification are
  therefore provably the same predictions the gates are computed on.
- Leakage: `_assert_no_leakage` is the shipped structural guard, plus an independent check that no
  training row's target season reaches the target. No 2020 cell, no 2026 data, 2021 excluded from
  every decision.

## 6. Axis 1 — existing D78 gates, evaluated unchanged

Computed by the shipped `evaluate_gates`, current snapshot, registered window.

| arm | G1 | G2 | G3 | G4 | G5 | G6 | G7 | verdict |
|---|---|---|---|---|---|---|---|---|
| **Y1** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **PASSES all seven** |
| Y2 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ RB | ✅ | **FAILS** |
| **Y3** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ **WR** | ✅ | **FAILS** |

Details: Y1 dMAE −1.345, 4/4 seasons better, p=0.0039. Y2 dMAE −1.289, 3/4 seasons (2022 is its
fallback cell, +0.00), p=0.0115. Y3 dMAE −2.572 — the best accuracy of any arm — 4/4 seasons,
p=0.0034, and it still fails G6.

Y3's G6 failure decomposed (signed top-decile bias at WR, by season):

| arm | 2022 | 2023 | 2024 | 2025 | \|mean\| |
|---|---|---|---|---|---|
| Y0 | +15.97 | −2.01 | −38.31 | −61.35 | 21.424 |
| Y3 | +10.16 | +1.92 | **−51.44** | −59.23 | **24.644** |

Y3 is *better* than control in 2022 and 2023 and worse in 2024, and the single 2024 WR cell decides
the gate. Reported plainly: this failure is driven by one cell, and the margin under the prose
reading (30.687 vs 29.407) is small relative to a statistic whose season values span 2 to 61. It is
still a failure, under both readings, and the pre-registered rule does not have a "nearly" branch.

**Selection rule applied unchanged — ship the lowest-numbered arm clearing all seven gates — selects
Y1, which is what is already in production.**

## 7. Axis 2 — top-6 identification results by arm

| arm | QB | RB | WR | TE | **all** | mean hits / cell |
|---|---|---|---|---|---|---|
| Y0 | 0.292 | 0.375 | 0.292 | 0.417 | 0.3438 | 2.06 |
| **Y1** | 0.375 | 0.333 | 0.333 | 0.458 | **0.3750** | **2.25** |
| Y2 | 0.292 | 0.375 | 0.333 | 0.292 | 0.3229 | 1.94 |
| Y3 | 0.417 | 0.292 | 0.333 | 0.417 | 0.3646 | 2.19 |

**Y1 is the best arm on the primary identification metric.** Y3 is second, Y2 is worse than control.

## 8. Per-position results

The per-position columns above are the headline. The comparison that decides the phase is Y3 − Y1,
in hits per cell:

| position | 2022 | 2023 | 2024 | 2025 | mean | record |
|---|---|---|---|---|---|---|
| QB | +0 | +0 | +1 | +0 | +0.25 | 1W/3T/0L |
| RB | +1 | −1 | −1 | +0 | −0.25 | 1W/1T/2L |
| WR | −1 | +1 | +1 | −1 | +0.00 | 2W/0T/2L |
| TE | −2 | +0 | +1 | +0 | −0.25 | 1W/2T/1L |

**No position consistently favours Y3.** Two of four are net negative, one is exactly zero, and the
positive one (QB) is a single player in a single season. This is precisely the "confined to a single
cell" pattern the pre-registered rule excludes.

## 9. Per-season results

Top-6 hits summed over the four positions (max 24):

| arm | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|
| Y0 | 6 | 9 | 10 | 8 |
| Y1 | 8 | 11 | 10 | 7 |
| Y2 | 6 | 8 | 11 | 6 |
| Y3 | 6 | 11 | 12 | 6 |

**2021 transparency panel — excluded from every decision** (§5.1):

| arm | hits (of 24) | mean hit rate | mean MAE |
|---|---|---|---|
| Y0 | 5 | 0.2083 | 44.531 |
| Y1 | 7 | 0.2917 | 41.870 |
| **Y2** | **5** | **0.2083** | **44.531** |
| **Y3** | **7** | **0.2917** | **41.870** |

Y2 is byte-identical to Y0 and Y3 byte-identical to Y1, as the fallback rules require.

## 10. Paired comparisons

Left block: 16 position-season cells (D78's own G5 unit). Right: 4 season clusters (the independent
unit). **Exploratory — see §12.**

| contrast | mean Δ | cells W/T/L | t | 95% CI | seasons W/T/L |
|---|---|---|---|---|---|
| Y1 − Y0 | **+0.0313** | 7W/5T/4L | 0.90 | [−0.043, +0.105] | 2W/1T/1L |
| Y2 − Y0 | −0.0208 | 2W/11T/3L | −0.70 | [−0.085, +0.043] | 1W/1T/2L |
| Y3 − Y0 | +0.0208 | 5W/6T/5L | 0.49 | [−0.070, +0.112] | 2W/1T/1L |
| **Y3 − Y1** | **−0.0104** | 5W/6T/5L | −0.27 | [−0.093, +0.072] | **1W/1T/2L** |
| Y3 − Y2 | +0.0417 | 7W/5T/4L | 1.07 | [−0.041, +0.124] | 2W/2T/0L |

Every interval spans zero. Not one contrast is resolved at this sample size, and none is claimed to
be. The informative content is the sign pattern: Y3 − Y1 is a coin flip at cell level (5W/6T/5L) and
negative at season level.

## 11. AUC and Spearman supporting results

| arm | AUC | Spearman (G4's own quantity) |
|---|---|---|
| Y0 | 0.8912 | 0.7659 |
| Y1 | 0.9029 | 0.7773 |
| Y2 | 0.8929 | 0.7721 |
| **Y3** | **0.9053** | **0.7823** |

| contrast | ΔAUC | cells W/T/L | t | 95% CI |
|---|---|---|---|---|
| Y1 − Y0 | +0.0117 | 8W/1T/7L | 1.71 | [−0.003, +0.026] |
| Y3 − Y0 | +0.0142 | 11W/1T/4L | 1.71 | [−0.003, +0.032] |
| Y3 − Y1 | +0.0024 | 8W/2T/6L | 0.60 | [−0.006, +0.011] |

**The supporting metrics and the primary metric disagree about Y3 vs Y1.** AUC and Spearman both
rank Y3 first; top-6 hit rate ranks Y1 first. That is not a contradiction — it is D100's point
restated on new data. AUC and Spearman are whole-pool statistics over ~60–190 players and are
dominated by the bulk of the distribution; top-6 membership is an extreme-tail event. **An arm can
order the pool better overall while identifying the top six slightly worse, and Y3 does.** The
practical consequence for the project is that **G4's Spearman gate cannot be treated as a proxy for
identification**, which is exactly the gap D100 said the D78 suite had.

## 12. Multiplicity and power

- **Four season clusters.** t(3, .975) = 3.182. Every identification interval in §10 spans zero.
- **Declared exploratory in advance**, so no identification result is called significant. For
  reference only, Bonferroni over the three primary-metric arm contrasts would need t ≈ 4.86 at 4
  clusters or t ≈ 2.69 at 16 cells; the largest observed is 1.71 (AUC), the largest on the primary
  metric is 1.07. **Nothing comes close under any correction, and nothing would come close
  uncorrected either.**
- **The cells are not independent.** The 16 position-seasons share four seasons and four training
  pipelines; the 16-cell t-statistics are reported because G5 uses that unit, not because they carry
  16 degrees of freedom.
- **The metric is coarse.** Six positives per cell means one player moves the hit rate by 0.167.
  Several contrasts are literally one or two players across the whole study.
- **Y2 is under-treated**: 4 of its 16 cells are fallbacks (§5.2), so its contrast is diluted by
  construction and should not be read as a clean test of the ECR-sentinel repair on its own.

## 13. Does Y3 add evidence beyond D78?

**Yes — and the evidence runs against Y3.**

The pre-registered requirement was that a positive answer needs **both** conditions. Y3 satisfies
**neither**:

1. *Existing projection-quality gates remain satisfied* — **NO.** Y3 fails G6 at WR, under both
   readings of that gate. D78's contrary record does not reproduce (§5.3).
2. *Identification improvement directionally consistent and not confined to a single cell/season* —
   **NO.** Y3 − Y1 is −0.0104 on the primary metric, 1W/1T/2L across seasons, and no position
   consistently favours Y3 (§8).

Y3 does have the best MAE (39.411), the best Spearman (0.7823) and the best AUC (0.9053) of the four
arms. That is honestly reported and it is *not* sufficient: it is exactly the pattern the seven
gates exist to refuse — a pooled-accuracy win that damages the top of the board at one position.

**Classification:**

| arm | class | reasoning |
|---|---|---|
| Y1 | **B** | passes all seven gates; identification best of the four but the improvement over control is weak and unresolved (2W/1T/1L seasons, CI spans zero) |
| Y2 | **D** | fails G6 at RB; identification *worse* than control (−0.0208); 4 of 16 cells are fallbacks |
| Y3 | **C** | identification up versus control on all three metrics, but the projection gates fail — and the "improvement" is a coin flip on the primary metric and negative against Y1 |

**Did the new identification layer add evidence the D78 suite missed?** Modestly, and it pointed the
same way. It rescued no arm the gates rejected and it ranked first the arm already shipped. Its one
genuinely new contribution is §11: identification and the existing rank gate disagree about Y3, so
the project cannot keep treating G4 as covering the top of the board.

## 14. Is any arm justified for downstream draft testing?

**No.** No arm passes both axes. Y1 passes the gates and leads identification, but Y1 **is** the
shipped production specification — there is nothing to test downstream that is not already live. Y2
and Y3 fail the gates. Per the brief's instruction, this phase stops here rather than designing the
next draft experiment, and no draft simulation, no 2026 run, and no production change was performed.

## 15. Decision

**DO NOT SHIP.**

Nothing is promoted. `models/` and `league/` are byte-identical to the Y1 baseline. The D78
selection rule, re-applied to current data, re-selects Y1 — the arm already in production — so the
correct outcome of this phase is that production does not move.

**The identification question about the registered training-set arms is now closed.** D100 asked
whether Y3 should be preferred; the answer is no, on both axes, and the training-set axis is
exhausted: none of the three registered variations captures the +0.80-of-6 exploitable signal D100
measured, and the best of them on identification is the arm already shipped.

**What remains unresolved, stated plainly:**

- **D78's published Y-arm table is not reproducible on the current snapshot** and the cause cannot
  be isolated without the old database. Until that is resolved, no D78 arm verdict should be quoted
  without re-derivation.
- **G6 is ambiguous** — its prose and its code are different statistics (§5.4) — and it is the gate
  that decides both Y2 and Y3.
- **The evaluation criterion itself is unsettled.** D79 recorded that its monotone-constraint arm
  "fails six of seven pre-registered gates" on pool-wide MAE while fixing the real defect in "the
  twenty players a draft actually consumes." D100 found the same mismatch from the feature side.
  D101 now finds it a third time, in the disagreement between AUC/Spearman and top-6 hit rate.

## 16. Smallest next experiment

Not another arm. **The three phases above have converged on the same unresolved question, and it is
a decision question, not a modelling one:** the gates measure pool-wide accuracy over ~150 players
per position-season, while the product consumes the top ~20.

> **Settle the projection objective before fitting anything else. On the measurement frames that
> D78, D79 and D101 have already produced — no new fits, no new data — pre-register (a) whether the
> project's projection criterion is pool-wide accuracy or top-of-board identification, or an
> explicitly weighted combination; and (b) whether G6 reads `mean(|signed bias|)`, as its prose
> says, or `|mean(signed bias)|`, as its code does.**

It costs almost nothing: every measurement it needs already exists in this repository. It is
decision-first, so it cannot be accused of choosing a criterion to suit a result — provided it is
registered before any arm is re-scored under it. And it unblocks something concrete: if
identification is adopted as a first-class criterion, **D79's E2 arm** — which drove M6's
partial-dependence inversions from 18.0% to 0.0% and moved the consensus RB1 from board rank 73 to
10, and was rejected on pool-wide MAE — becomes re-evaluable under a criterion that matches what the
draft actually consumes, using measurements already on disk.

Explicitly **not** recommended: inventing a Y4, re-running the arms on a widened population, or
carrying any arm from this phase to the draft benchmark.

## 17. Reproduction

```
uv run python scripts/research/d101_y_arm_identification.py --out <dir>
uv run pytest tests/unit/test_d101_y_arm_identification.py
# board vintage: ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99
```

The harness opens the database read-only, imports the shipped arm definitions, estimator and gate
evaluator, and writes nothing but its JSON artifacts. `--verify` (on by default) re-derives
`measure_arm`'s own metrics from the retained predictions and aborts on any disagreement, so the
identification layer cannot silently drift away from the fit the gates describe.
