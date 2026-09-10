# D85 — Separating economic valuation from roster legality

*Pre-registration: `src/alpha_squad/evaluation/decision_legality.py`, committed at `1212faa`
before any arm ran. Harness fix: `ab5a1aa`. Working scripts are diagnostic-only; `models/` and
`league/` are **byte-identical to Y1** throughout.*

---

## 1. Executive verdict

**DO NOT SHIP. Y1 remains production.** Every candidate fails the pre-registered gates, in every
format tested.

But the phase is not a null. It answers D85's primary question — *can Alpha separate economic
valuation from roster legality?* — with a clear **yes, and the separation is already complete**,
and it overturns the premise that motivated the question. Four findings, in order of importance:

1. **The two mechanisms were never entangled on this board.** D84 concluded the over-valuation
   was "load-bearing" — that pricing a kicker at 5.34× its surplus is what guarantees a kicker
   gets drafted at all. **That does not reproduce.** The corrected valuation produces **0
   infeasible rosters** here, against D84's 2. The legality constraint, verified to work, **never
   fires once in 800 real picks** under either valuation. Legality was not being bought by the
   over-valuation; it was never at risk.

2. **The corrected valuation does NOT reduce the decision layer's amplification of projection
   error.** `d(value_base)/d(proj) = 2.000` under Y1 **and under arm C**, at every position. Arm C
   subtracts a per-position *constant* (`R_p`); it fixes the level, not the slope. The only
   formulations with the economically correct unit slope are `daVORP` alone and
   `msv_over_replacement` alone — exactly the two already measured and rejected three times.
   **This is new; D84 attributed the 2× amplification to the double count and did not check
   whether its own correction removed it. It does not.**

3. **The mechanism generalises correctly across formats; the benefit does not.** Arm C defers QB
   in 1-QB (first QB 2.12 → 3.04) and leaves superflex untouched (1.56 → 1.54) — exactly what an
   economically valid formulation should do. But starter points are **+26.6 in the target format
   and negative in all three other formats** (−9.1, −4.4, −11.1). A sign flip on 3 of 3
   alternatives is disqualifying on its own.

4. **A silent harness defect was found and fixed before it could produce a false result.** The
   first D85 run had the L-tiers omitted from the draft-aware replacement dispatch, silently
   reverting every arm to the static level — the D65 defect D67 removed. It put the control 79
   points below its own known value. Caught by the pre-registered "L0 must equal Q0" check.

---

## 2. Phase 0 — baseline verification

Repository clean, `HEAD` at `9c7ed72`, branch identical to `origin/main`. Database rebuilt from
source (`make ingest … project-current-season`, all stages exit 0; the `projection-status` gate
passes with 610 established + 153 rookie + 74 K/DST rows, 837 players across all six positions).

`starters + bench == roster_size` holds (10 + 6 = 16). Consumption demand reproduces D84 exactly:
QB 2.2, RB 4.2, WR 5.8, TE 1.8, K 1.0, DST 1.0.

**Every reported behaviour reproduces on the production path** (2026 board, draft slot 1, whose
picks are 1, 20, 21, 40, 41, …):

| pick | round | player | pos | proj |
|---|---|---|---|---|
| 1 | 1 | Amon-Ra St. Brown | WR | 278.7 |
| **20** | **2** | **Josh Allen** | **QB** | **329.4** |
| 21 | 3 | Jeremiyah Love | RB | 243.9 |
| **80** | **8** | **Brandon Aubrey** | **K** | **182.4** |
| 81 | 9 | Tucker Kraft | TE | 145.2 |
| **100** | **10** | **SEA D/ST** | **DST** | **110.8** |

QB at #20, kicker in round 8, defense in round 10, WR first — all reproduce. The counterfactual
control was asserted equal to `recommend_draft_pick` at **all 16 picks**.

---

## 3. Phase 1 — mathematical diagnosis

### What each term is supposed to mean

* **`marginal_starter_value(c)`** — "how much would adding `c` improve *my* starting lineup."
  Baseline: **the lineup I have now**, i.e. an implicit **zero** for an empty slot.
* **`daVORP(c)`** — "how much better is `c` than the player at this position still freely
  available when the draft ends." Baseline: **`R_p`**, the consumption boundary.

### Are they different dimensions, or the same surplus twice?

**The same surplus, against different baselines.** Verified, not asserted: `msv(c) == proj(c)`
**exactly** whenever `c` fills an empty lineup slot — max deviation `8.5e-14` over all six
positions × four roster states. So for any candidate filling an empty slot,

```
value_base = msv + daVORP = proj + (proj − R) = 2·proj − R
```

which is not a sum of two dimensions of value. It is one surplus counted twice, once against 0
and once against `R`. Adding them is **not semantically valid**.

Amplification over the principled `proj − R` is `1 + proj/(proj − R)`, which diverges as
`R → proj`, so the flatter the position the worse it is. Measured at pick 1 on the 2026 board:

| pos | top proj | R | proj − R | 2·proj − R | amplification |
|---|---|---|---|---|---|
| DST | 110.8 | 95.2 | 15.6 | 126.4 | **8.10×** |
| K | 182.4 | 140.4 | 42.0 | 224.4 | **5.34×** |
| QB | 329.4 | 205.3 | 124.1 | 453.6 | 3.65× |
| TE | 197.8 | 119.7 | 78.0 | 275.8 | 3.53× |
| WR | 278.7 | 108.4 | 170.3 | 448.9 | 2.64× |
| RB | 276.7 | 96.0 | 180.7 | 457.5 | 2.53× |

DST and K reproduce D84 to two decimals; QB and TE swap order on the rebuilt board.

### The economically correct formulation — and why it cannot be had

The correct quantity is the surplus over the best alternative still obtainable:
`msv_over_replacement`, which reduces to `proj − R` on an empty roster and to `0` at a saturated
position. **It has unit slope in the projection.**

The decisive new measurement:

| value base | at an empty slot | `d/d(proj)` |
|---|---|---|
| Y1 `msv + daVORP` | `2·proj − R` | **2.000** |
| arm C `msv_over_repl + daVORP` | `2·proj − 2R` | **2.000** |
| `daVORP` alone | `proj − R` | 1.000 |
| `msv_over_repl` alone | `proj − R` | 1.000 |

Measured by finite difference at every position — all exactly 2.000 / 1.000. **Arm C removes the
double count of the *level* and preserves the double count of the *slope*.** `Y1 − armC = R_p`
exactly, at every projection: a per-position constant, structurally the same shape D67 rejected
in D66's uniform multiplier, differing only in that this constant is derived rather than tuned.

So there is a genuine trilemma, and it is the reason eight reformulations have now failed:

* keep the D63 scale (which the opportunity-cost term, denominated in static VORP, is calibrated
  against) → keep slope 2;
* take unit slope → halve the value base against a fixed opportunity cost → that is Z1/Z2/Z3,
  measured and lost;
* there is no third option inside `(value_base + oc) × multipliers`.

---

## 4. Phase 2 — QB #20 diagnosis

State: roster `[Amon-Ra St. Brown]`, pick #20, **next pick #21 — a snake turn, so every
opportunity cost is exactly 0.**

| player | pos | proj | R | MSV | daVORP | value base | oc | fit | risk | surv | score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Josh Allen** | QB | 329.4 | 205.3 | 329.4 | 124.1 | **453.6** | 0.0 | 1.10 | 0.68 | 1.00 | **340.8** |
| Jeremiyah Love | RB | 243.9 | 96.0 | 243.9 | 147.9 | 391.8 | 0.0 | 1.20 | 0.70 | 1.00 | 329.1 |
| Zay Flowers | WR | 213.4 | 108.4 | 213.4 | 105.0 | 318.4 | 0.0 | 1.10 | 0.72 | 1.05 | 265.0 |
| Trey McBride | TE | 197.8 | 119.7 | 197.8 | 78.0 | 275.8 | 0.0 | 1.10 | 0.78 | 1.04 | 246.5 |

Allen's **true** marginal value is `proj − R = 124.1`. The engine credits **453.6** — 3.65×.
Note that Love has the *larger* honest surplus (147.9 vs 124.1) and still loses, because the
double-counted raw projection (329.4 vs 243.9) dominates. That is the mechanism in one row.

**What causes QB to win:** removing the raw-projection half is sufficient and nothing else is.
Under arm C the value bases become Allen 248.3 / Love 295.8, and **the pick flips to Love**.

---

## 5. Phase 3 — K/DST diagnosis

At **#80** (roster of 7, snake turn, oc = 0):

| player | pos | proj | R | MSV | daVORP | value base | score |
|---|---|---|---|---|---|---|---|
| **Brandon Aubrey** | K | 182.4 | 140.4 | 182.4 | 42.0 | **224.4** | **172.8** |
| Tucker Kraft | TE | 145.2 | 119.7 | 145.2 | 25.5 | 170.7 | 158.8 |
| SEA D/ST | DST | 110.8 | 95.2 | 110.8 | 15.6 | 126.4 | 97.3 |
| Courtland Sutton | WR | 197.7 | 108.4 | **11.8** | 89.3 | 101.1 | 82.7 |

Reproduces D84's 224.5 / 172.8 to a decimal.

**Why they win early.** Sutton is the tell: his projection is *higher* than Aubrey's (197.7 vs
182.4) but his MSV is **11.8**, because the WR slots are nearly full. Aubrey's MSV is his full
182.4 because the K slot is empty. **MSV does not measure quality; it measures slot emptiness,
and it is denominated in raw points.** A kicker's 182 and a receiver's 198 are not the same
currency — that is exactly what a replacement level exists to express, and the engine computes
one and then adds the raw level back at equal weight.

**Why later availability doesn't suppress them.** It cannot: the opportunity-cost term correctly
returns **0.0** for K, but it is *added* to the value base rather than being the basis of it, so a
zero timing cost cannot stop the pick. The engine's own board says Aubrey's true marginal value at
#80 is ~0 — the second kicker (Fairbairn, 181.6) is still there at **#140**.

**K/DST have no starter-vs-consumption mismatch** (ratio exactly 1.00), so their pathology is
**entirely** the double count — and they suffer it worst, because they are the flattest positions.
Under arm C, Aubrey's base falls 224.4 → 84.0 and Sutton (unchanged at 101.1, since WR is
saturated and the correction is zero there) wins the pick.

---

## 6. Phase 4 — starter vs consumption demand

| pos | starter demand | consumption demand | C/S | starter R | consumption R |
|---|---|---|---|---|---|
| QB | 1.00 | 2.20 | **2.20×** | 263.1 | 205.3 |
| RB | 2.50 | 4.20 | 1.68× | — | 96.0 |
| WR | 3.50 | 5.80 | 1.66× | — | 108.4 |
| TE | 1.00 | 1.80 | 1.80× | — | 119.7 |
| K | 1.00 | 1.00 | **1.00×** | 140.4 | 140.4 |
| DST | 1.00 | 1.00 | **1.00×** | 95.2 | 95.2 |

`S` sums to the lineup size (10), `C` to `roster_size` (16), both by construction.

**What replacement level should represent:** the best alternative still obtainable at that
position if you do not take this player now. The *economic* argument favours starter demand —
points only enter the objective through starting lineups, so pricing every QB against QB22
credits them with beating someone who contributes zero to any lineup.

**The benchmark has rejected that argument twice, and it is not re-run here.** Starter-demand
replacement is essentially D67's `W0`, which consumption demand beat by +32.1, CI [+11.5, +52.7];
and D84 measured the starter boundary directly and found it *widens* the round-2 QB margin
(+38.6 → +48.5), because a shallower boundary raises every position's replacement and shrinks
every surplus toward zero, which *increases* the relative weight of the raw-projection term.
Arm B was withdrawn before running for exactly this reason and stays withdrawn.

**It should not differ by position or draft stage.** A per-position or per-round choice of
boundary is a positional re-weighting with a free parameter — the shape D66/D67 rejected. The
answer that survives is: one boundary (consumption), league-derived, and fix the *value base*
rather than the boundary.

---

## 7. Phase 6/7 — roster legality as a hard constraint

**The constraint.** D67's `W2`/`W3` rule, unchanged: once remaining picks equal unfilled
dedicated slots, restrict the candidate pool to those positions — still ordered by the arm's own
score. No free parameter, no round number, no position named, and it never touches a value.

**It provably works.** On a constructed state (14 skill players, 2 picks left, K and DST both
empty) L1 and L3 restrict the pick from A.J. Brown (WR) to Breece Hall (RB); L0 and L2 do not.

**It never fires in a real draft.** Instrumented over the full 5-season × 10-slot grid:

| tier | constraint changed the pick | of |
|---|---|---|
| L0 (no constraint) | 0 | 800 picks |
| **L1 (enforces legality)** | **0** | **800 picks** |
| L2 (no constraint) | 0 | 800 picks |
| **L3 (enforces legality)** | **0** | **800 picks** |

So `L1 == L0` and `L3 == L2` to the decimal is **measured inertness with a demonstrated-working
mechanism**, not a silent defect — the distinction that D78 and D81 record as the failure mode to
guard against.

**The 2×2, target format:**

| | legality OFF | legality ON | legality effect |
|---|---|---|---|
| **Y1 valuation** | L0 **2042.8** | L1 **2042.8** | +0.00 |
| **arm C valuation** | L2 **2069.4** | L3 **2069.4** | +0.00 |
| **valuation effect** | +26.59 | +26.59 | **interaction +0.00** |

Infeasible rosters: **0 in all four arms**. The interaction is exactly zero in every format
tested.

**This overturns D84's "the over-valuation is load-bearing" conclusion.** D84 measured 2
infeasible rosters under arm C and inferred that the double count was buying roster legality. On
this rebuilt board arm C produces zero, and the constraint that would have rescued them is never
needed. The two mechanisms are already separate; there was nothing to separate.

---

## 8. Phase 8 — RB layer isolation (mandatory)

**The projection error is real and reproduces.** Over 37 elite-ECR (top-24) RB seasons,
2022–2025, mean signed error (realized − Alpha) = **+47.7** — Alpha under-projects. D84 measured
+42.3 for the top-10 tier; the brief cites ~+45.5. Consistent.

**The decision layer amplifies it by exactly 2×, under both formulations** (§3). This is the
central answer.

**How much correction does the engine need before it acts?** Elite-RB cell (ECR ≤ 24) shifted by
Δ, everything else unchanged, in memory only:

| Δ | Y1 pick #1 | arm C pick #1 |
|---|---|---|
| +0 | Amon-Ra St. Brown (WR) | Amon-Ra St. Brown (WR) |
| +25 | Amon-Ra St. Brown (WR) | Amon-Ra St. Brown (WR) |
| **+50** | Amon-Ra St. Brown (WR) | **Christian McCaffrey (RB)** |
| **+75** | **Christian McCaffrey (RB)** | Christian McCaffrey (RB) |

Y1 needs **+75** (McCaffrey at 351.7 — this independently reproduces D84's "elite RBs must
project ~350"). Arm C needs **+50**. The measured bias is **+47.7**: *just* short of flipping the
pick under the corrected valuation, and nowhere near it under Y1.

At **#20** the RB projection is irrelevant under both: Y1 takes Josh Allen at every Δ up to +100;
arm C takes Jeremiyah Love at every Δ. The *valuation*, not the projection, decides that pick.

**Does the corrected formulation change the elite-RB ranking on the 2026 board?** Barely. Top-15
composition is **identical** (11 WR, 4 RB); elite RBs move 0 to +5 board positions; McCaffrey
stays #5, Bijan stays #15.

**Does opportunity cost compensate?** No — it works *against* elite RBs at the top. At pick #5,
McCaffrey has the higher value base (457.5 vs 448.9) and still loses, because RB opportunity cost
is 19.3 against WR's 51.2.

**Verdict on the A/B/C/D question: (C) both, in the shape of (D).** The projection is biased
+47.7; the decision layer requires +75 (Y1) or +50 (arm C) to respond; and the 2× amplification is
*not* removed by the corrected valuation. **No RB projection was modified.**

---

## 9. Phase 11 — snake turns

For draft slot 1 every pick after #1 alternates: #20 has a zero gap, #21 has 18 opponents, and so
on. `oc = 0` at a turn is *correct* — no opponent picks in between, so no positional value can be
lost.

| slot | pick | gap | winner | with oc(18) restored |
|---|---|---|---|---|
| 1 | 20 | 0 | Josh Allen (QB) | Allen still; margin **+11.7 → +36.2** |
| 1 | 40 | 0 | Davante Adams (WR) | unchanged, margin +17.2 → +17.2 |
| 10 | 10 | 0 | De'Von Achane (RB) | **changes → Drake London (WR)** |
| 5 | 25 | 10 | **Josh Allen (QB)** | oc live, QB wins anyway |

**This refines D84.** D84 found restoring oc at #20 collapsed the QB margin (+73.2 → +3.4); on
this board it **widens** it (+11.7 → +36.2), because QB draws oc 32.5 while the RB runner-up draws
0.0. And Allen wins at slot 5 pick #25 *with* a live opportunity cost. **The zero-gap turn is
neither necessary nor sufficient for the QB pick** — it can amplify or dampen depending on the
board. The double count is the cause; the snake turn is not.

---

## 10. Phases 9/10/12 — generalization and historical results

Four formats, 5 seasons × 10 slots each, fair roster-aware opponents:

| format | board | L0 | L1 | L2 | L3 | margin | 1st QB L0→L2 | 1st K | 1st DST |
|---|---|---|---|---|---|---|---|---|---|
| target 1QB | `ro` | 2042.8 | 2042.8 | 2069.4 | 2069.4 | **+26.6** | 2.12 → **3.04** | 8.78 → 10.44 | 10.00 → 12.98 |
| legacy 2QB dynasty | `dsf` | 2150.6 | 2150.6 | 2141.5 | 2141.5 | **−9.1** | 1.48 → 1.36 | — | — |
| superflex redraft | `rsf` | 2159.5 | 2159.5 | 2155.1 | 2155.1 | **−4.4** | 1.56 → **1.54** | 8.70 → 11.10 | 10.02 → 13.86 |
| 2QB redraft | `rsf` | 2110.7 | 2110.7 | 2099.6 | 2099.6 | **−11.1** | 1.38 → 1.24 | 8.90 → 11.00 | 10.60 → 13.64 |

**The mechanism generalises exactly as an economic formulation should.** It defers QB where QB
demand is low (1-QB: 2.12 → 3.04) and leaves it alone where demand is high (superflex: 1.56 →
1.54; 2QB: slightly *earlier*). The brief's requirement — "a 1-QB fix should not accidentally
suppress QB in Superflex" — is met. K/DST deferral is consistent in all three formats that have
those slots.

**The benefit does not generalise.** Positive in one format, negative in three.

Per-season margins (target format): 2021 +65.0, 2022 +45.2, 2023 −9.6, 2024 +121.4, 2025 −89.0 —
**2 of 5 seasons worse**, and the margin is dominated by 2024. Season-clustered 95% CI (D71, t,
df = 4): **[−72.5, +125.7]**, which contains zero. Legacy format: 4 of 5 seasons worse, CI
[−49.9, +31.7].

---

## 11. Phase 13 — the 2026 board, #1 / #20 / #21

| | Y1 (L0) | arm C (L2 = L3) |
|---|---|---|
| #1 | Amon-Ra St. Brown (WR) | Amon-Ra St. Brown (WR) |
| **#20** | **Josh Allen (QB)** | **Jeremiyah Love (RB)** |
| #21 | Jeremiyah Love (RB) | Josh Allen (QB) |
| first K | round 8 | round 10 |
| first DST | round 10 | round 14 |
| first TE | round 9 | **round 15** |
| composition | 5 WR, 3 RB, 2 QB, 2 TE, 2 K, 2 DST | 6 WR, 3 RB, 2 QB, 2 TE, 2 K, 1 DST |

Arm C swaps the order of #20/#21 and defers K, DST and TE. Both rosters are legal. Note arm C's
TE at **round 15** — a mandatory slot filled at the last realistic moment, which is the behaviour
the legality constraint exists to backstop and the reason it was measured jointly.

---

## 12. Gate results — pre-registered, applied mechanically

| tier | margin | G1 | G2 | G3 | G4 | G6 | G7 | G8 | G9 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **L1** legality alone | +0.0 | ok | ok | ok | ok | **FAIL** | ok | **FAIL** | **FAIL** | **DO NOT SHIP** |
| **L2** valuation alone | +26.6 | ok | ok | **FAIL** | ok | ok | **FAIL** | **FAIL** | ok | **DO NOT SHIP** |
| **L3** valuation + legality | +26.6 | ok | ok | **FAIL** | ok | ok | **FAIL** | **FAIL** | ok | **DO NOT SHIP** |

L1 is an exact null, so it fails the effect-size and interval gates by construction. L2/L3 clear
the 25-point floor in the target format but fail on per-season consistency (2 of 5 worse), on
cross-format sign (negative in 3 of 3 alternatives), and on the season-clustered interval.

**Nothing ships. `league/draft.py` stays byte-identical to Y1.**

---

## 13. Pre-registered predictions vs outcomes

| | prediction | outcome |
|---|---|---|
| **P1** | L1 close to inert, \|L1−L0\| < 25, 0 infeasible | **CORRECT, and stronger** — exactly 0.00, constraint never fires in 800 picks |
| **P2** | L2 reproduces D84's arm C (~+3 target, ~−30 legacy, ~2 infeasible) | **PARTLY WRONG** — see below |
| **P3** | L3 clears G1/G2 by construction, rescuing arm C's 2 infeasible rosters | **VACUOUS** — there were 0 to rescue |
| **P4** | L3 still fails G8/G9; most likely outcome is nothing ships | **CORRECT** — nothing ships, though L3 clears G9 and fails G3/G7/G8 instead |
| **P5** | interaction positive but small | **WRONG** — exactly 0.00, in all four formats |

### P2 — the registered reproduction check, reported before interpretation

P2 required that a material deviation be reported *before* L3 was interpreted. There is one.

| | D84 published | D85 measured | delta |
|---|---|---|---|
| control, target | 2055.9 | **2042.8** | −13.1 |
| control, legacy | 2114.5 | **2150.6** | +36.1 |
| arm C margin, target | +3.1 | **+26.6** | +23.5 |
| arm C margin, legacy | −29.6 | **−9.1** | +20.5 |
| **arm C infeasible rosters** | **2** | **0** | **qualitative** |

The **harness is verified identical**: on this board `L0 == Q0 == Z0 == S0 == W1 == X0` to four
decimals in both formats, so the difference is the **board**, not the wiring. The database was
rebuilt from source in this session and the data moved (837 players vs D84's 834; rookie class 153
vs 150). The numeric deltas sit well inside the ±100-point instrument noise D71 quantified, and
the sign is preserved in both formats.

**The one qualitative deviation is the important one.** D84's central claim for *not* pursuing
this direction — that the over-valuation is load-bearing for roster legality — rests on those 2
infeasible rosters. They do not reproduce. That claim should be treated as board-specific, not
structural.

---

## 14. Position-by-position impact (target format, L2/L3 vs Y1)

| position | first-round timing | late-round count | zeroed |
|---|---|---|---|
| QB | 2.12 → 3.04 (later) | 0.00 → 0.04 | 0 → 0 |
| RB | 3.92 → **3.26** (earlier) | 1.04 → 0.66 | 0 → 0 |
| WR | 1.80 → 1.54 (earlier) | 1.36 → 0.64 | 0 → 0 |
| TE | 6.72 → 8.06 (later) | 1.26 → 1.08 | 0 → 0 |
| K | 8.78 → 10.44 (later) | 1.02 → 1.34 | 0 → 0 |
| DST | 10.00 → 12.98 (later) | 0.32 → 1.24 | 0 → 0 |

No position is zeroed under either arm, and no position is drafted more than 2 rounds earlier
(G1/G4 pass). RB moves *earlier* by 0.66 rounds — the direction the brief hoped for — and TE moves
1.34 rounds later, which is the arm's main cost.

---

## 15. Remaining risks

* **The instrument still cannot resolve the effects being tested.** Every CI here spans ±100
  points against a 25-point ship threshold. D71's power analysis (MDE ≈ 128 points at 5 seasons)
  has now been confirmed by a ninth reformulation. **No draft-layer value-base change can be
  established or refuted at this data scale.** That is a property of the benchmark, not of any
  candidate.
* **The benchmark cannot price a wasted bench slot.** It models no injuries, byes, waivers or
  lineup decisions, so a roster spot spent on a kicker who starts beats one spent on a receiver
  who does not. The round-8 kicker is worth ~0 by the engine's own board and costs ~0 by the
  benchmark. Both facts are real; they are measured by different instruments.
* **The control moved 13 points on a from-source rebuild**, and D84's arm C infeasibility did not
  reproduce at all. Absolute figures from any single session should be labelled by the board that
  produced them.
* **Arm C's TE deferral to round 15** on the 2026 board is a genuine fragility. It did not produce
  an illegal roster here, and the legality constraint would backstop it, but it is close to the
  edge.
* **The 2× amplification is unresolved and now known to be unfixable within the current score
  shape.** Reducing it requires unit slope, which requires halving the value base against a
  static-VORP opportunity cost — the scale mismatch open since D60.

---

## 16. Trust assessment — plain English

> *"If I give Alpha pick #1 in a real 10-team 1-QB league, what can I trust it to do, what can I
> not trust it to do, and why?"*

**What you can trust.**

* **It will field a legal roster.** Zero unfilled mandatory slots in every one of the 800+ drafts
  measured here, across four formats and both valuations. This is now known to be robust rather
  than an accident of over-valuation.
* **It is enormously better than best-player-available.** The league-context layer is worth
  ~+1600 starter points over `alpha_bpa`. That is the largest and most reliable effect in the
  system.
* **It responds to the board, not to a hardcoded lean.** WR-first is a property of the 2026 board
  (46 of 60 across seasons; 2021 opens RB-TE-WR), and the engine adapts correctly across formats —
  superflex openings are QB-heavy, as they should be.
* **Its top-of-board ordering at #1.** Amon-Ra St. Brown at 1.01 is a defensible pick and is
  stable under every reformulation tested.

**What you cannot trust.**

* **The exact timing of QB, K and DST.** The round-2 quarterback and the round-8 kicker are
  produced by a value base that is provably incoherent — it counts the raw projection twice, worst
  at the flattest positions (DST 8.10×, K 5.34×). Alpha's own board says the kicker it takes at
  #80 is still available at #140. **Take the kicker and the defense later than Alpha says.** This
  is the one recommendation I would make with confidence, and it costs nothing measurable.
* **Elite running backs.** Alpha under-projects them by ~48 points, and the decision layer needs
  ~75 before it changes its #1 pick. It will systematically pass on the Bijan/Gibbs/McCaffrey tier
  earlier than a human should. Note the free consensus market makes the same error with the same
  sign (+35.2 vs Alpha's +42.3), so this is a hard problem rather than a bug.
* **Anything that depends on Alpha beating the free consensus board.** Its margin over a fair
  consensus opponent has no stable sign across rebuilds (+21.2, −21.3, and now −13 on the control
  alone). Alpha is *demonstrably* better than naive strategies; it is *not demonstrated* to be
  better than a good human with FantasyPros open.

**Why.** The value base asks two questions — "does he improve my lineup" and "is he better than
what I can get later" — and adds the answers even though both are the same surplus measured from
different zeros. Correcting that makes the engine behave exactly as intended (QB round 3, kicker
round 10, RB earlier) and, measured over five seasons and four formats, buys nothing you can
distinguish from noise, while costing points in three formats out of four. **That is why nothing
ships: the theory is right, and the evidence to act on it does not exist at this data scale.**
