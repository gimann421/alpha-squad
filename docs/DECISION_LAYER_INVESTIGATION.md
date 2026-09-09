# Decision-layer investigation — replacement level and marginal value (D84)

What does "replacement level" and "marginal value" actually mean inside Alpha, and is the
current formulation economically sound? Everything below runs the real production path
(`league/draft.py::recommend_draft_pick`) on the real board; the decomposition recomputes every
term with the same production functions and **asserts** the reassembled score equals the
production score to 1e-6, aborting rather than reporting if it does not.

**Nothing in `src/` has been changed by this investigation.**

Prior art this builds on rather than repeats: D63 selected the `msv + VORP` value base against a
*static* replacement level; D67 replaced that level with the draft-aware demand boundary; D79
re-measured the value base on top of D67 (the Z-tiers) and **every alternative lost in both
league formats**. D79 also already named the algebraic mechanism below. What is new here is the
separation of that mechanism into **two independent defects**, the measurement of their relative
severity per position, and the observation that the one axis nobody has varied is the *demand
target itself*.

---

## 1. The scoring function, exactly

```
value_base = msv(c)  +  1.0 · daVORP(c)
score      = (value_base + oc(pos)) × fit × risk × survival × [0.1 if over cap]
```

where `msv(c) = lineup(roster + c) − lineup(roster)` and `daVORP(c) = proj(c) − R_consumption(pos)`.

---

## 2. Phase 1 — first pick at every position (2026, slot 1, fair opponents)

Roster produced: `WR, QB, TE, RB, RB, WR, RB, WR, K, DST, QB, WR, WR, K, DST, TE`.

| first | round | pick | player | proj | MSV | daVORP | R | oc | fit | risk | surv× | score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WR | 1 | #1 | Ja'Marr Chase | 284.7 | 284.7 | 177.0 | 107.7 | 72.3 | 1.20 | 0.78 | 1.30 | 651.0 |
| QB | 2 | #20 | Josh Allen | 361.9 | 361.9 | 168.1 | 193.8 | 0.0 | 1.10 | 0.72 | 1.00 | 421.8 |
| TE | 3 | #21 | Trey McBride | 212.3 | 212.3 | 89.9 | 122.4 | 63.4 | 1.10 | 0.79 | 1.18 | 375.7 |
| RB | 4 | #40 | Jeremiyah Love | 243.9 | 243.9 | 144.8 | 99.1 | 0.0 | 1.20 | 0.70 | 1.11 | 362.6 |
| K | 9 | #81 | Brandon Aubrey | 182.4 | 182.4 | 42.0 | 140.4 | 0.0 | 1.10 | 0.70 | 1.00 | 172.8 |
| DST | 10 | #100 | SEA D/ST | 110.8 | 110.8 | 15.6 | 95.2 | 0.0 | 1.10 | 0.70 | 1.00 | 97.3 |

**`MSV == proj` in every single row.** That is the whole story in one column.

---

## 3. Defect 1 — MSV is a step function of slot occupancy, not of replaceability

Measured across four roster states, `marginal_starter_value(c)` equals `proj(c)` **exactly**
whenever `c` fills an empty lineup slot, and collapses to `0.0` once the position is saturated.
It never asks how much better `c` is than the body obtainable later. So when a slot is empty:

```
value_base = proj(c) + (proj(c) − R_p) = 2·proj(c) − R_p
```

The engine is adding **two surpluses measured against two different baselines**: MSV's implicit
baseline of **0** (an empty slot scores nothing) and daVORP's baseline of `R_p`. The quantity
that asks the relevant question — how much better is `c` than the body I could have in that slot
instead — is `msv(c) − msv(replacement body) = proj(c) − R_p`. The current base exceeds it by
exactly `proj(c)`, an **amplification**

```
A_p(c) = (2·proj − R_p) / (proj − R_p) = 1 + proj/(proj − R_p)
```

which diverges as `R_p → proj`. **The flatter the position, the more the engine over-values
taking one.** Measured on the real 2026 board, for the best available player at each position:

| pos | best available | proj | R | correct (proj−R) | current (2proj−R) | amplification |
|---|---|---|---|---|---|---|
| DST | SEA D/ST | 110.8 | 95.2 | 15.6 | 126.4 | **8.10×** |
| K | Brandon Aubrey | 182.4 | 140.4 | 42.0 | 224.4 | **5.34×** |
| TE | Trey McBride | 212.3 | 122.4 | 89.9 | 302.2 | 3.36× |
| QB | Josh Allen | 361.9 | 193.8 | 168.1 | 530.0 | 3.15× |
| WR | Ja'Marr Chase | 284.7 | 107.7 | 177.0 | 461.7 | 2.61× |
| RB | Christian McCaffrey | 266.2 | 99.1 | 167.1 | 433.2 | 2.59× |

**This ranking — DST > K > TE > QB > WR > RB — reproduces the observed pathology ranking, and it
was derived from the algebra rather than fitted to the symptom.**

---

## 4. Defect 2 — the value term's replacement level uses *consumption* demand

Both demands, computed from the league's own config on the real board:

| pos | S_p starter demand | C_p consumption demand | C/S | league S | league C |
|---|---|---|---|---|---|
| QB | 1.00 | 2.20 | **2.20×** | 10 | 22 |
| RB | 2.40 | 4.20 | 1.75× | 24 | 42 |
| WR | 3.60 | 5.80 | 1.61× | 36 | 58 |
| TE | 1.00 | 1.80 | 1.80× | 10 | 18 |
| K | 1.00 | 1.00 | **1.00×** | 10 | 10 |
| DST | 1.00 | 1.00 | **1.00×** | 10 | 10 |
| **total** | **10.00** | **16.00** | | 100 | 160 |

`S` sums to the starting-lineup size (10); `C` sums to `roster_size` (16), by construction. The
replacement level each implies, and the surplus D67's choice handed every player:

| pos | starter-demand R | who | consumption R | who | surplus added |
|---|---|---|---|---|---|
| QB | 265.2 | Jaxson Dart | 193.8 | Sam Darnold | **−71.4** |
| RB | 158.3 | Rico Dowdle | 99.1 | Tyler Allgeier | −59.2 |
| WR | 158.3 | Terry McLaurin | 107.7 | Tre Tucker | −50.5 |
| TE | 133.2 | Jake Ferguson | 122.4 | Hunter Henry | −10.8 |
| K | 140.4 | Wil Lutz | 140.4 | Wil Lutz | 0.0 |
| DST | 95.2 | LAC D/ST | 95.2 | LAC D/ST | 0.0 |

**The two defects are independent and hit different positions.** K and DST have `C == S`, so
D67's demand choice changed nothing for them — their problem is *purely* Defect 1, and it is
extreme (5.3×, 8.1×). QB has the largest `C/S` of any position, so it suffers *both*: the
double-count **and** a replacement level 71.4 points below its starter boundary.

### The economic argument

Value in this game is realised only through starting lineups — the benchmark's primary metric is
realized **starter** points, and `CLAUDE.md` states the objective as expected realized starter
points. A quarterback drafted 21st in a 10-team 1-QB league never starts for anyone. Pricing
every QB's surplus against QB21 therefore credits each of them with beating a player who
contributes zero to any lineup. The marginal *starting* quarterback is QB10–11.

The honest resolution is that **the two demands answer different questions and the engine needs
both**: starter demand bounds the *lineup contribution* a position can deliver; consumption
demand describes the *acquisition timing* — when the position actually leaves the board. The
current formulation uses consumption demand for the value term, which over-credits exactly those
positions where `C ≫ S`.

---

## 5. Phase 3 — the kicker contradiction, quantified

In one consensus mock draft of this league, **kickers go at overall picks 145–160** and defenses
at 133–156. Alpha takes its kicker at **#81** — 64 picks early.

Measured on Alpha's own board, Brandon Aubrey is still the best kicker available at picks 81,
100, 120 **and 141**, and the engine's own survival model gives him `P(survive) = 1.00` through
#120 and **0.81 at #141**.

So the engine knows he will be there. It cannot act on it:

```
survival_mult = 1.0 + 0.3 · (1 − P(survive))   ∈  [1.0, 1.3]
```

A player **certain to survive** scores exactly `1.0×`. The term can only *add* urgency, never
subtract it. **There is no factor anywhere in the score that says "you can have him later for
free."** Certainty of future availability is worth precisely nothing, so the 5.34× amplified
value base goes unopposed.

The deeper statement: by round 9 the roster is `WR,QB,TE,RB,RB,WR,RB,WR` and every startable
slot except K and DST is full. A fourth receiver genuinely adds **0** to the current starting
lineup while the kicker adds 182.4. MSV is answering *"what does this add to my lineup right
now"* correctly — but the right question is *"what does this add to my final 16-man roster's
lineup"*, and with eight picks left and kickers not leaving the board until #145, the answer for
the kicker is approximately zero. **The engine has no multi-pick planning view.**

---

## 6. Phase 8 — the snake turn UNMASKS the distortion, it does not cause it

At pick #20 `picks_until_next_turn == 0`, so every opportunity cost is exactly 0 — correct
behaviour, not a bug. Counterfactual: score the identical pick-20 board with the opportunity
costs that *would* apply if 18 opponents picked in between, changing nothing else.

| pos | candidate | proj | msv | daVORP | value base | oc(18) | base+oc |
|---|---|---|---|---|---|---|---|
| QB | Josh Allen | 361.9 | 361.9 | 168.1 | **530.0** | 0.0 | **530.0** |
| WR | Puka Nacua | 282.3 | 282.3 | 174.5 | 456.8 | 69.8 | 526.6 |
| RB | C. McCaffrey | 266.2 | 266.2 | 167.1 | 433.2 | 22.3 | 455.5 |
| TE | Trey McBride | 212.3 | 212.3 | 89.9 | 302.2 | 0.0 | 302.2 |
| K | Brandon Aubrey | 182.4 | 182.4 | 42.0 | 224.4 | 0.0 | 224.4 |
| DST | SEA D/ST | 110.8 | 110.8 | 15.6 | 126.4 | 0.0 | 126.4 |

**QB wins either way.** With the opportunity cost restored the margin collapses from +73.2 to
+3.4, so the term substantially offsets the distortion without reversing it.

**Verdict: primarily (C) MSV/daVORP double-counting, with (D) a real interaction.** The turn is
not the cause; it removes the one term that would otherwise nearly cancel the effect. Note that
`oc` is also the wrong shape for the job: it is denominated in *static* season-long VORP while
the value base it offsets is draft-aware, a scale mismatch open since D60.

---

## 7. Why the obvious fix is already known to fail

Defect 1's textbook correction is `msv_over_replacement = msv(c) − msv(replacement body)`, which
reduces to `proj − R` on an empty roster and to `0` at a saturated position. The codebase's own
`replacement_marginal_starter_values` docstring identifies it as the principled unification.

**It has been measured twice and lost both times**: as D63's tier N3 against the static level,
and as D79's tier **Z2 against D67's draft-aware level — −44.4 starter points in the target
format and −75.8 in `legacy_2qb_dynasty`.** Z1 (daVORP alone) lost −34.6/−58.5 and Z3
(`min(daVORP, msv)`) lost −39.4/−31.3. Every alternative lost, in both formats.

So the economically cleaner formulation drafts **worse**. Any candidate proposed here must
reckon with that, and "it is more principled" is not evidence.

### And the fix Defect 2 implies has also already failed

My first reading of the tier history was that the demand target had never been varied. **That is
wrong, and the correction matters more than the original claim.** D67's W-tiers varied exactly
that, and `W0` — static replacement via `replacement_level()`, which allocates dedicated plus
earned flex slots and *is* the starter-demand boundary — was the control. `W1` (consumption)
**beat it by +32.1 starter points, 95% CI [+11.5, +52.7]**, and by +75.5 [+38.6, +112.3] in
`legacy_2qb_dynasty`.

So the economic argument in §4 — that replacement should sit at the starter boundary because only
starters score — has already been put to the benchmark in close to its natural form, and it lost.
A draft-aware starter-boundary level is not *identical* to W0 (W0 never updates as the pool
depletes, which D67 measured as +178.2 too high for QB by round 13), but §4's own measurement
shows the draft-aware level is constant until roughly pick 120, so the two agree exactly where
the QB decision at #20 is made. **Candidate B below is therefore not proposed.**

### What is actually still untested

Two things, and only two:

1. **`msv_over_replacement + daVORP`** — no tier has this. Every arm that removed the raw
   projection (Z1, Z2, Z3) also *halved the scale of the value base* against a fixed opportunity
   cost, so "remove raw projection" and "halve the scale" are perfectly confounded in the
   existing evidence. This arm separates them.
2. **A survival term that can discount as well as urge.** `S_TIER_SPEC` swept the coefficient
   over {0.0, 0.15, 0.3, 0.6, 1.0} — all non-negative, so `survival_mult ≥ 1.0` in every arm ever
   run. Nothing has ever tested letting a player who is *certain* to be available be worth less
   now than later, which is precisely what §5 shows the kicker case needs.

---

## 8. Open question this raises about the control itself

Every prior gate asked whether an *alternative* drafted a position earlier than the control.
**Nothing has ever asked whether the control's own round-9 kicker is costly.** That is directly
measurable without changing the value function — run the production engine and simply decline
K/DST before round 13 — and it is the next thing to establish, because it decides whether the
K/DST behaviour is a genuine defect or merely an odd-looking one.

### 12. Measured: the early K/DST costs nothing, and the danger is elsewhere

Run the production engine unchanged and simply **decline** K/DST before round 13 — an external
constraint applied *after* scoring, so the engine's own numbers are byte-identical between arms
and only the acted-on candidate differs. The deferral round was read off the consensus board
(first K at #145, first DST at #133), not tuned. 50 paired drafts per arm, fair opponent. An
assertion fails the run if the deferral does not actually bind.

*(That assertion earned its place: the first version capped the candidate list at 60 and silently
fell through to the kicker, because at round 10 **all 60 top-ranked candidates were kickers**.)*

| | control | deferred |
|---|---|---|
| mean realized starter points | **2055.9** | 2048.4 |
| paired margin, season-clustered (D71) | — | **−7.6, 95% CI [−70.0, +54.8]** |
| seasons won | — | 2 of 5 |
| slots won | — | 23 of 50 |
| **starters filled** | **10.0** | **10.0** |
| first K / first DST | 8.64 / 10.08 | **13.00 / 14.00** |
| first QB / RB / WR | 2.20 / 4.94 / 1.62 | **2.20 / 4.94 / 1.62** *(identical)* |

The constraint binds perfectly — kickers move five rounds later, defenses four — while every
other position is untouched. **The cost is −7.6 points, indistinguishable from zero.**

Note also that the control's 2055.9 here comes from a completely independent code path (a direct
`recommend_draft_pick` loop) and matches both `Q0` and D79's published `Z0`. Three independent
harnesses, one number.

### The distinction this draws, which the value-base arms could not

| how K/DST is deferred | starter points | mandatory slots filled |
|---|---|---|
| by **constraint** (this probe: defer, but still draft them) | −7.6, CI includes 0 | **10.0 — all filled** |
| by **removing the valuation** (arms C/E) | +3.1 / +4.1, CI includes 0 | **2 and 4 infeasible rosters** |

**Deferring K/DST is free and safe. Removing their valuation is free and dangerous.** The early
kicker is not itself costly — what is costly is having nothing left to guarantee a kicker gets
drafted at all. That is a *scheduling* property, not a *valuation* property, and it is why the
remaining direction below is a constraint question rather than a value question.

---

## 11. Phases 5–6 — the pre-registered candidates, measured

Arms, gates and selection rule were committed in `evaluation/decision_value_base.py` (`d843120`)
and wired as Q-tiers (`6069721`) **before** any of this ran. 4 tiers × 5 seasons × 10 slots = 200
drafts, fair roster-aware opponent.

**The control is provably the shipped engine.** Q0 scores **2055.9**, which is D79's published
`Z0` figure to the decimal, and a test asserts Q0 scores identically to Z0 for every candidate.

| tier | arm | mean starter pts | margin | first QB | first RB | first K | first DST |
|---|---|---|---|---|---|---|---|
| Q3 | E | **2060.0** | **+4.1** | 3.86 | 3.86 | 10.78 | 13.45 |
| Q1 | C | 2059.0 | +3.1 | 3.10 | **3.62** | 10.14 | 12.94 |
| **Q0** | **A (control)** | **2055.9** | — | **2.20** | **4.94** | **8.64** | **10.08** |
| Q2 | D | 2040.7 | −15.2 | 2.74 | 4.90 | 8.98 | 10.24 |

### The behavioural fix works — and is worth nothing

Arm C produces **exactly** the behaviour this investigation set out to find: the first
quarterback moves from round 2.20 to 3.10, the first running back from 4.94 to **3.62**, the
first kicker from 8.64 to 10.14 and the first defense from 10.08 to 12.94. Arm E moves them
further still (QB 3.86, K 10.78, DST 13.45).

It is worth **+3.1 starter points, 95% CI [−128.8, +134.9]**. Arm E is worth +4.1,
CI [−182.4, +190.5]. Both are statistically indistinguishable from zero, and both are an order of
magnitude below the pre-registered 25-point floor.

### The apparent win is one season

| margin vs control | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Q1 (arm C) | −20.8 | −33.6 | −2.4 | **+179.3** | −107.0 |
| Q2 (arm D) | −48.8 | −40.9 | −115.4 | +181.8 | −53.0 |
| Q3 (arm E) | −50.9 | +2.2 | −122.5 | **+260.6** | −69.1 |

Arm C is **worse in four of the five seasons**. The entire +3.1 is 2024. This is precisely the
failure mode Gate 3 exists to catch, and leave-one-season-out confirms it: dropping 2024 turns
arm C's margin to **−41.0** and arm E's to **−60.1**.

### The over-valuation is load-bearing

| tier | TE zeroed | DST zeroed | infeasible rosters |
|---|---|---|---|
| **Q0 (control)** | **0** | **0** | **0** |
| Q1 (arm C) | 2 | 0 | **2** |
| Q3 (arm E) | 1 | **3** | **4** |

The arms that defer K/DST "correctly" **produce rosters that cannot field a legal lineup**. The
control's zero unfilled mandatory slots — the property noted as reassuring at the top of this
investigation — is not independent of the over-valuation. **It is bought by it.** Pricing a
kicker at 5.34× its surplus is what guarantees a kicker gets drafted at all.

### Gate table

| gate | Q1 (C) | Q2 (D) | Q3 (E) |
|---|---|---|---|
| G1 no position zeroed more than control | **FAIL** (TE 2) | pass | **FAIL** (TE 1, DST 3) |
| G2 infeasibility no higher | **FAIL** (2) | pass | **FAIL** (4) |
| G3 ≤1 season worse | **FAIL** (4) | **FAIL** (4) | **FAIL** (3) |
| G4 no position >2 rounds earlier | pass | pass | pass |
| G6 leave-one-season-out | **FAIL** | **FAIL** | **FAIL** |
| G8 season-clustered CI excludes 0 | **FAIL** | **FAIL** | **FAIL** |
| G9 margin ≥ 25 points | **FAIL** (+3.1) | **FAIL** (−15.2) | **FAIL** (+4.1) |

### Gate 7 — cross-format, and the clincher

Rerun unchanged on `legacy_2qb_dynasty`. **Q0 = 2114.5, again matching D79's published `Z0` for
this format to the decimal** — the control is verified in both formats.

| arm | target_league | legacy_2qb_dynasty | seasons won (2QB) | LOSO (2QB) |
|---|---|---|---|---|
| C | **+3.1** | **−29.6** | 2/5 | all negative |
| D | **−15.2** | **+50.8** | 4/5 | all positive (+29.1 … +71.4) |
| E | **+4.1** | **−11.2** | 1/5 | — |

**Both arms flip sign across formats.** Arm C helps marginally in the target format and *hurts* in
2QB; arm D hurts in the target format and is the best result anywhere in 2QB (+50.8, 4 of 5
seasons, leave-one-season-out positive on every held-out season, clearing the 25-point floor) —
yet still fails G8, its 95% CI being [−30.9, +132.5].

A candidate whose sign depends on the format is a format artifact, not an economic principle.
That is exactly what Gate 7 was written to detect, and it is the clinching evidence here.

**No arm ships in either format. `league/draft.py` stays byte-identical.**

---

## 9. Phase 7 — does the distortion move correctly with the league format?

| | | target_league (1-QB) | | | legacy_2qb_dynasty | |
|---|---|---|---|---|---|---|
| pos | S_p | C_p | C/S | S_p | C_p | C/S |
| QB | 1.00 | 2.20 | **2.20×** | 2.00 | 3.90 | 1.95× |
| RB | 2.40 | 4.20 | 1.75× | 2.40 | 4.00 | 1.67× |
| WR | 3.60 | 5.80 | 1.61× | 3.60 | 6.80 | 1.89× |
| TE | 1.00 | 1.80 | 1.80× | 1.00 | 2.30 | **2.30×** |
| K | 1.00 | 1.00 | 1.00× | — | — | — |
| DST | 1.00 | 1.00 | 1.00× | — | — | — |

Starter demand **does** respond correctly to the format: QB rises 1.00 → 2.00 when the league
starts two. So the framework is not a 1-QB artifact.

But the consumption target over-counts in **both** formats, and *which* position it hurts most
moves: QB in the 1-QB league, **TE in the 2-QB league (2.30×)**. And the surplus D67's choice
hands quarterbacks is far larger out of format — `legacy_2qb_dynasty` consumes 39 QBs, putting
replacement at **QB39 = 56.8** against a starter boundary of 214.3, a **−157.5** gift to every
quarterback. That the same mechanism produces a bigger distortion where QBs are genuinely more
valuable is why its net effect cannot be reasoned about, only measured.

---

## 10. Phase 9 — RB layer isolation: the answer is **both B and D**

**(a) The engine amplifies projection error by exactly 2×.** With an empty slot,
`value_base = 2·proj − R`, so `d(value_base)/d(proj) = 2` against `1` for the principled surplus.
Verified numerically on Jonathan Taylor at Δ ∈ {0, +10, +20, +40, +80}: the slope is **2.00 at
every step**. This is uniform across positions — amplifying, not RB-specific. Applied to the
known RB top-10 signed bias of +45.5, the value base carries roughly **91 points** of error.

**(b) There is also a genuinely RB-specific distortion, and it is a dead zone.** Opportunity cost
is computed in *static* VORP units off the board, so under-projecting the elite RBs suppresses
what the engine thinks it costs to lose them — and the response is **threshold-gated**:

| elite-RB cell set to | 169 (Y1) | 210 | 260 | 300 | 320 | 350 | 400 |
|---|---|---|---|---|---|---|---|
| RB opportunity cost | 3.3 | 3.3 | 3.3 | 37.1 | 57.1 | 87.1 | 137.1 |
| d(RB oc)/d(cell) | — | **0.000** | **0.000** | 0.846 | 1.000 | 1.000 | 1.000 |

Below ≈285 the term is **completely insensitive** to the elite-RB projection, then responds
one-for-one. So the decision layer simultaneously **over-reacts** to the RB projection error by
2× in the value base and **under-reacts** to it by 0× in the opportunity-cost term, until a
threshold flips the second on.

**RB is therefore both a projection problem and a decision problem** — and the two interact
non-linearly, which is why neither layer's fix has worked in isolation.
