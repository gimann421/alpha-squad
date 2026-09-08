# Final report — projection model and opening-draft investigation

Covers D81 (opening-draft audit), D82 (feature addition), D83 (seed ensembling) and the
draft-relevant validation that closes the line. Phase-by-phase detail for the opening audit is in
`docs/OPENING_DRAFT_AUDIT.md`; the decision records are D81–D83 in `docs/DECISIONS.md`.

**Bottom line: nothing shipped. `models/` and `league/` are byte-identical to their Y1 state.**
Y1 is the best validated option currently available, and the evidence for that is now strong
enough to stop looking in this direction.

---

## 1. OPENING-DRAFT VERDICT — what Alpha wants you to do with picks #1, #20, #21

Real production path (`league/draft.py::recommend_draft_pick`), live 2026 board, 10-team 1-QB
full-PPR, slot 1, fair consensus opponents:

| pick | recommendation | score | margin over next |
|---|---|---|---|
| **#1** | **Ja'Marr Chase (WR)** | 651.0 | +7.6 over Nacua, **+185.5 over the best RB** |
| **#20** | **Josh Allen (QB)** | 421.8 | +95.3 over the best RB |
| **#21** | **Trey McBride (TE)** | 375.7 | **+15.6** over Jeremiyah Love (RB) |

Full 16 rounds: `WR, QB, TE, RB, RB, WR, RB, WR, K, DST, QB, WR, WR, K, DST, TE` — **first running
back in round 4**, and six roster spots on QB/K/DST, positions this league starts one of each.

**Why each pick.** At #1 the single dominant term is positional opportunity cost: **72.3 for WR
against 3.3 for RB, a 22× asymmetry**. Of the +185.5 gap to the best RB, +69.0 is opportunity cost
and only +18.5 is the projection itself. At #20 the pick is *at the snake turn*, so
`picks_until_next_turn` is 0 and every opportunity cost is exactly zero — correct behaviour. With
`oc` gone the score collapses to `msv + daVORP`, which at an empty roster slot is
`2 × projection − replacement`; quarterbacks carry by far the highest raw projections, so Allen
wins on doubled projection. At #21 opportunity cost returns (TE 63.4, RB 0.0, WR 0.0) and decides
the pick outright — RB's 0.0 says the engine believes the RB it likes survives to #40.

---

## 2. Robustness across opponent worlds and slots

Twelve worlds (default, pure-ECR, WR-heavy, RB-heavy, eight stochastic), all through production:

| pick | distribution |
|---|---|
| #1 | **WR 100%** |
| #20 | QB 50%, WR 33%, RB 17% |
| #21 | QB 50%, TE 33%, RB 17% |

**Josh Allen is taken inside the first three picks in 12 of 12 worlds**, and from every draft slot
tested (1, 4, 7, 10). In a third of worlds Alpha takes **no running back at all** in the opening
three. This is structural, not incidental.

---

## 3. Practical trust test — what is and is not concerning

**Pick #1 (WR) is defensible.** Chase is Alpha's highest-projected non-QB and leads on every term.
The opportunity-cost asymmetry that decides it is at least directionally real — the consensus
board is receiver-heavy at the top, so receiver value genuinely does leave the board fastest. The
*size* of the asymmetry is suspect, not the direction.

**Pick #20 (QB) is not defensible.** Taking the consensus QB1 in round 2 of a **1-QB** league
forgoes a whole tier of skill players for an edge over a quarterback available six rounds later.
Two mechanical causes, both in the decision layer:

1. At the turn `oc = 0` for everyone, leaving a value base that **counts raw projection twice**.
2. QB replacement is drawn at the **consumption** boundary — 2.2 QB per team, i.e. QB22 at 193.8 —
   while a 1-QB league only ever **starts** ten. The QB you would actually roster instead is Hurts
   at 300.3, so Allen's real marginal value is ~61.6, not the 168.1 the engine credits.

**The round-3 TE is fragile rather than wrong** — a +15.6 margin decided entirely by one
opportunity-cost term; any modest change to that term flips it.

---

## 4. What actually causes it — controlled counterfactuals

Run against an **isolated copy** of the database, verified to reach the engine's own loader.
(Method note: the first version passed an override *into the draft loop* and was a silent no-op,
because `recommend_draft_pick` reloads the board itself. The decomposition self-check caught it.)

Moving the entire 2026 elite-RB cell together — a rule over a cell, never a player patch:

| elite-RB cell set to | #1 | #20 | #21 |
|---|---|---|---|
| 169 (Y1) / 210 / 230 / 260 / 285 / 300 / 320 | Chase (WR) | Allen (QB) | McBride (TE) |
| **350** | **Bijan (RB)** | Allen (QB) | McBride (TE) |

| QB adjustment | #1 | #20 | #21 |
|---|---|---|---|
| 0 / −10 / −22 (measured bias) / −40 / −60 | Chase (WR) | Allen (QB) | McBride (TE) |
| **−90** | Chase (WR) | **Love (RB)** | Allen (QB) |

**Both cut against the working hypothesis.** Elite RBs must project ~**350** — about **140 points
above the training data's own answer for their cell (210.3)** — before one goes at #1, and *no*
value changes #20 or #21. Correcting the full measured QB bias (−22) leaves Allen the round-2
pick; it takes **−90, four times the measured bias**, to dislodge him.

The one place the layers connect: opportunity cost is measured in Alpha's *own* VORP units, so
under-rating elite RBs suppresses what it costs to lose them — but it is **threshold-gated** (RB
`oc` stays 3.3 until the cell reaches 300) and at Y1's actual numbers is not the binding
constraint.

---

## 5. Model investigation

**5A — elite-tail sample scarcity.** Training rows for the 2026 fit:

| pos | n | ≥300 | ≥350 | distinct players ≥300 | realized mean in ≥350 tail |
|---|---|---|---|---|---|
| QB | 585 | 52 | 17 | 25 | 297.0 |
| RB | 1120 | 22 | **5** | **14** | **157.4** |
| WR | 1678 | 32 | 8 | 16 | 231.2 |
| TE | 943 | **0** | 0 | 0 | none |

**5B — partial dependence** on `prior_weighted_total` at an elite profile (100→450): QB 170→287
monotone, 0 reversals; **RB 199→peak 246 at 280→198, 4 reversals**; WR 162→peak 252 at 320→245,
2 reversals; TE flat past 280. The defect is RB-shaped because RB's tail is smallest *and* its
realized outcomes are worst.

**5C — simple baselines, walk-forward.** Y1 pool MAE **40.608** beats `prior_total` 46.078,
`ppg×17` 63.366, `shrunk` 56.900, `ridge` 45.938. `ecr_isotonic` ties at 40.493 — but that is the
market, and **the market shares the bias** (its own RB top10 bias is +36.6 against Alpha's +45.5).

**5D — shrinkage.** Failed badly (RB top10 MAE 137.8, bias +124.5).

**5E — added features (D82).** Five pre-registered arms; **all failed, and three made the elite
tail worse**: RB top10 ΔMAE +8.43 (age/career/draft), +6.28 (volume), +6.28 (all). F3 (usage
share) is the honest near-miss — QB top5 −7.69 in 4/4 seasons, WR top5 −14.00 in 3/4 — but it pays
with WR 11–24 +3.58 and fails the tier-preservation gate that exists for exactly that trade.

---

## 6. Tier-preservation validation

Gates P1–P9 were **committed to git before any arm ran** (`1553272` for D82, `67eaffb` for D83).
D83 imports D82's gate code rather than restating it, with a test asserting object identity so a
threshold cannot silently diverge.

**D83 seed ensembling** is the closest anything came. The pre-registered mechanism prediction was
**confirmed** — gains land in the head and scale with seed count:

| tier | ΔMAE 4 seeds | 12 seeds | 24 seeds |
|---|---|---|---|
| WR top5 | −3.87 | −5.88 | **−7.62** |
| WR top10 | −1.42 | −2.21 | −3.53 |
| QB top5 | −0.87 | −1.46 | −2.36 |
| overall top24 | −1.46 | −1.40 | −2.03 |
| **QB 11_24** | **+2.60** | **+2.46** | **+2.70** |
| pooled | −0.13 | −0.20 | −0.23 |

All three arms pass **7 of 9 gates**, including 4/4-season consistency. They fail **P1** (pooled
gain 0.04–0.12 against a 0.5-point floor, p=0.55–0.79) and **P2** (QB 11–24 damaged ~+2.6 in every
arm — consistent, so real). **Nothing ships.**

*Process note:* P1 originally required only "improves AND p<0.05". The regression tests caught
that this would pass a **0.001-point** gain, so the effect-size floor was added **before** any arm
ran. Significance alone is not a reason to change a production model.

---

## 7. Draft-relevant validation (exploratory, non-confirmatory)

D83's tier results were read before this was designed, so it **cannot license shipping**. It was
run because a null result closes the line. Z0 engine, fair roster-aware opponent, 2022–2025 × 10
slots = **40 paired drafts per arm**, projections substituted through D68's designed
`projections_override` point with K/DST/rookie values carried through untouched.

| | S0 (production Y1) | S3 (24-seed ensemble) |
|---|---|---|
| mean realized starter points | **2011.7** | 2003.8 |
| paired margin, season-clustered (D71) | — | **−7.9, 95% CI [−101.9, +86.1]** |
| seasons won | — | 2 of 4 |
| slots won | — | 19 of 40, median paired diff **+0.0** |
| **first pick RB** | **8 / 40** | **0 / 40** |
| first pick WR | 28 / 40 | **34 / 40** |

**A measurable top-of-board accuracy gain produced not one realized point, and made the WR
concentration worse.** The ensemble eliminates RB from the first pick entirely.

---

## 8. Common cause, and the TRUST ASSESSMENT in plain English

**The common cause.** Refitting the shipped model while varying *nothing but CatBoost's random
seed* moves predictions by **9.66 points in the head against 2.42 in the body**. The top of the
board is four times less determined by the data than the rest of it, before any change is made.
Added features inflate that instability, and across 40 arm × position × tier cells added
instability and added error are positively associated (r=+0.376, p=0.017, slope +1.23 MAE points
per point of added sd) — a real but partial channel (R²≈0.14).

So the head is **variance-limited, not information-limited**. That single fact explains why
changing the estimator (D79, D80) and changing the information (D82) both failed, and why
averaging (D83) moved the right tiers in the right direction but not far enough to matter.

### What this means for you, plainly

**Trust Alpha's picks #1 and #21 more than pick #20.** The receiver at #1 is a genuine read of a
receiver-heavy board, and the tight-end at #21 is a close call that could reasonably go either
way. **The round-2 quarterback is the one you should override.** In a 1-QB, 10-team league,
spending pick #20 on the consensus QB1 gives up a whole tier of skill players for an edge over a
quarterback who will still be there six rounds later. That is not the model being wrong about
Josh Allen — it is the draft engine double-counting his raw projection at an empty roster slot and
comparing him against a replacement quarterback (QB22) that a one-quarterback roster would never
start.

**Do not expect better projections to fix the receiver-heavy opening.** This was the working
hypothesis and it is now refuted three separate ways: the elite running backs would have to
project about 140 points above what the training data itself says players like them actually
score before one goes first overall; no projection change tested clears the validation gates; and
the one change that genuinely *did* improve top-of-board accuracy made the receiver concentration
**worse** while producing no extra points. The receiver-heavy opening lives in the decision layer.

**Known model limitations to hold in your head at a real draft**, unchanged from D80 and still
accurate: Alpha under-rates consensus-elite running backs by roughly 45 points (4 of 4 seasons) —
though note the market shares most of that bias, and the training data's own answer for those
players is ~210, not the ~280 consensus implies. It over-rates elite quarterbacks by roughly 22
points, which compounds the round-2 problem above. It is over-enthusiastic about receivers in the
**11–24** band by roughly 34 points. Tight end is unbiased.

**How much confidence to place in "nothing shipped".** This is a strong negative, not a shrug.
Thirteen pre-registered candidate models across three phases were tested against gates committed
to git before any of them ran, on genuinely walk-forward data, and the one that came closest was
then measured on realized starter points and produced a margin whose confidence interval
comfortably contains zero. Y1 is not merely the incumbent — it is the best of everything tried.

### Where the remaining value is

Not in the projection model. The open question is the decision layer's **value base**: `msv +
daVORP` counts raw projection twice at an empty roster slot, and replacement level is drawn at the
*consumption* boundary rather than the *starter* boundary. D79's Z-tiers already re-measured the
value base once and every alternative lost on realized starter points — but they did not examine
the interaction **at positions whose consumption demand far exceeds their starter demand**, and
QB in a 1-QB league is the extreme case: the draft consumes 2.2 per team and starts 1.0. That is
the next thing worth pre-registering.
