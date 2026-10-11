# W15 — 2026 holdout, look 2 (W14 protocol, unchanged)

**Status: LOOK 2 COMPLETE. The holdout continues.**

**Protocol-permitted verdict: INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT.** There are
4 eligible weeks; the frozen rule reads no direction before 8.

**What changed since look 1:** one new week (week 4).

**W10 still points the way it did in 2021–2025, more strongly than its history predicts:**

| B − A, weeks 1–4 | value | weeks better / worse / tied | exact p | W10 4-week predictive band |
|---|---:|---|---:|---|
| WR capture@10 | **+0.103** | 3 / 1 / 0 | 0.25 | 98th percentile, above the 97.5% edge |
| FLEX capture@10 | +0.048 | 3 / 0 / 1 | 0.25 | 80th percentile |

- **The shuffled-feature null shrank to +0.028** at WR and was zero in week 4. B beats the null by
  +0.075.
- **Four weeks still cannot confirm anything.** W10 §9 is applied once, after week 17.

**The freeze record below was committed (`bda7186`) before any look-2 result was computed.**
**All 12 gates pass. Research only. Production diff EMPTY.**

## Freeze record (2026-10-10)

**Protocol:** `docs/weekly/W14_PREREGISTRATION.md` §2–§7 and §10, with amendments A1–A5. A5 is
tooling only.

**Data path:** §3 steps 1–5 in a fresh isolated database, `data/w15/alpha_squad_2026.duckdb`. The
data was captured 2026-10-10 at 23:00 UTC; the schedule snapshot's sha256 is `ea76320b…`. The
canonical database is untouched (sha256 `fa8e32db…`).

**A2's row-order restore:** production's loader returns the canonical 2015–2025 sequence for QB,
RB, WR and TE.

**Eligible weeks, from the committed §4 rule only** (schedule, games present, teams with stats;
no outcome values):

| week | Friday board | games in data | status |
|---:|---|---:|---|
| 1–3 | 09-11, 09-18, 09-25 | 16 / 16 each | already in look 1 |
| **4** | 10-02 | **16 / 16** | **newly eligible** |
| 5 | none yet | 1 / 15 | pending (games unplayed; no canonical board in the ECR history yet) |
| 6–17 | — | 0 | not yet played |

**n = 4 < 8.** By §7, this look can only return INCONCLUSIVE — CONTINUE, unless a
material-contradiction condition (C) is met.

---

## 1. Frozen protocol reference

**Protocol:** `docs/weekly/W14_PREREGISTRATION.md`, unchanged in substance.

**What is applied unchanged:**

- **W10 (§2):** code byte-identical to `5de17c1` (G2), run through W10's own functions.
- **Arms:** A = production's weekly predictions; B = W10, trained on [2015, 2025].
- **Data path (§3):** production's CLI in a fresh isolated database, with A1's weekly command and
  **A2's canonical row-order restore**, applied before production's 2026 run.
- **Cutoff:** the canonical Friday board.
- **Eligibility (§4):** every game in the data, every team with stats, the last kickoff at least
  6 hours before capture.
- **Decision (§7):**
  - **Interim, fewer than 8 weeks:** INCONCLUSIVE — CONTINUE, unless the WR capture@10 interval
    lies entirely below 0 or the mean falls below the 2.5th percentile of W10's predictive band
    (NOT REPLICATED).
  - **Interim, at least 8 weeks:** PARTIAL becomes possible.
  - **Final, after week 17:** §9 and REPLICATED / PARTIAL / NOT REPLICATED, once.

**Committed code:** the W14 runner, unchanged. The W14 gates, plus amendment A5: a `--schedule`
argument, tooling only, committed before ingest (`47b81f6`).

## 2. Newly eligible weeks and exclusion reasons

See the freeze record above.

- **New: week 4**, all 16 of 16 games (its Monday game, NO–ATL, is now in the data).
- **Excluded:**
  - week 5: 1 of 15 games played, and no canonical Friday board in the ECR history yet;
  - weeks 6–17: not yet played;
  - week 18: never.

**Universe in week 4:** WR 137, RB 81, TE 74, FLEX 292.

**Weeks 1–3 were re-scored on look 2's fresh data, as §10 requires.**

- **Unchanged:** their predictions, stats (apart from one offensive lineman's position label) and
  WR capture@10 values are identical to look 1.
- **Changed:** 378 of 1,872 cell values (ranks and Spearman, at RB weeks 1–2 and WR week 3, and
  through them FLEX). Every change comes from DynastyProcess's newer crosswalk:
  - one RB lost his FantasyPros id;
  - the WR dropped in look 1 regained his.

  Each moved player is in the set of revised mappings, the same explained-difference test as
  G3/A4.

## 3. Anti-peek and leakage checks

All 12 W14 gates pass on look 2:

- **pass 1:** G1, G2 and G4–G11;
- **final pass:** G1–G5, G7–G10 and G12, on the same artifact (sha256 `2a423650…`).

| gate | look 2 |
|---|---|
| G1 parity | production's 2026 predictions **1,310 / 1,310** exact; 2021–2025 **26,097 / 26,097** exact |
| G2 W10 frozen | no file on W10's path changed since `5de17c1`; one `w10.trainings` call; no own fit; the 7 features as frozen |
| G3 history | training frames and durable table identical. W10's 2021–2025 re-run differs only in 2025 weeks whose universe moved; **all explained by the 13 revised crosswalk mappings** (A4) |
| G4 anti-peek | canonical database unmodified (sha256 `fa8e32db…`); no 2026 outcome rows in it; no NGS reader among the runner's 43 repository modules |
| G5 walk-forward | no 2026 row in any training frame |
| **G6 later weeks** | with every later 2026 week deleted, RB/WR/TE features and A/B predictions are **bit-identical** for weeks 1, 2, 3 and 4 (320, 320, 326, 324 player-weeks) |
| G7 inputs | B adds exactly W10's 7 prior-season columns |
| G8 eligibility | evaluated = eligible = weeks 1–4; schedule sha256 matches |
| G9 identity | 0 / 1,550 unresolved 2026 players; no stray team codes |
| G10 W10's own numbers | **4,920** values equal to the verbatim `w10_historical.py --seasons 2026` run; 96 recomputed boards match W10's capture@10 |
| G11 determinism | two runs byte-identical |
| G12 upstream | W5–W13 **14 / 14** byte-identical; W14's look-1 artifact also re-ran byte-identical (15 / 15) |

**No post-Friday information:**

- features end one game before each week (G6);
- the board is the Friday scrape;
- no injury, news or depth input (G7).

## 4. Newly added results (week 4, Full PPR, B − A)

| | WR c@10 | WR c@5 | FLEX c@10 | FLEX c@5 | FLEX c@20 | RB c@10 | TE c@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| week 4 | **+0.178** | 0.000 | 0.000 | +0.001 | +0.063 | +0.032 | −0.034 |

**WR capture@10 in week 4:**

| board | capture@10 |
|---|---:|
| **B** | **0.678** |
| ECR | 0.508 |
| A | 0.500 |
| null | 0.500 |

**FLEX in week 4:** B's and A's top 10s were identical (overlap 1.0).

## 5. Cumulative 2026 results (weeks 1–4, Full PPR, B − A)

| metric | B − A | by week (1 / 2 / 3 / 4) | W–L–T | exact p |
|---|---:|---|---|---:|
| **WR capture@10** | **+0.103** | −0.052 / +0.157 / +0.128 / +0.178 | 3–1–0 | 0.25 |
| WR capture@5 | +0.066 | 0.000 / +0.106 / +0.157 / 0.000 | 2–0–2 | 0.50 |
| WR capture@20 | +0.038 | | 4–0–0 | 0.125 |
| WR Spearman | +0.018 | | 4–0–0 | 0.125 |
| **FLEX capture@10** | **+0.048** | +0.050 / +0.028 / +0.114 / 0.000 | 3–0–1 | 0.25 |
| FLEX capture@5 | −0.031 | −0.075 / 0.000 / −0.048 / +0.001 | 1–2–1 | 0.50 |
| FLEX capture@20 | +0.055 | +0.026 / +0.052 / +0.077 / +0.063 | 4–0–0 | 0.125 |
| FLEX Spearman | +0.024 | | 4–0–0 | 0.125 |
| RB capture@10 (secondary) | +0.013 | +0.049 / −0.028 / 0.000 / +0.032 | 2–1–1 | 0.50 |
| RB capture@5 | −0.003 | | 1–2–1 | 0.50 |
| TE capture@10 (secondary) | +0.053 | −0.001 / +0.066 / +0.182 / −0.034 | 2–2–0 | 0.50 |
| TE Spearman | +0.043 | | 4–0–0 | 0.125 |

**Levels, WR and FLEX capture@10:**

| | A | B | ECR |
|---|---:|---:|---:|
| WR | 0.573 | **0.676** | 0.670 |
| FLEX | 0.628 | **0.676** | 0.681 |

**Other measures:**

- **WR regret@10:** −28.4 points a week (B leaves fewer points on the table; 3 of 4 weeks).
- **FLEX regret@10:** −14.1 (3 of 4 weeks).
- **No guardrail breach.**

## 6. Full-PPR and Half-PPR

| B − A, weeks 1–4 | Full PPR | Half-PPR |
|---|---:|---:|
| WR capture@10 | +0.103 (3–1–0) | **+0.107** (3–1–0) |
| WR capture@5 | +0.066 | +0.068 |
| FLEX capture@10 | +0.048 | +0.050 |
| FLEX capture@5 | −0.031 | −0.020 |
| FLEX capture@20 | +0.055 | +0.053 |
| RB capture@10 | +0.013 | +0.011 |
| TE capture@10 | +0.053 | +0.057 |

**Half-PPR agrees in every cell.** Its verdict under the same rule is the same: INCONCLUSIVE —
CONTINUE.

## 7. WR and FLEX primary results, set against W10's history

| | WR capture@10 | WR capture@5 | FLEX capture@10 |
|---|---:|---:|---:|
| **2026, weeks 1–4** | **+0.103** | +0.066 | +0.048 |
| W10, 2021–2025 (79 weeks) | +0.022 [+0.007, +0.038] | +0.028 | +0.019 |
| W10, first 4 weeks of 2021 / 2022 / 2023 / 2024 / 2025 | +0.055 / +0.022 / +0.068 / +0.071 / −0.003 | +0.075 / +0.065 / +0.073 / +0.049 / +0.003 | +0.004 / +0.047 / +0.088 / +0.076 / −0.017 |
| **W10's 4-week predictive band** (2.5–97.5%) | [−0.045, +0.095] | [−0.064, +0.134] | [−0.048, +0.087] |
| **2026's percentile** | **98.4%** | 79% | 80% |

**Reading it:**

- **The direction matches W10 everywhere.**
- **WR capture@10 now sits above W10's 97.5% band edge.** That is a larger effect than W10's own
  history makes likely over 4 weeks.
- **This is not a contradiction under the frozen rule,** which tests only the low side, but it is
  reported plainly. Possible readings:
  - an early-season effect stronger than history (W10's EARLY period was already its largest,
    +0.038);
  - a lucky run, given one week of +0.18;
  - or both.
- **It does not change the verdict,** and it is not evidence of replication.

**Mechanism, briefly** (W10's own outputs, weeks 1–4):

- **Movement attribution:** WR movers are quiet stars (+0.052) and small-sample players (+0.051).
- **Quiet-star recall:** A 0 / 5, B 2 / 5, ECR 2 / 5.
- **WR cliff** (capture@10 against W5's null):

  | | A | B |
  |---|---:|---:|
  | 2026, weeks 1–4 | −0.113 | −0.023 |
  | 2021–2025 | −0.080 | −0.062 |

## 8. Shuffled-feature comparison

| | WR capture@10 | FLEX capture@10 |
|---|---:|---:|
| **N − A** (W10's 7 features shuffled within the season), weeks 1–4 | **+0.028** (+0.036 / +0.016 / +0.059 / 0.000) | +0.016 (+0.032 / +0.031 / 0.000 / 0.000) |
| **B − N** | **+0.075** (−0.087 / +0.140 / +0.070 / +0.178) | +0.032 |
| look 1, weeks 1–3: N − A | +0.037, about half of B's gain | — |
| W10 history, 2021–2025: N − A | −0.007 | −0.003 |

- **The null did nothing in week 4**, where B gained +0.178.
- **The refit-noise share of B's WR gain has fallen from about half to about a quarter.**
- **The null is still above its historical level.** Half-PPR is the same: N − A +0.028, B − N
  +0.079.

## 9. Confidence intervals and uncertainty

- **Exact sign-flip test.** With 4 weeks there are 2⁴ = 16 sign patterns, so the smallest
  attainable two-sided p is **0.125**. WR capture@10 is at p = 0.25: three weeks up, one down.
- **The 4-week bootstrap intervals are degenerate.** They are roughly the range of the weekly
  values (WR capture@10: [−0.001, +0.167]) and are not real 95% intervals.
- **Honest scale:** from W10's weekly SD (0.0725), a 4-week mean carries about **±0.071** at 95%.
- **Nothing here is significant, and nothing could be.**
- **A positive interim is not replication, and the above-band size is not proof either way.**

## 10. Current protocol-permitted verdict

> **INCONCLUSIVE — CONTINUE PRE-REGISTERED 2026 HOLDOUT**, with **4 eligible weeks**, below the 8
> needed to read a direction.

**Not NOT REPLICATED:**

- the WR capture@10 interval is not below 0;
- the mean (+0.103) is far above the band's 2.5th percentile (−0.045).

**Not PARTIAL:** an interim look with fewer than 8 weeks cannot be PARTIAL.

**Not REPLICATED:** that verdict is final-look only.

**W10 §9:** not yet evaluable.

## 11. What remains before final confirmation

1. **Weeks 5–17.** Each joins when it passes §4: every game in the data, every team with stats,
   a canonical Friday board present.
2. **The first look able to read a direction has ≥ 8 eligible weeks**, likely after week 8. If
   WR capture@10 and @5 are both positive there, the verdict becomes PARTIAL REPLICATION;
   otherwise it continues.
3. **The decisive look comes after week 17,** once:
   - W10 §9: WR capture@10 and @5 positive, and the WR capture@10 CI above 0;
   - plus no guardrail breach for REPLICATED.

   Even with a real effect, the chance of §9 confirming is about 24% (pre-registration §6).
4. **At every look:**
   - the same committed runner and gates;
   - a fresh isolated ingest with A2's restore;
   - a reproduction of W5–W14 first.

   **No change to the model, features, eligibility or rules.**
5. **Watch:**
   - the null arm, now +0.028;
   - whether the above-band WR effect regresses toward W10's +0.022 as the season moves past the
     early weeks.

---

## Reproducibility and delivery

| | |
|---|---|
| prior research | W5–W13 re-run **14 / 14 byte-identical**; W14 look 1 re-ran byte-identical |
| look 2 | run twice (G11), byte-identical; sha256 `2a423650662adb02…` |
| tests | 1,907 pass |
| lint | clean |
| production diff vs `origin/main` | **EMPTY** |
| data (gitignored) | `data/w15/`: isolated database, raw 2026 snapshots, schedule snapshot, pipeline logs |
| artifact | `reports/weekly/w15_results.json` |

---

## LAYMAN'S TERMS

**What Claude did:**

- Added the newly finished week 4 to the frozen 2026 test, with W10 and today's model both
  unchanged and the eligible weeks locked in before scoring.
- Re-checked twelve ways that nothing leaked or broke, and re-ran all earlier research
  identically.

**What it means:**

- After four weeks W10 still picks better wide receivers, by more than history predicts. But four
  weeks is still too few to call it, and the rules say keep waiting.

**Next step:**

- Keep adding each finished week the same way, and make the first real call at eight weeks.
