# W11 — Pre-registration: quiet week or real role change?

**Status: PRE-REGISTERED, NOT EXECUTED.** Committed before any W11 quantity comparing boards,
models or outcomes was computed. §2 records coverage and timing facts only.

> **No change below after seeing results without a dated amendment here.**

Authority: `docs/weekly/W10_HISTORICAL_RESULTS.md` (the hypothesis), W5–W10 results, `CLAUDE.md`.
Decision record: `docs/DECISIONS.md` D119.

---

## 0. What is already known: read this first

**W10's movement attribution motivated W11.** It split B − A capture@10 by W10's categories:

| W10 category | RB | WR | TE |
|---|---:|---:|---:|
| QUIET_STAR (prior top-12, last game below prior PPG) | +0.041\* | +0.050\* | +0.026\* |
| ROLE_STRONGER_NOW (3-game touches ≥ prior + 3) | −0.055\* | −0.050\* | −0.009\* |
| ROLE_STRONGER_BEFORE (3-game touches ≤ prior − 3) | +0.015\* | +0.008\* | +0.001 |

W10's "recent" window crossed season boundaries, and it had no persistence rule. **W11's classes are
new definitions** (§3): current-season games only, a persistence rule, snap share as a second
measure, and QUIET not limited to elite players. So the W11 numbers are unseen, but they will be
correlated with W10's.

**Two known risks:**

- **The ROLE_DOWN direction may not hurt.** W10's crude "role shrank" category *helped* B.
- **The 3-touch threshold is W10's `ROLE_GAP`.** It is re-used, not chosen fresh.

**The 2021–2025 weeks have shaped this hypothesis, so W11 is retrospective research, not
confirmation.** The repository holds no 2026 data; the 2026 protocol is frozen in §10.

---

## 1. The question

> Can Alpha keep the benefit of remembering established players while recognizing when their
> current role has genuinely changed?

**Two stages, in order:**

1. **Mechanism (§4).** Does a pre-Friday current-vs-history role comparison separate where W10's
   memory helps (quiet weeks) from where it hurts (real role changes)?
2. **Model (§5–§7).** Only if the mechanism is established: does giving W10's model that
   comparison improve it, above all at RB, without giving back the WR gain?

---

## 2. Data and timing facts (coverage only)

| role measure | available? | used |
|---|---|---|
| opportunity per game (targets + carries) | yes: `player_week_stats` | **yes**, on the scale of W10's `prior_opp_pg` |
| offensive snap share | yes: `offense_snap_pct`, 0–1 scale, 99.9% non-null | **yes**, on the scale of `prior_snap` |
| target share | yes | no; it is WR/TE-specific and is already part of opportunity |
| carry share | derivable from team carries | no; RB-specific and part of opportunity |
| route participation | **absent from every source** | cannot be tested |
| teammate absence, coaching or personnel change | no timestamped source | visible only through the usage it causes |

**Why these two measures.** Opportunity per game is the axis on which W10's cost appeared.
Snap share is participation: the starter/backup signal. Both are defined identically for RB, WR
and TE, so nothing is tuned per position.

**Timing.**

- The current role uses only this season's `player_week_stats` rows with `week` < the predicted
  week. All of those games are complete before the Friday of the predicted week; Thursday games
  of the predicted week belong to that week and are excluded.
- **The current-season game count equals Alpha's own `games_played_prior` on all 55,093 panel
  rows (0 mismatches).**
- Last season's role is W9/W10's durable row from season S − 1.

**Coverage of the evaluated universe** (79 weeks, primary thresholds, player-weeks):

| | NO_PRIOR | TOO_EARLY | ROLE_UP | ROLE_DOWN | ROLE_MIXED | TRANSIENT | QUIET | STABLE | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RB | 1,180 | 571 | 830 | 959 | 0 | 1,095 | 746 | 549 | 5,930 |
| WR | 1,770 | 877 | 1,258 | 1,137 | 7 | 1,575 | 1,614 | 1,140 | 9,378 |
| TE | 741 | 525 | 534 | 465 | 2 | 780 | 903 | 792 | 4,742 |

TOO_EARLY is 25–30% of EARLY-period player-weeks and 1–4% later.

**Share of each universe classed as a sustained change (ROLE_UP, ROLE_DOWN or ROLE_MIXED):**

| | LOOSE | PRIMARY | STRICT |
|---|---:|---:|---:|
| RB | 41.0% | 30.2% | 22.6% |
| WR | 37.2% | 25.6% | 17.3% |
| TE | 33.3% | 21.1% | 12.9% |

---

## 3. The role-change definition (fixed)

For player *i* in week *w* of season *S*:

- **Last season's role:** `prior_opp_pg`, `prior_snap`, `prior_ppg` and `has_prior`, exactly
  W10's durable features.
- **Current games:** *i*'s appearances in season *S* with week < *w*, in week order. The current
  window is the last **3** of them.
- **Per-game deviation** in game *g*:
  - `opp_g − prior_opp_pg` (touches);
  - `snap_g − prior_snap` (share points). A missing snap value is skipped, never zero.
- **Thresholds** (touches, snap-share points):

  | set | τ_opp | τ_snap | role |
  |---|---:|---:|---|
  | **PRIMARY** | **3.0** | **0.15** | verdict and arm C |
  | LOOSE | 2.0 | 0.10 | mechanism sensitivity only |
  | STRICT | 4.0 | 0.20 | mechanism sensitivity only |

- **A game is UP** if either deviation ≥ +τ, **DOWN** if either ≤ −τ. It can be both when the
  measures conflict.
- **Persistence:** a change is **sustained** only if it holds, in the same direction, in **each of
  the last 2** current games.

**Classes** (first match wins):

| class | rule |
|---|---|
| `NO_PRIOR` | no season S − 1 appearance (`has_prior` ≠ 1) |
| `TOO_EARLY` | fewer than 2 current games |
| `ROLE_UP` | sustained UP, not sustained DOWN |
| `ROLE_DOWN` | sustained DOWN, not sustained UP |
| `ROLE_MIXED` | sustained both ways (conflicting measures) |
| `TRANSIENT` | the last game deviates, but it is not sustained (a one-game fluctuation) |
| `QUIET` | role intact, and PPR per game over the current window < `prior_ppg` |
| `STABLE` | role intact, production at or above last season |

**Groups:**

- **Group A, stable/quiet:** QUIET ∪ STABLE.
- **Group B, real role change:** ROLE_UP ∪ ROLE_DOWN ∪ ROLE_MIXED.

**Arm C's three features** (PRIMARY only):

| feature | definition |
|---|---|
| `role_d_opp` | current-window mean touches − `prior_opp_pg` |
| `role_d_snap` | current-window mean snap share − `prior_snap` |
| `role_shift` | +1 ROLE_UP, −1 ROLE_DOWN, 0 for MIXED/TRANSIENT/QUIET/STABLE |

- `role_d_opp` and `role_d_snap` are missing with no current game or no prior season.
- `role_shift` is missing for NO_PRIOR and TOO_EARLY.
- CatBoost treats missing values natively. For 2015 training rows everything is missing, because
  that season has no prior season.

---

## 4. Stage 1 — the mechanism test

**Setup.**

- Arm A is production's stored predictions.
- Arm B is W10's `ALPHA_PLUS_HISTORICAL`, retrained identically; G3 proves it.
- Both run on W7–W10's universe (79 weeks, Friday cutoff), per position.

**Measurements** (PRIMARY set, Full PPR, week-cluster inference as in W6–W10):

| | quantity | desired sign |
|---|---|---|
| **M1** | B − A capture@10 attributed to **QUIET** movers (exact split, W10's instrument) | **> 0**, CI excluding 0 (history helps) |
| **M2** | B − A capture@10 attributed to **ROLE_UP** movers | **< 0**, CI excluding 0 (history hurts) |
| M3 | among **substantial movers** (see below), the rate at which B's move is **wrong** (B's rank farther from the realized rank than A's), Group B minus Group A | > 0, CI excluding 0 |
| R | this week's realized touches − `prior_opp_pg`, for **ROLE_UP** minus **TRANSIENT-up** | > 0, CI excluding 0 |

- **Substantial movers:** in either board's top 24, and moved at least 3 ranks between A and B.
- **M3 is the "can we see it before the game" test.**
- **R is the persistence test:** does a sustained change persist into the predicted week more
  than a one-game spike? The realized week is used only as the outcome.

**The mechanism is ESTABLISHED at a position if M1 and M2 both hold.** M3 and R are reported and
answer questions 1 and 9; they are not required.

**The stage-1 rule. Stage 2 runs only if the mechanism is established at RB or WR** (PRIMARY, Full
PPR). Otherwise the verdict is **MECHANISM NOT ESTABLISHED**, the model is not modified, and the
report says the W10 interpretation may be incomplete.

**Also reported** (never selecting):

- every class's attribution;
- ROLE_DOWN versus TRANSIENT-down;
- the LOOSE and STRICT sets;
- EARLY/MID/LATE and per-season M1/M2;
- Half-PPR;
- B's rank-error change against A by class;
- W5's misses (predicted top-10 / realized outside 24; realized top-5 / predicted outside 24) for
  A and B by class.

---

## 5. Stage 2 — arms

| arm | definition | role |
|---|---|---|
| **A: CURRENT ALPHA** | production's stored predictions | reference |
| **B: HISTORICAL ALPHA** | W10's exact model (production's CatBoost + the 7 durable features) | **the baseline to beat** |
| **C: HISTORY + ROLE-AWARE** | B + the 3 PRIMARY role features (§3). Same CatBoost, hyperparameters, MAE loss, walk-forward `[2015, S − 1]`, target, universe, cutoff and scoring | **the test** |
| N: ROLE NULL | B + the 3 role features **permuted across players within (season, week, position)** | adding role-shaped noise must do nothing |

**The only change from B to C is the current-vs-history role comparison. ECR is a benchmark only:
never a feature, target, tiebreak or selector** (G5).

---

## 6. Metrics and statistics

- **Positional** (RB, WR, TE): capture@5, @10, @20 (primary depths), @50, Spearman, Kendall,
  pairwise, precision@10.
- **FLEX:** the existing pooled path, no FLEX model. capture@5, @10, @25, Spearman, pairwise.
- **Comparisons:**
  - **primary: C − B;**
  - secondary: B − A, C − A;
  - null: N − B, C − N;
  - ECR − C for context.
- **Periods** (fixed by week number): EARLY 1–6 (24 evaluated weeks), MID 7–12 (30), LATE 13–17
  (25). **Hypothesis: C − B grows through the season**, because role evidence accumulates.
- **Attribution:** C − B capture@10 split by PRIMARY class, and N − B the same way.
- **Statistics:** 79 weeks, paired within week, bootstrap over weeks (10,000 resamples, seeds
  0–9). MDE is the CI half-width. W–L–T counts, Wilcoxon, per-season, leave-one-season-out.
- **Point diagnostics** (secondary): MAE and bias of B and C, Full PPR only.

---

## 7. Stage-2 verdict — fixed now, evaluated in this order

**Guardrail breach:** a C − B difference with a CI excluding 0, negative, and of magnitude
≥ 0.005, in any of:

- capture@5, @10, @20 or @50, Spearman or pairwise at RB, WR or TE;
- FLEX capture@10, @25, Spearman or pairwise.

FLEX capture@5 is monitored and reported, but is not breach-eligible.

**WR harm:** WR capture@10 C − B is a breach, **or** its point estimate is ≤ −0.010. The W10 gain
must not materially deteriorate.

**The five SUCCESS conditions:**

- **S1 (RB improves):** RB capture@10 C − B has a CI excluding 0 **and** either:
  - it is ≥ +0.02; or
  - the C − B attribution to ROLE_UP is ≥ +0.02 with a CI excluding 0. This reading of "reduces
    the W10 RB tradeoff" still requires a significant RB top-10 gain.
- **S2 (WR preserved):** no WR harm, **and** WR capture@10 C − A has a CI excluding 0 above 0.
- **S3 (no damage):** no guardrail breach.
- **S4 (beyond noise):** RB capture@10 C − N has a CI excluding 0 above 0.
- **S5 (consistent):** RB capture@10 C − B is positive in ≥ 4 of 5 seasons, **and** its CI
  excludes 0 in ≥ 4 of 5 leave-one-season-out folds.

**The verdict, in order:**

| order | verdict | rule |
|---|---|---|
| 0 | **MECHANISM NOT ESTABLISHED** | stage 1 failed at both RB and WR (stage 2 not run) |
| 1 | **SUCCESS** | S1–S5 all hold |
| 2 | **TRADEOFF** | S1 holds, but there is a breach or WR harm. Decision tree: "improves RB but hurts WR". Never averaged |
| 3 | **HARM** | a breach or WR harm, and S1 fails |
| 4 | **PARTIAL** | any of: S1 holds (S4 or S5 failed); RB capture@10 C − B ≥ +0.02 (CI may include 0); the C − B ROLE_UP attribution has a CI excluding 0 above 0; any capture@10 C − B at RB, WR or TE ≥ +0.02 with a CI excluding 0 |
| 5 | **NO EFFECT** | anything else |

**Half-PPR replicates only and never selects.**

---

## 8. Robustness

- Per season and leave-one-season-out for C − B at RB, WR, TE and FLEX: capture@5, @10, @20 and
  Spearman.
- Half-PPR.
- The LOOSE and STRICT mechanism sets.
- The null arm N.
- Dependence on one season, position or depth is reported from the above.

---

## 9. What W11 may NOT do

- Modify production, or `models/`, `league/`, `api/`, `cli.py`, `market/`, `features/`,
  `identity/`, `ingest/` or `sources/`.
- Add ECR, experts, news, injuries or Vegas.
- Try other thresholds, windows, persistence rules, feature weights, architectures or
  per-position variants.
- Select anything by LOOSE, STRICT, Half-PPR or a period.
- Use 2026.

---

## 10. 2026: the out-of-sample protocol, frozen now

**Frozen before any 2026 data exists:**

- the §3 definition (PRIMARY thresholds, window 3, persistence 2, first-match classes);
- the 3 features;
- W10's 7 durable features;
- the CatBoost configuration.

Once 2026 weeks 1–17 and production's 2026 predictions are ingested, run:

```
w11_mechanism.py --seasons 2026
w11_role_model.py --seasons 2026
```

Arm B and arm C are trained through 2025.

**If W11 is SUCCESS, 2026 confirms it** if RB capture@10 C − B is positive **and** WR capture@10
C − A is positive **and** RB capture@10 C − B has a CI excluding 0. A null in 16 weeks is weak
evidence and will be called that. **No 2026 value may inform any W11 choice.**

---

## 11. Validity and leakage gates

**Stage 1's gates must pass before stage 1 is read. All gates must pass before stage 2 is read.**

| gate | check |
|---|---|
| **G1** | parity: the one-change trainer with no added feature reproduces production exactly |
| **G2** | the current role is pre-Friday. For 40 seeded evaluated (season, week) pairs, rebuild the role table from a database holding only rows before that week. Every role feature and class for that week is unchanged. The durable table passes W10's deletion test |
| **G3** | arm B is W10's arm. B's per-week cells (positional and FLEX, Full and Half-PPR) equal W10's committed `ALPHA_PLUS_HISTORICAL` cells |
| **G4** | no future information. No injury, depth, news, Vegas, ECR or realized token in the 3 role features. Scrambling season S's week-*w*-and-later outcomes moves 0 role values for week *w*. As a positive control, week *w* + 1's values do move |
| **G5** | ECR is never a feature. Exactly three training calls: B in `w11_mechanism.py`; C and N in `w11_role_model.py`. Their frames come only from `durable_panel` and `role_panel`, and `role_table` reads only `player_week_stats` |
| **G6** | walk-forward: no training frame contains the predicted season |
| **G7** | joins: unique role keys. The current-game count equals `games_played_prior` on every panel row. `role_d_opp` and `role_d_snap` for 300 seeded player-weeks equal an independent SQL computation |
| **G8** | order-free: the role table is identical when its input rows arrive reversed |
| **G9** | the universe and arm A: CF_A and ECR cells equal W10's committed cells; 79 weeks |
| **G10** | determinism: both stages' outputs are byte-identical on a re-run |
| **G11** | upstream: W5–W10's 10 artifacts are byte-identical |
| **G12** | null: arm N's capture@5 and @10 effects against B have CIs including 0 at RB, WR and TE |

**If a gate fails: stop, fix, re-run, document, then read.**

---

## 12. A priori predictions (unknown quantities)

1. **M1 holds at RB and WR:** history helps QUIET players.
2. **M2 holds at RB and WR:** history hurts ROLE_UP players.
3. **M3 holds at RB:** B's moves are wrong more often for role changers. WR is uncertain.
4. **R holds at RB and WR:** sustained increases persist into the week more than one-game spikes.
5. **ROLE_DOWN's attribution is ≥ 0.** History does *not* hurt role-down players, repeating W10.
6. **The mechanism is established, so stage 2 runs.**
7. **RB capture@10 C − B is small and positive** (+0.005 to +0.015), below the +0.02 bar. CatBoost
   already sees B's `prior_opp_pg` and Alpha's 3-game touches.
8. **WR is preserved:** C − B WR capture@10 is within ±0.01.
9. **C − B is largest LATE.**
10. **Verdict: PARTIAL.**
11. The null arm does nothing.
12. Half-PPR agrees.

---

## 13. Amendments

*(None yet.)*
