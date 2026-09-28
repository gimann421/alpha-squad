# D122 — Continuation-aware MSV audit

**Headline: no measurable MSV defect a decision rule could act on. This branch is closed.**

The question was whether MSV over-credits an RB for filling an empty starting slot, when the
fixed continuation would have filled that slot anyway. Two exact continuation-aware quantities
were built from the existing machinery, and they answer differently.

* **Continuation-aware MSV (CA), leave-one-out on the continuation's own final roster
  (pre-registered).** It does **not** remove the RB advantage:
  * target: it prefers the RB in 7/7 RB→QB and 13/16 RB→WR states;
  * it agrees with one-step value *less* often than current MSV does.
  * The reason: when the continuation already holds the RB, it drafts no further RB. The slot
    really is scarce given that roster plan.
  * Re-ranking the whole board on CA + DA-VORP moves **0 of 14 RB→QB picks** and **4 of 24
    RB→WR picks** in the two formats, and **none of them to the oracle**.
  * Across all rounds 1–6 states the re-rank is +5.6 pts/state in target (CI [−6.2, +17.4]).
    In dynasty it is **−5.9 (CI [−11.4, −0.4])**, which is worse than shipped.
* **The pairwise "otherwise" increment (added after a one-draft smoke run, before the full
  run).** This is the RB's value over the starters the continuation fields at RB if it takes the
  QB/WR instead.
  * It *does* remove the RB advantage: it prefers the RB in only 1/7 RB→QB states in both
    formats.
  * MSV exceeds it by ~200–245 points for the RB against ~30–190 for the QB/WR.
  * **But this quantity is the one-step value minus a small spillover term, by construction.**
    Its agreement with one-step value is not independent evidence. On a population selected
    because the oracle beat Alpha, its "MSV overstates the RB" statistic is mostly MSV's own
    error restated.

**RB→QB, the mechanism D121 singled out, is narrower than it looked.**

* It is **three distinct decisions, all in 2022**. Target has 6 of 7 states in 2022; dynasty has
  7 of 7. D121's "6/7 in both formats" is one season seen twice, not replication.
* In target, **3 of the 7 states (187 of 231 regret) are sequencing**: taking the QB, the
  continuation still drafts the same RB later.
* On the weekly objective, Alpha's RB is the better pick in 5 of 7 target states.

**Structural classification:**

* the pre-registered measure (CA) gives **C**;
* the amended pairwise measure gives **B**, driven by one cell, RB→WR target, whose test is near
  circular;
* no measure gives A or D, and no format passes the pre-registered decision-relevance test.

**No production change recommended. This branch is closed; no D123 is proposed.**

`src/alpha_squad/` byte-identical (tree `55e763e8…`). Diagnostic only; nothing ships.

---

## 1. Reproduction (stop conditions — all passed)

| check | result |
|---|---|
| ARM 4 pick recomputed at every state vs D120's stored pick | **640 / 640** |
| D121 primary population recovered state-for-state (P, O, flow) | **38 / 38** (23 target + 15 dynasty) |
| D121's factors, MSV, DA-VORP, one-step and weekly one-step for P and O | equal to 1e-6 at all 38 |
| ARM 4 one-step (season + weekly) vs D120; oracle one-step vs D115 | 240 / 240 R1–6 states, 1e-6 |
| engine MSV for P and O recomputed with `marginal_starter_value` | 1e-6, every state |
| ARM 4 projections equal realized points | asserted, every season |
| BL(final roster) on ARM 4 projections vs the season-long scorer | 1e-6, every captured roster |
| CA identity: one-step gap = CA gap + rest-of-roster gap | 1e-6, every state |
| pairwise groups (by position and by slot) sum to the one-step gap | 1e-6, every state |
| re-rank upper bound on CA | never violated on any evaluated candidate |

* D120 commit `2c8a78f8`; D121 commit `c33ff349` (HEAD at run time, `src_dirty = false`).
* Board vintage `f0022601…` (unchanged).

## 2. What was measured

* **P** is ARM 4's pick; **O** is the D115/D120 per-pick oracle.
* **F_c** is the final 16-man roster the fixed shipped continuation produces after taking c. It
  is captured by wrapping the shipped season-long scorer, which the unmodified production
  `rollout` calls exactly once after the last pick (asserted).
* **BL** is `best_lineup_points` (production allocator, `teams=1`).

| term | definition |
|---|---|
| **MSV** (shipped) | BL(roster now + c) − BL(roster now) |
| **CA** (pre-registered continuation-aware MSV) | BL(F_c) − BL(F_c − c): lineup value with c minus with the continuation's eventual replacement (exactly one bench body enters, possibly through a FLEX reshuffle) |
| **pw** (amendment, pair only) | c's position-group starter points in F_c minus the same group in F_other: c's increment over what the continuation fields at c's position if the *other* player is taken now |
| value terms | value_base = MSV + DA-VORP (shipped); ca_value = CA + DA-VORP; pw_value = pw + DA-VORP |

**Why the amendment exists.** It was recorded in the runner before the full run.

* The one-draft smoke run (target 2022, slot 1) showed CA(RB) = MSV(RB) = 328 in both RB→QB
  states: the continuation that holds the RB drafts no third RB.
* When the QB is taken instead, the same continuation starts a 202-point RB.
* Leave-one-out cannot see a replacement the continuation drafts only when the candidate is
  absent. Both quantities are therefore reported everywhere, and the pre-registered A–D rule is
  evaluated separately on each.

**Construction caveats, stated before any interpretation.**

* one-step gap = CA gap + rest-of-roster gap, exactly.
* pw gap = one-step gap − spillover, exactly (spillover = other positions' starter change).
* So pw agrees with one-step value largely by construction, and G_pw ≈ (MSV gap − one-step gap)
  + spillover. On a population selected for positive regret, that is mostly MSV's own error.

## 3. Populations

| population | target: states / distinct (P, O) decisions / seasons / regret | dynasty |
|---|---|---|
| **A. RB→QB** | 7 / **3** / **2022 ×6, 2023 ×1** / 231 | 7 / **3** / **2022 ×7** / 456 |
| **B. RB→WR** | 16 / 11 / all 5 seasons / 1,089 | 8 / 7 / 2021, 2022, 2023 ×6 / 901 |
| primary (A + B) | 23 / 14 / 1,320 | 15 / 10 / 1,357 |
| **S. all R1–6 wrong-position** | 52 / 34 / all 5 / 3,664 | 43 / 26 / all 5 / 3,413 |
| **R. re-rank grid (all R1–6)** | 120 / — / all 5 / 4,208 | 120 / — / all 5 / 3,997 |

**RB→QB is effectively one season.**

* The same RB/QB pairs recur across draft slots and back-to-back picks: target's RB `…648969`
  against QB `…26576c` appears in 5 of its 7 states.
* A season-clustered interval is impossible in dynasty (k = 1) and meaningless in target
  (k = 2: G_pw CI [−1195, +1327]).
* D121's "reproducible in both formats" for RB→QB is the same 2022 draft seen through two
  scoring formats. It does not meet D121's own "majority of seasons" bar. D121's conclusion (no
  candidate) is unaffected; its word "reproducible" should be read in that light.

Target's primary population includes 2 zero-regret states (both players end up on both rosters)
and 1 state with regret −88.8, where Alpha's pick lies outside the oracle's slate. All are
carried over from D121 unchanged.

## 4. RB → QB deep dive

**Target**

In the table, "otherwise" is the starter the continuation fields at that position when the other
player is taken now; `—` means no different starter, i.e. the same RB is drafted later.

| state | Alpha / Oracle | proj A/O | MSV A/O | DA-VORP A/O | roster now | CA A/O | CA replacement for A | CA replacement for O | otherwise at RB | otherwise at QB | pw A/O | one-step A/O | weekly A/O | score A/O | re-rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 s1 R4 #40 | RB …648969 / QB …26576c | 328 / 417 | 328 / 217 | 239 / 198 | WQR | 328 / 217 | none (slot left empty) | QB …e15eab (rostered) 201 | RB …be20e6 202 | QB …0a68bb 292 | 126 / 126 | 2086 / 2118 | 2165 / 2124 | 523 / 345 | unchanged |
| 2022 s1 R5 #41 | same pair | 328 / 417 | 328 / 217 | 239 / 198 | WQRW | 328 / 217 | none | QB …e15eab 201 | RB …be20e6 202 | QB …0a68bb 292 | 126 / 126 | 2086 / 2118 | 2165 / 2124 | 644 / 422 | unchanged |
| 2022 s4 R6 #57 | RB …1e35ad / QB …4c6719 | 249 / 378 | 249 / 178 | 158 / 159 | WQWWW | 249 / 178 | none | QB …e15eab 201 | RB …ca541d 74 | QB …0a68bb 292 | 175 / 86 | 2208 / 2119 | 2268 / 2116 | 387 / 298 | unchanged |
| 2022 s7 R4 #34 | RB …648969 / QB …26576c | 328 / 417 | 328 / 217 | 239 / 198 | WRQ | 328 / 217 | none | QB …e15eab 201 | — (same RB later) | QB …0a68bb 292 | 0 / 126 | 2241 / 2279 | 2210 / 2208 | 536 / 358 | unchanged |
| 2022 s7 R5 #47 | same pair | 328 / 417 | 328 / 217 | 239 / 198 | WRQW | 328 / 217 | none | QB …e15eab 201 | — (same RB later) | QB …0a68bb 292 | 0 / 126 | 2195 / 2233 | 2178 / 2170 | 552 / 408 | unchanged |
| 2022 s10 R4 #31 | same pair | 328 / 417 | 328 / 217 | 239 / 198 | WRQ | 328 / 217 | none | QB …e15eab 201 | — (same RB later) | QB …6f9719 219 | 0 / 198 | 2168 / 2279 | 2196 / 2208 | 543 / 399 | unchanged |
| 2023 s1 R2 #20 | RB …65cd3f / QB …4f59e0 | 290 / 393 | 290 / 393 | 188 / 165 | W | 286 / 122 | RB …dae9ae (continuation) 4 | QB …ee42b4 (continuation) 270 | RB …dd0e15 247 | QB …26576c 280 | 44 / 112 | 2065 / 2134 | 1914 / 1986 | 442 / 440 | unchanged |

**Dynasty** (all 2022)

| state | Alpha / Oracle | proj A/O | MSV A/O | DA-VORP A/O | roster now | CA A/O | CA replacement for A | CA replacement for O | otherwise at RB | pw A/O | one-step A/O | weekly A/O | score A/O | re-rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| s7 R2 #14 | RB …2a9db6 / QB …26576c | 373 / 417 | 373 / 217 | 279 / 236 | Q | 209 / 217 | WR …2ae08d @FLEX 164 | QB …e15eab (rostered) 201 | RB …de3dfe @FLEX 155, …dd0e15 @RB 303 | −85 / 217 | 2019 / 2242 | 2106 / 2259 | 805 / 379 | unchanged |
| s7 R5 #47 | RB …648969 / QB …4c6719 | 328 / 378 | 328 / 178 | 235 / 197 | QRWW | 164 / 178 | WR …2ae08d @FLEX 164 | QB …e15eab 201 | RB …dae9ae 226 | 102 / 178 | 1986 / 2061 | 2054 / 2066 | 501 / 296 | unchanged |
| s7 R6 #54 | same pair | 328 / 378 | 328 / 178 | 235 / 197 | QRWWW | 164 / 178 | WR …2ae08d @FLEX 164 | QB …e15eab 201 | none | 328 / 178 | 1986 / 1999 | 2054 / 2042 | 550 / 296 | unchanged |
| s10 R1 #10 | RB …2a9db6 / QB …26576c | 373 / 417 | 373 / 417 | 279 / 236 | – | 227 / 309 | WR …5c46f8 @FLEX 146 | QB …e12641 (continuation) 108 | RB …6229f3 238 | 135 / 217 | 2060 / 2142 | 2173 / 2128 | 662 / 583 | unchanged |
| s10 R2 #11 | same pair | 373 / 417 | 373 / 217 | 279 / 236 | Q | 227 / 217 | WR …5c46f8 @FLEX 146 | QB …e15eab 201 | RB …005366 @FLEX 200 | 173 / 217 | 2060 / 2071 | 2173 / 2130 | 824 / 391 | unchanged |
| s10 R5 #50 | RB …648969 / QB …3c88c6 | 328 / 351 | 328 / 150 | 235 / 169 | QRWR | 183 / 150 | WR …5c46f8 @FLEX 146 | QB …e15eab 201 | RB …005366 @FLEX 200 | 128 / 150 | 2027 / 2052 | 2060 / 2081 | 471 / 278 | unchanged |
| s10 R6 #51 | same pair | 328 / 351 | 328 / 150 | 235 / 169 | QRWRW | 183 / 150 | WR …5c46f8 @FLEX 146 | QB …e15eab 201 | RB …005366 @FLEX 200 | 128 / 150 | 2027 / 2052 | 2060 / 2081 | 617 / 322 | unchanged |

**Does a continuation-aware MSV remove the apparent RB advantage?**

| RB → QB | target | dynasty |
|---|---|---|
| current MSV prefers the RB | 6 / 7 | 6 / 7 |
| CA prefers the RB | **7 / 7** | 3 / 7 |
| pw prefers the RB | **1 / 7** | **1 / 7** |
| agrees with one-step (season): MSV / CA / pw | 2 / 1 / 7 | 1 / 4 / 6 |
| agrees with one-step (weekly): MSV / CA / pw | **6** / 5 / 3 | 2 / 3 / 5 |
| MSV − pw for the RB / for the QB (mean) | 244 / 108 | 217 / 29 |
| what the continuation does at RB if the QB is taken | same RB later 3 (187 regret); another RB 4 (44) | another RB 6 (443); none 1 (13) |
| re-rank on CA + DA-VORP: picks changed | 0 | 0 |

**Reading.**

* **CA (leave-one-out) does not remove the RB advantage.**
  * In target it cannot: CA = MSV for the RB in 6/7 states. With that RB on the roster, the
    continuation drafts no other RB, so removing him leaves a hole.
  * In dynasty it halves the RB's credit: a FLEX RB slides down and a WR enters FLEX. It flips
    3 of the 6 MSV preferences, but the value term (CA + DA-VORP) still prefers the RB in 6/7.
    DA-VORP alone carries 3 of those, CA and DA-VORP together the other 3.
* **pw removes the RB advantage in both formats.**
  * The RB's MSV is mostly value the continuation would supply otherwise: 244 / 217 points,
    against 108 / 29 for the QB.
  * In target, 3 of those 7 are the continuation drafting **the same RB** later. That is D115's
    sequencing (C2), not an MSV construction problem.
  * pw's agreement with one-step value (7/7, 6/7) is by construction (§2).
* **On the weekly objective Alpha's RB is better in 5/7 target RB→QB states.** Current MSV
  agrees with weekly value in 6/7. The target RB→QB "error" is largely a season-long-objective
  phenomenon.

## 5. RB → WR deep dive (target; dynasty in `d122_summary.json`)

| state | Alpha / Oracle | proj A/O | MSV A/O | DA-VORP A/O | CA A/O | CA replacement for A | CA replacement for O | pw A/O | one-step A/O | weekly A/O |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021 s7 R2 | RB …7b5fa6 / WR …c5e0f4 | 373 / 339 | 373 / 339 | 264 / 210 | 263 / 169 | WR @FLEX 110 | WR @FLEX 170 | 373 / 590 | 2051 / 2147 | 2081 / 1953 |
| 2021 s10 R2 | RB …7b5fa6 / WR …69a2f5 | 373 / 440 | 373 / 440 | 264 / 311 | 292 / 330 | RB @RB 81 | WR @FLEX 110 | 292 / 302 | 2040 / 2050 | 2046 / 1983 |
| 2022 s10 R5 | RB …648969 / WR …32da89 | 328 / 227 | 328 / 227 | 239 / 111 | 328 / 47 | none | WR @FLEX 180 | 0 / 0 | 2081 / 2081 | 2122 / 2122 |
| 2023 s1 R1 | RB …a9cafc / WR …981ffd | 391 / 403 | 391 / 403 | 290 / 291 | 387 / 258 | RB @RB 4 | WR @FLEX 145 | 145 / 258 | 2048 / 2162 | 1965 / 1986 |
| 2023 s1 R5 | RB …65cd3f / WR …65d275 | 290 / 298 | 291 / 298 | 188 / 186 | 146 / 89 | WR @FLEX 145 | WR @FLEX 209 (rostered) | 325 / 372 | 2109 / 2156 | 1987 / 1929 |
| 2023 s7 R3 | RB …65cd3f / WR …e40dab | 290 / 286 | 290 / 286 | 188 / 174 | 184 / 142 | RB @RB 106 | WR @FLEX 145 | 48 / 60 | 2045 / 2056 | 1940 / 1966 |
| 2023 s7 R4 | same pair | 290 / 286 | 290 / 286 | 188 / 174 | 184 / 142 | RB @RB 106 | WR @FLEX 145 | 89 / 136 | 2043 / 2090 | 1940 / 1983 |
| 2023 s7 R6 | RB …65cd3f / WR …23c7ba | 290 / 282 | 290 / 282 | 188 / 169 | 123 / 138 | RB @RB 167 | WR @FLEX 145 | 123 / 74 | 2111 / 2127 | 2034 / 2014 |
| 2023 s10 R3 | RB …65cd3f / WR …65d275 | 290 / 298 | 290 / 298 | 188 / 186 | 184 / 148 | RB @RB 106 | WR @FLEX 150 | 48 / 130 | 2036 / 2118 | 1944 / 1894 |
| 2023 s10 R5 | same pair | 290 / 298 | 290 / 298 | 188 / 185 | 140 / 148 | WR @FLEX 150 | WR @FLEX 150 | 291 / 298 | 2135 / 2143 | 2101 / 1943 |
| 2024 s1 R4 | RB …648969 / WR …749143 | 293 / 284 | 293 / 284 | 180 / 148 | 293 / 162 | none | WR @FLEX 122 | −24 / 178 | 2087 / 2304 | 2147 / 2250 |
| 2024 s1 R5 | same pair | 293 / 284 | 293 / 284 | 180 / 146 | 293 / 162 | none | WR @FLEX 122 (rostered) | −24 / 178 | 2087 / 2304 | 2147 / 2250 |
| 2024 s4 R4 | same pair | 293 / 284 | 293 / 284 | 180 / 148 | 260 / 162 | RB @RB 34 | WR @FLEX 122 | 39 / 100 | 2134 / 2225 | 2221 / 2270 |
| 2024 s4 R5 | RB …d7d7f4 / WR …749143 | 267 / 284 | 267 / 284 | 153 / 148 | 233 / 144 | RB @RB 34 | WR @FLEX 140 | 13 / 100 | 2206 / 2324 | 2214 / 2293 |
| 2025 s1 R1 | RB …a9cafc / WR …65d275 | 417 / 375 | 417 / 375 | 316 / 259 | 247 / 205 | RB @RB 170 | RB @FLEX 170 | 137 / 152 | 2244 / 2259 | 2265 / 2306 |
| 2025 s1 R4 | RB …d7d7f4 / WR …e40dab | 302 / 172 | 302 / 172 | 202 / 44 | 135 / 5 | RB @FLEX 167 | RB @FLEX 167 | 0 / 0 | 2054 / 2054 | 2101 / 2101 |

| RB → WR | target | dynasty |
|---|---|---|
| current MSV prefers the RB | 10 / 16 | 3 / 8 |
| CA prefers the RB | **13 / 16** | 4 / 8 |
| pw prefers the RB | **1 / 16** | 2 / 8 |
| agrees with one-step (season): MSV / CA / pw | 6 / 3 / 15 | 5 / 4 / 6 |
| agrees with one-step (weekly): MSV / CA / pw | 4 / 3 / 11 | 5 / 6 / 4 |
| CA / MSV for the RB · for the WR (mean) | 0.7 · **0.5** | 0.6 · **0.4** |
| MSV − pw for the RB / for the WR (mean) | 200 / 120 | 235 / 192 |
| re-rank: picks changed / to a WR | 1 / 0 (RB→RB, −53) | 3 / 0 (RB→RB, +97) |

**Flex, answered from the allocator rather than assumed from position.**

* **The WR's replacement enters through FLEX in every state:** 16/16 target, 8/8 dynasty.
  * It is a WR in 14/16 target states; in 2 it is an RB.
  * The oracle's WR himself lands in a dedicated WR slot 14/16 and in FLEX 2/16.
* **The RB's replacement is split:**
  * a dedicated RB 9/16, FLEX 4/16, and none 3/16 in target;
  * where it is FLEX, a FLEX RB slides into the RB slot and a WR enters FLEX.
* **A second WR slot is never empty in these states.** Two WR slots plus two FLEX mean the
  continuation's later WRs start at FLEX. Leave-one-out therefore charges the WR a cheap
  replacement (CA/MSV 0.5) and the RB a dearer one (0.7).
* **Consequence:** CA makes the RB look *better* relative to the WR than MSV does (G_CA −63,
  CI [−163, +12]). pw makes it look worse (G_pw +80, CI [+46, +141]).
* **On pairwise slot deltas**, taking the RB instead of the WR loses 55.5 FLEX points and 84.1
  WR-slot points (target mean), and gains 81.3 RB-slot points.
* **Where the continuation refills the RB position** when the WR is taken:
  * another RB 12/16 (986 regret), none 2/16 (103), the same RB later 2/16 (0) in target;
  * 7/8, 1 same-RB-later in dynasty.
* **The "empty WR slot" is not decisive in any state**, because the continuation always refills
  it through FLEX. Neither is the "empty RB slot" in most states. **Both players' MSV is
  largely value the continuation would supply otherwise.** In the RB's case it is more
  (200 vs 120 target, 235 vs 192 dynasty), and the two exact continuation-aware measures
  disagree on the sign of the net effect.

## 6. Agreement analysis (2 × 2 against one-step roster value)

Cells show states, % of the population, and regret. "Term → Alpha" means the term prefers
Alpha's pick; "1-step → Oracle" means one-step roster value prefers the oracle's player.

**Target, primary (23 states)**

| term | term → Alpha, 1-step → Oracle (**critical**) | term → Oracle, 1-step → Oracle | term → Alpha, 1-step → Alpha | ties |
|---|---|---|---|---|
| current MSV | **13 (57%), 962** · term gap +52 / med +34 · 1-step gap −74 / med −38 | 7 (30%), 447 | 1, −89 | 2 one-step ties, 0 |
| CA | **17 (74%), 1,374** · +95 / +111 · −81 / −69 | 3 (13%), 35 | 1, −89 | 2 one-step ties, 0 |
| pw | **1 (4%), 16** · +49 · −16 | 19 (83%), 1,393 | 1, −89 | 2 both tied, 0 |
| MSV + DA-VORP (shipped) | 13, 962 | 7, 447 | 1 | 2 |
| CA + DA-VORP | 18, 1,391 | 2, 18 | 1 | 2 |
| pw + DA-VORP | 5, 107 | 15, 1,302 | 1 | 2 |

**Dynasty, primary (15 states)**

| term | critical | term → Oracle, 1-step → Oracle |
|---|---|---|
| current MSV | **9 (60%), 820** · term gap +123 / med +151 · 1-step gap −91 / med −75 | 6, 537 |
| CA | **7 (47%), 486** · +111 / +33 · −69 / −51 | 8, 871 |
| pw | **3 (20%), 253** · +68 / +41 · −84 / −116 | 12, 1,104 |
| MSV + DA-VORP | 9, 820 | 6, 537 |
| CA + DA-VORP | 11, 922 | 4, 434 |
| pw + DA-VORP | 6, 534 | 9, 822 |

**Weekly critical cell** (term → Alpha, weekly one-step → Oracle):

| | MSV | CA | pw |
|---|---|---|---|
| target | 7, 709 | 10, 1,009 | 0 |
| dynasty | 5, 440 | 3, 141 | 1, 116 |

**All R1–6 wrong-position (secondary)** critical cell, MSV / CA / pw:

| | MSV | CA | pw |
|---|---|---|---|
| target (52) | 32, 2,603 | 28, 2,328 | 7, 375 |
| dynasty (43) | 29, 2,326 | 20, 1,508 | 7, 471 |

**The key metric.** Does the continuation-aware term shrink "MSV prefers Alpha but one-step
prefers Oracle"?

* **CA:** target primary **no** (13 → 17); dynasty primary yes (9 → 7); secondary target and
  dynasty both yes (32 → 28, 29 → 20). With DA-VORP added it does not shrink the primary cell in
  either format (13 → 18, 9 → 11).
* **pw:** yes everywhere, by construction.

## 7. Quantifying the correction

Gap = P minus O; error = gap − one-step gap.

| primary, season-long | target MAE / sign agree / Spearman | dynasty |
|---|---|---|
| current MSV | 99.6 / 8 of 23 / +0.24 | 153.5 / 6 of 15 / +0.42 |
| CA | 149.8 / 4 / −0.32 | 124.0 / 8 / +0.16 |
| pw | 26.4 / 22 / +0.86 | 57.0 / 12 / +0.51 |
| MSV + DA-VORP | 133.5 / 8 / +0.27 | 186.8 / 6 / +0.29 |
| CA + DA-VORP | 185.7 / 3 / −0.21 | 157.3 / 4 / +0.25 |
| pw + DA-VORP | 47.0 / 16 / +0.84 | 80.0 / 9 / +0.34 |

Mean errors are all positive: every term prefers Alpha more than one-step value does. That is
partly selection, because the population is chosen for positive regret.

**Overstatement and |error| reduction, season-clustered.** G = MSV gap − term gap. MDE is shown
as CI half-width / 80%-power paired MDE.

| | k | G_CA mean [CI] (MDE) | G_pw mean [CI] (MDE) | \|err\| reduction MSV→CA | \|err\| reduction MSV→pw |
|---|---|---|---|---|---|
| target RB→QB | 2 | −38 [−1825, +1559] | +137 [−1195, +1327] | −29 | +76 |
| target RB→WR | 5 | −63 [−163, +12] (87 / 117) | **+80 [+46, +141]** (47 / 63) | −60 [−162, +23] | **+72 [+22, +138]** |
| target primary | 5 | −56 [−103, +2] (52 / 70) | +97 [+40, +166] (63 / 84) | −50 [−97, +12] | +73 [+21, +133] |
| dynasty RB→QB | 1 | +138 (no CI) | +189 (no CI) | +138 | +157 |
| dynasty RB→WR | 3 | −65 [−149, +85] | +44 [−114, +216] | −65 | +44 |
| dynasty primary | 3 | +30 [−251, +268] | +111 [−175, +315] | +30 | +97 |
| target all R1–6 wrong-position | 5 | −7 [−53, +45] | +84 [+0.4, +155] | −16 [−61, +37] | +69 [−6, +134] |
| dynasty all R1–6 wrong-position | 5 | +33 [−36, +86] | +108 [+11, +180] | +27 [−52, +86] | +80 [−54, +174] |

**Every G_pw interval that excludes zero is near-circular.** G_pw = (MSV gap − one-step gap)
+ spillover, and spillover is small (target primary mean +7, median 0). For target RB→WR, G_pw
+80 ≈ MSV's mean error +83 − 2. It says "MSV prefers the RB more than one-step value does on
states chosen because one-step value preferred the WR". It does not say that from outside.

## 8. Counterfactual re-rank (diagnostic, not a production experiment)

The value term is CA + unchanged DA-VORP; OC / fit / risk / survival / capacity are untouched.
The argmax is exact over the whole board, taking 3.8 / 3.0 rollouts per state on average.

| target (120 R1–6 states) | n | changed | → oracle | improved / worse | Δ season | Δ weekly | regret before → after |
|---|---|---|---|---|---|---|---|
| primary RB→QB | 7 | **0** | 0 | 0 / 0 | 0 | 0 | 231 → 231 |
| primary RB→WR | 16 | 1 (RB→RB) | 0 | 0 / 1 | −53 | +14 | 1,089 → 1,142 |
| other wrong-position | 29 | 13 | 9 | 11 / 2 | +994 | +1,138 | — |
| same position / agrees | 68 | 9 | 1 | 3 / 6 | −264 | +85 | 544 → 808 |
| **all R1–6** | 120 | 23 | 10 | 14 / 9 | **+677** | +1,237 | 4,208 → 3,531 |

| dynasty (120 R1–6 states) | n | changed | → oracle | improved / worse | Δ season | Δ weekly | regret before → after |
|---|---|---|---|---|---|---|---|
| primary RB→QB | 7 | **0** | 0 | 0 / 0 | 0 | 0 | 456 → 456 |
| primary RB→WR | 8 | 3 (RB→RB) | 0 | 2 / 1 | +97 | +33 | 901 → 804 |
| other wrong-position | 28 | 10 | 3 | 4 / 6 | −228 | +52 | — |
| same position / agrees | 77 | 7 | 0 | 0 / 7 | −580 | −678 | 584 → 1,164 |
| **all R1–6** | 120 | 20 | 3 | 6 / 14 | **−711** | −594 | 3,997 → 4,708 |

**Per-state Δ and season-clustered CIs** (k = 5; MDE as half-width / 80%-power):

| | target | dynasty |
|---|---|---|
| all R1–6, season-long | +5.6 [−6.2, +17.4] (11.8 / 15.8) | **−5.9 [−11.4, −0.4]** (5.5 / 7.4) |
| all R1–6, weekly | +10.3 [−7.6, +28.3] | −4.9 [−12.7, +2.8] |
| primary, season-long | −2.3 [−5.0, +2.4] (3.7 / 5.0) | +6.5 [−17.8, +28.6] (23.2 / 28.9) |
| primary, weekly | +0.4 [−0.6, +1.3] | +1.8 [−6.1, +9.8] |

**Flips.**

* **Oracle-direction** (new pick has the oracle's position, Alpha's did not): 9 target / 4
  dynasty, none in the primary population.
* **Reverse-direction** (Alpha had the oracle's position, the new pick does not): 7 / 7. All 7 in
  dynasty are losses.
* The flips run mostly **toward RBs**: QB→RB 8 / 5 and WR→RB 6 / 5. CA discounts a QB whose
  replacement is an already-rostered QB, and a WR whose replacement enters cheaply through FLEX.

**By season (all R1–6, season-long Δ):**

| season | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| target | −106 | +165 | +69 | +504 | +44 |
| dynasty | +32 | −196 | −144 | −253 | −151 |

**By round:** target gains sit in R2–3 (+328, +324); dynasty's losses sit in R2 (−459).

**Moving picks toward the oracle is not claimed as improvement; only realized value is.** On the
primary population the re-rank moves no pick to the oracle's player or position in either
format. Across all R1–6 it helps target by an unresolved +5.6/state and **hurts dynasty
(−5.9/state, CI excludes 0)**.

## 9. MSV vs DA-VORP decomposition

| primary | target | dynasty |
|---|---|---|
| sign agreement with one-step: MSV / CA / pw / DA-VORP alone | 8 / 4 / 22 / 2 | 6 / 8 / 12 / 1 |
| term disagrees in sign with DA-VORP: MSV / CA / pw | 6 / 4 / **20** | 5 / 7 / **11** |
| DA-VORP gap (RB − WR/QB), mean | +31.7 | +33.3 |
| value term still prefers Alpha wrongly after CA / after pw | 18 (1,391) / 5 (107) | 11 (922) / 6 (534) |
| … of those, DA-VORP alone carries it (CA / pw) | 1 / **4** | 4 / 3 |
| … CA / pw and DA-VORP both favour Alpha | 16 / 1 | 7 / 3 |

1. **Does it fix the ranking by itself?**
   * CA: no. It agrees with one-step value in 4/23 and 8/15 states, against MSV's 8/23 and 6/15.
   * pw: 22/23 and 12/15, by construction.
2. **Does it create disagreement with DA-VORP?** pw does, in 20/23 and 11/15 states: DA-VORP
   also prefers the RB (+32 / +33 on average). CA does not (4/23, 7/15).
3. **Is DA-VORP left as the dominant remaining source?**
   * Under pw, yes: of the few states still wrong, DA-VORP alone carries 4 of 5 (target) and
     3 of 6 (dynasty).
   * Under CA, no: CA itself favours Alpha in 17 of the 18 target states still wrong, together
     with DA-VORP in 16.

## 10. Starter-slot counterfactual (empty-slot cases)

Every Alpha RB in the primary population fills an empty slot: MSV = projection in 23/23 target
and 15/15 dynasty states. For those, projection − the continuation-aware term is:

| | projection − CA | projection − pw | CA < projection | pw < projection |
|---|---|---|---|---|
| target RB (23) | mean 60, median 34, [0, 170] | mean 213, median 247, [−34, 328] | 14 / 23 | 20 / 23 |
| dynasty RB (15) | mean 132, median 146, [0, 202] | mean 227, median 226, [0, 458] | 14 / 15 | 14 / 15 |
| target oracle player, empty slot (17) | mean 157, median 145 | mean 129, median 169 | 17 / 17 | 14 / 17 |
| dynasty oracle player, empty slot (9) | mean 171, median 173 | mean 193, median 209 | 9 / 9 | 9 / 9 |

These are continuous quantities, with no materiality threshold. The empty-slot credit differs
from what the continuation would otherwise supply in almost every state, **and on both sides of
the pair**. The oracle's player's MSV is also mostly supplied otherwise. The question that
matters, whether the *difference* between the sides favours the RB, is exactly what G measures:
§7 shows it is either unresolved (CA) or near-circular (pw).

**How the continuation supplies it** (CA replacement's origin, primary):

| | drafted later by the continuation | already rostered at this pick | none (slot left empty) |
|---|---|---|---|
| target RB | 14 | 0 | 9 |
| target oracle player | 15 | 8 (6 are RB→QB's rostered QB) | 0 |
| dynasty RB | 13 | 1 | 1 |
| dynasty oracle player | 9 | 6 | 0 |

The brief's four cases map onto this as follows:

* **scarce need:** the "none" column;
* **continuation fills easily:** a replacement drafted later by the continuation;
* **changes which later player starts:** a FLEX entrant with a reshuffle — 8 of 15 dynasty RBs,
  4 of 23 target RBs;
* **redundant with a rostered player:** the QB side of RB→QB, 6/7 in both formats.

## 11. Statistical notes

* Season-clustered t intervals with k = number of seasons present. MDE is the CI half-width and
  the 80%-power paired MDE; the old 172–250 floor is not reused.
* The RB→QB populations cannot support any interval: target k = 2, dynasty k = 1, 3 distinct
  decisions each.
* Round tables are in `d122_summary.json`; they are too thin to read, at 1–7 states per round
  per flow.
* The only interval in D122 that excludes zero and is not construction-driven is the dynasty
  all-R1–6 re-rank: **−5.9/state, CI [−11.4, −0.4]**. The CA re-rank is worse than shipped there.

## 12. Structural interpretation

| rule (pre-registered, §PRE-REGISTRATION in the runner) | CA (pre-registered) | pw (amended) |
|---|---|---|
| overcredit supported: RB→QB target / dynasty | no / no | no (k = 2) / no (k = 1) |
| overcredit supported: RB→WR target / dynasty | no / no | **yes** / no |
| decision-relevant (primary re-rank CI > 0 and weekly > 0): target / dynasty | no / no | same test: no / no |
| **letter** | **C** | **B** |

**Reading the two letters together.**

* **C under the pre-registered measure.** The exact per-candidate continuation-aware MSV that
  existing machinery supports is not better aligned with one-step value than current MSV. In
  target it is worse, and a rule built on it does not move the primary picks.
* **B under the amended measure, and weaker than B looks.** Its one supported cell is
  near-circular (§7). The pw quantity is defined only for a pair: turning it into a decision rule
  needs a reference pick for every candidate, which is a new algorithm this brief forbids.
* **The mechanism differs between the two flows (the substance of D, though the D rule is not
  met).**
  * RB→QB: the continuation does not replace the RB when it has him, but does when it takes the
    QB. The QB side is an upgrade over an already-rostered QB.
  * RB→WR: the continuation refills both positions, and the WR side cheaply through FLEX.
  * CA and pw disagree in sign on RB→WR.
* **E is the honest description of the RB→QB question specifically.**
  * Leave-one-out cannot see the "otherwise" RB.
  * The pairwise measure sees him but is one-step value re-expressed.
  * The population is three 2022 decisions, three of seven target states are sequencing, and
    the weekly objective reverses five of seven.

**Overall.** MSV's empty-slot credit is, as a matter of arithmetic, mostly value the fixed
continuation would supply otherwise — for both players in the pair. No evidence here shows that
this is *why* Alpha takes the RB, in a way that holds across seasons, survives the weekly
objective, or yields a rule that realizes more value.

## 13. Decision

**No production change recommended.** Nothing is tuned; `src/alpha_squad/` is byte-identical.

**This branch is closed.** No D123 is proposed. Re-opening it would need all of the following:

* **(a)** a decision-time definition of "what the continuation would otherwise field" for *every*
  candidate, not just a pair. That is a new valuation algorithm and must be pre-registered as
  such.
* **(b)** an RB→QB population spanning more than one season.
* **(c)** a re-rank that passes the pre-registered decision-relevance test in both formats
  without the reverse-direction losses seen here.

## 14. Provenance

**Code and board**

| item | value |
|---|---|
| git HEAD at run | `c33ff3490f081200ef0fe7f50e38aa9f5cbffd60` (D121), `src_dirty = false` |
| `src/alpha_squad` tree | `55e763e8a80af908a2c2bcc0ae66753c16b629fc` |
| D120 commit / D121 commit | `2c8a78f8` / `c33ff349` |
| board vintage (combined) | `f00226015095534f22e1311c8fa1b4823d66e0679ef6fa8f1817500209dce89f` |
| per season | 2021 `79599ffa…` · 2022 `43f0e968…` · 2023 `aa73cd3f…` · 2024 `7873284c…` · 2025 `0b344c7e…` |
| upstream board / ID map | `e270d790…` / `36016b92…` |

**Inputs (sha256)**

| file | sha256 |
|---|---|
| D120 arms, target | `f032a3d1a238158cf55c067e6e7a6291b2b08b5a325b35d15cfb7edfeed77dc0` |
| D120 arms, dynasty | `258d3b5f31c04179edc986c5a24fadb69b1c79073afc58b568c72f8f1b4af16a` |
| D121 measured, target | `6ea623de2ead54f3a026f55ee298593859bb29216cb21370de1445053a9441cd` |
| D121 measured, dynasty | `236c565c9233082db9e9258918d862f46225db8fa88c9841e545e6261fc362c2` |
| D115 target: regret / timing / arms | `6d395458…` / `a8b44df6…` / `b259beba…` |
| D115 dynasty: regret / timing / arms | `ee4921c5…` / `72308875…` / `72c5d74c…` |

**Outputs (sha256)**

| file | sha256 |
|---|---|
| `d122_measured_target_league.json` | `9d5ebee03a19382dac53b557fe094a89a26dd4f38674fa97874def6c9fe710c2` |
| `d122_measured_dynasty_1qb.json` | `17437ee2656c341bd0fb0996550dc49ac30aea359f040b9f7c451f2effd4cb25` |
| `d122_summary.json` | `cdd76c2a39822f9ae5ad568e6e9262f12a9ce1583d60db725eae492ee9aaaf0c` |

**Reproduce**

```
uv run python scripts/research/d122_continuation_aware_msv.py --mode measure \
    --leagues target_league --d115 <d115 target dir> --d120 <d120 dir> --d121 <d121 dir> --out <o>
uv run python scripts/research/d122_continuation_aware_msv.py --mode measure \
    --leagues dynasty_1qb --d115 <d115 dynasty dir> --d120 <d120 dir> --d121 <d121 dir> --out <o>
uv run python scripts/research/d122_continuation_aware_msv.py --mode report --out <o>
```

Runtime is about 5 minutes per format.
