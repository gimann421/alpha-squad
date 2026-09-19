# W1 — Weekly Rankings: Foundation & Baseline Audit

> ## ⚠ CORRECTED BY W1.1 — read this first
>
> **Two of this document's three headline "the historical record cannot give us this" findings
> were wrong**, and they were wrong in the same way: W1 audited only the **DynastyProcess
> mirror** and reported that source's limits as limits of the historical record. FantasyPros'
> own API — already adapted in `sources/fantasypros.py`, with a configured key, recorded live
> in D36/D37 — was never queried for weekly rankings.
>
> | W1 said | actually |
> |---|---|
> | §3.3 "No 1-QB weekly overall/FLEX board exists" | **RETRACTED.** FantasyPros publishes a real weekly RB/WR/TE FLEX board (`position=FLX`) for every week of 2021–2025. The *mirror* lacks it. |
> | §3.2 "No Half-PPR ECR benchmark exists" | **DOWNGRADED.** FantasyPros serves `scoring=HALF` historically for every board. Our API tier returns only the top 10 rows, so a *full-depth* half-PPR benchmark is a **licensing** limit, not a data-availability one. |
> | §3.1 "The Tue–Sun daily cadence is not historically reconstructable" | **STANDS**, and is now doubly supported: the API's own vintage is a single Sunday-at-kickoff freeze, so it supplies no intermediate vintages either. |
>
> The FLEX reconstruction W1 built as a workaround (§4.5) has since been **validated against the
> real board**: median top-10 overlap **0.80** over 19 weeks, against a 0.70 threshold fixed
> before measuring. It is sound, and W2 ran on it.
>
> **Full correction and the corrected data audit: `docs/weekly/W11_FANTASYPROS_FLEX_AUDIT.md`.
> Benchmark results: `docs/weekly/W2_ECR_BENCHMARK_RESULTS.md`.**
>
> Everything else in this document — the Friday cutoff, the already-played exclusion, the
> ground-truth verification, the identity and coverage measurements, the repository and context
> hierarchy — was re-checked in W1.1/W2 and **stands unchanged**.

**Start here for the weekly-ranking program.** This is phase W1 of a research program that is
separate from the draft program (D86–D108, closed out in `docs/D108_PROGRAM_CLOSEOUT.md`). It
reuses that program's data, identity and provenance machinery, and reuses its *methodology* only
where the methodology actually transfers.

*Audit, measurement and pre-registration only. No production change: no `models/`, no `league/`,
no `api/`, no CLI, no config, no dataset update, nothing fitted, nothing merged.*

---

## 0. The question this phase answers

> **Do we now have a valid, leakage-free, reproducible experimental foundation for determining
> whether Alpha can produce weekly rankings that meaningfully outperform ECR?**

**Answer: YES for a Friday-cutoff, Full-PPR, FLEX-and-positional study over 79 player-weeks-rich
NFL weeks in 2021–2025 — and NO for three things the brief asked for.** The three are not
fixable by care in the harness; they are absent from the historical record. They are stated in
§3 and carried into the W2 pre-registration as scope limits rather than quietly dropped.

The north star is unchanged and is *not* "beat ECR":

> **Help the user identify the players they should value most for the upcoming fantasy week.**

ECR is three separate things in this program, and the report keeps them separate throughout: an
independent benchmark, a candidate Alpha input, and a practical product gate.

---

## 1. WHAT WE KNOW vs WHAT WE DO NOT YET KNOW

This section is the summary. Everything in it is sourced below. Nothing here is a hypothesis.

### WHAT WE KNOW (measured this phase, reproducible)

| # | Fact | Where |
|---|---|---|
| K1 | Weekly ECR exists in the mirror this project already downloads: **7 series, 96 scrape dates, 2020-10-16 → 2026-09-18** | §4.1 |
| K2 | There is **one ECR vintage per week and it is a Friday** (82 Friday / 10 Thursday / 2 Saturday / 1 Tue / 1 Wed) | §4.2 |
| K3 | **90 REG weeks** have a canonical weekly board across 2020–2025; **79** of them in 2021–2025 | §4.3 |
| K4 | No half-PPR or standard-scoring page exists **in the mirror** — but FantasyPros serves both (**W1.1 §8**) | §4.4, W1.1 |
| K5 | ~~No 1-QB weekly overall/FLEX board exists~~ **RETRACTED by W1.1** — true of the mirror only; FantasyPros publishes one | §4.5, W1.1 |
| K6 | The superflex board's within-position order matches the dedicated positional boards almost exactly (**RB ρ̃=0.9965, WR 0.9997, TE 0.9992**, 96 weeks) | §4.5 |
| K7 | **78 of 90 canonical boards carry already-played (Thursday-night) players — 2,522 / 42,260 rows (6.0%)** | §4.6 |
| K8 | Board → `gsis_id` identity resolves at **99.3–99.8% overall and 99.9–100% in the top 24** | §4.7 |
| K9 | nflverse `fantasy_points_ppr` **exactly** reproduces an explicit PPR formula: max abs diff **0.0 over 5,864 REG QB/RB/WR/TE player-weeks (2024)**, zero mismatches | §5.1 |
| K10 | Half-PPR is an **exact identity** over stored columns, agreeing to 0.0 by two independent routes | §5.1 |
| K11 | **All six positions** have weekly ground truth in one table: K and DST points are *computed* by `features/kicking_defense.py` and written into `player_week_stats` | §5.2 |
| K12 | The nflverse injury file is **one final row per player-week** (6,213 keys / 6,215 rows, 2024) with a real `date_modified`; **4,818 of 2024's rows were last modified on a Friday** | §6.2 |
| K13 | Injuries, depth charts and snaps run **2009→2026** — far deeper than ECR. **ECR is the binding constraint on the study period, not the NFL data** | §6 |
| K14 | A weekly model **already exists** (`models/established/`) — 11 features, QB/RB/WR/TE only, full-PPR target, **no opponent, no Vegas, no weather, no injury, no ECR** — and **has never been evaluated as a weekly ranking** | §7 |
| K15 | Weekly ECR is **not ingested**: `DEFAULT_ECR_TYPES = ("ro","do","rsf","dsf")` covers only the four draft series | §4.1 |
| K16 | Baseline parity re-established: **1427 tests pass, 44 deselected**; `make lint` clean — matching the D108 closeout record exactly | §11 |

### WHAT WE DO NOT YET KNOW

| # | Open question | Why it is open |
|---|---|---|
| U1 | Whether Alpha can beat ECR on weekly rank quality at any depth | No comparison has been run. W1 deliberately ran none. |
| U2 | Whether ECR adds information *to* Alpha, or Alpha adds information *beyond* ECR | Requires the three-system design in §14 |
| U3 | Whether the superflex board's **cross-position** RB/WR/TE calibration equals a 1-QB board's | No 1-QB weekly board exists to check against. K6 shows *within*-position agreement only. |
| U4 | The noise floor / minimum detectable improvement for the primary comparison | Estimable from the data in §12 but **not estimated this phase** — it must be computed on the real ECR-alone baseline, which is W2's first task |
| U5 | Whether a Tuesday/Wednesday Alpha ranking is *useful*, even though it cannot be *benchmarked* | Separable: Alpha's own inputs partly support earlier cutoffs (§6.3) even where ECR does not |
| U6 | How much of ECR's weekly edge (if any) is expert information vs. just being published later in the week | Confounded by K2; §14 proposes the only clean handle |
| U7 | Whether availability prediction is worth modelling separately at all | §8 defines the split; nothing measures its value yet |

### Explicitly NOT established (guard against later restatement)

- **Nothing in this phase measures ranking quality.** No ρ, no NDCG, no hit rate, no MAE against
  realized weekly points has been computed for any system. K6's correlations are between **two
  ECR boards**, not between a ranking and an outcome.
- **The existing weekly model is not a baseline yet.** K14 says it exists; it does not say it
  works. Its season-aggregate evaluation says nothing about weekly ranking quality.
- **Friday is a data constraint, not a product recommendation.** §6.3.

---

## 2. Deliverable index

The brief asked for 20 items. Map:

| # | Item | Section |
|---|---|---|
| 1 | Weekly infrastructure that exists | §7 |
| 2 | Historical data that exists | §4, §5, §6 |
| 3 | Historical data that is missing | §3, §6.4 |
| 4 | What is reconstructable without leakage | §6.3 |
| 5 | Are Tue–Sun snapshots feasible | §3.1, §6.2 |
| 6 | Half-PPR / Full-PPR support | §5.1, §3.2 |
| 7 | Position support | §5.2 |
| 8 | How FLEX should be constructed | §4.5 |
| 9 | How availability should be represented | §8 |
| 10 | Current Alpha architecture | §7 |
| 11 | Proposed experimental architecture | §13, §14 |
| 12 | Proposed repository/file hierarchy | §9 |
| 13 | Proposed context/knowledge hierarchy | §10 |
| 14 | Authoritative sources of truth | §10.2 |
| 15 | Evaluation framework | §13 |
| 16 | ECR benchmark | §14.1 |
| 17 | Alpha-without-ECR | §14.2 |
| 18 | Alpha-with-ECR | §14.3 |
| 19 | Limitations | §3, §15 |
| 20 | Proposed W2 experiment | §16 |

---

## 3. The three things the brief asked for that the historical record cannot give

Stated first, because they change the shape of the whole program and every later section
assumes them.

### 3.1 The Tuesday–Sunday daily snapshot cadence is NOT historically reconstructable

Two independent constraints agree on this.

**The benchmark has one vintage per week.** Across all 96 weekly boards the mirror holds, the
scrape-date weekday mix is **82 Friday, 10 Thursday (every one in 2020), 2 Saturday, 1 Tuesday,
1 Wednesday**. There is no Tuesday board and no Wednesday board in any ordinary week. The
brief's own rule forbids substituting a later ECR to fill a missing earlier one, so a Tuesday
ECR benchmark does not exist and cannot be manufactured.

**The injury report cannot be rewound past its last edit.** This is the subtler and more
dangerous one. nflverse's `injuries` file holds **one row per player-week** — 6,213 distinct
`(season, week, gsis_id)` keys in 6,215 rows for 2024 — and `date_modified` records when that
row was *last* touched. **4,818 of 2024's 6,215 rows were last modified on a Friday.** Filtering
`date_modified <= Wednesday` therefore does not reconstruct the Wednesday injury report; it
*deletes* most of the report, because a row updated again on Friday retains only its Friday
state. A "Wednesday snapshot" built that way would be systematically **healthier** than the real
Wednesday. That is a missingness bias, not a leak — and it is worse than a leak here, because it
would silently flatter any system that uses injury data while looking perfectly leakage-clean.

**Consequence.** W1 adopts a **single snapshot: Friday, after the Thursday-night game, before
the Sunday slate.** The daily cadence remains a legitimate *forward-looking product* capability —
from the moment the product starts capturing its own daily snapshots, it accumulates the vintages
history does not contain. It is not a *historically testable* one, and the W2 pre-registration
says so rather than approximating it.

### 3.2 A Half-PPR ECR benchmark does not exist historically — **CORRECTED: it exists; our tier cannot fetch it at depth (W1.1 §8)**

Pattern search over every distinct `fp_page` value in the mirror returns **zero** pages matching
`half`, `standard` or `non-ppr`. The weekly RB/WR/TE boards are `ppr-rb.php`, `ppr-wr.php`,
`ppr-te.php` — full PPR.

**This does not block Half-PPR as a product format.** Alpha can rank in Half-PPR, and Half-PPR
ground truth is exact (§5.1). What is absent is a Half-PPR *benchmark* to compare against. So:

- **Full-PPR** carries the ECR comparison — the full three-system design.
- **Half-PPR** carries an Alpha-internal evaluation (Alpha-with-ECR vs Alpha-without-ECR vs the
  Full-PPR ECR board re-scored against Half-PPR outcomes, clearly labelled as a *format-mismatched*
  reference, never as "the Half-PPR ECR benchmark").

Most of the practical difference is small — reception value is the only rule that changes — but
"small" is a hypothesis, and mislabelling a full-PPR board as a half-PPR one is exactly the D56
error. The two must not be blurred.

### 3.3 There is no 1-QB weekly overall/FLEX board — **RETRACTED (W1.1 §2): FantasyPros has one; the mirror does not**

This is D56 repeating itself in the weekly program, and it is the finding most likely to be
forgotten later. `ppr-flex.php` appears in the mirror only between 2019-12-27 and 2020-10-12
(7 dates, pre-rename labels) and never again. From 2020-10-16 onward the only weekly
cross-position board is **`/nfl/rankings/ppr-superflex.php`**.

The reconstruction and its measured support are in §4.5. The limit of that support is U3.

---

## 4. The ECR benchmark: what exists, exactly

Source: DynastyProcess `db_fpecr.parquet`, the same mirror `market/consensus.py` already reads.
Measured vintage for every number in this section:
`sha256 e270d790165a6c304e5854145332fe9da3caacab3a61e1efea280b57cc5db9a5`.
Reproduce with `scripts/research/w1_weekly_foundation_audit.py`.

### 4.1 Seven weekly series exist — and none is ingested

| series | FantasyPros page | rows | dates | span |
|---|---|---:|---:|---|
| `wp/weekly-qb` | `/nfl/rankings/qb.php` | 4,474 | 96 | 2020-10-16 → 2026-09-18 |
| `wp/weekly-rb` | `/nfl/rankings/ppr-rb.php` | 11,174 | 96 | " |
| `wp/weekly-wr` | `/nfl/rankings/ppr-wr.php` | 16,180 | 96 | " |
| `wp/weekly-te` | `/nfl/rankings/ppr-te.php` | 9,577 | 96 | " |
| `wp/weekly-k` | `/nfl/rankings/k.php` | 3,039 | 96 | " |
| `wp/weekly-dst` | `/nfl/rankings/dst.php` | 2,880 | 96 | " |
| `wsf/weekly-op` | `/nfl/rankings/ppr-superflex.php` | 45,147 | 96 | " |

**All six product positions have a dedicated weekly ECR board.** That is better coverage than
the draft program had, where K and DST needed a constructed board (D57).

**None of these is in the database.** `market/consensus.py::DEFAULT_ECR_TYPES` is
`("ro","do","rsf","dsf")` — the four draft series. Weekly ECR is present in the snapshot this
project already downloads and absent from `market_snapshot`. Wiring it in is a one-line widening
of an existing filter; it is a **production change**, so W1 does not make it. The audit reads the
recorded snapshot directly via `require_snapshot`, the same provenance-preserving reader the
market build uses — no second data path.

`ecr_type` alone is still not a rank space: `wp` labels six independently-ranked pages. The
`(ecr_type, page_type)` pair rule from D56 applies unchanged and is pinned by
`tests/unit/test_weekly_series.py`.

### 4.2 The cadence: one Friday vintage per week

| weekday | distinct scrape dates |
|---|---:|
| Friday | 82 |
| Thursday | 10 (all 2020) |
| Saturday | 2 |
| Wednesday | 1 |
| Tuesday | 1 |

The modal snapshot leads the week's first Sunday game by **2 days**: 82 of 96 boards.

### 4.3 Week coverage: 90 REG weeks, and a specific pattern of gaps

Assignment rule: a board belongs to the `(season, week)` whose **first Sunday game** it
precedes by ≤7 days. Anchoring on the week's *first* game would be off by one, because that game
is usually Thursday and a Friday board sits after it.

| season | weeks covered | which |
|---|---:|---|
| 2020 | 11 | 6–16 |
| 2021 | 17 | 1–17 |
| 2022 | 16 | 2–17 |
| 2023 | 16 | 2–17 |
| 2024 | 14 | 4–17 |
| 2025 | 16 | 2–17 |
| **total** | **90** | |

Three structural gaps, all of which the pre-registration must handle explicitly rather than
average over:

1. **Week 1 is covered only in 2021.** Week 1 is also the week with the least in-season signal,
   so its absence is a real limitation on any "how does Alpha do with no current-season data"
   question.
2. **Week 18 is never covered, in any season.** It is also not a fantasy week in standard
   leagues, so this costs nothing.
3. **2024 starts at week 4** and 2022/2023/2025 start at week 2 — the mirror's own capture
   history, not an NFL fact.

Four weeks carry two vintages (2020 w6, 2021 w5, 2021 w14, 2024 w13). `canonical_snapshots`
keeps the **latest** one, which is the Friday board in every case; using both would double-count
those weeks and mix a Tuesday information set into a Friday series.

### 4.4 Scoring formats present: PPR only

Distinct `fp_page` values matching `half` = **0**, `standard` = **0**, `non-ppr` = **0**.
See §3.2.

### 4.5 Constructing the FLEX benchmark — **validated in W2: median top-10 overlap 0.80 vs the real board**

There is no 1-QB weekly cross-position board (§3.3). The **only** available route is:

> take `wsf/weekly-op`, drop QB rows, drop already-played teams, re-rank the survivors densely.

**Measured support.** Per-board Spearman between the ordering the superflex board induces within
a position and the dedicated positional board for that position, over all 96 boards:

| position | weeks | median n | median ρ | p10 ρ | min ρ |
|---|---:|---:|---:|---:|---:|
| RB | 96 | 115 | **0.9965** | 0.9916 | 0.9866 |
| WR | 96 | 165 | **0.9997** | 0.9988 | 0.9862 |
| TE | 96 | 98 | **0.9992** | 0.9962 | 0.9817 |
| QB | 96 | 41 | 0.9962 | 0.9778 | 0.7042 |

The RB/WR/TE agreement is near-perfect: the superflex board and the positional boards are two
views of one product, so dropping QBs leaves an RB/WR/TE ordering consistent with FantasyPros'
own positional rankings. (QB's much lower floor — min 0.7042 — is the expected signature of a
superflex board pricing QBs differently, and is precisely why QBs are dropped rather than kept.)

**What this does NOT establish (U3).** It shows *within*-position consistency. It does **not**
show that the superflex board's *cross-position* RB-vs-WR-vs-TE calibration equals what a 1-QB
flex board would publish. No such board exists to check against. The reconstruction is therefore
an **assumption with measured internal support**, recorded as an assumption. A weekly ranking is
much closer to a pure expected-points question than a draft board is — superflex changes QB
scarcity, not an RB's expected points — which is the mechanism that makes the assumption
plausible, but plausible is not measured.

`flex_reference_series()` is deliberately not named `weekly_flex_series()`, and
`WEEKLY_OVERALL_SUPERFLEX.label` contains the word SUPERFLEX, so a future reader cannot restate
a superflex measurement as a 1-QB one without stepping over both.

The superflex board carries **no K and no DST**, so an "overall ranking across all six
positions" has no ECR analogue at all. FLEX (RB/WR/TE) does, and FLEX is what the product asked
for.

### 4.6 Already-played contamination — the central leakage hazard

A Friday vintage sits **after** the week's Thursday game. The boards keep those players on them:

| | |
|---|---:|
| canonical boards examined | 90 |
| boards carrying ≥1 already-played player | **78** |
| board rows | 42,260 |
| already-played rows | **2,522 (6.0%)** |

Their outcome is already determined at the cutoff. Leaving them in hands every system a free,
resolved row and corrupts every depth cutoff (a "top 10" containing two settled players is not a
top 10). They are removed **from the universe**, before ranking, by a rule that belongs to the
cutoff and not to any system — so ECR-alone, Alpha-without-ECR and Alpha-with-ECR are scored on
byte-identical player sets. Pinned by `tests/leakage/test_weekly_snapshot_cutoff.py`.

### 4.7 Identity: not a blocker

FantasyPros id → `gsis_id` through the DynastyProcess crosswalk:

| series | rows | matched | top-24 matched |
|---|---:|---:|---:|
| `wsf/weekly-op` | 45,147 | 99.28% | **99.91%** |
| `wp/weekly-qb` | 4,474 | 99.78% | **100.00%** |
| `wp/weekly-rb` | 11,174 | 99.69% | **100.00%** |
| `wp/weekly-wr` | 16,180 | 99.68% | **100.00%** |
| `wp/weekly-te` | 9,577 | 99.37% | **100.00%** |

Losses are concentrated far down the board, where they matter least. DST is team-coded (32 team
codes; only `JAC` and `LAR` differ from nflverse) and joins through the alias map
`features/kicking_defense.py::FANTASYPROS_TEAM_ALIASES` already contains — `{JAC→JAX, LAR→LA,
OAK→LV}` covers it exactly.

---

## 5. Ground truth

### 5.1 Scoring, verified rather than assumed

`player_week_stats` stores `fantasy_points` (standard), `fantasy_points_ppr` (1.0 PPR) and
`receptions`. Reception value is the only rule that differs between the formats in scope, so:

> **points(r) = fantasy_points_ppr − (1 − r) × receptions**

**Verification (2024 REG, QB/RB/WR/TE, n = 5,864):** an explicit PPR formula written out from
the scoring rules (0.04/pass yd, 4/pass TD, −2/INT, 0.1/rush+rec yd, 6/rush+rec TD, 1/reception,
−2/fumble lost, 2/2PC, 6/ST TD) reproduces the stored `fantasy_points_ppr` with **maximum
absolute difference 0.0 and zero mismatches**. The two independent routes to half-PPR
(`ppr − 0.5·rec` and `standard + 0.5·rec`) agree to **0.0** on the same rows.

So this is an *identity over stored columns*, not a re-implementation that can drift. That is
what earns the right to use the stored column rather than re-deriving from components — and it
keeps the weekly program scoring the same events the same way the draft program does.

**Spot checks** (real 2024 games, hand-computed expectations, pinned in
`tests/unit/test_weekly_scoring.py`):

| player-week | line | Full PPR | Half PPR |
|---|---|---:|---:|
| Ja'Marr Chase, wk5 vs BAL | 10 rec, 193 yd, 2 TD | 41.3 | 36.3 |
| Brock Bowers, wk5 vs DEN | 8 rec, 97 yd, 1 TD | 23.7 | 19.7 |
| Saquon Barkley, wk1 vs GB | 109 rush, 2 rush TD, 2/23/1 rec | 33.2 | 32.2 |
| Lamar Jackson, wk5 vs CIN | 348 pass, 4 TD, 55 rush | 33.42 | 33.42 |

### 5.2 All six positions are covered — two of them by computation

| position | weekly ground truth | source |
|---|---|---|
| QB / RB / WR / TE | `fantasy_points_ppr`, directly | nflverse `stats_player_week` |
| **K** | **computed**, written into `player_week_stats` | `features/kicking_defense.py` from `fg_made_0_19 … fg_made_60_`, `pat_made`, misses |
| **DST** | **computed**, written into `player_week_stats` | `def_*` from `stats_team_week` + points allowed from `team_week_points` |

This matters and is easy to get wrong: nflverse prices only passing/rushing/receiving, so **every
kicker's `fantasy_points_ppr` is 0.0** (verified: 569 K rows in 2024, sum exactly 0.0) and **team
defenses do not exist as an entity at all**. D57 built both; D78 fixed the build-order bug that
silently produced zero DST rows for every season. K and DST carry no receptions, so all three
formats coincide for them and the single formula above needs no positional special case.

The practical consequence for W2: `make features` must have run, and the D78 ordering must hold,
or K/DST silently evaluate as empty. `build_kicking_and_defense` now raises rather than writing
zero, which is the guard.

---

## 6. Data/source audit

Classified per the brief: **(A)** usable historically, **(B)** exists but not
point-in-time reconstructable, **(C)** needs new acquisition, **(D)** should not be used.

### 6.1 Class A — available historically and usable at a Friday cutoff

| source | coverage | grain | PIT reconstructable? | notes |
|---|---|---|---|---|
| nflverse `stats_player_week` | 1999→2026 | player-week, post-game | Yes — by week index | The outcome and the lag-feature raw material |
| nflverse `stats_team_week` | " | team-week, post-game | Yes | Team environment; DST components |
| nflverse `snap_counts` | 2012→2026 | player-game, post-game | Yes | Prior weeks only |
| nflverse `injuries` | **2009→2026** | one final row / player-week, `date_modified` | **Friday only** — see §6.2 | The only timestamped source |
| `games` (from pbp) | 1999→2026 | game, **date only** | Yes | No kickoff time — see §6.4 |
| DynastyProcess `db_fpecr` weekly series | 2020-10→2026-09 | board, `scrape_date` | Yes, at its own vintages | **The binding constraint: 90 weeks** |
| DynastyProcess `db_playerids` | current | crosswalk | Static | 99.3–99.8% join |
| `player_week_features` panel | derived | player-week | Yes, by construction | Window frames exclude current/future rows |

### 6.2 Class B — exists, but cannot be reconstructed at an arbitrary cutoff

**nflverse `injuries`** is the important one, and it is *half* class A. Structure: one row per
player-week, `date_modified` = last edit. 2024 weekday mix of `date_modified`: Friday 4,818,
Saturday 509, Wednesday 461, Thursday 351, Tuesday 51, Sunday 22, Monday 3. Only **1 row in the
whole 2024 season was modified after its team's kickoff**, and 13 on gameday — so the file is
overwhelmingly a pre-game final report, which is exactly what a Friday cutoff needs.

- **At a Friday cutoff:** usable, with `date_modified <= cutoff` applied. Sound.
- **At a Tuesday/Wednesday cutoff:** **not reconstructable.** §3.1.

**nflverse `depth_charts`** carries `(season, week)` and **no timestamp at all**. The assumption
that a week-*w* row reflects the state *entering* week *w* is exactly that — an assumption. It is
the same one `evidence/events.py` already makes. Usable at a Friday cutoff under that stated
assumption; flagged, not silently trusted.

**`weekly_rosters`** — same shape, same caveat.

### 6.3 What IS reconstructable without leakage, at Friday

Everything in §6.1 restricted to: player-weeks **strictly prior** to week *w*, plus the week-*w*
injury report filtered to `date_modified <= Friday cutoff`, plus the week-*w* schedule/opponent
(known months ahead), minus every player whose week-*w* game already kicked off.

The existing `player_week_features` panel is already Friday-safe for non-TNF players by
construction: its window frames are `ROWS BETWEEN n PRECEDING AND 1 PRECEDING` ordered by
`game_date`, per player. A player's week-*w* row sees only his own weeks < *w*, every one of
which completed before Friday of week *w*. The one case that breaks is exactly the TNF case that
§4.6 removes from the universe anyway.

### 6.4 Class C — would require new acquisition (none is a W2 blocker)

| wanted | status |
|---|---|
| **Vegas lines point-in-time** | `nfldata/games.csv` carries `spread_line`, `total_line`, moneylines — but as a **single continuously-rebuilt file with one value per game and no timestamp**. That value is effectively the closing line. Using it at a Friday cutoff is **class D**, not C, unless a timestamped odds history is acquired. |
| **Weather forecast** | Same file carries `temp` and `wind` — these are **actual game conditions**, not a Friday forecast. Class D. A forecast archive would be new acquisition. |
| **Practice participation by day (Wed/Thu/Fri)** | Not in nflverse. Would make earlier cutoffs reconstructable. |
| **News / beat reporting** | D5/D22 already recorded that this environment has no news API. Unchanged. |
| **Half-PPR ECR** | Not mirrored; would need direct FantasyPros weekly capture going forward. |

### 6.5 Class D — must NOT be used

- **`games.csv` `spread_line` / `total_line` / moneylines** at any historical cutoff — no
  timestamp, effectively closing values. Reconstructing "the Friday line" is impossible from it.
- **`games.csv` `temp` / `wind`** — realized game-time conditions. Using them is direct
  look-ahead dressed as a weather feature.
- **`snap_counts` / `stats_*` for week *w* itself** — post-game.
- **Any ECR vintage later than the week's canonical snapshot.**
- **Injury rows with `date_modified` > cutoff.**
- **Season-level aggregates that span the target week.**

Vegas and weather are the two most tempting features in weekly fantasy and both are class D
here. That is a real limitation on how strong Alpha-without-ECR can be, and it is stated up front
rather than discovered after a disappointing result.

---

## 7. Current Alpha architecture: what exists for weekly

**There is a weekly projection path, and it has never been evaluated as a weekly ranking.**

| | |
|---|---|
| where | `models/established/` (M5), surfaced at `GET /rankings/weekly` |
| table | `weekly_projection_snapshot (player_id, season, week, model_name, position, predicted_points)` |
| model | `ml_catboost` (also ridge, xgboost, two ablations) |
| training | walk-forward, expanding window, seasons **< S** only |
| features | **11 total** — `games_played_prior`, `fp_ppr_avg_last3`, `fp_ppr_avg_season_to_date`; `targets/carries/receptions/target_share/snap_pct _avg_last3`; `team_plays/pass_rate/epa _avg_last3` |
| positions | **QB/RB/WR/TE only — no K, no DST** |
| target | `target_fantasy_points_ppr` — **full PPR only** |
| opponent / matchup | **none** |
| Vegas / weather / injury / depth chart | **none** |
| ECR | **not used** |
| evidence layer | `projection_deltas` (M9) — a bounded adjustment from structured events, joined at serve time |
| **how it is evaluated** | **weekly predictions are summed into a season total** and compared against `player_season_stats` |

That last row is the crux. The weekly model was built as a *means to a season total* for the
draft program. Its own docstring says so: "aggregates those weekly predictions into a season-total
per player to compare against `player_season_stats`". **No weekly ranking metric has ever been
computed on it.** So K14: it exists, and nothing is known about whether it is any good at the job
this program cares about.

**Leakage posture of what exists.** Good, with one gap. The panel is leakage-safe by
construction (§6.3) and pinned by `tests/leakage/test_player_week_features_leakage.py`. The
evidence engine dates events to be available before the week starts. The gap is that neither was
built against a *calendar* cutoff — both use a "prior completed games" boundary, which coincides
with Friday-safety for every player except the TNF case §4.6 removes.

**Snapshot capability.** The system can produce historical weekly projections for any covered
week (that is what the walk-forward already does). It cannot currently produce them *as of a
stated timestamp* with an information-set filter, because no such filter exists. That is the
main piece of new machinery W2 needs, and W1 has built its foundation
(`evaluation/weekly/snapshots.py`).

---

## 8. How availability should be represented

Per the brief, and W1 endorses it on the evidence:

> **The core projection is expected fantasy production CONDITIONAL ON BEING ACTIVE.
> Availability is a separate, parallel quantity. The foundational ranking does not multiply
> them.**

The data supports keeping them separate cleanly, because `player_week_stats` has a row **iff the
player played**. A missing row is a bye, an inactive, an injury or an off-roster week — all
identical in consequence and all distinguishable from "played and scored 0.0". That is the same
mechanism `evaluation/weekly_objective.py` already relies on for the draft program's weekly
objective, so the two programs agree on what "did not play" means.

Two evaluation concepts, never mixed:

- **A — Production forecast.** Scored **only on players who played**. Answers: given that he
  played, how close was the projection, and how well were the players ordered?
- **B — Availability.** A separate binary-outcome question: did the ranked player play at all?

Why not multiply: an injury already moves projected production through workload, snaps, role and
efficiency. Multiplying by P(play) on top double-counts it. A later start/sit layer may use both;
the foundational ranking keeps them apart.

**Measured scale of B (2024, FLEX universe, post-TNF-exclusion, identity-joined):** of ranked
RB/WR/TE, **72.6% have a realized row** (3,889 of 5,357 across 14 weeks). That ~27% is dominated
by deep-board players who were never going to play, not by injury surprises — the top of the
board is far more available than the tail. Which is itself an argument for reporting A and B at
each depth rather than pooling them.

**W1 does not pick the availability metric.** It defines the split and the universes; W2 selects
the metric with the rest of the suite, pre-registered.

---

## 9. Proposed repository / file hierarchy

The repo is coherent for one research program and needs **small, additive** structure for a
second. No existing file is moved. What W1 added:

```
src/alpha_squad/evaluation/weekly/     NEW — weekly research instruments (research-only)
    scoring.py         Half/Full PPR ground truth; the verified identity
    series.py          weekly (ecr_type, page_type) series; the superflex/FLEX rule
    snapshots.py       cutoff, snapshot→week assignment, eligible universe   <-- leakage boundary
    audit.py           the W1 measurements, as functions
scripts/research/w1_weekly_foundation_audit.py   NEW — the runner (W-prefix, matching d###_)
docs/weekly/                                     NEW — weekly-program context
    W1_FOUNDATION_AUDIT.md      this document
    W2_PREREGISTRATION.md       the pre-registered W2 experiment
docs/README.md                                   NEW — the authority map (§10)
tests/unit/test_weekly_scoring.py                NEW
tests/unit/test_weekly_series.py                 NEW
tests/leakage/test_weekly_snapshot_cutoff.py     NEW — the leakage boundary's tests
```

**Why a subpackage rather than four more files at `evaluation/` root.** That directory already
holds 30 modules, effectively all of them draft-program instruments. A second program dropped
flat into it would be indistinguishable from the first within a phase or two. A subpackage costs
one directory and makes "is this draft or weekly?" answerable from the path.

**Why `evaluation/` at all, for research code.** It is where this repo already puts research
instruments — `rb_availability_experiment.py`, `board_vintage.py`, `draft_oracle.py`. D108
records that the only `src/` change across D98–D108 was `evaluation/draft_oracle.py`, "imported
by no production path". The weekly package holds to the same contract, stated in its `__init__`.

**Naming.** The draft program numbered phases by decision (`d100_*`). The weekly program numbers
by phase (`w1_*`) and still records a decision in the one shared log. See §10.2.

**How it scales to start/sit, waivers and trades.** Those are *decision layers* over the ranking,
which is the same separation `league/` vs `models/` already encodes and which CLAUDE.md requires
("universal player intelligence and league-specific decision logic are separate layers"). The
ranking lives in the weekly package; a future start/sit layer is roster-specific and belongs
next to `league/decisions.py`, consuming the ranking rather than reimplementing it. Nothing in
W1's structure has to change to add them — which is the test of the structure.

---

## 10. Proposed context / knowledge hierarchy

### 10.1 What was wrong

`docs/` is **44 files, flat**, mixing five different kinds of thing: product authority
(`TARGET_FORMAT_1QB.md`), shared methodology (`BENCHMARK_SPEC.md`), draft-program findings
(19 `D##_*.md`), living state (`PROJECT_STATE.md`, 200 KB), and the decision log
(`DECISIONS.md`, 568 KB, D1–D108). Nothing in the tree says which of those a given file is, or
whether a finding is draft-specific or general. With one program that was navigable by memory.
With two it is not: the single highest-risk failure mode for this phase is a future reader
applying a draft-program conclusion to a weekly question.

### 10.2 The fix: an authority map, not a reorganisation

`docs/README.md` (added) classifies every existing document by **kind** and **scope**
(shared / draft-specific / weekly-specific) and names the authoritative source for each type of
information. **No file is moved**, so no citation in 44 documents breaks.

The authority hierarchy, most authoritative first:

| tier | source | scope |
|---|---|---|
| 1 — Product authority | `PRODUCT_SPEC.md`, `ARCHITECTURE.md`, `ACCEPTANCE_CRITERIA.md`, `AGENT_CONTRACTS.md`, `IMPLEMENTATION_PLAN.md`, `CLAUDE.md` | shared |
| 2 — Decisions | **`docs/DECISIONS.md`** — one append-only log, D-numbered, for the whole project | shared |
| 3 — Program entry points | `docs/D108_PROGRAM_CLOSEOUT.md` (draft), **`docs/weekly/W1_FOUNDATION_AUDIT.md`** (weekly) | per-program |
| 4 — Methodology | `docs/BENCHMARK_SPEC.md` (draft), `docs/weekly/W2_PREREGISTRATION.md` (weekly) | per-program |
| 5 — Data contracts | `docs/DATA_SOURCES.md`, `docs/TARGET_FORMAT_1QB.md` | shared |
| 6 — Living state | `docs/PROJECT_STATE.md`, `docs/TRACEABILITY.md` | shared |
| 7 — Phase findings | `docs/D##_*.md`, `docs/weekly/W#_*.md` | per-phase, historical once superseded |

**One decision log, deliberately.** The alternative — a `WEEKLY_DECISIONS.md` — would create
exactly the parallel source of truth the brief warns against, and would make "has this been
decided?" a two-file question. The weekly program continues the D-sequence (this phase is
**D109**) and uses W-numbers only for *phases*. D-numbers say *what was decided*; W-numbers say
*which phase decided it*.

### 10.3 Shared vs draft-specific vs weekly-specific methodology

The brief asks for this explicitly, and it is the distinction most likely to be got wrong.

**Shared — transfers unchanged:**
- Pre-registration before measurement; decision rules fixed before results; no post-hoc metric
  selection (D70, D106).
- Leakage-safety by construction, with adversarial tests that try to disprove it.
- Provenance: immutable hashed snapshots; instruments committed, not ad hoc (**D92** — a finding
  had to be *retracted* because its runner was never committed).
- A series is `(ecr_type, page_type)` (**D56**) — and §3.3 shows it recurring verbatim.
- Never use a name as a join key; DST ids from team codes (**D57**).
- Report what failed; "nothing shipped" is a legitimate and common outcome.

**Draft-specific — does NOT transfer:**
- The **172–250 point detection floor**. That is a *draft* instrument's resolution over 5 season
  clusters. The weekly instrument has ~79 weeks × hundreds of players and an entirely different
  noise structure. Quoting it here would be a category error.
- **D108's canonical conclusion** (no ranking intervention beat Y1). It is explicitly scoped to
  the draft, 2021–2025, two roster configs. It says nothing about weekly.
- Replacement level, VORP, positional scarcity, roster construction, `roster_size`, draft-aware
  replacement. A weekly ranking has no draft.
- `weekly_lineup_points` / the weekly *objective* (D86/D103). That scores a **season of a fixed
  roster**; this program scores **one week's ordering of all players**. Same word, different
  quantity — a genuine trap given both live under `evaluation/`.
- Preseason-only scoping (D54) and the 2021+ board floor (D95): those are the *draft* series'
  constraints. The weekly series have their own, measured in §4.3.

**Weekly-specific — new here:**
- The Friday cutoff and its two independent justifications (§3.1).
- Already-played (TNF) exclusion (§4.6) — no draft analogue.
- The FLEX reconstruction from a superflex board and its stated limit (§4.5).
- The production-forecast / availability split (§8).
- Multi-depth evaluation (top 10/25/50/full) as a first-class requirement rather than a summary.

---

## 11. Parity / reproducibility baseline

| | |
|---|---|
| branch | `claude/dreamy-albattani-efvroj` |
| base commit | `b82d2cf` (D108 closeout) |
| tests before W1 | **1427 passed, 44 deselected** — exactly the D108 recorded state |
| tests after W1 | **1462 passed, 44 deselected** |
| new tests added by W1 | **35** — 11 scoring, 9 series, 15 leakage |
| `make lint` | clean, **both halves** (`check-secrets`, `ruff check`, `ruff format --check`: 255 files) — D108 §3's lesson |
| `models/`, `league/`, `api/`, `cli.py` | **untouched** |
| ECR vintage measured | `db_fpecr.parquet` sha256 `e270d790165a6c304e5854145332fe9da3caacab3a61e1efea280b57cc5db9a5` |
| crosswalk vintage | `db_playerids.csv` sha256 `36016b9239e3e7dab9a21d9a855692e374d3b7b98ba000af06a8555886b19ca4` |
| schedule vintage | `nfldata/games.csv` sha256 `b65b2a304096c9e6e17690d9b1e38a818e82579239e8ede03433c9c9b587ffcf` |
| dependencies | unchanged (`uv.lock` untouched) |

**The mirror is not immutable.** `db_fpecr.parquet` is continuously rebuilt upstream. D92 found
and then *retracted* a "board vintage" finding for the draft series, concluding the historical
board is immutable — that conclusion was established for the draft series and has **not** been
established for the weekly series. W2 must pin and re-verify the hash, and re-check whether
historical weekly rows ever change. Until then, treat weekly-board immutability as unverified.

---

## 12. Sample size and statistical power

What is actually available, for the primary (Full-PPR, FLEX, Friday) comparison:

| unit | count |
|---|---:|
| seasons | 5 usable (2021–2025); 2020 partial, 2026 excluded |
| covered REG weeks, 2021–2025 | **79** |
| covered REG weeks incl. 2020 | 90 |
| snapshots per week | **1** (Friday) |
| ranked FLEX (RB/WR/TE) player-weeks, 2021–2025 | **~30,200** (measured 5,357 over 14 weeks in 2024; scaled) |
| of those, **active** (have a realized row) | **~21,900** (72.6% measured) |
| positional player-weeks | QB ~3,600 · RB ~9,000 · WR ~13,000 · TE ~7,700 · K ~2,500 · DST ~2,400 |

**The honest unit of replication is the week, not the player-week.** Player-weeks within a week
share the slate, the weather, the injury news and the same ECR vintage, so they are nowhere near
independent. **n ≈ 79** is the number that governs how confidently two systems can be separated,
and a per-week paired comparison (the same 79 weeks, both systems) is the design that respects
it. That is far more replication than the draft program's 5 season-clusters, which is the single
biggest structural advantage this program has over the last one.

**W1 does not state a minimum detectable effect (U4).** Doing so would require the per-week
variance of the primary metric, which requires running the ECR-alone baseline — and running it
before pre-registering the metric suite is exactly the ordering the brief forbids. W2 computes
the noise floor **from the ECR-alone baseline alone**, before any Alpha comparison, and the
pre-registration fixes that ordering. Inventing a threshold now, from nothing, would be
manufacturing precision the data has not yet supplied.

---

## 13. Proposed evaluation framework

Full specification, with the decision rules, is in `docs/weekly/W2_PREREGISTRATION.md`. Summary
of the metric suite and — as the brief requires — the user need each metric corresponds to:

| metric | what it measures | user need |
|---|---|---|
| Spearman ρ (per week, per position & FLEX) | overall rank-order quality | "is this list ordered sensibly at all" |
| NDCG@k, k ∈ {10,25,50} | order quality weighted to the top | "the top of my list is what I act on" |
| Top-k hit rate, k ∈ {10,25,50} | set identification at depth | "did it find the right players to consider" |
| Pairwise ordering accuracy, and restricted to pairs with |Δpoints| ≥ 3 | decision-relevant ordering | **"which of these two do I start"** — the literal start/sit act |
| MAE / RMSE vs realized points (active only) | point-prediction accuracy | supporting diagnostic; needed for FLEX comparability across positions |
| Calibration of projected vs realized by decile | is the magnitude trustworthy | "16.8 should mean 16.8" |
| Availability metric (separate) | did the ranked player play | §8 — reported apart, never folded in |

**Deliberately no composite score.** A system excellent at the top and a system excellent deep
are useful for different products (shallow-league start/sit vs waiver research), and collapsing
them now would destroy the distinction before it has been measured. The brief says this and W1
agrees; it is also the D101 lesson — projection metrics are not even monotone in *each other*.

**Depths are reported separately, always.** D108's worked counterexample (ECR beat M6 on all
three identification metrics and then did not produce better picks) is the standing reminder
that one metric is not the product.

---

## 14. The three systems

All three are evaluated on the **identical** player universe, week, cutoff, scoring rules,
ground truth, depth cutoffs and metrics. The only thing that varies is the information each may
use.

### 14.1 ECR alone — the benchmark

The week's canonical Friday board for the relevant series (§4.1), already-played teams removed,
identity-joined, densely re-ranked. FLEX = superflex board minus QBs (§4.5). **Never** a later
vintage; **never** a substituted board for a missing week — an uncovered week is simply out of
scope, and the covered-week list in §4.3 is fixed in advance.

*Can it be constructed validly and reproducibly?* **Yes.** §4.1–4.7 establish every piece:
the series exist, the vintages are dated, the universe rule is cutoff-owned, identity resolves
at ~100% where it matters, and the whole thing is behind a hashed snapshot.

### 14.2 Alpha without ECR

The existing `models/established/` weekly path is the **starting point, not the answer**. As it
stands it has 11 features, no opponent, no injury and 4 positions (§7). To be a fair
"Alpha-without-ECR" it needs, at minimum: K and DST coverage (their ground truth already
exists), an opponent/matchup feature, and the Friday-filtered injury signal from §6.2.

*Can it be constructed validly and reproducibly?* **Yes, but it is work, and W2 must not let it
become an open-ended modelling project.** The pre-registration fixes its feature set in advance
precisely so it cannot be tuned after seeing the comparison.

### 14.3 Alpha with ECR

Identical to 14.2 **plus the week's Friday ECR as an input feature**, and nothing else changed.
ECR must be the *only* difference, or the contrast measures something else. The draft program
already established the relevant precedent: D98 found the ECR feature semantically correct and
the "obvious fix" a regression, so the same care applies to how the weekly ECR feature is
encoded (rank vs rank-within-position vs implied points).

*Can it be constructed validly and reproducibly?* **Yes**, conditional on 14.2.

**The questions this design answers** — and the reason it is three systems and not two: how
strong is ECR by itself; how strong is Alpha without it; does ECR add information to Alpha; does
Alpha add information beyond ECR; and do any of these differ by depth. A two-system design
answers only the last-but-one.

---

## 15. Major limitations

1. **One snapshot per week (Friday).** The daily cadence is not historically testable (§3.1).
2. **No Half-PPR benchmark** (§3.2).
3. **No 1-QB weekly overall board**; FLEX is a reconstruction whose cross-position calibration is
   unverified (§4.5, U3).
4. **Vegas and weather are unusable historically** (§6.4, §6.5). This caps how strong
   Alpha-without-ECR can be, and any null result must be read with it in view.
5. **Week 1 covered once; 2024 starts at week 4.** In-season signal availability is confounded
   with week index.
6. **Weekly-board immutability is unverified** (§11).
7. **Depth-chart timing is assumed, not timestamped** (§6.2).
8. **79 weeks is good replication but 5 seasons is few** for anything season-level.
9. **The existing weekly model is unevaluated as a ranking** — W2's baseline may turn out weak,
   and a weak Alpha-without-ECR makes the "does ECR add information" contrast easy in an
   uninteresting way.
10. **Nothing here measures ranking quality yet.** Every comparative statement in this program is
    still ahead of us.

---

## 16. Recommended W2 experiment

**W2 must answer one question, and it is not "does Alpha beat ECR".**

> **How strong is the ECR-alone weekly benchmark, and what is the noise floor of the primary
> comparison?**

Concretely: construct the ECR-alone baseline over the 79 covered 2021–2025 weeks, compute the
full pre-registered metric suite at every depth and position plus FLEX, and estimate the
**per-week variance and minimum detectable difference** of each primary metric.

**Why this is the highest-value next step against the product goal**, rather than building a
model:

1. **It is the gate every later claim depends on.** Without the noise floor, "Alpha beat ECR by
   0.01 ρ" is uninterpretable. The draft program's single most useful number was its detection
   floor, and it was computed *late* — after phases had been spent on effects below it.
2. **It is the only step that can be taken without contaminating the comparison.** Measuring ECR
   alone touches no Alpha system, so it cannot be tuned toward a result.
3. **It reveals the shape of the problem before anyone commits to a model.** If ECR is already
   near the achievable ceiling at the top 10 but weak at 50+, the product opportunity is deep-pool
   ranking and waiver research — a completely different modelling program from "beat ECR at
   WR1". W1 cannot tell which, and guessing would set the direction of everything after it.
4. **It is cheap and fully specified.** Every input is audited, hashed and reachable.

**What W2 must NOT do:** build the Alpha weekly model, tune anything, run a comparison, or select
a metric after seeing a result. Those are W3.

The pre-registration is written and committed **before** any of it runs:
`docs/weekly/W2_PREREGISTRATION.md`.

---

## 17. Reproducing every number in this document

```bash
make install
# provenance-preserving path (after `make ingest features market`):
uv run python scripts/research/w1_weekly_foundation_audit.py --from-db \
    --out reports/weekly/w1_audit.json

# pinned-vintage path, as W1 was actually run:
uv run python scripts/research/w1_weekly_foundation_audit.py --from-files \
    --ecr db_fpecr.parquet --xwalk db_playerids.csv --schedule nfl_games.csv

uv run pytest tests/unit/test_weekly_scoring.py tests/unit/test_weekly_series.py tests/leakage/
make lint
```
