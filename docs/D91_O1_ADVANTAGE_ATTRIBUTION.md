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
