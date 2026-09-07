# Draft decision engine investigation — positional scarcity and marginal draft value

Second-pass investigation, opened after the D78/Y1 projection work. The question is **not**
whether the projections are accurate. It is whether the engine turns them into good *draft*
decisions, with respect to positional scarcity, marginal value, roster construction and
snake-draft dynamics.

Status: **in progress.** Nothing in `src/alpha_squad/league/` has been modified. Every number
below is measured on the real 2021–2025 walk-forward board rebuilt from source in this session
(`make ingest`→`train`), against the real `ro`/`redraft-overall` consensus board and real
`player_season_stats` outcomes.

---

## 1. The decision architecture, as implemented

Traced by reading the implementation, not by inferring from names. Entry point:
`league/draft.py::recommend_draft_pick`. Every production caller (CLI, `POST
/league/{id}/draft`, the web Draft view, and the Claude review endpoint via
`_recommend_draft_pick_for_request`) reaches this one function; there is no second scoring path.

```
score = ( msv + w·daVORP + opportunity_cost[pos] )
        × roster_fit_multiplier(need[pos])          ∈ [0.7, 1.3]
        × risk_mult   ( = confidence, else 0.7 )    ∈ [0, 1]
        × survival_mult ( = 1 + 0.3·(1 − survival) )∈ [1.0, 1.3]
        × ( 0.1 if roster already holds ≥ positional_capacity[pos] )
```
with `w = DRAFT_VORP_WEIGHT = 1.0`.

| term | what it is | source | dynamic? | sees future picks? |
|---|---|---|---|---|
| `msv` | `best_lineup(roster+cand) − best_lineup(roster)` | `replacement.py::marginal_starter_value` | with the roster | no |
| `daVORP` | `projection − demand_boundary_replacement[pos]` | `replacement.py::demand_boundary_replacement`, demand from a full mock draft on the consensus board (`market_draft_demand`) | with the board | implicitly (demand is a full-draft quantity) |
| `opportunity_cost` | `max(0, best VORP at pos now) − max(0, best VORP at pos after replaying N consensus picks)` | `opportunity_cost.py::positional_opportunity_cost` | with the board and pick timing | **yes** |
| `roster_fit` | bounded fn of `roster_need` (a positional *count* vs `startable_slots`) | `roster.py` | with the roster | no |
| `risk_mult` | M6 `confidence` = `clip(1 − (p90−p10)/(2·projection), 0, 1)` | `uncertainty/conformal.py` | no | no |
| `survival_mult` | `1 + 0.3·(1 − P(player lasts to my next pick))`, rank ~ Uniform(ecr_best, ecr_worst) | `draft.py::next_pick_survival_probability` | with pick timing | **yes** |
| feasibility cap | hard 0.1× past `positional_capacity` | `roster.py` | with the roster | no |

**Answers to the directive's questions 1–9.** The engine is *not* raw-points-driven by design:
it computes a genuine, board-dynamic positional replacement level (`daVORP`), a genuine
opportunity cost that literally replays the consensus opponent forward to the user's next pick,
and it does know the snake geometry (`picks_until_next_turn` works off real overall pick numbers,
so it is correct at the turn, where it correctly returns 0). Roster need, remaining startable
slots and a hard feasibility cap all exist. So questions 3–9 are all "yes, a mechanism exists".
The defect is not an *absence*; it is that one term outvotes the scarcity machinery in exactly
the phase where scarcity matters most. See §3.

---

## 2. Is the WR-heaviness real? Yes, and it is large.

Measured on the real board: score every player with the production score at pick 1.01 (empty
roster, next pick #20), and compare the positional composition of the top 24 against two
references — the real preseason consensus board, and a **hindsight answer key**.

The answer key is deliberately *not* raw realized points (that is the raw-points ranking, which
is the thing under suspicion). It is realized points minus the **realized** demand-boundary
replacement level at that position, using the same demand target the engine uses — i.e. exactly
the quantity `recommend_draft_pick` is trying to estimate, computed with hindsight.

Pooled top-24 over 2021–2025 (5 seasons × 24 = 120 slots):

| source | QB | RB | WR | TE |
|---|---|---|---|---|
| **Alpha (production score)** | 28 | **24** | **63** | 5 |
| consensus ECR | 4 | 49 | 60 | 7 |
| **hindsight draft value** | 23 | **51** | **42** | 4 |

Alpha puts **less than half** as many RBs in its top 24 as the hindsight-optimal ranking does,
and ~50% more WRs. The RB deficit appears in **every one of the five seasons** (Alpha vs
hindsight: 5/7, 8/11, 2/10, 5/11, 4/12).

Rank correlation against the hindsight key, per season:

| | 2021 | 2022 | 2023 | 2024 | 2025 | mean |
|---|---|---|---|---|---|---|
| Alpha score | +0.655 | +0.667 | +0.666 | +0.692 | +0.672 | **+0.670** |
| consensus ECR | +0.669 | +0.700 | +0.707 | +0.751 | +0.730 | **+0.712** |

**Alpha's board is a worse estimator of realized draft value than the free consensus board, in
5 of 5 seasons.** That is a finding worth stating plainly, and it is not what the aggregate
starter-points benchmark shows — because the benchmark measures a *drafted roster*, where the
opponent field, roster constraints and pick timing absorb much of a board-ordering error.

---

## 3. Where the deficit enters: layer decomposition

Same pick-1.01 setup, but ranking players by each successive layer of the score. Pooled top-24
composition over the five seasons:

| layer | QB | RB | WR | TE |
|---|---|---|---|---|
| L1 raw projection (pure BPA) | 72 | **5** | 42 | 1 |
| **L2 `daVORP` alone** | **23** | **30** | 65 | 2 |
| L3 `msv + daVORP` (the shipped value base) | 49 | **16** | 54 | 1 |
| L4 `+ opportunity_cost` | 38 | 19 | 62 | 1 |
| L5 full production score | 28 | **24** | 63 | 5 |
| — hindsight answer key | 23 | **51** | 42 | 4 |

Read down the table:

* **L1** confirms raw projected points are useless as a draft ranking in a 1-QB league: 72 of
  120 top-24 slots go to quarterbacks. This is exactly why VORP exists.
* **L2** — the draft-aware replacement transform *on its own* — is the layer that most resembles
  the answer key. Its QB count is **exactly right** (23 vs 23) and its RB count is the highest
  any Alpha layer achieves (30).
* **L3 is where the damage is done.** Adding `msv` drops RB 30 → **16** and pushes QB 23 → **49**.
  On an empty roster `msv` is *mathematically identical to the candidate's own projection*
  (`replacement.py::marginal_starter_value` says so explicitly), so L3 is
  `projection + (projection − replacement)` = **raw points at double weight, scarcity at single
  weight**. The value base re-injects the very ranking L2 removed.
* **L4/L5** partially repair it — opportunity cost, roster fit and confidence pull QB back from
  49 to 28 — but never recover L2's RB count, let alone the answer key's.

So the mechanism is specific and it is not "there is no scarcity model". It is:

> During the early rounds, when every lineup slot is empty, `msv` carries **zero roster
> information** — it is identically the raw projection — yet it enters the value base at the
> same weight as the entire positional-scarcity correction, and therefore halves it.

This is not a new observation in kind: D63 recorded exactly this degeneracy ("on an EMPTY roster
it is mathematically identical to the candidate's own projection … In a 1-QB league raw points
favour quarterbacks, which is precisely what VORP existed to correct") and chose to *offset* it
by adding VORP rather than to remove it. What is new is the measurement of how much of the
scarcity correction that offset actually leaves standing: about half, and less than that for RB.

### 3a. The projection layer contributes too, and separably

Mean projection error (projected − realized) among the hindsight top-60, pooled 2021–2025:

| position | n | mean bias |
|---|---|---|
| QB | 51 | −66.8 |
| **RB** | 115 | **−86.2** |
| TE | 16 | −93.1 |
| **WR** | 118 | **−62.2** |

Every position is under-projected at the top of the board — that is the regression-to-the-mean
behaviour the previous investigation correctly concluded was expected (an expectation should sit
below the realized maximum). But RB is under-projected **24 points more than WR**, which is a
*relative* cross-positional bias, and it is in the same direction as the deficit above. This is
consistent with D68's finding that RB's residual bias is the only sign-stable one. D68, D69 and
D70 each attempted a treatment and each failed its pre-registered gates; this investigation does
not re-open that, and the decision-layer effect in §3 is the larger and more tractable of the two.

---

## 4. Two production defects found (independent of the value-base question)

These are divergences between what the product does and what the benchmark measured. They do
not need the benchmark to justify fixing, because the benchmark already validated the intended
behaviour.

### 4a. `GET /rankings` does not serve the board the draft engine drafts from

`api/routers/rankings.py` reads `uncertainty_predictions` only — QB/RB/WR/TE **established
players**. `league/replacement.py::load_season_projections`, which the engine uses, additionally
carries **rookies** (`rookie_predictions`) and **K/DST** (`projection_snapshot`).

`web/src/components/DraftView.tsx:381` builds `available_player_ids` from that rankings pool, so
the recommendation universe the product sends is missing, every season:

| season | engine board | UI board | missing | breakdown |
|---|---|---|---|---|
| 2021 | 636 | 468 | 168 | QB 9, RB 26, WR 38, TE 18, **K 45, DST 32** |
| 2022 | 651 | 472 | 179 | QB 8, RB 31, WR 40, TE 21, **K 47, DST 32** |
| 2023 | 610 | 439 | 171 | QB 11, RB 27, WR 39, TE 18, **K 44, DST 32** |
| 2024 | 602 | 439 | 163 | QB 7, RB 29, WR 38, TE 18, **K 39, DST 32** |
| 2025 | 629 | 453 | 176 | QB 10, RB 30, WR 43, TE 18, **K 43, DST 32** |

Consequences:

1. **Alpha can never recommend a kicker or a team defense.** The target league starts one of
   each. D67 measured an unfilled mandatory slot at roughly −130 realized points. The
   `market_consensus_roster_aware` opponent is *forced* to fill those slots; the product's own
   engine is structurally unable to suggest them.
2. **Alpha can never recommend a rookie.** In 2025 that includes Ashton Jeanty — the engine's
   own highest-projected running back (rank 20 overall by raw projection, and the top-scoring RB
   in its own value model). Between 6 and 13 of the engine's top-100 players are invisible to the
   product in every season, and the exclusion falls disproportionately on RB.

The players *can* be marked drafted by hand through `PlayerPicker` (which searches `GET
/players`), so the omission is specifically from the **recommendable** set, not from the board
the user can track.

### 4b. The D67 draft-aware replacement level never engages in the product

`recommend_draft_pick` guards the draft-aware replacement behind:

```python
max_drafted    = league.teams * roster_size                       # 160
pool_is_a_board = len(projections) - len(available_player_ids) <= max_drafted
```

The guard's premise is that everything missing from `available` was *drafted*. Because of §4a
that premise is false: 163–179 players were never in the pool at all. Measured:

| season | engine board | UI board | difference at pick 1 | guard passes? |
|---|---|---|---|---|
| 2021 | 636 | 468 | 168 | **no** |
| 2022 | 651 | 472 | 179 | **no** |
| 2023 | 610 | 439 | 171 | **no** |
| 2024 | 602 | 439 | 163 | **no** |
| 2025 | 629 | 453 | 176 | **no** |

So in the product the guard fails **from the very first pick, in every season**, and the engine
silently falls back to the static full-season replacement level — the D65 defect that D67 was
shipped to remove, and whose removal was the largest measured draft-layer change in the project
(+32.1 starter points). Meanwhile `evaluation/draft_simulation.py` passes `available =
set(projections)`, so the guard always passes there and every published D67 number was measured
with the mechanism *on*.

The directional consequence is exactly the reported symptom. Replacement levels at pick 1, 2025:

| | QB | RB | WR | TE |
|---|---|---|---|---|
| static (what the product uses) | 250.8 | 158.7 | 158.3 | 128.5 |
| draft-aware (what was benchmarked) | 195.3 | 83.7 | 114.8 | 119.2 |

RB-vs-WR replacement gap (`WR level − RB level`; positive favours RB): **−0.4 static**, **+31.1
draft-aware**. Falling back to static removes a ~31-point structural advantage for running backs.

Note the guard is also the only thing preventing a *worse* outcome: if the UI board were let
through as-is, `demand_boundary_replacement` would read the 176 absent players as drafted and
return badly inflated levels (2025: RB 178.5, WR 241.4). The two defects have to be fixed
together — the fix is to make the served board and the engine's board the same universe, not to
loosen the guard.

**Honesty about impact.** At pick 1.01 the guard defect changes the *scores* but not the top-8
*ordering* in 2024 or 2025 — both boards still recommend the same WR. It is a real defect with a
real directional effect on RB, but it is not by itself the explanation for the WR-heavy board;
§3 is.

---

## 5. What has *not* been established yet

* Whether any alternative value base actually produces more realized starter points. The
  composition analysis in §3 is a diagnostic of board ordering, not of drafted-roster outcome.
* Whether the effect is measurable at all. See §6.

## 6. The measurement constraint that governs what can ship

D71 established, from the stored benchmark rows, that the 50-trial draft benchmark is a
deterministic cross-product whose true experimental unit is the **season**, not the trial
(ICC 0.0995, design effect 1.90, F(9,36)=0.54 for slot vs F(4,36)=1.91 for season). Its
**minimum detectable effect at 5 seasons is ≈128 starter points**, and every draft-layer change
this project has ever shipped (D63 +39.9, D67 +32.1) sits below it.

A direct consequence, which is worth stating because it cuts against the incumbent as much as
against any challenger: **the shipped value base was itself selected on margins the instrument
cannot resolve.** D63's N4-over-N3 margin was +48.6 and N4-over-N1 was +62.6, both quoted with
naive i.i.d. intervals; under the season-clustered treatment D71 requires, neither is
significant. N4 is not *established* to be better than the alternatives it beat — it is the
incumbent because it won an underpowered comparison.

That does not license changing it on a whim. It does mean the honest bar for this phase is:

> ship only a change that is either (a) a defect fix restoring already-benchmarked behaviour,
> or (b) an effect large enough to clear the instrument's real resolution.

---

## 7. The experiment, and its result: the hypothesis is refuted

`Z`-tier: re-run the value-base ablation **on top of D67's draft-aware replacement**. The D63
ablation that selected `msv + VORP` was run against the *static* replacement level, and its
stated reason for the sum winning — that VORP alone prices bench kickers above replacement in
the late rounds (D64) — is a property of the static level that D67 removed. The value base had
never been re-measured since. The rule (control, primary metric, Gates 1–8, ship condition) was
committed to `evaluation/draft_forensics.py` **before the run**; `Z0` is asserted byte-identical
to the shipped `X0`/`W1` by a test, so a margin cannot be an artifact of the harness.

400 real drafts per format (8 arms × 5 seasons × 10 slots), fair
`market_consensus_roster_aware` opponent, production's real caps.

**Target format (10-team 1-QB PPR):**

| tier | value base | starter pts | margin | QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|---|---|---|
| **Z0** | **msv + 1.0·daVORP (shipped)** | **2055.9** | — | 1.94 | 2.88 | 5.68 | 2.02 | 2.14 | 1.34 |
| ZW3 | msv + 3.0·daVORP *(sweep)* | 2033.8 | −22.1 | 1.98 | 3.14 | 5.58 | 1.84 | 2.12 | 1.34 |
| ZW05 | msv + 0.5·daVORP *(sweep)* | 2033.1 | −22.8 | 1.94 | 2.82 | 5.60 | 2.18 | 2.12 | 1.34 |
| ZW2 | msv + 2.0·daVORP *(sweep)* | 2027.5 | −28.5 | 1.96 | 3.06 | 5.58 | 1.88 | 2.14 | 1.38 |
| Z1 | daVORP alone | 2021.4 | −34.6 | 2.12 | 3.14 | 5.72 | 2.02 | 2.06 | 0.94 |
| Z3 | min(daVORP, msv) | 2016.5 | −39.4 | 3.12 | 3.08 | 5.38 | 2.20 | 1.20 | 1.02 |
| Z2 | msv over draft-aware replacement | 2011.5 | −44.4 | 2.44 | 2.76 | 6.06 | 2.14 | 1.58 | 1.02 |
| ZW0 | msv alone *(sweep)* | 1974.9 | −81.1 | 2.48 | 2.42 | 6.24 | 2.26 | 1.58 | 1.02 |

**Every alternative loses to the shipped value base. Nothing ships.**

**Gate 7, `legacy_2qb_dynasty` (a genuinely different decision problem):** the same ordering, the
same sign. Z0 2114.5; ZW05 −5.7, ZW2 −21.2, Z3 −31.3, ZW3 −34.6, Z1 −58.5, Z2 −75.8, ZW0 −99.0.
So this is not a target-format artifact.

**Gate 8 (season-clustered, per D71):** no margin is resolvable — every 95% CI contains zero
(e.g. Z1 −34.6, CI [−158.8, +89.7], 1/5 seasons won; Z2 −44.4, CI [−222.7, +133.9], 1/5). That is
the expected outcome given D71's power analysis, and it is reported rather than replaced with the
naive n=50 interval that would have made several of these look decisive.

### What this means, stated against the hypothesis it was built to test

The §3 mechanism is **real but does not transfer to outcomes**. Removing or re-weighting `msv`
does exactly what §3 predicts to the board — Z1 and ZW3 draft more running backs (3.14 vs the
control's 2.88), ZW0 drafts the fewest (2.42) and is the most WR-heavy (6.24) — and every one of
those rosters is *worse* on realized starter points. More RBs did not mean better teams.

So the correct reading of §2/§3 is narrower than it first appears: Alpha's board ordering at
pick 1.01 really is a worse estimate of realized draft value than consensus, and `msv` really is
why — but board-ordering accuracy is not the objective. A draft is sequential, and the terms that
look like they are "diluting" the scarcity correction at pick 1 (raw points early, opportunity
cost and roster fit later) evidently produce better rosters than a purer VBD ranking does. The
hindsight key in §2 also rewards realized *variance*, which an expectation-maximising drafter is
right not to chase.

**D63's central finding survives re-measurement under the corrected replacement level.** The
specific reason this phase existed — that "summing wins, clamping loses" might have been an
artifact of the static level D65 later showed to be wrong — is refuted: it holds just as strongly
once the level is draft-aware, in both league formats. The incumbent now has positive evidence it
did not have before.

The sweep additionally shows `w = 1.0` sits at the **maximum of a broad plateau** (w = 0 → −81.1,
0.5 → −22.8, 1.0 → control, 2.0 → −28.5, 3.0 → −22.1), which is the D66/D67 shape test: a narrow
spike would have been evidence the pre-registered 1.0 got lucky. It is not one.

---

## 8. What changed, and what deliberately did not

**Changed — the two defects in §4, both restorations of already-benchmarked behaviour:**

`GET /rankings` now serves the engine's own board (`load_season_projections`) rather than
`uncertainty_predictions` alone, and the Draft view fetches all of it. Verified on the real
2021–2025 boards: the served universe is now **identical** to the engine's in every season, the
`pool_is_a_board` guard passes from pick 1, and kickers, defenses and rookies are recommendable
for the first time. `tests/unit/test_api.py::TestRankingsServeTheEngineBoard` pins the universes
as equal so they cannot drift apart again.

Stated honestly: this does **not** change the pick-1.01 recommendation on the real 2024 or 2025
boards — both the old and new boards recommend the same receiver, because the guard defect moved
scores without reordering the top of the board there. What it changes is that the engine now runs
the replacement level it was benchmarked with, and can fill the two mandatory starting slots it
previously could not see.

**Not changed — the scoring logic in `league/draft.py`**, which is byte-identical. The
pre-registered rule said ship the lowest-numbered tier clearing every gate, or nothing. Nothing
cleared, in either format. Per §6 that is the correct outcome, not a failure of the phase.

---

## 9. Phase 2 — the survival term, measured for the first time

`survival_mult = 1 + 0.3·(1 − P(survives to my next pick))` had been in `league/draft.py` since
M10 as a bare literal, never ablated, swept or justified in any decision entry — the only term in
the score with no evidence behind it, and large enough (up to 1.3× on the whole score,
multiplicative) to reverse an 81-point surplus gap in a controlled test. S-tiers hold the shipped
engine fixed and vary only that coefficient; rule and gates committed before the run, `S0`
asserted byte-identical to `Z0`.

| coefficient | target format | `legacy_2qb_dynasty` |
|---|---|---|
| 0.15 | −53.2 | −20.7 |
| **0.3 (shipped)** | **2055.9** | **2114.5** |
| 0.6 | −17.5 | **+27.0** |
| 1.0 | −12.2 | **+42.1** |
| **0.0 (term off)** | **−50.7** | **+14.4** |

**The sign flips between formats.** In the target format the shipped 0.3 is the best of five
values and removing the term costs −50.7; in the legacy format removing it *helps* (+14.4) and a
larger coefficient helps more. Only one comparison anywhere is resolvable under the
season-clustered interval (target-format 0.15, losing in 0/5 seasons, CI [−90.1, −16.3]).

So the honest reading is **not** "0.3 is validated". It is that the coefficient's effect is
format-dependent and unresolvable within either format. Gate 7 is what caught that — the
target-format run alone would have read as confirmation. Nothing ships: there is no evidence to
change the constant and none that it is right, and replacing an unmeasured constant with one
fitted off a five-point sweep would be strictly worse.

---

## 10. Phase 3 — the actual root cause, and it is in the projections

Found by verifying the **live 2026 board** rather than the historical ones. Full detail in
`docs/DECISIONS.md` D79 phase 3; module `evaluation/projection_monotonicity.py`.

**M6's fitted projection is non-monotone in its own features.** The estimator is a depth-3
gradient-boosted tree, which cannot extrapolate, and the top of the RB feature space is sparse —
22 of 1120 RB training rows carry `prior_weighted_total > 300`, with realized outcomes from 13.0
to 471.2 (the elite repeats and the season-ending injuries in one leaf). Partial dependence on
the real fitted 2026 RB model, sweeping one feature with the others held fixed:

| `preseason_ecr_rank` | 1.0 | 2.5 | 5.0 | 10.0 | 20.0 | 40.0 | 80.0 | 150.0 |
|---|---|---|---|---|---|---|---|---|
| projection | **138.1** | 169.2 | **231.7** | 224.2 | 225.7 | 221.0 | 213.2 | 192.2 |

A running back the market ranks **first overall** projects 93.6 points *below* one it ranks
fifth. Over D78's four evaluation seasons the shipped model inverts on **18.0%** of
partial-dependence steps and orders **272 of 2026** top-of-board dominated pairs backwards
(worst gaps: RB 116.2, WR 116.0, QB 79.6, TE 20.2).

**This is why the 2026 board looks the way it does.** Consensus RB1 Jahmyr Gibbs — 363 and 367
PPR points in the two prior seasons — projects 169.2, board rank **80**. Consensus RB2 Bijan
Robinson, rank 35. With the two best running backs mispriced by ~100 points each, the top of the
board is receivers by default. The decision engine is not the cause.

This is a correction to §2/§3's emphasis, not a contradiction of it: the layer decomposition
still describes how the score is built, but the dominant error on the *live* board enters before
the decision engine sees anything.

**The obvious fix works and cannot be shipped.** Adding a priori monotonicity constraints
(non-decreasing in prior production, non-increasing in ECR rank; `prior_games` left unconstrained
because its direction is genuinely ambiguous) takes inversions 18.0% → 0.0% and dominated pairs
272 → 65, and on the 2026 board moves Gibbs from rank 73 to **10** and Bijan from 55 to **9**
while nobody else moves more than 14 points. A constraint cannot manufacture optimism — where
the data really does fall it goes flat — so this is not board inflation.

It fails six of the seven pre-registered gates: +3.20 MAE versus the shipped model at every
position and in every season (+2.62 of that is the RMSE loss the constraint forces, +0.57 the
constraint itself). **Nothing ships; `models/` is byte-identical.**

An instrument defect was found and voided first, and is recorded rather than quietly fixed:
CatBoost applies monotone constraints only under some losses, and under M6's `MAE` it *silently*
falls back from `Exact` to `Gradient` leaf estimation and fits a **near-constant** model
(prediction sd 3.1 against the shipped 69.9). Three arms constraining different features returned
identical MAE — the tell. Published naively that would have read "constraints cost +29 MAE".
`_new_model` now raises on the combination.

**What blocks the fix is a metric mismatch, stated in the module before the run.** The gate is
pool-wide mean MAE over ~150 players per position-season; the defect is in the twenty players a
draft actually consumes. Gating on the first was chosen deliberately so the second could not be
invented after seeing which arm it would favour. The next phase — pre-registered before running —
should be one whose primary metric is top-of-board ordering. Per the D70 precedent, E2 was not
carried to the draft benchmark.

---

## 10a. Where the shipped engine actually stands

Measured on this session's freshly rebuilt 2021–2025 board (which carries D78/Y1's projections),
10 draft slots × 5 seasons, fair `market_consensus_roster_aware` opponent field:

| strategy | mean starter pts | unfilled mandatory slots |
|---|---|---|
| **Alpha (shipped engine)** | **2055.9** | 0.00 |
| fair consensus (`market_consensus_roster_aware`) | 2034.8 | 0.00 |
| `generic_prior_year` | 633.5 | 5.40 |
| `alpha_bpa` (Alpha's points, no league context) | 449.3 | 6.62 |

Alpha beats the fair consensus by **+21.2** starter points, paired on identical trials — winning
**2 of 5 seasons**, season-clustered 95% CI **[−193.2, +235.6]**. The naive n=50 interval would
report [−56.3, +98.6]; both contain zero, and per D71 the clustered one is the honest statement.

**Alpha is not demonstrably better than the free consensus board at the roster-outcome level.**
That is the same position D67/D71 established and this investigation did not move it. What the
league-context layer *is* demonstrably worth is the gap to `alpha_bpa` (449.3, finishing with a
mean 6.62 unfilled mandatory starting slots) — the same projections, ranked without VORP, roster
fit, opportunity cost or feasibility caps. The decision layer is doing very large work; it is the
*margin over consensus* that is unresolvable.

## 10b. End-to-end verification after the board fix

`web/draft-rehearsal.mjs` driven in real Chromium against the real API and the real 2026
projections: **20/20 checks pass**, including the pick-number correction, persistence through a
reload, roster-position sync, and the recommendation moving when the board moves.

One process note worth recording, because it nearly became a false regression: the rehearsal's
first run failed at step 3 against a cold API server, and the same failure did not reproduce
against a warm one. Before concluding, the pre-D79 Draft view was checked out and re-run — it
passed — which looked like proof the change had broken something. Re-running the *changed*
version against the now-warm server passed 20/20. The diff is a request limit and comments; the
first failure was a cold-start artifact of running the two versions in that order.

---

## 11. Open, and deliberately not acted on

* **The monotonicity defect in §10 is unresolved.** It is measured, mechanistically explained and
  has a working fix that fails the current gates. The next phase should pre-register a
  top-of-board metric (ordering among the ~60 players a draft consumes) rather than pool-wide
  MAE, and only then re-test. Until it is resolved, **Alpha's 2026 board should not be trusted on
  the elite running backs it ranks far below consensus** — Gibbs (Alpha 80th, consensus 2nd) and
  Bijan Robinson (Alpha 35th, consensus 4th). This is a measured defect, not a considered
  disagreement with the market.
* **Rookies and K/DST take a flat `risk_mult` of 0.7** because `confidence` only exists for M6
  rows, against ~0.71–0.81 for established players on the real board. That is a structural
  penalty applied by data availability rather than by evidence. It became reachable only with
  this phase's board fix (before it, those players could not be recommended at all), so its
  effect has never been measured in a draft.
* **The projection-layer RB bias in §3a** (RB under-projected 24 points more than WR at the top
  of the board). D68/D69/D70 each tried a treatment and each failed its gates. §10 is the likely
  mechanism behind it, so a successful monotonicity phase would be the thing to re-test it with.
* **`survival_mult`'s 0.3 coefficient** — now measured (§9) rather than open, but resolved only
  in the sense that there is no evidence for changing it. Its effect is format-dependent.
