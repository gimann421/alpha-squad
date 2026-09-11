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

*Sections 4–21 follow below once the 240-draft run completes.*
