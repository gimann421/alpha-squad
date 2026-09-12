# D90 — Does O1 generalise to a format where its mechanism can operate?

*Not a new objective, not a tuning phase, not a new gate. O1 is run exactly as D89 ran it; the
only thing that changes is the league config. `models/` and `league/` are **byte-identical to
Y1** throughout.*

---

## 1. Repository / baseline status (Phase 0)

| check | result |
|---|---|
| working tree at start | clean |
| HEAD at start | `fa57332` — matches the brief |
| `src/alpha_squad/models/` + `src/alpha_squad/league/` vs Y1 baseline | **byte-identical — empty diff** |
| D86–D89 artifacts | `otiers2.json`, `d87arms.json`, `equiv.json`, `d88.json`, `d89.json` all present |
| D85–D89 reports | all five present in `docs/` |
| database | intact, 231 MB |
| **D89 control reproduction** | **max \|Δ\| 0.000000000000** across 10 cells, both formats, both arms, including the 2020 cell; **0 roster mismatches** |

No production behaviour was modified and no production diff was prepared.

### One mismatch with the brief's premise, reported rather than assumed away

The brief states the repository is consolidated and main is current. **It is not.** `origin/main`
is at `b9c389d` (PR #16, which merged **D85**); the sixteen commits from **D86 through D89 exist
only on this branch**. Verified by file: `weekly_objective.py`, `replication_design.py`, and the
D87/D88/D89 reports are all branch-only.

Production integrity is unaffected — main is a strict ancestor, and nothing on the branch touches
`models/` or `league/` — so this is bookkeeping rather than an integrity failure, and D90 proceeds.
But D86–D89 are not on main, and that PR is worth merging.

---

## 2. Third format selection (Phase 1)

### 2.1 The candidate set is closed, not a matter of taste

`market/series.py` derives the consensus board from exactly two booleans — `is_dynasty` ×
`is_superflex`. This deployment therefore has **exactly four** possible market series, and two are
already spoken for. There is no discretion about *which formats exist*; only about which of the
two remaining ones to use.

### 2.2 The measurements that decided it, taken before any O1 result

| series | format | usable historical seasons | **K rows** | **DST rows** | status |
|---|---|---|---|---|---|
| `ro` | redraft 1QB | 6 (2020–2025) | 1,692 | 1,473 | `target_league` |
| `dsf` | dynasty superflex | 5 (2021–2025) | **0** | **0** | `legacy_2qb_dynasty` |
| `rsf` | redraft superflex | 5 (2021–2025) | **0** | **0** | candidate |
| **`do`** | **dynasty 1QB** | **6 (2020–2025)** | **1,533** | **1,494** | **SELECTED** |

Applying the brief's pre-specified tie-break in order:

1. **Most complete historical seasons** — `do` has **6**, `rsf` has **5**. The `rsf` series'
   earliest scrape of any kind is 2021-01-01, so it has no 2020 board under any `page_type`.
   **`do` wins outright on criterion 1**, and the rule stops there.
2. **Most complete draft boards** — not reached, but it points the same way.
3. **Closest structural match while remaining distinct** — also satisfied, see §2.4.

### 2.3 A finding that deepens D89's diagnosis

**Both superflex boards carry zero kickers and zero defenses.** FantasyPros' superflex ("OP") pages
rank offensive players only. So the legacy format could not test O1's mechanism for **two
independent reasons**, not the one D89 identified:

* its **lineup** has no K and no DEF slot (positional capacity literally `K: 0, DST: 0`, and both
  arms drafted zero of each in all 100 D89 drafts); **and**
* its **board** has no K and no DST players to rank in the first place.

This also disqualifies `rsf` on the brief's criterion 5 ("valid draft board") independently of the
season count: a lineup that must start a K and a DEF cannot be drafted against a board containing
neither.

### 2.4 The selected format, and the discretion deliberately removed

`dynasty_1qb` changes **exactly one field** from `target_league` — `format: redraft → dynasty`.
Lineup, teams, scoring and roster are identical (QB1/RB2/WR2/TE1/FLEX2/K1/DEF1, 10 starters,
bench 6, roster_size 16; `10 + 6 = 16` as the shipped-config test requires). Holding the lineup
fixed removes the discretion that could otherwise be used to shop for a favourable format.

**The scope limit this creates, recorded as prediction T6 before the run:** `is_dynasty` is
consumed by `market/series.py` **and by nothing else in the engine**. So relative to the target
format, D90 varies the **consensus board and everything downstream of it** — opponent draft order,
market ranks feeding survival / opportunity cost / daVORP, consumption demand, and where K and DST
sit (best K at overall rank 185–251 here vs 174–190 on `ro`). It does **not** vary the lineup
shape. **D90 is a board-generalisation test, not a lineup-generalisation test**, and its conclusion
must be read at that width.

---

## 3. Experiment design (Phases 2–4)

Committed as `431e424` **before any D90 result was examined**.

| | D89 | **D90** |
|---|---|---|
| league format | target 1QB + legacy 2QB | **`dynasty_1qb`** |
| seasons | 2020–2025 | 2020–2025 (unchanged) |
| slots | 10 | 10 (unchanged) |
| candidate set | full board | **full board, no shortlist** |
| objective | `E[weekly MSV] + 1.0·daVORP` | **unchanged** |
| control / opponent / metrics / gates | — | **unchanged** |
| randomization | CRN on `player_id`, deterministic, no seed | unchanged |

`tests/unit/test_replication_design.py` asserts mechanically that **D90 differs from D89 in
`phase` and `formats` and in nothing else**. The runner's complete diff from `run_d89.py` is the
league config plus threading the resolved `ecr_type` — which is a provable no-op, since
`load_season_static` resolves exactly that value when the argument is omitted.

**Sample:** 6 season clusters × 10 slots = **60 paired observations**, **120 drafts**.

---

## 4. Validation and controls (Phase 5)

| item | result |
|---|---|
| D89 shared cells reproduce | **bit-identical** (§1) |
| Y1 and O1 control values | both produced, both arms, all 6 seasons |
| roster legality | **16 players in all 120 drafts** |
| unfilled mandatory slots | **0 in all 120 drafts, both arms** |
| board non-empty and valid | 545 market_rank entries; **35 ranked K, 32 ranked DST** |
| opponent behaviour | `MARKET_CONSENSUS_ROSTER_AWARE`, unchanged |
| determinism within process | repeat draft identical, both arms |
| `PYTHONHASHSEED` sensitivity | seeds 0 and 4 give **identical values on every metric including `bench`** |
| board `page_type` per season | 2020 → `dynasty-offense`; 2021–2025 → `dynasty-overall` |

The 2020 board is published under `dynasty-offense`, the same relabelling D89 found for the target
format — resolved by `preseason_page_type`, not assumed. `dynasty_1qb` 2019 is excluded with its
measured reason (no July/August rows at all).

No defect was found that could alter the experiment, and nothing in `league/` or `models/` needed
to change.

---

## 5. Y1 vs O1 results (Phase 6)

| arm | weekly no-foresight — **primary** | weekly hindsight | season-long | total roster | bench | missed player-weeks | unfilled |
|---|---|---|---|---|---|---|---|
| O0 (Y1) | 2151.5 | 2344.5 | 2130.0 | 2889.1 | 486.7 | 49.3 | **0** |
| **O1-FULL** | **2172.3** | **2369.3** | **2143.0** | 2875.4 | 489.9 | 51.3 | **0** |
| **Δ** | **+20.8** | **+24.8** | **+13.1** | −13.7 | +3.3 | +2.0 | — |

**All three metrics move positive**, and the mechanism's signature from D88/D89 is present: fewer
raw roster points (−13.7) converted into more lineup points.

### Per season

| season | n | primary Δ | season-long Δ | weekly-hindsight Δ | winner |
|---|---|---|---|---|---|
| 2020 | 10 | **−46.2** | −55.7 | −71.6 | Y1 |
| 2021 | 10 | **−15.4** | +9.4 | +38.0 | Y1 |
| 2022 | 10 | +5.1 | −9.5 | −24.0 | O1 |
| 2023 | 10 | +31.4 | +16.7 | +66.6 | O1 |
| 2024 | 10 | +69.5 | +52.8 | +44.4 | O1 |
| 2025 | 10 | +80.2 | +64.8 | +95.2 | O1 |

**4 of 6 seasons improved.** Leave-one-season-out margins are **all positive** (+8.9 … +34.2).

### Power

| quantity | target (D89) | **dynasty_1qb (D90)** |
|---|---|---|
| SD of season means | 40.5 | 49.1 |
| within-season SD | 57.9 | 67.8 |
| between-season SD | 36.2 | 44.2 |
| clustered SE | 16.5 | 20.0 |
| **MDE** | **42.5** | **51.5** |
| observed effect | +49.0 | **+20.8** |
| effect / MDE | 1.15 | **0.40** |
| 95% CI | **[+6.5, +91.5]** | **[−30.8, +72.3]** |

**Against the project's 25-point economic threshold: the point estimate (+20.8) is below it, and
the interval's lower bound (−30.8) does not approach it.** The effect is positive and
same-signed with the target format, but it is **less than half the magnitude** and **not
statistically resolved**.

---

## 6. Mechanism results (Phase 7) — the part D90 exists to measure

| arm | 1st QB | 1st RB | 1st WR | 1st TE | 1st K | 1st DST | nQB | nRB | nWR | nTE | **nK** | **nDST** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| O0 (Y1) | 3.35 | 3.40 | 1.48 | 5.50 | 8.42 | 10.05 | 1.88 | 2.72 | 5.58 | 1.58 | **2.40** | **1.83** |
| **O1-FULL** | 3.30 | 3.52 | 1.42 | 5.65 | 8.60 | **10.97** | 1.97 | **2.97** | 5.47 | **1.97** | **2.00** | **1.63** |

> ### **The mechanism reproduces.**
> Kickers **2.40 → 2.00**, defenses **1.83 → 1.63**, with the freed picks going to RB depth
> (2.72 → 2.97) and TE depth (1.58 → 1.97). First DST moves a full round later (10.05 → 10.97).
> Early-round timing is essentially untouched — first QB, RB and WR all move by **< 0.1 rounds**.
> This is the same behavioural signature D88/D89 measured in the target format, in a format that
> shares no board with it.

Per season, and this is the sharpest version of the finding:

| season | Y1 nK | **O1 nK** | Y1 nDST | O1 nDST | Y1 nRB | O1 nRB | primary Δ |
|---|---|---|---|---|---|---|---|
| 2020 | 2.00 | **2.00** | 1.30 | 1.00 | 3.60 | 3.60 | −46.2 |
| 2021 | 2.00 | **2.00** | 1.70 | 2.00 | 2.30 | 2.30 | −15.4 |
| 2022 | 2.30 | **2.00** | 2.00 | 1.80 | 3.20 | 3.10 | +5.1 |
| 2023 | 2.70 | **2.00** | 2.00 | 1.00 | 2.60 | 3.10 | +31.4 |
| 2024 | 2.40 | **2.00** | 2.00 | 2.00 | 2.60 | 3.00 | +69.5 |
| 2025 | 3.00 | **2.00** | 2.00 | 2.00 | 2.00 | 2.70 | +80.2 |

**O1 draws exactly 2.00 kickers in every single season**, while Y1 ranges 2.00–3.00 and drifts
upward. O1 never drafts *more* kickers than Y1 in any season of any format now tested. The
positional cap for K in this league is 2, so O1 is drafting precisely to capacity and no further —
without any rule telling it to.

**Note the ordering, because it matters for §7:** the seasons where Y1 hoards kickers (2023–2025,
nK 2.40–3.00) are exactly the seasons where O1 wins (+31.4, +69.5, +80.2). The seasons where Y1
already drafts only 2 kickers (2020–2021) are the seasons O1 loses (−46.2, −15.4). The effect
tracks *how much there was to fix*, which is what the mechanism predicts — but see §7 before
reading that as confirmation.

---

## 7. An unregistered pattern, flagged rather than interpreted

The per-season effects in `dynasty_1qb` are **perfectly monotone increasing** across all six
seasons:

| format | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | ρ(season, effect) | monotone? |
|---|---|---|---|---|---|---|---|---|
| target_league | +41.3 | +57.3 | −10.4 | +21.0 | +90.8 | +94.0 | 0.54 | no |
| legacy_2qb_dynasty | — | −87.5 | +44.3 | +40.2 | +53.6 | −62.2 | 0.30 | no |
| **dynasty_1qb** | **−46.2** | **−15.4** | **+5.1** | **+31.4** | **+69.5** | **+80.2** | **1.00** | **yes** |

Split by era: `dynasty_1qb` early (2020–22) **−18.8** vs late (2023–25) **+60.4**, a gap of
**+79.2**. The target format shows the same direction, weaker: +29.4 → +68.6, gap +39.2.

**This was noticed after seeing results. It is not pre-registered, no inferential claim is made
about it, and no p-value is computed for it** — a perfectly ordered sequence is exactly the kind of
pattern that looks impressive precisely because it was selected for after the fact.

What it does mean, and this is not optional to state: **a mean of +20.8 assembled from a monotone
climb from −46 to +80 is not the same object as a stable +20.8.** The leave-one-season-out check
passes (all six margins positive) but cannot see this structure. It is recorded in §12 as the
phase's one documented new research question.

---

## 8. Cross-format comparison (Phase 8)

| format | K/DST slots | seasons | drafts | O1 effect | 95% CI | seasons improved | mechanism | resolved? |
|---|---|---|---|---|---|---|---|---|
| `target_league` | 2 / 2 | 6 | 120 | **+49.0** | [+6.5, +91.5] | 5/6 | **ACTIVE** | **yes** |
| `legacy_2qb_dynasty` | **0 / 0** | 5 | 100 | −2.3 | [−85.5, +80.8] | 3/5 | **NOT TESTABLE** | no |
| `dynasty_1qb` | 2 / 2 | 6 | 120 | **+20.8** | [−30.8, +72.3] | 4/6 | **ACTIVE** | no |

Against the brief's four candidate patterns, the observed result is **pattern 1 — target positive,
legacy null, third positive** — with one qualification the pattern list does not contain: **the
third format's effect is positive and same-signed but unresolved and less than half the target's.**

The clean structural fact is that **the mechanism is active in exactly the two formats where it is
structurally capable of being active, and absent in exactly the one where it is not.**

---

## 9. G7 analysis (Phase 9)

**G7 as written: FAIL.** The three formats do not share a sign (+49.0, −2.3, +20.8). D86's
selection rule is "ship the arm clearing **every** gate", so **O1 does not ship**, and this phase
does not revisit that.

### Does the legacy null still justify the failure?

The brief asks to distinguish **(A)** a true cross-format failure from **(B)** structural
non-identifiability. The evidence now separates them more than D89 could:

**For B (structural non-identifiability):**
* Legacy cannot express the mechanism for two independent reasons — no K/DEF slot **and** zero
  K/DST on its board. It is not a weak test; it is **not a test at all** of this mechanism.
* In the one newly-added format where the mechanism *can* operate, it **does** operate: kickers
  2.40 → 2.00, defenses 1.83 → 1.63, RB and TE depth up, early rounds untouched.
* The effect in that format is **positive and same-signed** with the target format, on a board
  that shares no rows with it.
* Among the two formats where the mechanism is structurally testable, the sign is consistent.

**For A (genuine weakness):**
* The third format's effect is **+20.8, less than half** the target's +49.0, **below** the 25-point
  economic threshold, and its CI **spans zero**.
* It is **negative in two of six seasons**, so G3 fails there on its own terms.
* The entire positive result is carried by the second half of the sample (§7).

**Conclusion, stated as a judgement and not as arithmetic:** the evidence favours **B over A**, but
it does **not** establish B. D89's G7 failure is now substantially better explained as a format
that cannot test the mechanism than as a defect in O1 — yet the format that *can* test it produced
an effect too small and too unstable for this benchmark to resolve.

**G7 is NOT satisfied, and is not redefined by this phase.** The diagnostic split in §8 ("same sign
among the two structurally testable formats") is reported as a diagnostic. It is not a gate, it was
not pre-registered as one, and converting it into one after seeing the result is precisely the
post-hoc move prediction T5 was written to forbid. If G7's text should distinguish "format lacks
the mechanism" from "candidate fails to generalise, that is a deliberate specification change to be
pre-registered **before** the next experiment — not a conclusion of this one.

---

## 10. 2026 board — #1 / #20 / #21 (Phase 10), `dynasty_1qb`

| pick | Y1 (O0) | O1-FULL |
|---|---|---|
| **#1** | Amon-Ra St. Brown (WR), score 550.1, msv 278.7, vorp 121.5 | **identical player**, score 507.6, msv 243.8, vorp 121.5 |
| **#20** | Christian McCaffrey (RB), score 346.6, msv 276.7, vorp 120.1 | **identical player**, score 309.2, msv 233.8, vorp 120.1 |
| **#21** | Josh Allen (QB), score 415.0, msv 329.4, vorp 62.9 | **identical player**, score 371.6, msv 284.9, vorp 62.9 |

**O1 makes the same three decisions**, exactly as in the target format. It lowers every score
(availability-discounted MSV) while preserving the ordering; `vorp` is identical by construction.
Top-5 alternatives are the same players in the same order at all three picks, with one swap at #20
(A.J. Brown vs George Pickens trade places at 4th/5th, changing no pick).

By position: **elite RB** — McCaffrey is #1 on the RB board and taken at #20 in both arms;
**WR** — St. Brown, Smith-Njigba, Nacua, Chase, London occupy the top 5 in both; **QB** — Allen
first at round 3 in both; **TE** — first TE round 9 (Y1) vs 10 (O1); **rookies** — unaffected at
the top of the board; **K** — first at round 8 in both, but Y1 takes **3** and O1 takes **2**;
**DST** — round 10 (Y1) vs 11 (O1), 2 each.

Final rosters from slot 1:

| arm | WR | RB | QB | TE | **K** | DST |
|---|---|---|---|---|---|---|
| Y1 | 4 | 3 | 2 | 2 | **3** | 2 |
| **O1-FULL** | **5** | 3 | 2 | 2 | **2** | 2 |

The single difference is Y1's third kicker becoming a fifth WR (Stefon Diggs) in round 16.

---

## 11. Computational cost (Phase 11)

| arm | s/pick | s/draft | vs Y1 |
|---|---|---|---|
| O0 (Y1) | **0.025** | 0.4 | 1.0× |
| O1-FULL | **4.505** | 72.1 | **180×** |

120 drafts, ≈ 1.2 h wall clock (six season blocks, 712–759 s each). No shortlist was used anywhere
in the primary experiment. A single live recommendation costs ≈ 4.5 s, immaterial in a real draft.

---

## 12. Existing gates — every gate, all three formats (Phase 12)

D86's gates, which are D84's, imported unchanged. None added, relaxed, strengthened or
re-thresholded.

| gate | threshold | target 1QB | legacy 2QB | **dynasty 1QB** |
|---|---|---|---|---|
| G1 | no dedicated position zeroed more often than control | **PASS** (0 v 0) | **PASS** (0 v 0) | **PASS** (0 v 0) |
| G2 | roster infeasibility ≤ control | **PASS** (0 v 0) | **PASS** (0 v 0) | **PASS** (0 v 0) |
| G3 | primary worse in ≤ 1 season | **PASS** (1/6) | **FAIL** (2/5) | **FAIL** (2/6) |
| G4 | no position drafted > 2 rounds earlier | **PASS** (+0.15 rd) | **PASS** (+0.02 rd) | **PASS** (+0.07 rd) |
| G5 | no increase in capacity breaches at any position | **PASS** (31 v 53) | **FAIL** (QB 22 v 19) | **PASS** (**0 v 24**) |
| G6 | leave-one-season-out margin stays positive | **PASS** | **FAIL** | **PASS** (+8.9…+34.2) |
| G8 | clustered 95% CI excludes zero | **PASS** [+6.5, +91.5] | **FAIL** | **FAIL** [−30.8, +72.3] |
| G9 | primary margin ≥ 25.0 | **PASS** (+49.0) | **FAIL** (−2.3) | **FAIL** (+20.8) |
| G10 | season-long margin ≥ −25.0 | **PASS** (+35.8) | **PASS** (+16.2) | **PASS** (+13.1) |
| **G7** | **cross-format sign** | **FAIL — +49.0 / −2.3 / +20.8** | | |

Worth noting on its own: **G5 in `dynasty_1qb` is 0 breaches for O1 against 24 for Y1** — O1 never
exceeds a positional capacity in 60 drafts, while Y1 does so 24 times, almost entirely at kicker.
That is the mechanism showing up in a legality-adjacent gate rather than in the point estimate.

---

## 13. Ship / do not ship

> ### **DO NOT SHIP. Y1 remains production.**
> No production file was changed and no production diff was prepared. O1 fails **G3, G8 and G9** in
> the third format and **G7** overall.

**Verdict: B — PROMISING BUT UNRESOLVED.**

* **Not A (ship).** Four gates fail. The third-format effect is below the economic threshold and
  its interval spans zero.
* **Not C in the sense of "the effect failed or reversed."** It did not: it is same-signed, the
  mechanism reproduced precisely, LOSO is all-positive, season-long is positive, roster legality is
  perfect, and capacity breaches fell to zero.
* **Not D (close O1).** Closing would require strong evidence that the target-format gain does not
  generalise. A same-signed +20.8 with an active mechanism is weak evidence *for* generalisation,
  not evidence against it. Closing on this would be the wrong call in the opposite direction.
* **B, with the ambiguity named:** the mechanism generalises; the *magnitude* does not clearly, and
  this benchmark cannot resolve an effect of +20.8 (its MDE here is 51.5).

Per the brief's instruction to choose the conservative outcome under ambiguity: **Y1 stays.**

---

## 14. Most important conclusion

> **"Was D89's G7 failure evidence that O1 does not generalise, or evidence that the legacy format
> was incapable of testing O1's mechanism?"**

**Substantially the latter — and the evidence for that is now structural, not inferential.** The
legacy format cannot express O1's mechanism for two independent reasons: its lineup has no K or DEF
slot, and its board contains zero kickers and zero defenses. It was never a test of this mechanism.
In the one available format that *can* test it, the mechanism reproduced cleanly and the effect
came out same-signed.

**But that answer is not a clean acquittal.** The format that could test it returned **+20.8, below
the economic threshold, with a CI spanning zero, negative in two of six seasons, and carried
entirely by the back half of the sample.** "The legacy format could not test O1" and "O1's benefit
is clearly established outside the target format" are different claims, and D90 supports the first
without establishing the second.

> **"Does O1 now have enough evidence to replace Y1?"**

**No.** It fails four pre-registered gates. The most that can be said is that the *reason* to doubt
O1 has changed: it is no longer "O1 might be a target-format artifact" — the mechanism demonstrably
operates on an independent board — but "the size of O1's benefit outside the target format is
smaller than this benchmark can measure."

---

## 15. Documented new research question (Phase 12)

**The effect is drifting upward over time in both formats where the mechanism operates, perfectly
monotonically in `dynasty_1qb` (−46.2 → +80.2, ρ = 1.00) and in the same direction in
`target_league` (early +29.4 → late +68.6).** Noticed after the fact and carrying no inferential
claim here.

If real, it changes the question from "how big is O1's effect?" to "is O1's effect a function of
how much K/DST over-drafting there is to correct, and has that been increasing?" — which is
testable directly, because Y1's own kicker count is observable per season and rose from 2.00 to
3.00 in `dynasty_1qb` over the same window. That is a diagnostic on existing artifacts, not a new
objective and not a new experiment.

**Explicitly not recommended:** creating O2, re-weighting O1, adding waiver or risk terms,
reopening projections, shortlists, more slots, or relaxing G7.

---

## 16. Plain-English trust assessment

**Nothing about Alpha's advice at the top of a 2026 draft changes, in either format.** In this new
dynasty format O1 makes the identical picks at #1, #20 and #21 — St. Brown, McCaffrey, Allen — and
first-QB, first-RB and first-WR rounds move by less than a tenth of a round across 120 drafts.

What O1 changes is the endgame, and it now does so on **two independent boards**: it stops buying
the extra kicker. In this format Y1 drafts 2.40 kickers per draft and drifts to 3.00 by 2025; O1
draws exactly **2.00 every season** — precisely the roster's capacity — and spends the difference
on running-back and tight-end depth. On the 2026 board that is three kickers versus two.

That behaviour is worth about **+21 realized weekly points** here, against **+49** in the target
format. Both are positive; only the target one is large enough for this benchmark to distinguish
from noise.

The honest summary after six phases and 700 drafts: **O1 is a better-specified objective whose
mechanism demonstrably works on more than one board, and whose benefit outside the target format is
real but smaller than the ruler.** And the practical advice is unchanged and now confirmed in a
second format: **take the kicker you need, then stop.** You still do not need this code change to
act on it.
