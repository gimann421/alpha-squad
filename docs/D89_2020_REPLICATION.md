# D89 — O1 at six seasons: the final power test on this benchmark

*Not a new objective, not a tuning phase. The only change from D88 is the **2020 season**.
`models/` and `league/` are **byte-identical to Y1** throughout.*

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| working tree at start | clean |
| HEAD at start | `13770d6` (D89 checkpoint) |
| branch | `claude/separate-valuation-legality-4tw82o` (12 ahead of `origin/main`, 0 behind) |
| `src/alpha_squad/models/` + `src/alpha_squad/league/` vs `origin/main` | **byte-identical — empty diff** |
| D85 artifacts | `decision_legality.py`, `test_decision_legality.py`, `VALUATION_LEGALITY_SEPARATION.md` |
| D86 artifacts | `objective_candidates.py`, `weekly_objective.py`, `draft_oracle.py`, `otiers2.json` |
| D87 artifacts | `d87arms.json`, `equiv.json`, `D87_SHORTLIST_REPLICATION.md` |
| D88 artifacts | `d88.json` (225 KB, 200 drafts), `D88_O1_POWER_REPLICATION.md` |
| database | intact, 231 MB |
| `shortlist_k` | `None` by default and never passed in D88/D89 — full board |

No production behaviour was modified and no production diff was prepared.

---

## 2. 2020 data validation (Phase 1)

The question is not "does 2020 exist" but "can 2020 be evaluated by **exactly** the code path that
produced 2021–2025". Every quantity below is produced by that same path, printed side by side so a
2020-specific anomaly would be visible rather than absorbed.

### 2.1 A defect found before running, without which 2020 would have been fabricated

`market/series.py` resolves the target format to `ecr_type='ro'`, and the harness assumed the
page was `redraft-overall`. That is true from 2021 on. **It is false for 2020.**

| season | preseason (Jul/Aug) rows under `redraft-overall` | rows under the season's actual preseason page |
|---|---|---|
| **2020** | **0** | **3,462** (`redraft-offense`) |
| 2021 | 5,147 | 5,147 (`redraft-overall`) |
| 2022 | 4,614 | 4,614 (`redraft-overall`) |
| 2023 | 5,132 | 5,132 (`redraft-overall`) |
| 2024 | 4,651 | 4,651 (`redraft-overall`) |
| 2025 | 4,452 | 4,452 (`redraft-overall`) |

2020 *does* have 4,922 `redraft-overall` rows — **all of them in-season**, i.e. information that
did not exist at the draft. Taking the default would have produced an **empty preseason board**
for 2020, and the fair-market opponent (`MARKET_CONSENSUS_ROSTER_AWARE`) would have fallen back to
drafting in **alphabetical order**. That is precisely the "manufactured 2020 observation" the brief
forbids, and it would have looked like a completed run.

The fix is `draft_forensics.preseason_page_type`, which asks the data which page actually carried a
July/August board that season instead of assuming one. It resolves `redraft-offense` for 2020 and
`redraft-overall` for 2021–2026, so **every previously published number is unchanged** — asserted
both by unit test (`TestD89PreseasonPageType`) and, in this run, by per-draft comparison against
`d88.json` (§4).

### 2.2 Comparability, on the engine's own inputs

| season | board | projected | market-ranked | coverage | weekly rows | weeks | best K rank | best DST rank | mean availability |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | *none* | 174 | 0 | **0.0%** | 17,158 | 1–17 | — | — | 89.2% |
| **2020** | `redraft-offense` | **612** | 458 | **74.8%** | 17,269 | 1–17 | 175.4 | 146.2 | **89.7%** |
| 2021 | `redraft-overall` | 636 | 490 | 77.0% | 17,569 | 1–17 | 174.4 | 149.8 | 88.3% |
| 2022 | `redraft-overall` | 651 | 496 | 76.2% | 17,420 | 1–17 | 178.0 | 157.5 | 88.3% |
| 2023 | `redraft-overall` | 610 | 484 | 79.3% | 17,271 | 1–17 | 173.9 | 161.9 | 89.6% |
| 2024 | `redraft-overall` | 602 | 515 | 85.5% | 17,570 | 1–17 | 189.8 | 158.5 | 89.6% |
| 2025 | `redraft-overall` | 629 | 480 | 76.3% | 17,968 | 1–17 | 187.0 | 152.8 | 89.7% |

Board composition and the demand the engine schedules against:

| season | QB | RB | WR | TE | K | DST | | demand QB | RB | WR | TE | K | DST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **2020** | 66 | 148 | 211 | 113 | 42 | 32 | | 2.0 | 4.8 | 5.2 | 2.0 | 1.0 | 1.0 |
| 2021 | 70 | 149 | 225 | 115 | 45 | 32 | | 1.9 | 4.8 | 5.5 | 1.8 | 1.0 | 1.0 |
| 2022 | 75 | 151 | 226 | 120 | 47 | 32 | | 1.7 | 4.8 | 5.8 | 1.7 | 1.0 | 1.0 |
| 2023 | 74 | 141 | 206 | 113 | 44 | 32 | | 1.8 | 4.7 | 6.0 | 1.5 | 1.0 | 1.0 |
| 2024 | 70 | 137 | 211 | 113 | 39 | 32 | | 2.5 | 4.3 | 5.5 | 1.7 | 1.0 | 1.0 |
| 2025 | 73 | 136 | 221 | 124 | 43 | 32 | | 2.3 | 4.6 | 5.4 | 1.7 | 1.0 | 1.0 |

Model-side inputs, all populated and in family:

| season | uncertainty predictions (`uncertainty_catboost_v2`) | confidence | ECR dispersion | availability window | positions measured |
|---|---|---|---|---|---|
| **2020** | **435** | 435 | 710 | **2015–2019** | 6/6 |
| 2021 | 468 | 468 | 1,529 | 2016–2020 | 6/6 |
| 2022 | 472 | 472 | 799 | 2017–2021 | 6/6 |
| 2023 | 439 | 439 | 728 | 2018–2022 | 6/6 |
| 2024 | 439 | 439 | 966 | 2019–2023 | 6/6 |
| 2025 | 453 | 453 | 826 | 2020–2024 | 6/6 |

Two consequences worth stating explicitly:

* **The availability window is a fixed `[season−5, season)` look-back, not "the seasons in the
  experiment".** Adding 2020 to D89 therefore does **not** change the rates 2021 uses (2021 already
  measured on 2016–2020). That is what makes bit-identical reproduction possible, and it is also
  what makes 2020 itself leakage-free: it measures on 2015–2019.
* **COVID did not degrade 2020 on the axis that matters here.** Measured availability is **89.7%**,
  the joint highest of the six seasons (range 88.3–89.7%). The a-priori worry that 2020 would be an
  availability outlier is not borne out in the data.

### 2.3 The one known asymmetry, recorded before the run

2020 was a 16-game / 17-week regular season; 2021 onward are 17-game / 18-week. `FANTASY_WEEKS` is
**1–17 for every season and was not changed for 2020** — the pre-existing D86 definition applied
unchanged, not a 2020-specific one. Consequence: weeks 1–17 covers all of 2020 and excludes
2021+'s final week. It is **paired** — both arms in a season see exactly the same weeks — so it
cannot bias the difference; it can only shift a season's level, which the paired design differences
out. Expect 2020's absolute totals to sit below 2021–2025's, because each player carries one more
bye week in a 16-game season.

### 2.4 Verdict for the target format

**2020 is comparable and is included. 2019 is not comparable and is excluded** — 174 board players
and **0% market coverage**, so there is no preseason board for the fair-market opponent to draft
against and the implied demand degenerates (K 3.3, DST 3.0). The exclusion is recorded in code
(`replication_design.EXCLUDED_SEASONS`) with that measured reason, not as a preference.

### 2.5 A gap in the validation above, which the run exposed: legacy 2020 does not exist

**Everything in §2.1–2.4 validates one market series, `ro`, and the legacy format does not use
it.** The two shipped formats resolve to different series — target to `ro` (redraft overall),
legacy to **`dsf`** (dynasty superflex). The first Phase 1 pass checked only `ro` and concluded
"2020 is comparable". That conclusion is correct for the target format and **was wrong for the
legacy format**. The run itself surfaced it by reporting `board=None` for the legacy 2020 block.

The `dsf` series' earliest scrape of **any** kind is **2020-10-16**:

| `dsf` rows in 2020 | count | window |
|---|---|---|
| July/August (preseason) | **0** | — |
| October | 997 | 2020-10-16 … 10-29 |
| November | 1,021 | 2020-11-05 … 11-26 |
| December | 1,228 | 2020-12-03 … 12-24 |

**There is no dynasty-superflex preseason board in 2020.** No page_type resolution can recover a
board that was never published, and the October rows cannot be substituted: they are *in-season*,
so reading them would leak market movement that happened after the draft — the D54 defect, and
exactly what §2.1's fix exists to prevent.

**Why this mattered more than a missing cell.** With `market_rank` empty, `_market_consensus_pick`
falls back to ordering by `player_id`, so the nine fair-market opponents draft **alphabetically**.
The loop completes, the rosters are legal, and every metric comes back finite — **the run looks
successful and measures a different game**. That is precisely the manufactured observation the
brief forbids, and it would have been invisible in the output.

**Action taken.** The legacy 2020 cell is **dropped, not repaired**: legacy runs on 2021–2025 (5
clusters), unchanged from D88. `EXCLUDED_SEASONS` is now keyed by `(format, season)`, because
usability is a property of the *pair*; the analysis scripts filter from that registry rather than
an ad-hoc condition, so the measured reason travels with the exclusion. **Recorded before any
legacy 2020 outcome was examined.**

**Guard added so this cannot recur silently.** `assert_usable_market_board` raises
`EmptyMarketBoardError` when a market-driven opponent is handed an empty board, checked as a
precondition of `simulate_forensic_draft`. Six regression tests, including one asserting the guard
is a pure precondition that changes no normal draft. Had it existed, this would have failed on the
first draft instead of after 120.

---

## 3. Pre-registration (Phase 2)

Committed as `8c34ff9`, **before any D89 result was examined**, as
`src/alpha_squad/evaluation/replication_design.py` with 18 tests.

| | D86 | D87 | D88 | **D89** |
|---|---|---|---|---|
| seasons | 2021–2025 | 2021–2025 | 2021–2025 | **2020–2025** |
| slots | 4 | 4 | 10 | 10 |
| candidate set | full board | K=10 shortlist | full board | **full board** |
| objective | `E[weekly MSV] + 1.0·daVORP` | unchanged | unchanged | **unchanged** |
| formats, opponent, scoring, metrics, gates | — | — | — | **unchanged** |
| randomization | common random numbers on `player_id`; deterministic, no seed | — | — | **unchanged** |

The designs are frozen dataclasses, and `tests/unit/test_replication_design.py` asserts
mechanically that **D89 differs from D88 in `phase` and `seasons` and in nothing else**, that
`shortlist_k is None`, that the gate constants are the *same objects* imported from
`objective_candidates` (hence D84's), and that no new numeric constant appears in the module. A
phase in this lineage therefore cannot drift into a new experiment while still being reported as a
power test.

Predictions R1–R6 were recorded with their failure modes, notably:

* **R1** — 2021–2025 reproduces D88 **bit-identically**, not "within tolerance". Anything else is a
  defect and stops the phase.
* **R2** — MDE falls from ~56 to ~47 **only if** 2020 lands near the existing between-season
  spread. It does **not** fall if 2020 is an outlier: one extreme cluster can raise the
  between-season SD enough to cancel the gain from `t(df=5) < t(df=4)`.
* **R3** — the point estimate should move less than `SD/√6 ≈ 18` points; more than that is
  instability, not better measurement.
* **R5** — verdict **B** remains the most likely single outcome, because a ~3-point margin either
  way is not a resolution.

---

## 4. D88 reproduction (Phase 4)

Slots 1–10 and seasons 2021–2025 are exactly D88's cells, so they are a built-in control inside
the same run.

| check | result |
|---|---|
| shared cells compared (5 seasons × 10 slots × 2 arms × 2 formats) | **200** |
| max abs deviation across the 6 gate-bearing metrics | **0.000000000000** |
| drafted-roster mismatches | **0** |
| target 2021–2025 margin | **+50.5, CI [−5.5, +106.6]** — D88's published number to the decimal |
| legacy 2021–2025 margin | **−2.3, CI [−85.5, +80.8]** — likewise |

**Prediction R1 holds: bit-identical, not merely "within tolerance."** The `preseason_page_type`
change is a proven no-op for 2021–2025, so 2020 is being added to an unchanged experiment rather
than to a re-specified one.

### The two cells that did not reproduce, and why they are not the experiment

Two of the 200 shared cells differ in exactly one field — `bench` — while every gate-bearing
metric and every drafted roster is identical:

| cell | D88 | D89 |
|---|---|---|
| legacy 2021, slot 2, O0 | 526.00 | 519.60 |
| legacy 2024, slot 8, O1-FULL | 647.72 | 651.72 |

**Cause, verified rather than inferred.** `league/replacement.py::compute_league_starters` builds
`flex_candidates` by iterating `flex_eligible_positions`, a `set[str]`, then stable-sorts on
points. When two flex-eligible players at *different* positions have exactly equal points, the
last flex slot is awarded by set-iteration order, which varies with `PYTHONHASHSEED` between
processes. Re-running the first cell under seeds 0–5:

| seed | `bench` | `weekly_no_foresight` | `weekly_hindsight` |
|---|---|---|---|
| 0, 1, 2, 3, 5 | 526.00 | 2334.32 | 2487.72 |
| **4** | **519.60** | **2334.32** | **2487.72** |

That is the signature the explanation predicts: the tied players contribute *equal* points, so the
**lineup total cannot move** — only the bench *attribution*, which asks which player was fielded.

**Consequences, stated rather than buried.** Every metric entering a gate or a conclusion is
bit-identical across all 200 cells, so the primary metric is provably unaffected. `bench` is a
secondary diagnostic used in the mechanism narrative and in **no gate**, but the bench figures
quoted in §11 carry a tie-break uncertainty of roughly this size (≈ 4–6 points on a 400–630 point
figure, 2 cells in 200) and should not be read as exact.

The fix is a deterministic secondary sort key in `league/replacement.py` — which D89 is forbidden
to touch, because Y1 must stay byte-identical. It is recorded as a future item in §20 and pinned
by three characterization tests (`TestD89FlexTieBreakIsOrderDependent`) that assert the invariant
half: the lineup total cannot change under an exact tie, both orderings are reachable so no caller
may depend on the winner, and an untied flex is fully deterministic.

---

## 5. Sample size (Phase 3)

| | target 1QB | legacy 2QB |
|---|---|---|
| seasons | **2020–2025** | **2021–2025** |
| paired draft observations | **60** | **50** |
| season clusters | **6** | **5** |
| slots per season | 10 | 10 |
| drafts analysed (both arms) | 120 | 100 |
| drafts run but **excluded** | 0 | **20** (legacy 2020, §2.5) |

**240 drafts run, 220 analysed.** The two formats legitimately carry different cluster counts,
because 2020 has a usable preseason board in the target format's market series and **none at all**
in the legacy format's. Any cross-format comparison below is therefore **6 clusters against 5**,
and is labelled as such rather than presented as symmetric.

---

## 6. Power / MDE (Phase 5) — target format

All figures below are recomputed from the `d88.json` and `d89.json` artifacts by one function, so
the two columns are directly comparable.

| quantity | D88 (5 seasons) | **D89 (6 seasons)** |
|---|---|---|
| SD of season means | 45.1 | **40.5** |
| mean within-season SD (across 10 slots) | 58.8 | 57.9 |
| irreducible between-season SD | 41.1 | **36.2** |
| clustered SE | 20.2 | **16.5** |
| `t(df = n−1)` | 2.776 | **2.571** |
| **MDE** | **56.0** | **42.5** |
| observed effect | +50.5 | **+49.0** |
| effect / MDE | 0.90 | **1.15** |
| MDE floor at infinite slots | 51.1 | **38.0** |

**The MDE fell further than D88 forecast, and for a reason D88 could not know in advance.** D88
projected MDE ≈ 47.3 at six seasons *holding the between-season SD at 45.1*. The actual SD fell to
**40.5**, because 2020's cluster mean (**+41.3**) landed close to the six-season mean rather than
in a tail. So the improvement has two sources:

| step | MDE |
|---|---|
| D88, 5 seasons, SD 45.1 | 56.0 |
| + one cluster (D88's forecast, SD held at 45.1) | 47.4 |
| + the SD 2020 actually produced (40.5) | **42.5** |

### A correction to D88's slot-sensitivity table

D88 published a table of `SE` against slot count (23.7 at 4 slots → 20.2 at ∞) and concluded the
MDE asymptotes at **56.0**. That column was computed as `sqrt(SD² + within²/n)/√k`, which **adds
within-variance to an SD that already contains it** — the 45.1 was the SD of the observed season
*means*, not an isolated between-season component. It is also inconsistent with D88's own published
interval: its CI half-width of 56.05 corresponds to `SE = 45.1/√5 = 20.2`, not to the 21.7 the
table lists at 10 slots.

Decomposing correctly, `Var(season mean) = between² + within²/n_slots`, gives a true between-season
SD of **41.1** and a 5-season infinite-slot floor of **51.1**, not 56.0.

**D88's headline conclusion is unaffected and in fact slightly strengthened**: the real floor
(51.1) still sat above the effect it was measuring (+50.5), so slots genuinely could not have
resolved it, and seasons genuinely were the binding constraint. Only the arithmetic of the
sensitivity column was wrong.

**This was registered in advance as a coin flip, not a foregone conclusion.** Prediction R2 stated
that the MDE would *not* fall if 2020 were an outlier, because one extreme cluster can raise the
between-season SD enough to cancel the gain from `t(df=5) < t(df=4)`. It landed on the favourable
side. Had 2020's cluster come in at, say, +150 or −60, this phase would have reported a *wider*
interval on more data.

---

## 7. D86 vs D88 vs D89 (Phase 5) — target format

| phase | slots | seasons | n | primary | 95% CI | between-SD | season-long |
|---|---|---|---|---|---|---|---|
| D86 (4 slots, full board) | 4 | 5 | 20 | +52.9 | [−8.3, +114.0] | 49.3 | +34.5 |
| D88 4-slot subset (control) | 4 | 5 | 20 | +52.9 | [−8.3, +114.0] | — | — |
| D88 (10 slots, full board) | 10 | 5 | 50 | +50.5 | [−5.5, +106.6] | 45.1 | +39.9 |
| **D89 (10 slots, full board)** | **10** | **6** | **60** | **+49.0** | **[+6.5, +91.5]** | **40.5** | **+35.8** |

**The effect is stable across all three phases: +52.9 → +50.5 → +49.0.** Movement D88 → D89 is
**−1.5**, against R3's pre-registered stability threshold of `SD/√6 = 16.5`. Three independent
enlargements of the sample (slots 4→10, seasons 5→6) have each moved the estimate by less than 4
points and never changed its sign. The season-long metric improves throughout.

---

## 8. Target 1QB results (Phase 6)

| arm | weekly no-foresight — **primary** | weekly hindsight | season-long | total roster | bench | missed player-weeks | unfilled |
|---|---|---|---|---|---|---|---|
| O0 (Y1) | 1902.7 | 2064.2 | 1915.4 | 2597.8 | 385.2 | 50.4 | **0** |
| **O1-FULL** | **1951.7** | **2130.9** | **1951.2** | 2581.5 | 403.7 | 55.6 | **0** |
| **Δ** | **+49.0** | **+66.6** | **+35.8** | **−16.3** | **+18.5** | **+5.2** | — |

### Season by season

| season | n | primary Δ | season-long Δ | weekly-hindsight Δ | winner |
|---|---|---|---|---|---|
| **2020** | 10 | **+41.3** | +15.4 | +21.2 | **O1** |
| 2021 | 10 | +57.3 | +6.5 | +28.4 | O1 |
| 2022 | 10 | **−10.4** | −24.0 | +29.6 | Y1 |
| 2023 | 10 | +21.0 | +38.6 | +104.6 | O1 |
| 2024 | 10 | +90.8 | +104.5 | +117.4 | O1 |
| 2025 | 10 | +94.0 | +73.9 | +98.6 | O1 |

**5 of 6 seasons improved.** 2022 remains the single losing season, unchanged from D88.

**2020 is consistent with the existing effect, not an outlier and not a source of instability.**
Its +41.3 sits between 2023's +21.0 and 2021's +57.3, and it is the reason the between-season SD
*fell*. Leave-one-season-out margins: dropping 2020 → +50.5 (exactly D88), 2021 → +47.3,
2022 → +60.9, 2023 → +54.6, 2024 → +40.6, 2025 → +40.0. **All positive; no single season carries
the result.**

---

## 9. Legacy 2QB results (Phase 6)

**5 clusters (2021–2025), unchanged from D88 — and therefore bit-identical to D88.**

| arm | weekly no-foresight — primary | weekly hindsight | season-long | total roster | bench | missed player-weeks | unfilled |
|---|---|---|---|---|---|---|---|
| O0 (Y1) | 2213.5 | 2477.3 | 2151.2 | 3050.6 | 612.0 | 74.9 | **0** |
| O1-FULL | 2211.2 | **2502.4** | **2167.5** | **3101.8** | 626.6 | 70.3 | **0** |
| **Δ** | **−2.3** | +25.1 | +16.2 | +51.1 | +14.6 | −4.7 | — |

| season | n | primary Δ | season-long Δ | weekly-hindsight Δ | winner |
|---|---|---|---|---|---|
| 2021 | 10 | **−87.5** | −52.0 | −22.8 | Y1 |
| 2022 | 10 | +44.3 | +69.8 | +57.8 | O1 |
| 2023 | 10 | +40.2 | +47.4 | +97.0 | O1 |
| 2024 | 10 | +53.6 | +60.0 | +75.6 | O1 |
| 2025 | 10 | **−62.2** | −44.0 | −82.0 | Y1 |

**3 of 5 improved. Clustered 95% CI [−85.5, +80.8] — an effective null**, with a between-season SD
of **67.0**, half again the target format's. The point estimate is **−0.1%** of a ~2,200-point
base, and the three secondary metrics all move *positive* (+25.1, +16.2, +51.1).

**This is what prediction R6 registered in advance, and the reason is structural.** The legacy
lineup has **no K and no DEF slot** — its positional capacities are literally `K: 0, DST: 0`, and
both arms draft **zero** kickers and **zero** defenses in all 100 drafts. O1's principal
mechanism — stop over-buying positions with a single startable slot — **has nothing to act on in
this format**. A large legacy effect in either direction would have indicated a harness problem
rather than a finding; a null is the coherent outcome.

---

## 10. Gate results (Phase 7) — both formats

D86's gates, which are D84's, imported unchanged. **D88's table reported seven of them; G1, G4 and
G5 are computable from the recorded rosters and the league config, so they are computed here rather
than omitted.** No gate was added, relaxed, strengthened or re-thresholded.

| gate | threshold | target 1QB | legacy 2QB |
|---|---|---|---|
| G1 | no dedicated-slot position zeroed more often than control | **PASS** (0 vs 0) | **PASS** (0 vs 0) |
| G2 | roster infeasibility ≤ control | **PASS** (0 vs 0 unfilled) | **PASS** (0 vs 0) |
| G3 | primary worse in ≤ 1 season | **PASS** (1/6) | **FAIL** (2/5) |
| G4 | no position drafted > 2 rounds earlier | **PASS** (max +0.15 rd, K) | **PASS** (max +0.02 rd, TE) |
| G5 | no increase in capacity breaches at **any** position | **PASS** (31 vs 53) | **FAIL** (QB 22 vs 19) |
| G6 | leave-one-season-out margin stays positive | **PASS** (+40.0 … +60.9) | **FAIL** (−16.3 … +19.0) |
| G8 | clustered 95% CI excludes zero | **PASS** [+6.5, +91.5] | **FAIL** [−85.5, +80.8] |
| G9 | primary margin ≥ 25.0 | **PASS** (+49.0) | **FAIL** (−2.3) |
| G10 | season-long margin ≥ −25.0 | **PASS** (+35.8) | **PASS** (+16.2) |
| **G7** | **cross-format sign** | **FAIL — +49.0 vs −2.3** | |

Note on G5: legacy's *total* breaches fall (59 vs 61), but the gate is per-position as written and
**QB breaches rise 19 → 22**. Scored as written.

### The caveat that belongs next to G8, not in a footnote

G8 and G9 are separate pre-registered gates and both pass in the target format exactly as written.
But the interval's **lower bound is +6.5**, well below the 25-point economic threshold G9 tests.
The honest statement is:

> The six-season evidence **rules out zero**. It does **not** rule out an effect smaller than the
> one this project defined as economically meaningful.

Both are true simultaneously, and the brief's instruction — "Do not choose A simply because the CI
barely excludes zero… use the pre-registered economic and statistical criteria together" — is
aimed precisely here.

### G7, stated without argument

**G7 fails.** D86's selection rule is "ship the lowest-numbered arm clearing **every** gate," so
**O1 does not ship**, and no amount of reading around that changes it.

The mechanistic reading is offered as *explanation, not exemption*: the legacy format has no K or
DEF slot, so O1's mechanism cannot fire there, and the null is what its own theory predicts. But
**G7 as written cannot distinguish "null because the mechanism has nothing to act on" from "a
target-format artifact"** — which is a real limitation of the gate, not a licence to override it.
Revisiting G7's specification would be a separate, pre-registered decision; making it here, after
seeing the result, is exactly the post-hoc move this project forbids.

---

## 11. Mechanism validation (Phase 8)

| target format | O0 (Y1) | O1-FULL | Δ |
|---|---|---|---|
| weekly, no foresight | 1902.7 | 1951.7 | **+49.0** |
| season-long | 1915.4 | 1951.2 | +35.8 |
| **total roster points** | 2597.8 | 2581.5 | **−16.3** |
| bench contribution | 385.2 | 403.7 | **+18.5** |
| missed player-weeks | 50.4 | 55.6 | **+5.2** |

**The D88 mechanism survives 2020 intact**: O1 accumulates *fewer* raw roster points, converts more
of them into lineup points on both metrics, draws more from the bench, and drafts players who miss
*more* time — and wins anyway. That is what real depth buys.

### Byes vs injuries — the decomposition D88 did not do

`missed_player_weeks` conflates a scheduled bye with an injury. Splitting them using each season's
own schedule (a bye = a week the player's team had no regular-season game):

| target format | byes | non-bye absences | unresolved | total |
|---|---|---|---|---|
| O0 (Y1) | 15.8 | 31.8 | 2.8 | 50.4 |
| **O1-FULL** | **15.9** | **37.5** | 2.3 | 55.6 |
| Δ | **+0.0** | **+5.8** | — | +5.2 |

(The "unresolved" column is players with no weekly rows at all in the season — one 2025 rookie who
never played, carried as 17 unattributable player-weeks rather than silently labelled a bye.)

**Byes are identical between the arms, and essentially fixed at one per rostered player.** O1 does
not and cannot dodge byes — every player has exactly one. **The entire availability difference is
non-bye absence (+5.8).** O1 knowingly accepts more injury exposure in exchange for depth.

Simultaneous-unavailability exposure makes the same point from the other side:

| arm | worst single week | median week |
|---|---|---|
| O0 (Y1) | 6.43 of 16 unavailable | 2.72 |
| **O1-FULL** | **7.20 of 16** | 3.07 |

**O1 carries a worse worst-week than Y1 and still scores +49.0.** The gain is not risk avoidance;
it is having a startable body when the hole appears.

---

## 12. Positional behaviour and K/DST (Phases 9, 14)

Target format, mean over 60 drafts:

| arm | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nQB | nRB | nWR | nTE | **nK** | nDST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 (Y1) | 2.83 | 4.15 | 1.58 | 6.70 | 7.77 | 9.97 | 1.75 | 2.10 | 4.68 | 1.93 | **3.45** | 2.08 |
| **O1-FULL** | 2.83 | 4.17 | 1.58 | 6.87 | 7.62 | 10.25 | 1.52 | **2.60** | 4.83 | **2.67** | **2.52** | 1.87 |

**Early-round timing is untouched** — first QB, first RB and first WR are identical to two
decimals across 120 drafts. Every behavioural difference is in the endgame, and **roster legality
is perfect in both arms: 0 unfilled mandatory slots in all 220 analysed drafts, both formats.**

Legacy 2QB, for contrast — and this is the whole of §10's G7 story in one table:

| arm | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nQB | nRB | nWR | nTE | **nK** | **nDST** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 (Y1) | 1.88 | 4.96 | 2.52 | 5.90 | — | — | 3.32 | 3.32 | 7.68 | 2.68 | **0.00** | **0.00** |
| O1-FULL | 1.86 | 5.56 | 2.52 | 5.88 | — | — | 3.50 | 3.30 | 7.22 | 2.98 | **0.00** | **0.00** |

**Zero kickers and zero defenses, in both arms, in all 100 legacy drafts** — that format's lineup
has no K or DEF slot, so its positional capacities are literally `K: 0, DST: 0`. O1's principal
mechanism cannot fire there at all. The one movement is TE depth (2.68 → 2.98) and a slightly
later first RB.

### Per-season K/DST — and why 2020's channel differs

| season | Y1 nK | O1 nK | Y1 nDST | O1 nDST | Y1 nRB | O1 nRB | Y1 nTE | O1 nTE | primary Δ |
|---|---|---|---|---|---|---|---|---|---|
| **2020** | **2.00** | **2.00** | 2.00 | **1.20** | 2.00 | **3.00** | 2.00 | 2.00 | +41.3 |
| 2021 | 2.80 | 2.40 | 2.30 | 2.00 | 2.10 | 2.10 | 2.00 | 3.00 | +57.3 |
| 2022 | 3.90 | 2.00 | 2.20 | 2.00 | 2.00 | 3.00 | 1.80 | 3.00 | −10.4 |
| 2023 | 4.50 | 2.80 | 2.00 | 2.00 | 2.50 | 3.20 | 2.00 | 3.00 | +21.0 |
| 2024 | 3.50 | 2.90 | 2.00 | 2.00 | 2.00 | 2.30 | 1.80 | 2.10 | +90.8 |
| 2025 | 4.00 | 3.00 | 2.00 | 2.00 | 2.00 | 2.00 | 2.00 | 2.90 | +94.0 |

**O1 never drafts more kickers than Y1 in any season** — the mechanism is directionally consistent
in all six. But **2020 is the one season where Y1 was already not hoarding kickers** (2.00, against
a 3.45 six-season mean), so there was nothing for O1 to recover there. In 2020 the gain came
through **DST (2.00 → 1.20) and RB depth (2.00 → 3.00)** instead.

That is the honest reading, and it is a qualification rather than a confirmation: the *general*
mechanism — stop over-buying positions with one startable slot, spend the picks on flex-eligible
depth — holds in 2020, but **the specific K channel D86/D88 emphasised does not fire there**, and
2020 still returns +41.3. Per the brief, the mechanism is not forced to fit: what 2020 shows is
that the effect does not *depend* on kicker hoarding being present.

**Do not read "later K/DST is automatically better" into this.** O1 does not take its first kicker
meaningfully later (7.77 → 7.62); it takes *fewer*. The realized-utility test, not the timing, is
what G8/G9 measure.

---

## 13. RB diagnostic (Phase 10) — diagnostic only

Elite-RB cell (2026 preseason ECR ≤ 24, n = 7) perturbed in memory via `projections_override`,
which rebuilds every projection-derived quantity so the arm stays internally consistent. **No
realized outcome is an input; no production projection was changed; no RB model was fitted.**

| Δ applied | Y1 pick #1 | O1 pick #1 | Y1 #20 | O1 #20 | Y1 #21 | O1 #21 |
|---|---|---|---|---|---|---|
| +0 | St. Brown (WR) | St. Brown (WR) | Allen (QB) | Allen (QB) | McBride (TE) | McBride (TE) |
| +25 | St. Brown | St. Brown | Allen | Allen | McBride | McBride |
| +50 | St. Brown | St. Brown | Allen | Allen | McBride | McBride |
| **+75** | **McCaffrey (RB)** | **McCaffrey (RB)** | Allen | Allen | McBride | McBride |
| +100 | McCaffrey | McCaffrey | Allen | Allen | McBride | McBride |

**D88's conclusion is CONFIRMED, not refuted. O1 and Y1 have identical elite-RB sensitivity**:
both require **+75** before taking an RB at #1, and neither changes at #20 or #21 at any
perturbation up to +100. The measured historical bias is ≈ **+47.7**, short of the +75 either
engine needs.

**O1 provides no protection whatsoever against the elite-RB under-projection.** That hypothesis is
closed. (For contrast, D85's arm C lowered the #1 threshold to +50; O1 does not.)

---

## 14. 2026 board — #1 / #20 / #21 (Phase 11)

| pick | Y1 (O0) | O1-FULL |
|---|---|---|
| **#1** | Amon-Ra St. Brown (WR), score 568.9, msv 278.7, vorp 121.5 | **identical player**, score 526.3, msv 243.8, vorp 121.5 |
| **#20** | Josh Allen (QB), score 294.8, msv 329.4, vorp 62.9 | **identical player**, score 261.4, msv 284.9, vorp 62.9 |
| **#21** | Trey McBride (TE), score 319.8, msv 197.8, vorp 65.2 | **identical player**, score 294.8, msv 173.0, vorp 65.2 |

**O1 makes the same three decisions.** It lowers every score — its MSV is an availability-discounted
expectation — but preserves the ordering, and `vorp` is identical by construction because only the
MSV half changed. Top-5 alternatives are the same players in the same order at #1 and #21; the only
change anywhere in the top 5 is at #20, where O1's fifth-ranked alternative is Drake Maye (QB, 197.9)
in place of Zay Flowers (WR, 224.4) — a fifth-place reshuffle that changes no pick.

Elite RBs (McCaffrey 5th at #1 in both), WRs, QBs, TEs and rookies at the top of the board are
**unaffected**. Final rosters from slot 1:

| arm | WR | QB | TE | RB | **K** | DST |
|---|---|---|---|---|---|---|
| Y1 | 5 | 1 | 2 | 2 | **4** | 2 |
| **O1-FULL** | 5 | 1 | **3** | **3** | **2** | 2 |

**First divergence is round 11.** Y1 drafts four kickers; O1 drafts two and spends the freed picks
on Zach Charbonnet (RB) and Hunter Henry (TE).

---

## 15. Computational cost (Phase 17)

| arm | s/pick | s/draft | vs Y1 |
|---|---|---|---|
| O0 (Y1) | **0.018** | 0.3 | 1.0× |
| O1-FULL | **3.353** | 53.6 | **186×** |

240 drafts run (220 analysed), ≈ 1.9 h wall clock for the main experiment. A single live
recommendation costs ≈ 3.4 s, immaterial during a real draft — the 186× multiplier matters only
for batch experiments, and it is the reason a whole format costs about an hour rather than a day.

---

## 16. Ship / do not ship (Phase 18)

> **DO NOT SHIP. Y1 remains production.** No production file was changed, and no production diff
> was prepared.

D86's selection rule is *"ship the lowest-numbered arm clearing **every** gate."* **O1 fails G7.**
That is dispositive on its own, and it is a pre-registered rule applied as written, not a judgement
made after seeing the numbers.

What changed since D88 is which gate blocks:

| | D88 | **D89** |
|---|---|---|
| blocking gate, target format | **G8** (CI included zero) | *none* — all nine in-format gates pass |
| blocking gate, overall | G8 + G7 | **G7 alone** |
| nature of the obstruction | **statistical resolution** | **cross-format generalisation** |

---

## 17. Final O1 verdict (Phase 13)

### **B — PROMISING BUT UNRESOLVED**, with the obstruction relocated, not removed.

Against the four options, applied literally:

* **Not A.** A requires the existing gates to pass. **G7 does not.** A also requires the evidence
  to be sufficient, and while the CI now excludes zero, its lower bound (**+6.5**) sits below the
  economic threshold (**25.0**) the project itself set — so "economically meaningful" is
  established for the *point estimate*, not for the *interval*. The brief's warning — "do not
  choose A simply because the CI barely excludes zero" — applies exactly.
* **Not C.** The effect did not collapse, reverse or destabilise. Across three independent
  enlargements of the sample it reads **+52.9 → +50.5 → +49.0**, it improves both metrics in every
  phase, it survives leave-one-season-out at six seasons, it passes **nine of nine** in-format
  gates, and it costs nothing in roster legality (0 unfilled slots in 220 analysed drafts). None of
  C's conditions is met.
* **Not D.** D requires another required format to be **materially harmed**. Legacy is **−2.3 on a
  ~2,200-point base (−0.1%)** with a CI of [−85.5, +80.8] and **three secondary metrics moving
  positive** (+25.1, +16.2, +51.1). That is a null, not harm — and a null is what O1's own
  mechanism predicts in a format with no K and no DEF slot.
* **B, therefore** — but B's stated condition ("evidence still cannot distinguish it from noise")
  is now only half true, and saying so precisely is the point of this phase. **In the target
  format the evidence does now distinguish the effect from noise.** What it cannot do is show the
  effect generalises beyond the one format whose lineup contains the slots the mechanism acts on.

**The honest one-line summary:** D89 answered the question D88 posed, and the answer was yes — and
then a *different* pre-registered gate turned out to be the binding one.

---

## 18. Answers to the seven final questions

**1. Did 2020 provide enough additional information to resolve O1?**

**Yes, in the target format, and by a wider margin than D88 forecast.** The CI moved from
[−5.5, +106.6] to **[+6.5, +91.5]**; the MDE fell **56.0 → 42.5** against an effect of **+49.0**
(effect/MDE **1.15**). D88 projected 47.3 assuming the between-season SD held at 45.1; it fell to
40.5 because 2020's cluster (+41.3) landed near the mean rather than in a tail — a coin flip that
**R2 registered in advance could have gone the other way.**

Two qualifications that belong in the same breath: the interval's lower bound (+6.5) does **not**
exclude an economically trivial effect, and **2020 could not be added to the legacy format at
all**, so "six seasons" is true of the target format only.

**2. Is the approximately +50-point O1 effect stable?**

**Yes, in the target format.** +52.9 (4 slots, 5 seasons) → +50.5 (10 slots, 5 seasons) → **+49.0**
(10 slots, 6 seasons). The D88 → D89 movement is **−1.5** against R3's pre-registered stability
threshold of ±16.5. Season-long improves throughout (+34.5 → +39.9 → +35.8). 5 of 6 seasons
improve; leave-one-season-out spans +40.0 … +60.9. **Across formats it is not stable** — that is
G7, and it is question 3's answer.

**3. Does O1 outperform Y1 enough to justify shipping?**

**No — and the reason is generalisation, not size.** In the target format it clears every
in-format gate including the economic one. But it fails **G7**, and D86's rule is to ship only an
arm clearing every gate. A secondary reservation stands on its own: the CI's lower bound is +6.5,
so the data is consistent with a real but economically marginal effect.

**4. Does O1 solve or mitigate the elite-RB problem?**

**No. Confirmed, not refuted.** O1 and Y1 have **identical** elite-RB sensitivity: both need
**+75** on the elite-RB cell before taking an RB at #1, and neither changes at #20 or #21 at any
perturbation to +100. The measured historical bias is ≈ **+47.7**, short of the +75 either engine
requires. Weekly roster utility offers **no** protection against elite-RB under-projection. The
hypothesis is closed.

**5. Does O1 improve the actual 2026 decision behaviour at #1/#20/#21?**

**No — it makes the identical three picks.** St. Brown (WR), Allen (QB), McBride (TE). O1 lowers
every score (its MSV is availability-discounted: St. Brown 278.7 → 243.8) but preserves the
ordering; `vorp` is identical by construction. The only top-5 movement anywhere is at #20, where
O1's *fifth* alternative is Drake Maye rather than Zay Flowers — which changes no pick. **O1's
entire 2026 effect is the endgame**: first divergence round 11, four kickers → two, the freed picks
going to Charbonnet (RB) and Henry (TE).

**6. If O1 does not ship, is the remaining problem objective, projection, data, benchmark, or a
combination?**

**Primarily benchmark/instrument resolution, with a second-order data problem now measured.**

* **Objective — largely solved, and this is the phase that establishes it.** O1 is better
  specified than Y1 and now beats it at conventional significance in the target format, through
  the mechanism it claimed.
* **Benchmark/instrument — still binding, and now binding in a new place.** Resolution is no
  longer the issue in the target format; **cross-format evidence** is. There are only two shipped
  formats, one of which structurally cannot exercise the mechanism, so G7 is currently a
  coin-flip-free *fail* for any K/DST-driven improvement. That is a property of the instrument.
* **Data — newly quantified.** The legacy format has **no preseason board before 2021** (`dsf`
  begins 2020-10-16), which caps legacy at five clusters permanently and is the direct cause of
  the asymmetry above.
* **Projection — unchanged and still real** (elite-RB ≈ +47.7 under-projection), but it is
  **orthogonal**: question 4 shows the objective cannot reach it.

**7. The single highest-value next research direction**

> **Establish whether G7 is testing what it was written to test — by adding a third league format
> that does contain K/DEF slots, before any further objective work.**

Not another objective, not more seasons, not a re-specification of O1. The evidence now points at
exactly one ambiguity: **G7 cannot presently distinguish "O1 is a target-format artifact" from "the
legacy format has no K or DEF slot for O1's mechanism to act on."** Those two readings imply
opposite decisions on a candidate that otherwise passes nine of nine gates, and nothing in the
current benchmark can separate them.

A third registered format with K and DEF slots but a genuinely different shape — 12-team, or a
different flex structure — converts G7 from an untestable constraint into a real test. If O1
reproduces there, G7's failure is diagnosed as a structural property of the legacy lineup and O1
becomes shippable under the *existing* rules with no gate relaxed. If O1 does **not** reproduce
there, G7 was right and O1 closes. **Either outcome is decisive, which is what makes it the highest
value.** It also costs a fraction of another objective search: the harness, metrics and gates all
exist, and D89's own cost table says a format is ~1 hour of compute.

*Explicitly not recommended, per the brief's stopping rule:* inventing O2, re-weighting O1, adding
waiver data or risk terms, reopening projections (D79–D83), shortlists (D87), more draft slots
(D88 proved they cannot help), or relaxing G7 because the target result is attractive.

---

## 19. What this phase changes about the stopping rule

The brief's stopping rule anticipated that six seasons might *fail* to resolve a ~50-point effect,
and directed that the next question then be "what new instrument would let us measure smaller
effects?" rather than "how do we make another objective pass."

**Six seasons did resolve it in the target format**, so that branch does not fire as written. But
its *spirit* is exactly right and now points one step sideways: the binding limitation was never
the objective and is no longer the seasonal sample — **it is that the benchmark contains only one
format in which the mechanism can act.** §18.7 is the instrument question, asked about
generalisation instead of resolution.

---

## 20. Defects found in this phase

| # | defect | status |
|---|---|---|
| 1 | 2020's target preseason board is under `redraft-offense`, not `redraft-overall`; the default returned an empty board and the opponents would have drafted alphabetically | **Fixed** before the run — `preseason_page_type`, 5 tests. 2021–2026 unchanged, asserted. |
| 2 | The legacy format has no 2020 preseason board at all (`dsf` begins 2020-10-16); Phase 1 validated only the target series and missed it | **Cell excluded**, per-format `EXCLUDED_SEASONS` with the measured reason, recorded before any legacy 2020 outcome was seen. |
| 3 | An empty market board degrades **silently** to alphabetical opponents — legal rosters, finite metrics, a fabricated observation that looks real | **Guarded** — `assert_usable_market_board` / `EmptyMarketBoardError`, 6 regression tests. |
| 4 | `compute_league_starters` breaks exact FLEX ties by `set` iteration order, so `bench_contribution` is `PYTHONHASHSEED`-dependent (2 cells of 200, ≈ 4–6 pts) | **Documented, not fixed** — the fix is in `league/`, which D89 must not touch. 3 characterization tests pin the invariant (lineup totals cannot move). **Future item.** |
| 5 | D88's slot-sensitivity table computed `SE = sqrt(SD² + within²/n)/√k`, adding within-variance to an SD that already contained it — inconsistent with its own published CI half-width | **Corrected here** (§6). D88's headline conclusion is unaffected and in fact strengthened: the true 5-season floor was **51.1**, still above the +50.5 effect. |
| 6 | D86's oracle **unit tests** seeded `ecr_type='do'`/`dynasty-overall` for a `format="redraft"` league, which resolves to `ro`/`redraft-overall` — so their `market_rank` was empty and the nine opponents drafted **alphabetically** | **Fixed** — fixture now seeds the series the league resolves to; 3 regression tests pin it. Found by defect 3's guard within minutes of it existing. **D86's published oracle numbers are unaffected**: they ran against the real database and a real preseason board. Only this module's fixture was wrong. |

Defect 6 is worth noting as evidence about defect 3's guard rather than as a result: the guard was
added to stop D89 fabricating a season, and the first thing it did was expose a latent fixture bug
in a different phase's tests that had been silently passing.

---

## 21. Plain-English trust assessment

**Nothing about Alpha's advice at the top of a 2026 draft changes.** O1 makes the identical picks
at #1, #20 and #21, and identical first-QB, first-RB and first-WR rounds across 120 historical
drafts. If you are looking for a different opening, this is not it, and three phases have now said
so.

What O1 changes is the **endgame**, and it changes it in the direction that makes economic sense:
Y1 drafts **3.45 kickers per draft**, O1 drafts **2.52**, and the freed picks go to tight-end and
running-back depth. On the 2026 board that is four kickers versus two. Over 120 target-format
drafts spanning six seasons, that behaviour is worth about **+49 realized weekly points**, and as
of this phase that number is — for the first time in this research line — **statistically
distinguishable from zero**.

Three honest limits sit next to that:

1. **It is one format.** The other shipped format has no kicker or defense slot, so the mechanism
   cannot act there, and it returns a null. The gate that exists to catch format-specific artifacts
   cannot tell that apart from a genuine artifact — so the pre-registered rule says ship nothing,
   and nothing ships.
2. **"Better than zero" is not "better than 25."** The interval runs from +6.5 to +91.5. The best
   estimate is comfortably worth having; the evidence is also consistent with a gain too small to
   care about.
3. **It does not fix the known projection problems.** Elite RBs are still under-projected by
   ≈ 47.7 points and O1 does not notice — it needs +75, exactly as Y1 does.

So the practical advice is unchanged from D86, and is now measured across six seasons and 220
drafts: **take the kicker you need, then stop.** You do not need this code change to act on it.

And the finding worth carrying forward: after five phases and 580 drafts, **the objective is no
longer the weak link.** O1 is better specified than Y1 and now measurably better in the format this
product targets. What blocks it is that the benchmark contains exactly one league in which its
mechanism can do anything — which is a statement about the ruler, not the idea.
