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

**What has never been varied is the demand target itself.** D66 swept a uniform multiplier on
`startable_slots` (rejected as positional re-weighting in disguise); D67 chose the consumption
boundary; D63/D79 varied the *form* of the value base while holding that boundary fixed. Nobody
has measured the *starter*-demand boundary in the value term. That is the one open axis, and it
is the axis Defect 2 identifies.

---

## 8. Open question this raises about the control itself

Every prior gate asked whether an *alternative* drafted a position earlier than the control.
**Nothing has ever asked whether the control's own round-9 kicker is costly.** That is directly
measurable without changing the value function — run the production engine and simply decline
K/DST before round 13 — and it is the next thing to establish, because it decides whether the
K/DST behaviour is a genuine defect or merely an odd-looking one.

*(Result recorded in §9 once measured.)*
