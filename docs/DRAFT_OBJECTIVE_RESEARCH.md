# D86 — What should Alpha optimize?

*Pre-registration: `src/alpha_squad/evaluation/objective_candidates.py`, committed at `8c309d9`
before any candidate ran. Instruments: `evaluation/draft_oracle.py` (`47ce0f1`),
`evaluation/weekly_objective.py` (`ee59634`). `models/` and `league/` are **byte-identical to
Y1** throughout.*

---

## 1. The current objective — what Alpha actually optimizes

`recommend_draft_pick` selects `argmax` over available players of

```
score(c) = ( value_base(c) + opportunity_cost(pos c) )
           × roster_fit(pos) × confidence(c) × survival(c) × [0.1 if over cap]

value_base(c) = MSV(c) + 1.0 × daVORP(c)
```

| term | what it represents | information used | future consequence it tries to capture | what it does NOT capture |
|---|---|---|---|---|
| **MSV** | how much `c` improves *my* best lineup | my roster + projections | lineup saturation — a 5th WR adds nothing | that a starter misses games; it assumes all 17 weeks played |
| **daVORP** | `proj − R`, surplus over the player still free at the draft's end | full board + a 160-pick mock draft | league-wide positional scarcity | in-season replacement (waivers); timing before the end |
| **opportunity cost** | positional value expected to vanish before my next turn | board + an 18-pick opponent replay | near-term positional depletion | anything beyond the next turn; it is 0 at a snake turn |
| **roster fit** | soft [0.7, 1.3] nudge on positional need | roster position counts | saturation, again | magnitude — it is a multiplier on need, not on value |
| **confidence** | M6's per-player interval confidence | uncertainty model | projection reliability | correlation between players; downside vs upside |
| **survival** | [1.0, 1.3] urgency if `c` may be gone | ECR dispersion | *this player's* availability at my next pick | it can only ADD urgency, never discount a certain survivor |
| **cap** | 0.1 past positional capacity | roster counts + league config | hard feasibility floor | it is a cliff, not a price |

**Formally, this is a myopic scoring heuristic, not an estimate of any well-defined expectation.**
It is not `E[starter points]` — the multipliers are unitless. It is not a value function of the
sequential problem. It is a hand-assembled sum of one points-denominated surplus and one
VORP-denominated cost, scaled by four unitless factors.

### Duplicated concepts, measured rather than asserted

**1. Positional saturation is encoded three times.** Holding one candidate WR fixed and varying
only how many WRs the roster already holds (WR has 4 startable slots, capacity 6):

| #WR held | MSV | roster_fit | cap mult |
|---|---|---|---|
| 0 | 227.5 | 1.20 | 1.00 |
| 3 | 227.5 | 1.03 | 1.00 |
| 4 | **0.0** | 1.00 | 1.00 |
| 6 | 0.0 | 0.70 | **0.10** |

Three mechanisms, three different thresholds, one state variable. And they are partly inert:
once MSV hits 0 the multipliers scale zero, so `roster_fit` and `cap` only ever act through the
daVORP half — which never saturates at all.

**2. Near-term availability is priced twice, in different algebra.** `opportunity_cost` is
positional and **added** in points; `survival` is per-player and **multiplies**, unitless. At
pick 1 the top WRs all carry oc 65.3 *and* survival multiplier 1.300 — perfectly collinear.

**3. Two models of future draft consumption, at different horizons, never reconciled.** daVORP's
replacement level comes from a full 160-pick mock draft; opportunity cost comes from an 18-pick
replay of the same opponent model.

**4. Three different replacement baselines coexist inside one sum.** MSV's implicit **0**,
daVORP's **draft-aware** level, and opportunity cost's **season-static** level:

| pos | static R (oc basis) | draft-aware R (value basis) | gap |
|---|---|---|---|
| QB | 266.5 | 205.3 | **+61.3** |
| RB | 156.6 | 96.0 | +60.6 |
| WR | 157.1 | 108.4 | +48.7 |
| TE | 132.6 | 119.7 | +12.8 |
| K / DST | 140.4 / 95.2 | 140.4 / 95.2 | 0.0 |

D85 established two of these baselines were being double-counted. The third — the unit mismatch
between an added VORP-denominated cost and a points-denominated value base — has been open since
D60 and is still open.

---

## 2. The actual draft objective

What we ultimately care about is winning the league. The honest chain, and where each link breaks:

```
P(championship)                             ← schedule luck; not controllable, correctly dropped
  ≈ E[wins]                                 ← depends on the DISTRIBUTION of weekly scores
  ≈ E[season starter points]                ← drops variance; defensible as a first-order proxy
  ≈ Σ_weeks best legal lineup among          ← THE CORRECT COMPUTABLE TARGET
      roster players available that week
  ≈ best legal lineup from season totals    ← WHAT EVERY PUBLISHED NUMBER USES
```

The last step is where the real damage is, and it is not a subtlety. Scoring a roster from season
totals with one lineup allocation means:

* **byes are invisible** — the same eleven players are started in all 17 weeks, including the ones
  they did not play;
* **injuries are invisible** — a player who tore an ACL in week 3 contributes his season total and
  never vacates the slot;
* **therefore the bench is worth exactly zero**, because the starter never leaves the lineup.

These are not three separate missing features requiring three new terms. **They are one error**,
and fixing the granularity fixes all three at once, with no new data: nflverse writes a
`player_week_stats` row when a player played, so "who was available in week *w*" is already
recorded, and a bye and an injury are the same thing — a missing row.

### What matters vs what is computable

| factor | matters? | computable here? |
|---|---|---|
| starting-lineup points | yes, primary | yes |
| bye weeks | yes | **yes** — missing weekly row |
| injury / availability | yes | **yes** — missing weekly row, and rates are measurable |
| bench value | yes | **yes** — it is an output of weekly scoring, not an input |
| positional requirements | yes | yes (already) |
| positional scarcity | yes | yes (already, daVORP) |
| future draft opportunity | yes | yes (already, opportunity cost) |
| projection uncertainty | yes | partly (confidence) |
| waivers / in-season churn | **yes, materially** | **NO** — no transaction history exists |
| trades | yes | no |
| player correlation (stacking) | second-order | not attempted |
| schedule / opponent strength | yes for wins | no, and correctly out of scope |

### The measurement

Rosters Alpha actually drafts, 2021–2025 × 4 slots:

| objective | mean |
|---|---|
| season-long (incumbent) | **2036.2** |
| weekly, no-foresight lineups | **2017.3** |
| weekly, hindsight lineups | 2238.6 |
| **bench contribution (no foresight)** | **358.5 — 17.8%** |
| bench contribution (hindsight) | 483.6 — 21.6% |
| weeks in which a bench player started (no foresight) | **16.2 of 17** |

**The incumbent metric's *level* is about right (2036.2 vs 2017.3); its *composition* is not.**
About a fifth of realized points come from players it scores at zero. That is the defect.

---

## 3. Missing value sources — quantified, not listed

| source | verdict | evidence |
|---|---|---|
| **bench depth** | **REAL and large** | 17.8% of realized points, 16.2 weeks in 17 |
| **injury / availability** | **REAL, and it is the mechanism behind bench value** | draftable availability: QB 88.2%, RB 85.3%, WR 86.1%, TE 87.3%, K 93.6%, DST 94.0% |
| **bye weeks** | real, same mechanism | indistinguishable from injury in the data, and correctly so |
| **positional depth** | real, and position-specific | RB misses 2.5 weeks/season, K misses 1.0 — so RB depth is worth more, from data not a rule |
| **waiver replacement** | real but **UNMEASURABLE here** | see §6 |
| **future draft scarcity** | already captured | see §5 — opportunity cost is directionally right |
| **opportunity cost** | already captured, imperfectly | oc = 0 at snake turns is *correct*, not a bug (D85) |
| **roster flexibility** | partly captured via FLEX in the allocator | not separately priced |
| **player volatility** | second-order | see §8 |
| **projection uncertainty** | already captured | `confidence` ∈ [0.63, 1.3] |
| **positional correlation** | not attempted | needs a schedule join; effect makes depth *more* valuable, so omitting it is conservative |
| **draft position / snake turns** | captured, and D85 showed it is not the cause of anything | — |

---

## 4. Oracle analysis — where Alpha disagrees with retrospectively optimal decisions

`evaluation/draft_oracle.py`. At each of **320 real production-path pick states** (2021–2025 × 4
slots × 16 rounds), every candidate on a ~20-player slate was evaluated by **rolling the rest of
the draft out with the shipped policy and scoring the final roster on realized points**. Realized
outcomes touch nothing but the final scoring; a signature-inspection guard enforces it.

### Raw regret is large — and mostly luck

| | mean regret (realized starter pts) |
|---|---|
| **Alpha's pick** | **116.2** |
| a random pick from the same slate | 122.3 |
| the highest-projection pick | 144.6 |
| the worst pick on the slate | 191.1 |

**Alpha captures only ~5% of the gap between random and perfect** — but it does beat
best-by-projection by 28.4 points, which is the decision layer earning its place.

### The decomposition that matters

| | |
|---|---|
| mean regret | 116.2 |
| mean realized-points gap (oracle's player − Alpha's player) | **104.1** |
| Spearman(Alpha's score, final roster value) | **−0.033** |

**~90% of the regret is explained by the oracle simply picking a player who scored more.** That is
luck, and no objective can recover it. The near-zero rank correlation says the same thing: within
a slate of plausible candidates, final roster value is dominated by outcome noise.

### The structural residual — the only part a better objective could reach

Restricting to picks where the oracle's player **scored no more** than Alpha's and still produced a
better roster:

* **16 of 320 picks (5%)**, mean regret **+112.2**
* dominant pattern: **Alpha took a QB, the oracle wanted a RB (6) or a WR (3)**
* **total structural headroom ≈ 90 points per draft**, and that is an upper bound, since capturing
  it at every pick simultaneously is not possible

### How much can one pick matter at all?

| | |
|---|---|
| spread of final-roster value across ~20 plausible picks | 191.1 |
| SD of final-roster value across the slate | **53.2** |
| typical final roster | 2036.2 |
| **⇒ one pick moves the final roster by ~2.6% (1 SD)** | |

And it decays monotonically: round 1 spread 343.7 → round 8 158.9 → round 16 113.0.

**This is the single most important number in D86.** The structural headroom available to *any*
better objective is ~90 points, and D71's minimum detectable effect for this benchmark is ~128
points at five seasons. **The prize is smaller than the ruler.**

---

## 5. Lookahead analysis

One-step lookahead = `argmax` of the **projected** final-roster value after rolling the rest of the
draft out with the shipped policy. Fully implementable (no outcome touches it); the formal
statement of the brief's objectives (D)/(G).

**Agreement test, 15 real states across 3 season/slot combinations: lookahead disagreed with greedy
in 4 (27%).** Pre-registered prediction Q6 said it would "change few picks" — **Q6 is wrong**, and
that is recorded as a miss rather than reinterpreted.

Every disagreement selected a candidate ranked **3rd or 4th** on the greedy list — a modest
reordering inside the top few, not a different strategy. Examples: 2023 slot 5 pick #5 Stefon Diggs
→ Travis Kelce; pick #16 Patrick Mahomes → Derrick Henry.

Cost: ~1 s per pick per candidate of rollout at width 8.

---

## 6. Replacement analysis — draft vs waiver

**There is no historical waiver or transaction data in this database.** Checked: no transactions
table, no adds/drops history; Sleeper's `trending_adds` is a live 25-row snapshot, not history.
So actual waiver *activity* cannot be measured and is not invented.

What *is* measurable is what the undrafted pool actually produced. Using the same mock draft that
defines `market_draft_demand`, so "undrafted" means exactly what the engine means by it
(2021–2025 means):

| pos | R_draft (engine's level) | best undrafted by preseason projection, realized | median drafted |
|---|---|---|---|
| QB | 200.4 | 194.6 | 260.5 |
| RB | 89.0 | 94.1 | 173.3 |
| WR | 111.9 | 133.8 | 183.7 |
| TE | 116.2 | 118.4 | 147.0 |
| K | 132.9 | 104.2 | 133.8 |
| DST | 95.5 | 87.4 | 99.2 |

**The incumbent draft replacement level is well calibrated to the no-foresight waiver
replacement** at every position. That is a validation of the current design, not a criticism, and
it is why no replacement-level change is proposed.

**Streaming optionality is real but not identifiable.** Weekly best-of-the-undrafted-pool with
perfect foresight reaches 172–290% of the median drafted player, and even a 3-player watchlist
reaches 144% at K and 161% at DST — but both retain within-week foresight a real manager does not
have. The honest statement: the option value is largest exactly at K/DST/TE, the positions the
engine already over-drafts, **and its magnitude cannot be pinned down without transaction data.**

---

## 7. Bench value

Answered in §2 and §3: **17.8% of realized points, no-foresight; a bench player starts in 16.2 of
17 weeks.** The current MSV prices it at exactly **0.0**.

The forward-looking fix needs no bonus. `expected_weekly_marginal_value` asks the same
marginal-value question under measured availability. On a saturated roster (4 WR / 1 QB / 1 K /
1 DST / 1 TE), where the shipped MSV returns exactly 0.0 for **every** one of these:

| backup at | shipped MSV | E[weekly] marginal |
|---|---|---|
| RB | 257.4 | **207.2** |
| WR | 0.0 | **79.2** |
| TE | 0.0 | **69.8** |
| QB | 0.0 | **34.1** |
| K | 0.0 | **9.1** |
| DST | 0.0 | **5.9** |

**A backup kicker is worth 9.1 and a backup running back 207.2 — from an availability rate, with
no positional rule anywhere.** This is the K/DST deferral that five previous phases could only
obtain with an arbitrary round rule.

---

## 8. Risk and uncertainty

The existing terms already span most of the available range: `confidence` ∈ [0.63, 1.3] in real
data, `survival` ∈ [1.0, 1.3]. D84 measured the one specific defect — survival can only *add*
urgency, never discount a player certain to still be there — and its correction (arm D, symmetric
survival) **failed its gates** (−15.2 in the target format, sign-flipping to +50.8 out of format).

No new risk term is proposed. Adding a third uncertainty factor without evidence that the first two
are mis-specified would be unmotivated, and the one motivated correction has already been measured
and rejected.

The variance that *does* matter is the one §4 quantified: realized outcome spread dwarfs
predictable spread (D84: realized SD 60–96 per tier against predicted 22–47). That is a property of
football, not a term to add.

---

## 9. RB interaction

D85 established: elite-ECR RB signed error **+47.7** (Alpha under-projects); Y1 needs **+75** of
correction before it takes an RB at #1; `d(value_base)/d(proj) = 2` under every formulation tested.

D86 adds the oracle's independent confirmation, from the outcome side rather than the projection
side. In the **structural residual** — the 5% of picks where a better objective could genuinely
have helped — the single dominant pattern is **Alpha took a QB where the oracle wanted a RB (6 of
16) or a WR (3 of 16)**. Across all disagreements, `QB → RB` carries the highest mean regret of any
swap (**181.1**).

So the RB problem and the QB-timing problem are **the same error seen from two sides**, and the
oracle says so without using any projection.

A richer objective helps here for a reason that is not projection accuracy: RB is **the least
available position** (85.3%, 2.5 weeks missed) **and** the only one with flex eligibility, so RB
depth is worth more than any other depth. The availability-aware objective prices that; the
incumbent cannot.

---

## 10. Candidate objectives

Pre-registered at `8c309d9` before any result. Arms:

* **O0** — control, the shipped Y1 engine. Asserted byte-identical to `L0`/`Q0`/`Z0`.
* **O1** — `E[weekly msv] + 1.0 × daVORP`. `marginal_starter_value` replaced by
  `expected_weekly_marginal_value`; **everything else unchanged**. The value base's *algebra* is
  untouched — D85 closed that seam — only what its marginal half is an expectation *of*.
* **O2** — one-step lookahead, conditional on the Phase 5 agreement test.

Availability rates are measured on seasons **strictly before** the drafted season (walk-forward by
construction) and O1 **raises** rather than defaulting if they are absent — the D78/D81/D85 failure
mode where an arm reports itself as running while measuring the control.

**Metrics.** Primary: weekly realized points, no-foresight lineups. Always also reported: weekly
hindsight, and season-long (so every D86 number stays comparable to D63/D67/D79/D84/D85).
Adjudication rule fixed in advance (**G10**): a candidate improving the primary but materially
degrading season-long does **not** ship — this project does not adopt a new instrument and a new
winner in the same step.

Not proposed, each with the evidence excluding it: any value-base algebra change (D85, nine
failures, structural slope problem); a waiver replacement level (§6, unmeasurable); a risk term
(§8); any bench or positional bonus (the brief — and O1 needs none, which is the test).

---

## 11. Historical results — the pre-registered O-tier evaluation

5 seasons × 4 draft slots × 2 formats, fair roster-aware opponents. **Scope note:** 4 slots
rather than 10 (the same slots the oracle audited). O1 costs ~180× a control pick, so the full
10-slot grid is ~3 h per format. The pre-registered `n_draws = 200` was **not** changed — it was
verified precise to 1.44 points against an n=800 reference.

### Target format (10-team 1-QB PPR)

| tier | weekly (no foresight) — **primary** | weekly (hindsight) | season-long | bench pts | infeasible |
|---|---|---|---|---|---|
| **O0** control | 1924.5 | 2100.5 | 1967.1 | 400.4 | 0 |
| **O1** | **1977.3** | **2175.2** | **2001.6** | 424.2 | 0 |
| **Δ** | **+52.9** | **+74.7** | **+34.5** | +23.8 | — |

Per season: 2021 **+71.0**, 2022 −14.6, 2023 +18.4, 2024 **+102.2**, 2025 **+87.5** — 1 of 5
worse. Leave-one-season-out: all five positive (+40.6 … +69.8). Season-clustered 95% CI
**[−8.3, +114.0]**.

| tier | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nQB | nRB | nWR | nTE | **nK** | nDST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 | 2.30 | 4.25 | 1.70 | 6.35 | 7.90 | 9.95 | 1.75 | 2.10 | 4.50 | 1.90 | **3.70** | 2.05 |
| O1 | 2.30 | 4.25 | 1.70 | 6.55 | 7.80 | 10.45 | 1.45 | **2.50** | 4.60 | **2.85** | **2.60** | 2.00 |

### Legacy 2QB dynasty (no K, no DEF slots)

| tier | weekly (no foresight) | weekly (hindsight) | season-long |
|---|---|---|---|
| O0 | 2207.3 | 2480.0 | 2151.4 |
| O1 | 2208.8 | 2499.7 | 2170.8 |
| **Δ** | **+1.6** | +19.7 | +19.3 |

Per season: −55.5, +28.9, +39.7, +38.5, −43.7 — 2 of 5 worse. CI **[−56.9, +60.1]**.

### Gates

| gate | target | legacy |
|---|---|---|
| G2 infeasibility | ok (0 vs 0) | ok |
| G3 ≤1 season worse | ok (1/5) | **FAIL** (2/5) |
| G6 leave-one-season-out | ok (all +) | **FAIL** |
| **G7 cross-format sign** | **ok — POSITIVE IN BOTH (+52.9 / +1.6)** | — |
| G8 clustered CI excludes 0 | **FAIL** [−8.3, +114.0] | **FAIL** |
| G9 margin ≥ 25 | ok (+52.9) | **FAIL** (+1.6) |
| G10 season-long not worse than −25 | ok (**+34.5**) | ok (+19.3) |

**Verdict: DO NOT SHIP.** In the target format only G8 fails; in `legacy_2qb_dynasty` the arm is
an effective null and fails four gates.

**This is nonetheless the strongest draft-layer result this project has produced.** It is the
first candidate in nine to (a) improve *both* metrics, (b) keep the same sign in both formats,
and (c) survive leave-one-season-out in the target format. Every previous candidate flipped sign
across formats or lost outright.

### Why it helps where it helps

The target-format gain is concentrated in one mechanism: **kickers drafted falls 3.70 → 2.60**,
with RB 2.10 → 2.50 and TE 1.90 → 2.85. `legacy_2qb_dynasty` has **no K and no DEF slots at
all** — so the mechanism has almost nothing to act on there, and the +1.6 null is exactly what
the mechanism predicts rather than a contradiction of it.

### Predictions vs outcomes

| | prediction | outcome |
|---|---|---|
| **Q1** | O1 defers first K by 1.5+ rounds, first DST by 2+ | **WRONG.** First K 7.90 → 7.80, first DST 9.95 → 10.45. O1 does not take the first kicker later — it stops **hoarding** them (3.70 → 2.60). A different mechanism than predicted. |
| **Q2** | more RB depth, fewer K/DST | **CORRECT** (RB 2.10 → 2.50, K 3.70 → 2.60); TE also rose 1.90 → 2.85, which was not predicted |
| **Q3** | O1 beats O0 on the weekly metric | **CORRECT** (+52.9) |
| **Q4** | O1 neutral-to-negative on season-long | **WRONG, favourably** — +34.5, comfortably positive, so G10 passes rather than being the failure route |
| **Q5** | most likely outcome is nothing ships, on G8 | **CORRECT** |
| **Q6** | lookahead changes few picks | **WRONG** — 27% disagreement |

Four of six predictions missed. Recorded as misses, not reinterpreted.

---

## 12. The 2026 board — #1 / #20 / #21

Draft slot 1, whose first three picks are overall #1, #20, #21.

| pick | Y1 (O0) | availability-aware (O1) |
|---|---|---|
| **#1** | Amon-Ra St. Brown (WR) | **identical** |
| **#20** | Josh Allen (QB) | **identical** |
| **#21** | Trey McBride (TE) | **identical** |

**O1 does not change the opening at all on the 2026 board.** The entire difference is in the
endgame:

| | Y1 | O1 |
|---|---|---|
| composition | WR 5, QB 1, TE 2, RB 2, **K 4**, DST 2 | WR 5, QB 1, **TE 3**, **RB 3**, **K 2**, DST 2 |
| rounds 11–16 | K, WR, TE, DST, **K**, **K** | TE, K, WR, DST, **RB**, **TE** |
| first K / DST | r9 / r10 | r9 / r10 (**unchanged**) |

Y1 drafts **four kickers** on this board. O1 replaces the third and fourth with a running back and
a tight end, and takes the first kicker at exactly the same time. The elite RBs, the rookies and
the QB timing are untouched.

---

## 13. Computational cost

| | per pick | 16-pick draft |
|---|---|---|
| O0 (shipped) | **0.03 s** | ~0.5 s |
| O1, full board (596 candidates) | **6.26 s** | ~100 s |
| **O1, K=40 shortlist** | **0.51 s** | **~7 s** |

The naive form is **180×** the control. But the expensive objective only needs to run on
candidates that could plausibly win: computing the cheap shipped score for the whole board and
re-scoring only the top K under the availability model reproduces the **identical pick and the
identical top five** at every K tested (20, 40, 80, 160).

**A K=40 shortlist is 12× faster than the full form and production-feasible** (~7 s for a whole
draft, ~0.5 s for a single recommendation). Memory is unchanged; the estimator is reproducible
across processes by construction (common random numbers on a non-salted hash).

---

## 14. Ship / do not ship

**DO NOT SHIP.** `league/draft.py` stays byte-identical to Y1.

O1 fails **G8** in both formats and fails G3/G6/G9 in `legacy_2qb_dynasty`. The pre-registered
selection rule requires every gate.

What is different from the eight previous failures, and worth recording: the point estimate is
positive on **both** metrics and in **both** formats, LOSO survives in the target format, and the
mechanism is a measured availability rate rather than a tuned constant. This is a near miss rather
than a refutation — but a near miss does not ship, and the rule was fixed in advance precisely so
that a near miss could not be talked into shipping afterwards.

---

## 15. Most promising next architecture

**More slots, not more terms.** The target-format CI is **[−8.3, +114.0]** — it excludes zero on
one side by 8 points. This evaluation ran 4 draft slots because O1 costs 180× the control; the
K=40 shortlist (§13) removes that constraint entirely. **Re-running the identical, already
pre-registered arm at the full 10 slots is the single highest-value next step, and it requires no
new idea.** It is the first time in this project's history that the honest recommendation is
"measure the same thing again with more power" rather than "try a different formula".

Two supporting directions, in order:

1. **Model bye-week correlation.** Availability is currently independent per player; real byes
   take a whole team out at once. That makes depth *more* valuable, so the current estimate is
   conservative — the effect can only help O1.
2. **Get transaction data.** §6 shows streaming optionality is real and largest at exactly the
   positions the engine over-drafts, and it is the one material value source this database cannot
   measure at all.

**Not recommended:** another value-base reformulation (nine failures, structural slope problem —
D85), a lookahead optimizer (27% disagreement but the structural headroom is ~90 points, below the
instrument's resolution), or any projection work (D79–D83 closed it).

---

## 16. Trust assessment — plain English

> **"Does Alpha fundamentally need a better objective, or are the remaining weaknesses primarily
> projection/data limitations?"**

**It needs a better objective, and the better objective has now been specified and measured — but
the honest answer is that neither a better objective nor better projections is the binding
constraint. The binding constraint is that fantasy football is mostly luck, and the benchmark
cannot resolve what remains.**

Three numbers carry that conclusion:

* **One pick moves the final roster by about 2.6%** (1 SD = 53.2 points of ~2036). Across ~20
  plausible candidates the whole spread is 191 points, and it shrinks every round.
* **About 90% of the gap to a retrospectively optimal pick is luck** — the oracle's advantage is
  almost entirely that its player scored more (104.1 of 116.2 points), and Alpha's score has
  essentially **zero** rank correlation (−0.03) with final realized roster value.
* **The structural headroom — the part a better objective could actually reach — is ~90 points per
  draft**, from just 5% of picks. D71's minimum detectable effect for this benchmark is ~128
  points. **The prize is smaller than the ruler.**

So the objective *was* genuinely wrong, in a way nobody had named: it scores season totals and
therefore prices the bench at zero, when the bench supplies **17.8%** of realized points and a
bench player starts in **16.2 of 17 weeks**. Fixing that is worth about **+53** points in the
target format — real, the right sign in both formats and on both metrics, and still inside the
noise band.

**What this changes about trusting Alpha at pick #1 in a real 10-team 1-QB league.** Nothing at the
top: on the 2026 board the availability-aware objective makes the **identical** picks at #1, #20
and #21. What it changes is the endgame — Y1 drafts **four kickers** on that board, and the
corrected objective drafts two, spending the other two picks on a running back and a tight end.
That is the concrete, defensible advice this phase produces, and a human can apply it without any
code change: **take the kicker you need, then stop.**

Everything D85 said about the top of the board still stands unchanged: trust Alpha to field a
legal roster and to beat naive strategies by a wide margin; do not trust its elite-RB valuation
(it under-projects them ~48 points and needs ~75 to act); and do not trust any claim that it beats
a good human with FantasyPros open, because that margin has never had a stable sign.
