# D91 — Where does O1 actually win?

*An architecture diagnosis, not an experiment to ship from. `models/` and `league/` are
**byte-identical to Y1** throughout and no production file is touched under any outcome.*

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| branch | `claude/o1-advantage-attribution-azp7k7` |
| working tree at start | clean |
| HEAD at start | `dc1bf18` — "Merge pull request #17 … separate-valuation-legality" |
| `origin/main` | **`dc1bf18` — the same commit** |
| commits between `origin/main` and HEAD | **0** |
| `src/alpha_squad/models/` tree hash | `73b408e9…` — **unchanged since `0be8263`, the D78 commit that shipped Y1** |
| `src/alpha_squad/league/` tree hash | `d4cfd00e…` — **unchanged since `74a9542`, the D84-validated Y1 baseline** |
| D85 → D90 reports | all six present in `docs/` |
| offline test suite | **1318 passed, 44 deselected** |

### The brief's premise about `main` is out of date, in the harmless direction

The brief states "origin/main still points to D85" and instructs me to **stop** if D86–D90 are
not merged. **They are merged.** `origin/main` and HEAD are the same commit and the diff between
them is empty. What is stale is the *local* `main` ref, which still points at `39a5756` (PR #10)
and reports itself "behind 69" — that is a bookkeeping artifact of this container's clone, not a
repository state. D90 §1 recorded the unmerged condition truthfully at the time; PR #17 merged it
afterwards. **The stop condition does not fire and D91 proceeds.**

### The finding that actually constrains this phase: the artifacts are gone

D90 §1 lists the research artifacts it relied on — `otiers2.json`, `d87arms.json`, `equiv.json`,
`d88.json`, `d89.json` — and a "231 MB intact" database. **None of them exists in this container.**

| expected | actual |
|---|---|
| `d88.json`, `d89.json`, `d90.json`, `otiers2.json`, `d87arms.json`, `equiv.json` | **absent** — filesystem-wide search returns nothing |
| `data/alpha_squad.duckdb` | **absent** — `data/` held only `.gitkeep` |
| `models/`, `predictions/`, `state/` | **absent** — `.gitkeep` only |
| `reports/` | only the six pre-D86 files that `.gitignore` deliberately un-ignores |

This is not a defect: `.gitignore` excludes `data/**`, `models/**`, `reports/**` by design, and
this session's container was cloned fresh. But it means **the brief's instruction to "reuse
D86–D90 artifacts" and "prefer analysis of already-computed paired drafts" cannot be followed as
written** — the paired drafts D89 and D90 computed no longer exist anywhere. What survives is
what was committed: the prose reports and their aggregate tables.

D91 therefore splits into two tracks, and every claim below is labelled with which one it rests on:

* **Track A — arithmetic on committed aggregates.** Exact, no re-computation, no inference.
  Covers Phases 2, 5 (partly) and 6.
* **Track B — reconstruction.** Rebuild the database from source and re-run the paired grid with
  the committed harness, recording the per-pick traces D89/D90 did **not** keep. Required for
  Phases 1, 3, 4 and 8, none of which the aggregates can reach.

---

## 2. Track B substrate, and the reproduction gate it must clear (pre-registered)

The database was rebuilt with the documented pipeline (`ingest → identity → college-usage →
features → market → train`, 2015–2025). Validated against D89 §2.2's published inputs:

| quantity | D89 published | this rebuild | verdict |
|---|---|---|---|
| weekly rows 2020…2025 | 17269 / 17569 / 17420 / 17271 / 17570 / 17968 | **identical, all six** | ✅ |
| projected board 2020…2025 | 612 / 636 / 651 / 610 / 602 / 629 | **identical, all six** | ✅ |
| uncertainty predictions 2020…2025 | 435 / 468 / 472 / 439 / 439 / 453 | **identical, all six** | ✅ |
| preseason `page_type` | 2020 `redraft-offense`, 2021+ `redraft-overall` | identical | ✅ |
| **market-ranked players 2020…2025** | **458 / 490 / 496 / 484 / 515 / 480** | **533 / 570 / 573 / 556 / 616 / 550** | ❌ **differs** |

**The realized-outcome side and the projection side reproduce exactly; the market board does
not.** DynastyProcess's `db_fpecr` is a living file, and it has gained historical rows since
D89's run. The market board drives the nine fair-market opponents, so **bit-identical
reproduction of D89 is impossible in this container** and nothing below should claim it.

> **Reproduction gate R0, registered before any Track B result was examined.** The reconstruction
> is admissible as an attribution of D89's effect only if its six-season target-format primary
> margin falls inside D89's published 95% CI **[+6.5, +91.5]** and the mechanism signature
> (nK down, RB/TE depth up, early rounds unmoved) is present. If R0 fails, the Track B drafts
> describe *a* Y1-vs-O1 contrast on a slightly different board — they do **not** decompose the
> published +49.0 — and the report must say exactly that rather than quietly re-labelling.

---

## 3. Pre-registered diagnostic ablations (Phase 4)

Registered **before any ablation was run**. None is a shipping candidate; no gate is evaluated on
any of them; `models/` and `league/` do not change under any result.

O1 differs from Y1 in **exactly one place**: `draft_forensics.score_candidate` swaps
`league.replacement.marginal_starter_value` for `weekly_objective.expected_weekly_marginal_value`.
That function takes exactly one new input — a per-position availability rate vector, measured
walk-forward on prior seasons (D86: QB 88.2%, RB 85.3%, WR 86.1%, TE 87.3%, K 93.6%, DST 94.0%).

**Because the mechanism has exactly one input, the principled ablations are on that input**, not
on bolted-on constraints. Each is applied by overriding `SeasonStatic.availability_rates` and
**nothing else** — zero code change, so an ablation cannot accidentally become a different engine.

| id | rates | what it removes | what it keeps |
|---|---|---|---|
| **A2** | `1.0` everywhere | *all* availability structure | nothing — should collapse to Y1 |
| **A1** | pooled mean, same at every position | the **cross-positional differential** (K 93.6% vs RB 85.3%) | non-degenerate MSV at saturated positions; slot-count structure |
| **A3** | measured for QB/RB/WR/TE; `1.0` for K and DST | the **K/DST channel specifically** | the mechanism everywhere else |

### Why A2 is the most valuable of the three

At rate 1.0 every player is available in every draw, so `expected_weekly_starter_points` reduces
to a single `compute_league_starters` call on the whole roster — which is *definitionally*
`marginal_starter_value`. **A2 must therefore reproduce O0's drafted roster exactly.**

> **P1.** A2 == O0 on every drafted roster in every season and slot. A mismatch is not a finding;
> it is a **defect that would invalidate the "O1 changes exactly one thing" framing on which every
> D86–D90 conclusion rests**, and the phase stops and reports it.

### Predictions for the two substantive ablations

> **P2 (A1, flat rates).** A1 **keeps most of O1's behavioural signature**. Rationale, recorded so
> it cannot be re-derived from the answer: a backup's expected chance of reaching the lineup scales
> with how many slots he could ever enter. In `target_league` those counts are K 1, DST 1, QB 1
> against RB 4, WR 4, TE 3 — a **4× structural asymmetry**, against an availability spread of only
> 93.6/85.3 = **1.10×**. If the mechanism is slot count, flattening the rates changes little. If
> A1 instead collapses toward O0, then differential *availability* is the carrier and the
> mechanism really is about injury rates — the opposite reading, and the one that would justify
> calling O1 an availability model.

> **P3 (A3, K/DST switched off).** This is the brief's Phase 5 question made concrete: *would the
> advantage still exist if the K/DST mechanism were removed?* If the +49 is carried by K/DST
> restraint, A3 collapses toward O0 **and** its kicker count returns toward Y1's 3.45. If A3
> retains most of the effect, the K/DST count is a **marker** of O1 having been used, not the
> **carrier** of its gain. Track A's 2020 cell (K restraint exactly 0.00, effect +41.3) already
> points that way, and A3 is the direct test.

### Registered power limit, so an ambiguous result is not over-read

n = 60 paired drafts per arm per format; D89 measured the between-season SD at 40.5 and the MDE at
42.5. **An ablation landing between "clearly O0" and "clearly O1" is not resolvable by this
instrument**, and the correct report in that case is *unresolved* — not a ranking of the arms.

### Deliberately not run, each with its reason

* **A slot-count MSV with no availability model at all** (replace the degenerate saturated-position
  MSV with a static function of startable-slot count). This is the most interesting *next* test —
  it would say whether the fix needs weekly evaluation at all, given O1 costs 180× Y1 — but it
  requires a new scoring path rather than an input override, which is a new engine and therefore a
  new pre-registration. Recorded in §12 as the recommended next question, not smuggled in here.
* **More seasons, more slots, new weights, new terms, projection changes.** Forbidden by the brief
  and already closed by D88/D89.

---

## 4. Track A — what the committed aggregates alone establish (Phase 2)

Exact arithmetic on D89 §8/§11/§12 and D90 §5/§6. No re-computation, no model, no inference.

### 4.1 Decomposition A — the gain is conversion efficiency, not a better roster

Realized lineup points factor exactly as `primary = conversion_rate × total_roster_points`, so the
paired difference splits with no residual:

    Δprimary = Δ(rate)·roster_Y1  +  rate_O1·Δ(roster)

| format | rate Y1 | rate O1 | Δ rate | **efficiency term** | **roster term** | total | published |
|---|---|---|---|---|---|---|---|
| `target_league` | 0.73243 | 0.75603 | **+0.0236** | **+61.3** | **−12.3** | +49.0 | +49.0 ✅ |
| `dynasty_1qb` | 0.74470 | 0.75548 | +0.0108 | **+31.2** | −10.4 | +20.8 | +20.8 ✅ |
| `legacy_2qb_dynasty` | 0.72559 | 0.71288 | **−0.0127** | **−38.8** | **+36.5** | −2.3 | −2.3 ✅ |

**In both 1-QB formats O1 drafts a materially *worse* raw roster and converts it better.** The
whole of the target-format effect is conversion: +61.3 of efficiency, of which 12.3 is handed back
as lower raw points.

> **A result D89/D90 did not report, and it sharpens the legacy story.** In `legacy_2qb_dynasty`
> the signature is **inverted, not absent**: O1's conversion efficiency went *down* (−0.0127), and
> it avoided a loss only by drafting a **better** raw roster (+51.2 points, +36.5 after conversion).
> The legacy null is therefore not "the mechanism sat idle" — it is "the mechanism ran backwards
> and was masked by a roster-quality gain." D89 §9 read the null as coherent-because-inert; the
> decomposition says the inertness claim is too generous.

### 4.2 Decomposition B — only about a quarter of the gain needs weekly granularity

Both metrics score the **same** rosters, so the season-long delta is "how much better O1's roster
is under the *incumbent* rule", and the remainder is what only weekly scoring can see.

| format | Δ primary (weekly) | Δ season-long | **weekly-only remainder** | % visible season-long |
|---|---|---|---|---|
| `target_league` | +49.0 | **+35.8** | **+13.2** | **73.1%** |
| `dynasty_1qb` | +20.8 | +13.0 | +7.8 | 62.5% |
| `legacy_2qb_dynasty` | −2.3 | +16.3 | −18.6 | — (signs disagree) |

> **This is the single most consequential number in Track A.** ~73% of O1's target-format advantage
> is visible to Y1's own season-long scorer. Weekly evaluation is how O1 *chooses*, but it is not
> where most of the measured benefit lands — O1's roster is simply better by the old ruler too.
> Any claim that the gain "comes from weekly lineup optimization" is, at most, a claim about 27%
> of it.

### 4.3 Decomposition C — bench and availability

`bench_contribution` is computed in hindsight-lineup space, so it is a component of
`weekly_hindsight`, **not** of the primary metric, and must be compared against that.

| format | Δ hindsight | Δ bench | bench share of hindsight | Δ missed player-weeks | Δ roster pts |
|---|---|---|---|---|---|
| `target_league` | +66.7 | +18.5 | **27.7%** | +5.2 | −16.3 |
| `dynasty_1qb` | +24.8 | +3.2 | 12.9% | +2.0 | −13.7 |
| `legacy_2qb_dynasty` | +25.1 | +14.6 | 58.2% | −4.6 | +51.2 |

D89 §11 already established that the availability difference is **entirely non-bye** (byes +0.0,
non-bye absences +5.8): O1 cannot and does not dodge byes — every player has exactly one — so
"bye-week coverage" is **not** one of the categories the effect can be attributed to. It is
excluded on measurement, not on judgement. `bench` also carries D89 defect #4's ±4–6 point
`PYTHONHASHSEED` tie-break uncertainty and should not be read as exact.

---

## 5. Track A — mechanism versus correlation (Phase 5)

### 5.1 The K/DST channel does not have a consistent relationship with the gain

Per-season Pearson correlations between O1's kicker restraint (`ΔnK = O1 − Y1`, negative = more
restraint) and the realized paired margin:

| format | r(ΔnK, Δprimary) | 95% CI | reading |
|---|---|---|---|
| `target_league` | **+0.575** | [−0.44, +0.95] | **less** restraint → **bigger** win |
| `dynasty_1qb` | **−0.842** | [−0.98, −0.10] | **more** restraint → bigger win |

**The two formats disagree in sign.** Controlling for the season index — which D90 §7 flagged as a
confound, since `dynasty_1qb`'s effect is perfectly monotone in time (ρ = 1.00) — both partial
correlations turn positive (+0.99 target, +0.91 dynasty), i.e. in *both* formats more kicker
restraint predicts a *worse* result once the time trend is removed. With n = 6 and three degrees
of freedom these partials are far too fragile to assert; the sign disagreement in the raw
correlations is the durable part, and it is enough to deny a consistent K→gain relationship.

### 5.2 The 2020 natural experiment — the decisive within-format case

D89 §12 records a cell nobody designed but which answers the question directly:

| target 2020 | value |
|---|---|
| Y1 kickers | 2.00 |
| O1 kickers | **2.00** |
| **K restraint** | **exactly 0.00** |
| Δ primary | **+41.3** |
| mean Δ over the five seasons where the K channel *did* fire | +50.5 |

**With the kicker channel completely switched off, O1 still delivers 82% of its average effect.**
In 2020 the gain came through DST (2.00 → 1.20) and RB depth (2.00 → 3.00) instead. This is a
real, pre-existing, paired observation on the target format itself — not a model.

### 5.3 The counter-case is just as sharp

| target season | K restraint | Δ primary |
|---|---|---|
| **2022** | **−1.90 (largest of the six)** | **−10.4 — the only losing season** |
| 2024 | −0.60 (second smallest) | **+90.8** |
| 2025 | −1.00 | **+94.0** |

**The season with the most kicker restraint is the season O1 loses.** Taken with §5.1 and §5.2:

> **K/DST restraint is a marker that O1 was used, not the carrier of its benefit.** It is the most
> *visible* thing O1 does — D86's prediction Q1 called it "nearly certain, therefore NOT evidence
> of anything on its own", and that warning has aged well. Five phases of plain-English summaries
> have led with the kicker count; the kicker count is the part of the story the data supports least.

### 5.4 Dose-response works across formats and fails within them

| format | picks moved off ≤1-slot positions | Δ primary | points per pick |
|---|---|---|---|
| `target_league` | 1.37 | +49.0 | +35.8 |
| `dynasty_1qb` | 0.51 | +20.8 | +40.8 |
| `legacy_2qb_dynasty` | **0.00** | −2.3 | — |

A single through-origin slope of **+36.4 points per reallocated pick** fits all three formats
(r = 0.996). **This is a consistency check and not evidence**: three points fitted with one
parameter, one of which is pinned at the origin, cannot fail informatively, and it is reported
here only because it is the kind of number that gets quoted as if it were a finding.

The version with real degrees of freedom **contradicts it**:

| format | r(K+DST picks reallocated, Δprimary) across its 6 seasons | 95% CI |
|---|---|---|
| `target_league` | **−0.831** | [−0.98, −0.06] ← **wrong sign** |
| `dynasty_1qb` | +0.478 | [−0.55, +0.93] |

**Seasons in which O1 reallocated more picks are seasons in which it did worse**, in the format
carrying the headline result.

### 5.5 Why Track A cannot finish the attribution, stated plainly

The per-season tests above are the only ones the committed aggregates support, and they have **six
clusters against a between-season SD of 40.5 and an MDE of 42.5** — the same resolution wall D88
and D89 hit. Every per-season correlation here has a 95% interval spanning most of the possible
range, and I selected among several candidate predictors after seeing the data. **They are strong
enough to *refute* a specific claim (K restraint carries the effect) because they refute it in both
directions and in both formats; they are nowhere near strong enough to *establish* an alternative.**
Establishing one needs the per-pick evidence, which is Track B.

---

## 6. Phase 7 — the RB question, closed with a reason rather than an observation

D88 and D89 both measured that O1 gives **no** protection against elite-RB under-projection: Y1
and O1 each need **+75** on the elite-RB cell before taking an RB at #1, against a measured
historical bias of ≈ **+47.7**, and neither moves at #20/#21 under perturbations through +100.
D89 §13 reported this empirically. **D91 can now say why, from the algebra, and the reason is
stronger than the observation.**

At the **first pick the roster is empty**, so for any candidate `c`:

    E[U({c})] − E[U({})]  =  rate(pos_c) · proj_c  −  0

i.e. O1's MSV term at the top of the board is the Y1 MSV term **multiplied by that position's
availability rate**. The published 2026 scores confirm it:

| phase | player | pos | Y1 msv | O1 msv | factor |
|---|---|---|---|---|---|
| D89 target | St. Brown | WR | 278.7 | 243.8 | 0.8748 |
| D89 target | McBride | TE | 197.8 | 173.0 | 0.8746 |
| D89 target | Allen | QB | 329.4 | 284.9 | 0.8649 |
| D90 dynasty | **McCaffrey** | **RB** | 276.7 | 233.8 | **0.8450** |

Two consequences:

1. **A near-uniform positive rescaling of the value base cannot reorder the board.** That is
   exactly what D89 §14 and D90 §10 observed without explaining — "lowers every score, preserves
   the ordering, `vorp` identical by construction". So O1 was never *capable* of changing the #1
   pick through this channel, at any projection error. The +75 threshold is a property of the
   terms O1 does **not** touch (daVORP, opportunity cost, the multipliers).

2. **To the extent the rescaling is not uniform, it points the wrong way.** The factor is the
   position's availability rate, and **RB's measured rate (85.3%) is the lowest of the six
   positions**. So O1 discounts elite RB value *more* than any other position — structurally, as a
   consequence of RBs missing the most time, not as a tuning choice. Taken at face value that makes
   the elite-RB problem marginally **worse**, not better.

   *Honest limit on point 2:* a single player's factor is a 200-draw Monte Carlo average, so it
   carries roughly ±2.4% of sampling noise; the McCaffrey-vs-St.-Brown gap (0.845 vs 0.875) is
   about one standard error of that. The *expectation* argument is solid; this one observed pair
   is consistent with it rather than proof of it.

> **The RB question is formally closed, and D91 adds no new reason to reopen it.** D88's and D89's
> answer stands, and now has a mechanism: the weekly roster-utility objective operates on the
> marginal-lineup term, which at an empty roster is a positive per-position rescale — and no
> positive rescale can rescue a ranking error. Fixing elite-RB under-projection is a
> **projection-layer** problem; no decision-layer objective of this shape can reach it.

---

## 7. Phase 6 — O1 is one idea, and this is the idea (`scripts/d91_msv_degeneracy.py`)

### 7.1 Architecturally there is only one change

O1 substitutes one function for another in one place. It adds no term, no bonus, no rule and no
weight. Its only new input is the per-position availability vector. **"Weekly lineup
optimization", "bench insurance" and "late-round K/DST restraint" are not three components of
O1 — they are three descriptions of one substitution's consequences.** So the brief's question
("is O1 really one idea?") has a clean architectural answer: yes. The useful question is the next
one down — *which* property of that substitution does the work.

### 7.2 The measurement: Y1's marginal value is degenerate exactly where the draft is still open

`scripts/d91_msv_degeneracy.py`, target format, 2024 board, on a roster whose ten starting slots
are already filled with elite players — i.e. the situation the engine is in for rounds 11–16.
The candidate is the **#20 player at each position**, worse than every incumbent he could displace:

| pos | startable slots | rate | P(a hole opens) | proj | **Y1 msv** | **O1 msv** |
|---|---|---|---|---|---|---|
| QB | 1 | 0.884 | 0.116 | 212.9 | **0.00** | 20.22 |
| RB | 4 | 0.845 | 0.490 | 146.9 | **0.00** | **77.14** |
| WR | 4 | 0.865 | 0.440 | 209.9 | **0.48** | **105.10** |
| TE | 3 | 0.869 | 0.345 | 105.0 | **0.00** | 59.32 |
| **K** | **1** | 0.938 | **0.062** | 118.4 | **0.00** | **6.51** |
| **DST** | **1** | 0.940 | **0.060** | 94.3 | **0.00** | **6.13** |

> **Y1's entire spread across six backups is 0.48 points. O1's is 99 points.**
>
> This is the defect, stated more precisely than "the bench is priced at zero": Y1 prices
> **every** bench candidate at zero **simultaneously**, so in the back half of a draft its
> marginal-value term carries *no information at all* and the pick is decided entirely by daVORP
> and the multipliers — which **D85 measured as over-valuing K by 5.34× and DST by 8.10×**.

That closes the causal chain, and every link is separately measured:

1. Y1's MSV → 0 for all bench candidates at once *(measured above)*
2. → the late draft is decided by daVORP × multipliers alone *(structural)*
3. → daVORP over-ranks K/DST by 5.3×/8.1× *(D85)*
4. → Y1 drafts **3.45 kickers** against a capacity of 2 *(D89 §12)*
5. O1 restores a non-zero ordering among bench candidates, ranked by `P(hole) = 1 − rate^slots`
6. → flex-eligible depth outbids the third kicker *(D89 §12, D90 §6)*
7. → a better roster, **73% of whose benefit is visible even to season-long scoring** *(§4.2)*

### 7.3 It is slot count, not injury rates — so this is not really an availability model

The RB-backup : K-backup separation is **11.8×**. Decompose it:

| driver | ratio |
|---|---|
| availability spread (K 0.938 vs RB 0.845) | **1.11×** |
| startable-slot count (RB 4 vs K 1) | **4×** |
| resulting `P(hole)` spread (0.490 vs 0.062) | **7.9×** |

`P(hole) = 1 − rate^slots` — **the exponent moves it far more than the base does.** O1 is sold as
an availability-aware objective; what it mostly exploits is a *structural* fact about the lineup
that needs no availability data to know: a kicker has one slot to reach and a running back has
four.

**Computed after P2 was committed and before any ablation had run**, so it is a sharpening of the
prediction rather than a result: flattening the rates to their pooled mean (0.8902) moves `P(hole)`
for K from 0.062 to **0.110** and for RB from 0.490 to 0.372, cutting the RB:K separation from
**7.9× to 3.4×** — halved, but nowhere near Y1's 1.0×. So **P2's direction should hold and its
strength was overstated**: A1 should keep the behaviour, but less sharply than I registered.

---

## 8. Phase 2 — why the requested additive accounting cannot be produced as specified

The brief asks for

    O1 advantage = weekly lineup optimization + bench/insurance + K/DST allocation
                 + positional depth + availability + future-board effects + other

with each category carrying a mean, a median and a share of the total. **That accounting cannot
be produced honestly, and the reason is not a measurement limitation — it is that the categories
are not disjoint events.** Taking them one at a time:

| requested category | status | why |
|---|---|---|
| weekly lineup optimization | **separable: +13.2 of +49.0 (26.9%)** | The season-long and weekly metrics score the *same* rosters, so their difference isolates what only weekly granularity can see. This is the one clean orthogonal split. |
| bench / insurance | **not separable — double-counts the above** | A bench player entering the lineup *is* weekly lineup optimization. `bench_contribution` measures the same events from the player side rather than the slot side. It is also on the **hindsight** scale (+18.5 of +66.7 = 27.7%), not the primary one, so it cannot be added to a primary-metric total at all. |
| K/DST allocation | **not assignable a point value** | Measurable as behaviour (−1.14 K+DST picks per draft), but §5 refutes it as a carrier: sign-inconsistent across formats, off entirely in target 2020 (+41.3), and strongest in the only losing season (2022, −10.4). A category whose dose does not predict the response cannot be given a share of it. |
| positional depth | **the same object as the row above** | The +1.39 picks onto flex-eligible positions and the −1.37 off single-slot positions are one reallocation seen from two sides. Listing both double-counts every pick. |
| availability | **wrong sign** | O1's players miss **more** time, not less (+5.2 player-weeks, all of it non-bye), and O1's worst-week exposure is worse (7.20 vs 6.43 of 16 unavailable). O1 does not buy availability; it buys a replacement for when availability fails. |
| bye-week coverage | **excluded on measurement** | D89 §11: byes are +0.0 between the arms and essentially fixed at one per rostered player. O1 cannot dodge a bye and does not. |
| future-board effects | **not measurable here** | Would require tracking, per pick, which future players each choice denied the other arm. Once the arms diverge their boards differ, so there is no shared counterfactual to difference against. |

**What can be stated as an accounting, and it has two terms rather than seven:**

| term | target (+49.0) | dynasty (+20.8) |
|---|---|---|
| conversion efficiency — same picks converted into more lineup points | **+61.3 (125%)** | +31.2 (150%) |
| raw roster quality — O1 drafts a *worse* pile of points | **−12.3 (−25%)** | −10.4 (−50%) |

and one orthogonal split *within* the first term:

| | target | dynasty |
|---|---|---|
| visible to season-long scoring (the incumbent ruler) | **+35.8 — 73.1%** | +13.0 — 62.5% |
| requires weekly granularity to see at all | **+13.2 — 26.9%** | +7.8 — 37.5% |

> **Stated plainly, because it is the answer to the brief's headline question:** the roughly +49
> is *not* mostly a weekly-lineup effect, *not* a bye effect, *not* an availability effect, and
> *not* demonstrably a kicker effect. It is **one reallocation of about 1.4 late picks from
> positions with a single startable slot to positions with three or four**, and about three
> quarters of its value is visible without any weekly machinery at all.

---

## 9. Track B — gate R0 **FAILS**, and the reason is the most important thing D91 found

The reconstruction ran the pre-registered grid: 6 seasons × 10 slots × 2 arms × 2 formats,
**240 drafts**, identical code, identical projections, identical realized outcomes. The **only**
input that differs from D89/D90 is the market-board vintage (§2).

| | D89/D90 published | D91 rebuild |
|---|---|---|
| **target** primary Δ | **+49.0**, CI **[+6.5, +91.5]** | **+28.0**, CI **[−40.7, +96.7]** |
| target between-season SD | **40.5** | **65.4** |
| target per season | +41.3 / +57.3 / −10.4 / +21.0 / +90.8 / +94.0 | +9.3 / +17.6 / **+158.7** / −20.4 / −5.7 / +8.5 |
| **dynasty** primary Δ | **+20.8**, CI **[−30.8, +72.3]** | **+31.5**, CI **[+4.6, +58.4]** |
| dynasty per season | −46.2 / −15.4 / +5.1 / +31.4 / +69.5 / +80.2 | +64.1 / +12.1 / +35.3 / +17.0 / +58.6 / +1.8 |

**Season-level agreement between the two board vintages: r = −0.652 (target), r = −0.340
(dynasty).** The per-season pattern does not merely fail to reproduce — it *anti*-correlates.

The baseline arm moved too, which rules out "a bug in the O1 path": Y1's own first-RB round goes
**4.15 → 5.27**, first TE **6.70 → 5.87**, and Y1's kicker count **3.45 → 2.98**. A different
board changes both arms' drafts, as it must.

> **R0 as written is not met.** The point estimate (+28.0) does fall inside D89's published
> interval, but that was the weakest of R0's conditions and the interval is 85 points wide. The
> per-season structure — which is what an attribution actually decomposes — is unrecognisable.
> **The Track B drafts below therefore describe *a* Y1-vs-O1 contrast on a 2026-vintage board.
> They do not decompose the published +49.0, and nothing below is labelled as if they did.**

### 9.1 What survives the board change, and what does not

**Survives — the sign.** Four estimates now exist across two board vintages × two 1-QB formats,
and **all four are positive**: +49.0, +28.0, +20.8, +31.5 (mean ≈ +32.5). O1 beating Y1 in a
format where its mechanism can operate is the most robust claim in this research line, and D91 is
the first phase to test it against an independently re-scraped board.

**Survives — the behavioural signature.** Kickers still fall (2.98 → 2.32), RB depth still rises
(2.22 → 2.53), TE depth still rises (1.97 → 2.50), picks still move off single-startable-slot
positions onto flex-eligible ones (−0.82 / +0.82). Same direction at every position as D89 §12.

**Does not survive — the magnitude, the per-season structure, and *which format resolves*:**

| | D89/D90 board | D91 board |
|---|---|---|
| target G8 (CI excludes zero) | **PASS** [+6.5, +91.5] | **FAIL** [−40.7, +96.7] |
| dynasty G8 | **FAIL** [−30.8, +72.3] | **PASS** [+4.6, +58.4] |

**The two formats swapped which one clears G8.** D89's headline — "six seasons DO resolve O1 in
the target format" — is, on this evidence, substantially a property of **one board snapshot**
rather than of six seasons.

**Does not survive — D90 §7's monotone trend.** Published ρ(season, effect) = **+0.994**; on the
refreshed board, **−0.397**. D90 flagged that pattern as noticed-after-the-fact and explicitly
declined to make any inferential claim about it. **That caution was correct**, and this is the
first direct evidence that it was noise.

### 9.2 The honest limits of this finding

* **Neither board is privileged.** Both are real DynastyProcess `db_fpecr` scrapes; mine simply
  has higher ECR coverage (2020: 87% vs 74.8%). I cannot say D89's snapshot was wrong, only that
  the result moves a lot between them.
* **This is n = 2 on a new dimension.** Two vintages cannot estimate the variance the vintage
  dimension contributes. The right reading is "board vintage is a material, previously
  uncontrolled source of variation", not a number for how large it is.
* **The 2022 cell shows how the same behaviour can pay opposite amounts.** On D89's board 2022 had
  the *largest* kicker restraint (−1.90) and was the *only losing* season (−10.4). On this board
  Y1 draws **4–5 kickers in all ten 2022 slots**, O1 draws 2–3, and the season returns **+158.7**
  — positive in every slot. Identical mechanism, opposite outcome, different board.

### 9.3 What this means for the benchmark

D89 §18.6 concluded the binding limitation was "benchmark/instrument resolution … cross-format
evidence". D91 adds a third axis the instrument does not control at all: **the market board is an
input that drifts, and the effect this benchmark measures is sensitive to it.** D89's
bit-identical reproduction control could not detect this, because it re-ran against *the same
stored database*. Reproducibility against a frozen snapshot and robustness to a refreshed one are
different properties, and only the first was ever tested.

**This independently reinforces DO NOT SHIP**, and it does so more strongly than G7 did: a
candidate whose headline interval depends on which week the market board was scraped is not ready
to replace production, regardless of how the cross-format gate reads.

---

## 10. Phases 1 and 3 — first-divergence analysis (Track B board; see §9 before reading)

All 60 target-format pairs diverge. Final rosters share **13.2 of 16 players** on average
(min 11, max 16) — O1 changes fewer than three players per draft.

### 10.1 Divergence is *not* concentrated in the endgame

| first divergence | n | mean Δ primary | 95% CI |
|---|---|---|---|
| rounds 1–5 | **26 (43%)** | **+42.3** | [−1.1, +85.8] |
| rounds 6–10 | 22 (37%) | +19.0 | [−1.4, +39.4] |
| rounds 11–16 | 12 (20%) | +13.5 | [−1.8, +28.9] |

Mean first-divergence round **6.4**, median 7, range **1–15**. **43% of drafts first part ways
inside the first five rounds**, and those drafts carry the *largest* mean margin — the reverse of
the "O1's entire effect is the endgame" summary that D86–D90 have used throughout.

That summary is not *wrong*, it is about a different quantity: D89 §12 measured the **mean round
of the first player at each position**, which is essentially unchanged (this board: first WR 1.27
in both arms; first QB 2.73/2.75; first RB 5.27/5.42). Both are true because **35% of first
divergences are same-position swaps** — the arms take *different players at the same position in
the same round*, which moves no positional timing at all.

### 10.2 The decision types, and the one nobody has described

| first-divergence decision type | n | % | mean Δ | 95% CI |
|---|---|---|---|---|
| **same position, different player** | **21** | **35%** | **+50.2** | [−1.9, +102.3] |
| between two multi-slot positions | 16 | 27% | +20.5 | [−7.4, +48.4] |
| off a 1-slot position onto a multi-slot one | 12 | 20% | +14.3 | [−4.9, +33.4] |
| onto a 1-slot position (O1 takes its K/DST *sooner*) | 11 | 18% | +11.5 | [−9.7, +32.8] |

> **Within a position, O1's availability factor is identical for every candidate — so a
> same-position swap cannot be a slot-count effect at all.** It is the *other* consequence of the
> substitution: O1 shrinks the `msv` term and leaves `daVORP` untouched, which changes the
> **ratio** of the two inside `value_base = msv + daVORP`. Players with different msv/vorp mixes
> reorder. This is a **reweighting of marginal-lineup value against replacement value**, it is the
> single most common first divergence, and **no phase from D86 to D90 has named it.**

Two cautions that are not optional. First, the 18% row is the direction correction D89 §12 already
insisted on: **O1 does not defer kickers — it takes fewer of them, and takes its first one
slightly *earlier*** (first K 8.25 → 7.82 on this board). Second, **these means are not causal
shares.** Conditioning on the *first* divergence conditions on an outcome; a draft that first
diverges on a WR swap still reallocates K/DST later. The classification describes where the arms
part ways, it does not partition the margin, and every interval above spans zero.

### 10.3 Reorder or substitution?

| | n | % |
|---|---|---|
| neither arm gets the other's player — a true substitution | 25 | 42% |
| both arms end up with both players — a pure reorder | 17 | 28% |
| one arm also gets the other's player | 18 | 30% |

**58% of first divergences are at least partly reorderings**: the two engines want the same
players and disagree about *when*. Only 42% are genuine substitutions where the rosters really
differ at that spot.

### 10.4 The K/DST conditional, and why it is not the causal test

| | n | mean Δ | 95% CI |
|---|---|---|---|
| O1 actually drafted fewer K+DST | 37 | **+54.0** | **[+25.8, +82.2]** |
| O1 did not | 23 | −13.9 | [−32.6, +4.8] |

Read naively this looks like strong support for the K/DST story — and it directly contradicts
Track A §5. **It is not a causal estimate.** It conditions on a *mediator*: "did O1 behave
differently in this draft" is an outcome of the draft, not an assignment. Drafts where O1 reduced
K/DST are drafts where O1 did something, and a draft where O1 did nothing must score ≈ 0 by
construction. The pre-registered ablation **A3** is the test that can separate these; §11 reports it.

---

## 11. Phase 8 — the 2026 reality check (diagnostic; the board was not changed)

`target_league`, 2026 board (837 projected, 557 market-ranked), slot 1 — whose first three picks
*are* overall #1, #20 and #21 in a 10-team snake.

| pick | Y1 | O1 | |
|---|---|---|---|
| **#1** | Jaxon Smith-Njigba (WR) 508.1, msv 265.3, vorp 107.7 | **same player**, 471.4, msv 234.8, vorp 107.7 | **identical** |
| **#20** | Josh Allen (QB) 316.4, msv 337.4, vorp 73.3 | **same player**, 281.3, msv 291.9, vorp 73.3 | **identical** |
| **#21** | **Jeremiyah Love (RB)** 306.6, msv 243.9, vorp 87.1 | **Trey McBride (TE)** 281.9, msv 169.6, vorp 60.2 | **DIFFERENT** |

**The first divergence is round 3, and it is a 0.2-point tie under Y1.** Y1 scores Love 306.6 and
McBride **306.4** — a gap of 0.2 points on a 306-point scale. O1 scores McBride 281.9 against
Love 269.3, a gap of 12.6. **Y1 was on a knife-edge and O1 broke the tie the other way**, which is
the cleanest single illustration of the whole mechanism: O1's contribution is information where Y1
has almost none.

What it is worth is visible in the endgame, not at the tie:

| | WR | RB | QB | TE | **K** | DST |
|---|---|---|---|---|---|---|
| Y1 | 4 | 3 | 2 | **1** | **4** | 2 |
| O1 | 4 | 3 | 2 | **3** | **2** | 2 |

**Two kickers become two tight ends.** O1 also ends up with Love anyway at a later pick; Y1 never
gets McBride. Y1's four kickers on the 2026 board reproduce D89 §14 exactly.

`dynasty_1qb`, same board: **#1, #20 and #21 are all identical** (Pickens at #21 in both). First
divergence is round 9 — Y1 takes George Kittle (TE), O1 takes Josh Jacobs (RB) — and the roster
difference is **one kicker becoming one running back**. Final rosters share 13/16.

> **Nothing about the top of a 2026 draft changes, in either format**, which is now the fourth
> consecutive phase to say so. What changes is a mid-round tie and the number of kickers.

---

## 12. Track B revisits Track A §5: the K/DST refutation is weaker than I first reported

Track A §5 concluded that kicker restraint is "a marker, not the carrier". **Track B undercuts
that, and the correction belongs here rather than in a footnote.**

Track A tested `ΔnK` — the restraint O1 actually *exercised*. The better variable, and the one
D90 §15 itself proposed, is **Y1's own kicker count: how much over-drafting there was to fix.**
There are now three ways to look at it:

| test | r | supports "K/DST is the carrier"? |
|---|---|---|
| within D89's board — r(Y1 nK level, effect) across 6 seasons | **−0.128** | no |
| within D91's board — r(Y1 nK level, effect) across 6 seasons | **+0.805** | **yes** |
| **between boards** — r(Δ Y1 nK, Δ effect) across the same 6 seasons | **+0.601** | **yes** |

The third row is a genuine natural experiment: *same seasons, same realized outcomes, same code*,
two ECR vintages. Where the refreshed board made Y1 hoard **more** kickers, O1's advantage grew
(2022: Y1 nK 3.90 → 4.30, effect −10.4 → **+158.7**); where it made Y1 hoard **fewer**, the
advantage shrank (2023: 4.50 → 2.90, effect +21.0 → **−20.4**; 2025: 4.00 → 3.00, +94.0 → +8.5).

**And Track A §5.2's decisive counterexample does not replicate.** On D89's board, 2020 had no
kicker hoarding to fix (Y1 nK 2.00) and still returned **+41.3** — which is what made it look
decisive. On this board 2020 also has Y1 nK 2.00 and returns **+9.3**, exactly what the K story
predicts. The counterexample was a property of the board that also produced the anti-correlating
per-season pattern.

> **Revised position.** Two of three tests, including the only one with a natural experiment
> behind it, now favour "the effect is roughly proportional to how much K/DST over-drafting Y1
> does". Track A §5's refutation rested on one board's per-season pattern and a single cell in it,
> and both are board-specific. **I over-read it.** What survives from §5 unchanged is the narrower
> claim that `ΔnK` (restraint exercised) has an inconsistent sign across *formats* — but "room to
> fix" is the better-motivated variable and it does not have that problem.
>
> None of these are causal: every one conditions on a draft outcome rather than an assignment, and
> all have n = 6. **Ablation A3 — K and DST held at rate 1.0 so O1's uplift is switched off at
> exactly those two positions and nowhere else — is the test that can settle it**, and it was
> registered in §3 before any of this was seen.
