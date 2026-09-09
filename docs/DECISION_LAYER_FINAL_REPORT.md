# Decision-layer investigation — final report (D84)

Detail and method: `docs/DECISION_LAYER_INVESTIGATION.md`. Decision record: D84 in
`docs/DECISIONS.md`. **`league/draft.py` and `models/` are byte-identical to their Y1 state.**

---

## 1. Executive verdict — is the decision engine economically sound?

**No, and it does not matter as much as it should.**

The value base is unsound in a precisely identifiable way: it adds **two surpluses measured
against two different baselines**. `marginal_starter_value` measures the candidate against an
*empty slot* (baseline 0), `daVORP` measures him against the *consumption-boundary replacement*
(baseline `R_p`), and the engine adds them. Whenever a lineup slot is empty — which is most of
the first ten rounds — the value base is

```
msv + daVORP = proj + (proj − R_p) = 2·proj − R_p
```

so **raw projection is counted twice and scarcity once**. That is not a defensible quantity in
any value-based-drafting framework.

But when the correction is made properly and measured, it is worth **+3.1 starter points, 95% CI
[−128.8, +134.9]**, it is worse in four of five seasons, it flips sign in the other league
format, and it **breaks roster legality**. The unsound term is load-bearing.

So the honest verdict is three-part: **mathematically incoherent, empirically almost free, and
structurally load-bearing.** That combination is why nothing ships.

---

## 2. #20 QB diagnosis — exactly why the quarterback wins

At pick #20 the roster is `[WR]`, `picks_until_next_turn == 0`, so every opportunity cost is
exactly zero — correct behaviour.

| term | Josh Allen (QB) | Jeremiyah Love (best RB) |
|---|---|---|
| projection | 361.9 | 243.9 |
| MSV | **361.9** *(= projection; the QB slot is empty)* | 243.9 |
| DA-VORP | 168.1 *(= 361.9 − 193.8)* | 144.8 *(= 243.9 − 99.1)* |
| value base | **530.0** | 388.7 |
| opportunity cost | 0.0 | 0.0 |
| × roster fit | 1.10 | 1.20 |
| × risk | 0.72 | 0.70 |
| × survival | 1.00 | 1.00 |
| **score** | **421.8** | 326.5 |

**Two terms decide it, and both are the defect.**

1. **Raw projection enters twice.** `msv` contributes Allen's entire 361.9 because nothing but a
   quarterback can fill an empty QB slot. Quarterbacks carry by far the highest raw projections
   on any board, so doubling raw projection is structurally a quarterback subsidy.
2. **Replacement is drawn at the consumption boundary.** A 10-team 1-QB league *consumes* 2.20
   QB per team, putting replacement at **QB22 = 193.8**; it *starts* 1.00, putting the starter
   boundary at **QB11 = 265.2**. That choice adds **+71.4** to every quarterback's surplus. The
   quarterback you would actually roster instead is Hurts at 300.3, so Allen's real marginal
   value is about **61.6**, not the 168.1 credited.

The margin is +95.3. Remove the double count and the quarterback drops behind the running back.
Correcting only the projections cannot: D81 measured that it takes a **−90-point** QB adjustment,
four times the measured QB bias, to dislodge him.

---

## 3. K/DST diagnosis — exactly why they go in rounds 9 and 10

Round 9, pick #81, roster `WR,QB,TE,RB,RB,WR,RB,WR`:

| | Brandon Aubrey (K) | Courtland Sutton (WR) |
|---|---|---|
| projection | 182.4 | 179.4 |
| **MSV** | **182.4** | **0.0** |
| **DA-VORP** | **42.0** | **71.7** |
| value base | **224.4** | 71.7 |
| score | **172.8** | 67.0 |

**The receiver is the better player by the only measure that prices replaceability** — his
surplus over replacement is 71.7 against the kicker's 42.0 — and he loses by 105.8, entirely on
MSV.

By round 9 every startable slot except K and DST is full, so a fourth receiver adds **0** to the
current lineup and the kicker adds his whole 182.4. MSV is answering *"what does this add to my
lineup right now"* correctly. The right question is *"what does this add to my final 16-man
roster"*, and with eight picks left the answer is near zero, because:

* In one consensus mock draft of this league, **kickers go at picks 145–160** and defenses at
  133–156. Alpha takes its kicker **64 picks early**.
* Aubrey is still the best kicker on the board at picks 81, 100, 120 **and 141**, and Alpha's own
  survival model gives him `P(survive) = 1.00` through #120 and **0.81 at #141**.

The engine knows and cannot act, because `survival_mult = 1.0 + 0.3·(1 − P)` lies in **[1.0,
1.3]**. A player certain to survive scores exactly `1.0×`. **Nothing in the score can say "you
can have him later for free."**

The severity is predicted by the algebra. The amplification of the value base over the principled
surplus is `1 + proj/(proj − R)`, which diverges as replacement approaches the top player — so
the **flatter** the position, the worse it is:

| DST | K | TE | QB | WR | RB |
|---|---|---|---|---|---|
| **8.10×** | **5.34×** | 3.36× | 3.15× | 2.61× | 2.59× |

That ranking, derived from the algebra rather than fitted, reproduces the observed pathology
ranking exactly. At round 10 of a real draft, **all 60 of the top 60 ranked candidates were
kickers.**

---

## 4. Replacement-level theory — what it should mean in Alpha

Replacement level is *the value of the best alternative you can still obtain at that position if
you do not take this player now.* Alpha currently holds **two incompatible answers at once and
adds them**: MSV's implicit **0** and daVORP's **consumption boundary**.

The single coherent quantity already exists in the codebase, and its own docstring names it:

```
msv_over_replacement(c) = lineup(roster + c) − lineup(roster + replacement body at c's position)
```

It reduces to `proj − R` on an empty roster (exactly VORP, which correctly refuses the early
quarterback) and to `0` at a saturated position (which correctly refuses the bench kicker). It is
the principled unification by construction rather than by clamping.

**It has now been measured three times and lost three times**: D63's `N3` against the static
level, D79's `Z2` against the draft-aware level (−44.4 target, −75.8 in 2QB), and this phase's
arm C, which held the value base's *scale* constant to rule out the one confound the earlier two
shared — and still produced +3.1 with a CI spanning ±130.

**The theory is right and the benchmark does not reward it.** That is the central finding.

---

## 5. Starter demand vs consumption demand — which should drive replacement

Both, computed from the league's own config on the real board:

| pos | S_p (starter) | C_p (consumed) | C/S | starter R | consumption R | surplus added |
|---|---|---|---|---|---|---|
| QB | 1.00 | 2.20 | **2.20×** | 265.2 | 193.8 | **−71.4** |
| RB | 2.40 | 4.20 | 1.75× | 158.3 | 99.1 | −59.2 |
| WR | 3.60 | 5.80 | 1.61× | 158.3 | 107.7 | −50.5 |
| TE | 1.00 | 1.80 | 1.80× | 133.2 | 122.4 | −10.8 |
| K | 1.00 | 1.00 | **1.00×** | 140.4 | 140.4 | 0.0 |
| DST | 1.00 | 1.00 | **1.00×** | 95.2 | 95.2 | 0.0 |
| **total** | **10.00** | **16.00** | | | | |

`S` sums to the starting-lineup size; `C` sums to `roster_size`. Both by construction.

**The economic argument favours starter demand.** Value is realised only through starting
lineups — the benchmark's primary metric is realized *starter* points. A quarterback drafted 21st
in a 10-team 1-QB league never starts for anyone, so pricing every QB against QB21 credits them
with beating a player who contributes zero to any lineup.

**The benchmark has already rejected that argument.** Starter-demand replacement is essentially
D67's `W0` control, and consumption demand (`W1`) beat it by **+32.1** starter points, CI
[+11.5, +52.7], and by +75.5 out of format. This is why arm B was withdrawn before being run
rather than proposed and re-refuted.

**The resolution.** The two demands answer different questions — starter demand bounds the
*lineup contribution*, consumption demand describes *acquisition timing* — and the engine needs
both. What the evidence says is that the consumption boundary is the better single choice, most
likely because it preserves the scale relationship between the value base and the
opportunity-cost term, which is denominated in season-long static VORP. Note that this scale
mismatch between a draft-aware value base and a static-VORP opportunity cost has been open since
D60 and remains unresolved.

---

## 6. Snake-turn effect — is `opportunity_cost = 0` exposing a flaw?

**It exposes one; it does not create one.** `oc = 0` at a turn is correct: zero opponents pick in
between, so no positional value can be lost.

Counterfactual — score the identical pick-20 board with the opportunity costs that *would* apply
if 18 opponents picked in between, changing nothing else:

| | value base | oc(18) | base + oc |
|---|---|---|---|
| Josh Allen (QB) | **530.0** | 0.0 | **530.0** |
| Puka Nacua (WR) | 456.8 | 69.8 | 526.6 |
| C. McCaffrey (RB) | 433.2 | 22.3 | 455.5 |

**QB wins either way**, but the margin collapses from **+73.2 to +3.4**. So the opportunity-cost
term very nearly offsets the double count, and removing it at the turn is what lets the
distortion through undiluted.

**Answer: (C) MSV/daVORP double-counting, with (D) a genuine interaction.** Not (A) and not (B)
alone.

---

## 7. Generalization — one mechanism explains all of it

The single quantity `1 + proj/(proj − R)` accounts for the quarterback at #20, the kicker at
round 9, the defense at round 10, the tight end's fragility, and why running backs and receivers
are least affected. **There is no need for a separate story per position.**

It is also correctly format-sensitive rather than a 1-QB artifact: starter demand for QB rises
1.00 → 2.00 in `legacy_2qb_dynasty`. But the distortion does not vanish, it *moves* — the
worst-hit position becomes **TE at 2.30×**, and the 2QB league consumes 39 quarterbacks, putting
replacement at **QB39 = 56.8** against a starter boundary of 214.3, a −157.5 gift to every
quarterback.

---

## 8. RB layer isolation — projection problem, decision problem, or both?

**Both, and they interact non-linearly.** The answer is **(B) amplifies** *and* **(D) creates an
additional RB-specific distortion**.

**(B)** With an empty slot, `d(value_base)/d(proj) = 2` against `1` for the principled surplus —
verified at 2.00 exactly at every step of a Δ ∈ {0, +10, +20, +40, +80} sweep. Applied to the
known RB top-10 signed bias of +45.5, the value base carries roughly **91 points** of error. This
is uniform across positions, so it amplifies rather than singles out RB.

**(D)** The opportunity-cost term is computed in *static* VORP units off the board, and its
response to the elite-RB projection is **threshold-gated**:

| elite-RB cell set to | 169 (Y1) | 210 | 260 | 300 | 320 | 350 |
|---|---|---|---|---|---|---|
| RB opportunity cost | 3.3 | 3.3 | 3.3 | 37.1 | 57.1 | 87.1 |
| slope | — | **0.000** | **0.000** | 0.846 | 1.000 | 1.000 |

Below ≈285 the term is **completely blind** to the elite-RB projection. So the decision layer
**over-reacts by 2×** in the value base and **under-reacts by 0×** in the opportunity cost, until
a threshold flips the second on. That non-linearity is a good reason neither layer's fix has
worked alone.

**The RB projection problem remains open and unchanged.** No RB projection was modified in this
investigation.

---

## 9. Candidates

| arm | rationale | target format | 2QB | gates | verdict |
|---|---|---|---|---|---|
| **A** | control — the shipped engine | **2055.9** | **2114.5** | — | **incumbent** |
| B | starter-demand replacement | — | — | — | **withdrawn before running**: it is D67's `W0`, already beaten by +32.1 |
| **C** | `msv_over_replacement + daVORP` — removes the double count while holding the scale, the one confound Z1/Z2/Z3 shared | +3.1, CI [−128.8, +134.9] | **−29.6** | G1 ✗ (TE zeroed ×2), G2 ✗ (2 infeasible), G3 ✗ (4/5 seasons worse), G6 ✗, G8 ✗, G9 ✗ | **FAIL** |
| **D** | symmetric survival, `1 + 0.3(1 − 2P)` ∈ [0.7, 1.3] — lets a certain-to-survive player be worth less now | −15.2 | **+50.8**, 4/5 seasons, LOSO all positive | G3 ✗, G6 ✗, G8 ✗ (CI [−30.9, +132.5]) | **FAIL** |
| **E** | C + D | +4.1, CI [−182.4, +190.5] | −11.2 | G1 ✗ (DST zeroed ×3), G2 ✗ (4 infeasible), G3 ✗, G6 ✗, G8 ✗, G9 ✗ | **FAIL** |

**Positional effects of arm C** (the one that behaves as intended): first QB 2.20 → **3.10**,
first RB 4.94 → **3.62**, first K 8.64 → **10.14**, first DST 10.08 → **12.94**. Arm E moves them
further (QB 3.86, K 10.78, DST 13.45).

**Three findings that decide the phase.**

1. **The behavioural fix is worth nothing.** Every change the brief hoped for, delivered — for
   +3.1 points with a CI spanning ±130.
2. **The apparent win is one season.** Arm C is worse in 4 of 5 seasons; the whole margin is
   2024. Dropping 2024 gives −41.0 (arm C) and −60.1 (arm E).
3. **The over-valuation is load-bearing.** Deferring K/DST "correctly" breaks roster legality:

   | | TE zeroed | DST zeroed | infeasible rosters |
   |---|---|---|---|
   | A (control) | **0** | **0** | **0** |
   | C | 2 | 0 | **2** |
   | E | 1 | **3** | **4** |

   Zero unfilled mandatory slots is **not independent of** the over-valuation — it is bought by
   it. Pricing a kicker at 5.34× its surplus is what guarantees a kicker gets drafted at all.

Both arms also **flip sign across formats** (C: +3.1 → −29.6; D: −15.2 → +50.8), which is what
Gate 7 exists to detect and is on its own disqualifying.

---

## 10. Production decision — **DO NOT SHIP**

`league/draft.py` stays byte-identical to its Y1 state. No arm cleared the pre-registered gates
in either format, and the two that came closest fail on the gates most designed to catch
self-deception: per-season consistency, leave-one-season-out, the season-clustered interval, and
cross-format sign stability.

**Why Y1 remains the correct baseline** — not merely "nothing better was found":

* Its control figures reproduce D79's published numbers to the decimal in **both** formats
  (2055.9 and 2114.5), so the incumbent is a verified quantity, not an assumption.
* Its known incoherence has now been given an exact algebraic form and a per-position severity
  ranking, and correcting that incoherence properly was measured to be worth approximately zero.
* Its over-valuation of K/DST is doing real work: it is the only thing keeping mandatory starting
  slots filled. Removing it without adding an explicit roster-legality constraint makes the
  product strictly worse.

**What would be needed before this could ship**, recorded so the next session does not restart
from scratch: a roster-legality constraint as a *hard restriction on the candidate pool* rather
than a valuation term (D67's `W2`/`W3` already prototype exactly this), measured **jointly** with
arm C. The double count and the legality guarantee are currently the same mechanism; they have to
be separated before either can be fixed. That is the single most promising remaining direction,
and it is a constraint question, not a valuation question.

---

## 11. Trust assessment

> *"If I gave Alpha the first pick in a real 10-team 1-QB draft, would I trust it to make the
> decisions for me today?"*

**Mostly yes for the first pick, no for the second, and yes-but-hold-your-nose for the rest.**

**Pick #1 — trust it.** Ja'Marr Chase leads on every term, and the opportunity-cost asymmetry
that decides it (WR 72.3 vs RB 3.3) is directionally real: the 2026 board genuinely is
receiver-heavy at the top. The *size* of that asymmetry is suspect, not its direction.

**Pick #20 — override it.** Taking the consensus QB1 in round 2 of a 1-QB league is the one
recommendation I would not follow. It comes from raw projection being counted twice at an empty
slot plus a replacement quarterback (QB22) that a one-QB roster would never start, and it
survives a 90-point projection change — four times the measured QB bias. Take the running back or
receiver; a quarterback within ~60 points of Allen is available six rounds later.

**Round 9's kicker — the honest answer is more uncomfortable than "override it."** It is
indefensible on its face: Alpha spends pick #81 on a player its own model says is 81% likely to
be there at #141, and at that moment it ranks *sixty kickers above every skill player alive*. But
when that behaviour is corrected properly and measured over 200 drafts, it is worth **+3.1
points** — and the corrected engine **starts leaving mandatory roster slots empty**. So: override
it if you want, take the receiver, and then *actually remember to draft a kicker and a defense*.
The engine's absurd kicker valuation is what currently guarantees you never forget.

**What I would not trust it for at all** is a claim that its numbers mean what they say. A value
base of 530 for Josh Allen is not 530 of anything; it is 361.9 points of projection counted twice
minus a replacement level drawn at the wrong boundary. Use the *ordering* within the first few
rounds, treat the *magnitudes* as uninterpretable, and keep the two known model biases in mind:
elite running backs under-rated by roughly 45 points (a bias the market largely shares), elite
quarterbacks over-rated by roughly 22.

**The bottom line for a real draft.** Alpha is a competent board with two identified structural
distortions whose *practical* cost is far smaller than their mathematical ugliness suggests. It
will not lose you the draft. It will take a quarterback too early, and it will take a kicker
absurdly early — and the second of those is, perversely, protecting you.
