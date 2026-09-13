# D93 — Reproducible O1 replication and power

*A measurement phase on the D92 instrument. No objective change, no Option G, no production diff.
`models/` and `league/` are **byte-identical to Y1** throughout.*

> ## Headline, stated first
>
> **The experiment D93 was asked to design has already been run, and the power analysis proves no
> larger version of it exists.** Both sample dimensions are hard-capped — exactly **6** usable
> seasons (no July/August board exists at all before 2020, for either market series) and exactly
> **10** draft slots (a 10-team league has ten draft positions) — and D92 proved the simulation is
> deterministic, so repeated seeds contribute **exactly zero** information. The maximum available
> sample is 6 × 10 = **60 paired drafts per format**, which is precisely what D91 ran and D92's
> committed runner reproduced bit-identically.
>
> At that maximum the two formats behave **oppositely**, which no previous phase noticed:
>
> | | between-season SD | within-season SD | **ICC** | MDE at max | effect | resolves? |
> |---|---|---|---|---|---|---|
> | `target_league` | **62.9** | 56.7 | **0.552** | **68.7** | +28.0 | **no — and cannot** |
> | `dynasty_1qb` | **8.2** | 76.8 | **0.011** | **26.9** | +31.5 | marginally yes |
>
> The target format would need **30 seasons** to resolve a 25-point effect; six exist. Its MDE
> floor at infinite slots is **66.1**. **D88's "slots cannot help" is true of the target format and
> false of dynasty** — where slots are the efficient lever and the floor is 8.6.

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| branch | `claude/o1-advantage-attribution-azp7k7` |
| working tree at start | clean |
| HEAD at start | **`265509a05759521547eb1b514e5f820e47e251b0`** — matches the brief |
| `origin/main` | `dc1bf18` — **neither D91 nor D92 is merged** |
| commits `origin/main..HEAD` | 12 (9 D91 + 3 D92) |
| files changed vs `origin/main` | 6 added, 2 modified (**`docs/DECISIONS.md`, `docs/PROJECT_STATE.md` only**) |
| modified pre-existing `src/` file | **none** — the only `src/` change is one added file |
| `src/alpha_squad/models/` | `73b408e9…` — unchanged since `0be8263` (D78 shipped Y1) |
| `src/alpha_squad/league/` | `d4cfd00e…` — unchanged since `74a9542` (D84 baseline) |
| full offline suite | **1338 passed, 44 deselected** |
| `ruff check` / `format --check` | **clean**, 242 files |
| D92 board-vintage tests | **20 passed** |
| `assert_vintage()` | **functions**; passes on the pinned hash and raises `VintageMismatchError` on a wrong one (negative control run) |
| live board vintage | `74b2ea7d680ebe4dfdf4f9d98568810f5a43d4bfde7e9e4428fcc46fac33f4de`, `matches_d89() == True` |
| `scripts/d92_paired_grid.py` registered control | **reproduces** (see §1.2) |

**D91 and D92 are not merged to `main`.** `origin/main` remains `dc1bf18` (PR #17, which merged
D85–D90). Production is unaffected — main is a strict ancestor, and the only non-doc changes on the
branch are three added research files — so this is bookkeeping rather than an integrity failure,
and D93 proceeds. But two phases now sit unmerged and that is worth resolving.

### 1.1 A gap D93's own brief exposed: the research control had never been checked against production

The brief requires the experiment to run "the actual production-path `recommend_draft_pick`" and
forbids "a simplified scoring path" or "a surrogate draft engine". Every O-tier since D86 runs
through `draft_forensics.score_candidate`, which is a **re-implementation** of production's scoring.

`evaluation/decision_counterfactuals.py` guards exactly this risk with
`assert_control_reproduces_production`, whose docstring states the principle plainly: *"if the
control itself disagrees with the engine, every margin reported is measuring the harness rather
than the change."* **`draft_forensics` has no such end-to-end assertion** — only component-level
parity (it shares `positional_feasibility_cap` with production, pinned by test since D61).

The harness does, however, already contain both sides of the comparison: tier **`H`** is documented
as *"the real, unmodified production `recommend_draft_pick`"* and tier **`O0`** as *"the shipped Y1
engine"*. D93 therefore measures `O0` against `H` directly, as a Phase 0 gate, before any
experiment. Result in §2.3.

---

## 2. Experimental instrument

### 2.1 What is pinned

| component | how it is pinned | value |
|---|---|---|
| upstream board blob | sha256, addressable to a public git commit | `a966176d…` (commit `9338630`, 2026-09-11 04:31Z) |
| upstream identity map | sha256 | `0174ea89…` |
| assembled board | per-season hash of `load_season_projections` | combined **`74b2ea7d…`** |
| simulation | determinism verified across `PYTHONHASHSEED` 0–5 (D92) | rosters and all gate-bearing metrics invariant |
| model training | full retrain reproduces the board bit-identically (D92) | all 7 seasons |
| runner | **committed** — `scripts/d92_paired_grid.py`, stamps git HEAD, argv, vintage, s/pick | — |

### 2.2 What is still NOT reproducible, and is therefore not used as evidence

D86–D90's published numbers. D92 established their runner was never committed and their outputs do
not regenerate from identical inputs. **The +49.0 is not cited in this phase as a measurement**, and
neither is D90's +20.8. The only measurements D93 treats as real are the ones on the pinned vintage
that the committed runner reproduces.

---

## 3. Estimand (Phase 1)

Fixed before any D93 result was examined.

| element | definition |
|---|---|
| **unit of observation** | one **(format, season, draft slot)** paired draft: two 16-round snake drafts from the same board against the same nine fair-market opponents, differing **only** in the objective used for the team-in-question's own pick |
| **primary metric** | **realized weekly no-foresight starter points**, summed over `FANTASY_WEEKS` 1–17: each week, field the best legal lineup from the roster players who actually played, ranked by *preseason projection* (not by hindsight) |
| **estimand** | `E[ O1 − Y1 ]` in that metric, over the population of (season, slot) draws in a given format |
| **paired structure** | the pair is the (format, season, slot) cell; the difference is taken **within** the cell, so board, opponents and realized player outcomes difference out |
| **clustering** | **by season.** All ten slots in a season share one realization of player outcomes, so they are not independent; the season is the independent unit |
| **interval** | season-clustered: mean of season means, `SE = sd(season means)/√k`, `t(k−1, .975)` |
| **draft-slot treatment** | all 10 slots, every season, both arms — a fixed census of the slot dimension, not a sample |
| **format treatment** | **analysed separately.** The primary format is `target_league`; `dynasty_1qb` is a secondary, independent-board replication. They are **not pooled** into the primary, because they share seasons *and* realized outcomes and so are not independent clusters |

**Secondary metrics** (all pre-specified, all reported whatever they show): season-long starter
points, total roster points, bench contribution, conversion efficiency (primary ÷ roster points),
missed player-weeks, positional counts (QB/RB/WR/TE/K/DST), first-round-by-position for all six
positions, capacity breaches, unfilled mandatory slots, first-divergence round, per-slot effects.

**Not redefined after the fact.** The primary metric is D86's `PRIMARY_METRIC =
"weekly_no_foresight"`, imported rather than restated.

---

## 4. Power analysis (Phase 2) — done before running anything

Variance model for the paired difference of season `s`, slot `j`:

    d[s,j] = mu + a[s] + e[s,j],   a[s] ~ (0, sb²),  e[s,j] ~ (0, sw²)
    Var(season mean over n slots) = sb² + sw²/n
    SE(mean over k seasons)       = sqrt( sb²/k + sw²/(k·n) )
    MDE                           = t(k−1,.975) · SE

Slots attack only the `sw²/n` term. The **ICC** `sb²/(sb²+sw²)` is the share of variance slots can
never reduce. Estimated by method of moments on the pinned-vintage grids (60 paired drafts each):

| | effect | SD of season means | `sw` | `sb` | **ICC** | SE | **MDE** | effect/MDE |
|---|---|---|---|---|---|---|---|---|
| `target_league` | +28.0 | 65.4 | 56.7 | **62.9** | **0.552** | 26.7 | **68.7** | 0.41 |
| `dynasty_1qb` | +31.5 | 25.6 | 76.8 | **8.2** | **0.011** | 10.5 | **26.9** | **1.17** |

### 4.1 Which lever actually works is format-dependent — and nobody had noticed

**`target_league` — slots are futile:**

| slots | 4 | 10 | 20 | 50 | 100 | ∞ |
|---|---|---|---|---|---|---|
| MDE | 72.4 | 68.7 | 67.4 | 66.6 | 66.3 | **66.1 (floor)** |

Even infinitely many slots leave MDE at **66.1** against an effect of **28**. Seasons needed to
reach the 25-point economic threshold: **30**.

**`dynasty_1qb` — slots are the efficient lever:**

| slots | 4 | 10 | 20 | 50 | 100 | ∞ |
|---|---|---|---|---|---|---|
| MDE | 41.2 | 26.9 | 20.0 | 14.3 | 11.8 | **8.6 (floor)** |

Its ICC is **0.011**: the effect is nearly homogeneous across seasons, so almost all the variance is
slot-level and reducible. **D88's conclusion that "draft slots provably cannot resolve it" is a
correct statement about the target format and does not generalise.**

### 4.2 But both levers are already exhausted, so neither finding can be acted on

| lever | cap | why |
|---|---|---|
| **seasons** | **6** (2020–2025) | **no July/August board exists before 2020** for either series — `preseason_page_type` returns `None` for 2015–2019. Not a judgement call; the rows do not exist. 2026 has a board but is unplayed, so it has no realized outcome to score |
| **slots** | **10** | a draft slot is a team's draft position and both leagues have `teams: 10`. `run_tier_ablation` defaults to `range(1, teams+1)` |
| **seeds** | **0 bits** | D92 verified the simulation is deterministic: identical rosters and identical gate-bearing metrics across `PYTHONHASHSEED` 0–5. A repeat run adds nothing |
| **formats** | 2 testable | §6 |

> **The maximum attainable sample is 6 × 10 = 60 paired drafts per format, and that is exactly what
> has already been run.** So the correct action is **not** to run a larger experiment — there isn't
> one — and D93 does not pretend otherwise.

### 4.3 Honest limit on what D93 can therefore claim

Because the sample is exhausted and the simulation is deterministic, **D93 cannot be an independent
replication of D91's effect sizes.** Re-running the same 60 cells on the same pinned board must
return the same numbers, and D92 already demonstrated that for 12 of them. The effect sizes were
known to me before this phase began, so **nothing about the magnitude is being tested blind here**,
and this document does not present it as if it were.

What D93 *can* establish, and what was genuinely unknown when the analysis plan was fixed:

1. whether the research control reproduces **production** (§1.1, §2.3) — this had never been checked
   and could invalidate every O1 margin ever published;
2. the **variance structure** and therefore whether any feasible experiment could resolve the effect
   (§4.1–4.2) — established above, before the confirmatory run;
3. whether the full 60-cell grid reproduces through the **committed** runner, not just 12 cells;
4. the **mechanism** and **stability** diagnostics under the registered analysis plan.

---

## 5. **The phase's decisive finding: the O-tier control was never the shipped engine**

The Phase 0 parity gate (§1.1) — mandated by D93's own brief, and never run before — fails.

### 5.1 The measurement

`target_league`, tier `O0` (the D86 control, documented as *"the shipped Y1 engine"*) against tier
`H` (*"the real, unmodified production `recommend_draft_pick`"*), same board, same opponents, same
loop, 18 cells across all six seasons and slots 1/5/10:

| | result |
|---|---|
| cells with an identical drafted roster | **0 / 18** |
| first differing pick | median **3**, min **1** |
| season-long starter points, O0 − H | **−27.0** (all cells) · **−43.0** (excluding 2020) |

And the positional signature of the gap is the one this entire research line has been studying:

| position | `O0` (research control) | `H` (production) | gap |
|---|---|---|---|
| **K** | **3.13** | **2.07** | **+1.07** |
| RB | 2.27 | 2.93 | −0.67 |
| WR | 4.73 | 5.33 | −0.60 |
| DST | 2.07 | 1.73 | +0.33 |

*(excluding 2020, whose default `page_type` hands production an empty preseason board — a separate
issue, and the gap is larger without it)*

**Production already drafts almost exactly to kicker capacity** — 2.00 in five of six seasons. The
over-drafting O1 was celebrated for curing is a property of the **harness control**, not of Y1.

### 5.2 The bisect: which tiers are the shipped engine?

One cell (2024, slot 1), every tier that has ever claimed to be the shipped engine:

| tier | nK | starter pts | identical to production `H`? |
|---|---|---|---|
| **H** (production) | 2 | 1842.4 | — |
| `W1`, `X0`, `Z0`, `S0`, `Q0`, `L0` | 2 | **1842.4** | **YES, all six** |
| `V0` | 3 | 1802.9 | no |
| **`O0`** | **3** | **1802.9** | **NO** |

So D79's, D84's and D85's controls *are* production. **D86's is not**, contrary to its own
documented claim that O0 is "byte-identical to L0/Q0/Z0".

### 5.3 Root cause, verified

`draft_forensics.py:1967` dispatches the **draft-aware replacement level** (D67's shipped rule) to
an explicitly enumerated list of tier families:

```python
elif (tier in X_TIERS or tier in Y_TIERS or tier in ALL_Z_TIERS
      or tier in ALL_S_TIERS or tier in Q_TIERS or tier in L_TIERS):
    dynamic_levels = consumption_replacement(static.consumption_demand)(...)
```

**`O_TIERS` is not in that list.** So for every O-tier `dynamic_levels` stays `None`, and
`score_candidate` falls back to the **static** replacement level — the D65 defect D67 shipped to
remove. Demonstrated directly:

```
_pick_by_tier, 2024 slot 1, top candidate:
   O0: score 570.74   replacement level used = STATIC
   Z0: score 613.15   replacement level used = draft-aware
```

**This is the D85 defect, repeated verbatim**, and the code comment three lines below the bug
describes it: *"D85: the L-tiers MUST be here. Omitting them silently reverted every L-tier to the
STATIC replacement level … which made the D85 control score 1963.62 against
Q0/Z0/S0/W1/X0's 2042.80 on the identical board."* D86 added the O-tiers and did not add them here.

### 5.4 Why the guard test did not catch it

`test_o0_is_the_shipped_engine` exists, and its docstring names exactly this risk. It passes — for
the wrong reason:

| path | O0 vs Z0 | why |
|---|---|---|
| `score_candidate` called directly — **what the test does** | **identical on all 602 candidates** | the test never passes `dynamic_levels`, so it is `None` for *both* tiers and both fall back to static |
| `_pick_by_tier` — **what a real draft does** | **different** (570.74 vs 613.15) | the dispatch that sets `dynamic_levels` lives here, and it omits `O_TIERS` |

**The hoisting the defect lives in happens in `_pick_by_tier`; the guard asserts on
`score_candidate`.** It cannot see the bug it was written to prevent. `test_every_o_tier_is_...
_draft_aware` likewise only asserts membership in `DRAFT_AWARE_REPLACEMENT_TIERS`, which is the set
`score_candidate` consults — not the dispatch list that actually computes the level.

### 5.5 What this invalidates

> **Every O-tier number published from D86 through D92 — the control and the candidate alike — was
> measured on an engine that silently reverted to the D65-era static replacement level.**

* **O0 is not Y1.** It is ~43 season-long starter points worse than production and drafts ~1.07
  more kickers.
* **O1 is not "Y1 + weekly marginal value."** It is "a D65-era engine + weekly marginal value",
  because it inherits the same omission.
* **O1's headline mechanism was largely repairing a harness defect.** Production drafts 2.07
  kickers; the defective control drafts 3.13; O1 drafts 2.32. O1 moved the control *towards*
  production's existing behaviour without reaching it.
* D91's finding that Y1's marginal value is degenerate across the bench (spread 0.48 points) was
  measured on the shipped `marginal_starter_value` directly, **not** through the O-tier path, so
  that measurement is unaffected. D92's board-immutability and determinism results are likewise
  unaffected — they are properties of the data and the simulator, not of the tier dispatch.

**No production code is touched by this finding.** The defect is in research/evaluation code, and
production `recommend_draft_pick` has been correct throughout — indeed it is the reference that
exposed the problem.

---

## 6. Historical sample (Phase 3)

Selection rule, applied to every season 2015–2026 and reported in full rather than filtered:

| season | `target_league` (`ro`) | `dynasty_1qb` (`do`) | verdict |
|---|---|---|---|
| 2015–2019 | **no July/August board at all** — `preseason_page_type` returns `None` | same | **EXCLUDED** — the rows do not exist |
| 2020 | `redraft-offense`, 612 projected, 458 ranked, 74.8% | `dynasty-offense`, 419 ranked, 68.5% | included |
| 2021 | `redraft-overall`, 636 / 490, 77.0% | 459, 72.2% | included |
| 2022 | 651 / 496, 76.2% | 466, 71.6% | included |
| 2023 | 610 / 484, 79.3% | 471, 77.2% | included |
| 2024 | 602 / 515, 85.5% | 471, 78.2% | included |
| 2025 | 629 / 480, 76.3% | 444, 70.6% | included |
| 2026 | board exists (837 / 524) | 523 | **EXCLUDED** — unplayed; no realized outcome to score against |

**No season was dropped for being difficult or unfavourable.** The 2015–2019 exclusion is not a
judgement: `preseason_page_type` finds no July/August scrape in either market series, so there is
no preseason board for the fair-market opponents to draft against, and D89's `EmptyMarketBoardError`
guard would refuse the run. **Six seasons is the entire population, not a sample of it.**

### A defect this survey surfaced, affecting production rather than the research path

For 2020 the preseason board is published under `redraft-offense`, not `redraft-overall`. D89 fixed
this for the research path by threading a resolved `page_type` into `load_season_static`.
**`recommend_draft_pick` takes no `page_type` argument** and resolves the series' default, so in
2020 production reads `redraft-overall` and gets an **empty** preseason board. That is exactly why
`Z0`/`Q0`/`L0` — which otherwise reproduce production in **20 of 20** cells — mismatch in precisely
the four 2020 cells and nowhere else.

This is a real finding about a production code path, not about the harness. It affects only a
*historical backtest* of 2020: a live draft resolves the current season, where the default page is
correct. **Nothing is changed here** — D93 forbids production edits — and it is recorded as a
defect for a future phase to fix deliberately.

---

## 7. Format sample (Phase 4)

`market/series.py` derives the board from `is_dynasty × is_superflex`, so **exactly four** market
series exist. The candidate set is therefore closed and was enumerated before selection:

| series | format | seasons | K rows | DST rows | status |
|---|---|---|---|---|---|
| `ro` | redraft 1QB | 6 | 1,692 | 1,473 | **primary** — `target_league` |
| `do` | dynasty 1QB | 6 | 1,533 | 1,494 | **secondary** — `dynasty_1qb` |
| `dsf` | dynasty superflex | 5 | **0** | **0** | **structurally untestable** |
| `rsf` | redraft superflex | 5 | **0** | **0** | **structurally untestable** |

Both superflex boards carry **zero** kickers and zero defenses (FantasyPros' "OP" pages rank
offensive players only), and `legacy_2qb_dynasty`'s lineup has no K or DEF slot at all. Per D93's
instruction — *"do not treat formats with no K/DST data as evidence for the K/DST mechanism"* — the
legacy format is reported as **structurally untestable for this mechanism, not as a pass or a
fail**, wherever a gate touches K/DST.

**No new format was created.** `dynasty_1qb` was registered in D90 on a pre-specified tie-break and
is reused unchanged.

---

## 8. Pre-registration, and what happened to it (Phase 5)

The estimand (§3), the power analysis (§4), the sample rule (§6) and the format set (§7) were all
fixed before the confirmatory run. The registered experiment was:

> `scripts/d92_paired_grid.py`, board vintage `74b2ea7d…` asserted as a precondition, both 1-QB
> formats, seasons 2020–2025, slots 1–10, arms `O0` (control) and `O1` (candidate), primary metric
> `weekly_no_foresight`, season-clustered `t(5)` interval, D84's gates unchanged, economic threshold
> 25.0, and the stopping rule that **no additional sample exists** (§4.2).

**That experiment was never run, because the Phase 0 production-parity gate failed first (§5).**
Its control arm `O0` is not the shipped engine, so the registered contrast would have measured
"a D65-era engine + weekly marginal value" against "a D65-era engine" and reported it as O1 vs Y1.

Running it anyway would have produced a number — and D91's artifacts say roughly which number —
but it would not have been an answer to D93's question. **The gate did its job, which is the point
of having gates run before the experiment rather than after.** What follows measures the defect's
consequences instead, which is the honest remaining use of the phase.

---

## 9. The defect measured against the correct baseline (Phases 7–9)

24 cells per format (6 seasons × slots 1/4/7/10), board vintage asserted, three arms:
**`H`** = real production `recommend_draft_pick`, **`O0`** = the D86 "control", **`O1`** = the
candidate (which **inherits** the same defect).

### 9.1 `target_league`, primary metric `weekly_no_foresight`

| arm | primary | season-long | roster pts | bench | nK | nRB | nTE |
|---|---|---|---|---|---|---|---|
| **`H`** production | **1931.5** | 1936.2 | 2578.9 | 418.2 | **2.08** | **2.92** | **2.42** |
| `O0` defective control | 1922.9 | 1907.6 | 2574.9 | 419.6 | **2.96** | 2.21 | 2.00 |
| `O1` candidate | 1941.5 | 1929.0 | 2601.3 | 444.7 | 2.29 | 2.50 | 2.54 |

> **Production's roster composition already resembles O1's far more than O0's does.** On kickers,
> running backs and tight ends alike, `H` sits where O1 was trying to move the control to — and in
> two of the three it goes further than O1 manages.

Paired contrasts, season-clustered 95% CI:

| contrast | effect | 95% CI |
|---|---|---|
| **`O1 − O0`** — what D86–D92 published | **+18.6** | [−47.9, +85.0] |
| **`O1 − H`** — candidate vs **real production** | **+10.0** | [−78.1, +98.1] |
| **`O0 − H`** — the harness defect alone | **−8.6** | [−85.0, +67.9] |

**Measured against the correct baseline the candidate's advantage falls from +18.6 to +10.0**, and
roughly **46%** of the published margin (8.6 of 18.6) is the harness defect rather than the
objective. Every interval spans zero by a wide margin, exactly as §4's power analysis said it must.

Per-season, `O1 − H` is **+77 / +83 / +90 / −17 / −80 / −92** across 2020→2025 — a monotone decline
from strongly positive to strongly negative. Noted, not interpreted: it is a post-hoc observation on
six clusters and D90 §7's monotone pattern already failed to replicate once.

### 9.2 `dynasty_1qb` — the defect generalises, and **its sign flips**

| arm | identical to `H` | mean nK | mean season-long starter pts | vs `H` |
|---|---|---|---|---|
| **`H`** production | 24/24 | **2.00** | 2058.0 | — |
| `Z0` / `Q0` / `L0` | **20/24** (only 2020) | 1.96 | 2084.4 | **+26.4** |
| **`O0`** | **0/24** | 2.08 | 2104.4 | **+46.5** |

The dispatch omission affects both formats — `O0` never reproduces production in either — but its
**consequence reverses**: in the target format the defective control is **28.6 points worse** than
production, in dynasty it is **46.5 points better**. A defect whose sign depends on the format
cannot be treated as a constant offset that "cancels in the paired difference".

*(`Z0`/`Q0`/`L0` differ from `H` by +26.4 here for the separate, documented 2020 `page_type` reason
in §6 — four of twenty-four cells — not because of the dispatch bug.)*

### 9.3 Why `O1 − H` is not a clean estimate of the objective either

`O1` is built on the same `score_candidate` path as `O0`, so it carries the same static-replacement
fallback. `O1 − H` therefore conflates **two** changes: the weekly marginal-value objective (the
thing under study) and the reverted replacement level (a defect). It is the most decision-relevant
number currently obtainable, and it is still **not** an estimate of O1's value.

> **The comparison that would answer D93's question — the shipped engine against the shipped engine
> plus weekly marginal value — has never been run, in any phase.**

### 9.4 RB interaction (Phase 9)

D91 closed this with algebra: at an empty roster O1's marginal term reduces to
`rate(position) × projection`, a positive per-position rescale, and no positive rescale can reorder
a board — so O1 cannot reach an elite-RB projection error, and RB's rate being the lowest of the six
means it discounts elite RBs *most*. **That argument is about `expected_weekly_marginal_value`
versus `marginal_starter_value` and does not depend on the replacement level**, so it survives this
phase's finding intact. No RB projection was touched and no new perturbation was run.

---

## 10. The instrument repair, and the corrected experiment **pre-registered before it ran**

### 10.1 The repair

`or tier in O_TIERS` added to `_pick_by_tier`'s draft-aware-replacement dispatch, plus
`TestD93DraftAwareDispatch`. Research/evaluation code only; `models/` and `league/` untouched.

Verified behaviourally: **`O0` now reproduces both production (`H`) and `Z0` in 12/12 cells across
both 1-QB formats**, drafting 2 kickers to match production, where before it matched production in
**0/24**.

Verified as a guard, by temporarily reverting the fix:

| test | with the bug | with the fix |
|---|---|---|
| `test_every_draft_aware_tier_actually_receives_a_draft_aware_level` (new) | **FAILS** | passes |
| `test_o0_reproduces_the_shipped_engine_THROUGH_pick_by_tier` (new) | **FAILS** | passes |
| `test_o0_is_the_shipped_engine` (pre-existing) | **PASSES** | passes |

The pre-existing guard passing while the bug is present is the direct demonstration that it was
blind to the defect it was written to prevent. The new loop covers **every** tier in
`DRAFT_AWARE_REPLACEMENT_TIERS`, exempting only tiers whose own spec declares static intent
(`V_TIER_SPEC["V0"] is None`; `W_TIER_SPEC["W0"/"W3"][0] is None`) — which is the discriminating
property, since the O-tiers had no such declaration anywhere.

### 10.2 Pre-registration of the corrected contrast (registered at commit `3681970`, before running)

For the first time in this research line, O1 can be compared against a control that *is* the
shipped engine. That is a **different experiment** from the one §8 registered, so it gets its own
registration rather than being slipped in after a defect was found.

| element | value |
|---|---|
| code | HEAD `3681970` (dispatch repaired, guards in place) |
| board vintage | `74b2ea7d680ebe4dfdf4f9d98568810f5a43d4bfde7e9e4428fcc46fac33f4de`, asserted as a precondition |
| formats | `target_league` (primary), `dynasty_1qb` (secondary) — analysed separately, never pooled |
| seasons | 2020–2025 (the whole population, §6) |
| slots | 1–10 (the whole census, §4.2) |
| arms | `O0` (now verified == production `recommend_draft_pick`) and `O1` |
| primary metric | `weekly_no_foresight` |
| interval | season-clustered, `t(5)`, per §3 |
| gates | D84's, imported unchanged. **G7 is not relaxed.** No gate added or re-thresholded |
| economic threshold | 25.0 |
| stopping rule | **the sample is exhausted** (§4.2). No additional seasons, slots or seeds will be sought whatever the result |
| exclusions | 2015–2019 (no board), 2026 (unplayed). 2020 **is included**: both arms read the D89-resolved `page_type`, so the O0-vs-O1 contrast is unaffected by the production `page_type` defect in §6 |

**Variance is re-estimated from the corrected runs**, not carried over: §4's ICC and MDE were
measured on the defective engine and may not survive the repair. The decision rule is registered;
the MDE number is not assumed.

### 10.3 Predictions, recorded before any corrected result was seen

> **P1.** `O0` reproduces production on the corrected path. *(Already verified on 12 cells; a
> subset is re-verified inside the registered run.)*
>
> **P2 — direction.** O1's margin against the **corrected** control is **smaller** than the
> +18.6 (24-cell) / +28.0 (60-cell) measured against the defective one, because §9.1 attributes
> about **46%** of that margin to the defect itself.
>
> **P3 — the mechanism should largely disappear.** This is the sharp one. O1's signature
> achievement was kicker restraint, and the corrected control **already drafts to capacity**
> (2.08, and exactly 2.00 in the cells checked). There is almost nothing left for O1 to remove, so
> `ΔnK` should collapse toward zero. If it does, then the K/DST mechanism six phases described was
> **an artifact of the defect**, not a property of the objective.
>
> **P4 — most likely outcome.** A small margin with an interval spanning zero: verdict **B** or
> **C**, not **A**. Registered so a null cannot be reported as a surprise, and so a positive
> result cannot be claimed as predicted.

---

## 11. The corrected result (Phases 7, 8, 10) — all four predictions confirmed

Registered grid, repaired dispatch, board vintage asserted, 60 paired cells per format,
`git HEAD f11c899`.

### 11.1 Primary

| | `target_league` | `dynasty_1qb` |
|---|---|---|
| **effect (O1 − Y1)** | **+3.8** | **+27.1** |
| season-clustered 95% CI | **[−43.2, +50.8]** | **[−7.8, +62.0]** |
| MDE (re-estimated) | 47.0 | 34.9 |
| SD of season means | 44.8 | 33.3 |
| cells won by O1 | 27/60 | 36/60 |
| median cell | **−7.9** | +17.3 |
| seasons O1 worse | **4/6** | 1/6 |
| worst leave-one-season-out | **−11.3** | +18.6 |
| per season | −12 / +79 / +29 / −15 / −8 / −50 | +9 / +70 / +51 / −24 / +39 / +17 |

**For comparison, the same contrast on the defective control was +28.0 [−40.7, +96.7].**

### 11.2 P3 — the mechanism is gone

| | defective `Y1` | defective O1 | **corrected `Y1`** | **corrected O1** |
|---|---|---|---|---|
| kickers drafted | 2.98 | 2.32 (**−0.67**) | **2.03** | **2.00** (**−0.03**) |
| picks off ≤1-slot positions | — | −0.82 | — | **−0.28** |
| Y1 capacity breaches (60 drafts) | **62** | — | **2** | — |

In `dynasty_1qb` it vanishes entirely: ΔnK **+0.05**, ΔnRB −0.03, ΔnTE +0.03, reallocation
**−0.03**.

> **The K/DST mechanism that D86–D92 described, and that five plain-English summaries reduced to
> "take the kicker you need, then stop", was an artifact of the dispatch defect.** Production
> already drafts to kicker capacity — 2.03 per draft, with **2 capacity breaches in 60 drafts**
> against the defective control's 62. There was almost nothing for O1 to correct, and the corrected
> numbers say it corrects almost nothing.

### 11.3 What the dynasty residual actually is — and it is not the theorised mechanism

`dynasty_1qb` keeps **+27.1**, and the registered secondary metrics say it arrives by a route O1
was never theorised to take:

| | value |
|---|---|
| conversion efficiency (primary ÷ roster points) | **−0.0001** — flat |
| total roster points | **+36.1** |
| positional reallocation | **−0.03 / +0.03** — none |

`+36.1 × 0.7575 ≈ +27.3`, which is the whole effect. **O1's dynasty gain is pure raw-roster
quality with zero conversion gain and zero reallocation** — the opposite of "convert the same
roster into more lineup points", which was the entire rationale. It is a real, reproducible
residual and it is **not** evidence for the weekly roster-utility story.

### 11.4 Prediction scorecard

| | prediction | outcome |
|---|---|---|
| **P1** | `O0` reproduces production | **CONFIRMED** — 16/16 picks on the 2026 board; 12/12 historical cells |
| **P2** | margin smaller than +28.0 | **CONFIRMED** — +3.8 |
| **P3** | the mechanism largely disappears | **CONFIRMED** — ΔnK −0.67 → **−0.03** |
| **P4** | small margin, CI spans zero, verdict B or C | **CONFIRMED** |

---

## 12. Gate table (Phase 11) — registered gates, none added, relaxed or re-thresholded

| gate | threshold | `target_league` | `dynasty_1qb` | `legacy_2qb_dynasty` |
|---|---|---|---|---|
| G1 | no dedicated position zeroed more than control | **PASS** (0 v 0) | **PASS** (0 v 0) | structurally untestable |
| G2 | roster infeasibility ≤ control | **PASS** (0 v 0) | **PASS** (0 v 0) | — |
| G3 | primary worse in ≤ 1 season | **FAIL (4/6)** | **PASS** (1/6) | — |
| G4 | no position drafted > 2 rounds earlier | **PASS** (max 0.05 rd) | **PASS** (0.03 rd) | — |
| G5 | no increase in capacity breaches | **PASS** (0 v 2) | **PASS** (0 v 5) | — |
| G6 | LOSO margin stays positive | **FAIL (−11.3)** | **PASS** (+18.6) | — |
| G8 | clustered 95% CI excludes zero | **FAIL** [−43.2, +50.8] | **FAIL** [−7.8, +62.0] | — |
| G9 | primary margin ≥ 25.0 | **FAIL (+3.8)** | **PASS** (+27.1) | — |
| G10 | season-long margin ≥ −25.0 | **PASS** (+11.9) | **PASS** (+36.9) | — |
| **G7** | **cross-format sign** | both positive (+3.8 / +27.1) — **PASS on sign**, but the primary format's is indistinguishable from zero | | |

`legacy_2qb_dynasty` is reported as **structurally untestable** for K/DST-touching gates (§7), not
as a pass.

---

## 13. 2026 reality check (Phase 12), on the repaired engine

`target_league`, 2026 board, slot 1 (whose first three picks are overall #1/#20/#21):

| pick | production `H` | `O0` | `O1` | |
|---|---|---|---|---|
| **#1** | Jaxon Smith-Njigba (WR) | same | same | **identical** |
| **#20** | Josh Allen (QB) | same | same | **identical** |
| **#21** | Jeremiyah Love (RB) 358.5 | **same, 358.5** | same, 321.2 | **identical** |

**`O0` now matches production on all 16 picks (16/16).** And the full roster composition is
**identical across all three arms** — QB 2, RB 3, WR 5, TE 2, **K 2**, DST 2.

> On the defective engine D91 reported Y1 taking **four** kickers against O1's two. On the repaired
> engine **production and O1 both take two.** The kicker difference at the top of a real 2026 draft
> does not exist.

First divergence is **round 9**: Y1 takes Tucker Kraft (TE), O1 takes Courtland Sutton (WR) — a
swap between two *multi-slot* positions, not a K/DST decision. Final rosters share 13/16.

---

## 14. Computational cost (Phase 13), measured

| arm | s/pick | s/draft | vs Y1 |
|---|---|---|---|
| `O0` (= production Y1) | **0.026** | 0.4 | 1.0× |
| `O1` full board | **4.61** | 74 | **≈177×** |

Reproducible: both formats' runs report the same figures (0.0263/4.615 and 0.0259/4.588). Memory
is unremarkable — the Monte Carlo holds only the roster and a values dict. Cost scales linearly in
candidate count (each candidate gets `DEFAULT_AVAILABILITY_DRAWS = 200` lineup allocations). A
single live recommendation is ≈ 4.6 s, immaterial in a real draft. No optimisation was attempted and
no new shortlist was created.

---

## 15. Ship / do not ship (Phase 14)

> ### **DO NOT SHIP. Y1 remains production. Verdict: C — REJECT, as specified.**

Not **A**: G8 fails in both formats, G3/G6/G9 fail in the primary one.

Not **D**: the instrument limitation was found *and repaired* inside this phase, and the corrected
comparison ran. The board is pinned, the simulation is deterministic, the control is now verified
against production, and the guard that was missing is in place.

Not **B**: B is for a candidate that is "directionally and mechanistically encouraging" where the
benchmark cannot resolve it. **The mechanism is refuted, not unresolved.** ΔnK went −0.67 → −0.03;
positional reallocation −0.82 → −0.28 (target) and −0.03 (dynasty); the 2026 kicker difference
disappeared entirely. The primary format's effect fell to **+3.8** with a **negative median cell**,
**4 of 6 seasons worse**, and a **leave-one-season-out that goes negative**.

**C**, therefore — and specifically: *reject O1 as specified and reject the mechanism as described.*
The one thing that survives is the `dynasty_1qb` residual of **+27.1**, which is real, reproducible,
5-of-6-seasons positive — and which §11.3 shows arrives entirely through raw roster quality with
**zero** conversion gain and **zero** reallocation. That is not the hypothesis O1 was built on, so
it cannot be counted as support for it. It is an unexplained finding, recorded as the phase's open
question rather than as a reason to keep the candidate alive.

**Production integrity:** `models/` `73b408e9` and `league/` `d4cfd00e` unchanged; the only `src/`
changes on this branch are one added research module and a one-line research-harness repair. 1340
tests pass, ruff clean.

---

## 16. Most important remaining uncertainty (Phase 17)

**Why `dynasty_1qb` returns +27.1 through raw roster quality alone.** It is reproducible, positive
in 5 of 6 seasons, LOSO-stable, and arrives with *zero* conversion gain and *zero* positional
reallocation — so none of the explanations this research line has developed accounts for it. It is
also below resolution: its CI is [−7.8, +62.0] and §4 shows the sample is exhausted, so it cannot
be settled by more of the same data.

The secondary uncertainty is the one D92 left and D93 sharpened: **seven phases of results rested
on a control nobody had checked against production.** The repair and the new guard close this
instance; what remains unknown is whether other research modules carry the same class of drift.
`decision_counterfactuals` has `assert_control_reproduces_production`; `draft_forensics` now has a
dispatch-level guard; nothing systematically checks the rest.

---

## 17. Next research question (Phase 18)

> **Re-check the *other* published draft-layer conclusions against production, the same way Phase 0
> checked this one — starting with the ones that shaped current beliefs.**

D85's "Y1 over-values K 5.34× and DST 8.10×" and D91's causal chain (degenerate marginal value →
daVORP decides the endgame → kickers get hoarded) were both built while the visible evidence was a
control that drafted **2.98** kickers. Production drafts **2.03**. D91's degeneracy *measurement*
stands — it was taken on the shipped `marginal_starter_value` directly — but **its last link does
not**: the degeneracy does not produce kicker hoarding in production, because production's
draft-aware replacement level changes what daVORP says. That chain should be re-measured on the
repaired engine before any of it is used to motivate a future change.

Cheap and worth doing alongside it: give `recommend_draft_pick` the D89 `page_type` resolution
(§6), so a historical backtest of 2020 stops handing production an empty preseason board.

**Explicitly not recommended:** implementing Option G, re-weighting O1, adding a shortlist, more
seasons or slots (§4.2 proves none exist), or treating the dynasty residual as a reason to keep O1.

---

## 18. Plain-English trust assessment (Phase 19)

**The kicker story was a bug in the measuring instrument, and I should say that plainly.** For seven
phases this project has reported that Alpha's draft engine over-buys kickers and that a better
objective would stop it. The engine that over-bought kickers was never the one in production — it
was a research copy that had silently lost a 2023 fix, so it valued late-round players against the
wrong baseline. **Real production drafts two kickers, which is exactly the right number**, and on
the 2026 board it and the candidate draft identical rosters down to the last slot.

**With that corrected, the candidate's advantage mostly evaporates.** In the format this product
targets it falls from +28 to **+3.8 points a season** — smaller than the measurement error, worse
than production in four of six seasons, and negative at the median draft. The mechanism it was
supposed to work through is gone: it now changes the kicker count by **0.03**.

**One thing did not evaporate**, and honesty requires flagging it rather than burying it: in the
dynasty format the candidate is still **+27** points ahead, consistently. But when you look at *how*,
it is not doing what it was designed to do — it is simply drafting players who scored more, with no
improvement at all in turning a roster into weekly points. That is an unexplained result, not a
vindication, and it is not a reason to ship.

**What to trust now:** the instrument, more than before. The board is pinned by hash, the simulator
is deterministic, the control is verified against real production, and the guard that should have
caught this defect exists and has been shown to fail when the bug is reintroduced. **What not to
trust:** any draft-layer number published between D86 and D92, and the parts of D85's and D91's
reasoning that depend on production over-drafting kickers. It does not.

---

## 19. The three questions, answered directly

> **"With the D92 instrument, is O1's advantage reproducible?"**

**No — it largely disappears once the control is actually production.** The D92 instrument pins the
board and the simulator, and it reproduced D91's numbers bit-identically; what neither D92 nor any
earlier phase checked is that the *control arm* was the shipped engine. It was not. Against the real
engine the target-format advantage falls from +28.0 to **+3.8** [−43.2, +50.8], and the mechanism
that explained it collapses from ΔnK −0.67 to **−0.03**.

> **"If reproducible, is it large and stable enough to justify replacing Y1?"**

**No.** It fails G8 in both formats and G3/G6/G9 in the primary one. In the target format it is
worse than production in 4 of 6 seasons, negative at the median draft, and leave-one-season-out
takes it negative. The dynasty residual (+27.1) is the only survivor and it arrives through a route
that contradicts O1's rationale.

> **"If not, what is the exact reason we cannot decide?"**

**On the primary format there is no longer much to decide** — the effect is +3.8 against an MDE of
47.0, and §4.2 proves the sample that produced that MDE is the entire available population (6
seasons × 10 slots, with seeds contributing nothing because the simulation is deterministic). So it
is not that a bigger experiment would settle it; **no bigger experiment exists**.

**On the dynasty residual we genuinely cannot decide**, for the same structural reason: +27.1 with a
CI of [−7.8, +62.0] and no remaining sample to add. That one is a real open question, and the
honest statement is that this benchmark cannot resolve it — not that O1 earned it.
