# D114 — Matched-state reanalysis of decision-layer effects

**Verdict, in one line: matched-state pairing is real but it is not a general power multiplier —
it resolved ECR's per-pick value to ±13 points and closed it, while the same treatment's
whole-draft effect stayed unresolved at ±83/±238. D113's tight intervals came from an inert
treatment, not from the pairing.**

**Experiment 2 (D97 PROD vs NAIVE) was NOT run. The NAIVE arm has never existed in this
repository's history and rebuilding it would be inventing a naive system, which the brief
forbids. D114 stops there and substitutes nothing.**

**ECR: CLOSED as a per-pick decision signal.** Its one-step value is **+1.32 points per pick
state in `target_league`** (95% CI [−12.1, +14.7]) and **−4.69 in `dynasty_1qb`** (CI [−17.4,
+8.1]). Both intervals lie entirely inside the ±25-point economic threshold, so an economically
meaningful per-pick effect is *excluded*, not merely undetected. Conditional on ECR actually
changing the pick it is 176 better / 149 worse (target) and 195 better / 212 worse (dynasty) — a
coin flip, in opposite directions by format.

**No production change. No ECR weight introduced, searched or tuned. No PR. Nothing merged.**
`src/alpha_squad/` is byte-identical to D108.

---

## 1. Plain-English conclusion

D113 found a decision-layer contrast whose interval was 4–16× tighter than the program's
172–250-point floor, and asked whether the *pairing* did that. **It did not.** The pairing that
mattered in D113 was that the capacity treatment barely moved the draft — it changed 0.7–2.6 of
16 roster slots and never diverged before round 10. ECR changes **8.4–10.5 of 16 slots and
diverges at round 1.7**, and its whole-draft interval is correspondingly wide: MDE **83.4**
(target) and **238.3** (dynasty), squarely in and above D97's band.

What the matched-state design *does* buy is a different, sharper question. Asking "what is ECR's
advice worth at **one** pick, with production playing every other pick" has an MDE of **13
points** — about a tenth of the ~135-point per-pick regret the oracle leaves on the table. On
that question ECR is answered: it is worth approximately nothing, and its sign flips between
formats.

So the old floor was **not** universally conservative. It was conservative for low-divergence
treatments and roughly correct — even optimistic — for high-divergence ones. The replacement rule
is not a new constant: **every contrast must report its own MDE, and the driver is how much of
the roster the treatment moves.**

---

## 2. Repository and vintage audit (the brief's steps 1–6), run before any measurement

`--mode audit`, output committed as the first thing D114 did.

| item | value |
|---|---|
| HEAD | `392066b42d1d9a398d65be50f882b7abf7bdb80b` — "D113: capacity has D112's leverage…" |
| branch | `claude/alpha-capacity-audit-prgn6s` (D91–D108 stack + D113 + D114) |
| board vintage, combined 2021–2025 | `0d52543044fe99d6d03a7592190c070bde36a6f465041e2304acdab5b35891e0` |
| per season | 2021 `40a000b3…` 2022 `139658bf…` 2023 `5f64d6c1…` 2024 `6bea3ee6…` 2025 `e7a115a3…` |
| vintage D103/D104/D105 recorded | `ca3e2d8af6aa892067c7450095a1c992087f613141e3b36b89b12928713d5f99` |
| **match** | **NO** |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| uncertainty model | `uncertainty_catboost_v2` |

### 2.1 Experiment 1 (ECR) — reconstructible

`scripts/research/d104_ecr_floor.py::ecr_ordered_static` is committed and tested
(`tests/unit/test_d104_ecr_floor.py`). D114 **imports** it rather than reimplementing it; a test
asserts the import resolves to that file and that D114 defines no substitution of its own.
**There is no ECR weight anywhere to retune**: the arm is a within-position rank permutation of
Y1's own value multiset, so replacement levels, scarcity and the positional value scale are
unchanged by construction. A test also forbids the strings `ecr_weight`, `WEIGHT_GRID`,
`for weight in` and `np.linspace` from the runner.

### 2.2 Experiment 2 (D97 PROD vs NAIVE) — **NOT reconstructible. STOP.**

Three independent repository queries, run by the audit itself rather than asserted:

| query | result |
|---|---|
| `git log --all -S NAIVE -- '*.py'` | **empty** — no commit on any branch ever added a NAIVE arm |
| `git log --all --diff-filter=A --name-only -- '*d97*'` | **empty** — no `d97*` file was ever added |
| `git log --all --diff-filter=D --name-only -- 'scripts/*'` | **empty** — no script was ever deleted |
| `grep -ril naive src/ scripts/` | hits are prose about "naive intervals", never an arm |

D97's own record says the phase ran "no experiment beyond the decomposition", and D107 §G lists
uncommitted runners as the reason "everything before D92 is unreproducible". `NAIVE` —
"projection over static replacement (classic VBD)" plus "the same endgame mandatory-slot rule" —
exists **only as prose in `docs/DECISIONS.md`**. The closest committed things are `alpha_bpa`
(raw projections, no VBD) and `homogeneous_league_draft`'s `"vorp"` helper (no fair opponent, no
endgame rule); neither is D97's arm, and the endgame mandatory-slot rule is carried only by the
W/L legality tiers, which the shipped engine does not use.

Rebuilding it would mean choosing a replacement definition, an endgame rule and a tie-break from
prose — **inventing a naive system**. The brief forbids that. **Experiment 2 is reported as
unreconstructible and no substitute is run.** A test (`test_no_naive_arm_exists_in_the_checkout`)
fails the day a NAIVE arm is added, which is the correct trigger to revisit this.

### 2.3 The vintage differs — and the ECR experiment survives it

Rule 6 forbids mixing vintages without labelling. Every number below is **CURRENT-VINTAGE**
except where explicitly marked HISTORICAL. To quantify what the vintage shift costs, D114 first
re-ran **D104's own committed runner, unmodified**, on its own grid:

| contrast | D104 published (HISTORICAL `ca3e2d8a…`) | D114 re-run (CURRENT `0d525430…`) |
|---|---|---|
| `target_league` Y1 → FP_ECR_Y1 | **+77.3** CI [−44.1, +198.6] t=1.77, 5W/0L | **+64.5** CI [−18.9, +147.9] t=2.15, 4W/1L |
| `dynasty_1qb` Y1 → FP_ECR_Y1 | **−132.1** CI [−371.1, +107.0] t=−1.53, 1W/4L | **−153.9** CI [−392.2, +84.4] t=−1.79, 1W/4L |
| `target_league` Y1 → ORACLE_Y1 | +795.3 (D107's identified form) | **+783.6** CI [+574.0, +993.3] |
| `dynasty_1qb` Y1 → ORACLE_Y1 | +717.0 | **+726.9** CI [+500.7, +953.0] |

**The experiment reconstructs in substance.** Every sign, every verdict and every season pattern
survives; the point estimates move by 13 and 22 points against intervals 170–480 points wide.
The one qualitative change is target-format season consistency, 5W/0L → 4W/1L (2024 flips to
−26). So: the *procedure* is exactly reconstructible, the *numbers* are not bit-identical, and
the difference is small relative to the uncertainty. Cross-vintage magnitude comparisons are
labelled throughout; **the design comparison that answers D114's question is run entirely within
the current vintage and is unaffected.**

---

## 3. Matched-state methodology

Both arms are the shipped Y1 decision rule (`SHIPPED_TIER = "L0"`, pinned byte-identical to
`recommend_draft_pick` by `TestShippedTierIsProduction`). **Only the projections the rule reads
differ.** Two estimators, same grid, same vintage, same fair
`market_consensus_roster_aware` opponents, same snake geometry:

**ESTIMATOR 1 — FREE-RUN** (D104's design). Each arm plays its own complete draft from the same
start. Estimand: *the value of adopting ECR for the whole draft.*

**ESTIMATOR 2 — ONE-STEP (matched state)** — the new instrument, built on D103's committed
`draft_oracle.rollout`. The control draft is played by the shipped engine on Y1's board. At each
of our pick states `s`:

```
y1_pick  = production's pick at s
ecr_pick = the SAME rule's pick at s when it reads the ECR-ordered board
if identical                -> delta(s) = 0, exactly, by construction
else  V_T(s) = rollout(after ecr_pick, continuation = SHIPPED policy on Y1's board)
      V_C(s) = rollout(after y1_pick,  continuation = SHIPPED policy on Y1's board)
      delta(s) = V_T(s) - V_C(s)
```

Everything except one pick is shared: same season, league, slot, starting roster, available pool,
opponents, and continuation policy. Estimand: *the value of taking ECR's advice at exactly one
pick.* This is the quantity Alpha's stated objective names — realized value from an individual
draft pick.

**Validity.** `V_C(s)` is recomputed through the *same* `rollout` call as `V_T(s)` rather than
reused from the control draft, and the runner raises `UnreconstructibleError` if it disagrees
with the control draft's own value. Across **1,600 matched pick states and ~2,000 rollout pairs**
it never fired — the harness demonstrably resumes production's own draft.

**The two estimators are never summed into each other.** One-step deviations are not additive:
each is measured against the same unchanged trajectory, so Σδ(s) is not the free-run effect and
is nowhere reported as one.

Population: seasons 2021–2025 (2020 refused, D95/D96); formats `target_league` and `dynasty_1qb`
(exactly D104's, reported separately, never pooled); slots 1–10 for both estimators, with D104's
(1, 4, 7, 10) reported as the **pre-registered common grid** so design rather than sample size is
what differs. Independent unit = season, k = 5, t_crit = 2.776.

**Pre-registration honesty note.** The decision rule (A/B/C and the 25-point economic threshold)
comes from D114's brief, not from D114. The runner's pre-registration block was written before
any D114 estimator ran, but — unlike D113 — it was **not committed before the run**; it was
committed with the results. The D104 replication in §2.3 *had* been seen when the runner was
written. No rule was changed after seeing an estimator result, and `_classify` is mechanical and
tested.

---

## 4. ECR result

### A/B. Matched pick states and how many differ

| format | matched pick states | changed | % changed | D104's published churn |
|---|---|---|---|---|
| `target_league` | **800** | **448** | **56.0%** | 57–64% |
| `dynasty_1qb` | **800** | **544** | **68.0%** | 57–64% |

Free-run rosters: **0 of 50 identical** in both formats; **8.44 / 10.46 of 16 players differ**;
mean first divergence round **1.9 / 1.7** (minimum 1). ECR is the opposite of an inert treatment.

### C. Realized value at the changed pick — and why it is the wrong number

| format | raw realized Δ at changed picks | one-step **roster-value** Δ | conversion |
|---|---|---|---|
| `target_league` | **+9 742.4** | **+1 056.7** | **10.9%** |
| `dynasty_1qb` | **−8 489.6** | **−3 752.8** | 44.2% |

At **60** target-format picks ECR's player outscored Y1's *and the roster got worse*; the reverse
happened at 26. The mechanism is visible by position (target, changed picks):

| position | Y1 gave up | ECR took | roster-value Δ | raw realized Δ |
|---|---|---|---|---|
| **K** | 0 | **135** | **−3 678.0** | **+1 282.4** |
| QB | 66 | 50 | −24.6 | +3 172.2 |
| DST | 0 | 42 | +1 343.5 | +125.8 |
| RB | 147 | 43 | +908.0 | +851.9 |
| TE | 87 | 57 | +1 106.7 | +1 763.3 |
| WR | 148 | 121 | +1 401.1 | +2 546.8 |

ECR took 135 kickers Y1 would not have, and those kickers scored **+1 282 raw realized points
while costing the roster 3 678**. That is D104 §11's own flagged confound — the substitution
re-orders skill positions while holding K/DST fixed, pulling the endgame toward kickers —
measured directly instead of inferred.

### D/E/F. Roster-level realized value

**ONE-STEP (matched state), per pick state — the primary matched-state result:**

| format | objective | effect | 95% CI | t | **MDE** | seasons | classification |
|---|---|---|---|---|---|---|---|
| `target_league` | season-long | **+1.32** | [−12.1, +14.7] | 0.27 | **13.37** | 3W/2L | **B — tight around zero** |
| | weekly no-foresight | −3.51 | [−12.5, +5.5] | −1.08 | 9.01 | 2W/3L | **B — tight around zero** |
| `dynasty_1qb` | season-long | **−4.69** | [−17.4, +8.1] | −1.02 | **12.75** | 2W/3L | **B — tight around zero** |
| | weekly no-foresight | −0.61 | [−15.4, +14.1] | −0.11 | 14.75 | 2W/3L | **B — tight around zero** |

Conditional on the pick actually changing: target **+2.38** CI [−20.9, +25.7] (176 better / 149
worse / 123 equal); dynasty **−7.57** CI [−27.1, +11.9] (195 better / 212 worse / 137 equal).

**FREE-RUN (adopt ECR), per draft:**

| format | grid | objective | effect | 95% CI | t | **MDE** | seasons | drafts | classification |
|---|---|---|---|---|---|---|---|---|---|
| `target_league` | 1,4,7,10 | season-long | **+64.5** | [−18.9, +147.9] | 2.15 | **83.4** | 4W/1L | 15W/0T/5L | **C — unresolved** |
| | 1–10 | season-long | +64.1 | [−30.5, +158.6] | 1.88 | 94.6 | 4W/1L | 33W/0T/17L | C — unresolved |
| | 1–10 | weekly | +17.2 | [−79.3, +113.6] | 0.49 | 96.5 | 4W/1L | 30W/0T/20L | C — unresolved |
| `dynasty_1qb` | 1,4,7,10 | season-long | **−153.9** | [−392.2, +84.4] | −1.79 | **238.3** | 1W/4L | 7W/0T/13L | **C — unresolved** |
| | 1–10 | season-long | −167.6 | [−426.8, +91.6] | −1.79 | 259.2 | 1W/4L | 17W/0T/33L | C — unresolved |
| | 1–10 | weekly | −205.4 | [−464.0, +53.2] | −2.20 | 258.6 | 1W/4L | 9W/0T/41L | C — unresolved |

**F. The dynasty objective is reported separately throughout and never pooled with the target
objective.** It disagrees with the target format in sign under both estimators.

### G. By draft phase (one-step, season-long, mean Δ per state)

| phase | `target_league` states / changed / Δ | `dynasty_1qb` states / changed / Δ |
|---|---|---|
| EARLY 1–5 | 250 / 125 (50.0%) / **+3.11** | 250 / 171 (68.4%) / −2.08 |
| MIDDLE 6–10 | 250 / 119 (47.6%) / −0.40 | 250 / 165 (66.0%) / **−13.03** |
| LATE 11–16 | 300 / 204 (68.0%) / +1.26 | 300 / 208 (69.3%) / +0.08 |

ECR's only positive phase in the target format is EARLY (+3.11/state, +6.23 on changed picks) —
consistent with D103's finding that regret is concentrated early — but it is an order of
magnitude below the ~181 points of early regret the oracle captures there.

### H. By position — see §4.C. I. By season

One-step, season-long, per pick state:

| | 2021 | 2022 | 2023 | 2024 | 2025 | between-season SD |
|---|---|---|---|---|---|---|
| `target_league` | +17.17 | +4.82 | +1.38 | −10.85 | −5.92 | 10.77 |
| `dynasty_1qb` | +3.82 | −13.63 | −15.44 | −5.85 | +7.66 | 10.27 |

Free-run, season-long, per draft (common grid): target +79 / +66 / +43 / −26 / +160 (SD 67.2);
dynasty +56 / −106 / −385 / −321 / −13 (SD 192.0).

### J/K/L/M. Intervals, MDE, direction, and whether it is precise enough

**L — direction: effectively zero, with a sign that flips by format.** +1.32 vs −4.69 per pick
state; +64.5 vs −153.9 per draft.

**M — precise enough?** For the per-pick question, **yes**: MDE 12.75–13.37 against a per-pick
action space where a single ECR swap moves final roster value with SD **69.5 / 80.3** and mean
|Δ| **46.6 / 51.6** (target range −239 to +345; dynasty −427 to +199), and against the oracle's
**134.8**-point mean per-pick regret (D103, HISTORICAL vintage). The estimator can resolve roughly **10% of the oracle's
per-pick regret**; ECR captures **1.8%** of it. This is a real null, not a dead instrument.

For the whole-draft question, **no**: MDE 83.4–238.3 against an oracle gap of 783.6/726.9, i.e.
it resolves 11–33% of the available headroom and cannot bound an effect of economic size.

**Reconciliation of the two estimators** (a heuristic, not an identity — one-step deviations are
not additive): 16 × (+1.32) = **+21** versus free-run **+64.5** CI [−18.9, +147.9]; 16 × (−4.69)
= **−75** versus **−153.9** CI [−392.2, +84.4]. Both sit comfortably inside the free-run
intervals. The two designs are consistent with "each ECR substitution is worth about nothing, and
the whole-draft point estimate is mostly noise."

---

## 5. PROD vs NAIVE result

**Not run.** See §2.2. The arm does not exist and cannot be rebuilt without inventing it.

The brief's underlying question — *does matched-state methodology materially improve our ability
to measure the contribution of the decision engine?* — is answered with the evidence D114 does
have, and the answer is **partially, and not in the way the framing assumed**:

* It **does** make a new, tighter question answerable: per-pick value, resolvable to ±13 points.
  For a decomposition like PROD vs NAIVE, the one-step form ("what is Y1's pick worth at this
  state versus VBD's, with a common continuation") would very likely resolve where the
  whole-draft form could not, because the estimand is smaller and the branches share everything
  but one pick.
* It does **not** lower the floor on the whole-draft estimand. D114's ECR free-run MDE (83.4,
  238.3) is in and above D97's band on the same k = 5 clusters, and widening from 4 slots to 10
  made it *worse* (83.4 → 94.6; 238.3 → 259.2), exactly as D88 predicted — seasons bind, not
  slots.
* So a matched-state PROD-vs-NAIVE would measure **a different quantity** from D97's +213.8, and
  would not "re-resolve" it. Anyone rebuilding it must say which of the two they mean.

---

## 6. Comparison with the original D104 / D97 findings

| finding | original | D114 | status |
|---|---|---|---|
| ECR whole-draft, target | +77.3 [−44.1, +198.6], 5W/0L (D104, HISTORICAL) | +64.5 [−18.9, +147.9], 4W/1L (CURRENT) | **replicates in substance**; 2024 flips |
| ECR whole-draft, dynasty_1qb | −132.1 [−371.1, +107.0], 1W/4L (D104) | −153.9 [−392.2, +84.4], 1W/4L | **replicates** |
| ECR pick churn | 57–64% (D104) | 56.0% / 68.0% | **replicates** |
| "ECR damage is concentrated LATE and at TE/K/DST" (D104 §11) | inferred from per-arm regret | **measured directly**: ECR takes 135 extra kickers worth −3 678 roster value | **confirmed and sharpened** |
| ECR per-pick value | not measured | **+1.32 [−12.1, +14.7] / −4.69 [−17.4, +8.1]** | **new; closes the question** |
| "Identifies better players ≠ produces better picks" (D104 §6) | whole-draft evidence | conversion **10.9%**; 60 picks better-player-worse-roster | **confirmed at pick level** |
| `PROD − NAIVE` = +213.8 (D97) | — | **unreconstructible** | **cannot be revisited** |
| "The 172–250 floor cannot be lowered" (D97 §6 / D107 §G) | asserted as universal | **false as stated, and false in both directions** | **corrected — see §7** |

---

## 7. Was the 172–250 floor overly conservative for these paired experiments?

**It was not a floor at all. It is a function of how much the treatment moves the roster**, and
D113 and D114 bracket it from both sides — same seasons, same slots, same formats, same
opponents, same vintage, same objective, k = 5 in every row:

| contrast | mean roster slots moved (of 16) | first divergence round | between-season SD | **own MDE** | vs 172–250 |
|---|---|---|---|---|---|
| D113 capacity, `dynasty_1qb` | **0.70** | 13.6 | 12.5 | **15.5** | 11–16× tighter |
| D113 capacity, `legacy_2qb_dynasty` | 2.60 | 12.7 | 14.4 | 17.9 | 10–14× tighter |
| D113 capacity, `target_league` | 1.64 | 13.5 | 37.8 | 46.9 | 4–5× tighter |
| **D114 ECR, `target_league`** | **8.44** | **1.9** | 76.2 | **94.6** | inside the band |
| **D114 ECR, `dynasty_1qb`** | **10.46** | **1.7** | 208.8 | **259.2** | **above the band** |

Monotone within each format, and spanning a **17×** range in MDE on identical statistical
machinery. D107 §G's "the detection floor is 172–250 and cannot be lowered" is therefore wrong as
a universal: it is far too conservative for a late, narrow treatment and slightly too *generous*
for a broad one.

**The replacement standard, which is a procedure rather than a number:**

1. Report every contrast's **own MDE** (the CI half-width at k = 5) alongside its effect. Never
   quote a program-wide floor.
2. Report **how much of the roster the treatment moves** (players differing, first divergence
   round) next to the MDE — it is the leading indicator of power.
3. When the whole-draft estimand is unresolvable, state whether the **one-step estimand** is the
   question actually being asked. For Alpha's stated objective it usually is.
4. Adding slots does not help (83.4 → 94.6 and 238.3 → 259.2 going from 4 seats to 10). Seasons
   bind — D88's finding, re-confirmed here on a new treatment.

---

## 8. What effect size this methodology can actually resolve

| design | estimand | MDE | the oracle's scale for that estimand | fraction resolvable |
|---|---|---|---|---|
| ONE-STEP, target | value of ECR's advice at one pick | **13.4** | 134.8 mean per-pick regret (D103, HISTORICAL) | **~10%** |
| ONE-STEP, dynasty_1qb | same | 12.8 | — | — |
| FREE-RUN, target | value of adopting ECR | **94.6** | 783.6 (Y1 → ORACLE_Y1, CURRENT) | **~12%** |
| FREE-RUN, dynasty_1qb | same | 259.2 | 726.9 | ~36% |

Two things follow. First, **in relative terms the two designs resolve about the same fraction of
their own oracle (~10–12% in the target format)** — the one-step estimator is more precise in
absolute points because the quantity is smaller, not because the pairing is magic. Second, the
25-point economic threshold is *inside* the one-step resolution (13 < 25) and *outside* the
free-run resolution (95 > 25): **economically meaningful per-pick effects are now measurable;
economically meaningful whole-draft effects still are not.**

---

## 9. Is ECR a credible small improvement, zero/closed, or unresolved?

**ZERO / CLOSED as a per-pick decision signal — the unit Alpha's objective is stated in.**
Decision rule B fires in both formats and on both objectives: the whole interval lies inside
±25 points. Reinforcing this, and independent of the interval:

* the sign **flips by format** (+1.32 target, −4.69 dynasty) under the one-step estimator and
  again under the free-run one (+64.5, −153.9);
* changed picks are **176 better / 149 worse** (target) and **195 better / 212 worse**
  (dynasty) — at or below chance;
* the free-run arm loses in **4 of 5 dynasty seasons**, and D104 found the same.

**It is not a credible small improvement and should not be preserved for combined-system
testing.** A component whose per-pick contribution is bounded within ±13 points and whose sign
depends on the format has nothing to contribute to a portfolio; combining it with other
components would import its format-dependence without importing any value.

**One honest qualification, stated rather than buried:** the *whole-draft adoption* question
remains formally **C — unresolved** (CI [−18.9, +147.9] target admits +148). D114 does not claim
to have excluded a large whole-draft ECR effect. It claims that the per-pick mechanism through
which such an effect would have to operate is measured and is approximately zero, that the
whole-draft point estimates are consistent with that (§4, reconciliation), and that the sign
disagreement across formats is evidence against a real positive effect. Closing ECR on the
per-pick evidence is a judgement, and the whole-draft interval is the reason it is a judgement
rather than a proof.

---

## 10. Recommended next research question

**Not another decision-layer component, and not PROD vs NAIVE.** The record now contains three
consecutive component measurements — capacity (+0.8 ± 47 per draft), ECR (+1.32 ± 13 per pick),
and per-position calibration (rejected on power, D99) — and a measured statement about why:
individual components are worth single-digit points against oracle gaps of 130 (per pick) and 780
(per draft).

> **Where does the ~135-point per-pick regret actually live, now that it can be measured to
> ±13?**
>
> D103 measured the oracle's per-pick regret but could only attribute it against *its own* arm.
> D114 shows the one-step estimator resolves ~10% of that regret, which is enough to decompose
> it. The question is: of the 134.8 points the oracle captures at an average pick, how much is
> reachable by **any** preseason-available ordering, how much requires a magnitude
> (calibration) change rather than an ordering change — the axis D107 §G lists as still live and
> that D105/D106's ordering ladder explicitly does not span — and how much is irreducible
> variance?

Concretely, and cheaply: run the one-step estimator over the arms that already exist
(`FP_ECR_Y1`, D99's calibration arms X2/X3, D105's perturbation ladder) against `ORACLE_Y1`'s
one-step choice, and report each arm's share of the per-pick regret it recovers, with its own
MDE. That is a decomposition rather than another ablation, it needs no new seasons, and every
arm in it is already committed.

**Second priority, explicitly lower.** If anyone does want D97's decomposition back, the correct
move is to **commit a NAIVE arm as an instrument with a test** — a named, reviewed definition —
and then measure it fresh under both estimators. That is building a new instrument, not
reconstructing D97, and the resulting number must not be compared to +213.8.

---

## 11. Reproduction, provenance, and what changed

```bash
uv run python scripts/research/d114_matched_state.py --mode audit   --out <dir>
uv run python scripts/research/d104_ecr_floor.py     --mode decomposition --out <dir>   # replication
uv run python scripts/research/d114_matched_state.py --mode freerun --out <dir>
uv run python scripts/research/d114_matched_state.py --mode onestep --slots 1,2,3,4,5,6,7,8,9,10 --out <dir>
uv run python scripts/research/d114_matched_state.py --mode report  --out <dir>
uv run pytest tests/unit/test_d114_matched_state.py
```

| item | value |
|---|---|
| HEAD at run time | `392066b42d1d9a398d65be50f882b7abf7bdb80b` |
| board vintage (combined, 2021–2025) | `0d52543044fe99d6d03a7592190c070bde36a6f465041e2304acdab5b35891e0` |
| matches D103/D104/D105's `ca3e2d8a…` | **NO** (§2.3 quantifies the cost) |
| upstream board / idmap sha256 | `e270d790…` / `36016b92…` |
| uncertainty model | `uncertainty_catboost_v2`; shipped tier `L0` |
| opponent field | `market_consensus_roster_aware` |
| grid | 2 formats × 5 seasons × 10 slots; **100 paired free-run drafts** (200 drafts played); **1,600 matched pick states, 992 changed, 1,984 rollout pairs** |

**Files changed by D114 — research only:**

| file | status |
|---|---|
| `scripts/research/d114_matched_state.py` | **new** — audit, both estimators, pre-registration |
| `tests/unit/test_d114_matched_state.py` | **new** — 28 tests |
| `docs/D114_MATCHED_STATE_REANALYSIS.md` | **new** — this report |
| `docs/DECISIONS.md`, `docs/PROJECT_STATE.md` | appended |
| `src/alpha_squad/**` | **unchanged — byte-identical to D108** |
| `scripts/research/d104_ecr_floor.py` | **unchanged** — re-run, not edited |
