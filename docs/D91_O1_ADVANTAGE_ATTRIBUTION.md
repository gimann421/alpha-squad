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
