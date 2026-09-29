# W12 — Timestamped pre-Friday information and RB breakouts

**Status: COMPLETE.**

**Pre-registered verdict: NO INCREMENTAL SIGNAL**, in Full PPR and Half-PPR. Per §7, **this
direction stops**.

**What that means:**

- **The only verifiable pre-Friday source, the NFL injury report, does not tell a real RB breakout
  from a blip.** A teammate's absence points the *wrong* way.
- **Given to the model, it leaves the RB top of the board unchanged.** It does improve the RB
  board's *overall* order.
- **News, coach and beat-reporter information cannot be tested:** no reconstructable timestamped
  history is reachable. That category is **data insufficient**, not "no signal".

**Provenance:**

- The audit and pre-registration were committed at `aa21437`, before any W12 outcome.
- The instruments were committed at `1892b25`.
- **Amendment A1 (`e12dd1a`)** closed a leak that gate G2 caught before any result was read (§7).

**Research only. Production diff EMPTY. ECR is a benchmark only, never a feature.** No PR, no
merge.

---

## 1. Research question

> Can genuinely timestamped pre-Friday information identify which sustained RB role risers are
> real breakouts, while preserving W10's historical-player-knowledge gains?

It was tested as two questions:

- **A.** Does the information exist and predict breakouts?
- **B.** Can Alpha exploit it?

## 2. Pre-registration

The full text is `docs/weekly/W12_PREREGISTRATION.md`. Frozen before any outcome:

- the cutoff instant;
- W11's `ROLE_UP` population;
- the BREAKOUT and ROLE_HELD outcomes (horizon: the ranked week);
- five Class A features;
- the coverage gate;
- two deciding tests (QA1, and RB capture@10 D − C ≥ +0.02 with conditions B2–B5);
- the ordered verdict and stopping rules;
- twelve gates;
- twelve predictions.

## 3–7. Data availability, sources, timestamp validity, coverage, leakage

The full audit is `docs/weekly/W12_DATA_AUDIT.md`. In short:

| information | source | class | historical coverage |
|---|---|---|---|
| **injury status and practice participation, incl. teammates** | NFL injury report via nflverse | **A**: last-modified UTC timestamps on 100% of rows | **2015–2024**. 2025 has no timestamps (**B**) |
| depth charts | ESPN via nflverse (daily captures) | **A** | **2025 only** |
| depth charts 2015–2024, weekly-roster reserve status | nflverse | **B**: no timestamps | — |
| news, coach statements, beat reporters | FantasyPros news API | serves only the latest ~10 items | **C** |
| | Wayback Machine | blocked by egress | **C** |
| | no other archive reachable | — | **untestable** |

**Cutoff:** 23:59:59 ET on the Friday before the week's first Sunday game. That Friday equals the
canonical snapshot date in 78 of 79 weeks.

**Coverage, 2021–2024 RB risers with an observable report (the gate passed):**

| | count |
|---|---:|
| risers | 666 |
| risers with a meaningful teammate vacancy | 40 (in 29 weeks) |
| BREAKOUTs | 166 |
| top-5 finishes | 81 |

Injury features are present for 94.8% of 2021–2024 panel rows and 0% of 2025.

**Timing:**

- About 92% of RB/WR/TE injury rows are last modified by the cutoff, the great majority in
  Friday's ~4 pm ET final report.
- **Under the strict cutoff (before Friday), only 2 risers have a vacancy.** In practice the
  week's injury information arrives Friday afternoon.

**Leakage audit:**

- Only 23 of 51,548 rows were edited after their game, and none after the season.
- Every comparison is converted to ET.
- The alias map covers the relocated team codes.
- **Gate G2 caught a real leak in the pre-registered own-status rule and it was fixed before any
  result (A1, §7).**

## 8. Breakout definition

| outcome | definition | role |
|---|---|---|
| **BREAKOUT** | a riser finishes in the **realized top 10** of the week's evaluated RBs (Full PPR, ties by `player_id`) | primary |
| ROLE_HELD | the week's touches − last season's per-game level ≥ 3 | secondary |

The horizon is the ranked week *w*. Both outcomes are future information, never features.

## 9. Baselines

| arm | definition |
|---|---|
| A | current Alpha |
| B | W10's model |
| C | W11's model (B + role) |
| **D** | **C + the 5 injury-report features** |
| N | C + the features permuted within (season, week, position) |
| D−tm, D−own | ablations |
| E | *exploratory, Class B*: D + the current-week nflverse depth chart |

- B and C reproduce W10's and W11's committed cells exactly (G3: 24,648 values).
- **Primary window: 2021–2024 (63 weeks).** The 79-week window is secondary.

## 10. Feature definitions (Class A, only rows modified ≤ the cutoff)

| feature | definition |
|---|---|
| `tm_out_opp` | touches/game of same-team, same-position teammates listed **Out/Doubtful** |
| `tm_q_opp` | the same for **Questionable** teammates |
| `tm_ret_opp` | the same for teammates **back** on the report after missing the team's last game |
| `own_status` | the player's own designation (0–3) |
| `own_practice` | the player's own practice participation (0–2) |

**VACANCY** = `tm_out_opp` ≥ 8.

---

## 11. Primary results

### Question A: does the information exist and predict breakouts? (RB risers, 2021–2024)

| test | with the signal | without | difference, 95% CI |
|---|---:|---:|---|
| **QA1 (decides): BREAKOUT, VACANCY vs not** | 12.5% (n 40) | 25.7% (626) | **−0.132 [−0.231, −0.026]** |
| QA2: the same, among risers W11's model ranks outside its top 10 | 11.1% (36) | 19.5% (466) | −0.084 [−0.183, +0.024] |
| QA3: ROLE_HELD, VACANCY vs not | 72.5% | 61.0% | +0.115 [−0.016, +0.242] |
| QA4: BREAKOUT, own status Questionable or worse | 16.3% (43) | 25.5% | −0.092 [−0.196, +0.030] |
| **QA5: BREAKOUT, a meaningful teammate *returning*** | 15.8% (57) | 25.8% | **−0.100 [−0.190, −0.007]** |
| QA-S: QA1 under the strict (pre-Friday) cutoff | **n = 2** | — | uninformative |
| QA-U: all RB player-weeks, VACANCY vs not | 12.5% (288) | 13.4% (4,154) | −0.009 [−0.049, +0.033] |
| QA-D: 2025 depth, exploratory. Riser listed RB1 at the last capture before the cutoff | 39.4% (71) | 14.3% (49) | +0.252 [+0.109, +0.380] (15 weeks, not tested as incremental) |

**QA1 excludes zero on the wrong side.** When a meaningful teammate is out, a riser's role holds
somewhat *more* often (QA3), but the riser breaks out *less* often.

- The sample is small: 5 breakouts in 40.
- The pre-registered test required a positive effect, so **"information exists" is false**.
- The negative association is reported as found, not explained away.
- One reading, not tested: a riser whose teammate is out gains carries in a thinner, injury-hit
  offense, not a starring role.

**Two signals work as expected but are narrow:**

- a meaningful teammate *returning* lowers the breakout rate (QA5);
- a riser's own injury designation points the same way (QA4, not significant).

**Depth charts carry an association in the one Class A season.** Being the listed RB1 is not
tested against what the model already knows; depth *changes* numbered 5.

### Question B: can Alpha exploit it? (D − C, 63 weeks, Full PPR)

\* = 95% CI excludes 0. MDE capture@10: RB 0.012, WR 0.012, FLEX 0.011.

| | capture@5 | capture@10 | capture@20 | capture@50 | Spearman | pairwise |
|---|---:|---:|---:|---:|---:|---:|
| **RB** | −0.009 | **−0.002** | +0.005 | +0.004\* | **+0.0067\*** | +0.0027\* |
| WR | +0.009 | +0.003 | +0.005 | +0.002 | +0.0014 | +0.0008 |
| TE | +0.014\* | +0.002 | −0.003 | +0.000 | +0.0015 | +0.0007 |
| FLEX | −0.002 | **+0.018\*** | −0.005 | +0.003 | +0.0026\* | +0.0011\* |

| condition | result |
|---|---|
| B1: RB capture@10 ≥ +0.02 with CI > 0 | ✗ −0.002, CI [−0.014, +0.010] |
| B2: RB capture@10 beats the null | ✗ D − N +0.001 |
| B3: RB consistent | ✗ positive in 2/4 seasons, 0/4 LOSO folds significant |
| B4: no breach | ✔ |
| B5: WR kept | ✔ D − C +0.003; **D − A +0.021\*** |

**Verdict: NO INCREMENTAL SIGNAL**, because QA1 does not hold positively and B1 fails.

## 12. RB results

**The top of the board does not move.**

| RB top of board, D − C | value |
|---|---|
| capture@10 | −0.002 |
| capture@5 | −0.009 |
| top-10 overlap | 91% (D changes about 1 of 10 RBs a week) |
| weeks D wins–loses–ties at capture@10 | 19–26–18 |

**What changed for risers** (per week, 63 weeks):

| | A | B | C | **D** | E (Class B) |
|---|---:|---:|---:|---:|---:|
| missed breakouts (top-5 finishers ranked outside 24) | 0.127 | 0.238 | 0.238 | **0.222** (−0.016, not significant) | 0.159 (**−0.079\*** vs C) |
| false top-10 risers (finish outside 24) | 0.952 | 0.651 | 0.635 | **0.730** (**+0.095\***) | 0.730 (+0.095\*) |
| riser regret (capture lost on top-10 risers left out) | 0.115 | 0.154 | 0.154 | 0.149 | 0.147 |

- **D trades:** slightly fewer missed breakouts for more false top-10 risers. The net top-of-board
  effect is zero.
- **The exploratory Class B depth chart** recovers about 70% of the misses W10 added: 0.238 → 0.159, against current Alpha's 0.127.
  It pays the same false-positive price, and it lowers WR capture@5 (−0.026\*), TE capture@10
  (−0.015\*) and FLEX capture@10 (−0.019\*). **It is not a solution even ignoring its leakage risk.**

**Where D does help RB: the whole board.**

- Spearman is +0.0067\*, positive in 3/4 seasons, **significant in 4/4 LOSO folds**, and beats
  the null (+0.0063\*).
- Most of it comes from the teammate features (+0.0066\* when they are removed from D).

**The injury report helps Alpha order the middle and bottom of the RB board** (who will not get
the ball), not find the top.

## 13. WR guardrail

| | capture@10 vs A | capture@5 vs A | Spearman vs A |
|---|---:|---:|---:|
| B (W10) | +0.023\* | +0.033\* | +0.007\* |
| C (W11) | C − B −0.005 | | |
| **D (W12)** | **+0.021\*** | **+0.038\*** | +0.008\* |

W10's WR gain is intact. 79 weeks: D − A capture@10 +0.020\*.

## 14. TE

| TE, D − C | value |
|---|---|
| capture@5 | +0.014\*: 4/4 seasons positive, 3/4 LOSO significant; Half-PPR +0.016\* |
| capture@10 | +0.002 |

Secondary and unadjusted.

## 15. Information-value decomposition

| category | status | effect |
|---|---|---|
| **teammate availability** | Class A, tested | carries most of D's **RB whole-board** gain: Spearman +0.0066\* when removed. **No top-of-board RB effect.** Vacancy predicts breakouts *negatively* (QA1); a returning teammate predicts them negatively (QA5) |
| **own injury / practice** | Class A, tested | carries D's **FLEX top-10** gain: FLEX capture@10 +0.016\* when removed. RB Spearman +0.0030\* |
| **depth chart** | Class A only in 2025 (16 weeks); Class B 2015–2024 | 2025: listed-RB1 risers break out 39% vs 14% (association only). Class B arm: fewer missed breakouts, no net gain, WR/TE/FLEX harm |
| **coach / beat-reporter / news** | **no reconstructable source** | **DATA INSUFFICIENT**, untestable here |
| other | none | — |

**The most useful structured signal is one Alpha has never seen: a player's own Friday injury
designation.** Its value shows up across positions (FLEX), not in finding RB breakouts.

## 16. Season-level robustness (D − C, 2021–2024)

| cell | 2021 | 2022 | 2023 | 2024 | LOSO folds significant |
|---|---:|---:|---:|---:|---:|
| RB capture@10 | −0.009 | −0.010 | +0.011 | +0.002 | 0/4 |
| RB capture@5 | +0.007 | −0.035 | −0.006 | −0.003 | 0/4 |
| RB Spearman | +0.007 | −0.001 | +0.010 | +0.011 | **4/4** |
| WR capture@10 | −0.007 | +0.016 | +0.010 | −0.008 | 0/4 |
| **FLEX capture@10** | +0.008 | +0.024 | +0.011 | +0.030 | **4/4** |
| TE capture@5 | +0.017 | +0.023 | +0.005 | +0.011 | 3/4 |

**Periods (RB capture@10):** EARLY +0.002, MID −0.015\*, LATE +0.011.

**FLEX capture@10 by period:** EARLY +0.035\*, MID −0.003, LATE +0.025\*.

**A caution on FLEX:** against the permuted-feature null, FLEX capture@10 is +0.009, **not
significant** in the primary window (+0.010\* over 79 weeks). Part of the +0.018 is a generic
model-perturbation effect. **The FLEX result is suggestive, not established.**

## 17. Half-PPR robustness

**Verdict: NO INCREMENTAL SIGNAL** (identical).

| D − C | Half-PPR |
|---|---:|
| RB capture@10 | −0.001 |
| RB Spearman | +0.0067\* |
| FLEX capture@10 | +0.017\* |
| TE capture@5 | +0.016\* |
| WR capture@10 | +0.003 |

## 18. Limitations

- **Retrospective:** 2021–2024 shaped the hypothesis since W9. There is no 2026 data.
- **Only one Class A source for the week's role changes**, and it has blind spots:
  - it holds only the *final* version of each row, so no day-by-day status history exists;
  - **injured-reserve players are not on it**, so long-term vacancies are invisible;
  - the Friday report arrives at about 4 pm ET, so any earlier product cutoff sees almost none of
    it (QA-S: n = 2).
- **Depth charts are Class A for one season**, and news for none. The categories most plausibly
  tied to breakouts (announced role changes, beat reports) could not be tested at all.
- **Small counts where they matter:** 40 vacancy risers with 5 breakouts, and 57 returning-teammate
  risers.
- **The secondary findings (FLEX, TE capture@5, RB Spearman) are unadjusted** and were not deciding
  tests.

## 19. Verdict

**NO INCREMENTAL SIGNAL** for the pre-registered question: pre-Friday information identifying
which sustained RB risers are real breakouts.

- The Class A source has enough coverage to test (the gate passed), so this is a genuine null, not
  data insufficiency.
- **For news, coach and beat-reporter information: DATA INSUFFICIENT.** No reconstructable
  timestamped history is reachable.
- **By the stopping rules, the RB-breakout direction stops.**

**What the evidence does establish:**

1. **The RB breakout problem is not solvable with verifiable pre-Friday injury information.** A
   teammate's absence does not mark a real breakout; if anything it marks the opposite.
2. **The injury report is still informative:**
   - it improves RB **whole-board** ordering robustly (all four LOSO folds, beats the null);
   - it points to a **FLEX top-10** gain from players' own designations: robust across seasons,
     folds and Half-PPR, but not clear of the null in the primary window.
3. **Current-week depth charts, even untimestamped,** recover some missed RB breakouts but add as
   many false ones, and hurt other positions.

## 20. Exact next research question

> **Does a player's own Friday injury designation improve the cross-position (FLEX) top 10 beyond
> W10's model, in a pre-registered confirmatory test with 2026 held out?**

**Why this question:**

- It is the one positive, robust-looking signal W12 found.
- It uses information Alpha has never had.
- It is Class A for 2015–2024.
- W12 could not separate it from the null.

**Two practical notes:**

- The 2025 injury file has no timestamps, so a confirmatory test also needs **timestamped
  collection going forward**: the injury report, and ideally daily depth charts and news. Without
  that, the questions W12 could not test stay untestable.
- **The RB-breakout question should not be reopened** without a new Class A source (for example
  forward-collected depth charts or role reports).

---

## Validity

**Reproduction first.** W5 through W11 reproduced **12/12 byte-identical**.

**All twelve gates pass** (`scripts/research/w12_validity_gates.py`):

| gate | result |
|---|---|
| G1 parity | 26,097/26,097 |
| G2 pre-cutoff | adversarial Out rows 1 second late moved 0/40 feature sets; 1 second early counted 40/40; deleting all 3,734 post-cutoff rows moved 0 values |
| G3 B = W10, C = W11 | 24,648 values, 0 mismatches |
| G4 Class A only | 2025 features all missing; injury seasons 2015–2024; `depth_now` only in arm E |
| G5 ECR never a feature | 5 declared training calls plus W10's B |
| G6 walk-forward | 0 leaks |
| G7 joins | 0 unmapped team codes; 100% gsis mapping; 300/300 independent SQL checks of `tm_out_opp` |
| G8 order-free | 0 values differ with every input reversed |
| G9 universe / A | 24,648 values, 0 mismatches; 79 and 63 weeks |
| G10 determinism | two runs byte-identical (`c23d5741…`) |
| G11 upstream | 12/12 |
| G12 null | N − C capture@5/@10 CIs include 0 at RB, WR and TE |

**Amendment A1: a leak caught before any result.**

- **Symptom.** The first gate dry run failed G2(c): deleting post-cutoff rows moved 276 values.
- **Cause.** The pre-registered rule marked a player's own status as *unknown* when their row was
  edited after the cutoff. That revealed that a post-cutoff edit existed.
- **Fix.** Every feature is now computed only from rows at or before the cutoff. A later-edited
  player counts as not listed, which is the documented healthiness bias.
- **Tests.** A regression test pins the invariance.

## Predictions (§11)

| # | prediction | outcome |
|---|---|---|
| 1 | coverage gate passes | ✔ |
| 2 | QA1 positive | ✗ significantly negative |
| 3 | QA2 positive, CI includes 0 | ✗ negative, CI includes 0 |
| 4 | QA4 negative | ~ negative, not significant |
| 5 | QA5 negative | ✔ −0.100\* |
| 6 | RB capture@10 D − C +0.000 to +0.008 | ~ −0.002: below the bar, as predicted |
| 7 | WR preserved | ✔ |
| 8 | verdict NOT ACTIONABLE | ✗ NO INCREMENTAL SIGNAL |
| 9 | teammate features carry most of D's effect | ~ at RB yes; FLEX's gain is own-status |
| 10 | arm E moves RB more than D | ~ fewer missed breakouts, no capture gain |
| 11 | 2025 depth changes too few | ✔ 5 |
| 12 | Half-PPR agrees | ✔ |

**Five right, four partly right, three wrong.**

## Files

| file | role |
|---|---|
| `docs/weekly/W12_DATA_AUDIT.md` | the audit |
| `docs/weekly/W12_PREREGISTRATION.md` | the pre-registration, with A1 |
| `src/alpha_squad/evaluation/weekly/timestamped.py` | cutoff, features, verdict (15 tests) |
| `scripts/research/w12_timestamped.py` | the runner |
| `scripts/research/w12_validity_gates.py` | G1–G12 |
| `reports/weekly/w12_results.json` | every cell and summary |

**Reproduce:**

```
uv run python scripts/research/w12_timestamped.py
uv run python scripts/research/w12_validity_gates.py --repro-summary <W5-W11 record>
```

---

## LAYMAN'S TERMS

**What Claude did:**

- Checked every source of "news before Friday" that can be proven to have existed in time. Only
  the NFL's injury report qualifies (2015–2024), with daily depth charts for 2025 alone. Historical
  news and beat reports could not be reconstructed.
- Asked whether that information tells a real running-back breakout from a one-week blip, and
  whether adding it to Alpha improves the weekly top 10.

**What it means:**

- It does not. A teammate being out does not mark a breakout, and Alpha's RB top 10 did not
  improve. So this path stops.
- The injury report still helps Alpha order the rest of the RB board. A player's own injury tag
  may help the overall FLEX top 10, though that is not yet proven.

**Next step:** Test, in one focused pre-registered study, whether a player's own Friday injury
designation improves the FLEX top 10, and start collecting timestamped injury, depth-chart and
news data now, because the missing history is what makes the bigger questions untestable.
