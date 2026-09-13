# D92 — Pin the instrument before changing the objective

*An instrumentation/reproducibility experiment. No objective changes. `models/`, `league/` and all
of `src/` are **byte-identical to production** throughout.*

> ## Headline, stated first because it retracts a D91 conclusion
>
> **The historical ECR board is NOT mutable, and board vintage cannot explain the D89 → D91
> difference.** D91's central claim was based on my own measurement error: I compared *all*
> `market_rank` entries (533 in 2020) against D89's published *market-ranked-within-the-projected-
> board* (458). Measured the way D89 measured it, **every one of ~90 published board figures
> matches exactly**, and the upstream board file's SHA-256 is provably the same blob D89 read.
>
> The real irreproducibility lies elsewhere: **D88/D89/D90's runner was never committed**, so their
> published outputs cannot be regenerated from the repository even though every input can.

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| branch | `claude/o1-advantage-attribution-azp7k7` |
| working tree at start | clean |
| HEAD at start | `7063609` — "D91 results…" |
| `origin/main` | `dc1bf18` — **D91 is NOT merged; D86–D90 are** |
| commits `origin/main..HEAD` | 9 (all D91), **docs/ and scripts/ only** |
| `src/` vs `origin/main` | **empty diff — byte-identical** |
| `src/alpha_squad/models/` | `73b408e9…` — unchanged since `0be8263` (D78 shipped Y1) |
| `src/alpha_squad/league/` | `d4cfd00e…` — unchanged since `74a9542` (D84 baseline) |
| offline test suite | **1318 passed, 44 deselected** |
| database | present, 232 MB — **this is D91's container, so its artifacts survive** |

**One inconsistency, reported rather than assumed away:** the brief says "D91 is complete and
pushed." It is pushed *to the branch*; it is **not merged to `main`**. Production is unaffected
(main is a strict ancestor and nothing outside `docs/`+`scripts/` differs), so this is bookkeeping,
not an integrity failure, and D92 proceeds. But D91 is not on `main` and that PR is worth merging.

---

## 2. How the market/ECR board is constructed (Phase 1)

| layer | detail |
|---|---|
| **upstream source** | one file: `https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet` |
| **secondary source** | `files/db_playerids.csv` (same repo) — maps FantasyPros ids to canonical `asq_` ids |
| **update cadence** | **weekly, automated, every Friday** ("Automated FP scrape Fri …") |
| **raw landing** | `data/raw/dynastyprocess/fp_ecr_history/captured_at=YYYY-MM-DD/default_db_fpecr.parquet` |
| **provenance table** | `snapshot_registry` — `snapshot_id`, `url`, `local_path`, **`sha256`**, `rows`, `captured_at` |
| **DB table** | `market_snapshot` (`player_id, scrape_date, ecr_type, position, ecr_rank, ecr_best, ecr_worst, source_snapshot_id, source, page_type`) — 711,444 rows |
| **write semantics** | **destructive**: `market/consensus.py` `DELETE`s then `INSERT`s. `storage/schema.py:490` — "this file is re-scraped in place, so one row per player, replaced" |
| **vintages retained in DB** | **exactly one.** `market_snapshot` holds a single `source_snapshot_id` |
| **board query** | `market/edge.py::_preseason_overall_market` — latest Jul/Aug `scrape_date` per player, scoped to one `(ecr_type, page_type)` (D56), `row_number() … ORDER BY scrape_date DESC` |
| **dedup / ordering** | one row per `player_id` by newest scrape; ranks are the file's `ecr` |
| **series resolution** | `market/series.py` from `is_dynasty × is_superflex` → `ro` / `rsf` / `do` / `dsf` |

**The board the draft actually reads** is not `market_snapshot` alone. `league/replacement.py::
load_season_projections` assembles the projection universe from three tables —
`uncertainty_predictions.point_prediction` (QB/RB/WR/TE, M6), `rookie_predictions` (M7 rookies),
and `projection_snapshot` (K/DST baseline, D57) — and `market_snapshot` supplies only the *rank*
overlay. A vintage definition has to cover both halves.

### Two real defects in the versioning, found here and not fixed (research-only observation)

1. **The raw partition key is day-granular** (`captured_at=2026-09-12`), so **two captures on the
   same day overwrite each other's file**. Within D91 the ingest ran three times on 2026-09-12 and
   all three wrote the same path; they happened to be the same bytes, so nothing was lost, but the
   scheme cannot represent two same-day vintages.
2. **`market_snapshot` keeps one vintage only.** The registry records the provenance of the
   vintage that *survived*; prior vintages leave no row in the table. So the database cannot
   answer "what did the board look like last week" — only the raw files and upstream git can.

Neither is a production-behaviour bug, and neither is touched in this phase.

---

## 3. Board vintage definition (Phase 2)

A vintage is reproducible only if a later run can rebuild the identical board. This phase defines
it as a **triple**, all three verifiable by hash:

| component | identifier | verified value (the vintage D89, D90 and D91 all used) |
|---|---|---|
| **V-a** upstream board blob | `sha256(db_fpecr.parquet)` | `a966176d2966591c4986833aefafb4c74e86f848ca1ba708f43e6a9e79e29525` |
| **V-b** upstream identity map | `sha256(db_playerids.csv)` | `0174ea890e71d33fa0afc1b846ce1c92273542278a287b6bd52c3a4aa5edce73` |
| **V-c** assembled board | `sha256` of `load_season_projections` output, per season, values rounded to 6 dp | 2020 `72080a71…` · 2021 `9e3f625d…` · 2022 `250589ee…` · 2023 `d9bfb8c4…` · 2024 `1bbc61e6…` · 2025 `f25adc8d…` · 2026 `b7a69eb8…` · **combined `85c46d299809a9dfc02d993afea6cd78b2865dbd32d02da623d13240a6e1f1a0`** |

V-a and V-b pin the *inputs*; V-c pins what the draft engine actually sees, which is what a result
depends on. A database timestamp alone would **not** suffice — §2 shows the ingest is destructive
and day-partitioned, so the timestamp does not determine the content.

**Anchoring to upstream git is what makes V-a/V-b recoverable at all.** DynastyProcess's `data`
repo is public, so any past vintage is addressable by commit: the board blob at commit
`9338630` (2026-09-11T04:31:15Z) hashes to exactly `a966176d…`, and so does the file on disk and
the `snapshot_registry` row. The registry's `url` field points at `master`, which is a moving
target; the commit SHA is the durable identifier and is what a future phase should record.

---

## 4. Vintages identified (Phase 3)

`files/db_fpecr.parquet` is committed weekly, so real vintages exist and **all of them are
recoverable**. Four were materialised here from upstream history:

| vintage | commit | committed (UTC) | file sha256 | total rows |
|---|---|---|---|---|
| **V0** | `a0625a4` | 2026-07-03 04:06 | `febfce92…` | 1,775,338 |
| **V1** | `5935744` | 2026-08-28 11:19 | `759c3115…` | 1,824,172 |
| **V2** | `8d326ab` | 2026-09-04 04:23 | `433eaec8…` | 1,830,022 |
| **V3** | `9338630` | **2026-09-11 04:31** | **`a966176d…`** | 1,834,947 |

### V3 is the board D89, D90 *and* D91 all used — and this is provable

| phase | ran at (UTC, from git commit times) | board file it would have fetched |
|---|---|---|
| D88 | 2026-09-11 14:39 – 16:38 | V3 (committed 04:31 that morning) |
| **D89** | **2026-09-11 17:46 – 19:43** | **V3** |
| D90 | 2026-09-11 21:19 – 22:47 | V3 |
| **D91** | **2026-09-12 11:54 – 12:55** | **V3** — no commit touched the file in between |

The previous board commit is **2026-09-04**, and the next is after D91. So D89 and D91 read the
*same bytes*, and `db_playerids.csv` likewise (last changed 2026-09-11 04:55, also before D89).

> **The brief's preferred split — "V1 = the D89/D90 board, V2 = the later board that produced the
> D91 rebuild" — does not exist.** There is one board across all four phases. Nothing was
> fabricated to fill the gap, and no earlier vintage is labelled as D89's.

---

## 5. Reproducibility / determinism check (Phase 4)

### 5.1 The simulation is deterministic

Same board, season, slot, tier, projections; six separate processes at `PYTHONHASHSEED` 0–5
(target 2022, slot 1):

| arm | roster sha | primary | hindsight | season-long | roster pts | bench |
|---|---|---|---|---|---|---|
| **O0 (Y1)** | `c9309376ce8e5e30` — identical at all 6 seeds | 1993.38 | 2158.02 | 2014.48 | 2859.90 | 516.12 (**513.92 at seed 4**) |
| **O1** | `ff8920d49ef42401` — identical at all 4 seeds tested | 2035.08 | 2192.12 | 2014.48 | 2726.70 | 522.82 |

**Drafted rosters and every gate-bearing metric are invariant.** The only quantity that moves is
`bench_contribution`, by 2.20 points at one seed — exactly D89 defect #4's documented signature
(`compute_league_starters` breaks an exact FLEX tie by `set` iteration order). It enters no gate.
**No new nondeterminism was found, and nothing in production was changed.**

### 5.2 Model training is bit-reproducible

A full retrain (`train established-season → uncertainty → rookie → kdst-projections`) on identical
data reproduced the assembled board **exactly**:

| season | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| players | 612 | 636 | 651 | 610 | 602 | 629 | 837 |
| **bit-identical** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| players differing | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

So `random_seed=42` is doing its job despite `thread_count` being unset. **The projection half of
the vintage is reproducible from the data, not just archivable.**

### 5.3 D91's own measurements reproduce exactly

Target 2022 slot 1, re-run today against the recorded D91 artifact: O0 primary `1993.38`, O1
`2035.08`, both roster hashes identical. **D91's numbers are sound; its interpretation was not.**

---

## 6. Board differences between vintages (Phase 7) — the decisive measurement

Content hash over exactly the fields the board reads (`id, scrape_date, pos, ecr, best, worst,
page_type`), restricted to July/August scrapes in the **backtest window 2020–2025**:

| market series | league | Jul/Aug rows 2020–2025 | V0 → V3 (10 weeks apart) |
|---|---|---|---|
| `ro` | `target_league` | 38,200 | **ALL FOUR IDENTICAL** |
| `dsf` | `legacy_2qb_dynasty` | 22,959 | **ALL FOUR IDENTICAL** |
| `do` | `dynasty_1qb` | 40,258 | **ALL FOUR IDENTICAL** |

**Positive control, so "identical" is not just a broken diff.** The same hash over **season 2026**
— the live season — *does* change:

| vintage | 2026 `ro` Jul/Aug rows | md5 |
|---|---|---|
| V0 (2026-07-03) | 1,493 | `f350fafab632b207` |
| V1 (2026-08-28) | 7,818 | `e3a269fa80f560d0` |
| V2, V3 | 7,818 | `e3a269fa80f560d0` |

> ### The file is append-only with respect to history.
> It grows — 1,775,338 → 1,834,947 rows over ten weeks — but **entirely by adding new scrapes for
> the current period.** Rows describing a *past* preseason never change. So for any backtest over
> 2020–2025 there is **no vintage sensitivity to measure**: the board is a constant.

### Every published D89 board figure matches, measured the way D89 measured it

| D89 §2.2 quantity | seasons checked | result |
|---|---|---|
| weekly rows | 2020–2025 | **exact, all six** |
| projected board size | 2020–2025 | **exact, all six** (612/636/651/610/602/629) |
| market-ranked **within the projected board** | 2020–2025 | **exact, all six** (458/490/496/484/515/480) |
| coverage % | 2020–2025 | **exact to the decimal** (74.8/77.0/76.2/79.3/85.5/76.3) |
| board composition by position | 2020–2025 | **exact, all 36 values** |
| consumption demand | 2020–2025 | **exact, all 24 values** |
| best K market rank | 2020–2025 | **exact, all six** (175.4/174.4/178.0/173.9/189.8/187.0) |
| best DST market rank | 2020–2025 | **exact, all six** (146.2/149.8/157.5/161.9/158.5/152.8) |
| uncertainty predictions | 2020–2025 | **exact, all six** (435/468/472/439/439/453) |
| ECR dispersion | 2020–2025 | **exact, all six** (710/1529/799/728/966/826) |
| preseason `page_type` | 2020–2026 | **exact** |

> **RETRACTION.** D91 §9 reported "the market board does not reproduce (533 vs 458 in 2020)" and
> built its headline finding on it. **That comparison was wrong.** D89's column counts
> market-ranked players *inside the projected board*; I counted every `market_rank` entry, a
> superset that includes hundreds of ranked players with no projection. Measured consistently the
> figures agree exactly. D91's §9, §12 and the "between-board natural experiment" (r = +0.601) all
> rest on that error: there was only ever **one board**, so none of them compares two vintages.
> D91's per-draft measurements stand; its board-vintage explanation does not.

---

## 7. Vintage sensitivity, quantified (Phase 7)

The brief asks for board size, common/added/removed players, rank changes and top-20 movement per
vintage pair. Over the **backtest window those are all zero**, so the table is only informative
alongside a case where they are not. V0 (2026-07-03) vs V3 (2026-09-11), ten weeks apart, `ro`:

| | season **2024** (historical) | season **2026** (live) |
|---|---|---|
| players, V0 → V3 | 619 → 619 | 482 → 577 |
| added in V3 | **0** | **95** |
| removed | **0** | 0 |
| common players whose rank moved | **0** | **478 of 482** |
| mean \|rank change\| | — | **14.2** (max 146) |
| top-20 overlap | 20/20 | 19/20 |

**A historical season is frozen; the live season churns.** That is the whole of Phase 7: there is
no vintage sensitivity to attribute for 2020–2025, because there is no vintage difference.

---

## 8. Controlled O1 vs Y1 by vintage (Phases 5, 6) — and what I deliberately did not run

The brief's design is: run the identical experiment on two vintages, changing only the board.
**On this data that comparison is degenerate, and running it would be a tautology.** The chain is:

1. the Jul/Aug rows for 2020–2025 are hash-identical across four vintages, in all three series (§6);
2. so `_preseason_overall_market` — a deterministic `row_number()` over exactly those rows —
   returns the identical board (§6, verified directly at board level, 17/17 season-series);
3. the projection half comes from model training, which is bit-reproducible (§5.2);
4. and the simulation is deterministic (§5.1).

Identical inputs through a deterministic transformation give identical outputs. **A two-vintage
draft comparison would consume roughly eight hours of compute to re-derive that, and I did not run
it.** What I ran instead is the check that actually carries the claim — a direct hash comparison of
the `(player, position, rank)` map the draft consumes, at every historical season in every series.

This is stated plainly rather than presented as a completed comparison: **D92 does not contain a
two-vintage Y1-vs-O1 result, because the two vintages are the same board.**

### The reproducible baseline, measured through the committed runner

What D92 *can* offer is a baseline that is reproducible by construction. On board vintage
`74b2ea7d680ebe4dfdf4f9d98568810f5a43d4bfde7e9e4428fcc46fac33f4de`:

| format | primary Δ (O1 − Y1) | 95% CI | season-long Δ | worst LOSO | largest season's share |
|---|---|---|---|---|---|
| `target_league` | **+28.0** | [−40.7, +96.7] | +31.4 | **+1.9** (drop 2022) | **2022 = 94%** |
| `dynasty_1qb` | **+31.5** | **[+4.6, +58.4]** | +22.3 | +24.9 (drop 2020) | 2020 = 34% |

These are D91's measurements, and the committed runner reproduces them **across every season**.
Six seasons x slot 3 x both arms, re-run through `scripts/d92_paired_grid.py` with
`--expect-vintage`, compared against D91's artifacts on drafted roster plus all four metrics:

| season | O0 primary | O1 primary | match |
|---|---|---|---|
| 2020 | 1552.36 | 1533.16 | **bit-identical** |
| 2021 | 2024.46 | 2025.36 | **bit-identical** |
| 2022 | 1801.78 | 1995.18 | **bit-identical** |
| 2023 | 2086.98 | 1998.82 | **bit-identical** |
| 2024 | 1953.58 | 1916.52 | **bit-identical** |
| 2025 | 1776.12 | 1823.42 | **bit-identical** |

**12/12 cells identical on rosters and on `weekly_no_foresight`, `weekly_hindsight`, `season_long`
and `total_roster_points`.** So the baseline above is not merely recorded, it is regenerable: the
committed runner, the pinned vintage and D91's numbers are one consistent object.

---

## 9. Attribution of the D89 → D91 difference (Phase 9)

The brief says not to assert a cause the comparison does not establish, and to separate measured
causes from hypotheses. Doing that literally:

### Measured, and therefore RULED OUT as causes

| candidate | how it was ruled out |
|---|---|
| board vintage | upstream blob sha256 identical to the commit D89 read; historical rows identical across four vintages (§4, §6) |
| player-universe change | identity-map sha256 identical; board composition matches all 36 published values (§6) |
| projection change | full retrain reproduced the board **bit-identically**, all seven seasons (§5.2) |
| scoring / metric inputs | weekly rows, uncertainty counts, ECR dispersion, consumption demand, best K/DST ranks — all exact (§6) |
| randomness | rosters and every gate-bearing metric invariant across `PYTHONHASHSEED` 0–5 (§5.1) |
| database contamination | one `source_snapshot_id` in `market_snapshot`, matching the registry (§2) |
| D91 measurement error | D91's recorded values re-run exactly (§5.3) |

### Measured, and therefore ESTABLISHED

**D89's and D90's published outputs do not reproduce**, in either format, from the committed code
and provably identical data:

| published Y1 figure | D89 | this container |
|---|---|---|
| target, first RB round | 4.15 | **5.27** |
| target, first WR round | 1.58 | **1.27** |
| target, first TE round | 6.70 | **5.87** |
| target, kickers drafted | 3.45 | **2.98** |
| legacy, first QB round | 1.88 | **2.20** |
| legacy, first TE round | 5.90 | **6.54** |

Neither available opponent strategy closes the gap (`market_consensus_roster_aware` and
`market_consensus` give *identical* early rounds, both differing from D89), and my aggregation
matches the harness's own `first_round_by_position` semantics.

> **Identical inputs + a deterministic transformation + different outputs ⇒ the transformation
> differed.** D88, D89 and D90 each ran their grid from a script that was **never committed**.
> That is the established cause of the irreproducibility, and it is a worse problem than a mutable
> board: a board can be pinned by hash, but uncommitted code leaves nothing to pin.

### Hypothesis, explicitly NOT established

*Which* runner difference it was — a different candidate pool, a different metric input, a
different season/slot handling — **cannot be determined**, because the code no longer exists. I can
say the inputs were identical and the outputs were not; I cannot say which line differed. **Any
specific story about it would be invention**, so none is offered.

**Consequence, stated so it is not discovered later:** D86–D90's published draft-layer numbers —
including the **+49.0** that six phases have cited — are **not reproducible and should not be
quoted as measurements of this system** going forward. They remain a record of what those phases
observed.

---

## 10. 2026 reality check (Phase 10)

`target_league`, 2026 board on the pinned vintage, slot 1 (whose first three picks *are* overall
#1/#20/#21 in a 10-team snake). Re-run after the full retrain and **identical to D91's**:

| pick | Y1 | O1 | |
|---|---|---|---|
| **#1** | Jaxon Smith-Njigba (WR) 508.1, msv 265.3, vorp 107.7 | **same player**, 471.4 | identical |
| **#20** | Josh Allen (QB) 316.4, msv 337.4, vorp 73.3 | **same player**, 281.3 | identical |
| **#21** | **Jeremiyah Love (RB)** 306.6, msv 243.9 | **Trey McBride (TE)** 281.9, msv 169.6 | **differs** |

**The first divergence is a 0.2-point tie under Y1** — Love 306.6 against McBride **306.4** — which
O1 separates by 12.6. Final rosters share 11/16, and the composition difference is exactly **two
kickers becoming two tight ends** (Y1: 4 K / 1 TE; O1: 2 K / 3 TE). O1 ends up with Love anyway at
a later pick; Y1 never gets McBride.

`dynasty_1qb`: #1, #20 and #21 all **identical** (Pickens at #21 in both); first divergence round 9
(Kittle TE → Jacobs RB); one kicker becomes one running back; rosters share 13/16.

> **Nothing at the top of a 2026 draft changes**, in either format — now the fifth consecutive
> phase to find that, and the first to find it on a hash-pinned board.

---

## 11. Computational cost (Phase 11) — measured, not estimated

Recorded by the committed runner on this container (4 cores):

| arm | s/pick | s/draft (16 picks) | vs Y1 |
|---|---|---|---|
| **O0 (Y1)** | **0.032** | 0.5 | 1.0× |
| **O1, full board** | **6.249** | 100 | **≈195×** |
| O1 with D87's research-only `shortlist_k=10` | not run | — | D87 measured it and **rejected it**: ranked by Y1 it re-imports Y1's K/DST bias and flips sign across formats |

No new shortlist was created. A single live recommendation costs ≈ **6 s**, which is immaterial
during a real draft; the 195× multiplier matters only for batch experiments, where it is the
difference between a one-hour and an eight-hour grid.

---

## 12. Gate results (Phase 12)

No gate was added, relaxed, re-thresholded, or invented around an observed result. **G7 is not
relaxed.** On the pinned vintage, with the caveat that these are one reproducible measurement
rather than a replication:

| gate | threshold | `target_league` | `dynasty_1qb` |
|---|---|---|---|
| G3 | primary worse in ≤ 1 season | **FAIL** (3/6) | **PASS** (0/6) |
| G6 | LOSO margin stays positive | PASS (+1.9 … +37.7) — **but see below** | **PASS** (+24.9 … +37.4) |
| G8 | clustered 95% CI excludes zero | **FAIL** [−40.7, +96.7] | **PASS** [+4.6, +58.4] |
| G9 | primary margin ≥ 25.0 | **PASS** (+28.0) | **PASS** (+31.5) |
| G10 | season-long margin ≥ −25.0 | **PASS** (+31.4) | **PASS** (+22.3) |
| **G7** | **cross-format sign** | **PASS on sign** (+28.0 / +31.5, both positive in the two formats where the mechanism can operate) — legacy remains structurally untestable per D90 | |

**G6 passes in the target format only in the letter.** Dropping 2022 leaves **+1.9**, because 2022
is 94% of the margin. A gate that reports PASS on a result carried by one season is not measuring
what it was written to measure — recorded as an observation about G6, **not** as a proposal to
change it.

---

## 13. Ship / do not ship

> ### **DO NOT SHIP. Y1 remains production.**

`src/` contains **two additive research files** (`evaluation/board_vintage.py`, its test) and one
script; `models/` (`73b408e9…`) and `league/` (`d4cfd00e…`) are unchanged from the Y1 baseline; no
pre-existing file was modified and **no production path imports either new file**. 1338 tests pass
(1318 before, +20 new); ruff clean.

D92 was never a shipping phase. The objective did not change and Option G was not implemented.

---

## 14. Most important next research question

> **Re-measure O1 once, through the committed runner, on the pinned vintage — and treat that as
> the first reproducible draft-layer number this project has.**

D86–D90's numbers are not reproducible (§9), so the research line currently has **one** usable
measurement per format, both from D91 and both now re-verifiable. A replication is no longer
"more of the same": it is the first time two comparable numbers would exist. Concretely:

1. Run `scripts/d92_paired_grid.py` for both 1-QB formats with `--expect-vintage`, full grid, and
   commit the summary (not the artifact — `reports/` is gitignored).
2. Then, and only then, revisit D91's Option G (a non-degenerate, startable-slot-aware marginal
   value for bench candidates), pre-registered against that baseline.

The second-most valuable item is cheap and closes a real gap: **make the raw snapshot path
vintage-addressable** — partition by the upstream commit or the content hash rather than by day,
so two same-day captures cannot overwrite each other and `market_snapshot` can hold more than one
vintage. §2 records both weaknesses; neither is fixed here.

---

## 15. Plain-English trust assessment

**The board was never the problem, and I was wrong in D91 to say it was.** DynastyProcess publishes
its ranking history weekly and only ever *adds* to it — the rows describing the 2022 preseason are
the same today as they were ten weeks ago, byte for byte, and I verified that against four separate
published versions with a control to prove the check works. The number I used in D91 to claim
otherwise was a mistake: I counted a different set of players than D89 did. Corrected, every one of
roughly ninety published figures lines up exactly.

**What is genuinely broken is bookkeeping, not data.** The programs that produced D88, D89 and
D90's headline numbers were never saved. Everything they read still exists and still reproduces;
the code that turned it into results does not. So those numbers — including the **+49** that six
phases have quoted — cannot be regenerated, and the honest thing is to stop citing them as
measurements. D92's fix is unglamorous: the runner is now committed, it stamps every result with a
hash of the board it read, and it can refuse to run against the wrong board.

**Nothing about the advice changes.** On a hash-pinned 2026 board, Y1 and O1 make the same pick at
#1 and #20 in both formats. The one difference at #21 is a **0.2-point tie** under Y1 that O1 breaks
the other way, and the endgame difference is still the same one every phase has found: Y1 buys four
kickers, O1 buys two and spends the rest on tight ends. **Take the kicker you need, then stop** —
and you still do not need a code change to do that.

**How much to trust the instrument now:** the data, the projections and the simulation are all
pinned and verified reproducible, which is more than was true yesterday. But **no result published
before D92 can be compared to one published after it**, and the one reproducible target-format
number we have (+28.0) is 94% a single season. The instrument is trustworthy going *forward*, not
backward.

---

## 16. The two questions, answered directly

> **"Is O1 a real improvement whose measured size is noisy, or is the apparent improvement
> materially dependent on the historical ECR board?"**

**Neither, and the second is now definitively excluded.** The historical ECR board is immutable, so
no draft-layer result over 2020–2025 can depend on its vintage — proven by hash across four
published versions, three market series and seventeen season-boards, with a positive control.

On "real improvement whose size is noisy": the honest answer is that **we do not yet have enough
reproducible measurements to call the size noisy or stable.** O1 is positive in both formats where
its mechanism can operate on the one pinned vintage (+28.0 target, +31.5 dynasty), and D91 showed
its behavioural signature is robust and its mechanism is startable-slot count rather than
availability. But the target-format figure is 94% one season, and the +49.0 it is usually compared
against is not reproducible and should be retired. **One measurement is not a measurement of
noise.**

> **"Do we now have a trustworthy experimental instrument for comparing future decision
> objectives?"**

**Substantially yes, and for the first time — but only prospectively.** Pinned and verified: the
board (hash-addressable to an upstream commit), the projections (bit-reproducible retrain), the
simulation (deterministic across hash seeds), and now the runner (committed, provenance-stamping,
vintage-asserting). The gap that remains is historical: **every phase before D92 is
unreproducible**, so the instrument cannot be used to re-examine D86–D90's conclusions — only to
measure honestly from here.
