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
