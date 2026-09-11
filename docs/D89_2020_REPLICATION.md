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

### 2.4 Verdict

**2020 is comparable and is included. 2019 is not comparable and is excluded** — 174 board players
and **0% market coverage**, so there is no preseason board for the fair-market opponent to draft
against and the implied demand degenerates (K 3.3, DST 3.0). The exclusion is recorded in code
(`replication_design.EXCLUDED_SEASONS`) with that measured reason, not as a preference.

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
| shared cells compared (5 seasons × 10 slots × 2 arms × 2 formats) | 100 target + 100 legacy |
| max abs deviation across 7 recorded metrics | **0.000000000000** |
| drafted-roster mismatches | **0** |
| target 2021–2025 margin | **+50.5, CI [−5.5, +106.6]** — D88's published number to the decimal |

**Prediction R1 holds: bit-identical, not merely "within tolerance."** The `preseason_page_type`
change is a proven no-op for 2021–2025, so 2020 is being added to an unchanged experiment rather
than to a re-specified one.

---

## 5. Sample size (Phase 3)

| | target 1QB | legacy 2QB |
|---|---|---|
| paired draft observations | **60** | **60** |
| season clusters | **6** | **6** |
| slots per season | 10 | 10 |
| drafts run (both arms) | 120 | 120 |

**240 drafts.** D86/D87 ran 40 per format, D88 100, D89 120.

---

## 6. Power / MDE (Phase 5) — target format

| quantity | D88 (5 seasons) | **D89 (6 seasons)** |
|---|---|---|
| SD of season means | 45.1 | **40.5** |
| within-season SD (across 10 slots) | 55.7 | 57.9 |
| irreducible between-season SD | 40.2 | **36.2** |
| clustered SE | 20.2 | **16.5** |
| `t(df = n−1)` | 2.776 | **2.571** |
| **MDE** | **56.0** | **42.5** |
| observed effect | +50.5 | **+49.0** |
| effect / MDE | 0.90 | **1.15** |
| MDE floor at infinite slots | 56.0 | **38.0** |

**The MDE fell further than D88 forecast, and for a reason D88 could not know in advance.** D88
projected MDE ≈ 47.3 at six seasons *holding the between-season SD at 45.1*. The actual SD fell to
**40.5**, because 2020's cluster mean (**+41.3**) landed close to the six-season mean rather than
in a tail. So the improvement has two sources:

| step | MDE |
|---|---|
| D88, 5 seasons, SD 45.1 | 56.0 |
| + one cluster (D88's forecast, SD held at 45.1) | 47.3 |
| + the SD 2020 actually produced (40.5) | **42.5** |

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

*Pending — the legacy block is still running.*

---

## 10. Gate results (Phase 7) — target 1QB

D86's gates, which are D84's, imported unchanged. **D88's table reported seven of them; G1, G4 and
G5 are computable from the recorded rosters and the league config, so they are computed here rather
than omitted.** No gate was added, relaxed, strengthened or re-thresholded.

| gate | threshold | measured | verdict |
|---|---|---|---|
| G1 | no dedicated-slot position zeroed more often than control | 0 vs 0 at every position | **PASS** |
| G2 | roster infeasibility ≤ control | 0 vs 0 unfilled slots in 120 drafts | **PASS** |
| G3 | primary worse in ≤ 1 season | 1/6 (2022) | **PASS** |
| G4 | no position drafted > 2 rounds earlier | max +0.15 rd (K) | **PASS** |
| G5 | no increase in positional-capacity breaches | **31 vs 53** — O1 breaches *fewer* | **PASS** |
| G6 | leave-one-season-out margin stays positive | +40.0 … +60.9, all positive | **PASS** |
| G8 | clustered 95% CI excludes zero | **[+6.5, +91.5]** | **PASS** |
| G9 | primary margin ≥ 25.0 | **+49.0** | **PASS** |
| G10 | season-long margin ≥ −25.0 | **+35.8** | **PASS** |
| G7 | cross-format sign | *pending legacy* | — |

### The caveat that belongs next to G8, not in a footnote

G8 and G9 are separate pre-registered gates and both pass exactly as written. But the interval's
**lower bound is +6.5**, well below the 25-point economic threshold G9 tests. So the honest
statement is:

> The six-season evidence **rules out zero**. It does **not** rule out an effect smaller than the
> one this project defined as economically meaningful.

Both facts are true simultaneously, and the brief's instruction — "Do not choose A simply because
the CI barely excludes zero… use the pre-registered economic and statistical criteria together" —
is aimed precisely at this situation.

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

| arm | byes | non-bye absences | unresolved | total |
|---|---|---|---|---|
| O0 (Y1) | 15.8 | 31.8 | 2.8 | 50.4 |
| **O1-FULL** | **15.9** | **37.5** | 2.3 | 55.6 |
| Δ | **+0.0** | **+5.8** | — | +5.2 |

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
is perfect in both arms: 0 unfilled mandatory slots in all 240 drafts.**

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
| O0 (Y1) | **0.020** | 0.3 | 1.0× |
| O1-FULL | **3.634** | 58.1 | **182×** |

240 drafts. A single live recommendation costs ≈ 3.6 s, immaterial during a real draft.

---

*Sections 16–21 — legacy results, G7, ship decision and verdict — follow once the legacy block
completes.*
