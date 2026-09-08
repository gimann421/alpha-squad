# Opening-draft behaviour audit (D81, Phases 1–4)

What does Alpha actually tell you to do with picks **#1, #20 and #21** of a real 10-team,
16-round snake draft, and *why*?

Everything below runs the real production path, `league/draft.py::recommend_draft_pick`, on the
live 2026 board. No parallel scoring implementation exists anywhere in this audit: the
decomposition recomputes each term with the same production functions and **asserts** that the
reassembled score equals the production score to 1e-6, aborting rather than reporting if it
does not. Nothing in `src/` changed.

---

## 1. The opening, and why

**Slot 1, default (fair consensus) opponents, 2026 board: `WR → QB → TE`.**

Full 16-round roster from that run: `WR, QB, TE, RB, RB, WR, RB, WR, K, DST, QB, WR, WR, K, DST, TE`
— first RB in round 4, and six roster spots spent on QB/K/DST, positions this league starts one
of each.

### Pick #1 — Ja'Marr Chase (WR), score 651.0

| player | pos | proj | msv | daVORP | oc | fit | risk | surv | sMlt | score |
|---|---|---|---|---|---|---|---|---|---|---|
| **Ja'Marr Chase** | WR | 284.7 | 284.7 | 177.0 | **72.3** | 1.20 | 0.78 | 0.00 | 1.30 | **651.0** |
| Puka Nacua | WR | 282.3 | 282.3 | 174.5 | 72.3 | 1.20 | 0.78 | 0.00 | 1.30 | 643.4 |
| Christian McCaffrey | RB | 266.2 | 266.2 | 167.1 | **3.3** | 1.20 | 0.72 | 0.21 | 1.24 | 465.5 |
| Josh Allen | QB | 361.9 | 361.9 | 168.1 | 0.0 | 1.10 | 0.72 | 1.00 | 1.00 | 421.8 |

Gap to the best RB: **+185.5**. Decomposed: projection +18.5, daVORP +9.9, **opportunity cost
+69.0**, the rest from `risk` and `survival`. The single dominant term is the positional
opportunity cost, **72.3 for WR against 3.3 for RB — a 22× asymmetry.**

### Pick #20 — Josh Allen (QB), score 421.8

At the turn (#20 → #21) `picks_until_next_turn` is **0**, so every opportunity cost is exactly
zero — correct behaviour, and the boundary condition the engine gets right. With `oc` gone the
score collapses to the value base, and the value base is `msv + daVORP`, which on a roster with
an empty QB slot is `2 × projection − replacement`:

* Josh Allen: `2 × 361.9 − 193.8 = 530.0` → × 1.10 × 0.72 = **421.8**
* Jeremiyah Love (best RB): `2 × 243.9 − 99.1 = 388.7` → × 1.20 × 0.70 = 326.5

Gap **+95.3**. Note QB wins on daVORP alone too (168.1 vs 144.8), because QB replacement is drawn
at the *consumption* boundary — 2.2 QB per team, i.e. QB22 at 193.8 — while a 1-QB league only
ever **starts** ten quarterbacks. The QB you would actually roster instead is Hurts at 300.3, so
Allen's real marginal value is ~61.6, not 168.1.

### Pick #21 — Trey McBride (TE), score 375.7

`oc` returns (18 opponent picks before #40) and is **TE 63.4, RB 0.0, WR 0.0**. McBride
(212.3 + 89.9 + 63.4) × 1.10 × 0.79 × 1.18 = 375.7 edges Jeremiyah Love
(243.9 + 144.8 + 0) × 1.20 × 0.70 × 1.10 = 360.1 by only **+15.6** — entirely on the TE
opportunity cost. RB's 0.0 says the engine believes the RB it likes will still be there at #40.

---

## 2. Across opponent worlds and draft slots

Twelve worlds — default, pure-ECR, WR-heavy, RB-heavy, and eight stochastic (consensus with
reach/slide) — all through the production path:

| pick | distribution |
|---|---|
| **#1** | **WR 100%** |
| #20 | QB 50%, WR 33%, RB 17% |
| #21 | QB 50%, TE 33%, RB 17% |

Opening sequences: `WR→QB→TE` 33%, `WR→WR→QB` 33%, `WR→RB→QB` 17%, `WR→QB→RB` 17%.

**Josh Allen is taken inside the first three picks in 12 of 12 worlds.** Slot sensitivity
(default opponents) says the same thing from every seat:

| slot | picks | recommendation |
|---|---|---|
| 1 | 1, 20, 21 | Chase (WR), **Allen (QB)**, McBride (TE) |
| 4 | 4, 17, 24 | Smith-Njigba (WR), **Allen (QB)**, Love (RB) |
| 7 | 7, 14, 27 | McCaffrey (RB), **Allen (QB)**, Love (RB) |
| 10 | 10, 11, 30 | **Allen (QB)**, Taylor (RB), Love (RB) |

So the engine takes the consensus QB1 in the first three picks of a **1-QB** league from every
slot and under every opponent model tested, and in a third of worlds takes **no running back at
all** in the opening three.

---

## 3. Is this economically coherent?

Two separate answers, because the two behaviours have different causes.

**Pick #1 (WR) is defensible.** Chase is Alpha's highest-projected non-QB, he leads on every
term, and the opportunity-cost asymmetry that decides it is at least *directionally* real — the
consensus board is receiver-heavy at the top, so more receiver value genuinely does leave the
board in the next 18 picks. The size of the asymmetry is suspect (see §4), not the direction.

**Pick #20 (QB) is not.** In a 1-QB, 10-team league, taking the consensus QB1 in round 2 forgoes
an entire tier of skill players for a marginal edge over a quarterback available six rounds
later. The engine gets there because at the snake turn `oc = 0` for everyone, leaving a value base
that counts raw projection twice — and quarterbacks carry by far the highest raw projections.
That it happens in **12 of 12** worlds and from **every slot** makes it structural, not incidental.

The round-3 TE at a **+15.6** margin, decided entirely by one opportunity-cost term, is fragile
rather than wrong: any modest change to that term flips it.

---

## 4. What actually causes it — controlled counterfactuals

Method note worth recording: the first version of this counterfactual passed a projection
override *into the draft loop* and was a **silent no-op** — `recommend_draft_pick` calls
`load_season_projections` itself and reloads the board from the database, so the engine never saw
it. The decomposition self-check caught it by failing to reproduce the production score. The real
counterfactual writes into an **isolated copy** of the database and restores afterwards;
production code and the real database are untouched, and the override is verified to reach the
engine's own loader before each run.

The 2026 elite-RB cell (ECR ≤ 12 **and** prior weighted total ≥ 300) is Gibbs (Y1: 169.2),
Bijan Robinson (224.1) and Jonathan Taylor (266.0). Moving the whole cell together — a rule, never
a player patch, and never derived from ECR:

| elite-RB cell set to | pick #1 | pick #20 | pick #21 |
|---|---|---|---|
| 169 (Y1) / 210 / 230 / 260 / 285 / 300 / 320 | Chase (WR) | **Allen (QB)** | McBride (TE) |
| **350** | **Bijan (RB)** | **Allen (QB)** | McBride (TE) |

And reducing **every** QB by a fixed amount:

| QB adjustment | pick #1 | pick #20 | pick #21 |
|---|---|---|---|
| 0 / −10 / −22 (the measured bias) / −40 / −60 | Chase (WR) | **Allen (QB)** | McBride (TE) |
| **−90** | Chase (WR) | Love (RB) | Allen (QB) |

Two conclusions, both of which cut against the working hypothesis:

1. **The RB projection defect is not what produces this opening.** The elite RBs would have to
   project **~350** — about 140 points above the training data's own answer for their cell
   (210.3) — before one is taken at #1, and *no* value of that cell changes picks #20 or #21 at
   all. By then the elite RBs are long gone anyway: at ECR 2.5–12 the opponents take them in
   picks 2–19.
2. **The QB behaviour is not a projection artifact either.** Correcting the full measured QB
   top-10 bias (−22) leaves Allen the round-2 pick. It takes **−90** — four times the measured
   bias — to dislodge him. This is the decision engine's value base, not the model's calibration.

### The one place the two layers do connect

Opportunity cost is measured in Alpha's **own** static VORP units, so under-rating the elite RBs
suppresses what it costs to lose them. Measured by moving the cell and re-reading the term,
nothing else changed:

| elite-RB cell | RB oc | WR oc |
|---|---|---|
| 169.2 (Y1) | **3.3** | 72.3 |
| 210.3 | 3.3 | 72.3 |
| 260 | 3.3 | 72.3 |
| 300 | 37.1 | 72.3 |
| 320 | 57.1 | 72.3 |
| 350 | **87.1** | 72.3 |

The suppression is real but **threshold-gated**: it only bites once the correction is large enough
to make those players the best available RB by static VORP (McCaffrey holds that spot at 266.2
until then). So the projection defect does feed the decision layer, but at Y1's actual numbers it
is not the binding constraint on the opening.

---

## 5. Where this leaves the investigation

The opening's two problems live in **different layers**, and only one of them is the projection
model:

* **#1 = WR** — driven by the positional opportunity-cost term, which is directionally sound and
  amplified by the RB under-projection. Fixing the projections would narrow it, not reverse it.
* **#20 = QB in a 1-QB league** — driven by the value base `msv + daVORP` counting raw projection
  twice at an empty roster slot, plus a QB replacement level drawn at the *consumption* boundary
  (QB22) rather than anything a 1-QB roster would ever actually start. Robust to a ±90-point
  projection change. **This is a decision-engine property.**

The value base has already been re-measured once (D79's Z-tiers: every alternative lost on
realized starter points, in two league formats). What has *not* been examined is the interaction
specifically at positions whose consumption demand far exceeds their starter demand — QB in a
1-QB league is the extreme case, where the draft consumes 2.2 per team but starts 1.0.

**Nothing has been shipped. `models/` and `league/` remain byte-identical to their Y1 state.**
