# D87 — Does a candidate shortlist preserve O1's decisions?

*A controlled replication / computational-efficiency experiment. Not a new objective.
`models/` and `league/` are **byte-identical to Y1** throughout. Shortlist parameter committed at
`4254455`.*

---

## 1. Repository / baseline status

| check | result |
|---|---|
| working tree | clean |
| HEAD | `7752e25` (D86 results), 6 commits ahead of `origin/main` |
| `origin/main` | `b9c389d` (D85 merge) — D86 is not yet merged |
| `league/` + `models/` vs `origin/main` | **byte-identical to Y1** |
| D86 evaluation code | present (`draft_oracle.py`, `weekly_objective.py`, `objective_candidates.py`) |
| D86 result artifacts | present and reusable (`otiers2.json`, 80 drafts) |
| database | intact (231 MB, unchanged since the D86 rebuild) |
| test suite | 1252 passing at D86 HEAD |

---

## 2. D86 O1 baseline — and a discrepancy in the D87 premise

### 2.1 The exact objective (unchanged)

```
O0 (= Y1 control):  value_base = MSV                        + 1.0 × daVORP
O1:                 value_base = E[weekly MSV]              + 1.0 × daVORP

score = (value_base + opportunity_cost) × roster_fit × confidence × survival × [cap]
```

`E[weekly MSV]` = `expected_weekly_marginal_value`: the same marginal-lineup question asked under
**measured** per-position availability (QB 88.2%, RB 85.3%, WR 86.1%, TE 87.3%, K 93.6%,
DST 94.0%), rates measured on seasons strictly **before** the drafted season, 200 common-random-
number draws. Everything else — daVORP, opportunity cost, roster fit, confidence, survival,
capacity, legality, the draft loop, the metrics, the gates — is production's, unchanged.

### 2.2 The discrepancy — diagnosed before anything was run

The D87 brief states:

> Y1 ~0.03 s/pick · **O1 K=40 ~6.26 s/pick** · **O1 K=10 ~0.51 s/pick**

**Both O1 rows are mislabelled.** Verified three independent ways:

1. **The code.** `_pick_by_tier` scores `for player_id in available` — the entire remaining
   board. There is no shortlist anywhere in the evaluated path.
2. **The D86 artifact** (`otiers2.json`, the run that produced +52.9): O0 **0.028 s/pick**,
   O1 **5.716 s/pick** — consistent with a full board, not with 0.51.
3. **D86's own cost table** (`DRAFT_OBJECTIVE_RESEARCH.md` §13): O0 0.03 s; O1 **full board
   (596 candidates)** 6.26 s; O1 **K=40 shortlist** 0.51 s.

| brief says | actually is |
|---|---|
| "O1 K=40 = 6.26 s/pick" | O1 **full board** = 6.26 s/pick |
| "O1 K=10 = 0.51 s/pick" | O1 **K=40 shortlist** = 0.51 s/pick |

**K=10 was never tested in D86.** The Ks probed were 20 (0.26 s), 40 (0.51 s), 80 (1.07 s) and
160 (2.05 s), and only as a per-pick cost probe — never as a historical arm.

Nothing is internally inconsistent: code, artifact and report all agree with each other. The
mislabel is in the brief's summary. But the consequence matters: **there is no "O1-K40"
historical baseline to replicate.** The D86 result (+52.9 target / +1.6 legacy) belongs to
**O1-FULL**.

### 2.3 Resolution adopted

Run the efficiency experiment against the **correct** baseline, and include the K the brief
believed was the baseline so nothing is lost:

| arm | what it is | D86 status |
|---|---|---|
| **O0** | Y1 control | evaluated |
| **O1-FULL** | the D86 evaluated arm — **the true baseline** | evaluated (+52.9 / +1.6) |
| **O1-K40** | the shortlist D86 cost-probed | cost only, never evaluated |
| **O1-K10** | the new arm under test | never tested |

O1's mathematics, the gates, the metrics, the period, the formats and the control are all
unchanged. The only thing that varies across the three O1 arms is **how many candidates the
expensive objective is evaluated on**.

### 2.4 Verified D86 results (reproduced from the artifact)

| format | metric | O0 | O1-FULL | Δ |
|---|---|---|---|---|
| target 1QB | weekly (no foresight) — primary | 1924.5 | 1977.3 | **+52.9** |
| target 1QB | season-long | 1967.1 | 2001.6 | **+34.5** |
| legacy 2QB | weekly (no foresight) | 2207.3 | 2208.8 | +1.6 |
| legacy 2QB | season-long | 2151.4 | 2170.8 | +19.3 |

---

## 3. Implementation (Phase 2)

`_pick_by_tier(shortlist_k=K)`: rank the whole board with the **cheap control scorer**, then
re-score only the top K under the expensive objective — exactly D86's Phase 14 procedure. `None`
scores the whole board and is the default, so every D86 number is reproduced by construction.

Isolated to evaluation code. Five tests pin it, including the sharp one: **at K=1 the arm
degenerates to the control's pick**, which is what makes any later "K=10 agrees with the full
board" a measurement rather than a tautology — the mechanism is demonstrably able to change a
pick.

**Control check.** The Phase 3 analysis derives each shortlist arm's pick as `argmax` of the
full-board O1 scores over the cheap top-K, rather than re-running. That derivation was checked
against a real `shortlist_k=K` call across 16 states (2 seasons × 4 roster depths × 2 Ks):
**16/16 identical**. So the equivalence numbers measure the arm, not the derivation.

---

## 4. K=10 equivalence (Phase 3) — 592 real pick states

Trajectory held fixed at O1-FULL's, so each number isolates the shortlist's effect on *that*
pick.

| format | K | contains the full-board pick | selects the same player | **changes the decision** |
|---|---|---|---|---|
| target 1QB | 40 | 94.1% | 94.1% | 5.9% |
| target 1QB | **10** | **89.7%** | **89.7%** | **10.3%** |
| legacy 2QB | 40 | 94.1% | 94.1% | 5.9% |
| legacy 2QB | 10 | 93.4% | 93.4% | 6.6% |

**The headline agreement rate is misleading.** Split by draft stage (target format):

| rounds | states | K=10 changes the decision |
|---|---|---|
| **1–7** | 140 | **0 (0.0%)** |
| **8–16** | 180 | **33 (18.3%)** |

K=10 is *perfectly* faithful early and *badly* unfaithful late — and late is exactly where O1's
mechanism operates.

### Where the changes go, and why

| O1-FULL took → K=10 took | n |
|---|---|
| TE → **K** | 13 |
| RB → **K** | 5 |
| TE → **DST** | 3 |
| WR → **DST** | 3 |
| other | 9 |

**In all 33 changed decisions the full-board pick was outside the cheap top-10** — median cheap
rank **205**, max 377. K=10 could not reach it.

The cause is structural, not incidental. The shortlist is ranked by the **cheap scorer, which is
Y1** — the engine D85 measured as over-valuing K by **5.34×** and DST by **8.10×**. So in the late
rounds the top-10 by Y1 score is saturated with kickers and defenses:

| round | QB in top-10 | RB | WR | TE | **K** | **DST** |
|---|---|---|---|---|---|---|
| 12 | 45% | 0% | 65% | 65% | **100%** | **95%** |
| 13 | 0% | 0% | 45% | 30% | **90%** | **100%** |
| 15 | 5% | 0% | 10% | 10% | **100%** | **100%** |
| 16 | 65% | 35% | 75% | 40% | **100%** | **100%** |

**The shortlist re-imports Y1's K/DST over-valuation into O1.** O1-K10 is structurally prevented
from expressing the very behaviour that made O1 interesting. Confirmed in the drafted counts
(target format): kickers per draft **Y1 3.70 → O1-FULL 2.60 → O1-K40 3.40 → O1-K10 3.25**.

---

## 5. Historical results (Phase 4)

### Target format (10-team 1-QB PPR), 5 seasons × 4 slots

| arm | weekly (no foresight) — primary | weekly (hindsight) | season-long | unfilled |
|---|---|---|---|---|
| O0 (Y1) | 1924.5 | 2100.5 | 1967.1 | 0 |
| **O1-FULL** | 1977.3 (**+52.9**) | 2175.2 (+74.7) | 2001.6 (+34.5) | 0 |
| O1-K40 | 1966.4 (**+41.9**) | 2147.7 (+47.2) | 1994.7 (+27.6) | 0 |
| O1-K10 | 1986.8 (**+62.3**) | 2176.8 (+76.3) | 2011.9 (+44.8) | 0 |

### Legacy 2QB dynasty

| arm | weekly (no foresight) | season-long |
|---|---|---|
| O0 (Y1) | 2207.3 | 2151.4 |
| **O1-FULL** | 2208.8 (**+1.6**) | 2170.8 (+19.3) |
| O1-K40 | 2201.1 (**−6.2**) | 2160.8 (+9.4) |
| O1-K10 | 2200.2 (**−7.1**) | 2157.0 (+5.5) |

### The margins are non-monotonic in K

    K=10  +62.3      K=40  +41.9      K=FULL  +52.9

More computation does **not** produce a better margin, and less does not produce a worse one.
A quantity that is not monotone in the amount of computation spent on it is not measuring the
computation. **These differences are noise**, and that reading is corroborated by the absence of
any mechanism: O1-K10 scores highest while drafting *more* kickers than O1-FULL — the opposite of
the mechanism O1's gain was attributed to.

---

## 6. Gate results (Phase 4) — D86's gates, unchanged

### Target format

| arm | margin | clustered 95% CI | worse | G2 | G3 | G6 | G8 | G9 | G10 |
|---|---|---|---|---|---|---|---|---|---|
| O1-FULL | +52.9 | [−8.3, +114.0] | 1/5 | ok | ok | ok | **FAIL** | ok | ok |
| O1-K40 | +41.9 | [−21.5, +105.4] | 1/5 | ok | ok | ok | **FAIL** | ok | ok |
| O1-K10 | +62.3 | **[+16.1, +108.6]** | 0/5 | ok | ok | ok | **ok** | ok | ok |

### Legacy 2QB dynasty

| arm | margin | clustered 95% CI | worse | G3 | G6 | G8 | G9 |
|---|---|---|---|---|---|---|---|
| O1-FULL | +1.6 | [−56.9, +60.1] | 2/5 | FAIL | FAIL | FAIL | FAIL |
| O1-K40 | −6.2 | [−70.9, +58.6] | 2/5 | FAIL | FAIL | FAIL | FAIL |
| O1-K10 | **−7.1** | [−70.6, +56.5] | 2/5 | FAIL | FAIL | FAIL | FAIL |

### G7 — the cross-format gate, which decides it

> *"rerun unchanged on `legacy_2qb_dynasty`; a candidate that only helps in the target format is
> a format artifact, not a fix"*

| arm | target | legacy | G7 |
|---|---|---|---|
| O1-FULL | +52.9 | **+1.6** | sign held — **ok** |
| O1-K40 | +41.9 | **−6.2** | **FAIL — sign flip** |
| **O1-K10** | **+62.3** | **−7.1** | **FAIL — sign flip** |

**O1-K10 passes every target-format gate and then fails G7.** It is the *only* arm whose margin
changes sign across formats — the exact failure mode D86's O1-FULL avoided and that G7 exists to
catch. The shortcut made the candidate **worse** on the criterion that distinguishes a fix from a
format artifact.

**Nothing ships.**

---

## 7. Behavioural results (Phase 5)

Target format, mean first round and count per draft:

| arm | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nRB | nTE | **nK** | nDST | unfilled |
|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 (Y1) | 2.30 | 4.25 | 1.70 | 6.35 | 7.90 | 9.95 | 2.10 | 1.90 | **3.70** | 2.05 | 0 |
| **O1-FULL** | 2.30 | 4.25 | 1.70 | 6.55 | 7.80 | 10.45 | **2.50** | **2.85** | **2.60** | 2.00 | 0 |
| O1-K40 | 2.30 | 4.25 | 1.70 | 6.55 | 7.80 | 10.45 | 2.15 | 2.35 | **3.40** | 2.05 | 0 |
| O1-K10 | 2.30 | 4.25 | 1.70 | 6.50 | 7.70 | 9.95 | 2.10 | 2.25 | **3.25** | 2.05 | 0 |

Early-round timing is identical across all four arms — consistent with 0% decision change in
rounds 1–7. The entire behavioural difference is late, and **the shortlist arms lose most of
O1-FULL's K reduction** (2.60 → 3.25/3.40, against Y1's 3.70) and most of its added RB and TE
depth.

**Roster legality survives everywhere: 0 unfilled mandatory slots in all four arms, both
formats.** The specific risk that a 10-candidate shortlist would strand a required position did
not materialise — but only because Y1 ranks K/DST so highly that they are *always* reachable. The
shortlist is safe for legality for the same reason it is unfaithful for valuation.

---

## 8. 2026 results (Phase 6) — slot 1

At **#1, #20 and #21 all four arms select the identical player**, because the full-board O1 pick
is also the cheap ranking's #1 at each:

| pick | all arms | O1 score | rank in cheap ranking |
|---|---|---|---|
| #1 | Amon-Ra St. Brown (WR) | 526.3 | 1 |
| #20 | Josh Allen (QB) | 261.4 | 1 |
| #21 | Trey McBride (TE) | 294.8 | 1 |

First divergence from O1-FULL: **O1-K40 at round 15**, **O1-K10 at round 11**.

Final 2026 compositions:

| arm | WR | QB | TE | RB | **K** | DST |
|---|---|---|---|---|---|---|
| Y1 (O0) | 5 | 1 | 2 | 2 | **4** | 2 |
| **O1-FULL** | 5 | 1 | **3** | **3** | **2** | 2 |
| **O1-K10** | 5 | 1 | 2 | 2 | **4** | 2 |

**O1-K10's 2026 roster is composition-identical to Y1's, four kickers included.** The one
concrete, defensible improvement D86 produced — "take the kicker you need, then stop" — is
entirely absent under K=10.

No elite RB, WR, QB or TE was lost at the top of the board: positions reachable in the cheap
top-10 at #1/#20/#21 covered every position that mattered there. The loss is confined to the
endgame.

---

## 9. Computational cost (Phase 7)

Measured inside this run (40 drafts per arm per format, same environment):

| arm | s/pick | s/draft | vs Y1 | candidates scored/pick |
|---|---|---|---|---|
| O0 (Y1) | **0.028** | 0.4 | 1.0× | whole board |
| O1-FULL | **4.972** | 79.6 | **179.6×** | ~600 |
| O1-K40 | **0.408** | 6.5 | 14.7× | 40 |
| O1-K10 | **0.131** | 2.1 | **4.7×** | 10 |

All three O1 arms are fast enough for a live draft (a single recommendation in ≤ 5 s even at full
board). **Computational feasibility was never the binding constraint** — a real draft pick has
minutes, not milliseconds. What K buys is throughput for *research* runs, and that is where it
costs fidelity.

Memory is unchanged; the estimator is reproducible across processes by construction.

---

## 10. Ship / do not ship

**DO NOT SHIP. Y1 remains production. `league/` and `models/` are byte-identical to Y1 and no
production diff was prepared, because no arm passed.**

* **O1-K10** — passes all target-format gates, then **fails G7** (+62.3 → −7.1, the only arm to
  flip sign). Not shippable, and not a faithful approximation.
* **O1-K40** — fails G8 and G7.
* **O1-FULL** — fails G8, exactly as in D86. Unchanged.

---

## 11. Interpretation

**A. Does K=10 adequately reproduce O1-FULL?**
**No.** 89.7% same-pick overall conceals 100% agreement in rounds 1–7 and 82% in rounds 8–16. The
disagreements are systematic, not random: they occur only where the full-board pick sits outside
the cheap top-10 (median cheap rank 205), and they overwhelmingly substitute a K or DST for a
TE/RB/WR. Because the shortlist is ranked by Y1 — which over-values K 5.34× and DST 8.10× — K=10
re-imports the exact pathology O1 exists to remove. On the 2026 board it reproduces Y1's roster
composition exactly.

**B. Is O1 computationally feasible without materially changing its decisions?**
Yes, but **not via K=10**. At full board O1 costs 5 s/pick, which is already fine for a live
draft. K=40 costs 0.41 s and changes 5.9% of decisions; K=10 costs 0.13 s and changes 10.3%,
concentrated where it matters. **Feasibility never required a shortlist.**

**C. Does O1 still justify further research?**
**Weakly yes, and less than before.** O1-FULL remains the only arm holding its sign across
formats, and it improves both metrics in the target format. But D87 adds a caution: the margins
are **non-monotonic in K** (+41.9 / +52.9 / +62.3), which means differences of this size in this
instrument are noise. D86 already showed the reachable structural headroom (~90 points) is below
the benchmark's resolution (~128). D87 does not change that arithmetic.

**D. Does anything here justify replacing Y1?**
**No.** The one arm that passed a gate set passed it in one format and flipped sign in the other,
with no mechanism to explain the gain and non-monotonic behaviour in the parameter under test.
That is precisely the pattern this project has declined to ship eight previous times.

**E. Highest-value next research question?**
Unchanged from D86 in substance, but **D87 has materially corrected how to do it.** D86's
recommendation was to re-run O1 at the full 10 slots for statistical power, and the obvious way to
afford that was the K=40 shortlist. **D87 shows that would have measured a different policy** —
K=40 loses most of O1's K-reduction (2.60 → 3.40) and flips sign in the legacy format. So:

> **Re-run O1-FULL — no shortlist — at the full 10 slots, both formats.** At 79.6 s/draft that is
> ~2.2 h per format, which is affordable. Any shortlist must be validated against the full board
> *for the behaviour under test*, not merely against the selected player, before it is used to buy
> power.

The secondary finding worth carrying forward: **a shortlist built from a biased cheap scorer
inherits that bias**. If a shortlist is ever wanted, it must be ranked by something other than the
engine whose pathology the expensive objective is meant to correct.
