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
