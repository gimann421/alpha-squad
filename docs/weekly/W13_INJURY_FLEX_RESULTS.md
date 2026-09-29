# W13 — A player's own Friday injury designation and the FLEX top 10

**Status: COMPLETE.**

**Pre-registered verdict: NO CONFIRMED INCREMENTAL SIGNAL**, in Full PPR and Half-PPR. Per §7 of
the pre-registration, **this injury-feature direction stops.**

**What that means:**

- **Adding a player's own Friday injury designation to W10's model does not improve the FLEX top
  10.** The change is −0.0020 capture@10 over 63 weeks, CI [−0.0141, +0.0099], with 28 weeks
  better, 28 worse and 7 tied.
- **The CI's upper end (+0.0099) is below the pre-registered bar (+0.011)**, so an effect of the
  size W13 set out to confirm is ruled out, not merely unproven.
- **W12's suggestive +0.016 was not a real signal.** In W13, adding the same two columns
  *shuffled* moves FLEX capture@5 and @10 by about as much as W12's hint. That hint is what
  refitting the model with any extra columns does.
- **Nothing was damaged:** W10's WR gain over current Alpha is intact (+0.0220\*), and no
  guardrail is breached.

**Provenance:**

| step | commit |
|---|---|
| pre-registration, before any W13 comparison existed | `90d93d6` |
| instruments | `6b4bd6a` |
| raw results (committed unread) | `33df7cc` |
| extra leakage regression tests | `d60ba45` |

All twelve validity gates passed before any result was read. **No amendments.**

**Research only. Production diff EMPTY. ECR is a benchmark only, never a feature.** No PR, no
merge.

---

## 1. Research question

> Does a player's own Friday injury designation provide incremental information that improves
> FLEX top-10 rankings beyond the W10 historical-player-knowledge model?

It is a confirmatory test of one W12 exploratory finding: the FLEX capture@10 gain from own
designations, +0.016 to +0.018. That finding was consistent across seasons but only **+0.009, not
significant, above a shuffled-feature null**.

**The outcome is ranking quality among players who played, not whether a player plays** (brief §5;
W2's universe).

## 2. Pre-registration

The full text is `docs/weekly/W13_PREREGISTRATION.md`, committed at `90d93d6` before any W13
quantity comparing boards or models was computed. It fixed all of the following:

- the hypothesis;
- the exact feature;
- the cutoff;
- the 63 weeks;
- the arms;
- the metrics;
- the statistics;
- the MDE bar of +0.011;
- a six-condition decision rule;
- the stopping rule;
- the missing-data rules;
- the 2026 protocol;
- twelve gates;
- nine predictions.

**§0 disclosed up front** that 2021–2024 generated the hypothesis, so W13 is a cleaner re-test on
the same weeks, not independent confirmation.

**Order of work:**

1. Instruments committed (`6b4bd6a`).
2. The runner crash-tested on 2021 into scratch (structure only).
3. The gates dry-run.
4. The full run, whose artifact was committed unread (`33df7cc`).
5. Gates G1–G10 and G12 run; G11 run once the W5–W12 reproduction finished.
6. Results read.

**Amendments: none.**

## 3. Exact feature definition

W12's `own` category, built by `w12_timestamped.injury_table` with the A1 fix. Nothing else was
added.

| feature | value |
|---|---|
| `own_status` | 0 = no designation (also Probable, Note, or not on the report); 1 = Questionable; 2 = Doubtful; 3 = Out |
| `own_practice` | 0 = full, or not listed; 1 = limited; 2 = did not participate (incl. "Out (Definitely Will Not Play)") |

**Rules:**

- Only the player's own team-week rows with `date_modified` ≤ the cutoff are used.
- **Multiple rows:** the most severe value.
- **No designation:** 0 on both.
- **No team row visible by the cutoff:** both missing. CatBoost handles missing values natively.
- **A row modified after the cutoff does not exist** (W12 A1). A player whose only row was edited
  later counts as not listed.

**Q/D/O and practice both enter.** Arm S (status only) is the exploratory split.

**In the evaluated universe, the feature is in practice "Questionable or not" plus practice
status.** Among the 2021–2024 RB/WR/TE player-weeks of players who played:

| status | player-weeks |
|---|---:|
| no designation | 18,731 |
| no report visible | 1,074 |
| Questionable | 918 |
| Doubtful | 1 |
| Out | 0 |

Out and Doubtful players almost never play, so they are almost never in a board that is scored.

## 4. Data source

**NFL official injury report via nflverse `injuries`**, regular season, 2015–2024. It is Class A:
`date_modified` (UTC, to the second) is on 100% of rows (`W12_DATA_AUDIT.md` §2–3).

- **Read:** 52,666 rows, 100% gsis-mapped, 0 unmapped team codes. OAK, SD and STL are aliased to
  LV, LAC and LA.
- **Provenance:** `snapshot_registry`, with sha256 per season. The raw files stay under `data/`
  (gitignored).
- **Not used:**
  - **2025**, because its file has no timestamp (Class B);
  - **2026**, because the repository holds no 2026 data.

## 5. Historical coverage

**Primary and only window: 2021–2024, 63 evaluated weeks** (the W5–W12 universe):

| season | weeks | count |
|---|---|---:|
| 2021 | 1–17 | 17 |
| 2022 | 2–17 | 16 |
| 2023 | 2–17 | 16 |
| 2024 | 4–17 | 14 |

- **Training:** walk-forward `[2015, S − 1]`. Injury timestamps exist for all of 2015–2024.
- **Feature coverage:** non-missing on 94.8% of 2021–2024 panel player-weeks.
- **FLEX universe (Full PPR):** 15,906 player-weeks, of which 735 (4.6%) are Questionable.
- **Gate G4 confirms** that only 2021–2024 was evaluated.

## 6. Cutoff definition

**23:59:59 America/New_York on the Friday before the week's first Sunday game.**

- **Timestamp field:** `date_modified`, the row's last modification, converted from UTC.
- **Snapshot date:** the cutoff Friday equals the canonical snapshot date in 62 of 63 weeks.
  - 2021 week 14's board is a Saturday; the Friday is used there, which is stricter.
- **Timing of rows:** most rows are the league's Friday final report, about 15:50 ET. About 92% of
  RB/WR/TE rows fall at or before the cutoff.
- **Nothing from Saturday or Sunday enters.** Regression test:
  `test_saturday_sunday_and_final_game_status_never_enter_the_own_features`.

## 7. Leakage audit

**All run before any result was read.** The full gate list is under **Validity** below.

| check (brief §16) | how it was verified | result |
|---|---|---|
| every feature timestamp ≤ cutoff | the construction filters `modified <= cutoff`, and an in-code assertion enforces it | holds |
| no post-cutoff row contributes | **G2:** an own **Out** row injected 1 s after the cutoff moved nothing (0/40); 1 s before, it set status 3 / practice 2 (40/40). Deleting all **3,734** post-cutoff rows moved **0** values | pass |
| no future injury information | **G6:** walk-forward (0 training frames contain the predicted season). Per-week features use that week's report only | pass |
| historical identity correct | **G7:** own status and practice for **300** seeded player-weeks (150 designated) equal an independent SQL computation: **0 wrong**. gsis map rate 1.0000; 0 unmapped team codes | pass |
| no final game status leaks backward | Sunday inactive-list and post-game rows are after the cutoff, so nonexistent (G2 and the regression tests). **Inactive players are not in the scored universe at all** | pass |
| no target information | features come from injury rows only. **G4:** B's frame is exactly W10's 7 durable + the 2 own columns. **G5:** exactly the declared training calls | pass |
| order-free | **G8:** 0 values differ with every input reversed | pass |

**Regression tests:**

- W12's `test_deleting_post_cutoff_rows_never_changes_a_feature` and
  `test_own_row_edited_after_the_cutoff_is_invisible` are unchanged.
- W13 adds three tests in `tests/unit/test_weekly_injuryflex.py`:
  - the exact cutoff instant;
  - Saturday, Sunday and post-game rows never entering;
  - most-severe-row handling.

## 8. Baseline

**A = W10, exactly:** `ALPHA_PLUS_HISTORICAL` is production's CatBoost (200 iterations, depth 4,
lr 0.05, MAE, seed 42) plus W10's 7 prior-season features, trained by W10's own function.

- **Gate G3:** A's 9,072 per-week values equal W10's committed cells (2021–2024; positional and
  FLEX; Full and Half-PPR) with **0 mismatches**.
- **CF_A** (current Alpha) and **ECR** are W10's cells exactly (G9: 18,144 values, 0 mismatches).

## 9. Treatment model

**B = A + `own_status` + `own_practice`.** Everything else is unchanged:

- the CatBoost configuration and seed;
- the loss;
- the target;
- walk-forward training;
- the universe;
- scoring.

**N (null)** is A plus the same two columns permuted jointly across players within (season, week,
position), with W12's seeds. G4 verified it is a within-group permutation of B's values.

**S (exploratory)** is A + `own_status` only. It is never a verdict input.

## 10. Primary FLEX capture@10 result

**Full PPR, 63 weeks, pooled FLEX path:**

| arm | FLEX capture@10 (mean) |
|---|---:|
| ECR (benchmark) | 0.6259 |
| **A: W10** | **0.6127** |
| **B: W10 + own injury** | **0.6107** |
| N: null | 0.6081 |
| S: status only | 0.6071 |
| CF_A: current Alpha | 0.5912 |

> **B − A = −0.0020.** B is marginally *below* W10.

## 11. Confidence interval

**B − A FLEX capture@10: −0.0020, 95% CI [−0.0141, +0.0099].** This is a paired bootstrap over
weeks: 10,000 resamples, seeds 0–9.

- **MDE (CI half-width): 0.012.** This matches the pre-registered bar of 0.011.
- **The upper bound, +0.0099, is below +0.011.** An improvement of the pre-registered size is
  excluded at 95%.

## 12. Statistical test

**Unit: the week (63 paired differences).**

| comparison (FLEX capture@10) | mean | 95% CI | W–L–T | Wilcoxon p | sign-flip p |
|---|---:|---|---|---:|---:|
| **B − A (primary)** | **−0.0020** | [−0.0141, +0.0099] | 28–28–7 | 0.88 | **0.76** |
| **B − N (vs the null)** | +0.0026 | [−0.0084, +0.0142] | 19–27–17 | 0.93 | 0.66 |
| N − A (the null itself) | −0.0045 | [−0.0171, +0.0079] | 25–33–5 | 0.44 | — |

**The sign-flip p is two-sided Monte Carlo, from 100,000 seeded draws.** Exact enumeration of 2⁶³
sign patterns is infeasible; the Monte Carlo standard error is about 0.001.

**Season level, B − A:**

| season | mean | 95% CI |
|---|---:|---|
| 2021 | +0.0033 | [−0.0141, +0.0199] |
| 2022 | −0.0086 | [−0.0393, +0.0175] |
| 2023 | +0.0049 | [−0.0209, +0.0322] |
| 2024 | −0.0087 | [−0.0321, +0.0145] |

Two seasons are positive and none is significant.

**Secondary FLEX outcomes, B − A** (unadjusted; none has a CI excluding 0):

| metric | B − A | 95% CI | W–L–T |
|---|---:|---|---|
| capture@5 | +0.0086 | [−0.0084, +0.0263] | 24–19–20 |
| capture@20 | −0.0056 | [−0.0132, +0.0019] | 24–35–4 |
| Spearman | +0.0008 | [−0.0002, +0.0017] | 36–27–0 |
| pairwise | +0.0003 | [−0.0001, +0.0007] | 36–26–1 |
| precision@10 | −0.0143 | [−0.0330, +0.0040] | 11–17–35 |
| regret@10 (points, lower is better) | +0.39 | [−3.10, +3.95] | 28–28–7 |

**Regret@10 levels** (best possible top-10 points minus the board's, per week):

| board | regret@10 |
|---|---:|
| ECR | 109.9 |
| A | 113.6 |
| B | 114.0 |
| N | 114.9 |
| S | 115.2 |
| CF_A | 120.1 |

## 13. Leave-one-season-out results

**B − A FLEX capture@10, dropping one season:**

| dropped | mean | 95% CI |
|---|---:|---|
| 2021 | −0.0039 | [−0.0198, +0.0110] |
| 2022 | +0.0003 | [−0.0126, +0.0133] |
| 2023 | −0.0043 | [−0.0180, +0.0087] |
| 2024 | −0.0000 | [−0.0144, +0.0138] |

**1 of 4 folds is positive and 0 of 4 are significant.** C3 needed all 4 positive and at least 3
significant.

## 14. Half-PPR result

**Robustness only; nothing was tuned on it.**

| comparison | mean | 95% CI | sign-flip p |
|---|---:|---|---:|
| **FLEX capture@10 B − A** | **−0.0010** | [−0.0134, +0.0111] | 0.87 |
| B − N | +0.0021 | [−0.0094, +0.0142] | 0.74 |

**Consistency with Full PPR:**

- LOSO folds: −0.0030, +0.0015, −0.0029, +0.0003.
- WR capture@10 B − CF_A: **+0.0206\*** [+0.0016, +0.0396].

**Same conclusion as Full PPR.**

## 15. Position-level effects

**B − A, Full PPR, 63 weeks.** \* means the CI excludes 0 (unadjusted).

| position | capture@5 | capture@10 | capture@20 | Spearman |
|---|---:|---:|---:|---:|
| RB | −0.0027 | −0.0102 [−0.0222, +0.0009] | +0.0037 | +0.0016 |
| WR | −0.0105 | −0.0014 [−0.0109, +0.0087] | −0.0032 | +0.0001 |
| TE | +0.0132 | +0.0012 [−0.0120, +0.0142] | −0.0022 | +0.0002 |

**No positional effect is significant.**

- **The largest is RB capture@10 at −0.0102.** Its CI reaches +0.0009, so by the pre-registered
  definition it is not a breach.
- **Per season** (unadjusted), RB capture@10 is significantly negative in 2023 (−0.028\*), and TE
  capture@10 in 2022 (−0.024\*).

**No guardrail breach anywhere** (§7: CI below 0 and magnitude ≥ 0.005). This covers:

- RB, WR and TE capture@10, @5 and Spearman;
- FLEX capture@5, @20 and Spearman.

## 16. WR guardrail

**C6 holds.**

| check | value | 95% CI |
|---|---:|---|
| WR capture@10 B − A (not a breach, > −0.010) | −0.0014 | [−0.0109, +0.0087] |
| **WR capture@10 B − CF_A** (W10's gain retained) | **+0.0220\*** | [+0.0032, +0.0408] |
| for reference, A − CF_A (W10's gain) | +0.0234\* | [+0.0060, +0.0409] |

**Injury information neither helps nor harms WR.** There is no tradeoff to report.

## 17. Mechanism analysis

**Exploratory.** Full PPR, FLEX, B versus A. The brief asks for the mechanism *if* the feature
improves the FLEX top 10. It did not, so this explains why it moved nothing.

**How much B moves the top 10:**

- B and A share **85.4%** of their weekly top 10: about 1.5 players swapped per week.
- 92 players entered B's top 10 over 63 weeks, and 92 left.
- **Precision@10 is −0.0143 (not significant).** The feature rearranges; it does not sharpen.

**The movers, by own status:**

| status group | entered B's top 10 | left it | mean points of entrants | mean points of leavers | attribution to B − A capture@10 |
|---|---:|---:|---:|---:|---:|
| no designation | 85 | 67 | 16.6 | 18.1 | +0.0104 [−0.0025, +0.0230] |
| Questionable | 3 | 17 | 18.4 | 14.1 | −0.0102\* [−0.0187, −0.0023] |
| no report visible | 4 | 8 | 14.4 | 12.1 | −0.0021 |
| Doubtful / Out | 0 | 0 | — | — | 0 |

Attribution assigns a mover's points to that mover's group, so a group's value is not a verdict on
the swap. The groups sum exactly to B − A (gated every week).

**The four questions the brief asks:**

1. **Does it demote players unlikely to play?** It cannot. Out players are never in the scored
   universe, and Doubtful players are there once in four seasons. The only designation left to
   act on is Questionable.
2. **Does it demote the right Questionable players?** Directionally, yes.
   - B pushes Questionable players out of the top 10: 17 out, 3 in.
   - Those it pushed out scored 14.1, below the 16.6 average of all entrants.
   - The value is small: roughly 17 × 2.5 ≈ 42 points over 63 weeks, about 0.002 of capture.
3. **Does it rescue healthy players?** No. B promotes a net 18 undesignated players, but the
   undesignated players it brings in (16.6) score *less* than the undesignated players it drops
   (18.1). That churn among healthy players cancels the Questionable gain. The null arm, with no
   information at all, shifts FLEX capture by as much (N − A: capture@5 +0.0138, capture@10
   −0.0045).
4. **By position:**

   | position | attribution |
   |---|---:|
   | RB swaps | +0.0066 (ns) |
   | WR swaps | −0.0019 (ns) |
   | TE swaps | −0.0067\* |

**Bias (prediction − realized points) by status, FLEX universe:**

| status | n | A | B |
|---|---:|---:|---:|
| no designation | 14,230 | −1.23 [−1.35, −1.12] | −1.22 [−1.33, −1.11] |
| Questionable | 735 | −0.22 [−0.63, +0.17] | −0.54 [−0.94, −0.15] |
| no report visible | 940 | −1.08 | −1.02 |

**Every group is under-predicted,** because conditioning on having played raises realized points.

- **A under-predicts Questionable players by about 1 point less than undesignated ones.** It
  over-rates them relative to healthy players.
- **B closes about a third of that gap** by lowering Questionable predictions by about 0.3 points.
- **That correction is real but too small to change who is in a top 10.**

**Why W12 looked positive:**

- W13's null shows that refitting the model with two uninformative extra columns shifts mean FLEX
  capture@5 and @10 by +0.014 and −0.005. That is the same size as W12's +0.016, measured on a
  different base.
- W12's own null comparison (+0.009, not significant) had already flagged this.
- **With the refit noise controlled (B − N: +0.0026, not significant), nothing remains.**

**Exploratory, unadjusted:**

- **Arm S (status without practice) improves FLEX Spearman by +0.0012\*** [+0.0004, +0.0020] and
  pairwise by +0.0005\*.
- It does not improve capture@10 (−0.0056, not significant).
- **B minus S** is not significant on FLEX capture@10 (+0.0037) or Spearman (−0.0004).
- This is a whole-board ordering nudge of the same kind W12 found for teammates. It is not a
  top-of-board gain, and under the stopping rule it is not pursued.

## 18. 2026 holdout protocol

**2026 was not used anywhere in W13:**

- The repository holds no 2026 stats, games, production predictions or injury snapshots.
- No 2026 value informed any choice.
- As of this report, the 2026 season is under way, and this repository has collected no 2026
  Friday snapshot.

**Frozen in pre-registration §9** before any W13 result:

- the two features;
- the cutoff rule;
- the A/B/N arms;
- W10's durable features;
- the CatBoost configuration;
- the decision rule.

**What must be collected for a clean 2026 test:**

1. **Every Friday before 23:59:59 ET:** a snapshot of the week's official NFL injury report, with
   retrieval time (UTC), source identifier and sha256. The raw file goes under `data/` and is
   registered in `snapshot_registry`.
   - The retrieval time is the Class A timestamp.
   - A week whose Friday passed before collection began is Class A only if the published file
     itself carries per-row timestamps. The nflverse 2025 file does not.
2. **Production's weekly 2026 predictions and the canonical Friday ECR board**, as in 2021–2025.
3. **After the season:** weekly stats and games through week 17.

**Run:** `scripts/research/w13_injury_flex.py --seasons 2026`, with arms trained through 2025.
2025 training rows carry missing injury features.

- The runner refuses 2025 as an evaluation season.
- It writes the single-season rule to `window_rule` (FLEX capture@10 B − A with a CI above 0).

**How a 2026 result would be read.** §9 was written to confirm a positive historical result, and
the historical result is null.

- **A null 2026** agrees with D121.
- **A 2026 CI above 0** would not reverse this verdict. Under the stopping rule, it could only
  justify a new, separately pre-registered experiment.

**No decision depends on running it.**

## 19. Limitations

- **The universe is players who played (W2).**
  - Any value of the injury report for *avoiding inactive players* is outside this test by
    construction: brief §5 says so, and the pre-registration fixed it.
  - What was tested is whether the designation helps rank players who did play. In that universe,
    the designation is essentially "Questionable or not".
- **Same weeks as the hypothesis.** 2021–2024 produced W12's hint. That makes a null *more*
  informative, not less.
- **One version per row.** The nflverse file keeps only each row's last version, and a row last
  edited after the cutoff is dropped: no Wednesday→Friday trajectory, and no in-week status changes
  (W12 audit).
- **Injured reserve** players are not on the weekly report (W12 audit). This is irrelevant here,
  since they do not play.
- **Only a Friday cutoff was tested.** Saturday or Sunday information was excluded by design, and
  no alternative cutoff was tried (stopping rule).
- **Refit noise.** With one seed, adding any columns perturbs CatBoost's trees. The null arm is how
  W13 controls for it; seed-averaging was not pre-registered and was not done.
- **Secondary tests are unadjusted.** The two per-season positional negatives (RB 2023, TE 2022)
  and arm S's Spearman gain are flagged and not interpreted as findings.

## 20. Verdict

**Six conditions (§7):**

| # | condition | value | result |
|---|---|---|---|
| C1 | FLEX capture@10 B − A ≥ +0.011 | −0.0020 | **fail** |
| C2 | CI excludes 0 | [−0.0141, +0.0099] | **fail** |
| C3 | LOSO: 4/4 positive and ≥ 3/4 significant | 1/4 positive, 0/4 significant | **fail** |
| C4 | B − N CI above 0 | +0.0026 [−0.0084, +0.0142] | **fail** |
| C5 | Half-PPR B − A positive | −0.0010 | **fail** |
| C6 | WR guardrail, no breach | WR B − A −0.0014; WR B − CF_A +0.0220\*; no breach | pass |

> **NO CONFIRMED INCREMENTAL SIGNAL.** A player's own Friday injury designation does not improve
> W10's FLEX top 10.

**Stopping rule applied.** This injury-feature direction stops. None of the following is tried:

- thresholds or transformations;
- interactions;
- tuning;
- alternate cutoffs;
- ECR, news or teammate features.

Only a separately pre-registered experiment could justify any of them. **W10 remains the model of
record for this research line.** Production is unchanged.

## 21. Exact next research question

Every verifiable pre-Friday injury signal has now been tested against the FLEX top 10:

- teammates' availability (W12);
- players' own designation (W13).

Neither moves the top of the board. W10 is the one gain that has survived pre-registration: FLEX
capture@10 +0.0215\* and WR capture@10 +0.0234\* over current Alpha, 2021–2024.

> **Does W10's historical-player-knowledge gain over current Alpha hold on untouched 2026 weeks,
> under W10's frozen §9 protocol?** W10's §9 rule: the WR capture@10 and capture@5 B − A point
> estimates are both positive, and the WR capture@10 CI excludes 0.

This needs the 2026 season, production's 2026 weekly predictions and the Friday ECR boards to be
collected as they happen. The Friday injury-report snapshots of §18 are optional; no W13 decision
depends on them.

---

## Validity

All twelve pre-registered gates pass (`scripts/research/w13_validity_gates.py`):

| gate | result |
|---|---|
| G1 parity | the one-change trainer with no extra feature reproduces production: 26,097/26,097 exact, max diff 0.0 |
| G2 pre-cutoff | own Out row 1 s late: 0/40 moved. 1 s early: 40/40 set status 3 / practice 2. Deleting 3,734 post-cutoff rows: 0 moved |
| G3 A = W10 | 9,072 values, 0 mismatches |
| G4 own features only | frame columns exact; no forbidden token; N a within-group permutation of B; only 2021–2024 evaluated; injury seasons 2015–2024 |
| G5 ECR never a feature | exactly 3 one-change calls (B, N, S) plus 1 call to W10's trainer; no ECR string in the arm code |
| G6 walk-forward | 0 leaking frames |
| G7 identity | 0/300 independent SQL mismatches; gsis 1.0000; 0 unmapped teams |
| G8 order-free | 0 values differ |
| G9 universe / cutoff | CF_A/ECR: 18,144 values, 0 mismatches; 63 weeks (Full and Half-PPR) |
| G10 determinism | two full runs byte-identical: sha256 `217e2763d5212b5d…` |
| G11 upstream | W5–W12 re-run: **13/13 artifacts byte-identical** |
| G12 null construction | N − A capture@5/@10 CIs include 0 at RB, WR and TE |

G12 detail:

| position | capture@5 | capture@10 |
|---|---:|---:|
| RB | +0.0020 | −0.0051 |
| WR | −0.0124 | −0.0096 [−0.0192, +0.0003] |
| TE | +0.0018 | +0.0053 |

Before the full run, the gates were dry-run on a 2021-only crash file. G3, G4 and G9 failed there
by construction (17 weeks instead of 63). G12 failed in 3 of 6 cells on 17 weeks and passed on the
pre-registered 63.

**Suite:** 1,894 tests pass (1,884 + 10 W13 tests). `make lint` is clean, and the W13 scripts are
ruff-clean. **Production diff vs `origin/main` EMPTY**, checked on:

- `models/`, `league/`, `api/`, `cli.py`;
- `market/`, `features/`, `identity/`, `ingest/`, `sources/`.

## Predictions (§11)

| # | prediction | outcome |
|---|---|---|
| 1 | FLEX capture@10 B − A positive, +0.005 to +0.015 | **wrong:** −0.0020 |
| 2 | C1 or C4 fails | **right:** both fail, and C2, C3 and C5 fail too |
| 3 | verdict NO CONFIRMED INCREMENTAL SIGNAL | **right** |
| 4 | Half-PPR positive | **wrong:** −0.0010 |
| 5 | WR preserved | **right:** B − CF_A +0.0220\*, no breach |
| 6 | B demotes Questionable players, who score less than their replacements; movers mostly RB/WR | **partly right:** Questionable players are demoted (17 out, 3 in) and score less than the average entrant (14.1 vs 16.6). Churn among undesignated players cancels it. Movers by position were not counted; by points, RB swaps are net positive and TE swaps net negative |
| 7 | A over-predicts Q/D more than undesignated players | **right** for Q, relative to undesignated players (by about 1.0 point). D is not assessable (n = 1) |
| 8 | arm S carries most of B's effect | **not assessable:** B has no effect to apportion. S is no better on capture@10 and only nudges FLEX Spearman |
| 9 | the null does nothing positionally | **right** (G12) |

**Score:** 5 right, 1 partly right, 2 wrong, 1 not assessable.

## Files

| file | role |
|---|---|
| `docs/weekly/W13_PREREGISTRATION.md` | frozen design (`90d93d6`) |
| `src/alpha_squad/evaluation/weekly/injuryflex.py` | status groups, sign-flip permutation p, the six-condition decision |
| `tests/unit/test_weekly_injuryflex.py` | 10 tests: decision rule, permutation p, leakage regressions |
| `scripts/research/w13_injury_flex.py` | runner: arms A/B/N/S, positional and FLEX evaluation, regret, mechanism, LOSO, verdict |
| `scripts/research/w13_validity_gates.py` | G1–G12 |
| `reports/weekly/w13_results.json` | every per-week cell, summary, mechanism series and provenance (sha256 `217e2763…`) |
| reused, unchanged | `scripts/research/w12_timestamped.py` (injury pipeline, A1), `scripts/research/w11_mechanism.py::train_b` (W10's trainer), `evaluation/weekly/timestamped.py` |

**Reproduce:**

```bash
uv run python scripts/research/w13_injury_flex.py --out reports/weekly/w13_results.json
uv run python scripts/research/w13_validity_gates.py --repro-summary <W5-W12 byte-comparison record>
```

---

## LAYMAN'S TERMS

**What Claude did:**

- Wrote down the exact test, and what would count as success, before looking at any result.
- Gave the proven W10 model one extra piece of information: whether a player was listed
  Questionable, Doubtful or Out on Friday. Only reports that existed by Friday night were used.
- Checked 12 ways that nothing leaked or broke, then compared the top-10 FLEX lists over 63 weeks.

**What it means:**

- Knowing a player's Friday injury tag does not pick a better FLEX top 10. It helps a little with
  Questionable players and hurts a little elsewhere, which nets to zero.
- W12's promising hint was the model reshuffling itself, not real information. So this direction
  stops.

**Next step:**

- Check whether W10's proven improvement also holds on the 2026 season, which nobody has looked
  at yet.
