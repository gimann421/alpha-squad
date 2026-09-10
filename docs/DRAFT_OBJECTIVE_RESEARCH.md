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
